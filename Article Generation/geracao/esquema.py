"""The JSON schema imposed on the generator's output during decoding, one per plan.

It fixes the title, the sections and their order, the fixed paragraphs and the paragraph caps,
and restricts which evidence markers ([E1], [E2], ...) each part of the article may or must cite.
"""

from typing import List

import plano as pv

# Characters allowed in free text. The class is positive on purpose: in xgrammar 0.1.33 a negated
# class does not exclude non-ASCII characters. Curly quotes are left out (the prompt asks for «»),
# and so are control characters, C1 controls and characters outside the BMP (emoji).
_ASCII_LIVRE = " !#-Z^-~"                  # the space and visible ASCII except " [ \ ]
_UNICODE_LIVRE = "\u00a0-\u201b\u201f-\uffff"  # U+00A0-U+FFFF except “ ” „
# xgrammar matches `pattern` against the whole string as written in the JSON: `[...]*` constrains
# every character, and escapes are rejected.
TEXTO_SEM_RECTO = "[" + _ASCII_LIVRE + _UNICODE_LIVRE + "]*"
# The first character cannot be a space, so a lead or paragraph is never empty or all spaces.
INICIO = "[" + _ASCII_LIVRE.lstrip() + _UNICODE_LIVRE + "]"


def padrao_marcadores(refs: List[str]) -> str:
    """Free text whose only square brackets are the given markers; none if `refs` is empty."""
    if not refs:
        return INICIO + TEXTO_SEM_RECTO
    # Longest numbers first, for readability only: the alternation compiles to a union, so the
    # order does not change the accepted language.
    numeros = sorted({r[1:] for r in refs}, key=lambda n: (-len(n), int(n)))
    marcador = r"\[E(" + "|".join(numeros) + r")\]"
    return (INICIO + TEXTO_SEM_RECTO + "(" + marcador + TEXTO_SEM_RECTO + ")*")


def tecto(seccao: dict) -> int:
    """Maximum number of paragraphs of a free-text section, as set by the plan."""
    return seccao["max_paragrafos"]


def padrao_com_marcador(refs: List[str]) -> str:
    """Like `padrao_marcadores`, but at least one marker is required."""
    numeros = sorted({r[1:] for r in refs}, key=lambda n: (-len(n), int(n)))
    marcador = r"\[E(" + "|".join(numeros) + r")\]"
    return INICIO + TEXTO_SEM_RECTO + "(" + marcador + TEXTO_SEM_RECTO + ")+"


def _paragrafos(seccao: dict, plano: dict) -> dict:
    """A section's paragraphs, with markers required wherever the plan asks for citations."""
    if "texto_fixo" in seccao:
        return {"type": "array", "minItems": 1, "maxItems": 1,
                "items": {"const": seccao["texto_fixo"]}}

    permitidos = seccao["marcadores_permitidos"]
    if not permitidos:
        return {"type": "array", "minItems": 1, "maxItems": tecto(seccao),
                "items": {"type": "string", "pattern": padrao_marcadores([])}}
    com = {"type": "string", "pattern": padrao_com_marcador(permitidos)}
    if seccao["id"] != pv.S_VERIFICACAO:
        return {"type": "array", "minItems": 1, "maxItems": tecto(seccao), "items": com}
    # The verification may end with one paragraph without markers (the explanation): either every
    # paragraph cites, or k >= 1 citing paragraphs are followed by one that does not.
    livre = {"type": "string", "pattern": padrao_marcadores([])}
    alternativas = [{"type": "array", "minItems": 1, "maxItems": tecto(seccao), "items": com}]
    alternativas += [{"type": "array", "prefixItems": [com] * k + [livre],
                      "minItems": k + 1, "maxItems": k + 1}
                     for k in range(1, tecto(seccao))]
    return {"anyOf": alternativas}


def esquema_do_plano(plano: dict) -> dict:
    """Article schema for one plan: {title, lead, seccoes[{titulo, paragrafos[]}]}."""
    seccoes = [
        {"type": "object",
         "properties": {"titulo": {"const": s["titulo"]},
                        "paragrafos": _paragrafos(s, plano)},
         "required": ["titulo", "paragrafos"],
         "additionalProperties": False}
        for s in plano["seccoes"]
    ]
    return {
        "type": "object",
        "properties": {
            "title": {"const": plano["titulo"]},
            # The lead may cite only the evidence listed on the plan's LEAD line.
            "lead": {"type": "string", "pattern": padrao_marcadores(plano["lead_marcadores"])},
            "seccoes": {"type": "array", "prefixItems": seccoes,
                        "minItems": len(seccoes), "maxItems": len(seccoes)},
        },
        "required": ["title", "lead", "seccoes"],
        "additionalProperties": False,
    }


def para_blocos(dados: dict) -> List[dict]:
    """Convert the sectioned reply into heading/paragraph blocks (the generator's section and loop checks)."""
    blocos = []
    for seccao in dados.get("seccoes") or []:
        if not isinstance(seccao, dict):
            texto = str(seccao).strip()
            if texto:
                blocos.append({"type": "paragraph", "text": texto})
            continue
        titulo = (seccao.get("titulo") or "").strip()
        if titulo:
            blocos.append({"type": "heading", "text": titulo})
        for paragrafo in seccao.get("paragrafos") or []:
            texto = (paragrafo or "").strip() if isinstance(paragrafo, str) else ""
            if texto:
                blocos.append({"type": "paragraph", "text": texto})
    return blocos
