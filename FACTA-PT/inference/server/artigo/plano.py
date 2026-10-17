"""The content plan of one claim, as in `Article Generation/geracao/plano.py` (condition `full`).

Deterministic, without a model. Deduplication runs before, in `web/app/pipeline/evidencia.py`, and
keeps the longer of two near-duplicates by raw length, where the evaluated run measured it typeset.
"""

from __future__ import annotations

import re

from . import veredito as vd

# An order, not a ranking: the nei passages frame what the reader needs to read the deciding ones.
ORDEM_GRUPOS = (vd.NEI, vd.SUPPORTED, vd.REFUTED)
TITULOS_GRUPO = {
    vd.NEI: "EVIDÊNCIAS RELEVANTES NÃO DECISIVAS (NEI)",
    vd.SUPPORTED: "EVIDÊNCIAS QUE APOIAM A CLAIM",
    vd.REFUTED: "EVIDÊNCIAS QUE CONTRARIAM A CLAIM",
}

S_CLAIM = "claim"
S_ENQUADRAMENTO = "enquadramento"
S_VERIFICACAO = "verificacao"
S_LIMITES = "limites"
S_CONCLUSAO = "conclusao"

TITULOS_SECCAO = {
    S_CLAIM: "A claim",
    S_ENQUADRAMENTO: "Enquadramento factual",
    S_VERIFICACAO: "A verificação",
    S_LIMITES: "Limites da verificação",
    S_CONCLUSAO: "Conclusão",
}

# Paragraph ceilings are set here because the plan tells them to the model: a grammar closing a
# section the model expected to go on leaves evidence uncited. Evidence sections get one
# paragraph per piece of evidence plus one.
MAX_PARAGRAFOS_CLAIM = 3


def tecto_de(ident: str, n_marcadores: int, uma_sintese: bool = False) -> int:
    if ident == S_CLAIM:
        return MAX_PARAGRAFOS_CLAIM
    if uma_sintese:
        return 1
    return max(1, n_marcadores) + 1


def marcador(numero: int) -> str:
    return f"[E{numero}]"


def titulo_artigo(claim: str) -> str:
    return f"Verificação da claim: «{claim}»"


# --------------------------------------------------------------------------- dates
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro")


def por_extenso(data_iso: str) -> str:
    """2025-05-07 -> «7 de maio de 2025»."""
    try:
        ano, mes, dia = (int(x) for x in data_iso.split("-")[:3])
    except (ValueError, AttributeError):
        return data_iso
    return f"{dia} de {MESES[mes - 1]} de {ano}"


def vespera(data_iso: str) -> str:
    """The day before, written out: the last day the retrieval may return news from."""
    from datetime import date, timedelta

    try:
        ano, mes, dia = (int(x) for x in data_iso.split("-")[:3])
    except (ValueError, AttributeError):
        return data_iso
    return por_extenso((date(ano, mes, dia) - timedelta(days=1)).isoformat())


# --------------------------------------------------------------------------- headlines
# Lusa production tags say the item has audio or video, or is a reissue, and not what it says.
# Only tags in parentheses go; parentheses that say something («(CDU)») stay.
_ETIQUETA_DE_PRODUCAO = re.compile(
    r"\s*\((?:[Cc]/[^()]*|ATUALIZADA(?:\s+\d+)?|REPETIÇÃO|CORREÇÃO)\)")
# «Sentence -- Author»: the agency's attribution, with two hyphens.
_ATRIBUICAO = re.compile(r"\s+--\s+")


def limpar_titulo(titulo: str) -> str:
    titulo = _ETIQUETA_DE_PRODUCAO.sub("", titulo or "")
    return _ATRIBUICAO.sub(" - ", titulo).strip()


