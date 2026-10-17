"""The JSON Schema imposed while decoding, one per plan (`Article Generation/geracao/esquema.py`).

Title, section titles and fixed paragraphs are `const`, and each section can write only its own
markers. xgrammar reads a `pattern` as the whole string: checking elsewhere needs `re.fullmatch`.
"""

from __future__ import annotations

from . import plano as pv

# A POSITIVE class, since in xgrammar 0.1.33 a negated one does not exclude non-ASCII characters:
# visible ASCII, the space and U+00A0-U+FFFF, without " [ \ ] and U+201C-U+201E (“ ” „).
_ASCII_LIVRE = " !#-Z^-~"                  # visible ASCII without " [ \ ], and the space
_UNICODE_LIVRE = " -‛‟-￿"
TEXTO_SEM_RECTO = "[" + _ASCII_LIVRE + _UNICODE_LIVRE + "]*"
# The first character of a free string is visible: no empty or blank lead or paragraph.
INICIO = "[" + _ASCII_LIVRE.lstrip() + _UNICODE_LIVRE + "]"


def _alternativa(refs: list[str]) -> str:
    numeros = sorted({r[1:] for r in refs}, key=lambda n: (-len(n), int(n)))
    return r"\[E(" + "|".join(numeros) + r")\]"


def padrao_marcadores(refs: list[str]) -> str:
    """Text whose only possible square bracket is one of these markers; none when `refs` is
    empty."""
    if not refs:
        return INICIO + TEXTO_SEM_RECTO
    return INICIO + TEXTO_SEM_RECTO + "(" + _alternativa(refs) + TEXTO_SEM_RECTO + ")*"


def padrao_com_marcador(refs: list[str]) -> str:
    """As `padrao_marcadores`, but with AT LEAST one of these markers."""
    return INICIO + TEXTO_SEM_RECTO + "(" + _alternativa(refs) + TEXTO_SEM_RECTO + ")+"


def _paragrafos(seccao: dict) -> dict:
    if "texto_fixo" in seccao:
        return {"type": "array", "minItems": 1, "maxItems": 1,
                "items": {"const": seccao["texto_fixo"]}}

    tecto = seccao["max_paragrafos"]
    permitidos = seccao["marcadores_permitidos"]
    if not permitidos:
        return {"type": "array", "minItems": 1, "maxItems": tecto,
                "items": {"type": "string", "pattern": padrao_marcadores([])}}
    com = {"type": "string", "pattern": padrao_com_marcador(permitidos)}
    if seccao["id"] != pv.S_VERIFICACAO:
        return {"type": "array", "minItems": 1, "maxItems": tecto, "items": com}
    # k paragraphs with markers, or k with markers and the explanation without, at the end.
    livre = {"type": "string", "pattern": padrao_marcadores([])}
    alternativas = [{"type": "array", "minItems": 1, "maxItems": tecto, "items": com}]
    alternativas += [{"type": "array", "prefixItems": [com] * k + [livre],
                      "minItems": k + 1, "maxItems": k + 1}
                     for k in range(1, tecto)]
    return {"anyOf": alternativas}


def esquema_do_plano(plano: dict) -> dict:
    """{title, lead, seccoes[{titulo, paragrafos[]}]}, with this plan's sections."""
    seccoes = [
        {"type": "object",
         "properties": {"titulo": {"const": s["titulo"]},
                        "paragrafos": _paragrafos(s)},
         "required": ["titulo", "paragrafos"],
         "additionalProperties": False}
        for s in plano["seccoes"]
    ]
    return {
        "type": "object",
        "properties": {
            "title": {"const": plano["titulo"]},
            "lead": {"type": "string", "pattern": padrao_marcadores(plano["lead_marcadores"])},
            "seccoes": {"type": "array", "prefixItems": seccoes,
                        "minItems": len(seccoes), "maxItems": len(seccoes)},
        },
        "required": ["title", "lead", "seccoes"],
        "additionalProperties": False,
    }
