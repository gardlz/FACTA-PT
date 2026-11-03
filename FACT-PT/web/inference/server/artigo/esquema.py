"""The grammar: the JSON Schema imposed while decoding (`v2_campanha2/esquema_v2.py`).

One schema per plan. The prompt ASKS; this IMPOSES - a token that would make the output invalid
gets probability zero. What it imposes:

* `title` is a `const`, and `seccoes` has exactly the plan's sections, in order, with their
  exact titles as `const`;
* the paragraphs of «Limites da verificação» and «Conclusão» are `const`;
* in all free text: no `"`, no backslash, no line breaks or other control characters, no curly
  double quotes, and no square brackets outside the markers;
* only markers that exist in the plan can be written, and each section only those that belong
  to it: the lead the ones its LEAD line lists, «A claim» none, «Enquadramento factual» the nei,
  «A verificação» the deciding ones;
* every paragraph of «Enquadramento factual» and of a deciding «A verificação» carries at least
  one marker, and the verification may end with one paragraph without any - the explanation.

`pattern` is compiled by xgrammar as the language of the WHOLE string. A generic JSON Schema
validator reads it as a search and accepts anything with this `[...]*`; checking an output
outside the model means anchoring the patterns (`re.fullmatch`).

The character class is POSITIVE: in the xgrammar of the evaluated run (0.1.33) a negated class
does not exclude non-ASCII characters. It allows visible ASCII without «"», «[», «\\» and «]»,
the space, and Unicode from U+00A0 to U+FFFF with a hole at U+201C-U+201E (“ ” „).
"""

from __future__ import annotations

import hashlib
import json

from . import plano as pv

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


def sha256_esquema(plano: dict) -> str:
    corpo = json.dumps(esquema_do_plano(plano), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()
