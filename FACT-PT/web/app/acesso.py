"""Sign-in: an account per person, with a role, and a session cookie.

Everything under `/api` except the session route needs a valid session, so the data is never sent
to someone who has not signed in; the interface's files carry nothing private and stay public (they
hold the sign-in page itself).

- Accounts live in `utilizadores.py`; passwords are only ever stored as Argon2id hashes.
- A session is a signed, expiring token in an HttpOnly, Secure, SameSite=Strict cookie. It is
  stateless, so every worker accepts it, and carries the account's id and the number of its
  session generation: changing a password or deactivating an account bumps that number and ends
  its sessions, without touching anyone else's.
- The role's permissions are read on every request (`plataforma.py`), so a change of role or
  permission applies at once.
- Wrong credentials are throttled per client address and over all addresses.
- Requests that change something must come from this site (`Origin` check), on top of SameSite.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .mensagens import lingua_do_pedido, texto
from .settings import Settings, get_settings
from .utilizadores import (
    PALAVRA_PASSE_MAXIMA,
    UTILIZADOR_VALIDO,
    Utilizador,
    UserStore,
    gerar_hash,
    hash_inutilizavel,
    palavra_passe_certa,
    utilizador_local,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AcessoMalConfigurado",
    "Limitador",
    "criar_sessao",
    "endereco",
    "entrar",
    "estado",
    "exigir_permissao",
    "exigir_sessao",
    "gerar_hash",
    "palavra_passe_certa",
    "quem",
    "router",
    "sair",
    "sessao_valida",
    "utilizador_atual",
    "validar_configuracao",
    "verificar_origem",
]

VERSAO = "v2"
SEGREDO_MINIMO = 32

# A hash of nothing in particular, verified when there is no account so that the answer takes as
# long as a real check.
_FALSO = gerar_hash(secrets.token_urlsafe(16))


class AcessoMalConfigurado(RuntimeError):
    """The gate is on but cannot work: starting anyway would leave the site open or locked."""


def validar_configuracao(definicoes: Settings, utilizadores: UserStore | None = None) -> None:
    """Raise `AcessoMalConfigurado` unless the gate is configured, or off on purpose."""
    if definicoes.access_gate_disabled:
        logger.warning("ACCESS_GATE_DISABLED: o acesso NÃO está protegido por contas")
        return
    if len(definicoes.session_secret) < SEGREDO_MINIMO:
        raise AcessoMalConfigurado(
            f"SESSION_SECRET em falta ou com menos de {SEGREDO_MINIMO} caracteres. "
            "Gere-o com: python -m app.acesso"
        )
    if not UTILIZADOR_VALIDO.match(definicoes.admin_username or ""):
        raise AcessoMalConfigurado(
            "ADMIN_USERNAME inválido: 3 a 40 caracteres, letras minúsculas, dígitos, '.', '_' ou '-'."
        )
    # With accounts already made, the bootstrap hash has done its work and may be gone.
    if utilizadores is not None and utilizadores.tem_utilizadores():
        return
    hash_admin = definicoes.admin_password_hash or definicoes.access_password_hash
    if hash_inutilizavel(hash_admin):
        raise AcessoMalConfigurado(
            "ADMIN_PASSWORD_HASH em falta ou inválida (tem de ser um hash Argon2id). "
            "Gere-a com: python -m app.acesso"
        )


# ---- Session token --------------------------------------------------------------------------


def _chave(definicoes: Settings) -> bytes:
    return hmac.digest(definicoes.session_secret.encode(), b"facta-pt:sessao:v2", "sha256")


def _assinar(carga: str, definicoes: Settings) -> str:
    assinatura = hmac.digest(_chave(definicoes), carga.encode(), "sha256")
    return base64.urlsafe_b64encode(assinatura).rstrip(b"=").decode()


def criar_sessao(definicoes: Settings, utilizador: Utilizador, agora: float | None = None) -> str:
    """A token for `utilizador`, valid for `SESSION_HOURS`."""
    validade = int((agora if agora is not None else time.time()) + definicoes.session_hours * 3600)
    carga = (f"{VERSAO}.{validade}.{utilizador.id}.{utilizador.versao_sessao}."
             f"{secrets.token_urlsafe(16)}")
    return f"{carga}.{_assinar(carga, definicoes)}"


def _partes(token: str | None, definicoes: Settings, agora: float | None = None) -> dict | None:
    """The token's fields, when its signature and expiry are good: `id`, `versao`, `aleatorio`."""
    if not token:
        return None
    carga, _, assinatura = token.rpartition(".")
    partes = carga.split(".")
    if len(partes) != 5 or partes[0] != VERSAO:
        return None
    if not hmac.compare_digest(assinatura.encode(), _assinar(carga, definicoes).encode()):
        return None
    try:
        validade = int(partes[1])
        versao = int(partes[3])
    except ValueError:
        return None
    if validade <= (agora if agora is not None else time.time()):
        return None
    return {"id": partes[2], "versao": versao, "aleatorio": partes[4]}


