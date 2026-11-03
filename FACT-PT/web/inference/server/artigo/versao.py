"""The versions of each piece of the article writer (`v2_campanha2/versao.py`).

Whoever changes the TEXT or the BEHAVIOUR of a piece bumps its version: an article records the
versions it was written with, and an article written under other texts is another experiment.
"""

ARQUITETURA = "editorial_v2"
PROMPT = "prompt_base_editorial_2.6"
REGRAS = "regras_editoriais_2.4"
PLANO = "content_plan_2.7"
GRAMATICA = "gramatica_editorial_2.6"

VERSOES = {
    "arquitetura": ARQUITETURA,
    "prompt_versao": PROMPT,
    "regras_versao": REGRAS,
    "plano_versao": PLANO,
    "gramatica_versao": GRAMATICA,
}
