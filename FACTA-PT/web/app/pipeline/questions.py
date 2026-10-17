"""Stage 1: the verification questions, with stable ids.

The inference service already cleans the model output as in the question-generation evaluation
(deduplicated, ending in "?"); here the questions only get ids and a cap.
"""

from __future__ import annotations

from ..schemas import Question


def to_questions(textos: list[str], limite: int) -> list[Question]:
    return [
        Question(id=f"q{i}", index=i, text=texto)
        for i, texto in enumerate(textos[:limite], start=1)
    ]
