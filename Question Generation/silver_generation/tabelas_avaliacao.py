"""Prints the compliance rates of the manual evaluation (Tables 3.8 and 3.9) from the files in
silver_generation/avaliacao/ (written by app.py), using the sample and the aggregation of
amostra.py.

    python silver_generation/tabelas_avaliacao.py
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from amostra import (METRICAS_CLEVER, NOMES, NOMES_CLEVER, RATINGS_CLEVER_FILE,  # noqa: E402
                     RATINGS_FILE, carregar_amostra, chave_pergunta, normalizar_clever,
                     taxas_clever, taxas_qualidade)


def ler(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def main() -> None:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()

    amostra = carregar_amostra()
    ratings, clever = ler(RATINGS_FILE), ler(RATINGS_CLEVER_FILE)

    # General question quality (Table 3.8): questions with the four criteria answered
    # (amostra.taxas_qualidade).
    chaves = [chave_pergunta(r["id"], n) for r in amostra
              for n in range(1, len(r["questions"]) + 1)]
    taxas_q = taxas_qualidade(ratings, chaves)
    feitas = next(iter(taxas_q.values()))[1]
    print(f"Table 3.8, general question quality ({len(amostra)} claim spans, "
          f"{feitas}/{len(chaves)} questions evaluated; unit: question)")
    for m, (ok, n) in taxas_q.items():
        print(f"  {NOMES[m]:34s} {ok:>4}/{n:<4} {100 * ok / n:5.1f}%" if n else f"  {NOMES[m]}: —")

    # Adherence to the CLEVER guidelines (Table 3.9): each criterion in its own unit.
    avaliacoes = [normalizar_clever(clever.get(r["id"]) or {}, len(r["questions"]))
                  for r in amostra]
    taxas = taxas_clever(avaliacoes)
    print("\nTable 3.9, adherence to the CLEVER guidelines (each criterion in its own unit)")
    for m in METRICAS_CLEVER:
        ok, n, unidade = taxas[m]
        print(f"  {NOMES_CLEVER[m]:34s} {ok:>4}/{n:<4} {100 * ok / n:5.1f}%  ({unidade})"
              if n else f"  {NOMES_CLEVER[m]}: —")
    print(f"\nSpecial cases apply to {taxas['casos_especiais'][1]} of {len(amostra)} claim spans.")


if __name__ == "__main__":
    main()
