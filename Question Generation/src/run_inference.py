"""Zero-shot and few-shot inference on the CLEVER test set for the models of a YAML file.

    python src/run_inference.py --config configs/models_decoder.yaml --only amalia_9b \
        --regime few_shot --seed 42 --bf16 --offline

A model that fails is logged and the next one runs.
"""

import argparse
import traceback
from pathlib import Path
from typing import List

import carbon
from experiment_utils import build_prediction_record, prediction_filename, select_models, set_seed
from generate_predictions import generate_for_examples
from io_utils import load_examples, load_yaml, write_jsonl
from model_utils import (fit_fewshot_input, fit_input, free_model, load_decoder,
                         load_encoder_decoder, load_tokenizer, neutral_generation_config,
                         stop_token_overrides, to_chat_prompt, to_device, wants_chat_template)


def pick_fewshot_shots(pool: List[dict], k: int) -> List[dict]:
    """Fixed demonstrations: the first training claim (by id) with 1, 2, ..., k gold questions.

    The pool is the 40 CLEVER training claim spans; the selected demonstrations are
    returned in id order.
    """
    ordenado = sorted(pool, key=lambda e: e.get("id", ""))
    escolhidos: List[dict] = []
    ids: set = set()
    for n in range(1, k + 1):
        for ex in ordenado:
            if ex.get("id") in ids:
                continue
            if len(ex.get("reference_questions") or []) == n:
                escolhidos.append(ex)
                ids.add(ex.get("id"))
                break
    # A cardinality missing from the pool is filled with the first remaining ids.
    for ex in ordenado:
        if len(escolhidos) >= k:
            break
        if ex.get("id") not in ids:
            escolhidos.append(ex)
            ids.add(ex.get("id"))
    return sorted(escolhidos[:k], key=lambda e: e.get("id", ""))


def run_one_model(model_cfg: dict, examples: List[dict], args, shots: List[dict], shots_ids: List[str]) -> None:
    arch = model_cfg["architecture"]
    short = model_cfg["short_name"]
    gen_cfg = neutral_generation_config()
    out_path = Path(args.predictions_dir) / prediction_filename(args.regime, "none", arch, short, args.seed)

    bf16 = args.bf16
    print(f"\n=== [{args.regime}] {short} ({arch}, {'bf16' if bf16 else 'fp32'}) ===")

    # Prompts are built and checked with the tokenizer before the weights are loaded.
    tokenizer = load_tokenizer(model_cfg["model_name_or_path"], args.offline)
    gen_cfg.update(stop_token_overrides(model_cfg, tokenizer))

    max_src = model_cfg.get("max_source_length", model_cfg.get("max_seq_length", 1024))
    # Decoder-only models share the window with the generated tokens.
    reserve = gen_cfg["max_new_tokens"] if arch == "decoder_only" else 0

    # Instruct decoders get the prompt inside their chat template.
    use_chat = wants_chat_template(tokenizer, arch)
    tmpl_kwargs = model_cfg.get("chat_template_kwargs") or {}

    # Every model of a regime receives the full prompt; one that does not fit stops the model.
    prompts = {}
    for ex in examples:
        if args.regime == "few_shot":
            bruto = fit_fewshot_input(tokenizer, ex, shots, max_src, reserve)
        else:
            bruto = fit_input(tokenizer, ex, max_src, reserve)
        prompts[id(ex)] = to_chat_prompt(tokenizer, bruto, tmpl_kwargs) if use_chat else bruto

    if arch == "encoder_decoder":
        model, _ = load_encoder_decoder(model_cfg["model_name_or_path"], args.offline, bf16)
    else:
        model, _ = load_decoder(model_cfg["model_name_or_path"], args.offline, bf16,
                                load_in_4bit=model_cfg.get("load_in_4bit", False))
    model = to_device(model)
    prompt_fn = lambda ex: prompts[id(ex)]
    print(f"[input] {short}: chat_template={'sim' if use_chat else 'não (texto cru)'}"
          + (f" | template_kwargs={tmpl_kwargs}" if tmpl_kwargs else ""))
    results = generate_for_examples(model, tokenizer, examples, arch, gen_cfg, prompt_fn,
                                    max_src, add_special_tokens=not use_chat)
    records = [
        build_prediction_record(
            ex, gen_qs, raw, model_cfg=model_cfg, regime=args.regime, train_setting="none",
            claimpt_percentage=None, seed=args.seed, generation_config=gen_cfg,
            few_shot_example_ids=shots_ids,
        )
        for ex, (gen_qs, raw) in zip(examples, results)
    ]
    write_jsonl(out_path, records)
    print(f"[ok] {len(records)} predictions -> {out_path}")
    free_model(model, tokenizer)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", required=True, help="configs/models_encdec.yaml or configs/models_decoder.yaml")
    p.add_argument("--regime", choices=["zero_shot", "few_shot"], required=True)
    p.add_argument("--test_file", default="data/clever/clever_test_100.jsonl")
    p.add_argument("--train_file", default="data/clever/clever_train_40.jsonl",
                   help="Pool of few-shot demonstrations (the 40 CLEVER training claim spans only).")
    p.add_argument("--predictions_dir", default="outputs/predictions")
    p.add_argument("--carbon_dir", default="outputs/carbon",
                   help="Where the codecarbon measurements are written.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--k", type=int, default=3,
                   help="Number of few-shot demonstrations (one per cardinality: 1, 2 and 3 questions).")
    p.add_argument("--only", default=None, help="Comma-separated short names.")
    p.add_argument("--bf16", action="store_true")
    p.add_argument("--offline", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    models = load_yaml(args.config)["models"]
    models = select_models(models, args.only)
    examples = load_examples(args.test_file)

    shots, shots_ids = [], []
    if args.regime == "few_shot":
        pool = load_examples(args.train_file)
        shots = pick_fewshot_shots(pool, args.k)
        shots_ids = [s.get("id", "") for s in shots]
        print(f"[few_shot] k={args.k} exemplos: {shots_ids}")

    for model_cfg in models:
        try:
            # The measurement covers loading the model, building the prompts and generating.
            with carbon.medir(f"{args.regime}__{model_cfg['short_name']}__seed{args.seed}",
                              args.carbon_dir, args.regime):
                run_one_model(model_cfg, examples, args, shots, shots_ids)
        except Exception as e:
            print(f"[ERRO] modelo {model_cfg.get('short_name')} falhou: {e}")
            traceback.print_exc()
        finally:
            # Free the GPU even after a failure, so the next model does not inherit an OOM.
            free_model()
    print("\n[run_inference] concluído.")


if __name__ == "__main__":
    main()
