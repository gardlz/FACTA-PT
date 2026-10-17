"""Sentence splitter for the generated articles (Portuguese news text).

Any change here moves sentence boundaries, and with them the units of every citation metric.
"""

import re
from typing import List

# Abbreviations whose full stop does not end the sentence ("Sr.", "Dr.", "n.º", ...).
_ABREVIATURAS = {"s", "sr", "sra", "srs", "dr", "dra", "drs", "prof", "profs", "eng", "arq",
                 "art", "arts", "n", "nº", "av", "cf", "vol", "pág", "págs", "p", "pp", "ex",
                 "sto", "sta", "d"}


def _abreviatura(texto: str, i: int) -> bool:
    """True if the full stop at `i` closes an abbreviation or a single capital initial."""
    m = re.search(r"(\w+)$", texto[:i])
    if not m:
        return False
    palavra = m.group(1)
    return palavra.lower() in _ABREVIATURAS or (len(palavra) == 1 and palavra.isupper())


def frases(texto: str) -> List[str]:
    """Split into sentences, never after an abbreviation or inside «quotes» that do not end the sentence."""
    texto = (texto or "").strip()
    if not texto:
        return []
    # Unbalanced «» (e.g. a quotation cut by an excerpt window) are ignored, so that an unclosed «
    # cannot swallow the rest of the paragraph.
    equilibrado = texto.count("«") == texto.count("»")
    saida, inicio, profundidade, i, n = [], 0, 0, 0, len(texto)
    while i < n:
        c = texto[i]
        if equilibrado and c == "«":
            profundidade += 1
        elif equilibrado and c == "»":
            profundidade = max(0, profundidade - 1)
        elif c in ".!?…":
            # Closing », ) and ” stay with the sentence. A boundary then needs the end of the text,
            # or whitespace followed by a capital, a digit or «.
            j = i + 1
            while j < n and texto[j] in "»)”":
                if equilibrado and texto[j] == "»":
                    profundidade = max(0, profundidade - 1)
                j += 1
            resto = texto[j:]
            fronteira = not resto.strip() or re.match(r"\s+[A-ZÀ-Ý«0-9]", resto)
            if fronteira and profundidade == 0 and not (c == "." and _abreviatura(texto, i)):
                saida.append(texto[inicio:j].strip())
                inicio = j
            i = j
            continue
        i += 1
    if texto[inicio:].strip():
        saida.append(texto[inicio:].strip())
    return saida
