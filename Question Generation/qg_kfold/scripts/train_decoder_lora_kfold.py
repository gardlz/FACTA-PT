"""Fine-tuning of decoder-only models on one cross-validation fold (LoRA or QLoRA).

Trains for the whole horizon without early stopping and evaluates the gold dev fold at
the end of every epoch. Only the `qlora` family loads the backbone in 4-bit NF4; the CLEVER
test set is never read here.
"""

import argparse
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kfold_eval import constroi_callback, constroi_callback_lr
from training_protocol import (aplicar_adaptacao, gradient_accumulation_steps,
                               make_horizon_trainer_classes)

import carbon
from cleanup_utils import safe_rmtree
from experiment_utils import arch_short, select_models, set_seed
from generate_predictions import generate_for_examples
from io_utils import load_examples, load_yaml
from model_utils import (fit_input, free_model, load_decoder, neutral_generation_config,
                         stop_token_overrides)
from prompts import build_target


def build_dataset(examples, tokenizer, max_seq_length):
    """prompt + target + EOS per example, with the prompt masked out of the labels."""
    from datasets import Dataset

    eos = tokenizer.eos_token or ""

    def encode(ex):
        answer = build_target(ex["questions"]) + eos
        answer_ids = tokenizer(answer, add_special_tokens=False)["input_ids"]
        prompt = fit_input(tokenizer, ex, max_seq_length, reserve=len(answer_ids))
        prompt_ids = tokenizer(prompt, add_special_tokens=True)["input_ids"]
        input_ids = (prompt_ids + answer_ids)[:max_seq_length]
        labels = ([-100] * len(prompt_ids) + answer_ids)[:max_seq_length]
        return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels}

    return Dataset.from_list([encode(e) for e in examples])


def make_collator(pad_id):
    import torch

    def collate(features):
        maxlen = max(len(f["input_ids"]) for f in features)
        input_ids, attn, labels = [], [], []
        for f in features:
            pad = maxlen - len(f["input_ids"])
            input_ids.append(f["input_ids"] + [pad_id] * pad)
            attn.append(f["attention_mask"] + [0] * pad)
            labels.append(f["labels"] + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids),
            "attention_mask": torch.tensor(attn),
            "labels": torch.tensor(labels),
        }

    return collate


