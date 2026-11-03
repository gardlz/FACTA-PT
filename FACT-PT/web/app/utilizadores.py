"""Accounts: who may use the site, and in what role.

Two roles, each with a fixed ceiling of permissions (the matrix itself lives in `plataforma.py`):

- `jornalista` verifies, reads and edits the verification's editorial review.
- `administrador` also manages accounts, roles, permissions and platform settings.

The accounts are a JSON file on the data volume, written through `armazenamento` (atomic, `.bak`,
locked), so every process sees the same ones. Passwords are only ever stored as Argon2id hashes.

The first account is made at startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` (or, for a
deployment that still has only the old shared password, from `ACCESS_PASSWORD_HASH`). After that the
file is the source of truth; `python -m app.utilizadores` manages it from the command line.
"""

from __future__ import annotations

import getpass
import logging
import re
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel, Field, field_validator

from .armazenamento import FalhaAoGravar, actualizar_json, bloqueio, gravar_json, ler_json

logger = logging.getLogger(__name__)

PAPEIS: tuple[str, ...] = ("jornalista", "administrador")
PAPEL_OMISSAO = "jornalista"
# Long enough for any passphrase, short enough that hashing it costs nothing extra.
PALAVRA_PASSE_MINIMA = 12
PALAVRA_PASSE_MAXIMA = 512
UTILIZADOR_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")

_hasher = PasswordHasher()  # Argon2id, with the library's RFC 9106 parameters.

# A hash of nothing in particular, verified when there is no account so that the answer takes as
# long as a real check.
_FALSO = _hasher.hash(secrets.token_urlsafe(16))


def gerar_hash(palavra_passe: str) -> str:
    return _hasher.hash(palavra_passe)


def palavra_passe_certa(palavra_passe: str, hash_guardado: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, palavra_passe)
    except (VerificationError, InvalidHashError):
        return False


def hash_inutilizavel(hash_guardado: str) -> bool:
    return not hash_guardado.startswith("$argon2id$")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Utilizador(BaseModel):
    id: str
    utilizador: str
    nome: str = ""
    papel: str = PAPEL_OMISSAO
    palavra_passe_hash: str = ""
    activo: bool = True
    criado_em: str = ""
    actualizado_em: str = ""
    # Bumped on a password change or a deactivation: sessions carrying the old number are refused.
    versao_sessao: int = 1
    ultima_entrada: Optional[str] = None

    @field_validator("papel")
    @classmethod
    def _papel_previsto(cls, v: str) -> str:
        if v not in PAPEIS:
            raise ValueError(f"papel must be one of {', '.join(PAPEIS)}")
        return v

    @field_validator("utilizador")
    @classmethod
    def _nome_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if not UTILIZADOR_VALIDO.match(v):
            raise ValueError(
                "utilizador must be 3-40 characters: lowercase letters, digits, '.', '_' or '-'"
            )
        return v

    def publico(self) -> dict[str, Any]:
        """What the page may see: never the password hash."""
        return {
            "id": self.id,
            "utilizador": self.utilizador,
            "nome": self.nome,
            "papel": self.papel,
            "activo": self.activo,
            "criado_em": self.criado_em,
            "actualizado_em": self.actualizado_em,
            "ultima_entrada": self.ultima_entrada,
        }

    def resumo(self) -> dict[str, Any]:
        """Who did something, as a revision records it."""
        return {"id": self.id, "utilizador": self.utilizador, "nome": self.nome, "papel": self.papel}


def utilizador_local() -> Utilizador:
    """Who is asking when the gate is switched off on purpose (`ACCESS_GATE_DISABLED`): a local
    administrator, with no password to check."""
    return Utilizador(
        id="local",
        utilizador="local",
        nome="Local",
        papel="administrador",
        activo=True,
        criado_em=_agora(),
        actualizado_em=_agora(),
    )


class UtilizadoresMalConfigurados(RuntimeError):
    """No account can be made and there is none to sign in with."""


