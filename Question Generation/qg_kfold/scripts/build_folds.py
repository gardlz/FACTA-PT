"""Builds the 4 cross-validation folds over the 40 CLEVER training claim spans.

Whole source documents stay in one fold, every fold has exactly 10 claim spans, and among
the valid partitions found by a seeded random search the one with the most balanced number
of reference questions per fold is kept. The 100 test claim spans are not read.

    python qg_kfold/scripts/build_folds.py
"""

import argparse
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
KFOLD = RAIZ / "qg_kfold"

N_FOLDS = 4
CLAIMS_POR_FOLD = 10


def documento_de(claim_id: str) -> str:
    """`<doc>_c3_s0` -> `<doc>` (strips the claim and span suffixes)."""
    return re.sub(r"_c\d+(_s\d+)?$", "", claim_id)


def le_gold(caminho: Path) -> list:
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def agrupa_por_documento(claims: list) -> list:
    """[(document, [claim_ids], n_questions)] — the indivisible unit of the partition."""
    grupos = defaultdict(list)
    for c in claims:
        grupos[documento_de(c["id"])].append(c)
    return [(doc, [c["id"] for c in cs], sum(len(c["reference_questions"]) for c in cs))
            for doc, cs in sorted(grupos.items())]


def particiona(grupos: list, seed: int, tentativas: int) -> list:
    """Best partition found: 4 folds of 10 claims, minimising (range, std) of questions per fold."""
    rng = random.Random(seed)
    melhor, melhor_custo = None, None
    for _ in range(tentativas):
        ordem = grupos[:]
        rng.shuffle(ordem)
        folds = [[] for _ in range(N_FOLDS)]
        n_claims = [0] * N_FOLDS
        n_perguntas = [0] * N_FOLDS
        ok = True
        # Larger groups first: they are the ones that constrain the partition.
        for doc, ids, perguntas in sorted(ordem, key=lambda g: -len(g[1])):
            cabem = [i for i in range(N_FOLDS) if n_claims[i] + len(ids) <= CLAIMS_POR_FOLD]
            if not cabem:
                ok = False
                break
            i = min(cabem, key=lambda i: (n_perguntas[i], n_claims[i]))
            folds[i].append((doc, ids, perguntas))
            n_claims[i] += len(ids)
            n_perguntas[i] += perguntas
        if not ok or any(n != CLAIMS_POR_FOLD for n in n_claims):
            continue
        custo = (max(n_perguntas) - min(n_perguntas), statistics.pstdev(n_perguntas))
        if melhor_custo is None or custo < melhor_custo:
            melhor, melhor_custo = folds, custo
    if melhor is None:
        raise SystemExit("Não foi encontrada partição válida — verificar os dados de entrada.")
    return melhor


def escreve(folds: list, claims: list) -> dict:
    por_id = {c["id"]: c for c in claims}
    (KFOLD / "folds").mkdir(parents=True, exist_ok=True)

    resumo = {"folds": []}

    for n, fold in enumerate(folds, 1):
        ids = [i for _, lista, _ in fold for i in lista]
        info = {
            "fold": n,
            "n_claims": len(ids),
            "n_reference_questions": sum(len(por_id[i]["reference_questions"]) for i in ids),
            "n_documentos": len(fold),
            "documentos": sorted(doc for doc, _, _ in fold),
            "claim_ids": sorted(ids),
        }
        (KFOLD / "folds" / f"fold{n}.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        resumo["folds"].append({k: info[k] for k in
                                ("fold", "n_claims", "n_reference_questions", "n_documentos")})
    return resumo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gold", default=str(RAIZ / "data/clever/clever_train_40.jsonl"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tentativas", type=int, default=20000)
    args = p.parse_args()

    claims = le_gold(Path(args.gold))
    grupos = agrupa_por_documento(claims)
    print(f"[folds] {len(claims)} claims gold em {len(grupos)} documentos "
          f"({sum(1 for g in grupos if len(g[1]) > 1)} com mais de uma claim)")

    folds = particiona(grupos, args.seed, args.tentativas)
    resumo = escreve(folds, claims)
    for f in resumo["folds"]:
        print(f"  fold {f['fold']}: {f['n_claims']} claims, "
              f"{f['n_reference_questions']} perguntas, {f['n_documentos']} documentos")


if __name__ == "__main__":
    main()
