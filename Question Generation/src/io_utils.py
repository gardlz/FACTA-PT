"""JSONL/YAML helpers and the normalised example schema shared by every script.

An example has: id, claim_span, context, claim_objects, claimers, publication_time,
claim_time, reference_questions (CLEVER), silver_questions (ClaimPT) and questions (the
training target), plus source.
"""

import json
import re
from pathlib import Path
from typing import Any, Iterable, List, Tuple

NAO_FORNECIDO = "Não fornecido."

# Alternative names of the publication-date field in the input data.
_PUBDATE_KEYS = ("publication_time", "publication_date", "date", "published_at", "pub_date")


def read_jsonl(path) -> List[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_yaml(path) -> dict:
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text)).strip() if text is not None else ""


def _first_pubdate(raw: dict) -> str:
    """First non-empty publication date among the alternative field names."""
    for key in _PUBDATE_KEYS:
        val = raw.get(key)
        if val is not None and str(val).strip():
            return _clean(val)
    return ""


def as_text_list(value: Any) -> List[str]:
    """str / {'text': ...} / list of them -> list of cleaned strings."""
    if not value:
        return []
    if isinstance(value, str):
        t = _clean(value)
        return [t] if t else []
    if isinstance(value, dict):
        t = _clean(value.get("text", ""))
        return [t] if t else []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(as_text_list(item))
        return out
    return []


def normalize_key(text: str) -> str:
    """Deduplication key for a claim span (case-folded, whitespace collapsed)."""
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def normalize_example(raw: dict) -> dict:
    """Example in the normalised schema, with safe defaults."""
    reference = as_text_list(raw.get("reference_questions"))
    silver = as_text_list(raw.get("silver_questions"))
    # Generic "questions" field (e.g. the silver generation output) as a fallback.
    generic = as_text_list(raw.get("questions"))
    questions = reference or silver or generic

    return {
        "id": raw.get("id") or raw.get("span_id") or "",
        "claim_span": _clean(raw.get("claim_span")),
        "context": _clean(raw.get("context")),
        "claim_objects": as_text_list(raw.get("claim_objects")),
        "claimers": as_text_list(raw.get("claimers")),
        "publication_time": _first_pubdate(raw),
        "claim_time": _clean(raw.get("claim_time")),
        "reference_questions": reference or generic,
        "silver_questions": silver or generic,
        "questions": questions,
        "source": raw.get("source", ""),
    }


def load_examples(path) -> List[dict]:
    return [normalize_example(r) for r in read_jsonl(path)]


def dedup_key(example: dict) -> str:
    """The id if present, otherwise the normalised claim span."""
    if example.get("id"):
        return f"id::{example['id']}"
    return f"span::{normalize_key(example.get('claim_span', ''))}"


def dedup(examples: List[dict]) -> Tuple[List[dict], int, int]:
    """Drop duplicates keeping order. Returns (list, n_before, n_after)."""
    seen: set = set()
    out: List[dict] = []
    for ex in examples:
        key = dedup_key(ex)
        if key in seen:
            continue
        seen.add(key)
        out.append(ex)
    return out, len(examples), len(out)
