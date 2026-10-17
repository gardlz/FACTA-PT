"""Splits a relevant news item into the three-sentence passages the entailment classifier reads.

Consecutive passages are one sentence apart (stride 1), so every run of three sentences is
classified. Offsets index the text served to the page, so a citation can highlight its passage.
"""

from __future__ import annotations

import re

from ..schemas import Excerpt

FRASES_POR_EXCERTO = 3

# The sentence split that built the classifier's training passages
# (`Document Relevance and Claim-Evidence Entailment/src/entradas.py`), so the premises match the ones it learned from.
_FIM_DE_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚ«\"])")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence, without surrounding whitespace."""
    limites, inicio = [], 0
    for fim_de_frase in _FIM_DE_FRASE.finditer(text):
        limites.append((inicio, fim_de_frase.start()))
        inicio = fim_de_frase.end()
    limites.append((inicio, len(text)))

    frases = []
    for a, b in limites:
        frase = text[a:b]
        if frase.strip():
            a += len(frase) - len(frase.lstrip())
            b -= len(frase) - len(frase.rstrip())
            frases.append((a, b))
    return frases


def build_excerpts(doc_id: str, text: str) -> list[Excerpt]:
    """Every run of three consecutive sentences; a news item with fewer gives one passage."""
    frases = split_sentences(text)
    if not frases:
        return []
    excertos = []
    for inicio in range(max(1, len(frases) - FRASES_POR_EXCERTO + 1)):
        janela = frases[inicio : inicio + FRASES_POR_EXCERTO]
        begin, end = janela[0][0], janela[-1][1]
        excertos.append(
            Excerpt(
                id=f"{doc_id}-e{inicio + 1}",
                doc_id=doc_id,
                begin=begin,
                end=end,
                text=text[begin:end],
            )
        )
    return excertos
