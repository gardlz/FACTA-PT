"""Inference service: question generation, news-item relevance, passage stance and the article,
written by the model the run chose."""

from __future__ import annotations

import asyncio
import gc
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .api_externa import estado as estado_remoto, nome_do_modelo
from .artigo.redator_api import ApiWriter
from .gpu import Partilha, devolver_cache, devolver_ram, driver_empresta, resumo
from .qg import QuestionGenerator, base_do_adaptador
from .relevance import RelevanceClassifier
from .settings import get_settings
from .stance import StanceClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger(__name__)
# The hub client logs every request of a download, one line per file.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Seconds between two looks at whether OpenRouter still takes the Gemma writer's key, while /health
# is asked: free, it writes nothing (`ApiWriter.verificar`).
VERIFICAR_CHAVES_S = 120.0


class Indisponivel(Exception):
    """The model asked for could not be brought into memory."""


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
    # The model that writes it: its writer is the service's `article_<redator>`.
    redator: str = "gemma"
    claim_date: date
    context: str = ""
    evidence: list[PassageIn] = Field(default_factory=list)
    # Seconds from now within which the article must be back, the wait in the queue included;
    # past them the service stops writing and completes what it has. None: no deadline.
    deadline_s: float | None = Field(default=None, gt=0)


async def _carregar(app: FastAPI) -> None:
    """Loads the models off the startup path: the service answers /health meanwhile. On a GPU
    they wait in main memory and go there when first asked for. A model behind an API is only
    asked whether it answers."""
    for nome, modelo in app.state.modelos.items():
        try:
            await asyncio.to_thread(modelo.load)
        except Exception as erro:
            logger.exception("falha ao carregar o modelo de %s", nome)
            app.state.falhas[nome] = f"falhou ao carregar: {erro}"
    app.state.pronto = True


async def _vigiar_inactividade(app: FastAPI, ttl_gpu: float, ttl_ram: float) -> None:
    """Takes the models idle for longer than `ttl_gpu` seconds off the GPU (`Partilha.recolher`)
    and lets go of those idle for longer than `ttl_ram` (`_soltar`); 0 skips that half. It looks
    without the queue, and takes a queue only when something is idle, so a busy service is never
    held up by it; the models are looked at again once it has the queue, since a call may have
    used one while it waited."""
    partilha = app.state.partilha
    while True:
        await asyncio.sleep(min(30.0, max(1.0, min(t for t in (ttl_gpu, ttl_ram) if t > 0) / 4)))
        if not app.state.pronto:
            continue
        try:
            if ttl_gpu > 0 and partilha.inactivos(ttl_gpu):
                async with app.state.gpu:
                    await asyncio.to_thread(partilha.recolher, ttl_gpu)
            if ttl_ram > 0:
                for nome in partilha.parados(ttl_ram):
                    async with _fila(nome):
                        if nome in partilha.parados(ttl_ram):
                            logger.info("%s parado há mais de %.0f s: sai da memória", nome, ttl_ram)
                            await asyncio.to_thread(_soltar, nome)
        except Exception:  # noqa: BLE001 - a failed sweep is tried again at the next one
            logger.exception("falha ao tirar os modelos parados da memória")


