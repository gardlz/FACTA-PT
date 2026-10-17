"""Shared training protocol: effective batch, fixed-horizon LR schedule, adaptation family.

Optimiser settings stay at the Transformers defaults except the effective batch size,
the warm-up ratio, the learning rate and the scheduler horizon.
"""

from __future__ import annotations

import math


def gradient_accumulation_steps(effective_batch_size: int, physical_batch_size: int) -> int:
    """Accumulation steps for the effective batch; the physical batch must divide it."""
    if effective_batch_size <= 0 or physical_batch_size <= 0:
        raise ValueError("Batch sizes must be positive integers.")
    if physical_batch_size > effective_batch_size:
        raise ValueError(
            f"physical batch ({physical_batch_size}) cannot exceed effective batch "
            f"({effective_batch_size}) in this protocol."
        )
    if effective_batch_size % physical_batch_size != 0:
        raise ValueError(
            f"effective batch {effective_batch_size} is not divisible by physical batch "
            f"{physical_batch_size}. Choose e.g. 8, 4, 2 or 1 for effective batch 8."
        )
    return effective_batch_size // physical_batch_size


def _create_fixed_horizon_scheduler(trainer, num_training_steps: int, optimizer=None):
    """Linear schedule over the reference horizon, which may be longer than the actual run.

    In the final training the run stops at the selected epoch while the schedule keeps the
    cross-validation horizon, so the learning-rate trajectory is the one that was validated.
    """
    from transformers import get_scheduler

    if trainer.lr_scheduler is not None:
        return trainer.lr_scheduler

    actual_epochs = float(trainer.args.num_train_epochs)
    horizon_epochs = float(trainer.scheduler_horizon_epochs)
    if actual_epochs <= 0 or horizon_epochs <= 0:
        raise ValueError("Training epochs and scheduler horizon must be positive.")
    if horizon_epochs < actual_epochs:
        raise ValueError(
            f"scheduler horizon ({horizon_epochs}) cannot be shorter than actual training "
            f"duration ({actual_epochs})."
        )

    # Scale the run's exact update-step count by the epoch ratio.
    horizon_steps = max(1, int(math.ceil(num_training_steps * horizon_epochs / actual_epochs)))
    warmup_steps = trainer.args.get_warmup_steps(horizon_steps)
    opt = optimizer if optimizer is not None else trainer.optimizer
    trainer.lr_scheduler = get_scheduler(
        trainer.args.lr_scheduler_type,
        optimizer=opt,
        num_warmup_steps=warmup_steps,
        num_training_steps=horizon_steps,
    )
    trainer.scheduler_horizon_steps = horizon_steps
    return trainer.lr_scheduler


def make_horizon_trainer_classes():
    """Trainer subclasses with the fixed-horizon scheduler (Transformers imported lazily)."""
    from transformers import Seq2SeqTrainer, Trainer

    class HorizonTrainer(Trainer):
        def __init__(self, *args, scheduler_horizon_epochs=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.scheduler_horizon_epochs = (
                float(scheduler_horizon_epochs)
                if scheduler_horizon_epochs is not None
                else float(self.args.num_train_epochs)
            )
            self.scheduler_horizon_steps = None

        def create_scheduler(self, num_training_steps: int, optimizer=None):
            return _create_fixed_horizon_scheduler(self, num_training_steps, optimizer)

    class HorizonSeq2SeqTrainer(Seq2SeqTrainer):
        def __init__(self, *args, scheduler_horizon_epochs=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.scheduler_horizon_epochs = (
                float(scheduler_horizon_epochs)
                if scheduler_horizon_epochs is not None
                else float(self.args.num_train_epochs)
            )
            self.scheduler_horizon_steps = None

        def create_scheduler(self, num_training_steps: int, optimizer=None):
            return _create_fixed_horizon_scheduler(self, num_training_steps, optimizer)

    return HorizonTrainer, HorizonSeq2SeqTrainer


def loss_seq2seq_normalizada(outputs, labels, num_items_in_batch=None):
    """Seq2seq cross-entropy normalised by the target tokens of the whole accumulation window.

    T5's loss averages per micro-batch, so under gradient accumulation it scales the gradient
    (changing clipping) and weighs micro-batches equally. Identical to it without accumulation.
    """
    import torch

    logits = outputs["logits"] if isinstance(outputs, dict) else outputs.logits
    perda = torch.nn.functional.cross_entropy(
        logits.view(-1, logits.size(-1)),
        labels.view(-1),
        ignore_index=-100,
        reduction="sum",
    )
    if num_items_in_batch is None:
        n = (labels != -100).sum()
        return perda / torch.clamp(n, min=1)
    if torch.is_tensor(num_items_in_batch):
        num_items_in_batch = num_items_in_batch.to(perda.device)
    return perda / num_items_in_batch


FAMILIAS = ("full_fine_tuning", "lora", "qlora")


def aplicar_adaptacao(model, familia: str, *, r: int, alpha: int, dropout: float):
    """Apply the adaptation family (decided by model size in models_manifest.json).

    full_fine_tuning: unchanged; lora: adapters on all linear layers over a frozen backbone;
    qlora: the same over a 4-bit NF4 backbone, after `prepare_model_for_kbit_training`.
    """
    if familia not in FAMILIAS:
        raise ValueError(f"família de adaptação desconhecida: {familia!r} (esperado {FAMILIAS})")
    if familia == "full_fine_tuning":
        return model

    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training

    if familia == "qlora":
        model = prepare_model_for_kbit_training(model)

    seq2seq = bool(getattr(getattr(model, "config", None), "is_encoder_decoder", False))
    cfg = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM if seq2seq else TaskType.CAUSAL_LM,
        r=r, lora_alpha=alpha, lora_dropout=dropout, bias="none",
        target_modules="all-linear",
    )
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    return model
