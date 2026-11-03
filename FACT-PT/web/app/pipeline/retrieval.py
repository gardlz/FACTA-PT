"""Stages 2 and 3: retrieve each question's news items from LUSA and drop duplicates.

Sources must predate the date the claim was made: search is capped at the day before, so
the news item where the claim was uttered cannot enter as evidence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from ..schemas import EvidenceDocument, FoundBy, Question
from ..services.lusa import LusaClient
from . import versoes

logger = logging.getLogger(__name__)


def data_limite(claim_date: date) -> str:
    """Day before the claim, in the format the API accepts."""
    return (claim_date - timedelta(days=1)).isoformat()


def _documento(doc: dict, hit: dict, question_id: str, rank: int) -> EvidenceDocument:
    return EvidenceDocument(
        doc_id=str(hit["doc_id"]),
        headline=doc.get("headline") or hit.get("headline") or "",
        published_at=doc.get("published_at") or hit.get("published_at") or "",
        genre=doc.get("genre") or hit.get("genre") or "",
        topics=list(doc.get("topic_names_pt") or hit.get("topics") or []),
        byline=doc.get("byline") or "",
        word_count=doc.get("word_count"),
        content=doc.get("content") or "",
        found_by=[FoundBy(question_id=question_id, rank=rank)],
    )


async def retrieve(
    client: LusaClient,
    questions: list[Question],
    claim_date: date,
    top_k: int,
    concurrency: int,
    overfetch: int = 2,
) -> tuple[list[EvidenceDocument], dict[str, int | str]]:
    """Top-k news items per question, in the order the search returned them.

    `overfetch` times the cut is requested because deduplication merges re-issues of the
    same news item and those slots have to be refilled: the API's first 5 results hold 3.87
    distinct items on average, not 5.

    The same item can show up for several questions; deduplication merges them. Here the
    result mirrors what the API returned, so each stage's counts stay honest.
    """
    limite = data_limite(claim_date)
    semaforo = asyncio.Semaphore(max(1, concurrency))

    async def pesquisar(question: Question) -> tuple[Question, list[dict]]:
        async with semaforo:
            pedidos = max(top_k, top_k * max(1, overfetch))
            resposta = await client.search(question.text, size=pedidos, date_to=limite)
        return question, list(resposta.get("results") or [])[:pedidos]

    pesquisas = await asyncio.gather(*(pesquisar(q) for q in questions))

    doc_ids: list[str] = []
    for _, hits in pesquisas:
        for hit in hits:
            doc_id = str(hit["doc_id"])
            if doc_id not in doc_ids:
                doc_ids.append(doc_id)

    async def carregar(doc_id: str) -> tuple[str, dict]:
        async with semaforo:
            return doc_id, await client.get_document(doc_id)

    conteudos: dict[str, dict] = {}
    if doc_ids:
        for doc_id, documento in await asyncio.gather(*(carregar(d) for d in doc_ids)):
            conteudos[doc_id] = documento

    recuperados: list[EvidenceDocument] = []
    total_hits = 0
    sem_conteudo = 0
    for question, hits in pesquisas:
        total_hits += len(hits)
        for posicao, hit in enumerate(hits, start=1):
            doc_id = str(hit["doc_id"])
            documento = conteudos.get(doc_id) or {}
            if not (documento.get("content") or "").strip():
                sem_conteudo += 1
                continue
            rank = int(hit.get("rank") or posicao)
            recuperados.append(_documento(documento, hit, question.id, rank))

    estatisticas = {
        "perguntas": len(questions),
        "hits": total_hits,
        "recuperados": len(recuperados),
        "sem_conteudo": sem_conteudo,
        "ate": limite,
    }
    return recuperados, estatisticas


def deduplicate(
    documentos: list[EvidenceDocument], top_k: int | None = None
) -> tuple[list[EvidenceDocument], dict[str, int]]:
    """One entry per NEWS ITEM, not per identifier, and at most `top_k` per question.

    Two repetitions are merged: sibling questions that returned the same document (same
    `doc_id`), and reissues of the same dispatch, which LUSA publishes under a new `doc_id`
    and only the text can catch (`versoes.py`). The version with the most text is kept and
    inherits every version's origins: which question found it, and at which position.

    The cut counts distinct news items in each question's own ranking: an item stays when it
    is among the first `top_k` of at least one question.
    """
    vistos: dict[str, EvidenceDocument] = {}
    ordem: list[str] = []
    repetidos = 0
    for documento in documentos:
        if documento.doc_id in vistos:
            vistos[documento.doc_id].found_by.extend(documento.found_by)
            repetidos += 1
            continue
        vistos[documento.doc_id] = documento
        ordem.append(documento.doc_id)
    por_id = [vistos[doc_id] for doc_id in ordem]

    # Re-issues, now over documents already distinct by identifier.
    como_dict = [
        {"doc_id": d.doc_id, "headline": d.headline, "published_at": d.published_at,
         "content": d.content, "word_count": d.word_count}
        for d in por_id
    ]
    finais: list[EvidenceDocument] = []
    reemissoes = 0
    for escolhido, grupo in versoes.agrupar_por_noticia(como_dict):
        documento = vistos[str(escolhido)]
        for outro in grupo:
            if str(outro) != str(escolhido):
                documento.found_by.extend(vistos[str(outro)].found_by)
                reemissoes += 1
        finais.append(documento)

    for documento in finais:
        documento.found_by.sort(key=lambda f: (f.question_id, f.rank))

    # The cut runs here and not at search time: only once versions are merged is it known
    # how many DISTINCT news items each question brought.
    cortados = 0
    if top_k is not None:
        por_pergunta: dict[str, list[tuple[int, str]]] = {}
        for documento in finais:
            for origem in documento.found_by:
                por_pergunta.setdefault(origem.question_id, []).append(
                    (origem.rank, documento.doc_id)
                )
        ficam: set[str] = set()
        for ranking in por_pergunta.values():
            distintos = list(dict.fromkeys(doc_id for _, doc_id in sorted(ranking)))
            ficam.update(distintos[:top_k])
        cortados = sum(1 for d in finais if d.doc_id not in ficam)
        finais = [d for d in finais if d.doc_id in ficam]

    return finais, {
        "entrada": len(documentos),
        "distintos": len(finais),
        "repetidos": repetidos,
        "reemissoes": reemissoes,
        "fora_do_corte": cortados,
    }

