"""Builds the content plans from the CLEVER evidence annotations: one JSON per claim span (by default
in `dados/planos/<condition>/`).

Deterministic, CPU only, no model. For each condition it prints the number of plans and evidence
passages, the passages removed by deduplication and the number of claim spans in each plan case.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import plano as pv          # noqa: E402

PASTA = pv.SAIDAS / "planos"


def construir_condicao(dados, condicao: str, saida: Path) -> dict:
    """Write every plan of one condition to `saida`; return the counts printed by `main`."""
    saida.mkdir(parents=True, exist_ok=True)
    casos = Counter()
    n_planos = n_evidencias = removidas = 0
    for span in dados:
        plano = pv.construir(span, condicao)
        n_planos += 1
        n_evidencias += plano["n_evidencias"]
        casos[plano["caso"]] += 1
        removidas += len(plano["evidencias_removidas"]["deduplicacao"])
        (saida / f"{plano['claim_span_id']}.json").write_text(
            json.dumps(plano, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"n_planos": n_planos, "n_evidencias": n_evidencias,
            "removidas_deduplicacao": removidas, "casos": dict(sorted(casos.items()))}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default=str(pv.DATASET),
                   help="CLEVER (clever.json, com clean_files/ ao lado). Por omissão, "
                        "../CLEVER/clever.json.")
    p.add_argument("--condicao", choices=sorted(pv.CONDICOES), default="full")
    p.add_argument("--todas", action="store_true", help="Constrói as quatro condições.")
    p.add_argument("--saida", default=None,
                   help="Pasta de saída. Por omissão, dados/planos/<condição>.")
    args = p.parse_args()

    dados = pv.carregar_dataset(Path(args.dataset))
    condicoes = sorted(pv.CONDICOES) if args.todas else [args.condicao]
    if args.todas and args.saida:
        raise SystemExit("--todas não se combina com --saida.")

    for condicao in condicoes:
        saida = Path(args.saida) if args.saida else PASTA / condicao
        m = construir_condicao(dados, condicao, saida)
        print(f"[planos] {condicao}: {m['n_planos']} planos, {m['n_evidencias']} evidências "
              f"-> {saida}")
        print(f"  removidas pela deduplicação: {m['removidas_deduplicacao']}")
        for caso, n in m["casos"].items():
            print(f"  {caso:18} {n:3}")


if __name__ == "__main__":
    main()
