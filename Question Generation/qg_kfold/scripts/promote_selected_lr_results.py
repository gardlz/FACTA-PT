"""Copies the cross-validation results of the learning-rate-selection models, at the selected
rates, into the main results folder (same folds, data and recipe as the primary
configuration), with their per-step learning-rate logs.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def lr_key(lr: float) -> str:
    return f"{lr:.0e}".replace("+", "").replace("-0", "-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifesto", default="qg_kfold/configs/models_manifest.json")
    parser.add_argument("--selected", default="qg_kfold/runs/v3/selected_learning_rates.json")
    parser.add_argument("--lr_root", default="qg_kfold/runs/v3/lr_ablation/results")
    parser.add_argument("--main_results", default="qg_kfold/runs/v3/results")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifesto).read_text(encoding="utf-8"))
    selected_payload = json.loads(Path(args.selected).read_text(encoding="utf-8"))
    selected = selected_payload["families"]
    primary = manifest["primary_training_setting"]
    output = Path(args.main_results)
    output.mkdir(parents=True, exist_ok=True)

    by_name = {model["short_name"]: model for model in manifest["modelos"]}
    calibration = manifest.get("lr_calibration_models") or []
    copied = 0
    for model_name in calibration:
        model_cfg = by_name[model_name]
        arch = model_cfg["arquitetura"]
        familia = model_cfg["familia_adaptacao"]
        lr = float(selected[familia]["learning_rate"])
        key = lr_key(lr)
        # File names follow the architecture; folders follow the adaptation family.
        arch_short = "encdec" if arch == "encoder_decoder" else "decoder"
        src_dir = Path(args.lr_root) / familia / key
        for fold in (1, 2, 3, 4):
            basename = f"{primary}__{arch_short}__{model_name}__fold{fold}__por_epoca.jsonl"
            src = src_dir / basename
            dst = output / basename
            if not src.exists():
                raise SystemExit(f"Missing selected-LR result: {src}")
            shutil.copy2(src, dst)

            for lr_src in src_dir.glob(
                    f"{primary}__{arch_short}__{model_name}__fold{fold}*__lr_por_step.jsonl"):
                shutil.copy2(lr_src, output / lr_src.name)
            copied += 1

    print(f"[promote] copied {copied} selected-LR fold files into {output}")


if __name__ == "__main__":
    main()
