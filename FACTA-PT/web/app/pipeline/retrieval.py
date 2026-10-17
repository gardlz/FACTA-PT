"""Stages 2 and 3: retrieve each question's news items from LUSA, then merge duplicates.

Sources must predate the claim: the search stops at the day before it, so the news item where
the claim was made cannot enter as evidence.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from ..schemas import EvidenceDocument, FoundBy, Question
from ..services.lusa import LusaClient
from . import versoes


def data_limite(claim_date: date) -> str:
    """Day before the claim, in the format the API accepts."""
    return (claim_date - timedelta(days=1)).isoformat()


def _documento(doc: dict, hit: dict, question_id: str, rank: int) -> EvidenceDocument:
    return EvidenceDocument(
        doc_id=str(hit["doc_id"]),
        headline=doc.get("headline") or hit.get("headline") or "",
        published_at=doc.get("published_at") or hit.get("published_at") or "",
        genre=doc.get("genre") or hit.get("genre") or "",
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
) -> list[EvidenceDocument]:
    """The hits of every question, with their full documents, in search order.

    Each search asks for `overfetch` times `top_k` results, because merging reissues frees slots;
    `deduplicate` makes the cut. Hits whose document has no text are dropped.
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
    for question, hits in pesquisas:
        for posicao, hit in enumerate(hits, start=1):
            doc_id = str(hit["doc_id"])
            documento = conteudos.get(doc_id) or {}
            if not (documento.get("content") or "").strip():
                continue
            rank = int(hit.get("rank") or posicao)
            recuperados.append(_documento(documento, hit, question.id, rank))
    return recuperados


def deduplicate(documentos: list[EvidenceDocument], top_k: int) -> list[EvidenceDocument]:
    """One entry per news item, keeping the first `top_k` distinct items of each question.

    Merges the same `doc_id` found by several questions, and reissues of a dispatch under a new
    `doc_id` (`versoes.py`); the version kept inherits the `found_by` of all of them.
    """
    vistos: dict[str, EvidenceDocument] = {}
    ordem: list[str] = []
    for documento in documentos:
        if documento.doc_id in vistos:
            vistos[documento.doc_id].found_by.extend(documento.found_by)
            continue
        vistos[documento.doc_id] = documento
        ordem.append(documento.doc_id)
    por_id = [vistos[doc_id] for doc_id in ordem]

    # Reissues: the same dispatch under different `doc_id`s.
    como_dict = [
        {"doc_id": d.doc_id, "headline": d.headline, "published_at": d.published_at,
         "content": d.content, "word_count": d.word_count}
        for d in por_id
    ]
    finais: list[EvidenceDocument] = []
    for escolhido, grupo in versoes.agrupar_por_noticia(como_dict):
        documento = vistos[str(escolhido)]
        for outro in grupo:
            if str(outro) != str(escolhido):
                documento.found_by.extend(vistos[str(outro)].found_by)
        finais.append(documento)

    for documento in finais:
        documento.found_by.sort(key=lambda f: (f.question_id, f.rank))

    # The cut comes after merging, when the distinct items of each question are known.
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
    return [d for d in finais if d.doc_id in ficam]
