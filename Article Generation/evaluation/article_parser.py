"""Load the generated articles and their plans, normalise them and split them into sentences.

Each sentence keeps its [E#] markers, a marker-free copy for the citation judge, and whether it
counts towards Citation Recall.
"""

import json
import re
import unicodedata
from typing import Iterator, List, Optional, Tuple

from . import config
from .segmentacao import frases as _frases

MARCADOR = re.compile(r"\[E(\d+)\]")
RELACAO = {"supported": "support", "refuted": "refute", "nei": "nei"}

# The section type decides which sentences count towards Citation Recall. Titles are matched by
# pattern, lowercased and without accents, because runs without the output grammar write their own.
PADROES_SECCAO = [
    ("limites", re.compile(r"^limit")),
    ("conclusao", re.compile(r"^conclus")),
    ("enquadramento", re.compile(r"^enquadramento")),
    ("verificacao", re.compile(r"^(a )?verifica")),
    # "(A) claim/afirmação/...", "Contexto da claim/afirmação/..." or a bare "Contexto";
    # any other "Contexto ..." title is not the claim section.
    ("claim", re.compile(r"^(a )?(claim|afirmacao|declaracao|alegacao)\b"
                         r"|^contexto( d[aoe]s?)? (claim|afirmacao|declaracao|alegacao|critica)\b|^contexto$")),
]
MAX_BRUTO = 12000                      # characters of raw output kept when there is no parseable JSON

# The Citation Recall denominator follows from the article structure alone, never from a model.
_EXCLUSAO_POR_SECCAO = {"claim": "section_claim", "limites": "section_limits", "conclusao": "section_conclusion"}


def caso_das_evidencias(artigo_normalizado: dict) -> str:
    """Return "no_evidence", "decisive" (at least one supported or refuted unit) or "only_nei"."""
    rel = {e["relation"] for e in artigo_normalizado.get("evidence") or []}
    return "no_evidence" if not rel else "decisive" if rel & {"support", "refute"} else "only_nei"


def caso_do_artigo(artigo_normalizado: dict) -> str:
    """The evidence case, except "unstructured" for an article with evidence but no readable structure."""
    caso = caso_das_evidencias(artigo_normalizado)
    if caso != "no_evidence" and artigo_normalizado.get("parse_warning") == "artigo_sem_json":
        return "unstructured"
    return caso


def razao_de_exclusao(tipo: str, caso: str, fixa: bool, palavras: bool) -> Optional[str]:
    """Why a sentence is left out of the Citation Recall denominator, or None if it counts."""
    if caso == "unstructured":
        return "unstructured_article"
    if tipo in _EXCLUSAO_POR_SECCAO:
        return _EXCLUSAO_POR_SECCAO[tipo]
    if not palavras:
        return "empty"
    if fixa:
        return "fixed_text"
    if tipo == "verificacao" and caso == "only_nei":
        return "only_nei_verification_synthesis"
    return None


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def tipo_da_seccao(titulo: str) -> str:
    t = re.sub(r"\s+", " ", _sem_acentos((titulo or "").strip().lower()))
    for tipo, padrao in PADROES_SECCAO:
        if padrao.search(t):
            return tipo
    return "outra"


# --------------------------------------------------------------------------- segmentation
# Markers placed after the final punctuation ("... ended. [E1] [E2] Then ...") belong to the sentence
# on the left; frases() only splits before whitespace + capital, so it would merge both sentences.
_MARCADOR_DEPOIS_DO_PONTO = re.compile(r"([.!?…][»”)]*(?:\s*\[E\d+\])+)\s+(?=[A-ZÀ-Ý«0-9])")


