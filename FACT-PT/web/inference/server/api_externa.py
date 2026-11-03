"""The models that run outside this process, behind an OpenAI-compatible API (Modal, vLLM,
OpenRouter): where each request goes, and whether the server holds the model asked for. Of an API it
cannot use the service says only that it is unavailable; why goes to the log, without the API's
address.

A GPU that scales to zero - Modal's, behind the gateway of the AMALIA models - is off while nobody
asks it anything, and any request switches it on, the list of models included: it is not asked
whether it holds a model, and whether it is on is estimated from this service's own requests
(`estado`)."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

# What the service says of an API it cannot use.
INDISPONIVEL = "a API está indisponível"
# Endpoints an address may have been given with: the service adds its own.
ENDPOINTS = ("/chat/completions", "/completions", "/models")
# Hosts whose GPU scales to zero: Modal's web endpoints.
ESCALA_A_ZERO = (".modal.run",)
# Taken off the GPU's idle time when estimating whether it is still on: a model shown as ready
# must be.
MARGEM_LIGADA = 5.0


def endereco(url: str, caminho: str) -> str:
    """`caminho` (`models`, `completions`…) under the API's address, given with or without its
    `/v1`, or as one of its endpoints."""
    base = url.rstrip("/")
    for ponto in ENDPOINTS:
        if base.endswith(ponto):
            base = base[: -len(ponto)]
            break
    if not base.endswith("/v1"):
        base += "/v1"
    return f"{base}/{caminho}"


def indisponivel(motivo: str) -> str:
    """Logs why the API cannot be used, and returns what the service says of it."""
    logger.warning("API indisponível: %s", motivo)
    return INDISPONIVEL


def resposta_falhada(resposta: httpx.Response) -> str:
    """An answer that is not 200, as the log keeps it: the endpoint, the status, the server's text."""
    return (f"{resposta.request.url.path} respondeu {resposta.status_code}: "
            f"{resposta.text[:200]}")


def cabecalhos(chave: str) -> dict | None:
    """The headers of a request to an API that asks for a key."""
    return {"Authorization": f"Bearer {chave}"} if chave else None


def escala_a_zero(url: str) -> bool:
    """Whether the API's GPU is off while nobody asks it anything, and on with any request."""
    return (urlsplit(url).hostname or "").endswith(ESCALA_A_ZERO)


class _Ligacao:
    """What this service knows of a GPU that scales to zero: its requests under way, whether it was
    off when the first of them left, and when it last answered."""

    def __init__(self) -> None:
        self.trinco = threading.Lock()
        self.em_curso = 0
        self.a_frio = False
        self.respondido: float | None = None

    def ligada(self, inativa: float) -> bool:
        return (self.respondido is not None
                and time.monotonic() - self.respondido < inativa - MARGEM_LIGADA)


_ligacoes: dict[str, _Ligacao] = {}
_trinco = threading.Lock()


def _ligacao(url: str) -> _Ligacao:
    with _trinco:
        return _ligacoes.setdefault(urlsplit(url).netloc, _Ligacao())


@contextmanager
def pedido(url: str, inativa: float):
    """A request to the API, counted towards the state of its GPU when that GPU scales to zero: on
    from the moment the API answers - whatever it answers - until `inativa` seconds later."""
    if not escala_a_zero(url):
        yield
        return
    ligacao = _ligacao(url)
    with ligacao.trinco:
        if not ligacao.em_curso:
            ligacao.a_frio = not ligacao.ligada(inativa)
        ligacao.em_curso += 1
    respondeu = False
    try:
        yield
        respondeu = True
    finally:
        with ligacao.trinco:
            ligacao.em_curso -= 1
            if respondeu:
                ligacao.respondido = time.monotonic()
                ligacao.a_frio = False


def estado(url: str, inativa: float) -> str | None:
    """`ligado`, `a_ligar` or `desligado` for an API whose GPU scales to zero; None for one that is
    always on. Estimated from this service's own requests: a GPU that something else switched on
    shows as off until this service asks it something."""
    if not url or not escala_a_zero(url):
        return None
    ligacao = _ligacao(url)
    with ligacao.trinco:
        if ligacao.em_curso:
            return "a_ligar" if ligacao.a_frio else "ligado"
        return "ligado" if ligacao.ligada(inativa) else "desligado"


