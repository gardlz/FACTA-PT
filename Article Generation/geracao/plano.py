"""Builds the content plan of a claim span, deterministically and without a model.

Steps: 3-sentence evidence windows -> deduplication within each relation -> classification
(`veredito.py`) -> [E1]..[En] numbering -> sections and plan instructions. `render.py` turns the
plan into the user message and `esquema.py` into the output grammar.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent                                            # this stage's folder
SAIDAS = RAIZ / "dados"                                       # plans and articles
sys.path.insert(0, str(AQUI))

import citacoes                                               # noqa: E402
from dedup_excertos import LIMIAR_CONTENCAO, N_GRAMA, desduplicar  # noqa: E402
from janela import sentence_window                            # noqa: E402

import veredito as vd                                         # noqa: E402

# CLEVER, at the root of the repository: clever.json, with the article texts in clean_files/.
DATASET = RAIZ.parent / "CLEVER" / "clever.json"

# --------------------------------------------------------------------------- passages and dates
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro")


def por_extenso(data_iso: str) -> str:
    """ISO date -> Portuguese long form ("2001-02-03" -> "3 de fevereiro de 2001")."""
    try:
        ano, mes, dia = (int(x) for x in data_iso.split("-")[:3])
    except (ValueError, AttributeError):
        return data_iso
    return f"{dia} de {MESES[mes - 1]} de {ano}"


def vespera(data_iso: str) -> str:
    """The day before an ISO date, in long form."""
    from datetime import date, timedelta
    try:
        ano, mes, dia = (int(x) for x in data_iso.split("-")[:3])
    except (ValueError, AttributeError):
        return data_iso
    return por_extenso((date(ano, mes, dia) - timedelta(days=1)).isoformat())


def evidencias_do_documento(doc: dict) -> List[dict]:
    """One entry per annotated passage of the document, with id `<doc_id>-e<n>` and its offsets."""
    spans = doc.get("evidence_excerpt_spans") or []
    saida = []
    for i, texto in enumerate(doc.get("evidence_excerpts") or [], 1):
        offsets = spans[i - 1] if len(spans) >= i else {}
        saida.append({
            "id": f"{doc['doc_id']}-e{i}",
            "texto": texto.strip(),
            "doc_id": doc["doc_id"],
            "headline": doc.get("headline", ""),
            "data": (doc.get("published_at") or "")[:10],
            "relacao": vd.normalizar_relacao(doc["relation"]),
            "begin": offsets.get("begin"),
            "end": offsets.get("end"),
        })
    return saida


# The claim context is the claim span's sentence(s) plus one sentence on each side, the same window
# as in question generation (`janela.py`); never the whole source article.
FRASES_ANTES = 1
FRASES_DEPOIS = 1


def janela_de_contexto(span: dict) -> str:
    """The ±1-sentence context window; raises instead of falling back to the whole article."""
    janela = sentence_window(span["source_article"], span["claim_span"],
                             n_before=FRASES_ANTES, n_after=FRASES_DEPOIS)
    if not janela:
        raise ValueError(f"{span['claim_span_id']}: claim span não localizável no artigo de "
                         "origem; a janela de contexto não pode ser construída")
    return janela

# --------------------------------------------------------------------------- conditions
# The four ablation conditions cross two switches: deduplicate the evidence or not, and give the
# model the content plan or only the article data. Everything else is the same in all four.
CONDICOES = {
    "full": {"dedup": True, "com_plano": True},
    "sem_dedup": {"dedup": False, "com_plano": True},
    "sem_plano": {"dedup": True, "com_plano": False},
    "direct": {"dedup": False, "com_plano": False},
}

# --------------------------------------------------------------------------- fixed names
ROTULO_EXTERNO = {vd.SUPPORTED: "Supported", vd.REFUTED: "Refuted", vd.NEI: "NEI"}

# Evidence group headings, as written in the user message.
TITULOS_GRUPO = {
    vd.NEI: "EVIDÊNCIAS RELEVANTES NÃO DECISIVAS (NEI)",
    vd.SUPPORTED: "EVIDÊNCIAS QUE APOIAM A CLAIM",
    vd.REFUTED: "EVIDÊNCIAS QUE CONTRARIAM A CLAIM",
}
# A fixed order, not a ranking: NEI evidence frames the decisive evidence, so it comes first.
ORDEM_GRUPOS = (vd.NEI, vd.SUPPORTED, vd.REFUTED)

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

# Paragraph caps live in the plan, which states them to the model; the grammar reads them from it.
MAX_PARAGRAFOS_CLAIM = 3


def tecto_de(ident: str, n_marcadores: int, uma_sintese: bool = False) -> int:
    """Max paragraphs of a free-text section: one per evidence item plus one, or 1 for a summary."""
    if ident == S_CLAIM:
        return MAX_PARAGRAFOS_CLAIM
    if uma_sintese:
        return 1
    return max(1, n_marcadores) + 1


def titulo_artigo(claim: str) -> str:
    return f"Verificação da claim: «{claim}»"


# --------------------------------------------------------------------------- news headlines
# Lusa production tags in parentheses: "(C/...)" (with audio, video or photo), "(ATUALIZADA [n])",
# "(REPETIÇÃO)", "(CORREÇÃO)". They say how a story was distributed, not what it says.
_ETIQUETA_DE_PRODUCAO = re.compile(
    r"\s*\((?:[Cc]/[^()]*|ATUALIZADA(?:\s+\d+)?|REPETIÇÃO|CORREÇÃO)\)")
# Lusa attribution with a double hyphen: "Statement -- Speaker".
_ATRIBUICAO = re.compile(r"\s+--\s+")


def limpar_titulo(titulo: str) -> str:
    """Headline as the model reads it: production tags removed and " -- " replaced by " - "."""
    titulo = _ETIQUETA_DE_PRODUCAO.sub("", titulo or "")
    return _ATRIBUICAO.sub(" - ", titulo).strip()


# --------------------------------------------------------------------------- typography
_INTERCALACAO = re.compile(r"\[([^\[\]\n]*)\]")
# Single quotes around a word or phrase; the lookarounds leave apostrophes inside words alone.
_SIMPLES = re.compile(r"(?<!\w)['‘]([^'‘’\n]+?)['’](?!\w)")
# A comma glued to the next word ("um,dois") gets a space; decimal commas ("1,5") are left alone.
# The claim becomes the article title, a grammar constant, so the model could not fix it there.
_VIRGULA_COLADA = re.compile(r"(?<=[^\d\s]),(?=[^\s\d])")


def aspas_angulares(texto: str) -> str:
    """Straight, curly and single quotes -> angle quotes («»), without changing any word."""
    if not texto:
        return texto or ""
    texto = _SIMPLES.sub(r"«\1»", texto)
    saida, profundidade = [], 0
    for i, c in enumerate(texto):
        anterior = texto[i - 1] if i else ""
        seguinte = texto[i + 1] if i + 1 < len(texto) else ""
        if c in '"“”':
            # A straight quote opens or closes depending on its neighbours, not on pairing, so
            # nested quotations keep their direction. "[" counts as an opening sign because
            # brackets only become parentheses later, in `tipografia`.
            abre = c == "“" or (c == '"' and (not anterior or anterior.isspace()
                                              or anterior in "«([\u2014\u2013-/")
                                and (seguinte.isalnum() or seguinte in "«(…["))
            saida.append("«" if abre else "»")
            profundidade = profundidade + 1 if abre else max(0, profundidade - 1)
        elif c in "'’" and profundidade and anterior.isalpha() and not seguinte.isalnum():
            saida.append("»")                   # some sources close a quotation with '
            profundidade -= 1
        else:
            if c == "«":
                profundidade += 1
            elif c == "»":
                profundidade = max(0, profundidade - 1)
            saida.append(c)
    return "".join(saida)


def tipografia(texto: str) -> str:
    """The text as the model reads it: typography only, no word is changed."""
    # No-break spaces become plain spaces (for a BPE tokenizer, a rare byte glued to the next word).
    texto = (texto or "").replace("\u00a0", " ").replace("\u202f", " ")
    # Brackets become parentheses: in the output grammar "[" can only open a citation marker.
    texto = _INTERCALACAO.sub(r"(\1)", aspas_angulares(texto)).replace("(...)", "(…)")
    return _VIRGULA_COLADA.sub(", ", texto)


# --------------------------------------------------------------------------- 3-sentence windows
# Each evidence item is a 3-sentence window around an annotated excerpt (dissertation, Section
# 6.2.3). An excerpt longer than three sentences, which CLEVER does not have, would get several
# windows overlapping by SOBREPOSICAO sentences. Two excerpts in the same place give identical
# windows; only deduplication removes the copy.
FRASES_POR_EXCERTO = 3
SOBREPOSICAO = 1
# Sentence splitter of the evidence passages (no abbreviation guard). The claim context uses the
# question-generation splitter instead (`janela.sentence_window`).
_FIM_DE_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý«\"])")
# A window can cross paragraphs; line breaks become spaces so each evidence item is one paragraph.
_QUEBRA = re.compile(r"\s*\n\s*")


def frases_da_noticia(texto: str) -> List[Tuple[int, int]]:
    """(start, end) character offsets of each sentence of an article."""
    spans, inicio = [], 0
    for m in _FIM_DE_FRASE.finditer(texto):
        if m.start() > inicio:
            spans.append((inicio, m.start()))
            inicio = m.end()
    if inicio < len(texto):
        spans.append((inicio, len(texto)))
    return [(a, b) for a, b in spans if texto[a:b].strip()]


def janelas_do_excerto(n_frases: int, primeira: int, ultima: int) -> List[Tuple[int, int]]:
    """(first, last) sentence of each window for the excerpt at sentences `primeira`..`ultima`."""
    k = ultima - primeira + 1
    if k <= FRASES_POR_EXCERTO:
        # 1 or 2 sentences: the window starts one sentence before the excerpt
        inicios = [primeira - 1 if k < FRASES_POR_EXCERTO else primeira]
    else:
        inicios, passo = [primeira], FRASES_POR_EXCERTO - SOBREPOSICAO
        while inicios[-1] + FRASES_POR_EXCERTO - 1 < ultima:
            inicios.append(inicios[-1] + passo)
    saida = []
    for inicio in inicios:
        inicio = max(0, min(inicio, n_frases - FRASES_POR_EXCERTO))   # slide inward at the edges
        saida.append((inicio, min(n_frases, inicio + FRASES_POR_EXCERTO) - 1))
    return saida


def janelas_do_documento(doc: dict) -> List[dict]:
    """Windows of a relevant article, one per annotated excerpt (and part), in sentence order."""
    texto = doc.get("content") or ""
    frases = frases_da_noticia(texto)
    janelas: List[dict] = []
    for e in evidencias_do_documento(doc):
        if e["begin"] is None or texto[e["begin"]:e["end"]].strip() != e["texto"]:
            raise ValueError(f"{e['id']}: o excerto anotado não está no texto nos seus offsets")
        toca = [i for i, (a, b) in enumerate(frases) if a < e["end"] and b > e["begin"]]
        for parte, (lo, hi) in enumerate(janelas_do_excerto(len(frases), toca[0], toca[-1]), 1):
            janelas.append({"frases": (lo, hi), "begin": frases[lo][0], "end": frases[hi][1],
                            "excerto": {"id": e["id"], "texto": e["texto"], "begin": e["begin"],
                                        "end": e["end"], "parte": parte}})
    return sorted(janelas, key=lambda j: j["frases"])             # stable: ties keep excerpt order


# --------------------------------------------------------------------------- evidence
def evidencias_do_span(span: dict) -> List[dict]:
    """One evidence item per window of the span's relevant documents, in dataset order."""
    saida = []
    for posicao, doc in enumerate(span["candidate_documents"]):
        if not doc.get("relevant"):
            continue
        base = evidencias_do_documento(doc)[0]
        vistas: Dict[Tuple[int, int], int] = {}
        for indice, j in enumerate(janelas_do_documento(doc), 1):
            texto = doc["content"][j["begin"]:j["end"]].strip()
            # the same sentences again (another excerpt there): number the repeat in the id
            vistas[j["frases"]] = vistas.get(j["frases"], 0) + 1
            repeticao = f"-{vistas[j['frases']]}" if vistas[j["frases"]] > 1 else ""
            saida.append({
                "id": f"{doc['doc_id']}-f{j['frases'][0] + 1}-{j['frases'][1] + 1}{repeticao}",
                "doc_id": doc["doc_id"],
                "relacao": base["relacao"],
                "texto_original": texto,
                "texto": tipografia(_QUEBRA.sub(" ", texto)),
                "headline_original": base["headline"],
                "headline": tipografia(limpar_titulo(base["headline"])),
                "data": base["data"],
                "data_extenso": por_extenso(base["data"]),
                "begin": j["begin"],
                "end": j["end"],
                "frases": [j["frases"][0] + 1, j["frases"][1] + 1],
                "excertos_anotados": [j["excerto"]],
                "indice_excerto": indice,
                "posicao_documento": posicao,
            })
    return saida


