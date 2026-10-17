"""The user message: ARTICLE DATA and CONTENT PLAN (`Article Generation/geracao/render.py`).

Neither the classification nor its reason is written in it - the CONCLUSÃO sentence carries the
result - and neither are the verification questions, which only serve to retrieve the evidence.
"""

from __future__ import annotations

from . import plano as pv
from . import veredito as vd

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

TEMPLATE_PLANO = """PLANO DE CONTEÚDO

ESTRUTURA FINAL:
{estrutura}

{partes}"""


def _cabecalho_noticia(noticia: dict) -> list[str]:
    return [f"Notícia publicada em {noticia['data_extenso']}",
            f"Título da notícia: {noticia['headline']}"]


def bloco_evidencias(grupo: dict) -> str:
    """A group, each piece of evidence under the news item it came from: three passages of one
    item are one source, not three. An empty group is «NENHUMA», right under its header."""
    if not grupo["evidencias"]:
        return pv.NENHUMA
    por_ref = {e["ref"]: e for e in grupo["evidencias"]}
    linhas: list[str] = []
    for noticia in grupo["noticias"]:
        linhas.append("")
        linhas.extend(_cabecalho_noticia(noticia))
        for r in noticia["refs"]:
            linhas.extend(["", f"{por_ref[r]['marcador']} {por_ref[r]['texto']}"])
    return "\n".join(linhas)


def partes_do_plano(plano: dict) -> list[tuple]:
    """(header, instructions) of each part of the CONTENT PLAN, in FINAL STRUCTURE order."""
    partes = [(pv.TITULOS_PLANO["lead"], plano["instrucoes_lead"])]
    partes += [(pv.TITULOS_PLANO[s["id"]], s["instrucoes"]) for s in plano["seccoes"]]
    return partes


def valores_do_plano(plano: dict) -> dict:
    grupos = {g["rotulo"]: g for g in plano["grupos"]}
    return {
        "titulo": plano["titulo"],
        "claim": plano["claim"],
        "claim_date": plano["claim_date"],
        "contexto": plano["contexto"] or pv.NENHUMA,
        "evidencias_nei": bloco_evidencias(grupos[vd.NEI]),
        "evidencias_apoiam": bloco_evidencias(grupos[vd.SUPPORTED]),
        "evidencias_contrariam": bloco_evidencias(grupos[vd.REFUTED]),
        "limites": plano["limites_texto"],
        "conclusao": plano["conclusao_texto"],
        "estrutura": "\n".join(f"{i}. {parte}" for i, parte in enumerate(plano["estrutura_final"], 1)),
        "partes": "\n\n".join(cabecalho + "\n" + "\n".join(f"- {linha}" for linha in linhas)
                              for cabecalho, linhas in partes_do_plano(plano)),
    }


def mensagem(plano: dict) -> str:
    """The ARTICLE DATA and the CONTENT PLAN, separated by a blank line. `str.format`, so a
    placeholder missing from the values fails here instead of reaching the model."""
    valores = valores_do_plano(plano)
    return TEMPLATE_DADOS.format(**valores) + "\n\n" + TEMPLATE_PLANO.format(**valores)
