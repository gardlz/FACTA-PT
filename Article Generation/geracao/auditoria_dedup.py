"""Audits the containment threshold used by deduplication (`dedup_excertos.LIMIAR_CONTENCAO`).

Lists the window pairs of the same claim span and relation with containment >= MINIMO, and prints
the candidate removals and the removal precision at each threshold in LIMIARES. Identical pairs are
REDUNDANT; the other labels are read from `dados/dedup/anotacao_dedup.json`.
"""

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import dedup_excertos as dx                     # noqa: E402
import plano as pv                              # noqa: E402

LIMIARES = (0.90, 0.85, 0.80)
MINIMO = min(LIMIARES)
PASTA = AQUI.parent / "dados" / "dedup"
ANOTACOES = PASTA / "anotacao_dedup.json"
REDUNDANT, NON_REDUNDANT = "REDUNDANT", "NON_REDUNDANT"


def pares_candidatos(dados: List[dict]) -> List[dict]:
    """Window pairs of one claim span and relation with containment >= MINIMO, highest first."""
    saida = []
    for span in dados:
        evidencias = pv.evidencias_do_span(span)
        for relacao in pv.ORDEM_GRUPOS:
            grupo = [e for e in evidencias if e["relacao"] == relacao]
            for a, b in itertools.combinations(grupo, 2):
                igual = dx.normalizar(a["texto"]) == dx.normalizar(b["texto"])
                contencao = dx.contencao(a["texto"], b["texto"])
                if contencao < MINIMO:
                    continue
                # The one desduplicar would drop: the shorter text (on equal length, the later one).
                curta, longa = (a, b) if len(a["texto"]) < len(b["texto"]) else (b, a)
                saida.append({
                    "id": f"{span['claim_span_id']}|{curta['id']}|{longa['id']}",
                    "claim_span_id": span["claim_span_id"],
                    "relacao": relacao,
                    "contencao": round(contencao, 4),
                    "igual": igual,
                })
    return sorted(saida, key=lambda p: (-p["contencao"], p["id"]))


def carregar_anotacoes() -> Dict[str, dict]:
    if not ANOTACOES.exists():
        return {}
    return json.loads(ANOTACOES.read_text(encoding="utf-8"))


def removidas_pelo_algoritmo(dados: List[dict], limiar: float) -> int:
    """How many windows `desduplicar` removes at `limiar`; can differ from the number of pairs."""
    total = 0
    for span in dados:
        evidencias = pv.evidencias_do_span(span)
        for relacao in pv.ORDEM_GRUPOS:
            total += len(dx.desduplicar([e for e in evidencias if e["relacao"] == relacao], limiar)[1])
    return total


def rotulo(par: dict, anotacoes: Dict[str, dict]) -> Optional[str]:
    """Identical pairs are REDUNDANT by definition; others take their annotated label, if any."""
    return REDUNDANT if par["igual"] else anotacoes.get(par["id"], {}).get("rotulo")


def tabela(pares: List[dict], anotacoes: Dict[str, dict]) -> List[dict]:
    """Per threshold: pair and label counts, and precision (None until every pair is labelled)."""
    linhas = []
    for t in LIMIARES:
        acima = [p for p in pares if p["contencao"] >= t]
        rotulos = [rotulo(p, anotacoes) for p in acima]
        red, nao = rotulos.count(REDUNDANT), rotulos.count(NON_REDUNDANT)
        completo = red + nao == len(acima)
        linhas.append({"limiar": t, "pares": len(acima), "iguais": sum(p["igual"] for p in acima),
                       "rotulados": red + nao, "redundantes": red, "nao_redundantes": nao,
                       "precisao": (red / len(acima) if acima else 1.0) if completo else None})
    return linhas


def limiar_escolhido(linhas: List[dict]) -> Optional[float]:
    """t* = the lowest threshold with precision 1; None if labels are missing or none qualifies."""
    if any(l["precisao"] is None for l in linhas):
        return None
    certos = [l["limiar"] for l in linhas if l["precisao"] == 1.0]
    return min(certos) if certos else None


def main() -> None:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    dados = pv.carregar_dataset()
    pares = pares_candidatos(dados)
    anotacoes = carregar_anotacoes()
    print(f"{len(pares)} pares com contenção >= {MINIMO} (janelas de 3 frases, mesmo span e mesma "
          f"relação); {sum(p['igual'] for p in pares)} iguais (redundantes por definição).")
    for p in pares:
        r = rotulo(p, anotacoes) or "por anotar"
        print(f"  {p['contencao']:.3f} {p['id']:60} {r}{' (igual)' if p['igual'] else ''}")
    print("\ntodos os spans:")
    linhas = tabela(pares, anotacoes)
    for l in linhas:
        prec = "-" if l["precisao"] is None else f"{l['precisao']:.2f}"
        print(f"  {l['limiar']:.2f}: {l['pares']} pares ({l['iguais']} iguais), {l['rotulados']} rotulados, "
              f"{l['redundantes']} redundantes, {l['nao_redundantes']} não redundantes, precisão {prec}")
    t = limiar_escolhido(linhas)
    print(f"  t* = {t if t is not None else '(por decidir: faltam anotações)'}")
    total = sum(len(pv.evidencias_do_span(s)) for s in dados)
    print(f"\njanelas removidas pelo algoritmo (de {total}): "
          + ", ".join(f"{t:.2f} -> {removidas_pelo_algoritmo(dados, t)}" for t in LIMIARES))


if __name__ == "__main__":
    main()
