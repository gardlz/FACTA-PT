"""Client of the inference service: question generation, relevance, entailment and the article."""

from __future__ import annotations

import httpx

from ..mensagens import Texto
from ..settings import Settings

# Seconds taken off the article timeout for the deadline sent to the service: the time it needs
# to stop generating, complete the article and send it back.
MARGEM_DO_ARTIGO = 120.0


class InferenceError(RuntimeError):
    """The inference service answered badly."""


class InferenceUnavailable(InferenceError):
    """The inference service is not answering, typically because it is not running."""


class InferenceTimeout(InferenceError):
    """The inference service took the request but did not answer in time. It is running, so the
    stage fails instead of being reported as unavailable."""


def _detalhe(resposta: httpx.Response) -> str:
    try:
        detalhe = resposta.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detalhe if isinstance(detalhe, str) else ""


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
        self, claim: str, claim_date: str, context: str, evidence: list[dict]
    ) -> dict:
        # The service is told how long it has, so that an article always comes back before this
        # client gives up: past the deadline it stops writing and completes what it has.
        prazo = max(60.0, self._settings.article_timeout - MARGEM_DO_ARTIGO)
        data = await self._post(
            "/v1/article",
            {"claim": claim, "claim_date": claim_date, "context": context, "evidence": evidence,
             "deadline_s": prazo},
            timeout=self._settings.article_timeout,
        )
        if not isinstance(data.get("article"), dict) or not isinstance(data.get("evidence"), list):
            raise InferenceError(Texto("resposta_sem_artigo"))
        return data

    async def probe(self) -> tuple[bool, str]:
        try:
            response = await self._client.get("/health", timeout=8.0)
            response.raise_for_status()
            body = response.json()
            loaded = [name for name, ok in body.get("models", {}).items() if ok]
            if not loaded:
                return False, "serviço acessível, sem modelos carregados"
            return True, "modelos: " + ", ".join(sorted(loaded))
        except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
            return False, "serviço de inferência inacessível"
