"""Evidence consolidation: which classified passages reach the article writer.

Runs over the passages of the relevant news items, after classification:

1. every passage classified as supported or refuted is kept as decisive evidence;
2. a news item with at least one decisive passage forwards none of its nei passages;
3. a news item whose passages are all nei forwards one of them: the one with the smallest
   margin to the closest decisive class, M(w) = z'_nei(w) - max(z'_supported(w), z'_refuted(w)).
   The margin only ranks; the passage stays nei;
4. the article generation's deduplication then runs over what was kept: within each relation,
   the shorter of two passages is dropped when at least 90% of its word 5-grams occur in the
   longer one. A news item it would leave without any passage of a relation it has keeps the
   most confident of them all the same, for display only: the writer does not read it, since it
   repeats a passage the writer reads, but the news item shows it, and an article that cites
   the passage it repeats cites it right after;
5. last, passages of the same news item with the same relation that overlap or follow one
   another - nothing but whitespace between them - are joined into one, from the first one's
   start to the last one's end. The windows advance one sentence at a time, so a decisive
   stretch of text is classified two or three times over, and unjoined the writer would read
   it as often. Joining comes after the deduplication, which stays as the article generation
   ran it, on three-sentence windows. A news item forwards at most one nei passage, so in
   practice only supported and refuted passages join. A join never takes in a whole window of
   the same news item classified with the other decisive relation: two supported windows that
   touch around refuted ones would make one supported passage of text the classifier read as
   refuted, so the next window starts a passage of its own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..schemas import LABELS, EvidenceDocument, EvidencePassage, Excerpt, ExcerptStance

DECISIVOS = ("supported", "refuted")

# The article generation's deduplication, verbatim: same normalisation, n-gram and threshold.
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


def desduplicar(
    excertos: list[Excerpt], absorvidas: dict[str, str] | None = None
) -> tuple[list[Excerpt], list[Excerpt]]:
    """(kept, dropped). Of each redundant pair the longer passage stays (on equal length, the
    first one); the kept ones come back in input order. `absorvidas`, when given, gets the id of
    each dropped passage mapped to the kept one it was found in."""
    mantidos: list[Excerpt] = []
    removidos: list[Excerpt] = []
    for candidato in sorted(excertos, key=lambda e: len(e.text), reverse=True):
        dentro = next((m for m in mantidos
                       if contencao(candidato.text, m.text) >= LIMIAR_CONTENCAO), None)
        if dentro is not None:
            removidos.append(candidato)
            if absorvidas is not None:
                absorvidas[candidato.id] = dentro.id
        else:
            mantidos.append(candidato)
    ficam = {e.id for e in mantidos}
    return [e for e in excertos if e.id in ficam], removidos


def margem(stance: ExcerptStance) -> float:
    """M(w): how far the nei adjusted logit is above the closest decisive one."""
    z = stance.logits
    return z["nei"] - max(z["supported"], z["refuted"])


def prioridade(stance: ExcerptStance) -> float:
    """How much the passage is worth to the article: for a decisive passage, how far its
    relation's logit is above the closest other one; for a nei passage, minus M(w), the ranking of
    step 3 - the closer to deciding, the more it says. When the passages do not all fit the
    article's prompt, the lowest go first."""
    if stance.logits is None:
        return 0.0
    if stance.label == "nei":
        return -margem(stance)
    z = stance.logits
    return z[stance.label] - max(v for rotulo, v in z.items() if rotulo != stance.label)


def juntar(
    guardados: list[tuple[EvidenceDocument, Excerpt, str]], prioridades: dict[str, float],
    contrarias: dict[tuple[str, str], list[tuple[int, int]]] | None = None,
) -> list[EvidencePassage]:
    """Step 5. `guardados` holds (news item, passage, relation) in document order; each run of
    passages of one news item and one relation that overlap or touch becomes one passage, with
    the highest priority among them. `contrarias` holds, for (news item, relation), the offsets
    of that news item's windows classified with the other decisive relation: a join that would
    take one in whole does not happen."""
    contrarias = contrarias or {}
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
    # Every supported or refuted passage, before deduplication: the classification the page
    # shows on the timeline and in the balance.
    decisivos: list[str]
    contagem: dict[str, int]
    # The passages kept for display only (step 4), each with the writer's passage it repeats.
    repetidas: list[EvidencePassage] = field(default_factory=list)


def consolidar(
    documentos: list[EvidenceDocument], stances: list[ExcerptStance]
) -> Consolidacao:
    por_id = {s.excerpt_id: s for s in stances}
    mantidos: list[tuple[EvidenceDocument, Excerpt, str]] = []
    decisivos: list[str] = []
    contagem = {"supported": 0, "refuted": 0, "nei": 0, "nei_descartados": 0}

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
            contagem[rotulo] += 1
            if rotulo in DECISIVOS:
                decisivos.append(excerto.id)
        contagem["nei_descartados"] += len(classificados) - len(escolhidos)

    ficam: set[str] = set()
    absorvidas: dict[str, str] = {}
    repetidos = 0
    for rotulo in LABELS:
        guardados, fora = desduplicar([e for _, e, r in mantidos if r == rotulo], absorvidas)
        ficam.update(e.id for e in guardados)
        repetidos += len(fora)

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

    # Step 4's exception: a news item and relation the deduplication left with nothing keeps its
    # most confident passage (on equal priority, the earliest), shown and never read. Of windows
    # of the same text it is the first, the one a citation of that text is found at. What it
    # repeats was kept, so it is inside one of the writer's passages.
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
    return Consolidacao(
        evidencia=evidencia,
        decisivos=decisivos,
        repetidas=repetidas,
        contagem={
            "classificados": len(stances),
            **contagem,
            "repetidos": repetidos,
            # Passages that went into the one before them.
            "juntos": len(ficam) - len(evidencia),
            "evidencia": len(evidencia),
        },
    )