def chave_openrouter(url: str, chave: str) -> str:
    """Why OpenRouter would refuse a request made with this key - not taken, expired, or its
    spending limit, or a budget over it, spent - or "" when it would not. Asked of its `/key`,
    which describes the key and writes nothing: it costs no credits. The account's balance is not
    there (only a management key reads it): a request it cannot pay for is answered 402."""
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as cliente:
            resposta = cliente.get(endereco(url, "key"), headers=cabecalhos(chave))
    except httpx.HTTPError as erro:
        return indisponivel(f"OpenRouter: a API não responde ({erro.__class__.__name__})")
    if resposta.status_code != 200:
        return indisponivel(f"OpenRouter: a chave não foi aceite ({resposta_falhada(resposta)})")
    try:
        dados = resposta.json()["data"]
    except (ValueError, KeyError, TypeError):
        return indisponivel("OpenRouter: /key não respondeu com os dados da chave")
    restante = dados.get("limit_remaining")
    if restante is not None and restante <= 0:
        return indisponivel(f"OpenRouter: a chave gastou o seu limite ({dados.get('limit')} USD)")
    orcamento = dados.get("effective_budget") or {}
    if orcamento.get("remaining_usd") is not None and orcamento["remaining_usd"] <= 0:
        return indisponivel(f"OpenRouter: o orçamento da chave ({orcamento.get('scope')}) está gasto")
    expira = dados.get("expires_at")
    if expira and datetime.fromisoformat(expira.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        return indisponivel("OpenRouter: a chave expirou")
    return ""


def servido(url: str, modelo: str, chave: str = "") -> tuple[dict | None, str]:
    """The server's entry for `modelo` in /v1/models (vLLM's carries `max_model_len`, and `parent`
    for an adapter; OpenRouter's, `context_length` and `supported_parameters`), or why there is
    none. `chave`, the API's key, when it asks for one. Cheap and repeatable: a server started after
    this service is picked up when a request asks again."""
    if not url:
        return None, indisponivel(f"{modelo or 'o modelo'}: o endereço da API está por definir")
    if not modelo:
        return None, indisponivel("o nome do modelo na API está por definir")
    if escala_a_zero(url):
        # Asking would switch its GPU on: the model is taken as served, and a request that finds
        # otherwise says so.
        return {}, ""
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as cliente:
            resposta = cliente.get(endereco(url, "models"),
                                   headers={"Authorization": f"Bearer {chave}"} if chave else None)
    except httpx.InvalidURL:
        return None, indisponivel(f"{modelo}: o endereço da API não é válido")
    except httpx.HTTPError as erro:
        return None, indisponivel(f"{modelo}: a API não responde ({erro.__class__.__name__})")
    if resposta.status_code != 200:
        return None, indisponivel(f"{modelo}: {resposta_falhada(resposta)}")
    try:
        entradas = {m.get("id", ""): m for m in resposta.json().get("data", [])}
    except ValueError:
        return None, indisponivel(f"{modelo}: a API não respondeu com a lista de modelos")
    if modelo not in entradas:
        return None, indisponivel(f"o modelo {modelo!r} não está servido na API")
    return entradas[modelo], ""


def nome_do_modelo(modelo: str) -> str:
    """A model's name as the page shows it, from its id on the API:
    `google/gemma-4-26b-a4b-it:free` is "Gemma 4 26B A4B (free)"."""
    base, _, variante = modelo.partition(":")
    partes = [p for p in base.rsplit("/", 1)[-1].split("-") if p and p.lower() != "it"]
    nome = " ".join(p.upper() if any(c.isdigit() for c in p) else p.capitalize() for p in partes)
    return f"{nome} ({variante})" if variante else nome


def mesmo_servidor(url_a: str, url_b: str) -> bool:
    return bool(url_a and url_b) and endereco(url_a, "") == endereco(url_b, "")
