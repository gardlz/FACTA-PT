"""Final training on all training data and one-time generation for the 100 CLEVER test spans.

Same recipe as cross-validation (learning rate fixed by the learning-rate selection, effective
batch, warm-up, adaptation family). Training stops at the selected epoch while the LR scheduler
keeps the cross-validation horizon (20/30/40). Training files: qg_kfold/data/final/.
"""

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import carbon
from cleanup_utils import safe_rmtree
from experiment_utils import (build_prediction_record, claimpt_percentage_of,
                              prediction_filename, select_models, set_seed)
from generate_predictions import generate_for_examples
from io_utils import load_examples, load_yaml, write_jsonl
from model_utils import (fit_input, free_model, load_decoder, load_encoder_decoder,
                         neutral_generation_config, stop_token_overrides, to_device)
from training_protocol import (aplicar_adaptacao, gradient_accumulation_steps,
                               loss_seq2seq_normalizada, make_horizon_trainer_classes)


def _args_treino(args, tmp_dir: Path, seq2seq: bool):
    from transformers import Seq2SeqTrainingArguments, TrainingArguments

    grad_accum = gradient_accumulation_steps(args.effective_batch_size, args.batch_size)
    # Same precision for every family: bf16 autocast over fp32 (or NF4) weights.
    comuns = dict(
        output_dir=str(tmp_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        bf16=True,
        eval_strategy="no",
        save_strategy="no",
        load_best_model_at_end=False,
        logging_strategy="epoch",
        report_to=[],
        seed=args.seed,
        data_seed=args.seed,
    )
    return Seq2SeqTrainingArguments(**comuns) if seq2seq else TrainingArguments(**comuns)


def treina_encdec(model_cfg, train_examples, test_examples, args):
    from train_encdec_kfold import build_dataset
    from transformers import DataCollatorForSeq2Seq

    _, HorizonSeq2SeqTrainer = make_horizon_trainer_classes()

    short, arch = model_cfg["short_name"], model_cfg["architecture"]
    max_src = model_cfg.get("max_source_length", args.max_source_length)
    max_tgt = model_cfg.get("max_target_length", args.max_target_length)
    tmp_dir = Path(args.output_base_dir) / short / args.train_setting

    # Loaded exactly as in cross-validation: the family decides quantisation.
    load_4bit = args.familia_adaptacao == "qlora"

    print(f"\n=== [final:{args.train_setting}] {short} ({arch}, "
          f"{args.familia_adaptacao}, "
          f"{'pesos NF4 4-bit + compute bf16' if load_4bit else 'pesos fp32 + autocast bf16'}) ===")
    model, tokenizer = load_encoder_decoder(
        model_cfg["model_name_or_path"], args.offline, bf16=load_4bit,
        load_in_4bit=load_4bit)
    model = to_device(model)
    model = aplicar_adaptacao(model, args.familia_adaptacao, r=args.lora_r,
                              alpha=args.lora_alpha, dropout=args.lora_dropout)

    trainer = HorizonSeq2SeqTrainer(
        model=model,
        args=_args_treino(args, tmp_dir, seq2seq=True),
        # Loss normalised over the whole accumulation window (see training_protocol).
        compute_loss_func=loss_seq2seq_normalizada,
        scheduler_horizon_epochs=args.scheduler_horizon_epochs,
        train_dataset=build_dataset(train_examples, tokenizer, max_src, max_tgt),
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model),
    )
    trainer.train()

    gen_cfg = neutral_generation_config()
    resultados = generate_for_examples(
        trainer.model, tokenizer, test_examples, arch, gen_cfg,
        lambda ex: fit_input(tokenizer, ex, max_src), max_src)
    return trainer, tokenizer, gen_cfg, resultados, tmp_dir


