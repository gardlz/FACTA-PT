"""Client of the inference service: question generation, relevance, stance and the article."""

from __future__ import annotations

import logging

import httpx

from ..mensagens import Texto
from ..settings import Settings

logger = logging.getLogger(__name__)

# Seconds kept back from the article's timeout when telling the service its deadline: what it
# takes to stop a generation mid-token, complete the article and send it.
MARGEM_DO_ARTIGO = 120.0
# A model behind an API whose GPU scales to zero (Modal's), by the state of that GPU: being switched
# on by a request, or off until a run needs it. On, it is ready.
ESTADO_REMOTO = {"a_ligar": "loading", "desligado": "waiting"}


class InferenceError(RuntimeError):
    """The inference service answered badly."""


class InferenceUnavailable(InferenceError):
    """The inference service is not answering, typically because it is not running."""


class InferenceTimeout(InferenceError):
    """The inference service took the request and did not answer in time: it is working, not
    down, so this is a failure of the stage and not a model to wait for."""


def _detalhe(resposta: httpx.Response) -> str:
    try:
        detalhe = resposta.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detalhe if isinstance(detalhe, str) else ""


def estado_dos_modelos(corpo: dict, redator: str) -> list[dict]:
    """The models a run with this writer uses, from the inference service's /health: the three
    that every run needs and the one that writes its article, not the writers it will not use.
    Each is `ready` (loaded), `loading` (the service is still loading at startup), `waiting`
    (loads when a run needs it: it was taken off the GPU or takes its turn in memory) or `error`
    (refused to load, with the reason in `detail`). A model behind an API whose GPU scales to zero -
    the AMALIA models, on Modal - is `ready` while that GPU is on, `loading` while a request switches
    it on, and `waiting` while it is off (`remotos`, the service's estimate)."""
    carregados = corpo.get("models") or {}
    motivos = corpo.get("motivos") or {}
    em_espera = corpo.get("em_espera") or []
    remotos = corpo.get("remotos") or {}
    a_arrancar = corpo.get("status") == "a carregar"
    ids = ["questions", "relevance", "stance", f"article_{redator}"]
    modelos = []
    for nome in ids:
        detalhe = ""
        if carregados.get(nome):
            estado = ESTADO_REMOTO.get(remotos.get(nome), "ready")
        elif motivos.get(nome):
            estado, detalhe = "error", str(motivos[nome])
        elif a_arrancar and not nome.startswith("article_"):
            estado = "loading"
        else:
            estado = "waiting"
        modelos.append({"id": nome, "estado": estado, "detalhe": detalhe,
                        "na_gpu": nome in (corpo.get("gpu") or []),
                        "em_espera": nome in em_espera})
    return modelos


class InferenceClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.inference_url.rstrip("/"),
            timeout=httpx.Timeout(settings.inference_timeout, connect=15.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        prazo = httpx.Timeout(timeout, connect=15.0) if timeout else httpx.USE_CLIENT_DEFAULT
        try:
            response = await self._client.post(path, json=payload, timeout=prazo)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 503:
                # The service says why: still loading, or the reason it declined to load.
                raise InferenceUnavailable(
                    _detalhe(error.response)
                    or "o serviço de inferência está a correr, mas ainda sem o modelo carregado"
                ) from error
            detalhe = _detalhe(error.response)
            raise InferenceError(
                Texto("inferencia_erro", detalhe=detalhe) if detalhe
                else Texto("inferencia_http", status=error.response.status_code, caminho=path,
                           texto=error.response.text[:200])
            ) from error
        except httpx.ConnectTimeout as error:
            raise InferenceUnavailable(
                "o serviço de inferência não está a atender em "
                f"{self._settings.inference_url}"
            ) from error
        except httpx.TimeoutException as error:
            segundos = timeout or self._settings.inference_timeout
            raise InferenceTimeout(
                Texto("inferencia_sem_resposta", segundos=f"{segundos:.0f}")
            ) from error
        except httpx.TransportError as error:
            raise InferenceUnavailable(
                "o serviço de inferência não está a atender em "
                f"{self._settings.inference_url}"
            ) from error
        except ValueError as error:
            raise InferenceError(Texto("resposta_invalida", caminho=path, erro=error)) from error

    async def generate_questions(self, claim: str, claim_date: str, context: str) -> list[str]:
        data = await self._post(
            "/v1/questions",
            {"claim_span": claim, "publication_time": claim_date, "context": context},
        )
        questions = data.get("questions")
        if not isinstance(questions, list):
            raise InferenceError(Texto("resposta_sem_lista", campo="questions"))
        return [str(q).strip() for q in questions if str(q).strip()]

    async def relevance(self, claim: str, documents: list[dict]) -> list[dict]:
        data = await self._post("/v1/relevance", {"claim": claim, "documents": documents})
        results = data.get("results")
        if not isinstance(results, list):
            raise InferenceError(Texto("resposta_sem_lista", campo="results"))
        return results

    async def classify(self, claim: str, excerpts: list[dict]) -> list[dict]:
        data = await self._post("/v1/stance", {"claim": claim, "excerpts": excerpts})
        results = data.get("results")
        if not isinstance(results, list):
            raise InferenceError(Texto("resposta_sem_lista", campo="results"))
        return results

    async def write_article(
        self, claim: str, claim_date: str, context: str, evidence: list[dict], redator: str
    ) -> dict:
        # The service is told how long it has, so that an article always comes back before this
        # client gives up: past the deadline it stops writing and completes what it has.
        prazo = max(60.0, self._settings.article_timeout - MARGEM_DO_ARTIGO)
        data = await self._post(
            "/v1/article",
            {"claim": claim, "claim_date": claim_date, "context": context, "evidence": evidence,
             "redator": redator, "deadline_s": prazo},
            timeout=self._settings.article_timeout,
        )
        if not isinstance(data.get("article"), dict) or not isinstance(data.get("evidence"), list):
            raise InferenceError(Texto("resposta_sem_artigo"))
        return data

    async def modelos(self, redator: str) -> list[dict] | None:
        """The state of the models a run with this writer uses (`estado_dos_modelos`), or None
        when the service does not answer."""
        try:
            resposta = await self._client.get("/health", timeout=4.0)
            resposta.raise_for_status()
            return estado_dos_modelos(resposta.json(), redator)
        except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
            return None

    async def probe(self) -> tuple[bool, str]:
        try:
            response = await self._client.get("/health", timeout=8.0)
            response.raise_for_status()
            body = response.json()
            # The writers are not listed: which one a run uses is its own choice (`modelos`).
            loaded = [name for name, ok in body.get("models", {}).items()
                      if ok and not name.startswith("article_")]
            if not loaded:
                return False, "serviço acessível, sem modelos carregados"
            return True, "modelos: " + ", ".join(sorted(loaded))
        except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
            return False, "serviço de inferência inacessível"
