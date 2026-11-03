"""Where a checkpoint's files are: a local folder as given, or a Hugging Face repository at a
pinned revision, downloaded once into the cache volume.

The published checkpoints are FACTA-PT's three models (question generation adapter, relevance,
stance) under `liaad/`, and the base models they and the article writers start from.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _parece_caminho(caminho: str) -> bool:
    """A repository id is `organização/nome`: anything else is meant as a local path."""
    return caminho.startswith(("/", ".", "~")) or caminho.count("/") != 1


def pasta(caminho: str, revisao: str = "") -> Path:
    """The checkpoint folder: a local path as given, or the revision of a Hugging Face id.

    The hub is asked first, so that a download cut halfway is completed (a snapshot folder can
    exist with files missing); without the hub, the cache is used as it is."""
    if Path(caminho).is_dir():
        return Path(caminho)
    if _parece_caminho(caminho):
        raise FileNotFoundError(f"a pasta {caminho!r} não existe")
    from huggingface_hub import snapshot_download

    revisao = revisao or None
    try:
        logger.info("a obter %s @ %s (descarregado só o que falta na cache)", caminho, revisao)
        return Path(snapshot_download(caminho, revision=revisao))
    except Exception as erro:  # noqa: BLE001 - no hub: the cache may still hold it
        try:
            local = Path(snapshot_download(caminho, revision=revisao, local_files_only=True))
        except Exception:  # noqa: BLE001 - neither: the hub's error is the one that says why
            raise erro from None
        logger.warning("hub inacessível (%s): %s @ %s vem da cache", erro, caminho, revisao)
        return local


def ficheiro(caminho: str, nome: str, revisao: str = "") -> Path:
    """One file of a checkpoint - its card or its tokenizer, say - without the weights: from the
    local folder as given, or from the revision of a Hugging Face id (the cache without the hub)."""
    if Path(caminho).is_dir():
        return Path(caminho) / nome
    if _parece_caminho(caminho):
        raise FileNotFoundError(f"a pasta {caminho!r} não existe")
    from huggingface_hub import hf_hub_download

    revisao = revisao or None
    try:
        return Path(hf_hub_download(caminho, nome, revision=revisao))
    except Exception as erro:  # noqa: BLE001 - no hub: the cache may still hold it
        try:
            local = Path(hf_hub_download(caminho, nome, revision=revisao, local_files_only=True))
        except Exception:  # noqa: BLE001 - neither: the hub's error is the one that says why
            raise erro from None
        logger.warning("hub inacessível (%s): %s de %s @ %s vem da cache", erro, nome, caminho,
                       revisao)
        return local
