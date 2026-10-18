"""Builds the gold-question units used as retrieval queries, from CLEVER (clever.json).

Keeps the items with ``claim == true``, expands each ``claim_span`` (dict or list) into a span
and each span into its gold questions. Writes ``gold_questions.jsonl`` with every claim span of
CLEVER; each unit carries its claim span, complete claim and publication date, and its id is
``<span_id>__q<n>``.
"""

import argparse
import re
from collections import Counter
from datetime import date
from pathlib import Path

from comum import (CLEVER_JSON, OUTPUTS_DIR, formatar_contagens as format_counts,
                   iter_claim_spans, ler_clever, write_jsonl)

# Abbreviated Portuguese months of the CLEVER publication_time field.
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}

# Year assumed when publication_time has none (the corpus covers the 2025 elections).
DEFAULT_YEAR = 2025


def parse_publication_time(raw):
    """'DD mmm YYYY' -> 'YYYY-MM-DD' (year optional, possibly in brackets)."""
    if not isinstance(raw, str):
        return None
    match = re.fullmatch(r"(\d{1,2})\s+([a-zç]{3,})\.?\s*(?:\(?(\d{4})\)?)?", raw.strip().lower())
    if not match:
        return None
    day, month, year = match.groups()
    if month[:3] not in MESES:
        return None
    try:
        return date(int(year) if year else DEFAULT_YEAR, MESES[month[:3]], int(day)).isoformat()
    except ValueError:
        return None


def collapse_spaces(text):
    """Collapse spaces, line breaks and non-breaking spaces into one space."""
    return re.sub(r"\s+", " ", text).strip()


def build_span_unit(document, item, span_id, span):
    """The unit of one claim span.

    ``claim_span`` and ``text_segment`` are kept verbatim; questions get normalised spaces.
    """
    return {
        "span_id": span_id,
        "publication_time": parse_publication_time(document.get("publication_time")),
        "claim_span": span.get("text"),
        "text_segment": item.get("text_segment"),
        "questions": [collapse_spaces(q["text"]) for q in span.get("questions") or []
                      if q["text"] and q["text"].strip()],
    }


def iter_span_units(documents):
    """One unit per claim span of CLEVER (items with claim == true only)."""
    for document, item, span_id, span in iter_claim_spans(documents):
        yield build_span_unit(document, item, span_id, span)


def iter_question_units(span_unit):
    """One unit per gold question of a span (question_id <span_id>__q<n>)."""
    rest = {key: value for key, value in span_unit.items() if key != "questions"}
    for index, question in enumerate(span_unit["questions"], 1):
        yield {
            "question_id": f'{span_unit["span_id"]}__q{index}',
            "question": question,
            **rest,
        }


def build_units(clever_json):
    """(span units, question units) of every claim span of CLEVER."""
    spans = list(iter_span_units(ler_clever(clever_json)))
    questions = [q for span in spans for q in iter_question_units(span)]
    return spans, questions


def print_summary(spans, questions):
    print(f"Spans: {len(spans)}")
    print(f"Perguntas: {len(questions)}")
    print(f"Perguntas por span: {format_counts(Counter(len(s['questions']) for s in spans))}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--clever", type=Path, default=CLEVER_JSON,
                   help="CLEVER (default: ../CLEVER/clever.json).")
    p.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR,
                   help="Output folder for gold_questions.jsonl.")
    return p.parse_args()


def main():
    args = parse_args()
    spans, questions = build_units(args.clever)

    questions_path = args.output_dir / "gold_questions.jsonl"
    write_jsonl(questions_path, questions)

    print(f"[ok] {len(questions)} perguntas -> {questions_path}")
    print_summary(spans, questions)


if __name__ == "__main__":
    main()