def treina_decoder(model_cfg, train_examples, test_examples, args):
    from train_decoder_lora_kfold import build_dataset, make_collator

    HorizonTrainer, _ = make_horizon_trainer_classes()

    short, arch = model_cfg["short_name"], model_cfg["architecture"]
    max_seq = model_cfg.get("max_seq_length", args.max_seq_length)
    load_4bit = args.familia_adaptacao == "qlora"
    tmp_dir = Path(args.output_base_dir) / short / args.train_setting

    print(f"\n=== [final:{args.train_setting}] {short} ({arch}, "
          f"{args.familia_adaptacao}) ===")
    model, tokenizer = load_decoder(
        model_cfg["model_name_or_path"], args.offline, bf16=load_4bit,
        load_in_4bit=load_4bit)
    model = aplicar_adaptacao(model, args.familia_adaptacao, r=args.lora_r,
                              alpha=args.lora_alpha, dropout=args.lora_dropout)

    trainer = HorizonTrainer(
        model=model,
        args=_args_treino(args, tmp_dir, seq2seq=False),
        scheduler_horizon_epochs=args.scheduler_horizon_epochs,
        train_dataset=build_dataset(train_examples, tokenizer, max_seq),
        data_collator=make_collator(tokenizer.pad_token_id or tokenizer.eos_token_id),
    )
    trainer.train()

    gen_cfg = neutral_generation_config()
    gen_cfg.update(stop_token_overrides(model_cfg, tokenizer))
    prompt_fn = lambda ex: fit_input(tokenizer, ex, max_seq, reserve=gen_cfg["max_new_tokens"])
    resultados = generate_for_examples(
        trainer.model, tokenizer, test_examples, arch, gen_cfg, prompt_fn, max_seq)
    return trainer, tokenizer, gen_cfg, resultados, tmp_dir


