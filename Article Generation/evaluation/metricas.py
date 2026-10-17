"""Keys, reported names and groups of the six evaluation metrics.

Evidence Grounding: Citation Recall, Citation Precision, Evidence Coverage. Article Quality: Relevance,
Comprehensibility, Evidence Presentation. `vista()` puts a per-article result in the flat shape the
aggregation reads.
"""

from typing import Dict

GROUNDING = ("citation_recall", "citation_precision", "evidence_coverage")
QUALIDADE = ("relevance", "comprehensibility", "evidence_presentation")

NOMES: Dict[str, str] = {
    "citation_recall": "Citation Recall",
    "citation_precision": "Citation Precision",
    "evidence_coverage": "Evidence Coverage",
    "relevance": "Relevance",
    "comprehensibility": "Comprehensibility",
    "evidence_presentation": "Evidence Presentation",
}


def vista(r: dict) -> dict:
    """Flatten one per-article result: grounding values, status and null reasons, quality scores."""
    g = r["evidence_grounding"]
    q = r["article_quality"]
    return {"grounding": {m: g.get(m) for m in GROUNDING},
            "grounding_status": g.get("status"), "grounding_reasons": g.get("null_reasons") or {},
            "qualidade": {d: q[d] for d in QUALIDADE if d in q}}


def nome(chave: str) -> str:
    return NOMES.get(chave, chave)