def preparar(evidencias: List[dict], dedup: bool) -> Tuple[Dict[str, List[dict]], List[dict]]:
    """Group the evidence by relation, deduplicating within each group: (groups, removed)."""
    por_relacao = {r: [e for e in evidencias if e["relacao"] == r] for r in ORDEM_GRUPOS}
    removidas = []
    for rotulo in ORDEM_GRUPOS:
        mantidas = por_relacao[rotulo]
        if dedup:
            mantidas, fora = desduplicar(mantidas)
            removidas.extend({**f, "relacao": rotulo} for f in fora)
        por_relacao[rotulo] = mantidas
    return por_relacao, removidas


def _chave_plano(e: dict):
    """Order within a group: article date, article id, then position in the article."""
    return (e["data"], e["doc_id"], e["begin"] if e["begin"] is not None else 10 ** 9,
            e["indice_excerto"])


def _noticias(evidencias: List[dict]) -> List[dict]:
    """The articles of a group, in order of their first evidence item, each with its refs."""
    vistas: Dict[str, dict] = {}
    for e in evidencias:
        n = vistas.setdefault(e["doc_id"], {"doc_id": e["doc_id"], "headline": e["headline"],
                                            "data": e["data"], "data_extenso": e["data_extenso"],
                                            "refs": []})
        n["refs"].append(e["ref"])
    return list(vistas.values())