@asynccontextmanager
async def lifespan(app: FastAPI):
    definicoes = get_settings()
    app.state.modelos = {
        "relevance": RelevanceClassifier(definicoes),
        "stance": StanceClassifier(definicoes),
        "questions": QuestionGenerator(definicoes),
        "article_gemma": ApiWriter(
            definicoes, nome_do_modelo(definicoes.article_api_model), definicoes.article_api_url,
            definicoes.article_api_model,
            definicoes.article_api_key,
            tokenizador_de=lambda: (definicoes.article_api_tokenizer, ""), vllm=False),
        # AMALIA's tokenizer: the base the question generator's adapter was trained on.
        "article_amalia": ApiWriter(
            definicoes, "AMALIA-9B-0626-DPO", definicoes.amalia_api_url,
            definicoes.amalia_api_model,
            definicoes.amalia_api_key,
            tokenizador_de=lambda: base_do_adaptador(definicoes)[:2]),
    }
    # Where each model behind an API answers, and how long a GPU there that scales to zero (Modal's)
    # stays on after a request: /health says whether it is on.
    app.state.apis = {"questions": definicoes.qg_api_url, "article_gemma": definicoes.article_api_url,
                      "article_amalia": definicoes.amalia_api_url}
    app.state.inativa = definicoes.modal_gpu_idle_s
    app.state.chaves_vistas = 0.0
    app.state.verificacao = None
    app.state.falhas = {}
    app.state.pronto = False
    # The models let go of main memory for being idle (`_vigiar_inactividade`); each is loaded
    # again when its next call comes (`_recarregar`).
    app.state.despejados = set()
    # Models run off the event loop, so two requests could reach the device at once: the
    # lock queues them, since overlapping passes double peak memory and gain nothing. Whoever
    # holds it also moves the models in and out of the GPU (`gpu.py`).
    app.state.gpu = asyncio.Lock()
    # The articles have a queue of their own: written behind an API, they take minutes, and one
    # person's article must not hold back another person's classification.
    app.state.redacao = asyncio.Lock()
    # A model behind an API that is not a writer - the question generator - has a queue of its own:
    # one call at a time, and never behind an article.
    app.state.proprias = {nome: asyncio.Lock() for nome, modelo in app.state.modelos.items()
                          if getattr(modelo, "externa", False) and not nome.startswith("article_")}
    app.state.partilha = Partilha(app.state.modelos,
                                  empresta=driver_empresta(definicoes.gpu_lends_memory))
    carregamento = asyncio.create_task(_carregar(app))
    # The GPU's idle time only means something with a GPU.
    ttl_gpu = definicoes.gpu_idle_ttl_s if torch.cuda.is_available() else 0.0
    vigia = (asyncio.create_task(_vigiar_inactividade(app, ttl_gpu, definicoes.ram_idle_ttl_s))
             if ttl_gpu > 0 or definicoes.ram_idle_ttl_s > 0 else None)
    try:
        yield
    finally:
        carregamento.cancel()
        if vigia:
            vigia.cancel()


app = FastAPI(
    title="Serviço de inferência",
    description="Modelos da pipeline de verificação factual.",
    version="1.0.0",
    lifespan=lifespan,
)


def _modelo(nome: str):
    """The loaded model, or 503 saying why it is not available. One let go for being idle loads
    again in its call (`_recarregar`)."""
    modelo = app.state.modelos[nome]
    if modelo.loaded or (nome in app.state.despejados and app.state.pronto):
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
    # One let go for being idle loads again in its call (`_recarregar`), in the queue it runs in.
    if modelo.loaded or not app.state.pronto or nome in app.state.despejados:
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
    """The GPU's queue for the models that run here; for one behind an API, the article's queue,
    or a queue of its own when it is not a writer."""
    # A model that runs outside this process holds no memory here: it does not wait for the
    # models that do.
    if getattr(app.state.modelos[nome], "externa", False):
        return app.state.proprias.get(nome, app.state.redacao)
    return app.state.gpu


def _soltar(nome: str) -> None:
    """Lets a model idle for too long go - from the GPU and from main memory - and gives the memory
    back to the machine (`_vigiar_inactividade`). It is loaded again when its next call comes
    (`_recarregar`)."""
    cuda = torch.cuda.is_available()
    antes = resumo() if cuda else ""
    app.state.modelos[nome].descarregar()
    app.state.despejados.add(nome)
    gc.collect()
    devolver_ram()
    devolver_cache()
    logger.info("%s sai da memória: volta a carregar quando for preciso%s", nome,
                f". GPU antes: {antes}; depois: {resumo()}" if cuda else "")


def _recarregar(nome: str) -> None:
    """A model let go for being idle, back in memory for its call."""
    modelo = app.state.modelos[nome]
    if modelo.loaded:
        app.state.despejados.discard(nome)
        return
    gc.collect()
    devolver_ram()
    devolver_cache()
    inicio = time.perf_counter()
    try:
        modelo.load()
    except Exception as erro:
        logger.exception("falha ao carregar o modelo de %s", nome)
        raise Indisponivel(f"falhou ao carregar: {erro}") from erro
    if not modelo.loaded:
        raise Indisponivel(getattr(modelo, "motivo", "") or "modelo não carregado")
    app.state.despejados.discard(nome)
    logger.info("%s carregado de novo em %.0f s", nome, time.perf_counter() - inicio)


