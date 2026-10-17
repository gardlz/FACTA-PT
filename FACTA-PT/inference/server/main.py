"""Inference service: question generation, news-item relevance, claim-passage entailment and the
article."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .artigo.redator import ArticleWriter
from .gpu import Partilha
from .qg import QuestionGenerator
from .relevance import RelevanceClassifier
from .settings import get_settings
from .stance import StanceClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger(__name__)


class QuestionRequest(BaseModel):
    claim_span: str = Field(min_length=1)
    publication_time: str = ""
    context: str = ""


class DocumentIn(BaseModel):
    doc_id: str
    headline: str = ""
    content: str = ""


class RelevanceRequest(BaseModel):
    claim: str = Field(min_length=1)
    documents: list[DocumentIn]


class ExcerptIn(BaseModel):
    id: str
    text: str


class StanceRequest(BaseModel):
    claim: str = Field(min_length=1)
    excerpts: list[ExcerptIn]


class PassageIn(BaseModel):
    """A consolidated passage: its text as it stands in the news item, and where."""

    id: str
    doc_id: str
    label: Literal["supported", "refuted", "nei"]
    text: str = Field(min_length=1)
    begin: int
    end: int
    headline: str = ""
    published_at: str = ""
    # Its place among the news item's passages: breaks ties in the evidence order.
    index: int = 0
    # What the passage is worth to the article (for a decisive one, how sure the classifier is
    # of its relation; for a nei one, how close it came to deciding): when the passages do not
    # all fit the prompt, the lowest leave first.
    priority: float = 0.0


class ArticleRequest(BaseModel):
    claim: str = Field(min_length=1)
    claim_date: date
    context: str = ""
    evidence: list[PassageIn] = Field(default_factory=list)
    # Seconds from now within which the article must be back, the wait in the queue included;
    # past them the service stops writing and completes what it has. None: no deadline.
    deadline_s: float | None = Field(default=None, gt=0)


async def _carregar(app: FastAPI) -> None:
    """Loads the models off the startup path: the service answers /health meanwhile. The
    encoders go first, since the decoder takes minutes. On a GPU only the question generator
    loads onto it; the others wait in main memory and go there when first asked for."""
    for nome, modelo in app.state.modelos.items():
        try:
            await asyncio.to_thread(modelo.load)
        except Exception as erro:
            logger.exception("falha ao carregar o modelo de %s", nome)
            app.state.falhas[nome] = f"falhou ao carregar: {erro}"
    app.state.pronto = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    definicoes = get_settings()
    app.state.modelos = {
        "relevance": RelevanceClassifier(definicoes),
        "stance": StanceClassifier(definicoes),
        "questions": QuestionGenerator(definicoes),
        "article": ArticleWriter(definicoes),
    }
    app.state.falhas = {}
    app.state.pronto = False
    # Models run off the event loop, so two requests could reach the device at once: the
    # lock queues them, since overlapping passes double peak memory and gain nothing. Whoever
    # holds it also moves the models in and out of the GPU (`gpu.py`).
    app.state.gpu = asyncio.Lock()
    # The article on the CPU has a queue of its own: there it takes minutes, and one person's
    # article must not hold back another person's questions. On the GPU it takes the GPU's queue,
    # since it needs the GPU to itself.
    app.state.redacao = asyncio.Lock()
    app.state.partilha = Partilha(app.state.modelos)
    carregamento = asyncio.create_task(_carregar(app))
    try:
        yield
    finally:
        carregamento.cancel()


app = FastAPI(
    title="Serviço de inferência",
    description="Modelos da pipeline de verificação factual.",
    version="1.0.0",
    lifespan=lifespan,
)


def _modelo(nome: str):
    """The loaded model, or 503 saying why it is not available."""
    modelo = app.state.modelos[nome]
    if modelo.loaded:
        return modelo
    if not app.state.pronto:
        detalhe = "o modelo ainda está a carregar"
    else:
        detalhe = app.state.falhas.get(nome) or getattr(modelo, "motivo", "") or "modelo não carregado"
    raise HTTPException(status_code=503, detail=detalhe)


async def _carregar_a_pedido(nome: str, fila: asyncio.Lock) -> None:
    """A model that did not load at startup is tried again when it is asked for, in its own
    queue: the memory it lacked then may be free now (on a shared machine, another program can
    hold it while the service starts). One try per request; still lacking, the call says why."""
    modelo = app.state.modelos[nome]
    if modelo.loaded or not app.state.pronto:
        return
    async with fila:
        if modelo.loaded:
            return
        try:
            await asyncio.to_thread(modelo.load)
        except Exception as erro:
            logger.exception("falha ao carregar o modelo de %s a pedido", nome)
            app.state.falhas[nome] = f"falhou ao carregar: {erro}"
            return
        # Loaded, or refused for a reason of now (`motivo`): an older failure no longer applies.
        app.state.falhas.pop(nome, None)
        if modelo.loaded:
            logger.info("modelo de %s carregado a pedido", nome)


def _fila(nome: str) -> asyncio.Lock:
    """The GPU's queue, or the article's own when the article runs on the CPU."""
    if nome == "article" and not app.state.modelos[nome].movel:
        return app.state.redacao
    return app.state.gpu


def _no_dispositivo(nome: str, funcao, *args):
    """Puts the model on the GPU, when it runs there, and runs it."""
    app.state.partilha.preparar(nome)
    return funcao(*args)


async def _correr(nome: str, request: Request, funcao, *args):
    """Runs a model off the event loop, one call at a time in its queue. A request whose client
    went away while it waited is dropped when its turn comes, before it moves any model."""
    async with _fila(nome):
        if await request.is_disconnected():
            logger.info("pedido de %s abandonado na fila", nome)
            raise HTTPException(status_code=499, detail="o pedido foi abandonado")
        try:
            return await asyncio.to_thread(_no_dispositivo, nome, funcao, *args)
        except RuntimeError as erro:
            raise HTTPException(status_code=500, detail=str(erro)) from erro
        except Exception as erro:
            logger.exception("falha inesperada num modelo")
            raise HTTPException(status_code=500, detail=f"falha inesperada: {erro}") from erro


@app.get("/health")
async def health() -> dict:
    carregados = {nome: modelo.loaded for nome, modelo in app.state.modelos.items()}
    if not app.state.pronto:
        estado = "a carregar"
    else:
        estado = "ok" if all(carregados.values()) else "degradado"
    motivos = {
        nome: app.state.falhas.get(nome) or getattr(modelo, "motivo", "")
        for nome, modelo in app.state.modelos.items()
        if app.state.pronto and not modelo.loaded
    }
    return {"status": estado, "models": carregados, "motivos": motivos}


@app.post("/v1/questions")
async def questions(pedido: QuestionRequest, request: Request) -> dict:
    modelo = _modelo("questions")
    perguntas = await _correr(
        "questions", request, modelo.generate, pedido.claim_span, pedido.publication_time,
        pedido.context,
    )
    return {"questions": perguntas}


@app.post("/v1/relevance")
async def relevance(pedido: RelevanceRequest, request: Request) -> dict:
    modelo = _modelo("relevance")
    if not pedido.documents:
        return {"results": []}
    resultados = await _correr(
        "relevance", request, modelo.classify, pedido.claim,
        [d.model_dump() for d in pedido.documents],
    )
    return {"results": resultados}


@app.post("/v1/stance")
async def stance(pedido: StanceRequest, request: Request) -> dict:
    modelo = _modelo("stance")
    if not pedido.excerpts:
        return {"results": []}
    resultados = await _correr(
        "stance", request, modelo.classify, pedido.claim,
        [e.model_dump() for e in pedido.excerpts],
    )
    return {"results": resultados}


@app.post("/v1/article")
async def article(pedido: ArticleRequest, request: Request) -> dict:
    """The article and its [En] -> passage map. No evidence is a case of its own
    (`no_evidence`), not an error."""
    prazo = time.monotonic() + pedido.deadline_s if pedido.deadline_s else None
    await _carregar_a_pedido("article", app.state.redacao)
    modelo = _modelo("article")
    cancelado = threading.Event()

    async def vigiar() -> None:
        # A client that timed out or went away can no longer be answered: stop writing for it,
        # waiting in the queue or mid-article, so the next one gets the model. A plain endpoint
        # is never told, so it is asked.
        while not cancelado.is_set():
            if await request.is_disconnected():
                logger.info("pedido de artigo abandonado: a geração pára")
                cancelado.set()
                return
            await asyncio.sleep(2)

    vigia = asyncio.create_task(vigiar())
    try:
        return await _correr(
            "article", request, modelo.write, pedido.claim, pedido.claim_date.isoformat(),
            pedido.context, [p.model_dump() for p in pedido.evidence], cancelado, prazo,
        )
    finally:
        vigia.cancel()