def numerar(por_relacao: Dict[str, List[dict]]) -> List[dict]:
    """Number the evidence [E1]..[En] in the order the message lists it, and return the groups."""
    ordem = [e for r in ORDEM_GRUPOS for e in sorted(por_relacao[r], key=_chave_plano)]
    for n, e in enumerate(ordem, 1):
        e["ref"] = f"E{n}"
        e["marcador"] = citacoes.formatar(n)
    grupos = []
    for rotulo in ORDEM_GRUPOS:
        do_grupo = sorted(por_relacao[rotulo], key=lambda e: int(e["ref"][1:]))
        grupos.append({"rotulo": rotulo, "rotulo_externo": ROTULO_EXTERNO[rotulo],
                       "titulo": TITULOS_GRUPO[rotulo], "evidencias": do_grupo,
                       "noticias": _noticias(do_grupo)})
    return grupos


# --------------------------------------------------------------------------- plan instructions
# Templates of the PLANO DE CONTEÚDO. A template is a (singular, plural) pair chosen by the number of
# evidence items, or a single sentence.
NENHUMA = "NENHUMA"
ESTRUTURA_LEAD = "Lead"
TITULOS_PLANO = {"lead": "LEAD", S_CLAIM: "A CLAIM", S_ENQUADRAMENTO: "ENQUADRAMENTO FACTUAL",
                 S_VERIFICACAO: "A VERIFICAÇÃO", S_LIMITES: "LIMITES DA VERIFICAÇÃO",
                 S_CONCLUSAO: "CONCLUSÃO"}