# --------------------------------------------------------------------------- typography
_INTERCALACAO = re.compile(r"\[([^\[\]\n]*)\]")
# Single quotes around a word or phrase ('rating', ‘núcleo duro’); apostrophes stay (d'água).
_SIMPLES = re.compile(r"(?<!\w)['‘]([^'‘’\n]+?)['’](?!\w)")
# A comma glued between letters («25 de Abril,deputados»): the claim goes into the title, which
# is a const the model cannot correct. Numbers («1,60») are left alone.
_VIRGULA_COLADA = re.compile(r"(?<=[^\d\s]),(?=[^\s\d])")
# A line break inside a passage (it can cross paragraphs) becomes a space.
_QUEBRA = re.compile(r"\s*\n\s*")


def aspas_angulares(texto: str) -> str:
    """Straight, curly and single quotes -> angle quotes; not one word changes. A double quote
    opens after the start, a space or an opening sign and before a letter, and closes otherwise; a
    single quote after a letter closes an open quote (some sources open with " and close with ').
    """
    if not texto:
        return texto or ""
    texto = _SIMPLES.sub(r"«\1»", texto)
    saida, profundidade = [], 0
    for i, c in enumerate(texto):
        anterior = texto[i - 1] if i else ""
        seguinte = texto[i + 1] if i + 1 < len(texto) else ""
        if c in '"“”':
            abre = c == "“" or (c == '"' and (not anterior or anterior.isspace()
                                              or anterior in "«([—–-/")
                                and (seguinte.isalnum() or seguinte in "«(…["))
            saida.append("«" if abre else "»")
            profundidade = profundidade + 1 if abre else max(0, profundidade - 1)
        elif c in "'’" and profundidade and anterior.isalpha() and not seguinte.isalnum():
            saida.append("»")
            profundidade -= 1
        else:
            if c == "«":
                profundidade += 1
            elif c == "»":
                profundidade = max(0, profundidade - 1)
            saida.append(c)
    return "".join(saida)


def tipografia(texto: str) -> str:
    """What the model reads: angle quotes, interpolations in parentheses, plain spaces. The
    grammar bans `"` and keeps `[` for markers, so a passage quoted verbatim must have neither."""
    texto = (texto or "").replace(" ", " ").replace(" ", " ")
    texto = _INTERCALACAO.sub(r"(\1)", aspas_angulares(texto)).replace("(...)", "(…)")
    return _VIRGULA_COLADA.sub(", ", texto)


# --------------------------------------------------------------------------- evidence
def evidencia(passagem: dict) -> dict:
    """One piece of evidence of the plan, from a passage shaped as `PassageIn` in `main.py`."""
    texto = (passagem.get("text") or "").strip()
    data = (passagem.get("published_at") or "")[:10]
    return {
        "id": passagem["id"],
        "doc_id": passagem["doc_id"],
        "relacao": passagem["label"],
        "texto_original": texto,
        "texto": tipografia(_QUEBRA.sub(" ", texto)),
        "headline_original": passagem.get("headline") or "",
        "headline": tipografia(limpar_titulo(passagem.get("headline") or "")),
        "data": data,
        "data_extenso": por_extenso(data),
        "begin": passagem.get("begin"),
        "end": passagem.get("end"),
        "indice_excerto": passagem.get("index", 0),
    }


def _chave_plano(e: dict):
    """Order within a group: news item by date, then news id, then position in the text."""
    return (e["data"], e["doc_id"], e["begin"] if e["begin"] is not None else 10 ** 9,
            e["indice_excerto"])


def _noticias(evidencias: list[dict]) -> list[dict]:
    """The news items of a group, in the order of each one's first piece of evidence."""
    vistas: dict[str, dict] = {}
    for e in evidencias:
        n = vistas.setdefault(e["doc_id"], {"doc_id": e["doc_id"], "headline": e["headline"],
                                            "data": e["data"], "data_extenso": e["data_extenso"],
                                            "refs": []})
        n["refs"].append(e["ref"])
    return list(vistas.values())


