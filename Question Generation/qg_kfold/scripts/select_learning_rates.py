"""Selects one learning rate per adaptation family from cross-validation only, never the test set.

Best macro-average, over the family's learning-rate-selection models, of the 4-fold mean H-BERT
on human40_silver100 at the selected epoch (earliest within 0.05 of the maximum; ties: smaller
LR). A model with a candidate selected at its last epoch reruns all candidates at the next
horizon.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
KFOLD = RAIZ / "qg_kfold"
EXTENSION_LADDER = {20: 30, 30: 40}
ABSOLUTE_MAX = 40


def read_epoch_records(path: Path) -> list[dict]:
    records: list[dict] = []
    for file in sorted(path.glob("*__por_epoca.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def best_for_model_lr(records: list[dict], epoch_tolerance: float, required_folds: int = 4):
    """Return the H-BERT-selected epoch for one model/LR, requiring all four folds."""
    by_epoch: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        by_epoch[int(record["epoch"])].append(record)

    candidates = []
    for epoch, rows in sorted(by_epoch.items()):
        folds = {int(row["fold"]) for row in rows}
        values = [row.get("mean_h_bert") for row in rows
                  if isinstance(row.get("mean_h_bert"), (int, float))]
        if len(folds) != required_folds or len(values) != required_folds:
            continue
        horizons = {int(row.get("scheduler_horizon_epochs") or row.get("epochs_max") or epoch)
                    for row in rows}
        if len(horizons) != 1:
            raise ValueError(f"Inconsistent scheduler horizons at epoch {epoch}: {sorted(horizons)}")
        candidates.append({
            "epoch": epoch,
            "mean_h_bert": statistics.fmean(values),
            "horizon": horizons.pop(),
        })

    if not candidates:
        return None

    observed_horizons = {row["horizon"] for row in candidates}
    if len(observed_horizons) != 1:
        raise ValueError(
            "A model/LR result directory mixes scheduler horizons. Extension reruns must "
            "replace all four shorter-horizon files before LR selection."
        )
    horizon = observed_horizons.pop()
    max_epoch = max(row["epoch"] for row in candidates)
    if max_epoch != horizon:
        # A completed run contains every epoch through the declared horizon.
        raise ValueError(f"Incomplete run: highest epoch {max_epoch}, declared horizon {horizon}.")

    peak = max(row["mean_h_bert"] for row in candidates)
    tied = [row for row in candidates if peak - row["mean_h_bert"] <= epoch_tolerance]
    return min(tied, key=lambda row: row["epoch"])


def lr_key(lr: float) -> str:
    return f"{lr:.0e}".replace("+", "").replace("-0", "-")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifesto", default=str(KFOLD / "configs/models_manifest.json"))
    parser.add_argument("--run_root", default=str(KFOLD / "runs/v3/lr_ablation"))
    parser.add_argument("--output", default=str(KFOLD / "runs/v3/selected_learning_rates.json"))
    parser.add_argument("--epoch_tolerance", type=float, default=0.05)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifesto).read_text(encoding="utf-8"))
    root = Path(args.run_root)
    candidates = manifest["hyperparameter_protocol"]["lr_candidates"]
    primary = manifest["primary_training_setting"]
    calibration_names = manifest.get("lr_calibration_models") or []
    if not calibration_names:
        raise SystemExit("Manifest does not define lr_calibration_models.")

    by_name = {model["short_name"]: model for model in manifest["modelos"]}
    missing = [name for name in calibration_names if name not in by_name]
    if missing:
        raise SystemExit(f"Learning-rate-selection models missing from manifest: {missing}")
    calibration_models = [by_name[name] for name in calibration_names]

    model_summaries: dict[str, list[dict]] = defaultdict(list)
    incomplete = []

    for model_cfg in calibration_models:
        model = model_cfg["short_name"]
        familia = model_cfg["familia_adaptacao"]
        for lr in map(float, candidates[familia]):
            result_dir = root / "results" / familia / lr_key(lr)
            records = [
                row for row in read_epoch_records(result_dir)
                if row.get("modelo") == model and row.get("config") == primary
            ]
            try:
                best = best_for_model_lr(records, args.epoch_tolerance)
            except ValueError as exc:
                incomplete.append(f"{model} lr={lr:g}: {exc}")
                continue
            if best is None:
                incomplete.append(f"{model} lr={lr:g}: no complete four-fold epochs")
                continue
            model_summaries[model].append({
                "familia": familia,
                "lr": lr,
                "best_epoch": best["epoch"],
                "horizon": best["horizon"],
                "mean_h_bert": round(best["mean_h_bert"], 6),
            })

    if incomplete:
        raise SystemExit(
            "LR selection stopped because some model/LR runs are incomplete:\n  - "
            + "\n  - ".join(incomplete)
        )

    # Extension is decided at model level: all candidate LRs of a model share one horizon.
    extensions = []
    absolute_boundary = []
    for model_cfg in calibration_models:
        model = model_cfg["short_name"]
        rows = model_summaries[model]
        expected = len(candidates[model_cfg["familia_adaptacao"]])
        if len(rows) != expected:
            raise SystemExit(f"{model}: expected {expected} LR results, got {len(rows)}.")
        horizons = {int(row["horizon"]) for row in rows}
        if len(horizons) != 1:
            raise SystemExit(
                f"{model}: LR candidates were evaluated under different scheduler horizons "
                f"{sorted(horizons)}. Rerun ALL candidates for this model at one common horizon."
            )
        horizon = horizons.pop()
        boundary = any(int(row["best_epoch"]) == horizon for row in rows)
        if not boundary:
            continue
        if horizon in EXTENSION_LADDER:
            extensions.append({
                "modelo": model,
                "familia": model_cfg["familia_adaptacao"],
                "arquitetura": model_cfg["arquitetura"],
                "horizon_atual": horizon,
                "prolongar_ate": EXTENSION_LADDER[horizon],
                "motivo": "at least one LR candidate peaks at the common search boundary",
            })
        else:
            absolute_boundary.append({
                "modelo": model,
                "familia": model_cfg["familia_adaptacao"],
                "arquitetura": model_cfg["arquitetura"],
                "horizon_atual": horizon,
                "limite": ABSOLUTE_MAX,
            })

    pending_path = root / "extensions_pending.csv"
    if extensions:
        write_csv(pending_path, extensions)
        raise SystemExit(
            f"LR selection stopped: {len(extensions)} learning-rate-selection model(s) require a "
            f"common horizon extension ({pending_path}). All LR candidates of each affected model "
            "are rerun with the longer horizon, so the comparison stays fair."
        )
    if pending_path.exists():
        pending_path.unlink()
    if absolute_boundary:
        write_csv(root / "absolute_boundary.csv", absolute_boundary)
        raise SystemExit(
            "LR selection stopped: at least one learning-rate-selection model still has an LR "
            f"candidate peaking at the absolute {ABSOLUTE_MAX}-epoch boundary, the longest "
            "horizon of the protocol."
        )

    by_familia_lr: dict[tuple[str, float], list[float]] = defaultdict(list)
    for rows in model_summaries.values():
        for row in rows:
            by_familia_lr[(row["familia"], float(row["lr"]))].append(float(row["mean_h_bert"]))

    selected = {}
    for familia, lr_values in candidates.items():
        family_models = [model for model in calibration_models
                         if model["familia_adaptacao"] == familia]
        expected_models = len(family_models)
        scores = []
        for lr in map(float, lr_values):
            values = by_familia_lr[(familia, lr)]
            if len(values) != expected_models:
                raise SystemExit(
                    f"{familia} lr={lr:g}: expected {expected_models} learning-rate-selection "
                    f"models, got {len(values)}."
                )
            scores.append((lr, statistics.fmean(values)))

        best_mean = max(score[1] for score in scores)
        # Strict maximum; an exact tie goes to the smaller learning rate.
        tied = [score for score in scores if score[1] == best_mean]
        chosen = min(tied, key=lambda score: score[0])
        selected[familia] = {
            "learning_rate": chosen[0],
            "modelos_representativos": [m["short_name"] for m in family_models],
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol_tag": manifest.get("protocol_tag", "qg_v3"),
        "calibration_models": calibration_names,
        "families": selected,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[LR] selected learning rates -> {output}")
    for familia, row in selected.items():
        print(f"  {familia}: {row['learning_rate']:g}")


if __name__ == "__main__":
    main()