# Paragraph cap: the last line of each part.
TECTO = ("Um único parágrafo.", "No máximo {n} parágrafos.")
TECTO_EXPLICACAO = "No máximo {n} parágrafos, incluindo um eventual parágrafo de explicação."

# LEAD
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

# A CLAIM (the claim section)
CLAIM_FIXAS = (
    "Usa apenas o CONTEXTO DA CLAIM.",
    "Explica claramente o que está a ser verificado e as circunstâncias em que a claim foi "
    "proferida.",
    "Não uses evidências nem marcadores [E#].",
)

# Evidence used by a part, and evidence from the same article (framing and verification)
USA = ("Usa apenas a evidência {refs}.", "Usa todas e apenas as evidências {refs}.")
MESMA_NOTICIA = "{refs} pertencem à mesma notícia; integra-as de forma coerente sempre que fizer sentido."

# ENQUADRAMENTO FACTUAL (factual framing)
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

# A VERIFICAÇÃO (verification) with decisive evidence
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
# "no fim da secção": the grammar only allows the paragraph without markers at the end.
VER_UM_SEM_MARCADORES = ("Pode existir no máximo um parágrafo sem marcadores, no fim da secção, "
                         "exclusivamente para explicar a relação global entre a evidência já "
                         "apresentada e a claim, sem introduzir novos factos.")
