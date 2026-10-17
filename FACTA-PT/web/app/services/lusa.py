"""Async client of the LUSA search API: login, search and document retrieval.

Renews the access token on HTTP 401 and retries transient errors with exponential backoff;
timeouts are long, so that a slow answer does not fail the run. The API is reachable only over
the institutional VPN.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from ..mensagens import Texto
from ..settings import Settings

TRANSIENT_STATUS = {429, 500, 502, 503, 504}
TOKEN_STATUS = {401}
BACKOFF_INITIAL = 2.0
BACKOFF_MAX = 30.0


class LusaError(RuntimeError):
    """Error while talking to the LUSA API."""


class LusaConnectionError(LusaError):
    """The API did not answer, typically for lack of VPN."""


class LusaNotConfigured(LusaError):
    """Credentials missing from the environment."""


class LusaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=settings.lusa_api_url.rstrip("/") if settings.lusa_api_url else "",
            timeout=httpx.Timeout(settings.lusa_timeout, connect=30.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _require_config(self) -> None:
        if not self._settings.lusa_configured:
            raise LusaNotConfigured(Texto("lusa_sem_credenciais"))

    async def _fetch_token(self) -> str:
        self._require_config()
        payload = {"username": self._settings.lusa_user, "password": self._settings.lusa_password}
        try:
            response = await self._client.post(
                "/v1/login", json=payload, timeout=self._settings.lusa_login_timeout
            )
            response.raise_for_status()
            return response.json()["access_token"]
        except httpx.HTTPStatusError as error:
            raise LusaError(
                Texto("lusa_login_recusado", status=error.response.status_code)
            ) from error
        except (httpx.TransportError, httpx.TimeoutException) as error:
            raise LusaConnectionError(Texto("lusa_sem_vpn_erro", erro=repr(error))) from error
        except (json.JSONDecodeError, KeyError, ValueError) as error:
            raise LusaError(Texto("lusa_login_inesperado", erro=error)) from error

    async def _token_value(self) -> str:
        if self._token is None:
            async with self._lock:
                if self._token is None:
                    self._token = await self._fetch_token()
        return self._token

    async def _renew(self, expired: str | None) -> str:
        async with self._lock:
            if self._token == expired or self._token is None:
                self._token = await self._fetch_token()
            return self._token

    async def _get(self, path: str, params: dict) -> dict:
        delay = BACKOFF_INITIAL
        last_error: LusaError = LusaError(Texto("lusa_falha", caminho=path))
        for attempt in range(1, self._settings.lusa_retries + 1):
            token: str | None = None
            try:
                token = await self._token_value()
                response = await self._client.get(
                    path, params=params, headers={"Authorization": f"Bearer {token}"}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                last_error = LusaError(Texto("lusa_http", status=status, caminho=path))
                if status not in TOKEN_STATUS | TRANSIENT_STATUS:
                    raise last_error from error
                if status in TOKEN_STATUS:
                    try:
                        await self._renew(token)
                    except LusaError as login_error:
                        last_error = login_error
            except (httpx.TransportError, httpx.TimeoutException) as error:
                last_error = LusaConnectionError(Texto("lusa_sem_vpn_erro", erro=repr(error)))
            except (json.JSONDecodeError, ValueError) as error:
                last_error = LusaError(Texto("resposta_invalida", caminho=path, erro=error))
            except LusaNotConfigured:
                raise
            except LusaError as error:
                last_error = error
            if attempt == self._settings.lusa_retries:
                raise last_error
            await asyncio.sleep(delay)
            delay = min(delay * 2, BACKOFF_MAX)
        raise last_error

    async def search(self, query: str, size: int, date_to: str | None = None) -> dict:
        """Hybrid search (BM25 + semantic), up to `date_to` inclusive: the JSON with 'total' and
        'results'."""
        params: dict[str, object] = {"dataset": self._settings.lusa_dataset, "q": query, "size": size}
        if date_to:
            params["filters"] = json.dumps({"published_at": {"lte": date_to}})
        return await self._get("/v1/search", params)

    async def get_document(self, doc_id: str) -> dict:
        """Full document (metadata and 'content') by doc_id."""
        return await self._get(
            "/v1/get_document", {"dataset": self._settings.lusa_dataset, "id": doc_id}
        )

    async def probe(self) -> tuple[bool, str]:
        """Report whether the API is reachable, without raising."""
        if not self._settings.lusa_configured:
            return False, "credenciais por definir"
        try:
            await self._fetch_token()
            return True, "ligada"
        except LusaConnectionError:
            return False, str(Texto("lusa_sem_vpn"))
        except LusaError as error:
            return False, str(error)
