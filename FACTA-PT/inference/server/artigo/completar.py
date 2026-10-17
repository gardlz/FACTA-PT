"""Completing from the plan an article no attempt finished, so it always has the plan's structure.

Written sections stay as they are, the limits and conclusion take the plan's fixed texts, a section
never reached gets one sentence in the plan's words, and a missing lead becomes the conclusion.
"""

from __future__ import annotations

from . import plano as pv
from . import veredito as vd

CLAIM = "Está em verificação a afirmação «{claim}», publicada a {data}."
ENQUADRAMENTO = (
    "A evidência {refs} é relevante para compreender a claim, mas não permite sustentá-la nem "
    "refutá-la.",
    "As evidências {refs} são relevantes para compreender a claim, mas não permitem sustentá-la "
    "nem refutá-la.",
)
NAO_DECISIVA = ("A informação apresentada em «Enquadramento factual» não permite sustentar nem "
                "refutar a claim.")
SEM_EVIDENCIA = ("Não foram recuperadas evidências relevantes que permitam verificar factualmente "
                 "a claim.")
LEAD = "Lead"


def frase(plano: dict, seccao: dict) -> str:
    """The sentence that stands for a section the model did not write."""
    if seccao["id"] == pv.S_CLAIM:
        return CLAIM.format(claim=plano["claim"], data=plano["claim_date"])
    if seccao["id"] == pv.S_ENQUADRAMENTO:
        return pv._com(ENQUADRAMENTO, seccao["marcadores"])
    base = pv._caso_base(plano["caso"])
    if base == vd.CASO_NAO_DECISIVA:
        return NAO_DECISIVA
    if base == vd.CASO_SEM_EVIDENCIA:
        return SEM_EVIDENCIA
    partes = []
    for rotulo, modelos in ((vd.SUPPORTED, pv.VER_CONFLITO_APOIAM),
                            (vd.REFUTED, pv.VER_CONFLITO_CONTRARIAM)):
        refs = pv._refs(plano["grupos"], rotulo)
        if refs:
            partes.append(pv._com(modelos, refs))
    return " ".join(partes)


def paragrafos_por_seccao(blocos: list[dict]) -> dict[str, list[str]]:
    """The paragraphs written under each heading."""
    escritos: dict[str, list[str]] = {}
    atual = None
    for bloco in blocos:
        if bloco["type"] == "heading":
            atual = bloco["text"]
            escritos.setdefault(atual, [])
        elif atual is not None:
            escritos[atual].append(bloco["text"])
    return escritos


def completar(plano: dict, artigo: dict) -> tuple[dict, list[str]]:
    """(the article with every section of the plan, the parts put together without the model)."""
    escritos = paragrafos_por_seccao(artigo.get("blocks") or [])
    blocos: list[dict] = []
    completadas: list[str] = []
    for seccao in plano["seccoes"]:
        paragrafos = escritos.get(seccao["titulo"]) or []
        if "texto_fixo" in seccao:
            if paragrafos != [seccao["texto_fixo"]]:
                completadas.append(seccao["titulo"])
            paragrafos = [seccao["texto_fixo"]]
        elif not paragrafos:
            paragrafos = [frase(plano, seccao)]
            completadas.append(seccao["titulo"])
        blocos.append({"type": "heading", "text": seccao["titulo"]})
        blocos.extend({"type": "paragraph", "text": p} for p in paragrafos)
    lead = (artigo.get("lead") or "").strip()
    if not lead:
        lead = plano["conclusao_texto"]
        completadas.insert(0, LEAD)
    return {"title": plano["titulo"], "lead": lead, "blocks": blocos}, completadas