def train_one_model(model_cfg, train_examples, dev_examples, args) -> None:
    from transformers import TrainingArguments

    HorizonTrainer, _ = make_horizon_trainer_classes()

    short = model_cfg["short_name"]
    arch = model_cfg["architecture"]
    max_seq = model_cfg.get("max_seq_length", args.max_seq_length)
    # The adaptation family decides quantisation: only qlora loads in 4-bit.
    load_4bit = args.familia_adaptacao == "qlora"
    tmp_dir = Path(args.output_base_dir) / short / args.train_setting / f"fold{args.fold}"
    grad_accum = gradient_accumulation_steps(args.effective_batch_size, args.batch_size)

    print(
        f"\n=== [fine_tuning:{args.train_setting}] {short} ({arch}, "
        f"{args.familia_adaptacao}) ===\n"
        f"    lr={args.learning_rate:g} | physical_batch={args.batch_size} | "
        f"grad_accum={grad_accum} | effective_batch={args.effective_batch_size} | "
        f"warmup_ratio={args.warmup_ratio} | epochs={args.epochs} | "
        f"scheduler_horizon={args.scheduler_horizon_epochs} | "
        f"LoRA(r={args.lora_r}, alpha={args.lora_alpha}, dropout={args.lora_dropout})"
    )

    # QLoRA: bf16 is the NF4 compute dtype. LoRA: fp32 weights with bf16 autocast.
    model, tokenizer = load_decoder(
        model_cfg["model_name_or_path"], args.offline, bf16=load_4bit,
        load_in_4bit=load_4bit)
    model = aplicar_adaptacao(model, args.familia_adaptacao, r=args.lora_r,
                              alpha=args.lora_alpha, dropout=args.lora_dropout)

    train_ds = build_dataset(train_examples, tokenizer, max_seq)
    dev_ds = build_dataset(dev_examples, tokenizer, max_seq) if dev_examples else None
    collator = make_collator(tokenizer.pad_token_id or tokenizer.eos_token_id)

    train_args = TrainingArguments(
        output_dir=str(tmp_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        bf16=True,
        eval_strategy="epoch" if dev_ds is not None else "no",
        save_strategy="no",
        load_best_model_at_end=False,
        logging_strategy="epoch",
        report_to=[],
        seed=args.seed,
        data_seed=args.seed,
    )

    gen_cfg = neutral_generation_config()
    gen_cfg.update(stop_token_overrides(model_cfg, tokenizer))
    prompt_fn = lambda ex: fit_input(tokenizer, ex, max_seq, reserve=gen_cfg["max_new_tokens"])
    gerar = lambda m: generate_for_examples(
        m, tokenizer, dev_examples, arch, gen_cfg, prompt_fn, max_seq)

    trainer = HorizonTrainer(
        model=model,
        args=train_args,
        scheduler_horizon_epochs=args.scheduler_horizon_epochs,
        train_dataset=train_ds,
        eval_dataset=dev_ds,
        data_collator=collator,
        callbacks=[constroi_callback(
            dev_examples=dev_examples,
            gerar=gerar,
            modelo=short,
            config=args.train_setting,
            fold=args.fold,
            arquitetura=arch_short(arch),
            destino=Path(args.results_dir),
            device_metricas=args.metrics_device,
            training_meta={
                "learning_rate": args.learning_rate,
                "warmup_ratio": args.warmup_ratio,
                "physical_batch_size": args.batch_size,
                "gradient_accumulation_steps": grad_accum,
                "effective_batch_size": args.effective_batch_size,
                "scheduler_horizon_epochs": args.scheduler_horizon_epochs,
                "precision": ("nf4 4-bit + bf16" if load_4bit
                              else "fp32 weights + bf16 autocast"),
                "familia_adaptacao": args.familia_adaptacao,
                "lora_r": args.lora_r,
                "lora_alpha": args.lora_alpha,
                "lora_dropout": args.lora_dropout,
            },
        ), constroi_callback_lr(
            modelo=short, config=args.train_setting, fold=args.fold,
            arquitetura=arch_short(arch), destino=Path(args.results_dir),
            horizonte=args.scheduler_horizon_epochs,
        )],
    )
    trainer.train()
    print(f"[ok] {short} · fold {args.fold} · {args.train_setting}: "
          f"{args.epochs} épocas avaliadas no dev gold -> {args.results_dir}")

    free_model(model, tokenizer, trainer)
    safe_rmtree(tmp_dir)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True)
    p.add_argument("--train_file", required=True)
    p.add_argument("--train_setting", required=True)
    p.add_argument("--fold", type=int, required=True)
    p.add_argument("--dev_file", required=True)
    p.add_argument("--results_dir", default="qg_kfold/runs/v3/results")
    p.add_argument("--metrics_device", default="cpu")
    p.add_argument("--output_base_dir", default="tmp/adapters/decoder_v3")
    p.add_argument("--carbon_dir", default="qg_kfold/runs/v3/carbon",
                   help="Where the codecarbon measurements are written.")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--scheduler_horizon_epochs", type=int, default=None)
    p.add_argument("--batch_size", type=int, default=8,
                   help="Physical batch; the effective batch stays fixed by accumulation.")
    p.add_argument("--effective_batch_size", type=int, default=8)
    p.add_argument("--familia_adaptacao", required=True, choices=("lora", "qlora"),
                   help="Adaptation family, decided by model size in models_manifest.json.")
    p.add_argument("--learning_rate", type=float, required=True)
    p.add_argument("--warmup_ratio", type=float, default=0.10)
    p.add_argument("--lora_r", type=int, default=64)
    p.add_argument("--lora_alpha", type=int, default=16)
    p.add_argument("--lora_dropout", type=float, default=0.10)
    p.add_argument("--max_seq_length", type=int, default=2048)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--only", default=None)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    if args.scheduler_horizon_epochs is None:
        args.scheduler_horizon_epochs = args.epochs
    return args


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    models = select_models(load_yaml(args.config)["models"], args.only)
    train_examples = load_examples(args.train_file)
    dev_examples = load_examples(args.dev_file)
    print(f"[train_decoder_lora_kfold] fold={args.fold} setting={args.train_setting} | "
          f"treino={len(train_examples)} | dev gold={len(dev_examples)} | "
          f"épocas={args.epochs} (sem early stopping)")

    for model_cfg in models:
        try:
            # The measurement covers loading, training and the per-epoch dev evaluation.
            with carbon.medir(
                    f"kfold__{args.train_setting}__{model_cfg['short_name']}"
                    f"__fold{args.fold}__lr{args.learning_rate:g}"
                    f"__h{args.scheduler_horizon_epochs}",
                    args.carbon_dir, "fine_tuning_kfold"):
                train_one_model(model_cfg, train_examples, dev_examples, args)
        except Exception as e:
            print(f"[ERRO] modelo {model_cfg.get('short_name')} falhou: {e}")
            traceback.print_exc()
            continue
    print("\n[train_decoder_lora_kfold] concluído.")


if __name__ == "__main__":
    main()
