"""Paths and small I/O helpers shared by the retrieval scripts.

CLEVER sits at the root of the repository, next to the stage folders. Standard library only, so
the offline scripts do not pull in the API client.
"""

import json
import logging
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent           # src/
STAGE_DIR = SCRIPT_DIR.parent
CLEVER_JSON = STAGE_DIR.parent / "CLEVER" / "clever.json"

OUTPUTS_DIR = STAGE_DIR / "outputs"
QUESTIONS_FILE = OUTPUTS_DIR / "gold_questions.jsonl"
TOP20_DIR = OUTPUTS_DIR / "lusa_top20"
DOCS_DIR = OUTPUTS_DIR / "lusa_docs"

# Characters not allowed in file names (Windows included).
CARACTERES_PROIBIDOS = '/\\:*?"<>|'


def ler_clever(path=CLEVER_JSON):
    """CLEVER (JSON array of articles); a missing file stops with the place the README gives it."""
    path = Path(path)
    if not path.exists():
        sys.exit(f"Falta {path}. O CLEVER fica na raiz do repositório (ver o README).")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_spans(item):
    """(span_id, claim_span) of an item: dict -> item id; list -> <id>_s<i>."""
    spans = item.get("claim_span")
    if isinstance(spans, dict):
        yield item["id"], spans
    elif isinstance(spans, list):
        for i, span in enumerate(spans):
            yield f'{item["id"]}_s{i}', span


def iter_claim_spans(documents):
    """(document, item, span_id, span) of every claim span of CLEVER (items with claim == true)."""
    for document in documents:
        for item in document.get("items", []):
            if item.get("claim") is True:
                for span_id, span in iter_spans(item):
                    yield document, item, span_id, span


def safe_name(valor):
    """File name derived from an id (question_id, span_id or doc_id)."""
    return "".join("_" if c in CARACTERES_PROIBIDOS else c for c in str(valor)).strip()


def write_json(path, data):
    """Write indented UTF-8 JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporario = path.with_name(path.name + ".tmp")
    temporario.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, path)


def read_jsonl(path, dica=None):
    """Read a JSONL file; with `dica`, a missing file exits with that hint."""
    if dica and not path.exists():
        sys.exit(f"Ficheiro em falta: {path}. Executar primeiro: {dica}")
    with path.open(encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def write_jsonl(path, records):
    """Write one JSON object per line (UTF-8, accents kept)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def configurar_log(caminho_log):
    """Log to the console and to the given file."""
    caminho_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(caminho_log, encoding="utf-8")],
    )


def formatar_contagens(counter):
    """Format a Counter as 'value N | value N', most frequent first."""
    return " | ".join(f"{rotulo} {n}" for rotulo, n in counter.most_common())