def numerar(evidencias: list[dict]) -> list[dict]:
    """Numbers the evidence [E1]..[En] in the order the reader meets it (group, news item,
    position) and returns the groups, NEI -> Supported -> Refuted. No gaps: they would tell the
    model evidence was removed."""
    por_relacao = {r: [e for e in evidencias if e["relacao"] == r] for r in ORDEM_GRUPOS}
    ordem = [e for r in ORDEM_GRUPOS for e in sorted(por_relacao[r], key=_chave_plano)]
    for n, e in enumerate(ordem, 1):
        e["ref"] = f"E{n}"
        e["marcador"] = marcador(n)
    grupos = []
    for rotulo in ORDEM_GRUPOS:
        do_grupo = sorted(por_relacao[rotulo], key=lambda e: int(e["ref"][1:]))
        grupos.append({"rotulo": rotulo, "titulo": TITULOS_GRUPO[rotulo],
                       "evidencias": do_grupo, "noticias": _noticias(do_grupo)})
    return grupos


# --------------------------------------------------------------------------- instructions
# The instruction templates of the CONTENT PLAN. A tuple is (singular, plural), chosen by the
# number of pieces of evidence it names; a plain string does not depend on it.
NENHUMA = "NENHUMA"
ESTRUTURA_LEAD = "Lead"
TITULOS_PLANO = {"lead": "LEAD", S_CLAIM: "A CLAIM", S_ENQUADRAMENTO: "ENQUADRAMENTO FACTUAL",
                 S_VERIFICACAO: "A VERIFICAÇÃO", S_LIMITES: "LIMITES DA VERIFICAÇÃO",
                 S_CONCLUSAO: "CONCLUSÃO"}

TECTO = ("Um único parágrafo.", "No máximo {n} parágrafos.")
TECTO_EXPLICACAO = "No máximo {n} parágrafos, incluindo um eventual parágrafo de explicação."

LEAD_FIXAS = (
    "Escreve duas ou três frases.",
    "Permite ao leitor compreender rapidamente o principal resultado da verificação.",
    "Não repitas integralmente a claim.",
    "Podes antecipar sinteticamente a conclusão, mantendo exatamente o seu sentido e sem "
    "classificar a claim como «verdadeira» ou «falsa».",
)
LEAD_SINTETIZA = ("Sintetiza a evidência {refs}.", "Sintetiza as evidências {refs}.")
LEAD_MARCADORES = ("Sempre que apresentares informação factual proveniente desta evidência, usa o "
                   "marcador correspondente.",
                   "Sempre que apresentares informação factual proveniente destas evidências, usa "
                   "os marcadores correspondentes.")
LEAD_SEM_EVIDENCIA = "Não existem evidências a sintetizar; não uses marcadores [E#]."

CLAIM_FIXAS = (
    "Usa apenas o CONTEXTO DA CLAIM.",
    "Explica claramente o que está a ser verificado e as circunstâncias em que a claim foi "
    "proferida.",
    "Não uses evidências nem marcadores [E#].",
)

USA = ("Usa apenas a evidência {refs}.", "Usa todas e apenas as evidências {refs}.")
MESMA_NOTICIA = "{refs} pertencem à mesma notícia; integra-as de forma coerente sempre que fizer sentido."

ENQ_APRESENTA = ("Apresenta a informação factual que esta evidência permite estabelecer e explica "
                 "por que é relevante para compreender ou verificar a claim.",
                 "Apresenta a informação factual que estas evidências permitem estabelecer e "
                 "explica por que é relevante para compreender ou verificar a claim.")
ENQ_NAO_PROVA = "Não apresentes {refs_ou} como evidência de que a claim é apoiada ou contrariada."
ENQ_FORMULACOES = ("Não uses formulações como «confirma», «comprova», «desmente» ou «contraria a "
                   "claim» para caracterizar esta evidência.",
                   "Não uses formulações como «confirma», «comprova», «desmente» ou «contraria a "
                   "claim» para caracterizar estas evidências.")
ENQ_MARCADOR = "Todos os parágrafos devem conter pelo menos um marcador de evidência."

VER_APOIAM = ("Esta evidência apoia a claim e não existem evidências que a contrariem.",
              "Estas evidências apoiam a claim e não existem evidências que a contrariem.")
VER_CONTRARIAM = ("Esta evidência contraria a claim e não existem evidências que a apoiem.",
                  "Estas evidências contrariam a claim e não existem evidências que a apoiem.")