def sessao_valida(token: str | None, definicoes: Settings, agora: float | None = None) -> bool:
    """Whether the token is this site's and has not expired. Who it is for is `utilizador_atual`."""
    return _partes(token, definicoes, agora) is not None


def _utilizador_do_pedido(request: Request, definicoes: Settings) -> Utilizador | None:
    if definicoes.access_gate_disabled:
        return utilizador_local()
    partes = _partes(request.cookies.get(_nome_do_cookie(definicoes)), definicoes)
    if partes is None:
        return None
    store: UserStore | None = getattr(request.app.state, "utilizadores", None)
    if store is None:
        return None
    utilizador = store.por_id(partes["id"])
    if utilizador is None or not utilizador.activo or utilizador.versao_sessao != partes["versao"]:
        return None
    return utilizador


def utilizador_atual(request: Request) -> Utilizador:
    """Dependency of every protected route: who is asking."""
    utilizador = _utilizador_do_pedido(request, get_settings())
    if utilizador is None:
        lingua = lingua_do_pedido(request.headers.get("accept-language"))
        raise HTTPException(status_code=401, detail=texto("sem_sessao", lingua))
    return utilizador


# Kept for the routes that only need the check.
exigir_sessao = utilizador_atual


def exigir_permissao(permissao: str):
    """A dependency that also requires `permissao` of the signed-in account's role."""

    def dependencia(request: Request, utilizador: Utilizador = Depends(utilizador_atual)) -> Utilizador:
        plataforma = getattr(request.app.state, "plataforma", None)
        if plataforma is None or not plataforma.pode(utilizador, permissao):
            lingua = lingua_do_pedido(request.headers.get("accept-language"))
            raise HTTPException(status_code=403, detail=texto("sem_permissao", lingua))
        return utilizador

    return dependencia


def quem(request: Request) -> str:
    """Who is asking, for the queue's limits and a run's owner: the session - a digest of its
    random part, so the token itself is never stored - or, without one (the gate switched off),
    the client address."""
    definicoes = get_settings()
    partes = _partes(request.cookies.get(_nome_do_cookie(definicoes)), definicoes)
    if partes is not None:
        return hashlib.sha256(partes["aleatorio"].encode()).hexdigest()[:12]
    return "endereco:" + _endereco(request)


def _nome_do_cookie(definicoes: Settings) -> str:
    # `__Host-` makes the browser refuse the cookie unless it is Secure, set for this exact
    # host and for the whole site: no sibling subdomain can plant or overwrite it.
    return "__Host-facta_sessao" if definicoes.cookie_secure else "facta_sessao"


# ---- Throttling -----------------------------------------------------------------------------


class Limitador:
    """Failed sign-ins in a sliding window, per client address and overall. In memory, so each
    worker counts on its own."""

    MAX_ENDERECOS = 10_000

    def __init__(self) -> None:
        self._por_endereco: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()

    @staticmethod
    def _podar(falhas: deque[float], limite: float) -> None:
        while falhas and falhas[0] <= limite:
            falhas.popleft()

    def espera(self, endereco: str, definicoes: Settings, agora: float | None = None) -> int:
        """Seconds until `endereco` may try again; 0 when it may now."""
        agora = agora if agora is not None else time.monotonic()
        limite = agora - definicoes.login_window
        espera = 0.0
        falhas = self._por_endereco.get(endereco)
        if falhas is not None:
            self._podar(falhas, limite)
            if not falhas:
                del self._por_endereco[endereco]
            elif len(falhas) >= definicoes.login_max_failures:
                espera = falhas[0] + definicoes.login_window - agora
        self._podar(self._global, limite)
        if len(self._global) >= definicoes.login_max_failures_global:
            espera = max(espera, self._global[0] + definicoes.login_window - agora)
        return int(espera) + 1 if espera > 0 else 0

    def falhou(self, endereco: str, agora: float | None = None) -> None:
        agora = agora if agora is not None else time.monotonic()
        if endereco not in self._por_endereco and len(self._por_endereco) >= self.MAX_ENDERECOS:
            # Memory guard: drop the address that has been quiet the longest.
            mais_antigo = min(self._por_endereco, key=lambda e: self._por_endereco[e][-1])
            del self._por_endereco[mais_antigo]
        self._por_endereco.setdefault(endereco, deque()).append(agora)
        self._global.append(agora)

    def limpar(self, endereco: str) -> None:
        self._por_endereco.pop(endereco, None)


_limitador = Limitador()


# ---- Routes ---------------------------------------------------------------------------------