def segmentar(texto: str) -> List[str]:
    saida = []
    for f in _frases(texto or ""):
        saida += [x for x in _MARCADOR_DEPOIS_DO_PONTO.sub(r"\1\n", f).split("\n") if x.strip()]
    # A segment with only markers or punctuation ("[E1]", ").") is merged into the previous sentence.
    juntas: List[str] = []
    for f in saida:
        if juntas and not re.sub(r"[\W_]+", "", MARCADOR.sub("", f)):
            juntas[-1] = juntas[-1] + " " + f.strip()
        else:
            juntas.append(f.strip())
    return juntas


def limpar_marcadores(frase: str) -> str:
    """The sentence without [E#] markers or the space they leave before punctuation."""
    t = MARCADOR.sub(" ", frase)
    t = re.sub(r"\s+([.,;:!?…»)])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def marcadores(frase: str) -> List[str]:
    """Cited ids in order, repetitions included ("E1", "E4", ...)."""
    return [f"E{n}" for n in MARCADOR.findall(frase)]


def frases_do_artigo(artigo_normalizado: dict) -> List[dict]:
    """One record per sentence of the lead and the sections (the title and headings are never sentences)."""
    art = artigo_normalizado["article"]
    caso = caso_do_artigo(artigo_normalizado)
    fixos = [t for t in (artigo_normalizado.get("limits_text"), artigo_normalizado.get("expected_conclusion")) if t]
    fixos_limpos = [limpar_marcadores(t) for t in fixos]
    blocos = [("lead", art.get("lead") or "")]
    for s in art.get("seccoes") or []:
        if not isinstance(s, dict):
            continue
        for p in s.get("paragrafos") or []:
            blocos.append((tipo_da_seccao(s.get("titulo")), str(p)))
    saida = []
    for tipo, texto in blocos:
        for f in segmentar(texto):
            limpa = limpar_marcadores(f)
            fixa = bool(limpa) and any(limpa in t for t in fixos_limpos)
            palavras = bool(re.sub(r"[\W_]+", "", limpa))
            saida.append({"clean_text": limpa, "markers": marcadores(f),
                          "avaliar_recall": razao_de_exclusao(tipo, caso, fixa, palavras) is None})
    return saida


# --------------------------------------------------------------------------- normalisation
def _evidencias(plano: dict) -> List[dict]:
    evid = [{"id": e["ref"], "relation": RELACAO[g["rotulo"]], "text": e["texto"],
             "date": e.get("data_extenso"), "source_title": e.get("headline")}
            for g in plano.get("grupos", []) for e in g["evidencias"]]
    return sorted(evid, key=lambda e: int(e["id"][1:]))


def _texto(valor) -> str:
    """Flatten any JSON value to text; runs without the grammar may emit lists or objects for strings."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list):
        return " ".join(_texto(v) for v in valor)
    if isinstance(valor, dict):
        return " ".join(_texto(v) for v in valor.values())
    return str(valor)


CHAVES_ARTIGO = ("title", "lead", "seccoes")


def _seccoes(valor) -> List[dict]:
    """Sections as {titulo, paragrafos}; text under unknown section keys is appended to the paragraphs."""
    saida = []
    for s in valor if isinstance(valor, list) else []:
        if not isinstance(s, dict):
            if _texto(s).strip():
                saida.append({"titulo": "", "paragrafos": [_texto(s)]})
            continue
        pars = []
        for k, v in s.items():
            if k == "titulo":
                continue
            for p in (v if isinstance(v, list) else [v]):
                if _texto(p).strip():
                    pars.append(_texto(p))
        saida.append({"titulo": _texto(s.get("titulo")), "paragrafos": pars})
    return saida


def _artigo(registo: dict) -> Tuple[dict, Optional[str]]:
    """The article as the generator wrote it, without dropping content: (article, warning), where the
    warning is "artigo_sem_json" when no structure can be read and None otherwise."""
    res = registo.get("resposta")
    if isinstance(res, dict) and ("lead" in res or "seccoes" in res):
        seccoes = _seccoes(res.get("seccoes"))
        # Unknown top-level keys become trailing sections, titled with the key name.
        for k, v in res.items():
            if k not in CHAVES_ARTIGO and _texto(v).strip():
                seccoes.append({"titulo": k, "paragrafos": [_texto(v)]})
        return {"title": _texto(res.get("title")), "lead": _texto(res.get("lead")), "seccoes": seccoes}, None
    bruto = (registo.get("bruto") or "")[:MAX_BRUTO]
    recuperado = _estrutura_do_bruto(bruto)
    if recuperado:
        return recuperado, None
    # Nothing recoverable: the raw text is still evaluated, as one untitled section (Citation Recall is null).
    return {"title": "", "lead": "", "seccoes": [{"titulo": "", "paragrafos": [bruto]}]}, "artigo_sem_json"


# A JSON string literal; group 1 is its still-escaped content.
_STR = r'"((?:[^"\\]|\\.)*)"'


def _desescapar(t: str) -> str:
    try:
        return json.loads(f'"{t}"')
    except ValueError:
        return t


def _estrutura_do_bruto(bruto: str) -> Optional[dict]:
    """Recover title, lead and sections from broken (e.g. truncated) JSON; None without lead or sections."""
    titulo = re.search(r'"title"\s*:\s*' + _STR, bruto)
    lead = re.search(r'"lead"\s*:\s*' + _STR, bruto)
    seccoes = []
    for m in re.finditer(r'"titulo"\s*:\s*' + _STR + r'\s*,\s*"paragrafos"\s*:\s*\[', bruto):
        corpo = bruto[m.end():]
        fim = re.search(r'\]\s*[,}]', corpo)
        corpo = corpo[:fim.start()] if fim else corpo
        paragrafos = [_desescapar(p) for p in re.findall(_STR, corpo) if p.strip()]
        if paragrafos:
            seccoes.append({"titulo": _desescapar(m.group(1)), "paragrafos": paragrafos})
    if not (lead or seccoes):
        return None
    return {"title": _desescapar(titulo.group(1)) if titulo else "", "lead": _desescapar(lead.group(1)) if lead else "",
            "seccoes": seccoes}


def normalizar(registo: dict, plano: dict, condicao: str, pasta_modelo: str) -> dict:
    sem_gramatica = pasta_modelo.endswith("_sem_gramatica")
    modelo = pasta_modelo[:-len("_sem_gramatica")] if sem_gramatica else pasta_modelo
    artigo, aviso = _artigo(registo)
    span = plano["claim_span_id"]
    return {
        "article_id": f"{condicao}/{pasta_modelo}/{span}",
        "claim_id": span,
        "generator_model": modelo,
        "condition": condicao + ("+sem_gramatica" if sem_gramatica else ""),
        "claim": plano["claim"],
        "claim_date": plano.get("claim_date"),
        "claim_context": plano.get("contexto"),
        "expected_conclusion": plano["conclusao_texto"],
        "limits_text": plano.get("limites_texto"),
        "evidence": _evidencias(plano),
        "article": artigo,
        "parse_warning": aviso,
    }


def carregar_artigos(modelos: Optional[List[str]] = None,
                     condicoes: Optional[List[str]] = None) -> Iterator[dict]:
    """Yield normalised articles in condition, model, span order; filters match the normalised names."""
    if not config.ARTIGOS.exists():
        return
    for condicao_dir in sorted(p for p in config.ARTIGOS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for mod_dir in sorted(p for p in condicao_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            # Hidden files (e.g. macOS "._*" metadata) are not articles.
            for f in sorted(p for p in mod_dir.glob("*.json") if not p.name.startswith(".")):
                plano_f = config.PLANOS / condicao_dir.name / f.name
                if not plano_f.exists():
                    continue
                art = normalizar(json.loads(f.read_text(encoding="utf-8")),
                                 json.loads(plano_f.read_text(encoding="utf-8")),
                                 condicao_dir.name, mod_dir.name)
                if modelos and art["generator_model"] not in modelos:
                    continue
                if condicoes and art["condition"] not in condicoes:
                    continue
                yield art
