"""Splits a relevant news item into the three-sentence passages the entailment classifier reads.

A passage is three consecutive sentences, and consecutive passages are one sentence apart
(stride 1), so every run of three sentences is classified. The sentences are those NLTK's Punkt
model for Portuguese finds, `nltk.sent_tokenize(text, language="portuguese")`, the split that
built the classifier's training windows (`Document Relevance and Claim-Evidence
Entailment/src/entradas.py`). The text the classifier reads is the training window: the passage's
sentences with their whitespace collapsed, joined by one space. Offsets index the text served to
the page, so a citation can highlight its passage; that stretch differs from what the classifier
read in its spacing at most.
"""

from __future__ import annotations

from pathlib import Path

import nltk
from nltk.tokenize.punkt import PunktTokenizer

from ..schemas import Excerpt

FRASES_POR_EXCERTO = 3

# The Punkt data (`punkt_tab`) is looked up first in `web/nltk_data/`, where the Dockerfile
# downloads it (`/srv/nltk_data` in the image), then in NLTK's usual places.
nltk.data.path.insert(0, str(Path(__file__).resolve().parents[2] / "nltk_data"))
_PUNKT = PunktTokenizer("portuguese")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence, without surrounding whitespace."""
    frases = []
    for a, b in _PUNKT.span_tokenize(text):
        frase = text[a:b]
        if frase.strip():
            frases.append((a + len(frase) - len(frase.lstrip()),
                           b - (len(frase) - len(frase.rstrip()))))
    return frases


def build_excerpts(doc_id: str, text: str) -> list[Excerpt]:
    """Every run of three consecutive sentences; a news item with fewer gives one passage."""
    frases = split_sentences(text)
    if not frases:
        return []
    k = min(FRASES_POR_EXCERTO, len(frases))
    excertos = []
    for inicio in range(len(frases) - k + 1):
        janela = frases[inicio : inicio + k]
        excertos.append(
            Excerpt(
                id=f"{doc_id}-e{inicio + 1}",
                doc_id=doc_id,
                begin=janela[0][0],
                end=janela[-1][1],
                text=" ".join(" ".join(text[a:b].split()) for a, b in janela),
            )
        )
    return excertos
