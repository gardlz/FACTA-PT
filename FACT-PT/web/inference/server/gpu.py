"""Sharing one GPU between the models that run here: the relevance and stance classifiers (the
question generator and the article writers answer behind APIs).

The models wait in main memory and take turns on the GPU: before a model runs, the ones used least
recently go back to main memory until there is room for it and for the memory its call needs. A run
goes through its stages one after the other, so on a card that cannot hold them all each model moves
in and out once per claim, in seconds. On a GPU that holds them all, none moves to make room - but
one idle for longer than `gpu_idle_ttl_s` leaves the card anyway
(`Partilha.recolher`), and comes back with its next call. One idle for longer than
`ram_idle_ttl_s` leaves main memory too (`Partilha.parados`), and loads again with its next call.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
import time
from pathlib import Path

import torch

from .dispositivo import MARGEM_RAM, memoria_disponivel

logger = logging.getLogger(__name__)


def alocada() -> int:
    """Bytes of GPU memory this process's tensors take (0 without CUDA)."""
    return torch.cuda.memory_allocated() if torch.cuda.is_available() else 0


def devolver_cache() -> None:
    """Gives the GPU's cached memory back to the driver. The cuBLAS workspace - a few MB the
    allocator hands out for the first matrix product - sits in whatever segment is there at the
    time, and a segment with a live block cannot be released: one workspace kept 6 GB of a model
    long gone. Dropping the workspaces first lets the whole segment go; the next product makes a
    new one."""
    if not torch.cuda.is_available():
        return
    torch.cuda.synchronize()
    limpar = getattr(torch._C, "_cuda_clearCublasWorkspaces", None)
    if limpar is not None:
        limpar()
    torch.cuda.empty_cache()


def livre() -> int:
    """Bytes free in the GPU's own memory. What the allocator holds unused is given back first:
    on Windows the driver lends system memory to a GPU that fills up, reached over the bus and
    many times slower, so memory the allocator holds may not be on the card at all."""
    devolver_cache()
    return torch.cuda.mem_get_info()[0]


def capacidade() -> int:
    """Bytes this process could hold on the GPU with every model moved out."""
    return livre() + torch.cuda.memory_allocated()


def driver_empresta(pedido: bool | None = None) -> bool:
    """Whether the driver lends system memory to a GPU whose own runs out, instead of failing: the
    Windows driver does, and so WSL and Docker Desktop on it, whose kernel says so. `pedido`
    (GPU_LENDS_MEMORY) overrides the guess."""
    if pedido is not None:
        return pedido
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def bytes_de(modulo: torch.nn.Module) -> int:
    """Bytes of a module's weights and buffers."""
    return sum(t.numel() * t.element_size()
               for t in itertools.chain(modulo.parameters(), modulo.buffers()))


def gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def resumo() -> str:
    """The GPU's memory as the process and the driver see it: what live tensors hold, what the
    allocator keeps, and what the driver says is free. When a model has been let go and the
    first stays high, something still refers to it; when only the last does, it is the driver."""
    livre_, total = torch.cuda.mem_get_info()
    return (f"alocada {gb(torch.cuda.memory_allocated())}, reservada "
            f"{gb(torch.cuda.memory_reserved())}, livre no controlador {gb(livre_)} de {gb(total)}")


