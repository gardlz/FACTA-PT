"""JSON Schema of the holistic judge's reply.

`HOLISTIC_OUTPUT_SCHEMA` is sent to Gemini as the response JSON schema and also validates each reply.
The citation judge is an NLI classifier that returns no JSON, so it has no reply schema.
"""

from typing import Any, List

from .metricas import QUALIDADE

_DIMENSAO = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "justification": {"type": "string"},
    },
    "required": ["score", "justification"],
    "additionalProperties": False,
}

# Relevance, Comprehensibility, Evidence Presentation (QRAFT); no overall score, ranking or comparison.
# It is part of every request and of the cache key: any change invalidates the cached replies.
HOLISTIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {d: _DIMENSAO for d in QUALIDADE},
    "required": list(QUALIDADE),
    "additionalProperties": False,
}


def erros(instancia: Any, schema: dict) -> List[str]:
    """Schema violations (empty = valid); needs `jsonschema` and never falls back to a partial check."""
    try:
        import jsonschema
    except ImportError as e:
        raise ImportError("A avaliação precisa do pacote `jsonschema` (pip install jsonschema) para "
                          "validar as respostas dos juízes.") from e
    validador = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.path)) or '(raiz)'}: {e.message}" for e in validador.iter_errors(instancia)]
