"""Training/dev files for each fold and for the final training, per supervision configuration.

Dev is always the fold's 10 gold claim spans; the silver part is the fixed nested subset
(25/50/75/100%). The 100 test claim spans are not read.
"""

import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
KFOLD = RAIZ / "qg_kfold"

# configuration -> (silver percentage or None, include the gold training claim spans)
CONFIGS = {
    "human40":            (None, True),
    "human40_silver25":   (25, True),
    "human40_silver50":   (50, True),
    "human40_silver75":   (75, True),
    "human40_silver100":  (100, True),
    "silver100":          (100, False),
}


def le(caminho: Path) -> list:
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def escreve(caminho: Path, registos: list) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        for r in registos:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gold", default=str(RAIZ / "data/clever/clever_train_40.jsonl"))
    p.add_argument("--silver_dir", default=str(RAIZ / "data/processed"))
    args = p.parse_args()

    gold_list = le(Path(args.gold))
    gold = {g["id"]: g for g in gold_list}
    silver = {n: le(Path(args.silver_dir) / f"claimpt_silver_{n}.jsonl") for n in (25, 50, 75, 100)}

    silver_ids = {n: [r["id"] for r in rows] for n, rows in silver.items()}
    for n, ids in silver_ids.items():
        if len(ids) != len(set(ids)):
            raise SystemExit(f"claimpt_silver_{n}.jsonl contains duplicate ids.")
    for menor, maior in ((25, 50), (50, 75), (75, 100)):
        if not set(silver_ids[menor]).issubset(set(silver_ids[maior])):
            raise SystemExit(
                f"Silver subsets are not nested: {menor}% is not a subset of {maior}%."
            )

    for n in range(1, 5):
        fold = json.loads((KFOLD / "folds" / f"fold{n}.json").read_text(encoding="utf-8"))
        dev_ids = set(fold["claim_ids"])
        dev = [gold[i] for i in fold["claim_ids"]]
        train_gold = [g for i, g in gold.items() if i not in dev_ids]
        pasta = KFOLD / "data" / f"fold{n}"

        escreve(pasta / "dev_gold.jsonl", dev)
        for nome, (subset, com_gold) in CONFIGS.items():
            registos = list(train_gold) if com_gold else []
            if subset is not None:
                registos += silver[subset]
            escreve(pasta / f"train_{nome}.jsonl", registos)

    # Final-training files: the 40 gold training claim spans plus the silver subset.
    final_dir = KFOLD / "data" / "final"
    for nome, (subset, com_gold) in CONFIGS.items():
        registos = list(gold_list) if com_gold else []
        if subset is not None:
            registos += silver[subset]
        escreve(final_dir / f"train_{nome}.jsonl", registos)

    print(f"[dados] CV -> {KFOLD / 'data'}")
    print(f"[dados] final -> {final_dir}")


if __name__ == "__main__":
    main()
