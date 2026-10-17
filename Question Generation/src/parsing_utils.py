"""Raw model output -> list of questions: split on newlines, "||" and "?" (T5 SentencePiece
vocabularies have no newline), strip bullets and numbering, add a missing "?", and drop template
headers and duplicates. Special tokens are not filtered; the raw output is stored next to the
questions.
"""

import json
import re
from typing import List

_BULLET_RE = re.compile(r"^\s*(?:[-–—•*]|\d+[.)])\s*")
_PIPE_SEP_RE = re.compile(r"\s*\|\|\s*")
_QUESTION_RE = re.compile(r"[^?]+\?")


def _clean_line(line: str) -> str:
    line = _BULLET_RE.sub("", line).strip()
    line = line.strip("\"'` ").strip()
    return line


def _e_etiqueta_do_molde(texto: str) -> bool:
    """True if the candidate is only a header of the prompt template (e.g. "PERGUNTAS:")."""
    from prompts import ETIQUETAS_DO_MOLDE

    nu = texto.strip().rstrip("?:").strip().casefold()
    return any(nu == etiqueta.casefold() for etiqueta in ETIQUETAS_DO_MOLDE)


def _from_json(raw: str):
    """List of strings if the output is JSON ({"questions": [...]} or a list), else None."""
    raw = raw.strip()
    if not (raw.startswith("{") or raw.startswith("[")):
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(obj, dict):
        obj = obj.get("questions", [])
    if isinstance(obj, list):
        return [str(x) for x in obj if isinstance(x, (str, int, float))]
    return None


def _split_on_qmarks(text: str) -> List[str]:
    """"Q1? Q2?" -> ["Q1?", "Q2?"]; a trailing remainder without "?" is kept as its own piece."""
    matches = list(_QUESTION_RE.finditer(text))
    if not matches:
        return [text]
    parts = [m.group() for m in matches]
    tail = text[matches[-1].end():].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_candidates(raw_output: str) -> List[str]:
    """Lines -> "||" -> "?"."""
    pieces: List[str] = []
    for line in raw_output.splitlines():
        for chunk in _PIPE_SEP_RE.split(line):
            pieces.extend(_split_on_qmarks(chunk))
    return pieces


def parse_questions(raw_output: str, ensure_qmark: bool = True) -> List[str]:
    """Clean, de-duplicated list of questions from the model output."""
    if not raw_output:
        return []

    candidates = _from_json(raw_output)
    if candidates is None:
        candidates = _split_candidates(raw_output)

    questions: List[str] = []
    seen = set()
    for cand in candidates:
        q = _clean_line(cand)
        if len(q) < 3 or _e_etiqueta_do_molde(q):
            continue
        if ensure_qmark and not q.endswith("?"):
            q = q.rstrip(".;:!") + "?"
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        questions.append(q)
    return questions