VER_CONFLITO_APOIAM = ("A evidência {refs} apoia a claim.", "As evidências {refs} apoiam a claim.")
VER_CONFLITO_CONTRARIAM = ("A evidência {refs} contraria a claim.",
                           "As evidências {refs} contrariam a claim.")
VER_CONFLITO_ORDEM = ("Apresenta primeiro {sup} e depois {ref}, com o mesmo cuidado para os dois "
                      "sentidos.")
VER_ORGANIZA = ("Organiza e sintetiza a informação de forma natural.",
                "Organiza e sintetiza a informação de forma natural, evitando apresentar os "
                "excertos como uma simples lista.")
VER_EXPLICA = ("Explica explicitamente como a informação estabelecida pela evidência se relaciona "
               "com a claim.",
               "Explica explicitamente como a informação estabelecida pelas evidências se "
               "relaciona com a claim.")
VER_CONFLITO_EXPLICA = ("Explica que as evidências disponíveis apontam em sentidos diferentes, sem "
                        "escolher um dos lados.")
VER_MARCADORES = ("Todos os parágrafos que apresentem informação factual das evidências devem "
                  "conter os respetivos marcadores.")
# «no fim da secção»: the only place the grammar leaves that paragraph.
VER_UM_SEM_MARCADORES = ("Pode existir no máximo um parágrafo sem marcadores, no fim da secção, "
                         "exclusivamente para explicar a relação global entre a evidência já "
                         "apresentada e a claim, sem introduzir novos factos.")
VER_NAO_REPETIR_NEI = "Não repitas as evidências NEI apresentadas em «Enquadramento factual»."

VER_NAO_DECISIVA = ("Explica, numa síntese curta e sem repetir os excertos, que a informação "
                    "apresentada em «Enquadramento factual» não permite sustentar nem refutar a "
                    "claim.")
VER_SEM_EVIDENCIA = ("Indica apenas que não foram recuperadas evidências relevantes que permitam "
                     "verificar factualmente a claim.")
VER_SEM_EVIDENCIA_EXTERNO = "Não preenchas essa ausência com conhecimento externo."
SEM_MARCADORES = "Não uses marcadores [E#]."

LIMITES_INCLUI = "Inclui exatamente o texto fornecido em LIMITES DA VERIFICAÇÃO."
CONCLUSAO_INCLUI = "Inclui exatamente a frase fornecida em CONCLUSÃO."


def _lista(refs: list[str], conjuncao: str = "e") -> str:
    marcadores = [marcador(int(r[1:])) for r in refs]
    if len(marcadores) == 1:
        return marcadores[0]
    return ", ".join(marcadores[:-1]) + f" {conjuncao} " + marcadores[-1]


def _forma(templates: tuple, n: int) -> str:
    return templates[0] if n == 1 else templates[-1]


def _com(templates: tuple, refs: list[str]) -> str:
    return _forma(templates, len(refs)).format(refs=_lista(refs))


def _tecto(n: int, explicacao: bool = False) -> str:
    if n == 1:
        return TECTO[0]
    return (TECTO_EXPLICACAO if explicacao else TECTO[1]).format(n=n)


def _mesma_noticia(grupo: dict) -> list[str]:
    """One line per news item of the group with more than one piece of evidence."""
    return [MESMA_NOTICIA.format(refs=_lista(n["refs"])) for n in grupo["noticias"]
            if len(n["refs"]) > 1]


def _refs(grupos: list[dict], rotulo: str) -> list[str]:
    return [e["ref"] for g in grupos if g["rotulo"] == rotulo for e in g["evidencias"]]


def _grupo(grupos: list[dict], rotulo: str) -> dict:
    return next(g for g in grupos if g["rotulo"] == rotulo)


def _caso_base(caso: str) -> str:
    return caso[:-4] if caso.endswith("_nei") else caso