def devolver_ram() -> None:
    """Gives the main memory a model freed on going to the GPU back to the system; the C
    allocator would otherwise keep it for reuse."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def copia_propria(modulo: torch.nn.Module) -> torch.nn.Module:
    """The module with weights of its own in main memory. Loaded weights are the checkpoint file
    mapped from disk, and a model that waits in main memory must not depend on that disk, which
    can be slow to read again or go away, as a USB drive does."""
    for tensor in itertools.chain(modulo.parameters(), modulo.buffers()):
        tensor.data = tensor.data.clone()
    return modulo


class ModeloMovel:
    """A model that takes turns on the GPU. `_model` is the module, `_casa` the device it runs on
    (a model that runs elsewhere does not take part), `ocupa` the bytes its weights take on the
    GPU, and `folga` the bytes a call needs there beyond them. `_na_gpu` is set only once a move
    to the GPU has finished: a model left halfway counts as off it, and goes in whole next time."""

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

    def descarregar(self) -> None:
        """Lets the model go, from the GPU and from main memory; it loads again with `load`. A
        model with more to let go (a file it holds open, say) overrides it."""
        self._model = None
        self._na_gpu = False

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

    def __init__(self, modelos: dict[str, ModeloMovel], empresta: bool = False) -> None:
        self._modelos = modelos
        self._usado: dict[str, float] = {}
        # A model on the GPU that was never asked for (the one loaded there at startup) has been
        # idle since the service came up.
        self._desde = time.monotonic()
        # Whether the driver lends system memory (`driver_empresta`): weights larger than the GPU
        # then go in all the same, the part that does not fit reached over the bus.
        self._empresta = empresta

    def na_gpu(self) -> list[str]:
        return [nome for nome, modelo in self._modelos.items() if modelo.na_gpu]

    def preparar(self, nome: str) -> None:
        """Puts `nome` on the GPU with room for its call, moving out the models used least
        recently until there is. One that main memory has no room for stays where it is; the rest
        move to main memory. If the
        GPU still lacks room for the call, it runs anyway - on Windows over memory the driver
        lends, more slowly; if it lacks room for the weights themselves, the call is refused, unless
        the driver lends memory for them too."""
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
            if not self._empresta:
                raise RuntimeError(f"não há lugar na GPU para {modelo.descricao}: os pesos "
                                   f"precisam de {gb(modelo.ocupa)} e só há {gb(sobra)}")
            logger.warning("%s: os pesos precisam de %s na GPU e só há %s: o controlador empresta o "
                           "resto da memória do sistema, mais devagar", nome, gb(modelo.ocupa),
                           gb(sobra))
        if sobra < precisa:
            logger.warning("%s precisa de %s na GPU e só há %s: corre na mesma, mais devagar se o "
                           "controlador emprestar memória do sistema", nome, gb(precisa), gb(sobra))
        if not modelo.na_gpu:
            self._mover(nome, entra=True)

    def usado(self, nome: str) -> None:
        """Marks `nome` as used just now. Called when its call ends as well as when it starts: an
        article takes minutes, and a model is idle from the end of its last call."""
        self._usado[nome] = time.monotonic()

    def inactivos(self, ttl: float) -> list[str]:
        """The models on the GPU unused for longer than `ttl` seconds, the idlest first."""
        agora = time.monotonic()
        paradas = {n: agora - self._usado.get(n, self._desde) for n in self.na_gpu()}
        return sorted((n for n, parada in paradas.items() if parada > ttl),
                      key=lambda n: -paradas[n])

    def parados(self, ttl: float) -> list[str]:
        """The models held in memory here unused for longer than `ttl` seconds, the idlest first.
        One that runs outside this process holds none, so it is never among them."""
        agora = time.monotonic()
        paradas = {n: agora - self._usado.get(n, self._desde) for n, m in self._modelos.items()
                   if m.loaded and not getattr(m, "externa", False)}
        return sorted((n for n, parada in paradas.items() if parada > ttl),
                      key=lambda n: -paradas[n])

    def recolher(self, ttl: float) -> list[str]:
        """Takes the models idle for longer than `ttl` seconds off the GPU, so that a card that
        holds them all does not keep them there for good: the driver gets the memory back, for the
        other programs on the machine. They leave as they do for a model that needs the room (to
        main memory, unless it has no room for them) and come back, in seconds, with their next
        call. Called with the GPU's queue held. Returns who left."""
        saiu = []
        for nome in self.inactivos(ttl):
            modelo = self._modelos[nome]
            falta = int(modelo.ram_ao_sair * MARGEM_RAM)
            disponivel = memoria_disponivel()
            if disponivel is not None and disponivel < falta:
                continue
            self._mover(nome, entra=False)
            saiu.append(nome)
        if saiu:
            devolver_cache()
            logger.info("parados há mais de %.0f s, saem da GPU: %s; GPU: %s", ttl,
                        ", ".join(saiu), resumo())
        return saiu

    def _mover(self, nome: str, entra: bool) -> None:
        modelo = self._modelos[nome]
        inicio = time.perf_counter()
        try:
            modelo.para_gpu() if entra else modelo.para_ram()
        except Exception:
            if entra:
                # A model left halfway would run with its weights on two devices: what went in
                # comes back.
                try:
                    modelo.para_ram()
                except Exception:  # noqa: BLE001 - the first failure is the one to report
                    logger.exception("%s ficou a meio caminho da GPU", nome)
            raise
        if entra:
            devolver_ram()
        logger.info("%s %s GPU em %.1f s (%s); GPU: %s", nome, "entrou na" if entra else "saiu da",
                    time.perf_counter() - inicio, gb(modelo.ocupa), resumo())