VER_NAO_REPETIR_NEI = "Não repitas as evidências NEI apresentadas em «Enquadramento factual»."

# A VERIFICAÇÃO without decisive evidence: one paragraph, no markers
VER_NAO_DECISIVA = ("Explica, numa síntese curta e sem repetir os excertos, que a informação "
                    "apresentada em «Enquadramento factual» não permite sustentar nem refutar a "
                    "claim.")
VER_SEM_EVIDENCIA = ("Indica apenas que não foram recuperadas evidências relevantes que permitam "
                     "verificar factualmente a claim.")
VER_SEM_EVIDENCIA_EXTERNO = "Não preenchas essa ausência com conhecimento externo."
SEM_MARCADORES = "Não uses marcadores [E#]."

# LIMITES DA VERIFICAÇÃO and CONCLUSÃO: their fixed texts are given in the DADOS DO ARTIGO
LIMITES_INCLUI = "Inclui exatamente o texto fornecido em LIMITES DA VERIFICAÇÃO."
CONCLUSAO_INCLUI = "Inclui exatamente a frase fornecida em CONCLUSÃO."


def _lista(refs: List[str], conjuncao: str = "e") -> str:
    marcadores = [citacoes.formatar(int(r[1:])) for r in refs]
    if len(marcadores) == 1:
        return marcadores[0]
    return ", ".join(marcadores[:-1]) + f" {conjuncao} " + marcadores[-1]


def _forma(templates: tuple, n: int) -> str:
    return templates[0] if n == 1 else templates[-1]


def _com(templates: tuple, refs: List[str]) -> str:
    """The template in the singular or plural for `refs`, filled with their markers."""
    return _forma(templates, len(refs)).format(refs=_lista(refs))


def _tecto(n: int, explicacao: bool = False) -> str:
    """The paragraph-cap line; with `explicacao`, the cap counts an explanation paragraph."""
    if n == 1:
        return TECTO[0]
    return (TECTO_EXPLICACAO if explicacao else TECTO[1]).format(n=n)


