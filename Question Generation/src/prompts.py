"""Task instruction and input/target formatting (claim span + publication date + context).

The same instruction and input structure are used by every model and regime; the prompt
text is the task instrument and stays in European Portuguese.
"""

import re
from typing import List

from io_utils import NAO_FORNECIDO, _PUBDATE_KEYS

# Identifier of this prompt format. The released question-generation adapter records it as
# `prompt_version` in its checkpoint_info.json, and the FACTA-PT inference service checks it.
PROMPT_VERSION = "claim_span_publication_date_context_v5_criterios"

DATA_NAO_FORNECIDA = "Não fornecida."

PREAMBULO = (
    "És um sistema de geração de perguntas para fact-checking.\n"
    "Recebes um claim span, a data de publicação e o respetivo contexto (a frase anterior, "
    "a frase do claim span e a frase seguinte).\n"
    "Gera as perguntas que um fact-checker usaria para procurar a evidência que confirma ou "
    "desmente o facto alegado no claim span.\n"
    "Regras:\n"
    "1. Verifica o facto alegado no claim span, não a opinião nem a intenção de quem o "
    "disse.\n"
    "2. Escreve duas perguntas de níveis diferentes: a primeira geral, sobre o tema do claim "
    "span; a segunda específica, sobre o dado concreto a validar (valores, datas, medidas, "
    "nomes de instituições). Escreve apenas uma se o claim span não permitir duas perguntas "
    "distintas, e acrescenta uma terceira ou quarta só se sobrar outro facto do claim span "
    "por verificar.\n"
    "3. Perguntas neutras: sem termos que induzam a resposta e sem dar como certo que o claim "
    "é verdadeiro ou falso.\n"
    "4. Sem pronomes nem expressões vagas (\"ele\", \"aquilo\", \"esta medida\"): usa os nomes "
    "próprios que aparecem no claim span ou no contexto.\n"
    "5. Inclui a baliza temporal quando o facto depender dela, convertendo o tempo relativo "
    "com a data de publicação; inclui a região quando o facto for local; inclui quem afirma, "
    "tal como aparece no contexto, apenas quando a validade do facto depender da autoridade "
    "dele — não para citar o ato de fala. Não faças perguntas sobre a data de publicação em "
    "si.\n"
    "6. Se o claim span referir um estudo, relatório ou documento, formula a pergunta de modo "
    "a localizar esse documento. Se fizer uma comparação, escreve perguntas que obtenham os "
    "dois termos comparados.\n"
    "7. Não escrevas duas perguntas que digam o mesmo por outras palavras.\n"
    "Responde apenas com as perguntas, uma por linha, sem numeração."
)

INPUT_TEMPLATE = (
    "{preambulo}\n\n"
    "CLAIM SPAN:\n{claim_span}\n\n"
    "DATA DE PUBLICAÇÃO:\n{publication_time}\n\n"
    "CONTEXTO:\n{context}\n\n"
    "PERGUNTAS:\n"
)


# Section headers of the template (plus the few-shot block header). A model that copies the
# template instead of answering emits them; the parser drops a candidate that is only a header.
ETIQUETAS_DO_MOLDE = tuple(re.findall(r"^([A-ZÀ-Þ][A-ZÀ-Þ ]*):", INPUT_TEMPLATE, re.M)) + (
    "Exemplos",)


def get_publication_time(example: dict) -> str:
    """Publication date from the first non-empty date field, else "Não fornecida."."""
    for key in _PUBDATE_KEYS:
        val = example.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return DATA_NAO_FORNECIDA


def build_input(claim_span: str, publication_time: str, context: str) -> str:
    """Source text for claim span + publication date + context."""
    return INPUT_TEMPLATE.format(
        preambulo=PREAMBULO,
        claim_span=(claim_span or "").strip() or NAO_FORNECIDO,
        publication_time=(publication_time or "").strip() or DATA_NAO_FORNECIDA,
        context=(context or "").strip() or NAO_FORNECIDO,
    )


def build_target(questions: List[str]) -> str:
    """Target text: one question per line."""
    return "\n".join(q.strip() for q in questions if q and q.strip())


def _shot_block(shot: dict) -> str:
    return (
        "CLAIM SPAN:\n" + ((shot.get("claim_span") or "").strip() or NAO_FORNECIDO) + "\n\n"
        "DATA DE PUBLICAÇÃO:\n" + get_publication_time(shot) + "\n\n"
        "CONTEXTO:\n" + ((shot.get("context") or "").strip() or NAO_FORNECIDO) + "\n\n"
        "PERGUNTAS:\n" + build_target(shot.get("questions", [])) + "\n"
    )


def build_fewshot_input(example: dict, shots: List[dict]) -> str:
    """Input with k solved demonstrations before the query."""
    if not shots:
        return build_input(example.get("claim_span", ""), get_publication_time(example),
                           example.get("context", ""))
    exemplos = "\n---\n".join(_shot_block(s) for s in shots)
    return (
        PREAMBULO + "\n\n"
        "Exemplos:\n" + exemplos + "\n===\n\n"
        "CLAIM SPAN:\n" + ((example.get("claim_span") or "").strip() or NAO_FORNECIDO) + "\n\n"
        "DATA DE PUBLICAÇÃO:\n" + get_publication_time(example) + "\n\n"
        "CONTEXTO:\n" + ((example.get("context") or "").strip() or NAO_FORNECIDO) + "\n\n"
        "PERGUNTAS:\n"
    )
