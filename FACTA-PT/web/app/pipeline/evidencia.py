"""Evidence consolidation: which classified passages reach the article writer.

Runs over the passages of the relevant news items. Steps 1-4 are those of Sections 6.2.2 and 8.1
of the dissertation:

1. every passage classified as supported or refuted is kept as decisive evidence;
2. a news item with at least one decisive passage forwards none of its nei passages;
3. a news item without decisive passages forwards one nei passage, the one with the smallest
   margin M(w) = z'_nei(w) - max(z'_supported(w), z'_refuted(w));
4. the article generation's deduplication (`Article Generation/geracao/dedup_excertos.py`):
   within each relation, the shorter of two passages is dropped when at least 90% of its word
   5-grams occur in the longer one;
5. passages of the same news item and relation that overlap or are separated only by
   whitespace are joined into one, unless the join would take in a whole window of that news
   item classified with the other decisive relation.

A news item that step 4 would leave without any passage of a relation it has keeps its most
confident passage of that relation for display only: the writer does not read it, since its text
is in a passage the writer reads, but the news item lists it and the article cites it right after
the passage it repeats.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ..schemas import LABELS, EvidenceDocument, EvidencePassage, Excerpt, ExcerptStance

DECISIVOS = ("supported", "refuted")

# Same normalisation, n-gram size and threshold as `Article Generation/geracao/dedup_excertos.py`.
LIMIAR_CONTENCAO = 0.90
N_GRAMA = 5

_ESPACO = re.compile(r"\s+")
_PONTUACAO = re.compile(r"[^\w\s]", re.UNICODE)


def normalizar(texto: str) -> str:
    """Lowercase, no accents, no punctuation, collapsed whitespace."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return _ESPACO.sub(" ", _PONTUACAO.sub(" ", texto.lower())).strip()


def ngramas(texto: str) -> set[str]:
    palavras = normalizar(texto).split()
    if len(palavras) < N_GRAMA:
        return {" ".join(palavras)} if palavras else set()
    return {" ".join(palavras[i : i + N_GRAMA]) for i in range(len(palavras) - N_GRAMA + 1)}


def contencao(a: str, b: str) -> float:
    """Share of the shorter text's n-grams that also occur in the longer one."""
    ga, gb = ngramas(a), ngramas(b)
    if not ga or not gb:
        return 0.0
    curto, longo = (ga, gb) if len(ga) <= len(gb) else (gb, ga)
    return len(curto & longo) / len(curto)


def desduplicar(excertos: list[Excerpt], absorvidas: dict[str, str]) -> list[Excerpt]:
    """The passages kept. Of each redundant pair the longer passage stays (on equal length, the
    first one); the kept ones come back in input order. `absorvidas` gets the id of each dropped
    passage mapped to the kept one it was found in."""
    mantidos: list[Excerpt] = []
    for candidato in sorted(excertos, key=lambda e: len(e.text), reverse=True):
        dentro = next((m for m in mantidos
                       if contencao(candidato.text, m.text) >= LIMIAR_CONTENCAO), None)
        if dentro is None:
            mantidos.append(candidato)
        else:
            absorvidas[candidato.id] = dentro.id
    ficam = {e.id for e in mantidos}
    return [e for e in excertos if e.id in ficam]


def margem(stance: ExcerptStance) -> float:
    """M(w): how far the nei adjusted logit is above the closest decisive one."""
    z = stance.logits
    return z["nei"] - max(z["supported"], z["refuted"])


def prioridade(stance: ExcerptStance) -> float:
    """What a passage is worth to the article; the lowest go first when the prompt is full.
    Decisive: its relation's logit minus the highest of the other two. Nei: -M(w), as in step 3."""
    if stance.logits is None:
        return 0.0
    if stance.label == "nei":
        return -margem(stance)
    z = stance.logits
    return z[stance.label] - max(v for rotulo, v in z.items() if rotulo != stance.label)


