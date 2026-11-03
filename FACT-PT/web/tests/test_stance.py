"""The stance classifier's answer, as the pipeline contract reads it."""

import pytest
from pydantic import ValidationError

from app.pipeline.stance import to_stance

LOGITS = {"supported": 2.0, "refuted": -1.0, "nei": 0.5}


def test_to_stance_keeps_the_label_and_adjusted_logits():
    stance = to_stance("e1", {"id": "e1", "label": "supported", "logits": LOGITS})

    assert stance.excerpt_id == "e1"
    assert stance.label == "supported"
    assert stance.logits == LOGITS


def test_to_stance_refuses_an_unknown_label():
    with pytest.raises(ValidationError):
        to_stance("e1", {"label": "talvez", "logits": LOGITS})


def test_to_stance_refuses_an_answer_without_a_label_or_logits():
    with pytest.raises(KeyError):
        to_stance("e1", {"logits": LOGITS})
    with pytest.raises(KeyError):
        to_stance("e1", {"label": "supported"})
