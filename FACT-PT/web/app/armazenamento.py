"""Small JSON files shared by the site's processes: accounts, platform settings and reviews.

The app runs in several processes and has no database, so these live on the same volume as the
runs (`RUN_STORE_DIR`), written atomically and read whole. Every write keeps the previous file as
`.bak`, so a bad edit or a crash still leaves the state before it.

A read-modify-write goes through `bloqueio`: a lock of the process (threads) and of the system (the
other processes and the worker), so two requests cannot both read version 3 and both write 4.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

if os.name == "nt":  # pragma: no cover - the tests and the development machines
    import msvcrt
else:  # pragma: no cover - the containers
    import fcntl


class FalhaAoGravar(OSError):
    """The file could not be written: the disk is full, or the volume is gone. Callers must not
    report the change as saved."""

# One lock per file, so two threads of a process wait for each other before the system lock.
_trancas: dict[str, Lock] = {}
_trancas_guarda = Lock()


def _tranca(caminho: Path) -> Lock:
    chave = str(caminho.resolve()).lower()
    with _trancas_guarda:
        return _trancas.setdefault(chave, Lock())


def _travar(ficheiro) -> None:
    if os.name == "nt":  # pragma: no cover
        ficheiro.seek(0)
        ficheiro.write(b"\0")
        ficheiro.flush()
        # `LK_LOCK` gives up after ten tries; retry until the other process is done.
        for _ in range(500):
            try:
                ficheiro.seek(0)
                msvcrt.locking(ficheiro.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                import time

                time.sleep(0.02)
        raise TimeoutError(f"não foi possível bloquear {ficheiro.name}")
    fcntl.flock(ficheiro.fileno(), fcntl.LOCK_EX)


def _destravar(ficheiro) -> None:
    if os.name == "nt":  # pragma: no cover
        ficheiro.seek(0)
        msvcrt.locking(ficheiro.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(ficheiro.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def bloqueio(caminho: Path) -> Iterator[None]:
    """Holds the lock of `caminho` for the block, in this process and in the others."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with _tranca(caminho):
        with open(caminho.with_name(f"{caminho.name}.lock"), "a+b") as ficheiro:
            _travar(ficheiro)
            try:
                yield
            finally:
                _destravar(ficheiro)


def ler_json(caminho: Path) -> dict[str, Any] | None:
    """The file's content, or None when it is absent or unreadable."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as erro:
        logger.error("%s ilegível: %s", caminho, erro)
        return None


def gravar_json(caminho: Path, dados: dict[str, Any], copia: bool = True) -> bool:
    """Writes `dados` atomically, keeping the file it replaces as `.bak`. False when it could not."""
    parcial: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if copia and caminho.exists():
            try:
                shutil.copy2(caminho, caminho.with_name(f"{caminho.stem}.bak{caminho.suffix}"))
            except OSError as erro:
                logger.warning("não foi possível guardar a cópia de %s: %s", caminho, erro)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=caminho.parent, delete=False, suffix=".parcial"
        ) as ficheiro:
            parcial = Path(ficheiro.name)
            json.dump(dados, ficheiro, ensure_ascii=False, indent=2)
            ficheiro.write("\n")
            ficheiro.flush()
            os.fsync(ficheiro.fileno())
        parcial.replace(caminho)
    except OSError as erro:
        logger.error("não foi possível gravar %s: %s", caminho, erro)
        if parcial is not None:
            parcial.unlink(missing_ok=True)
        return False
    return True


def actualizar_json(
    caminho: Path, funcao: Callable[[dict[str, Any]], dict[str, Any]], inicial: dict[str, Any]
) -> dict[str, Any]:
    """Reads the file (or `inicial`), hands it to `funcao`, and writes what it returns, all under
    the lock. Returns the written data."""
    with bloqueio(caminho):
        dados = ler_json(caminho) or inicial
        novos = funcao(dados)
        if not gravar_json(caminho, novos):
            raise FalhaAoGravar(str(caminho))
        return novos