def juntar(
    guardados: list[tuple[EvidenceDocument, Excerpt, str]], prioridades: dict[str, float],
    contrarias: dict[tuple[str, str], list[tuple[int, int]]],
) -> list[EvidencePassage]:
    """Step 5. `guardados` holds (news item, passage, relation) in document order; passages of
    one news item and relation that overlap or touch become one, with the highest priority.
    `contrarias` holds, for (news item, relation), the offsets of that news item's windows
    classified with the other decisive relation: a join that would take one in whole does not
    happen, and the passage starts a new one."""
    passagens: list[EvidencePassage] = []
    abertas: dict[tuple[str, str], EvidencePassage] = {}
    for documento, excerto, rotulo in guardados:
        aberta = abertas.get((documento.doc_id, rotulo))
        if aberta is not None and (
            excerto.begin <= aberta.end
            or not documento.content[aberta.end : excerto.begin].strip()
        ) and not any(
            aberta.begin <= inicio and fim <= max(aberta.end, excerto.end)
            for inicio, fim in contrarias.get((documento.doc_id, rotulo), ())
        ):
            aberta.end = max(aberta.end, excerto.end)
            aberta.excerpt_ids.append(excerto.id)
            aberta.priority = max(aberta.priority, prioridades[excerto.id])
            continue
        aberta = EvidencePassage(id=excerto.id, doc_id=documento.doc_id, label=rotulo,
                                 begin=excerto.begin, end=excerto.end, excerpt_ids=[excerto.id],
                                 priority=prioridades[excerto.id])
        abertas[(documento.doc_id, rotulo)] = aberta
        passagens.append(aberta)
    for passagem in passagens:
        if len(passagem.excerpt_ids) > 1:
            passagem.id = f"{passagem.excerpt_ids[0]}..{passagem.excerpt_ids[-1]}"
    return passagens


@dataclass
class Consolidacao:
    # What the writer reads, in document order.
    evidencia: list[EvidencePassage]
    # Every supported or refuted passage, before deduplication, as the page shows them.
    decisivos: list[str]
    # The passages kept for display only, each with the writer's passage it repeats (`repeats`).
    repetidas: list[EvidencePassage]


def consolidar(
    documentos: list[EvidenceDocument], stances: list[ExcerptStance]
) -> Consolidacao:
    """Steps 1-5 over the classified passages of the given news items, and the passages kept for
    display only."""
    por_id = {s.excerpt_id: s for s in stances}
    mantidos: list[tuple[EvidenceDocument, Excerpt, str]] = []
    decisivos: list[str] = []

    for documento in documentos:
        classificados = [(e, por_id[e.id]) for e in documento.excerpts if e.id in por_id]
        if not classificados:
            continue
        escolhidos = [(e, s.label) for e, s in classificados if s.label in DECISIVOS]
        if not escolhidos:
            # `min` keeps the first of equal margins: the earliest passage in the document.
            excerto, _ = min(classificados, key=lambda par: margem(par[1]))
            escolhidos = [(excerto, "nei")]
        for excerto, rotulo in escolhidos:
            mantidos.append((documento, excerto, rotulo))
            if rotulo in DECISIVOS:
                decisivos.append(excerto.id)

    ficam: set[str] = set()
    absorvidas: dict[str, str] = {}
    for rotulo in LABELS:
        ficam.update(e.id for e in desduplicar([e for _, e, r in mantidos if r == rotulo],
                                                absorvidas))

    # Every window of the other decisive relation bars a join over it, whether the deduplication
    # kept it or not: its text was read as that relation.
    contrarias: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for documento in documentos:
        for excerto in documento.excerpts:
            estado = por_id.get(excerto.id)
            if estado is not None and estado.label in DECISIVOS:
                outra = DECISIVOS[1 - DECISIVOS.index(estado.label)]
                contrarias.setdefault((documento.doc_id, outra), []).append(
                    (excerto.begin, excerto.end))

    evidencia = juntar(
        [(d, e, r) for d, e, r in mantidos if e.id in ficam],
        {e.id: prioridade(por_id[e.id]) for _, e, _ in mantidos},
        contrarias,
    )

    # A news item and relation the deduplication left with nothing keeps its most confident
    # passage (on equal priority, the earliest), shown and never read. Of windows with the same
    # text it is the first, the one a citation of that text is found at. What it repeats was
    # kept, so it lies inside one of the writer's passages.
    passagem_de = {i: passagem for passagem in evidencia for i in passagem.excerpt_ids}
    grupos: dict[tuple[str, str], list[tuple[EvidenceDocument, Excerpt]]] = {}
    for documento, excerto, rotulo in mantidos:
        grupos.setdefault((documento.doc_id, rotulo), []).append((documento, excerto))
    repetidas = []
    for (doc_id, rotulo), membros in grupos.items():
        if any(e.id in ficam for _, e in membros):
            continue
        documento, melhor = max(membros, key=lambda par: prioridade(por_id[par[1].id]))
        texto = documento.content[melhor.begin:melhor.end]
        excerto = next(e for _, e in membros if documento.content[e.begin:e.end] == texto)
        repetidas.append(EvidencePassage(
            id=excerto.id, doc_id=doc_id, label=rotulo, begin=excerto.begin, end=excerto.end,
            excerpt_ids=[excerto.id], priority=prioridade(por_id[excerto.id]),
            repeats=passagem_de[absorvidas[excerto.id]].id,
        ))
    return Consolidacao(evidencia=evidencia, decisivos=decisivos, repetidas=repetidas)
