"""Retention of runs, so their documents can be served to the reader and a finished verification
can be opened again by its address.

The app runs in several processes and the request for a citation's document may land on a
different one than the run did, so the store is on disk, with an in-memory cache in front.

Two kinds of file: the last `capacidade` runs, finished or not, which only the citations of a page
under way need; and the verifications that finished (`guardar`), in a folder of their own, which are
the page's permanent addresses and are pruned only past `guardadas` of them (0, never).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .schemas import RunResult

logger = logging.getLogger(__name__)

RUN_ID_VALIDO = re.compile(r"^[0-9a-f]{6,32}$")
CACHE_EM_MEMORIA = 8
PASTA_GUARDADAS = "guardadas"


class RunStore:
    def __init__(self, capacidade: int, directoria: str | os.PathLike[str],
                 guardadas: int = 0) -> None:
        self._capacidade = max(1, capacidade)
        # 0: the saved verifications are kept for good.
        self._guardadas = max(0, guardadas)
        self._directoria = Path(directoria)
        self._permanente = self._directoria / PASTA_GUARDADAS
        self._cache: OrderedDict[str, RunResult] = OrderedDict()
        # A saved verification never changes, so its copy here is never stale; a run's may be.
        self._cache_guardadas: OrderedDict[str, RunResult] = OrderedDict()
        self._lock = Lock()

    def _caminho(self, run_id: str, pasta: Path | None = None) -> Path | None:
        if not RUN_ID_VALIDO.match(run_id):
            return None
        return (pasta or self._directoria) / f"{run_id}.json"

    def _gravar(self, caminho: Path, resultado: RunResult) -> bool:
        parcial: Path | None = None
        try:
            # Atomic write: a reader in another process never sees a half-written file.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=caminho.parent, delete=False, suffix=".parcial"
            ) as ficheiro:
                parcial = Path(ficheiro.name)
                ficheiro.write(resultado.model_dump_json())
            parcial.replace(caminho)
        except OSError as erro:
            logger.error("não foi possível gravar a execução %s: %s", resultado.run_id, erro)
            # A failed write leaves no `.parcial` behind: pruning only sees the `.json` files.
            if parcial is not None:
                parcial.unlink(missing_ok=True)
            return False
        return True

    def put(self, resultado: RunResult) -> None:
        caminho = self._caminho(resultado.run_id)
        if caminho is None:
            logger.warning("identificador de execução inesperado: %r", resultado.run_id)
            return
        if not self._gravar(caminho, resultado):
            return

        self._lembrar(self._cache, resultado.run_id, resultado)
        self._podar(self._directoria, self._capacidade)

    def guardar(self, resultado: RunResult) -> bool:
        """Keeps a finished verification for good, so its address opens it again. False when it
        could not be written."""
        caminho = self._caminho(resultado.run_id, self._permanente)
        if caminho is None:
            logger.warning("identificador de execução inesperado: %r", resultado.run_id)
            return False
        resultado = resultado.model_copy(
            update={"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        try:
            self._permanente.mkdir(parents=True, exist_ok=True)
        except OSError as erro:
            logger.error("não foi possível criar %s: %s", self._permanente, erro)
            return False
        if not self._gravar(caminho, resultado):
            return False
        self._lembrar(self._cache_guardadas, resultado.run_id, resultado)
        if self._guardadas:
            self._podar(self._permanente, self._guardadas)
        return True

    def _lembrar(self, cache: OrderedDict[str, RunResult], run_id: str,
                 resultado: RunResult) -> None:
        """Keeps `resultado` in an in-memory cache, the most recent last."""
        with self._lock:
            cache[run_id] = resultado
            cache.move_to_end(run_id)
            while len(cache) > CACHE_EM_MEMORIA:
                cache.popitem(last=False)

    def _ler(self, caminho: Path | None) -> RunResult | None:
        if caminho is None or not caminho.exists():
            return None
        try:
            return RunResult.model_validate_json(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erro:
            logger.error("execução %s ilegível: %s", caminho.stem, erro)
            return None

    def guardada(self, run_id: str) -> RunResult | None:
        """The verification kept for `run_id` (`guardar`), or None: a run that is under way, or
        failed, or has left the store, is not one."""
        with self._lock:
            resultado = self._cache_guardadas.get(run_id)
            if resultado is not None:
                self._cache_guardadas.move_to_end(run_id)
                return resultado
        resultado = self._ler(self._caminho(run_id, self._permanente))
        if resultado is not None:
            self._lembrar(self._cache_guardadas, run_id, resultado)
        return resultado

    def get(self, run_id: str) -> RunResult | None:
        with self._lock:
            resultado = self._cache.get(run_id)
            if resultado is not None:
                self._cache.move_to_end(run_id)
                return resultado

        resultado = self._ler(self._caminho(run_id)) or self.guardada(run_id)
        if resultado is not None:
            self._lembrar(self._cache, run_id, resultado)
        return resultado

    @staticmethod
    def _podar(directoria: Path, capacidade: int) -> None:
        """Keep only the most recent files of `directoria`, by modification time."""
        try:
            ficheiros = sorted(
                directoria.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            return
        for antigo in ficheiros[capacidade:]:
            try:
                antigo.unlink()
            except OSError:
                pass
