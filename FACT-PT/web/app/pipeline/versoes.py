"""Merges the several versions of the same LUSA news item, keeping only the fullest one.

LUSA does not correct a dispatch, it re-issues it: every re-issue enters the archive as a
NEW document with a NEW `doc_id`, and the NewsML field that should tell revisions apart
(`public_identifier`) is always `1`. Merging by `doc_id` alone catches none of this — the
same item takes 2 to 4 top-N slots and counts as that many pieces of evidence.

Two items are the same when any of these holds:

- re-issue: Jaccard of 8-grams >= 0.85 within 7 days (copy with image, `(REPETIÇÃO)`,
  `(CORREÇÃO)`);
- update: containment >= 0.75 within 8 h (`(ATUALIZADA)`, expanded `URGENTE`/`SMS`);
- equal headline: normalized headline equal within 8 h and containment >= 0.10 (the update
  that rewrites the text instead of adding to it).

The version with the MOST text wins, not the most recent: the agency sequence is
`Notícia` -> `(ATUALIZADA)` -> `c/ imagem`, and that last one re-issues the OLD text.

The rule and its thresholds are those of the retrieval experiments; changing one here makes
the website disagree with them about the same data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

TAMANHO_SHINGLE = 8

# Re-issue: practically the same text, so the date window can be generous. The threshold
# sits between the weakest true pair (0.875) and the strongest false positive (0.761)
# measured on the corpus; retune it on another corpus.
LIMIAR_JACCARD = 0.85
JANELA_REEMISSAO_H = 24 * 7

# Update: the older text is (almost) contained in the new one. The short window is what
# separates an update from a follow-up that repeats the framing — the nearest false pair
# is 14.6 h apart.
LIMIAR_CONTENCAO = 0.75
JANELA_ATUALIZACAO_H = 8

# Containment divides by the smaller set: in an 8-word text (1 shingle) a shared opening
# sentence alone would give 1.0. Below this many shingles the two containment rules do not
# apply and only Jaccard decides.
MINIMO_SHINGLES_CONTENCAO = 12

# Equal headline: same window as the update. The overlap required is minimal — it only
# separates a rewrite (which always repeats the opening) from the daily roundup that ships
# twice under the same headline with entirely different content.
LIMIAR_CONTENCAO_TITULO = 0.10

# Service note at the start of the dispatch: "(ESTA NOTÍCIA FOI SUBSTITUÍDA ...)",
# "(NOVA VERSÃO ...)", "(Corrige a informação ...)", "(REPETIÇÃO)". Not story text and it
# changes between versions, so it is stripped before measuring and comparing.
RE_NOTA_EDITORIAL = re.compile(r"^\s*\(([^()]{0,400}?)\)\s*")

# The agency states in the note that this version no longer stands.
RE_OBSOLETA = re.compile(r"SUBSTITU[ÍI]D|ANULAD", re.IGNORECASE)

# Dispatch header: "Lisboa, 07 abr 2021 (Lusa) -- ", sometimes preceded by
# "*** Serviço áudio disponível em www.lusa.pt ***" (C/ÁUDIO version only) or by
# "VERSÃO INTEGRAL CORRIGIDA:". All of it changes between versions while the body does not.
# `SMS` dispatches open with "Lusa: " instead.
RE_DATELINE = re.compile(r"^\s*lusa:\s*|^.{0,400}?\(lusa\)\s*-+\s*", re.IGNORECASE)
RE_NAO_PALAVRA = re.compile(r"[^0-9a-zà-öø-ÿ]+")

# Strip from the headline whatever changes between re-issues: the parenthesized markers —
# `(ATUALIZADA)`, `(C/ÁUDIO)`, `(REPETIÇÃO)` —, the flash `URGENTE:`/`SMS:` and the topic
# prefix (`OE2017:`, `Novo Banco:`), which the agency adds and removes.
RE_MARCADOR_TITULO = re.compile(r"\([^)]*\)")
RE_FLASH_TITULO = re.compile(r"^(?:urgente|flash|sms)\s*:?\s*", re.IGNORECASE)
RE_TEMA_TITULO = re.compile(r"^[^:]{1,30}:\s*")


def nota_editorial(texto):
    """The parenthesized service note opening the dispatch (or '' when there is none)."""
    encontrada = RE_NOTA_EDITORIAL.match(texto or "")
    return encontrada.group(1) if encontrada else ""


def corpo(texto):
    """The text without the leading service note — this is what counts as the story."""
    return RE_NOTA_EDITORIAL.sub("", texto or "", count=1)


def foi_substituida(documento):
    """Did LUSA itself declare this version replaced or cancelled?"""
    return bool(RE_OBSOLETA.search(nota_editorial(documento.get("content"))))


def normalizar(texto):
    """Text reduced to what is worth comparing: no service note, no header, words only."""
    texto = RE_DATELINE.sub("", corpo(texto).lower(), count=1)
    return RE_NAO_PALAVRA.sub(" ", texto).strip()


def palavras(documento):
    """Word count of the story, without any service note preceding it.

    Counted from the text and not from the API's `word_count`, which includes the note —
    that made a retracted version win the tie-break for being longer.
    """
    return len(corpo(documento.get("content")).split()) or (documento.get("word_count") or 0)


def titulo_comparavel(headline):
    """Headline without the parts the agency adds and removes between re-issues."""
    titulo = RE_MARCADOR_TITULO.sub(" ", (headline or "").lower())
    titulo = RE_TEMA_TITULO.sub("", RE_FLASH_TITULO.sub("", titulo))
    return RE_NAO_PALAVRA.sub(" ", titulo).strip()


def shingles(texto):
    """Set of the text's word n-grams (empty when the text is too short)."""
    unidades = normalizar(texto).split()
    return {" ".join(unidades[i:i + TAMANHO_SHINGLE])
            for i in range(len(unidades) - TAMANHO_SHINGLE + 1)}


