"""The question generation prompt the model was trained on (`Question Generation/src/prompts.py`).

`PROMPT_VERSION` must match the adapter's `checkpoint_info.json`; the model refuses to load
otherwise.
"""

PROMPT_VERSION = "claim_span_publication_date_context_v5_criterios"

NAO_FORNECIDO = "Não fornecido."
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


def build_question_input(claim_span: str, publication_time: str, context: str) -> str:
    return INPUT_TEMPLATE.format(
        preambulo=PREAMBULO,
        claim_span=(claim_span or "").strip() or NAO_FORNECIDO,
        publication_time=(publication_time or "").strip() or DATA_NAO_FORNECIDA,
        context=(context or "").strip() or NAO_FORNECIDO,
    )

