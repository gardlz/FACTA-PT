"""Reads the claim span-document pairs of one partition."""

import functools
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PARES = RAIZ / "data" / "pares.jsonl"


@functools.lru_cache(maxsize=None)
def _ler():
    if not PARES.exists():
        raise SystemExit(f"não há {PARES}.\nCorrer primeiro:\n"
                         f"    python src/construir_dados.py")
    return [json.loads(l) for l in PARES.read_text(encoding="utf-8").splitlines() if l.strip()]


def pares(conjunto):
    """The pairs of one partition, in file order."""
    if conjunto not in ("train", "test"):
        raise SystemExit(f"conjunto «{conjunto}» não existe: train ou test")
    return [dict(x) for x in _ler() if x["particao"] == conjunto]