def ler_data(valor):
    """`published_at` -> NAIVE datetime; None when missing or unreadable.

    LUSA dates all come without a timezone, but one aware value is enough to break date
    comparisons with TypeError, so aware ones are converted to UTC and stripped.
    """
    try:
        data = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    return data.astimezone(timezone.utc).replace(tzinfo=None) if data.tzinfo else data


def assinatura(documento):
    """What is needed from a document to compare it with the others.

    Returns `None` for documents that cannot be compared (not enough text, or no date):
    those always stay as a news item of their own and are never discarded.
    """
    marcas = shingles(documento.get("content"))
    data = ler_data(documento.get("published_at"))
    if not marcas or data is None:
        return None
    return {"doc_id": str(documento.get("doc_id")), "shingles": marcas, "data": data,
            "titulo": titulo_comparavel(documento.get("headline"))}


def mesma_noticia(uma, outra):
    """Two versions of the same news item? (re-issue, update or equal headline)."""
    horas = abs((outra["data"] - uma["data"]).total_seconds()) / 3600
    comuns = len(uma["shingles"] & outra["shingles"])
    if not comuns:
        return False
    if (comuns / len(uma["shingles"] | outra["shingles"]) >= LIMIAR_JACCARD
            and horas <= JANELA_REEMISSAO_H):
        return True
    menor = min(len(uma["shingles"]), len(outra["shingles"]))
    if horas > JANELA_ATUALIZACAO_H or menor < MINIMO_SHINGLES_CONTENCAO:
        return False
    contencao = comuns / menor
    return (contencao >= LIMIAR_CONTENCAO
            or (bool(uma["titulo"]) and uma["titulo"] == outra["titulo"]
                and contencao >= LIMIAR_CONTENCAO_TITULO))


def agrupar_versoes(documentos):
    """Groups documents by news item; returns a list of lists of `doc_id`.

    Single linkage: two documents land in the same group when a chain of similar pairs joins
    them, which is what resolves `flash -> story -> update`, whose ends no longer resemble
    each other. The time windows stop the chain from drifting: in the corpus the largest
    group has 6 versions and the widest spans 120 h (a genuine re-issue 5 days later).

    Documents that cannot be compared (no text or no date) each get a group of their own —
    when in doubt, discard nothing. Groups hold `doc_id`s, so a repeated `doc_id` appears
    only once: it is the same document.
    """
    assinaturas, vistos = [], set()
    for documento in documentos:
        marca = assinatura(documento)
        if marca and marca["doc_id"] not in vistos and documento.get("doc_id") is not None:
            vistos.add(marca["doc_id"])
            assinaturas.append(marca)
    assinaturas.sort(key=lambda a: a["data"])

    raiz = {a["doc_id"]: a["doc_id"] for a in assinaturas}

    def procurar(doc_id):
        while raiz[doc_id] != doc_id:
            raiz[doc_id] = raiz[raiz[doc_id]]
            doc_id = raiz[doc_id]
        return doc_id

    for i, uma in enumerate(assinaturas):
        for outra in assinaturas[i + 1:]:
            if (outra["data"] - uma["data"]).total_seconds() / 3600 > JANELA_REEMISSAO_H:
                break                                # sorted by date: the rest are even further
            if mesma_noticia(uma, outra):
                raiz[procurar(uma["doc_id"])] = procurar(outra["doc_id"])

    grupos = {}
    for a in assinaturas:
        grupos.setdefault(procurar(a["doc_id"]), []).append(a["doc_id"])

    # Incomparable documents stand alone, but once each: the input list may carry the same
    # `doc_id` twice.
    sozinhos, ja_agrupados = [], set(raiz)
    for documento in documentos:
        doc_id = str(documento.get("doc_id"))
        if doc_id not in ja_agrupados:
            ja_agrupados.add(doc_id)
            sozinhos.append([doc_id])
    return list(grupos.values()) + sozinhos


def escolher_versao(doc_ids, documentos):
    """The version that stays: the one with most words in the story body, ties broken by
    recency. A version LUSA declared replaced or cancelled only stays when there is no other.
    """
    def chave(doc_id):
        documento = documentos.get(str(doc_id)) or {}
        valida = not foi_substituida(documento)
        data = ler_data(documento.get("published_at")) or datetime.min
        return (valida, palavras(documento), data)

    return max(doc_ids, key=chave)


def agrupar_por_noticia(documentos):
    """[(doc_id kept, [doc_id of every version])], in input order: each news item takes the
    best position any of its versions held."""
    por_id, posicao = {}, {}
    for indice, documento in enumerate(documentos):
        doc_id = str(documento.get("doc_id"))
        por_id.setdefault(doc_id, documento)
        posicao.setdefault(doc_id, indice)

    grupos = [(min(posicao.get(d, len(documentos)) for d in grupo),
               escolher_versao(grupo, por_id), grupo)
              for grupo in agrupar_versoes(documentos)]
    return [(escolhido, grupo) for _, escolhido, grupo in sorted(grupos)]


