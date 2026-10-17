"""The (premise, hypothesis) texts the encoder sees; the hypothesis is always the claim span.

Relevance premise: news title + '. ' + body cut at 380 words. Entailment premise: the
three-sentence window built by `folds.exemplos_entailment`.
"""

import re

MAX_PALAVRAS = 380


def frases_do(texto):
    """Rough sentence split, used to build the entailment windows and measure their coverage."""
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚ«\"])", texto or "")
            if f.strip()]


def premissa(par):
    """The evidence side of a relevance pair: the title, then the body truncated to 380 words."""
    topo = par.get("titulo") or ""
    corpo = " ".join((par.get("evidencia_texto") or "").split()[:MAX_PALAVRAS])
    return (topo + ". " + corpo).strip(" .") if topo else corpo.strip()


def hipotese(par):
    """The claim side: the claim span with surrounding spaces and dots stripped."""
    return (par["claim_span"] or "").strip(" .").strip()


def construir(par):
    """(premise, hypothesis) of a relevance pair."""
    return premissa(par), hipotese(par)