def _no_dispositivo(nome: str, funcao, *args):
    """Brings the model back into memory when it was let go, puts it on the GPU when it runs
    there, and runs it."""
    if nome in app.state.despejados:
        _recarregar(nome)
    app.state.partilha.preparar(nome)
    try:
        return funcao(*args)
    finally:
        # Idle from the end of the call, not from its start: an article takes minutes.
        app.state.partilha.usado(nome)


async def _correr(nome: str, request: Request, funcao, *args):
    """Runs a model off the event loop, one call at a time in its queue. A request whose client
    went away while it waited is dropped when its turn comes, before it moves any model."""
    async with _fila(nome):
        if await request.is_disconnected():
            logger.info("pedido de %s abandonado na fila", nome)
            raise HTTPException(status_code=499, detail="o pedido foi abandonado")
        try:
            return await asyncio.to_thread(_no_dispositivo, nome, funcao, *args)
        except Indisponivel as erro:
            raise HTTPException(status_code=503, detail=str(erro)) from erro
        except RuntimeError as erro:
            raise HTTPException(status_code=500, detail=str(erro)) from erro
        except Exception as erro:
            logger.exception("falha inesperada num modelo")
            raise HTTPException(status_code=500, detail=f"falha inesperada: {erro}") from erro


async def _verificar_chaves() -> None:
    """The writers behind a key, asked again whether it is taken, each in its queue: never while it
    writes an article."""
    for nome, modelo in app.state.modelos.items():
        if not hasattr(modelo, "verificar"):
            continue
        async with _fila(nome):
            try:
                await asyncio.to_thread(modelo.verificar)
            except Exception:  # noqa: BLE001 - the next look tries again
                logger.exception("falha ao verificar a chave de %s", nome)


@app.get("/health")
async def health() -> dict:
    if app.state.pronto and time.monotonic() - app.state.chaves_vistas > VERIFICAR_CHAVES_S:
        app.state.chaves_vistas = time.monotonic()
        app.state.verificacao = asyncio.create_task(_verificar_chaves())
    carregados = {nome: modelo.loaded for nome, modelo in app.state.modelos.items()}
    motivos = {
        nome: app.state.falhas.get(nome) or getattr(modelo, "motivo", "")
        for nome, modelo in app.state.modelos.items()
        if app.state.pronto and not modelo.loaded
    }
    # A model let go for being idle is waiting for its next call, not missing.
    em_espera = [nome for nome, motivo in motivos.items()
                 if nome in app.state.despejados and not motivo]
    for nome in em_espera:
        del motivos[nome]
    if not app.state.pronto:
        estado = "a carregar"
    else:
        estado = "ok" if not motivos else "degradado"
    # A model behind an API whose GPU scales to zero: whether that GPU is on (`ligado`), being
    # switched on by a request (`a_ligar`) or off (`desligado`), as this service last saw it.
    remotos = {nome: remoto for nome, url in app.state.apis.items()
               if (remoto := estado_remoto(url, app.state.inativa))}
    return {"status": estado, "models": carregados, "motivos": motivos, "em_espera": em_espera,
            "gpu": app.state.partilha.na_gpu(), "remotos": remotos}


@app.post("/v1/questions")
async def questions(pedido: QuestionRequest, request: Request) -> dict:
    await _carregar_a_pedido("questions", _fila("questions"))
    modelo = _modelo("questions")
    perguntas, bruto = await _correr(
        "questions", request, modelo.generate, pedido.claim_span, pedido.publication_time,
        pedido.context,
    )
    return {"questions": perguntas, "raw_output": bruto}


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
    """The article, its [En] -> passage map, and how it was written. No evidence is a case of
    its own (`no_evidence`), not an error."""
    prazo = time.monotonic() + pedido.deadline_s if pedido.deadline_s else None
    nome = f"article_{pedido.redator}"
    if nome not in app.state.modelos:
        raise HTTPException(status_code=503,
                            detail=f"este serviço não tem o modelo de redação «{pedido.redator}»")
    await _carregar_a_pedido(nome, app.state.redacao)
    modelo = _modelo(nome)
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
            nome, request, modelo.write, pedido.claim, pedido.claim_date.isoformat(),
            pedido.context, [p.model_dump() for p in pedido.evidence], cancelado, prazo,
        )
    finally:
        vigia.cancel()