class UserStore:
    def __init__(self, caminho: str | Path) -> None:
        self._caminho = Path(caminho)

    @property
    def caminho(self) -> Path:
        return self._caminho

    # ---- Reading ------------------------------------------------------------------------------

    def _todos(self) -> list[Utilizador]:
        dados = ler_json(self._caminho) or {}
        utilizadores = []
        for registo in dados.get("utilizadores", []):
            try:
                utilizadores.append(Utilizador.model_validate(registo))
            except ValueError as erro:
                logger.error("conta inválida em %s: %s", self._caminho, erro)
        return utilizadores

    def listar(self) -> list[Utilizador]:
        return sorted(self._todos(), key=lambda u: (u.papel, u.utilizador))

    def por_nome(self, nome: str) -> Utilizador | None:
        nome = (nome or "").strip().lower()
        return next((u for u in self._todos() if u.utilizador == nome), None)

    def por_id(self, utilizador_id: str) -> Utilizador | None:
        return next((u for u in self._todos() if u.id == utilizador_id), None)

    def tem_utilizadores(self) -> bool:
        return bool(self._todos())

    # ---- Writing ------------------------------------------------------------------------------

    def _gravar(self, utilizadores: list[Utilizador]) -> None:
        if not gravar_json(self._caminho, {"utilizadores": [u.model_dump() for u in utilizadores]}):
            raise FalhaAoGravar(str(self._caminho))

    def criar(
        self,
        utilizador: str,
        palavra_passe: str,
        papel: str = PAPEL_OMISSAO,
        nome: str = "",
        activo: bool = True,
    ) -> Utilizador:
        """Adds an account. Raises `ValueError` for a repeated or invalid name, or a short
        password."""
        if len(palavra_passe) < PALAVRA_PASSE_MINIMA:
            raise ValueError(f"a palavra-passe tem de ter pelo menos {PALAVRA_PASSE_MINIMA} caracteres")
        if len(palavra_passe) > PALAVRA_PASSE_MAXIMA:
            raise ValueError(f"a palavra-passe tem no máximo {PALAVRA_PASSE_MAXIMA} caracteres")
        novo = Utilizador(
            id=uuid.uuid4().hex[:12],
            utilizador=utilizador,
            nome=nome.strip() or utilizador.strip().lower(),
            papel=papel,
            palavra_passe_hash=gerar_hash(palavra_passe),
            activo=activo,
            criado_em=_agora(),
            actualizado_em=_agora(),
        )

        def juntar(dados: dict[str, Any]) -> dict[str, Any]:
            existentes = [Utilizador.model_validate(r) for r in dados.get("utilizadores", [])]
            if any(u.utilizador == novo.utilizador for u in existentes):
                raise ValueError(f"já existe a conta «{novo.utilizador}»")
            existentes.append(novo)
            return {"utilizadores": [u.model_dump() for u in existentes]}

        actualizar_json(self._caminho, juntar, {"utilizadores": []})
        return novo

    def actualizar(self, utilizador_id: str, **campos: Any) -> Utilizador:
        """Changes an account's fields. A new password bumps `versao_sessao`; so does deactivating
        it. Raises `KeyError` when there is no such account."""
        resultado: dict[str, Any] = {}

        def mudar(dados: dict[str, Any]) -> dict[str, Any]:
            utilizadores = [Utilizador.model_validate(r) for r in dados.get("utilizadores", [])]
            alvo = next((u for u in utilizadores if u.id == utilizador_id), None)
            if alvo is None:
                raise KeyError(utilizador_id)
            novo = alvo.model_copy(deep=True)
            for campo in ("nome", "papel", "activo", "ultima_entrada"):
                if campo in campos and campos[campo] is not None:
                    setattr(novo, campo, campos[campo])
            if campos.get("palavra_passe"):
                palavra_passe = campos["palavra_passe"]
                if len(palavra_passe) < PALAVRA_PASSE_MINIMA:
                    raise ValueError(
                        f"a palavra-passe tem de ter pelo menos {PALAVRA_PASSE_MINIMA} caracteres"
                    )
                if len(palavra_passe) > PALAVRA_PASSE_MAXIMA:
                    raise ValueError(f"a palavra-passe tem no máximo {PALAVRA_PASSE_MAXIMA} caracteres")
                novo.palavra_passe_hash = gerar_hash(palavra_passe)
                novo.versao_sessao += 1
            if "activo" in campos and campos["activo"] is False and alvo.activo:
                novo.versao_sessao += 1
            novo.actualizado_em = _agora()
            resultado["utilizador"] = novo
            return {"utilizadores": [u.model_dump() for u in utilizadores if u.id != utilizador_id]
                    + [novo.model_dump()]}

        actualizar_json(self._caminho, mudar, {"utilizadores": []})
        return resultado["utilizador"]

    def apagar(self, utilizador_id: str) -> None:
        """Removes an account, which also ends its sessions: they name an id no longer here. Raises
        `KeyError` when there is no such account."""

        def retirar(dados: dict[str, Any]) -> dict[str, Any]:
            registos = dados.get("utilizadores", [])
            restantes = [r for r in registos if r.get("id") != utilizador_id]
            if len(restantes) == len(registos):
                raise KeyError(utilizador_id)
            return {"utilizadores": restantes}

        actualizar_json(self._caminho, retirar, {"utilizadores": []})

    def entrou(self, utilizador_id: str) -> None:
        """Records the last sign-in; a failure here never keeps anyone out."""
        try:
            self.actualizar(utilizador_id, ultima_entrada=_agora())
        except (KeyError, ValueError, OSError) as erro:
            logger.warning("não foi possível registar a entrada de %s: %s", utilizador_id, erro)

    def garantir_admin(self, definicoes) -> Utilizador | None:
        """Creates the first administrator when there is no account at all.

        `ADMIN_PASSWORD_HASH` is what a new deployment sets; `ACCESS_PASSWORD_HASH`, the old shared
        password, lets an existing one sign in once as `ADMIN_USERNAME` and make the real accounts.
        """
        if self.tem_utilizadores():
            return None
        hash_admin = definicoes.admin_password_hash or definicoes.access_password_hash
        if hash_inutilizavel(hash_admin):
            raise UtilizadoresMalConfigurados(
                "não há contas e falta ADMIN_PASSWORD_HASH (um hash Argon2id). "
                "Gere-a com: python -m app.acesso"
            )
        nome = definicoes.admin_username or "admin"
        admin = Utilizador(
            id=uuid.uuid4().hex[:12],
            utilizador=nome,
            nome="Administrador",
            papel="administrador",
            palavra_passe_hash=hash_admin,
            activo=True,
            criado_em=_agora(),
            actualizado_em=_agora(),
        )
        with bloqueio(self._caminho):
            if self.tem_utilizadores():
                return None
            self._gravar([admin])
        logger.info("conta de administrador criada: %s", admin.utilizador)
        return admin


