"""Renders a plan into the user message the model reads.

The message is the article data (DADOS DO ARTIGO) in every condition, followed by the content plan
(PLANO DE CONTEÚDO) only in the conditions with a plan.
"""

from typing import List

import plano as pv
import veredito as vd

NENHUMA = pv.NENHUMA

# DADOS DO ARTIGO. The {placeholders} are filled by `valores_do_plano`; the rest is fixed text.
TEMPLATE_DADOS = """DADOS DO ARTIGO

TÍTULO DO ARTIGO:
{titulo}

CLAIM:
{claim}

DATA DA CLAIM:
{claim_date}

CONTEXTO DA CLAIM:
{contexto}

EVIDÊNCIAS RELEVANTES NÃO DECISIVAS (NEI):
{evidencias_nei}

EVIDÊNCIAS QUE APOIAM A CLAIM:
{evidencias_apoiam}

EVIDÊNCIAS QUE CONTRARIAM A CLAIM:
{evidencias_contrariam}

LIMITES DA VERIFICAÇÃO:
{limites}

CONCLUSÃO:
{conclusao}"""

# PLANO DE CONTEÚDO: the numbered parts (ESTRUTURA FINAL), then each part's heading
# (`plano.TITULOS_PLANO`) with its instructions, one "- " line each.
TEMPLATE_PLANO = """PLANO DE CONTEÚDO

ESTRUTURA FINAL:
{estrutura}

{partes}"""


def _cabecalho_noticia(noticia: dict) -> List[str]:
    return [f"Notícia publicada em {noticia['data_extenso']}",
            f"Título da notícia: {noticia['headline']}"]


def bloco_evidencias(grupo: dict) -> str:
    """One evidence group with its passages under their news items; NENHUMA if empty."""
    if not grupo["evidencias"]:
        return NENHUMA
    por_ref = {e["ref"]: e for e in grupo["evidencias"]}
    linhas: List[str] = []
    for noticia in grupo["noticias"]:
        linhas.append("")          # before every news item, so the block also starts blank
        linhas.extend(_cabecalho_noticia(noticia))
        for r in noticia["refs"]:
            linhas.extend(["", f"{por_ref[r]['marcador']} {por_ref[r]['texto']}"])
    return "\n".join(linhas)


def partes_do_plano(plano: dict) -> List[tuple]:
    """(heading, instructions) of each part of the content plan, in ESTRUTURA FINAL order."""
    partes = [(pv.TITULOS_PLANO["lead"], plano["instrucoes_lead"])]
    partes += [(pv.TITULOS_PLANO[s["id"]], s["instrucoes"]) for s in plano["seccoes"]]
    return partes


def valores_do_plano(plano: dict) -> dict:
    """Value of each placeholder of the two templates for this plan."""
    grupos = {g["rotulo"]: g for g in plano["grupos"]}
    return {
        "titulo": plano["titulo"],
        "claim": plano["claim"],
        "claim_date": plano["claim_date"],
        "contexto": plano["contexto"] or NENHUMA,
        "evidencias_nei": bloco_evidencias(grupos[vd.NEI]),
        "evidencias_apoiam": bloco_evidencias(grupos[vd.SUPPORTED]),
        "evidencias_contrariam": bloco_evidencias(grupos[vd.REFUTED]),
        "limites": plano["limites_texto"],
        "conclusao": plano["conclusao_texto"],
        "estrutura": "\n".join(f"{i}. {parte}" for i, parte in enumerate(plano["estrutura_final"], 1)),
        "partes": "\n\n".join(cabecalho + "\n" + "\n".join(f"- {linha}" for linha in linhas)
                              for cabecalho, linhas in partes_do_plano(plano)),
    }


def _preencher(template: str, valores: dict) -> str:
    # str.format rather than manual replacement: a missing placeholder raises KeyError here
    # instead of leaving "{...}" in the prompt.
    return template.format(**valores)


def dados_do_artigo(plano: dict) -> str:
    return _preencher(TEMPLATE_DADOS, valores_do_plano(plano))


def plano_de_conteudo(plano: dict) -> str:
    return _preencher(TEMPLATE_PLANO, valores_do_plano(plano))


def mensagem(plano: dict) -> str:
    """The user message: the article data, plus the content plan when the condition has one."""
    if plano["parametros_evidencia"]["com_plano"]:
        return dados_do_artigo(plano) + "\n\n" + plano_de_conteudo(plano)
    return dados_do_artigo(plano)
