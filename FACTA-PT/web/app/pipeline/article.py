"""The article stage: the article, with its citation markers resolved to news passages.

The inference service writes it from the consolidated evidence (`evidencia.py`). The text is
served as written: only the `[En]` markers change, so that the page can make them clickable.
"""

from __future__ import annotations

import re

from ..schemas import Article, ArticleBlock, Citation, EvidenceDocument

# Citation markers as the writer emits them: `[E1]`, `[E2]`, ..., numbered as in its plan.
MARCADOR = re.compile(r"\s*\[E(\d+)\]")


def _resolver(artigo: dict, alvos: list[dict], documentos: list[EvidenceDocument]) -> Article:
    """`[E1]` becomes `[[C:1:E1]]`, numbered in the order of `alvos`; a marker with nothing to
    point at is dropped."""
    por_doc = {documento.doc_id: documento for documento in documentos}

    numeros: dict[str, int] = {}
    citacoes: list[Citation] = []
    for alvo in alvos:
        documento = por_doc.get(alvo["doc_id"])
        if documento is None:
            continue
        numeros[alvo["ref"]] = len(citacoes) + 1
        citacoes.append(
            Citation(
                marker=str(numeros[alvo["ref"]]),
                excerpt_id=alvo["ref"],
                doc_id=documento.doc_id,
                headline=documento.headline,
                published_at=documento.published_at,
                label=alvo["label"],
                excerpt_text=documento.content[alvo["begin"]:alvo["end"]],
                begin=alvo["begin"],
                end=alvo["end"],
            )
        )

    def substituir(texto: str) -> str:
        def troca(encontro: re.Match) -> str:
            ref = f"E{encontro.group(1)}"
            return f"[[C:{numeros[ref]}:{ref}]]" if ref in numeros else ""

        return MARCADOR.sub(troca, texto).strip()

    return Article(
        title=artigo.get("title") or "",
        lead=substituir(artigo.get("lead") or ""),
        blocks=[
            ArticleBlock(type=bloco["type"], text=substituir(bloco["text"]))
            for bloco in artigo["blocks"]
        ],
        citations=citacoes,
    )


def do_modelo(resposta: dict, documentos: list[EvidenceDocument]) -> Article:
    """The article the inference service wrote; its `evidence` maps each `[En]` to a passage.
    Citations are numbered in the order the article first cites them."""
    artigo = resposta["article"]
    por_ref = {e["ref"]: e for e in resposta["evidence"]}
    texto = " ".join([artigo.get("lead") or ""] + [b["text"] for b in artigo["blocks"]])
    citadas = dict.fromkeys(f"E{numero}" for numero in MARCADOR.findall(texto))
    return _resolver(artigo, [por_ref[ref] for ref in citadas if ref in por_ref], documentos)