def verificar_origem(request: Request) -> None:
    """Refuse a request that changes something when the browser says it comes from another site.

    `SameSite=Strict` already keeps the cookie off such requests; this is the second lock. A
    request with no `Origin` (not a browser form or fetch) is let through: it has no cookie of
    the victim's to abuse.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origem = request.headers.get("origin")
    if not origem:
        return
    permitidas = {urlsplit(o).netloc for o in get_settings().allowed_origins}
    anfitrioes = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")}
    if urlsplit(origem).netloc not in permitidas | (anfitrioes - {""}):
        lingua = lingua_do_pedido(request.headers.get("accept-language"))
        raise HTTPException(status_code=403, detail=texto("origem_invalida", lingua))


router = APIRouter(prefix="/api/sessao", dependencies=[Depends(verificar_origem)])

SEM_ARMAZENAR = {"Cache-Control": "no-store"}


class Entrada(BaseModel):
    utilizador: str = Field(min_length=1, max_length=40)
    palavra_passe: str = Field(max_length=PALAVRA_PASSE_MAXIMA)


def _endereco(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def endereco(request: Request) -> str:
    """The client address: behind a proxy, the one it passes on (uvicorn's `--proxy-headers`)."""
    return _endereco(request)


def _sessao_publica(request: Request, definicoes: Settings) -> dict:
    utilizador = _utilizador_do_pedido(request, definicoes)
    if utilizador is None:
        return {"autenticada": False, "protegido": not definicoes.access_gate_disabled,
                "utilizador": None, "permissoes": []}
    plataforma = getattr(request.app.state, "plataforma", None)
    return {
        "autenticada": True,
        "protegido": not definicoes.access_gate_disabled,
        "utilizador": utilizador.publico(),
        "permissoes": plataforma.permissoes(utilizador.papel) if plataforma else [],
    }


@router.get("")
async def estado(request: Request) -> JSONResponse:
    """Whether this browser has a session, and whose. Always 200, so the page (and the container
    health check) can ask without being refused."""
    return JSONResponse(_sessao_publica(request, get_settings()), headers=SEM_ARMAZENAR)


# A plain `def`: the Argon2 check is CPU work and runs in the thread pool, not on the event loop.
@router.post("", status_code=204)
def entrar(corpo: Entrada, request: Request) -> Response:
    definicoes = get_settings()
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    endereco = _endereco(request)

    espera = _limitador.espera(endereco, definicoes)
    if espera:
        raise HTTPException(
            status_code=429,
            detail=texto("demasiadas_tentativas", lingua),
            headers={**SEM_ARMAZENAR, "Retry-After": str(espera)},
        )

    store: UserStore = request.app.state.utilizadores
    utilizador = store.por_nome(corpo.utilizador)
    # Checked even when there is no such account, so timing says nothing about it.
    hash_guardado = (utilizador.palavra_passe_hash
                     if utilizador is not None and not hash_inutilizavel(utilizador.palavra_passe_hash)
                     else _FALSO)
    certa = palavra_passe_certa(corpo.palavra_passe, hash_guardado)
    if utilizador is None or not utilizador.activo or not certa:
        _limitador.falhou(endereco)
        logger.warning("entrada recusada para %r de %s", corpo.utilizador[:40], endereco)
        raise HTTPException(
            status_code=401, detail=texto("credenciais_invalidas", lingua), headers=SEM_ARMAZENAR
        )

    _limitador.limpar(endereco)
    store.entrou(utilizador.id)
    resposta = Response(status_code=204, headers=SEM_ARMAZENAR)
    resposta.set_cookie(
        _nome_do_cookie(definicoes),
        criar_sessao(definicoes, utilizador),
        max_age=definicoes.session_hours * 3600,
        path="/",
        secure=definicoes.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return resposta


@router.delete("", status_code=204)
async def sair() -> Response:
    definicoes = get_settings()
    resposta = Response(status_code=204, headers=SEM_ARMAZENAR)
    resposta.delete_cookie(
        _nome_do_cookie(definicoes),
        path="/",
        secure=definicoes.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return resposta


# ---- Command line: make the values to put in the environment -------------------------------


def _principal() -> None:
    import getpass
    import sys

    palavra_passe = getpass.getpass("Palavra-passe do administrador: ")
    if len(palavra_passe) < 12:
        sys.exit("Use pelo menos 12 caracteres (de preferência uma frase com várias palavras).")
    if len(palavra_passe) > PALAVRA_PASSE_MAXIMA:
        sys.exit(f"No máximo {PALAVRA_PASSE_MAXIMA} caracteres.")
    if getpass.getpass("Repita: ") != palavra_passe:
        sys.exit("As palavras-passe não coincidem.")
    # Single quotes: the hash holds `$`, which Docker Compose would otherwise expand in a .env.
    print("\nAcrescente ao .env (o ficheiro não vai para o git):\n")
    print(f"ADMIN_PASSWORD_HASH='{gerar_hash(palavra_passe)}'")
    print(f"SESSION_SECRET='{secrets.token_urlsafe(48)}'")


if __name__ == "__main__":
    _principal()
