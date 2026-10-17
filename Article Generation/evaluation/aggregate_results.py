"""Aggregate the per-article results by (generator model, condition): one row per group and metric.

Each row has the article count, n (articles with a value), nulls by reason and the mean. A null value
never enters the mean and never counts as zero.
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

if __package__ in (None, ""):                       # also allow `python evaluation/aggregate_results.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "evaluation"

from . import config, metricas           # noqa: E402
from .cache import escrever_csv, ler_jsonl  # noqa: E402

CHAVES_PADRAO = ("generator_model", "condition")


def estatisticas(xs: List[Optional[float]]) -> dict:
    vals = [x for x in xs if x is not None]
    return {"n": len(vals), "n_null": len(xs) - len(vals),
            "mean": statistics.fmean(vals) if vals else None}


def agregar(resultados: List[dict]) -> List[dict]:
    grupos: Dict[tuple, list] = defaultdict(list)
    for r in resultados:
        grupos[tuple(r.get(c) for c in CHAVES_PADRAO)].append(metricas.vista(r))
    saida = []
    for g, vs in sorted(grupos.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        base = {**dict(zip(CHAVES_PADRAO, g)), "n_articles": len(vs)}
        for m in metricas.GROUNDING:
            e = estatisticas([v["grounding"][m] for v in vs])
            razoes = Counter(v["grounding_reasons"].get(m) or v["grounding_status"] for v in vs if v["grounding"][m] is None)
            # n = articles with a value (the ones averaged); an article without one (overlength, no
            # citations, ...) is counted apart with its reason, never as 0
            saida.append({**base, "group": "Evidence Grounding", "metric": metricas.nome(m), **e,
                          "null_status": dict(razoes)})
        for d in metricas.QUALIDADE:
            notas = [(v["qualidade"].get(d) or {}).get("score") for v in vs]
            e = estatisticas(notas)
            saida.append({**base, "group": "Article Quality", "metric": metricas.nome(d), **e,
                          "null_status": {"missing": e["n_null"]} if e["n_null"] else {}})
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultados", type=Path, default=config.SAIDAS / "resultados.jsonl")
    p.add_argument("--saida", type=Path, default=config.SAIDAS / "agregado")
    args = p.parse_args()
    linhas = agregar(ler_jsonl(args.resultados))
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.with_suffix(".json").write_text(json.dumps(linhas, ensure_ascii=False, indent=1))
    escrever_csv(args.saida.with_suffix(".csv"),
                 [{**l, "null_status": json.dumps(l["null_status"], ensure_ascii=False)} for l in linhas])
    for l in linhas:
        media = "null" if l["mean"] is None else f"{l['mean']:.3f}"
        print(*(l[c] for c in CHAVES_PADRAO), f"{l['metric']:<22}", f"média {media}",
              f"(n={l['n']}, null={l['n_null']})")
    print(f"-> {args.saida.with_suffix('.csv')} e .json")


if __name__ == "__main__":
    main()
