"""Merges reissues of the same LUSA news item, keeping the fullest version.

LUSA reissues a dispatch under a new `doc_id` (copy with image, update, expanded flash), so
equivalence is decided on the text: word 8-gram Jaccard, containment and normalised headline,
each within a time window. The rule and thresholds are those of the Evidence Retrieval stage
(`dedup_versions.py`).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

TAMANHO_SHINGLE = 8

# Reissue: almost the same text, so a generous window.
LIMIAR_JACCARD = 0.85
JANELA_REEMISSAO_H = 24 * 7

# Update: the earlier text is (almost) contained in the new one. The short window keeps out
# follow-ups that repeat the framing.
LIMIAR_CONTENCAO = 0.75
JANELA_ATUALIZACAO_H = 8

# Containment divides by the smaller set, so a very short text would match on a shared opening
# alone: below this many shingles only Jaccard decides.
MINIMO_SHINGLES_CONTENCAO = 12

# Same normalised headline, within the update window. The minimal overlap separates a rewrite,
# which repeats the opening, from a recurring roundup published under the same headline.
LIMIAR_CONTENCAO_TITULO = 0.10

# Editorial note at the start of a dispatch, e.g. "(NOVA VERSÃO ...)" or "(REPETIÇÃO)". It
# changes between versions, so it is stripped before comparing.
RE_NOTA_EDITORIAL = re.compile(r"^\s*\(([^()]{0,400}?)\)\s*")

# The note declares the version replaced or cancelled.
RE_OBSOLETA = re.compile(r"SUBSTITU[ÍI]D|ANULAD", re.IGNORECASE)

# Dispatch header ("<place>, <dd mmm yyyy> (Lusa) -- "), possibly preceded by an audio-service
# line; SMS dispatches start with "Lusa: ". It changes between versions while the body does not.
RE_DATELINE = re.compile(r"^\s*lusa:\s*|^.{0,400}?\(lusa\)\s*-+\s*", re.IGNORECASE)
RE_NAO_PALAVRA = re.compile(r"[^0-9a-zà-öø-ÿ]+")

# Headline parts that change between reissues: bracketed markers such as `(ATUALIZADA)`, flash
# prefixes (`URGENTE:`) and a topic prefix.
RE_MARCADOR_TITULO = re.compile(r"\([^)]*\)")
RE_FLASH_TITULO = re.compile(r"^(?:urgente|flash|sms)\s*:?\s*", re.IGNORECASE)
RE_TEMA_TITULO = re.compile(r"^[^:]{1,30}:\s*")


def nota_editorial(texto):
    """The bracketed editorial note opening the dispatch, or '' when there is none."""
    encontrada = RE_NOTA_EDITORIAL.match(texto or "")
    return encontrada.group(1) if encontrada else ""


def corpo(texto):
    """The text without the leading editorial note."""
    return RE_NOTA_EDITORIAL.sub("", texto or "", count=1)


def foi_substituida(documento):
    """Did the agency declare this version replaced or cancelled?"""
    return bool(RE_OBSOLETA.search(nota_editorial(documento.get("content"))))


def normalizar(texto):
    """Lower-cased words of the body, without editorial note and dispatch header."""
    texto = RE_DATELINE.sub("", corpo(texto).lower(), count=1)
    return RE_NAO_PALAVRA.sub(" ", texto).strip()


def palavras(documento):
    """Word count of the body, editorial note excluded (the API's `word_count` includes it)."""
    return len(corpo(documento.get("content")).split()) or (documento.get("word_count") or 0)


def titulo_comparavel(headline):
    """Headline without the parts the agency adds and removes between reissues."""
    titulo = RE_MARCADOR_TITULO.sub(" ", (headline or "").lower())
    titulo = RE_TEMA_TITULO.sub("", RE_FLASH_TITULO.sub("", titulo))
    return RE_NAO_PALAVRA.sub(" ", titulo).strip()


def shingles(texto):
    """Set of the text's word n-grams (empty when the text is too short)."""
    unidades = normalizar(texto).split()
    return {" ".join(unidades[i:i + TAMANHO_SHINGLE])
            for i in range(len(unidades) - TAMANHO_SHINGLE + 1)}


def ler_data(valor):
    """`published_at` as a naive datetime, or None. Aware values are converted to UTC, since a
    single aware value among naive ones makes comparisons raise TypeError."""
    try:
        data = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    return data.astimezone(timezone.utc).replace(tzinfo=None) if data.tzinfo else data


def assinatura(documento):
    """What is compared between documents; None when there is too little text or no date (the
    document then stays a news item of its own)."""
    marcas = shingles(documento.get("content"))
    data = ler_data(documento.get("published_at"))
    if not marcas or data is None:
        return None
    return {"doc_id": str(documento.get("doc_id")), "shingles": marcas, "data": data,
            "titulo": titulo_comparavel(documento.get("headline"))}


def mesma_noticia(uma, outra):
    """Two versions of the same news item? (reissue, update or same headline)"""
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
    """Groups documents by news item, as lists of `doc_id`.

    Single linkage, so a chain `flash -> story -> update` ends in one group even when its ends
    no longer resemble each other. Documents without text or date stay alone; a repeated
    `doc_id` appears once.
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

    # Incomparable documents stand alone, once each (the input may repeat a `doc_id`).
    sozinhos, ja_agrupados = [], set(raiz)
    for documento in documentos:
        doc_id = str(documento.get("doc_id"))
        if doc_id not in ja_agrupados:
            ja_agrupados.add(doc_id)
            sozinhos.append([doc_id])
    return list(grupos.values()) + sozinhos


def escolher_versao(doc_ids, documentos):
    """The version kept: not withdrawn by the agency, then most words, then most recent. Not
    simply the latest, because a later copy with image can carry the older text."""
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


