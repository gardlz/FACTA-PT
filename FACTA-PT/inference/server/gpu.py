"""Sharing one GPU between the four models.

The models wait in main memory and take turns on the GPU: before one runs, the least recently used
go back to main memory until there is room for its weights and its call.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
import time

import torch

from .dispositivo import MARGEM_RAM, memoria_disponivel

logger = logging.getLogger(__name__)


def alocada() -> int:
    """Bytes of GPU memory this process's tensors take (0 without CUDA)."""
    return torch.cuda.memory_allocated() if torch.cuda.is_available() else 0


def livre() -> int:
    """Bytes free on the card. The allocator's unused cache is released first: where the driver
    lends system memory to a full GPU (as on Windows), what it holds may not be on the card."""
    torch.cuda.empty_cache()
    return torch.cuda.mem_get_info()[0]


def capacidade() -> int:
    """Bytes this process could hold on the GPU with every model moved out."""
    return livre() + torch.cuda.memory_allocated()


def bytes_de(modulo: torch.nn.Module) -> int:
    """Bytes of a module's weights and buffers."""
    return sum(t.numel() * t.element_size()
               for t in itertools.chain(modulo.parameters(), modulo.buffers()))


def gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def devolver_ram() -> None:
    """Gives the main memory a model freed on going to the GPU back to the system; the C
    allocator would otherwise keep it for reuse."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def copia_propria(modulo: torch.nn.Module) -> torch.nn.Module:
    """The module with its weights copied into main memory. Loaded weights are the checkpoint
    file mapped from disk, which may be slow to read again or be unplugged."""
    for tensor in itertools.chain(modulo.parameters(), modulo.buffers()):
        tensor.data = tensor.data.clone()
    return modulo


class ModeloMovel:
    """A model that takes turns on the GPU: `_model` runs on `_casa` (only a CUDA one takes part),
    its weights take `ocupa` bytes there and a call `folga` more. `_na_gpu` is set only once a move
    in has finished, so a model left halfway goes in whole next time."""

    _model = None
    _casa = ""
    _na_gpu = False
    ocupa = 0
    folga = 0
    descricao = "o modelo"

    @property
    def movel(self) -> bool:
        return self._model is not None and self._casa.startswith("cuda")

    @property
    def na_gpu(self) -> bool:
        return self.movel and self._na_gpu

    @property
    def ram_ao_sair(self) -> int:
        """Main memory the model takes when it leaves the GPU."""
        return self.ocupa

    def para_gpu(self) -> None:
        self._na_gpu = False
        antes = torch.cuda.memory_allocated()
        self._enviar()
        self.ocupa = torch.cuda.memory_allocated() - antes
        self._na_gpu = True

    def _enviar(self) -> None:
        self._model.to(self._casa)

    def para_ram(self) -> None:
        self._na_gpu = False
        self._model.to("cpu")


class Partilha:
    """Moves the models in and out of the GPU. It is called with the GPU's queue held, so no
    model runs while another one moves."""

    def __init__(self, modelos: dict[str, ModeloMovel]) -> None:
        self._modelos = modelos
        self._usado: dict[str, float] = {}

    def na_gpu(self) -> list[str]:
        return [nome for nome, modelo in self._modelos.items() if modelo.na_gpu]

    def preparar(self, nome: str) -> None:
        """Puts `nome` on the GPU with room for its call, moving out the least recently used models
        that main memory has room for. Short of room for the call it runs anyway, slower where the
        driver lends system memory; short of room for the weights it is refused."""
        modelo = self._modelos[nome]
        self._usado[nome] = time.monotonic()
        if not modelo.movel:
            return
        precisa = modelo.folga + (0 if modelo.na_gpu else modelo.ocupa)
        outros = sorted((n for n in self.na_gpu() if n != nome),
                        key=lambda n: self._usado.get(n, 0.0))
        for outro in outros:
            if livre() >= precisa:
                break
            falta = int(self._modelos[outro].ram_ao_sair * MARGEM_RAM)
            disponivel = memoria_disponivel()
            if disponivel is not None and disponivel < falta:
                logger.warning("%s fica na GPU: precisa de %s de memória principal para sair e só "
                               "há %s", outro, gb(falta), gb(disponivel))
                continue
            self._mover(outro, entra=False)
        sobra = livre()
        if not modelo.na_gpu and sobra < modelo.ocupa:
            raise RuntimeError(f"não há lugar na GPU para {modelo.descricao}: os pesos precisam de "
                               f"{gb(modelo.ocupa)} e só há {gb(sobra)}")
        if sobra < precisa:
            logger.warning("%s precisa de %s na GPU e só há %s: corre na mesma, mais devagar se o "
                           "controlador emprestar memória do sistema", nome, gb(precisa), gb(sobra))
        if not modelo.na_gpu:
            self._mover(nome, entra=True)

    def _mover(self, nome: str, entra: bool) -> None:
        modelo = self._modelos[nome]
        try:
            modelo.para_gpu() if entra else modelo.para_ram()
        except Exception:
            if entra:
                # Half moved, a model would run with its weights on two devices: move it back out.
                try:
                    modelo.para_ram()
                except Exception:  # noqa: BLE001 - the first failure is the one to report
                    logger.exception("%s ficou a meio caminho da GPU", nome)
            raise
        if entra:
            devolver_ram()
        logger.info("%s %s GPU (%s)", nome, "entrou na" if entra else "saiu da", gb(modelo.ocupa))
