"""Question generation input window and output parsing, as in `Question Generation/src/`.

The ±1 sentence window is that of `model_utils.py`, the parsing that of `parsing_utils.py`. The
encoders were trained on another sentence split (`web/app/pipeline/excerpts.py`).
"""

from __future__ import annotations

import json
import re

from .prompts import INPUT_TEMPLATE

# Sentence end: ".", "!" or "?" before whitespace, except after common abbreviations and
# after an initial ("J. Silva").
_ABREVIATURAS = (r"(?<!\bSr)(?<!\bSra)(?<!\bDr)(?<!\bDra)(?<!\bEng)(?<!\bProf)(?<!\bex)(?<!\bp)"
                 r"(?<!\bfig)(?<!\bart)(?<!\bpág)(?<!\bvs)"
                 r"(?<!\s[A-ZÀ-Þ])")
_FIM_DE_FRASE = re.compile(r"(?<=[.!?])(?=\s)")

_BULLET = re.compile(r"^\s*(?:[-–—•*]|\d+[.)])\s*")
_PIPE = re.compile(r"\s*\|\|\s*")
_PERGUNTA = re.compile(r"[^?]+\?")

# Prompt headers a model may copy instead of answering; never questions.
ETIQUETAS_DO_MOLDE = tuple(re.findall(r"^([A-ZÀ-Þ][A-ZÀ-Þ ]*):", INPUT_TEMPLATE, re.M)) + (
    "Exemplos",)


def split_sentences(texto: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence. Cuts are positions, so a sentence starts on the space."""
    if not texto:
        return []
    cortes = [0]
    for encontro in _FIM_DE_FRASE.finditer(texto):
        i = encontro.start()
        if re.search(_ABREVIATURAS + r"[.!?]$", texto[:i]):
            cortes.append(i)
    cortes.append(len(texto))
    spans = [(a, b) for a, b in zip(cortes, cortes[1:]) if texto[a:b].strip()]
    return spans or [(0, len(texto))]


def localizar(context: str, claim_span: str) -> tuple[int, int] | None:
    """(start, end) of the claim in the context: verbatim, then with any whitespace between
    its words, then by its first six words."""
    if not context or not claim_span:
        return None
    i = context.find(claim_span)
    if i >= 0:
        return i, i + len(claim_span)
    palavras = [re.escape(p) for p in claim_span.split() if p]
    if not palavras:
        return None
    encontro = re.search(r"\s+".join(palavras), context)
    if encontro:
        return encontro.start(), encontro.end()
    encontro = re.search(r"\s+".join(palavras[:6]), context)
    if encontro:
        return encontro.start(), min(len(context), encontro.start() + len(claim_span))
    return None


def claim_context(context: str, claim_span: str) -> str:
    """Previous sentence, the claim's sentence(s) and the next one; "" when the claim cannot
    be located in the context."""
    alvo = localizar(context, claim_span)
    if alvo is None:
        return ""
    inicio, fim = alvo
    frases = split_sentences(context)
    tocadas = [i for i, (a, b) in enumerate(frases) if a < fim and b > inicio]
    if not tocadas:
        return ""
    primeira = max(0, tocadas[0] - 1)
    ultima = min(len(frases) - 1, tocadas[-1] + 1)
    return context[frases[primeira][0] : frases[ultima][1]].strip()


def _do_json(bruto: str) -> list[str] | None:
    texto = bruto.strip()
    if not (texto.startswith("{") or texto.startswith("[")):
        return None
    try:
        objecto = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if isinstance(objecto, dict):
        objecto = objecto.get("questions", [])
    if isinstance(objecto, list):
        return [str(x) for x in objecto if isinstance(x, (str, int, float))]
    return None


def _candidatos(bruto: str) -> list[str]:
    """Lines, then "||", then "?": several questions glued on one line are split on the "?"."""
    pedacos: list[str] = []
    for linha in bruto.splitlines():
        for pedaco in _PIPE.split(linha):
            encontros = list(_PERGUNTA.finditer(pedaco))
            if not encontros:
                pedacos.append(pedaco)
                continue
            pedacos.extend(e.group() for e in encontros)
            resto = pedaco[encontros[-1].end() :].strip()
            if resto:
                pedacos.append(resto)
    return pedacos


def _e_etiqueta(texto: str) -> bool:
    nu = texto.strip().rstrip("?:").strip().casefold()
    return any(nu == etiqueta.casefold() for etiqueta in ETIQUETAS_DO_MOLDE)


def parse_questions(bruto: str) -> list[str]:
    """Model output -> clean questions, without repetitions."""
    if not bruto:
        return []
    candidatos = _do_json(bruto)
    if candidatos is None:
        candidatos = _candidatos(bruto)

    perguntas: list[str] = []
    vistas: set[str] = set()
    for candidato in candidatos:
        pergunta = _BULLET.sub("", candidato).strip().strip("\"'` ").strip()
        if len(pergunta) < 3 or _e_etiqueta(pergunta):
            continue
        if not pergunta.endswith("?"):
            pergunta = pergunta.rstrip(".;:!") + "?"
        chave = pergunta.casefold()
        if chave in vistas:
            continue
        vistas.add(chave)
        perguntas.append(pergunta)
    return perguntas
