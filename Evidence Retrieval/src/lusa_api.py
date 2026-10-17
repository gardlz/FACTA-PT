"""Client for the LUSA News Corpus search API: login, search and document retrieval.

Renews the access token on HTTP 401 and retries transient errors (429/5xx, timeouts, broken
connections, unreadable JSON) with exponential backoff. Credentials are read from a `.env`
file in the stage folder: API_URL_LUSA, USER_LUSA and PASSWORD_LUSA.
"""

import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent           # src/
REPO_ROOT = SCRIPT_DIR.parent                          # stage folder (.env)

load_dotenv(REPO_ROOT / ".env")

API_URL = os.getenv("API_URL_LUSA")
USERNAME = os.getenv("USER_LUSA")
PASSWORD = os.getenv("PASSWORD_LUSA")

# The server is slow to answer.
TIMEOUT_LOGIN = 60
TIMEOUT_PEDIDO = 120

CODIGOS_TRANSITORIOS = (429, 500, 502, 503, 504)
# Only 401 renews the token: a 403 is a permission error and a new token does not fix it.
CODIGOS_TOKEN = (401,)

BACKOFF_INICIAL = 2
BACKOFF_MAXIMO = 30

# URLError and TimeoutError are OSError; IncompleteRead comes from http.client and is not.
ERROS_DE_REDE = (OSError, http.client.HTTPException)
RESPOSTA_ILEGIVEL = (json.JSONDecodeError, UnicodeDecodeError)

SEM_VPN = "não foi possível ligar à API (confirmar a ligação à VPN)"


class LusaApiError(RuntimeError):
    """Error while talking to the API."""


class LusaConnectionError(LusaApiError):
    """The API did not answer (typically no VPN)."""


def require_config():
    """Fail early when the API credentials are missing from .env."""
    em_falta = [nome for nome, valor in (("API_URL_LUSA", API_URL),
                                         ("USER_LUSA", USERNAME),
                                         ("PASSWORD_LUSA", PASSWORD)) if not valor]
    if em_falta:
        raise LusaApiError(f"falta {', '.join(em_falta)} no .env em {REPO_ROOT}")


class LusaApi:
    """Authenticated client for one dataset of the API (default ``LUSA``)."""

    def __init__(self, dataset="LUSA", retries=4):
        self.dataset = dataset
        self.retries = max(1, retries)
        self._token = None
        self._lock = threading.Lock()                # the token is shared by the threads

    def login(self):
        """Request a new access token."""
        with self._lock:
            self._token = self._fetch_token()
        return self._token

    @property
    def token(self):
        return self._token or self.login()

    def _renew(self, expirado):
        """Renew the token after a 401, unless another thread already did."""
        with self._lock:
            if self._token == expirado:
                self._token = self._fetch_token()
            return self._token

    def _fetch_token(self):
        require_config()
        body = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
        request = urllib.request.Request(f"{API_URL}/v1/login", data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_LOGIN) as response:
                return json.load(response)["access_token"]
        except urllib.error.HTTPError as error:
            raise LusaApiError(f"login recusado pela API ({API_URL}): HTTP {error.code}") from error
        except ERROS_DE_REDE as error:
            raise LusaConnectionError(f"{SEM_VPN} ({API_URL}: {error!r})") from error
        except (*RESPOSTA_ILEGIVEL, KeyError) as error:
            raise LusaApiError(f"resposta inesperada do login ({API_URL}): {error}") from error

    def _get(self, path, params):
        """Authenticated GET with retries, backoff and token renewal (login included)."""
        url = f"{API_URL}{path}?{urllib.parse.urlencode(params)}"
        delay = BACKOFF_INICIAL
        for tentativa in range(1, self.retries + 1):
            token = None
            try:
                token = self.token
                request = urllib.request.Request(
                    url, headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(request, timeout=TIMEOUT_PEDIDO) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                ultimo_erro = LusaApiError(f"HTTP {error.code} em {path}")
                if error.code not in CODIGOS_TOKEN + CODIGOS_TRANSITORIOS:
                    raise ultimo_erro from error
                if error.code in CODIGOS_TOKEN:
                    try:
                        self._renew(token)
                    except LusaApiError as erro_login:
                        ultimo_erro = erro_login
            except LusaApiError as error:            # the token request failed
                ultimo_erro = error
            except ERROS_DE_REDE as error:
                ultimo_erro = LusaConnectionError(f"{SEM_VPN} ({API_URL}: {error!r})")
            except RESPOSTA_ILEGIVEL as error:
                ultimo_erro = LusaApiError(f"resposta inválida em {path}: {error}")
            if tentativa == self.retries:
                raise ultimo_erro
            time.sleep(delay)
            delay = min(delay * 2, BACKOFF_MAXIMO)

    def search(self, query, size, date_to):
        """Hybrid search over the documents published up to `date_to`.

        Returns the JSON with 'total' and 'results'.
        """
        params = {"dataset": self.dataset, "q": query, "size": size,
                  "filters": json.dumps({"published_at": {"lte": date_to}})}
        return self._get("/v1/search", params)

    def get_document(self, doc_id):
        """Full document (metadata and 'content') for a doc_id."""
        return self._get("/v1/get_document", {"dataset": self.dataset, "id": doc_id})
