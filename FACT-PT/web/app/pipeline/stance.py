"""Stage 5: the relation between the claim and each excerpt, as the classifier answers it.

The task is the claim-evidence relation, never the veracity of the claim: the pair
(claim, excerpt) is labelled supported, refuted or nei. Which excerpts then reach the article is
`evidencia.py`'s to decide.
"""

from __future__ import annotations

from ..schemas import ExcerptStance


def to_stance(excerpt_id: str, payload: dict) -> ExcerptStance:
    """One answer of the inference service's `/v1/stance`: its label and its adjusted logits,
    one per label. Raises `KeyError` when either is missing and `ValidationError` when the label
    or the logits are not the three the pipeline knows."""
    return ExcerptStance(excerpt_id=excerpt_id, label=payload["label"], logits=payload["logits"])
