"""A saved verification as the events the page receives: what a run sent while it ran, rebuilt
from what the store kept, every stage already over.

The page feeds them to the same reducer as a live run's, so a verification opened by its address
looks as it did when it finished. Like a worked example's (`demo/corrida.py`), none of it needs a
model or the corpus.
"""

from __future__ import annotations

from .schemas import STAGE_ORDER, RunResult


def _dados(nome: str, resultado: RunResult) -> dict:
    """What a finished stage added to the page, as its event carried it."""
    if nome == "questions":
        return {"questions": [p.model_dump() for p in resultado.questions]}
    if nome == "dedup":
        # Retrieved, and not yet judged relevant: the timeline fills before it narrows.
        return {"documents": [{**d.resumo(), "relevant": None} for d in resultado.documents]}
    if nome == "relevance":
        return {"documents": [d.resumo() for d in resultado.documents]}
    if nome == "stance":
        return {"stances": [e.model_dump() for e in resultado.stances],
                "decisive": resultado.decisive_excerpt_ids}
    if nome == "article":
        return {"articles": [a.model_dump() for a in resultado.articles]}
    return {}


def eventos(resultado: RunResult) -> list[dict]:
    """The run, from start to done, in the order its stages ran."""
    por_nome = {etapa.name: etapa for etapa in resultado.stages}
    saida = [{"type": "start", "run_id": resultado.run_id,
              "stages": [etapa.model_dump() for etapa in resultado.stages]}]
    for nome in STAGE_ORDER:
        etapa = por_nome.get(nome)
        if etapa is None:
            continue
        dados = _dados(nome, resultado) if etapa.status == "done" else {}
        saida.append({"type": "stage", "stage": etapa.model_dump(), **dados})
    saida.append({"type": "done"})
    return saida