def treina_um(model_cfg, train_examples, test_examples, args) -> None:
    arch = model_cfg["architecture"]
    fn = treina_encdec if arch == "encoder_decoder" else treina_decoder
    trainer, tokenizer, gen_cfg, resultados, tmp_dir = fn(
        model_cfg, train_examples, test_examples, args)

    grad_accum = gradient_accumulation_steps(args.effective_batch_size, args.batch_size)
    destino = Path(args.predictions_dir) / prediction_filename(
        "fine_tuning", args.train_setting, arch, model_cfg["short_name"], args.seed)
    training_meta = {
        "protocolo": args.protocol_tag,
        "epochs_selected": args.epochs,
        "scheduler_horizon_epochs": args.scheduler_horizon_epochs,
        "learning_rate": args.learning_rate,
        "warmup_ratio": args.warmup_ratio,
        "physical_batch_size": args.batch_size,
        "gradient_accumulation_steps": grad_accum,
        "effective_batch_size": args.effective_batch_size,
        "precision": ("nf4 4-bit + bf16" if args.familia_adaptacao == "qlora"
                      else "fp32 weights + bf16 autocast"),
        "familia_adaptacao": args.familia_adaptacao,
        "early_stopping": False,
        "dev": None,
        "best_epoch_origem": "mean H-BERT dos 4 folds gold",
    }
    if args.familia_adaptacao == "full_fine_tuning":
        training_meta["adaptation"] = "full fine-tuning"
    else:
        training_meta.update({
            "adaptation": "QLoRA 4-bit" if args.familia_adaptacao == "qlora" else "LoRA",
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
            "lora_target_modules": "all-linear",
        })

    registos = [
        build_prediction_record(
            ex, perguntas, raw,
            model_cfg=model_cfg,
            regime="fine_tuning",
            train_setting=args.train_setting,
            claimpt_percentage=claimpt_percentage_of(args.train_setting),
            seed=args.seed,
            generation_config=gen_cfg,
            few_shot_example_ids=[],
            training=training_meta,
        )
        for ex, (perguntas, raw) in zip(test_examples, resultados)
    ]
    write_jsonl(destino, registos)
    print(f"[ok] {len(registos)} predictions -> {destino}")

    free_model(trainer.model, tokenizer, trainer)
    safe_rmtree(tmp_dir)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True)
    p.add_argument("--train_setting", required=True)
    p.add_argument("--epochs", type=int, required=True,
                   help="Epoch selected by the 4-fold cross-validation.")
    p.add_argument("--scheduler_horizon_epochs", type=int, required=True,
                   help="Cross-validation horizon in which that epoch was observed (20/30/40).")
    p.add_argument("--learning_rate", type=float, required=True,
                   help="Learning rate selected by select_learning_rates.py (checked against the file).")
    p.add_argument("--only", default=None)
    p.add_argument("--train_file", default=None)
    p.add_argument("--test_file", default=str(RAIZ / "data/clever/clever_test_100.jsonl"))
    p.add_argument("--output_base_dir", default="qg_kfold/runs/v3/tmp/final")
    p.add_argument("--predictions_dir", default="qg_kfold/runs/v3/results/final/predictions")
    p.add_argument("--carbon_dir", default="qg_kfold/runs/v3/carbon",
                   help="Where the codecarbon measurements are written.")
    p.add_argument("--batch_size", type=int, default=8)
    p.add_argument("--effective_batch_size", type=int, default=8)
    p.add_argument("--familia_adaptacao", required=True,
                   choices=("full_fine_tuning", "lora", "qlora"),
                   help="Adaptation family, decided by model size in models_manifest.json.")
    p.add_argument("--warmup_ratio", type=float, default=0.10)
    p.add_argument("--max_source_length", type=int, default=1024)
    p.add_argument("--max_target_length", type=int, default=192)
    p.add_argument("--max_seq_length", type=int, default=2048)
    p.add_argument("--lora_r", type=int, default=64)
    p.add_argument("--lora_alpha", type=int, default=16)
    p.add_argument("--lora_dropout", type=float, default=0.10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--selected_lr_file", default="qg_kfold/runs/v3/selected_learning_rates.json",
                   help="Output of select_learning_rates.py; the final training refuses another LR.")
    p.add_argument("--protocol_tag", default="qg_v3")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.epochs > args.scheduler_horizon_epochs:
        raise SystemExit("Selected epochs cannot exceed scheduler_horizon_epochs.")
    set_seed(args.seed)
    models = select_models(load_yaml(args.config)["models"], args.only)
    if not models:
        raise SystemExit("No model selected for final refit.")

    # The final training uses the learning rate selected by select_learning_rates.py.
    selected_path = Path(args.selected_lr_file)
    if not selected_path.exists():
        raise SystemExit(f"Missing learning-rate selection file: {selected_path}")
    selected_payload = json.loads(selected_path.read_text(encoding="utf-8"))
    for model_cfg in models:
        expected_lr = float(
            selected_payload["families"][args.familia_adaptacao]["learning_rate"])
        if not math.isclose(args.learning_rate, expected_lr, rel_tol=0.0, abs_tol=1e-15):
            raise SystemExit(
                f"Final LR mismatch for {model_cfg['short_name']}: received {args.learning_rate:g}, "
                f"selected {expected_lr:g}."
            )

    if args.train_file is None:
        args.train_file = str(RAIZ / f"qg_kfold/data/final/train_{args.train_setting}.jsonl")

    train_examples = load_examples(args.train_file)
    test_examples = load_examples(args.test_file)
    print(
        f"[final] setting={args.train_setting} | treino={len(train_examples)} | "
        f"teste={len(test_examples)} | epoch selecionada={args.epochs} | "
        f"scheduler horizon={args.scheduler_horizon_epochs} | lr={args.learning_rate:g}"
    )

    for model_cfg in models:
        try:
            # The measurement covers loading, training to the selected epoch and generation.
            with carbon.medir(f"final__{args.train_setting}__{model_cfg['short_name']}",
                              args.carbon_dir, "fine_tuning_final"):
                treina_um(model_cfg, train_examples, test_examples, args)
        except Exception as e:
            print(f"[ERRO] modelo {model_cfg.get('short_name')} falhou: {e}")
            traceback.print_exc()
            continue
    print("\n[final] concluído.")


if __name__ == "__main__":
    main()
