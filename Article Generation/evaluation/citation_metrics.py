"""Citation Recall, Citation Precision and Evidence Coverage.

Adapted from ALCE (Gao et al., 2023) and CLEF CheckThat! 2026 Task 3. The only model decision is entailment
(citation_judge); the rest is deterministic. A metric that cannot be computed is null, never 0.
"""

from typing import Dict, List, Optional, Tuple

from . import article_parser as ap
from .metricas import GROUNDING

SEPARADOR_PREMISSA = "\n\n"


def texto_da_evidencia(e: dict) -> str:
    """Premise text of one evidence unit: publication date (if any) and exact passage, no title or [E#]."""
    return f"Notícia publicada em {e['date']}: {e['text']}" if e.get("date") else e["text"]


def _premissa(ids: List[str], textos: Dict[str, str]) -> str:
    return SEPARADOR_PREMISSA.join(textos[i] for i in ids)


def _planear(artigo: dict) -> dict:
    textos = {e["id"]: texto_da_evidencia(e) for e in artigo["evidence"]}
    frases = ap.frases_do_artigo(artigo)
    for f in frases:
        distintos = list(dict.fromkeys(f["markers"]))                     # deduplicated, in citation order
        f["cited_valid"] = [i for i in distintos if i in textos]
        f["cited_invalid"] = [i for i in distintos if i not in textos]
    return {"artigo": artigo, "textos": textos, "frases": frases, "caso": ap.caso_do_artigo(artigo)}


def avaliar(artigos: List[dict], juiz) -> Dict[str, dict]:
    """Metrics per article; every article has input evidence (`evaluate_articles` leaves the others out)."""
    planos = [_planear(a) for a in artigos]

    def pedir(pedidos):
        return juiz.decidir([(_premissa(ids, p["textos"]), f["clean_text"]) for p, f, ids, _ in pedidos])

    # 1. joint support of the valid citations (with a single one, this is its individual decision)
    pedidos = [(p, f, f["cited_valid"], None) for p in planos for f in p["frases"] if f["cited_valid"]]
    for (p, f, ids, _), d in zip(pedidos, pedir(pedidos)):
        f["joint"] = d
    # 2. each Ei alone, in sentences with 2+ valid citations and joint support
    pedidos = [(p, f, [i], i) for p in planos for f in p["frases"]
               if len(f["cited_valid"]) > 1 and f["joint"]["support"] == 1 for i in f["cited_valid"]]
    for (p, f, ids, i), d in zip(pedidos, pedir(pedidos)):
        f.setdefault("single", {})[i] = d
    # 3. leave-one-out: the other citations without Ei, for each Ei that does not support alone
    pedidos = [(p, f, [j for j in f["cited_valid"] if j != i], i) for p in planos for f in p["frases"]
               for i, d in (f.get("single") or {}).items() if d["support"] == 0]
    for (p, f, ids, i), d in zip(pedidos, pedir(pedidos)):
        f.setdefault("loo", {})[i] = d

    return {p["artigo"]["article_id"]: calcular(p) for p in planos}


def correcao_das_citacoes(f: dict) -> Dict[str, Tuple[Optional[int], str]]:
    """Each distinct citation in the sentence -> (1 | 0 | None if unresolved, reason)."""
    saida: Dict[str, Tuple[Optional[int], str]] = {i: (0, "invalid") for i in f["cited_invalid"]}
    validos = f["cited_valid"]
    if not validos:
        return saida
    joint = f["joint"]
    if joint["status"] == "overlength":
        return {**saida, **{i: (None, "overlength") for i in validos}}
    if len(validos) == 1:
        saida[validos[0]] = (joint["support"], "supports" if joint["support"] else "does_not_support")
        return saida
    if joint["support"] == 0:
        return {**saida, **{i: (0, "no_joint_support") for i in validos}}
    for i in validos:
        s = f["single"][i]
        if s["status"] == "overlength":
            saida[i] = (None, "overlength")
        elif s["support"] == 1:
            saida[i] = (1, "supports_alone")
        else:
            loo = f["loo"][i]
            if loo["status"] == "overlength":
                saida[i] = (None, "overlength")
            elif loo["support"] == 1:
                saida[i] = (0, "unnecessary")                  # the others support the sentence without it
            else:
                saida[i] = (1, "necessary")                    # without it, the joint support is lost
    return saida


def suporte_da_frase(f: dict) -> Tuple[Optional[int], str]:
    """A recall-eligible sentence's contribution to Citation Recall (1 | 0 | None if unresolved) and the reason."""
    if not f["markers"]:
        return 0, "no_citation"
    if f["cited_invalid"]:
        return 0, "invalid_citation"
    if f["joint"]["status"] == "overlength":
        return None, "overlength"
    return f["joint"]["support"], "joint_support" if f["joint"]["support"] else "no_joint_support"


def calcular(plano: dict, decisoes_disponiveis: bool = True, estado: str = "ok",
             razao: Optional[str] = None) -> dict:
    """The three metrics of one article, with its status and the reason for each metric left null."""
    frases, textos, caso = plano["frases"], plano["textos"], plano["caso"]
    n_evid = len(textos)
    elegiveis = [f for f in frases if f["avaliar_recall"]]
    razoes: Dict[str, str] = {}
    recall = precision = coverage = None

    if not decisoes_disponiveis:            # no judge decisions: metrics stay null, with the given status and reason
        razoes = {m: razao or estado for m in GROUNDING}
    else:
        estado = "ok"
        apoios = [suporte_da_frase(f) for f in elegiveis]
        if caso == "unstructured":
            razoes["citation_recall"] = "unstructured_article"
        elif not elegiveis:
            razoes["citation_recall"] = "no_recall_eligible_sentences"
        elif any(s is None for s, _ in apoios):
            razoes["citation_recall"] = "overlength_unresolved"
        else:
            recall = sum(s for s, _ in apoios) / len(elegiveis)
        total, corretas, cobertas, por_resolver = 0, 0, set(), set()
        for f in frases:
            for i, (ok, _) in correcao_das_citacoes(f).items():
                total += 1
                if ok is None:
                    por_resolver.add(i)
                    continue
                corretas += ok
                if ok:
                    cobertas.add(i)
        if total == 0:
            razoes["citation_precision"] = "no_citations"
        elif por_resolver:
            razoes["citation_precision"] = "overlength_unresolved"
        else:
            precision = corretas / total
        if por_resolver - cobertas:          # an unresolved unit only matters if no other citation covers it
            razoes["evidence_coverage"] = "overlength_unresolved"
        else:
            coverage = len(cobertas & set(textos)) / n_evid
        if "overlength_unresolved" in razoes.values():
            estado = "unresolved_overlength"

    return {"citation_recall": recall, "citation_precision": precision, "evidence_coverage": coverage,
            "status": estado, "null_reasons": razoes}