def refs_do_lead(grupos: list[dict], caso: str) -> list[str]:
    """What the lead sums up: the deciding evidence; in the non-deciding case, the nei; with no
    evidence, none. They are also the only markers the grammar lets the lead write."""
    if _caso_base(caso) == vd.CASO_NAO_DECISIVA:
        return _refs(grupos, vd.NEI)
    return _refs(grupos, vd.SUPPORTED) + _refs(grupos, vd.REFUTED)


def instrucoes(grupos: list[dict], caso: str) -> dict[str, list[str]]:
    """The instructions of each part of the CONTENT PLAN for this case, one sentence each."""
    base = _caso_base(caso)
    nei, sup, ref = (_refs(grupos, r) for r in (vd.NEI, vd.SUPPORTED, vd.REFUTED))
    decisivas = sup + ref
    uma_sintese = base in (vd.CASO_NAO_DECISIVA, vd.CASO_SEM_EVIDENCIA)

    do_lead = refs_do_lead(grupos, caso)
    lead = list(LEAD_FIXAS)
    if do_lead:
        lead += [_com(LEAD_SINTETIZA, do_lead), _forma(LEAD_MARCADORES, len(do_lead))]
    else:
        lead.append(LEAD_SEM_EVIDENCIA)

    claim = [*CLAIM_FIXAS, _tecto(tecto_de(S_CLAIM, 0))]

    enquadramento = []
    if nei:
        enquadramento = [_com(USA, nei), *_mesma_noticia(_grupo(grupos, vd.NEI)),
                         _forma(ENQ_APRESENTA, len(nei)),
                         ENQ_NAO_PROVA.format(refs_ou=_lista(nei, "ou")),
                         _forma(ENQ_FORMULACOES, len(nei)), ENQ_MARCADOR,
                         _tecto(tecto_de(S_ENQUADRAMENTO, len(nei)))]

    if base == vd.CASO_NAO_DECISIVA:
        verificacao = [VER_NAO_DECISIVA, SEM_MARCADORES]
    elif base == vd.CASO_SEM_EVIDENCIA:
        verificacao = [VER_SEM_EVIDENCIA, VER_SEM_EVIDENCIA_EXTERNO, SEM_MARCADORES]
    else:
        mesma = [linha for r in (vd.SUPPORTED, vd.REFUTED)
                 for linha in _mesma_noticia(_grupo(grupos, r))]
        verificacao = [_com(USA, decisivas), *mesma]
        if base == vd.CASO_CONFLITO:
            verificacao += [_com(VER_CONFLITO_APOIAM, sup), _com(VER_CONFLITO_CONTRARIAM, ref),
                            VER_CONFLITO_ORDEM.format(sup=_lista(sup), ref=_lista(ref)),
                            _forma(VER_ORGANIZA, len(decisivas)), VER_CONFLITO_EXPLICA]
        else:
            relacao = VER_APOIAM if base == vd.CASO_APOIA else VER_CONTRARIAM
            verificacao += [_forma(relacao, len(decisivas)), _forma(VER_ORGANIZA, len(decisivas)),
                            _forma(VER_EXPLICA, len(decisivas))]
        verificacao += [VER_MARCADORES, VER_UM_SEM_MARCADORES]
        if nei:
            verificacao.append(VER_NAO_REPETIR_NEI)
    verificacao.append(_tecto(tecto_de(S_VERIFICACAO, len(decisivas), uma_sintese),
                              explicacao=not uma_sintese))

    return {"lead": lead, S_CLAIM: claim, S_ENQUADRAMENTO: enquadramento,
            S_VERIFICACAO: verificacao, S_LIMITES: [LIMITES_INCLUI, TECTO[0]],
            S_CONCLUSAO: [CONCLUSAO_INCLUI, TECTO[0]]}


