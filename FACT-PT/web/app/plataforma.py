"""Platform settings: what each role may do, and the few defaults an administrator may change.

The matrix has two fixed ceilings and one editable row:

- `administrador` always has every permission, and cannot lose one.
- `jornalista` may be given any of the reader/editor permissions, and by default has them all.

`segundo_plano` lets a run go on with nobody watching it: its owner may leave the page, and find it
again under way. Without it, a run needs its page open, as it always did.

Nothing here is a secret: infrastructure (addresses, secrets, retention) stays in the environment.
What an administrator changes at runtime is the journalist's row and the defaults a new run starts
with (`top_k_omissao`, `redator_omissao`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, field_validator

from .armazenamento import actualizar_json, ler_json
from .schemas import REDATORES, REDATORES_ANTIGOS, TOP_K_OPCOES

logger = logging.getLogger(__name__)

PERMISSOES: tuple[str, ...] = (
    "verificar",
    "segundo_plano",
    "ver_resultados",
    "ver_historico",
    "editar_resultados",
    "gerir_utilizadores",
    "gerir_plataforma",
)

# What an administrator may give a journalist: the administration permissions never are.
PERMISSOES_EDITAVEIS: tuple[str, ...] = (
    "verificar",
    "segundo_plano",
    "ver_resultados",
    "ver_historico",
    "editar_resultados",
)

PERMISSOES_POR_PAPEL: dict[str, tuple[str, ...]] = {
    "jornalista": PERMISSOES_EDITAVEIS,
    "administrador": PERMISSOES,
}


class Definicoes(BaseModel):
    """The runtime choices an administrator may make."""

    top_k_omissao: int = 5
    redator_omissao: str = next(iter(REDATORES))

    @field_validator("top_k_omissao")
    @classmethod
    def _top_k_previsto(cls, v: int) -> int:
        if v not in TOP_K_OPCOES:
            raise ValueError(f"top_k_omissao must be one of {', '.join(map(str, TOP_K_OPCOES))}")
        return v

    @field_validator("redator_omissao")
    @classmethod
    def _redator_previsto(cls, v: str) -> str:
        # A default saved while that writer was offered falls back to the first one.
        if v in REDATORES_ANTIGOS:
            return next(iter(REDATORES))
        if v not in REDATORES:
            raise ValueError(f"redator_omissao must be one of {', '.join(REDATORES)}")
        return v


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _limpar_permissoes(valores: Iterable[str]) -> list[str]:
    """The valid, editable permissions in `valores`, without repeats, in the matrix's order."""
    escolhidas = {v for v in valores if v in PERMISSOES_EDITAVEIS}
    return [p for p in PERMISSOES_EDITAVEIS if p in escolhidas]


class PlatformStore:
    def __init__(self, caminho: str | Path) -> None:
        self._caminho = Path(caminho)

    @property
    def caminho(self) -> Path:
        return self._caminho

    def _lido(self) -> dict[str, Any]:
        return ler_json(self._caminho) or {}

    def estado(self) -> dict[str, Any]:
        """The file as the page reads it, with the defaults filled in and invalid values dropped."""
        lido = self._lido()
        permissoes = dict(PERMISSOES_POR_PAPEL)
        jornalista = (lido.get("permissoes") or {}).get("jornalista")
        if isinstance(jornalista, list):
            permissoes["jornalista"] = tuple(_limpar_permissoes(jornalista))
        try:
            definicoes = Definicoes.model_validate(lido.get("definicoes") or {})
        except ValueError as erro:
            logger.warning("definições da plataforma inválidas, a usar as de omissão: %s", erro)
            definicoes = Definicoes()
        return {
            "permissoes": {papel: list(valores) for papel, valores in permissoes.items()},
            "editaveis": list(PERMISSOES_EDITAVEIS),
            "todas": list(PERMISSOES),
            "definicoes": definicoes.model_dump(),
            "actualizado_em": lido.get("actualizado_em"),
            "actualizado_por": lido.get("actualizado_por"),
        }

    def permissoes(self, papel: str) -> list[str]:
        return list(self.estado()["permissoes"].get(papel, ()))

    def definicoes(self) -> Definicoes:
        return Definicoes.model_validate(self.estado()["definicoes"])

    def pode(self, utilizador, permissao: str) -> bool:
        if utilizador is None or not getattr(utilizador, "activo", False):
            return False
        return permissao in self.permissoes(utilizador.papel)

    def actualizar(
        self,
        permissoes_jornalista: Iterable[str] | None = None,
        definicoes: dict[str, Any] | None = None,
        autor: str = "",
    ) -> dict[str, Any]:
        """Changes the journalist's permissions and/or the runtime defaults. The invariants of the
        other roles are not editable, and an unknown value is refused by `Definicoes`."""
        novas = Definicoes.model_validate({**self.definicoes().model_dump(), **(definicoes or {})})
        if permissoes_jornalista is None:
            jornalista = self.permissoes("jornalista")
        else:
            jornalista = _limpar_permissoes(permissoes_jornalista)

        def mudar(dados: dict[str, Any]) -> dict[str, Any]:
            return {
                **dados,
                "permissoes": {"jornalista": jornalista},
                "definicoes": novas.model_dump(),
                "actualizado_em": _agora(),
                "actualizado_por": autor,
            }

        actualizar_json(self._caminho, mudar, {})
        return self.estado()
