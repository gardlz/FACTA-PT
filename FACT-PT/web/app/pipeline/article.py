"""The article stage: the article with its citations resolved.

The inference service writes it from the consolidated evidence (`evidencia.py`), with the
configuration the article-generation pipeline evaluated. Its text is served exactly as the model
wrote it; only the citation markers change shape, so the frontend can make them clickable. A
passage the writer did not read because its text repeats one it cites (`evidencia.consolidar`)
is cited right after that one.
"""

from __future__ import annotations

import re

from ..schemas import (Article, ArticleBlock, Citation, CitedExcerpt, EvidenceDocument,
                       EvidencePassage)

# The writer cites `[E1]`, `[E2]`…: one number per piece of evidence of the plan it wrote against.
MARCADOR = re.compile(r"\s*\[E(\d+)\]")


def janelas_dentro(documento: EvidenceDocument, inicio: int, fim: int,
                   rotulos: dict[str, str]) -> list[CitedExcerpt]:
    """The classified windows of `documento` that lie whole inside [inicio, fim), in document
    order, each with the label the stance classifier gave it."""
    return [
        CitedExcerpt(excerpt_id=janela.id, label=rotulos[janela.id], begin=janela.begin,
                     end=janela.end, text=documento.content[janela.begin:janela.end])
        for janela in documento.excerpts
        if inicio <= janela.begin and janela.end <= fim and janela.id in rotulos
    ]


def _resolver(modelo: str, artigo: dict, alvos: list[dict],
              documentos: list[EvidenceDocument],
              repetidas: list[EvidencePassage] | None = None,
              rotulos: dict[str, str] | None = None) -> Article:
    """`[E1]` becomes `[[C:1:E1]]`, numbered in the order of `alvos`; a marker with nothing to
    point at is dropped. A passage of `repetidas` that repeats the one `[E1]` points at is cited
    right after it, with the next number: `[[C:1:E1]][[C:2:E1+<its id>]]`. Each citation lists
    the classified windows inside its passage, with the labels of `rotulos`."""
    por_doc = {documento.doc_id: documento for documento in documentos}
    por_repetida: dict[str, list[EvidencePassage]] = {}
    for passagem in repetidas or []:
        if passagem.repeats:
            por_repetida.setdefault(passagem.repeats, []).append(passagem)

    # What each marker stands for: (number, excerpt id) of its own citation, then of the
    # passages that repeat it.
    numeros: dict[str, list[tuple[int, str]]] = {}
    citacoes: list[Citation] = []

    def citar(chave: str, documento: EvidenceDocument, rotulo: str, inicio: int,
              fim: int) -> tuple[int, str]:
        citacoes.append(
            Citation(
                marker=str(len(citacoes) + 1),
                excerpt_id=chave,
                doc_id=documento.doc_id,
                headline=documento.headline,
                published_at=documento.published_at,
                label=rotulo,
                excerpt_text=documento.content[inicio:fim],
                begin=inicio,
                end=fim,
                excerpts=janelas_dentro(documento, inicio, fim, rotulos or {}),
            )
        )
        return len(citacoes), chave

    for alvo in alvos:
        documento = por_doc.get(alvo["doc_id"])
        if documento is None or alvo["ref"] in numeros:
            continue
        numeros[alvo["ref"]] = [citar(alvo["ref"], documento, alvo["label"], alvo["begin"],
                                      alvo["end"])]
        for passagem in por_repetida.get(alvo.get("id") or "", []):
            outro = por_doc.get(passagem.doc_id)
            if outro is not None:
                numeros[alvo["ref"]].append(citar(f"{alvo['ref']}+{passagem.id}", outro,
                                                  passagem.label, passagem.begin, passagem.end))

    def substituir(texto: str) -> str:
        def troca(encontro: re.Match) -> str:
            ref = f"E{encontro.group(1)}"
            return "".join(f"[[C:{numero}:{chave}]]" for numero, chave in numeros.get(ref, []))

        return MARCADOR.sub(troca, texto).strip()

    return Article(
        model=modelo,
        title=artigo.get("title") or "",
        lead=substituir(artigo.get("lead") or ""),
        blocks=[
            ArticleBlock(type=bloco["type"], text=substituir(bloco["text"]))
            for bloco in artigo["blocks"]
        ],
        citations=citacoes,
    )


def do_modelo(resposta: dict, documentos: list[EvidenceDocument], modelo: str,
              repetidas: list[EvidencePassage] | None = None,
              rotulos: dict[str, str] | None = None) -> Article:
    """The article `modelo` wrote, as the inference service sent it. Its `evidence` maps each
    `[En]` of the plan to the passage it numbered; citations are listed in the order the article
    first cites them, each followed by the passages of `repetidas` that repeat it, and each with
    the classified windows inside its passage (`rotulos`: excerpt id -> label)."""
    artigo = resposta["article"]
    por_ref = {e["ref"]: e for e in resposta["evidence"]}
    texto = " ".join([artigo.get("lead") or ""] + [b["text"] for b in artigo["blocks"]])
    citadas = dict.fromkeys(f"E{numero}" for numero in MARCADOR.findall(texto))
    return _resolver(modelo, artigo, [por_ref[ref] for ref in citadas if ref in por_ref],
                     documentos, repetidas, rotulos)