# --------------------------------------------------------------------------- sections
def seccoes(grupos: list[dict], classificacao: dict, textos: dict[str, list[str]],
            limites: str) -> list[dict]:
    """The article's sections, in order. «Enquadramento factual» exists only with nei evidence.
    `marcadores` are the markers a section must use; `marcadores_permitidos`, those the grammar
    lets it write."""
    base = _caso_base(classificacao["caso"])
    nei, sup, ref = (_refs(grupos, r) for r in (vd.NEI, vd.SUPPORTED, vd.REFUTED))

    lista = [{"id": S_CLAIM, "titulo": TITULOS_SECCAO[S_CLAIM],
              "instrucoes": textos[S_CLAIM], "marcadores": [], "marcadores_permitidos": [],
              "max_paragrafos": tecto_de(S_CLAIM, 0)}]
    if nei:
        lista.append({"id": S_ENQUADRAMENTO, "titulo": TITULOS_SECCAO[S_ENQUADRAMENTO],
                      "instrucoes": textos[S_ENQUADRAMENTO], "marcadores": nei,
                      "marcadores_permitidos": nei,
                      "max_paragrafos": tecto_de(S_ENQUADRAMENTO, len(nei))})
    # The deciding evidence is compulsory in «A verificação» and the only one it may cite; the
    # summaries (non-deciding, no evidence) cite nothing.
    obrigatorios = sup + ref
    uma_sintese = base in (vd.CASO_NAO_DECISIVA, vd.CASO_SEM_EVIDENCIA)
    lista.append({"id": S_VERIFICACAO, "titulo": TITULOS_SECCAO[S_VERIFICACAO],
                  "instrucoes": textos[S_VERIFICACAO], "marcadores": obrigatorios,
                  "marcadores_permitidos": [] if uma_sintese else obrigatorios,
                  "uma_sintese": uma_sintese,
                  "max_paragrafos": tecto_de(S_VERIFICACAO, len(obrigatorios), uma_sintese)})
    lista.append({"id": S_LIMITES, "titulo": TITULOS_SECCAO[S_LIMITES],
                  "instrucoes": textos[S_LIMITES], "texto_fixo": limites, "marcadores": [],
                  "marcadores_permitidos": []})
    lista.append({"id": S_CONCLUSAO, "titulo": TITULOS_SECCAO[S_CONCLUSAO],
                  "instrucoes": textos[S_CONCLUSAO], "texto_fixo": classificacao["conclusao_texto"],
                  "marcadores": [], "marcadores_permitidos": []})
    return lista


# --------------------------------------------------------------------------- the plan
def construir(claim: str, claim_date: str, contexto: str, passagens: list[dict]) -> dict:
    """The plan of one claim. `claim_date` is ISO; `contexto` is the ±1 sentence window around
    the claim ("" when it cannot be located); `passagens` are the consolidated passages."""
    claim_lida = tipografia(claim)
    data_iso = (claim_date or "")[:10]

    grupos = numerar([evidencia(p) for p in passagens])
    classificacao = vd.do_grupos(grupos)
    limites = vd.limites(vespera(data_iso))
    textos = instrucoes(grupos, classificacao["caso"])

    plano = {
        "titulo": titulo_artigo(claim_lida),
        "claim": claim_lida,
        "claim_original": claim,
        "claim_date": por_extenso(data_iso),
        "claim_date_iso": data_iso,
        # The day before the claim: the date rule the retrieval already applies.
        "data_limite": vespera(data_iso),
        "contexto": tipografia(contexto),
        "contexto_original": contexto,
        **classificacao,
        "grupos": grupos,
        "instrucoes_lead": textos["lead"],
        "lead_marcadores": refs_do_lead(grupos, classificacao["caso"]),
        "seccoes": seccoes(grupos, classificacao, textos, limites),
        "limites_texto": limites,
        "n_evidencias": sum(len(g["evidencias"]) for g in grupos),
        "n_noticias": len({e["doc_id"] for g in grupos for e in g["evidencias"]}),
    }
    plano["estrutura_final"] = [ESTRUTURA_LEAD] + [s["titulo"] for s in plano["seccoes"]]
    return plano


def todas_as_evidencias(plano: dict) -> list[dict]:
    """The plan's evidence in marker order."""
    return sorted((e for g in plano["grupos"] for e in g["evidencias"]),
                  key=lambda e: int(e["ref"][1:]))
