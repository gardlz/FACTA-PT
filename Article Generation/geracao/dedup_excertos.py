"""Near-duplicate removal among the evidence passages of one group (claim span + relation).

Of two passages whose word 5-gram containment (`contencao`) is at least `LIMIAR_CONTENCAO`, the
shorter one is dropped; identical passages have containment 1 and need no rule of their own.
`auditoria_dedup.py` audits the threshold.
"""

import re
import unicodedata
from typing import Dict, List, Tuple

LIMIAR_CONTENCAO = 0.90
N_GRAMA = 5

_ESPACO = re.compile(r"\s+")
_PONTUACAO = re.compile(r"[^\w\s]", re.UNICODE)


def normalizar(texto: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return _ESPACO.sub(" ", _PONTUACAO.sub(" ", texto.lower())).strip()


def ngramas(texto: str) -> set:
    """Word n-grams of the normalised text; a text shorter than `N_GRAMA` words is one n-gram."""
    palavras = normalizar(texto).split()
    if len(palavras) < N_GRAMA:
        return {" ".join(palavras)} if palavras else set()
    return {" ".join(palavras[i:i + N_GRAMA]) for i in range(len(palavras) - N_GRAMA + 1)}


def contencao(a: str, b: str) -> float:
    """Share of the smaller n-gram set found in the other one (0 if either text has none)."""
    ga, gb = ngramas(a), ngramas(b)
    if not ga or not gb:
        return 0.0
    curto, longo = (ga, gb) if len(ga) <= len(gb) else (gb, ga)
    return len(curto & longo) / len(curto)


def desduplicar(evidencias: List[dict],
                limiar: float = LIMIAR_CONTENCAO) -> Tuple[List[dict], List[Dict]]:
    """Return (kept, removed), visiting passages longest first (equal lengths in input order)."""
    ordenadas = sorted(evidencias, key=lambda e: len(e["texto"]), reverse=True)
    mantidas: List[dict] = []
    removidas: List[Dict] = []

    for candidata in ordenadas:
        duplicada_de = None
        for mantida in mantidas:
            valor = contencao(candidata["texto"], mantida["texto"])
            if valor >= limiar:
                duplicada_de, score = mantida, valor
                break
        if duplicada_de is None:
            mantidas.append(candidata)
        else:
            removidas.append({
                "id": candidata["id"],
                "mantida": duplicada_de["id"],
                "metrica": f"contencao_{N_GRAMA}gramas",
                "score": round(score, 4),
            })

    # Input order, not length order: the plan sorts the passages by date afterwards.
    ids = {e["id"] for e in mantidas}
    return [e for e in evidencias if e["id"] in ids], removidas