def _mesma_noticia(grupo: dict) -> List[str]:
    """One "same article" line for each article of the group with more than one evidence item."""
    return [MESMA_NOTICIA.format(refs=_lista(n["refs"])) for n in grupo["noticias"]
            if len(n["refs"]) > 1]


def _refs(grupos: List[dict], rotulo: str) -> List[str]:
    return [e["ref"] for g in grupos if g["rotulo"] == rotulo for e in g["evidencias"]]


def _grupo(grupos: List[dict], rotulo: str) -> dict:
    return next(g for g in grupos if g["rotulo"] == rotulo)


def _caso_base(caso: str) -> str:
    return caso[:-4] if caso.endswith("_nei") else caso


def refs_do_lead(grupos: List[dict], caso: str) -> List[str]:
    """Refs the lead summarises and may cite: the decisive ones, else the NEI ones."""
    if _caso_base(caso) == vd.CASO_NAO_DECISIVA:
        return _refs(grupos, vd.NEI)
    return _refs(grupos, vd.SUPPORTED) + _refs(grupos, vd.REFUTED)


def instrucoes(grupos: List[dict], caso: str) -> Dict[str, List[str]]:
    """The PLANO DE CONTEÚDO instructions for this case: a list of sentences per part."""
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
        mesma = [linha for r in (vd.SUPPORTED, vd.REFUTED) for linha in _mesma_noticia(_grupo(grupos, r))]
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


def estrutura_final(seccoes_do_plano: List[dict]) -> List[str]:
    """The ESTRUTURA FINAL: the lead, then the section titles in order."""
    return [ESTRUTURA_LEAD] + [s["titulo"] for s in seccoes_do_plano]


# --------------------------------------------------------------------------- sections
def seccoes(grupos: List[dict], classificacao: dict, textos: Dict[str, List[str]],
            limites: str) -> List[dict]:
    """The article's sections in order; `marcadores` must be cited, `marcadores_permitidos` may be."""
    caso = classificacao["caso"]
    base = _caso_base(caso)
    nei, sup, ref = (_refs(grupos, r) for r in (vd.NEI, vd.SUPPORTED, vd.REFUTED))

    lista = [{"id": S_CLAIM, "titulo": TITULOS_SECCAO[S_CLAIM],
              "instrucoes": textos[S_CLAIM], "marcadores": [], "marcadores_permitidos": [],
              "max_paragrafos": tecto_de(S_CLAIM, 0)}]
    if nei:
        lista.append({"id": S_ENQUADRAMENTO, "titulo": TITULOS_SECCAO[S_ENQUADRAMENTO],
                      "instrucoes": textos[S_ENQUADRAMENTO], "marcadores": nei,
                      "marcadores_permitidos": nei,
                      "max_paragrafos": tecto_de(S_ENQUADRAMENTO, len(nei))})
    # The verification may cite only the decisive evidence (the plan tells the model not to repeat
    # the NEI evidence there); a summary-only verification cites nothing.
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
def construir(span: dict, condicao: str = "full") -> dict:
    """The plan of one claim span under `condicao`."""
    if condicao not in CONDICOES:
        raise ValueError(f"condição desconhecida: {condicao!r}; há {sorted(CONDICOES)}")
    cfg = CONDICOES[condicao]
    claim = tipografia(span["claim_span"])

    evidencias = evidencias_do_span(span)
    por_relacao, removidas = preparar(evidencias, cfg["dedup"])
    grupos = numerar(por_relacao)
    classificacao = vd.do_grupos(grupos)

    data_iso = span["publication_time"][:10]
    limites = vd.limites(vespera(data_iso))
    contexto = janela_de_contexto(span)
    contexto_lido = tipografia(contexto)
    textos = instrucoes(grupos, classificacao["caso"])

    plano = {
        "condicao": condicao,
        "parametros_evidencia": {
            "dedup": cfg["dedup"], "dedup_limiar_contencao": LIMIAR_CONTENCAO,
            "dedup_n_grama": N_GRAMA, "com_plano": cfg["com_plano"],
            "frases_por_excerto": FRASES_POR_EXCERTO,
            "sobreposicao": SOBREPOSICAO,
        },
        "claim_span_id": span["claim_span_id"],
        "claim_id": span["claim_id"],
        "source_document": span["source_document"],
        "titulo": titulo_artigo(claim),
        "claim": claim,
        "claim_original": span["claim_span"],
        "claim_date": por_extenso(data_iso),
        "claim_date_iso": data_iso,
        # Evidence cut-off: the day before the claim was published, the same rule as retrieval.
        "data_limite": vespera(data_iso),
        "contexto": contexto_lido,
        "contexto_original": contexto,
        **classificacao,
        "enquadramento_incluido": bool(_refs(grupos, vd.NEI)),
        "grupos": grupos,
        "instrucoes_lead": textos["lead"],
        "lead_marcadores": refs_do_lead(grupos, classificacao["caso"]),
        "seccoes": seccoes(grupos, classificacao, textos, limites),
        "limites_texto": limites,
        "n_evidencias": sum(len(g["evidencias"]) for g in grupos),
        "n_noticias": len({e["doc_id"] for g in grupos for e in g["evidencias"]}),
        "evidencias_removidas": {"deduplicacao": removidas},
    }
    plano["estrutura_final"] = estrutura_final(plano["seccoes"])
    return plano


