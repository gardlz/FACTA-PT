"""Finished runs, kept so that the news item behind a citation can be served later.

The request for a document may reach a different process than the one that ran the pipeline,
so runs are stored on disk, with a small in-memory cache in front.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from .schemas import RunResult

logger = logging.getLogger(__name__)

RUN_ID_VALIDO = re.compile(r"^[0-9a-f]{6,32}$")
CACHE_EM_MEMORIA = 8


class RunStore:
    def __init__(self, capacidade: int, directoria: str | os.PathLike[str]) -> None:
        self._capacidade = max(1, capacidade)
        self._directoria = Path(directoria)
        self._directoria.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, RunResult] = OrderedDict()
        self._lock = Lock()

    def _caminho(self, run_id: str) -> Path | None:
        if not RUN_ID_VALIDO.match(run_id):
            return None
        return self._directoria / f"{run_id}.json"

    def put(self, resultado: RunResult) -> None:
        caminho = self._caminho(resultado.run_id)
        if caminho is None:
            logger.warning("identificador de execução inesperado: %r", resultado.run_id)
            return
        try:
            # Atomic write: a reader in another process never sees a half-written file.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self._directoria, delete=False, suffix=".parcial"
            ) as ficheiro:
                ficheiro.write(resultado.model_dump_json())
                parcial = Path(ficheiro.name)
            parcial.replace(caminho)
        except OSError as erro:
            logger.error("não foi possível gravar a execução %s: %s", resultado.run_id, erro)
            return

        with self._lock:
            self._cache[resultado.run_id] = resultado
            self._cache.move_to_end(resultado.run_id)
            while len(self._cache) > CACHE_EM_MEMORIA:
                self._cache.popitem(last=False)
        self._podar()

    def get(self, run_id: str) -> RunResult | None:
        with self._lock:
            resultado = self._cache.get(run_id)
            if resultado is not None:
                self._cache.move_to_end(run_id)
                return resultado

        caminho = self._caminho(run_id)
        if caminho is None or not caminho.exists():
            return None
        try:
            resultado = RunResult.model_validate_json(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erro:
            logger.error("execução %s ilegível: %s", run_id, erro)
            return None

        with self._lock:
            self._cache[run_id] = resultado
            self._cache.move_to_end(run_id)
            while len(self._cache) > CACHE_EM_MEMORIA:
                self._cache.popitem(last=False)
        return resultado

    def _podar(self) -> None:
        """Keep only the most recent runs, by modification time."""
        try:
            ficheiros = sorted(
                self._directoria.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            return
        for antigo in ficheiros[self._capacidade :]:
            try:
                antigo.unlink()
            except OSError:
                pass
