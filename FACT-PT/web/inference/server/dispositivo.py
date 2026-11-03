"""Where a model runs: the requested device, or else CUDA, then Apple's MPS, then CPU."""

from __future__ import annotations

import torch

# Free main memory a model needs beyond its own size: to load it, to take it off the GPU, and on
# the CPU for its working memory.
MARGEM_RAM = 1.15


def escolher(pedido: str) -> str:
    if pedido and pedido != "auto":
        return pedido
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def memoria_disponivel() -> int | None:
    """Free main memory in bytes as seen from inside the container. None if unreadable."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as ficheiro:
            for linha in ficheiro:
                if linha.startswith("MemAvailable:"):
                    return int(linha.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None