# ---- Command line ----------------------------------------------------------------------------


def _pedir_palavra_passe() -> str:
    palavra_passe = getpass.getpass("Palavra-passe: ")
    if len(palavra_passe) < PALAVRA_PASSE_MINIMA:
        sys.exit(f"Use pelo menos {PALAVRA_PASSE_MINIMA} caracteres.")
    if getpass.getpass("Repita: ") != palavra_passe:
        sys.exit("As palavras-passe não coincidem.")
    return palavra_passe


def _principal() -> None:
    import argparse

    from .settings import get_settings

    parser = argparse.ArgumentParser(prog="python -m app.utilizadores", description=__doc__)
    parser.add_argument("--ficheiro", help="o ficheiro de contas (por omissão, o das definições)")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("listar", help="as contas existentes")
    criar = sub.add_parser("criar", help="uma conta nova")
    criar.add_argument("utilizador")
    criar.add_argument("--papel", choices=PAPEIS, default=PAPEL_OMISSAO)
    criar.add_argument("--nome", default="")
    repor = sub.add_parser("repor", help="mudar a palavra-passe (termina as sessões da conta)")
    repor.add_argument("utilizador")
    papel = sub.add_parser("papel", help="mudar o papel")
    papel.add_argument("utilizador")
    papel.add_argument("novo", choices=PAPEIS)
    activar = sub.add_parser("activar", help="voltar a deixar entrar a conta")
    activar.add_argument("utilizador")
    desactivar = sub.add_parser("desactivar", help="impedir a entrada e terminar as sessões")
    desactivar.add_argument("utilizador")

    argumentos = parser.parse_args()
    definicoes = get_settings()
    store = UserStore(argumentos.ficheiro or definicoes.utilizadores_path)

    if argumentos.comando == "listar":
        for u in store.listar():
            print(f"{u.utilizador:20} {u.papel:15} {'activa' if u.activo else 'inactiva':9} {u.nome}")
        return
    if argumentos.comando == "criar":
        novo = store.criar(argumentos.utilizador, _pedir_palavra_passe(), argumentos.papel, argumentos.nome)
        print(f"Conta criada: {novo.utilizador} ({novo.papel})")
        return
    if argumentos.comando == "repor":
        alvo = store.por_nome(argumentos.utilizador)
        if alvo is None:
            sys.exit(f"Não existe a conta «{argumentos.utilizador}».")
        store.actualizar(alvo.id, palavra_passe=_pedir_palavra_passe())
        print(f"Palavra-passe de {alvo.utilizador} mudada.")
        return
    if argumentos.comando == "papel":
        alvo = store.por_nome(argumentos.utilizador)
        if alvo is None:
            sys.exit(f"Não existe a conta «{argumentos.utilizador}».")
        store.actualizar(alvo.id, papel=argumentos.novo)
        print(f"{alvo.utilizador} é agora {argumentos.novo}.")
        return
    alvo = store.por_nome(argumentos.utilizador)
    if alvo is None:
        sys.exit(f"Não existe a conta «{argumentos.utilizador}».")
    store.actualizar(alvo.id, activo=argumentos.comando == "activar")
    print(f"{alvo.utilizador} {'activada' if argumentos.comando == 'activar' else 'desactivada'}.")


if __name__ == "__main__":
    _principal()