MESES_CLEVER = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
                "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
# A CLEVER date without a year is from 2025, the year of the elections the corpus covers.
ANO_CLEVER = 2025


def data_clever(texto: str) -> str:
    """CLEVER publication date ('05 mai 2025', '12 mai', '08 mai (2025)') -> ISO."""
    m = re.fullmatch(r"(\d{1,2})\s+([a-zç]{3,})\.?\s*(?:\(?(\d{4})\)?)?", texto.strip().lower())
    if not m or m.group(2)[:3] not in MESES_CLEVER:
        raise ValueError(f"data do CLEVER ilegível: {texto!r}")
    ano = int(m.group(3)) if m.group(3) else ANO_CLEVER
    return f"{ano:04d}-{MESES_CLEVER[m.group(2)[:3]]:02d}-{int(m.group(1)):02d}"


def carregar_dataset(caminho: Path = DATASET) -> List[dict]:
    """The CLEVER claim spans with their annotated retrieved documents, sorted by claim span id.

    The claim span id is the item id, or `<item id>_s<i>` for multi-span items; the source
    article is read from clean_files/, next to clever.json.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise SystemExit(f"o CLEVER não existe: {caminho} (fica na raiz do repositório; ver o README)")
    spans = []
    for artigo in json.loads(caminho.read_text(encoding="utf-8")):
        texto = (caminho.parent / "clean_files" / artigo["document"]).read_text(encoding="utf-8")
        for item in artigo["items"]:
            if not item.get("claim"):
                continue
            lista = item["claim_span"] if isinstance(item["claim_span"], list) else [item["claim_span"]]
            for i, span in enumerate(lista):
                spans.append({
                    "claim_span_id": item["id"] if len(lista) == 1 else f"{item['id']}_s{i}",
                    "claim_id": item["id"],
                    "claim_span": span["text"],
                    "source_document": artigo["document"],
                    "source_article": texto,
                    "publication_time": data_clever(artigo["publication_time"]),
                    "candidate_documents": [{
                        "doc_id": doc["lusa_doc_id"],  # the LUSA id names the evidence
                        "headline": doc["headline"],
                        "published_at": doc["published_at"],
                        "content": doc["content"],
                        "relevant": doc["relevant"],
                        "relation": doc["relation"] or "NEI",
                        "evidence_excerpts": [e["text"] for e in doc["evidence_excerpts"]],
                        "evidence_excerpt_spans": [{"begin": e["begin"], "end": e["end"]}
                                                   for e in doc["evidence_excerpts"]],
                    } for doc in span["retrieved_documents"]],
                })
    return sorted(spans, key=lambda s: s["claim_span_id"])
