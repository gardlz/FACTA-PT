"""HTTP routes: health, the example catalogue, pipeline runs and the documents of a run."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .demo.store import get_exemplos
from .mensagens import lingua_do_pedido, texto
from .pipeline.orchestrator import PipelineRunner
from .schemas import ClaimInput, HealthReport, RunResult
from .settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Seconds of silence after which the stream sends a keep-alive line, so that a proxy does not
# close the connection during a slow stage. Lines starting with ":" are SSE comments.
SINAL_DE_VIDA = 15.0
_FIM = object()


def _sse(evento: dict) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


@router.get("/health", response_model=HealthReport)
async def health(request: Request) -> HealthReport:
    lusa_ok, lusa_detalhe = await request.app.state.lusa.probe()
    inferencia_ok, inferencia_detalhe = await request.app.state.inference.probe()
    estado = "ok" if lusa_ok and inferencia_ok else "degraded"
    return HealthReport(
        status=estado,
        lusa={"available": lusa_ok, "detail": lusa_detalhe},
        inference={"available": inferencia_ok, "detail": inferencia_detalhe},
    )


@router.get("/exemplos")
async def exemplos() -> JSONResponse:
    """Example catalogue, without the news text. Sent with `no-cache`: it changes whenever the
    examples file is rebuilt."""
    return JSONResponse(
        {"topicos": get_exemplos().catalogo()}, headers={"Cache-Control": "no-cache"}
    )


@router.post("/run")
async def run(payload: ClaimInput, request: Request) -> StreamingResponse:
    definicoes = get_settings()
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    runner = PipelineRunner(
        definicoes, request.app.state.inference, request.app.state.lusa, get_exemplos(),
        lingua=lingua,
    )
    store = request.app.state.runs
    limitador = request.app.state.limitador

    # A run holds the inference service and the LUSA API from start to end, so runs are capped:
    # a request that cannot start within `run_queue_timeout` gets a 503. A stored example runs
    # no model, so it is never held back.
    com_modelos = not (payload.exemplo_id and get_exemplos().get(payload.exemplo_id))
    if com_modelos:
        try:
            await asyncio.wait_for(limitador.acquire(), timeout=definicoes.run_queue_timeout)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail=texto("ocupado", lingua),
            ) from None

    fila: asyncio.Queue = asyncio.Queue()

    async def correr() -> None:
        try:
            async for evento in runner.run(payload):
                await fila.put(evento)
        except Exception:
            logger.exception("falha inesperada na pipeline")
            await fila.put({"type": "error", "message": texto("erro_inesperado", lingua)})
        finally:
            await fila.put(_FIM)

    async def eventos() -> AsyncIterator[str]:
        # The run goes on in its own task, so the stream can send keep-alives during a silent
        # stage; when the page goes away, the run is cancelled.
        tarefa = asyncio.create_task(correr())
        try:
            while True:
                try:
                    evento = await asyncio.wait_for(fila.get(), timeout=SINAL_DE_VIDA)
                except asyncio.TimeoutError:
                    yield ": a trabalhar\n\n"
                    continue
                if evento is _FIM:
                    break
                if evento["type"] == "snapshot":
                    try:
                        store.put(RunResult.model_validate(evento["result"]))
                    except Exception:
                        logger.exception("falha ao guardar a execução a meio")
                    continue
                if evento["type"] in ("done", "error") and evento.get("result"):
                    try:
                        store.put(RunResult.model_validate(evento["result"]))
                        evento["result"] = _sem_conteudo(evento["result"])
                    except Exception:
                        logger.exception("falha inesperada ao guardar a execução")
                        evento = {"type": "error", "message": texto("erro_inesperado", lingua)}
                yield _sse(evento)
        finally:
            tarefa.cancel()
            if com_modelos:
                limitador.release()

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _sem_conteudo(resultado: dict) -> dict:
    """The result without the news and excerpt text, keeping ids and offsets. The page fetches a
    document's text from `/api/runs/{run_id}/documents/{doc_id}`, served from the run store."""
    aligeirado = dict(resultado)
    aligeirado["documents"] = [
        {
            **documento,
            "content": "",
            "excerpts": [{**e, "text": ""} for e in documento.get("excerpts", [])],
        }
        for documento in resultado.get("documents", [])
    ]
    return aligeirado


@router.get("/runs/{run_id}/documents/{doc_id}")
async def document(run_id: str, doc_id: str, request: Request) -> dict:
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = request.app.state.runs.get(run_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    for documento in resultado.documents:
        if documento.doc_id == doc_id:
            return {
                "doc_id": documento.doc_id,
                "headline": documento.headline,
                "published_at": documento.published_at,
                "genre": documento.genre,
                "byline": documento.byline,
                "word_count": documento.word_count,
                "content": documento.content,
            }
    raise HTTPException(status_code=404, detail=texto("noticia_ausente", lingua))
