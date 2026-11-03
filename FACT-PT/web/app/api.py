"""HTTP routes: system health, demo cases, pipeline runs and documents."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from .acesso import (
    endereco, exigir_permissao, exigir_sessao, quem, utilizador_atual, verificar_origem,
)
from .armazenamento import FalhaAoGravar
from .demo.store import get_exemplos
from . import guardadas
from .fila import correr
from .mensagens import lingua_do_pedido, texto
from .pipeline.orchestrator import PipelineRunner
from .revisao import (
    ACCOES_ANTIGAS, Autor, Conflito, ErroRevisao, PedidoArtigo, RevisaoEstado, agora,
    artigos_da_evidencia, expandir, passagens_revistas,
)
from .runstore import RUN_ID_VALIDO
from .schemas import REDATORES, TOP_K_OPCOES, ClaimInput, HealthReport, RunResult
from .settings import get_settings
from .utilizadores import Utilizador

logger = logging.getLogger(__name__)
# Every route here needs a signed-in session (see `acesso.py`).
router = APIRouter(prefix="/api", dependencies=[Depends(exigir_sessao), Depends(verificar_origem)])

# A Redis stream id, the number of the last event a page saw.
ID_DO_EVENTO = re.compile(r"^\d+(-\d+)?$")
# The runs this process plays back itself (worked examples): asyncio keeps only weak references.
_EM_CURSO: set[asyncio.Task] = set()


def lancar(corrotina) -> asyncio.Task:
    tarefa = asyncio.create_task(corrotina)
    _EM_CURSO.add(tarefa)
    tarefa.add_done_callback(_EM_CURSO.discard)
    return tarefa


# Headers of an event stream: no caching, and no buffering by a proxy in front.
CABECALHOS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


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


@router.get("/modelos")
async def modelos(request: Request, redator: str = "") -> JSONResponse:
    """What the models a run uses are doing, for the dots on the page's bar: the three every run
    needs and the writer chosen (`redator`; the platform's default when it is not one on offer).
    `disponivel` is false when the inference service does not answer."""
    definicoes = get_settings()
    if redator not in definicoes.redatores:
        omissao = request.app.state.plataforma.definicoes().redator_omissao
        redator = omissao if omissao in definicoes.redatores else definicoes.redatores[0]
    estados = await request.app.state.inference.modelos(redator)
    return JSONResponse({"disponivel": estados is not None, "modelos": estados or []},
                        headers={"Cache-Control": "no-store"})


@router.get("/exemplos")
async def exemplos(request: Request) -> JSONResponse:
    """Example catalogue, without the news text, and what a run can choose: the number of news
    items per question and the model that writes the article. The defaults are the platform's, so
    an administrator can change them without a restart. Not cached: it changes when the dataset is
    rebuilt."""
    definicoes = get_settings()
    plataforma = request.app.state.plataforma.definicoes()
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    return JSONResponse(
        {
            "exemplos": get_exemplos().catalogo(lingua),
            "top_k": {"opcoes": list(TOP_K_OPCOES), "omissao": plataforma.top_k_omissao},
            "redatores": {
                "opcoes": [{"id": chave, "nome": REDATORES[chave]}
                           for chave in definicoes.redatores],
                "omissao": plataforma.redator_omissao
                if plataforma.redator_omissao in definicoes.redatores
                else definicoes.redatores[0],
            },
        },
        headers={"Cache-Control": "no-cache"},
    )


async def pedir_na_fila(request: Request, payload: ClaimInput, lingua: str, run_id: str,
                        limite: int, conta: str | None) -> None:
    """Puts a run in the queue, or refuses it with the reason the page shows."""
    definicoes = get_settings()
    recusa = await request.app.state.fila.por_na_fila(
        payload, lingua, run_id, quem(request), endereco(request), limite_sessao=limite, conta=conta)
    if recusa == "fila":
        raise HTTPException(status_code=503, detail=texto("ocupado", lingua))
    if recusa == "sessao":
        raise HTTPException(status_code=429, detail=texto("demasiadas_execucoes", lingua, n=limite))
    if recusa == "endereco":
        raise HTTPException(status_code=429, detail=texto(
            "demasiadas_execucoes_endereco", lingua, n=definicoes.runs_per_address))


@router.post("/run")
async def run(payload: ClaimInput, request: Request,
              utilizador: Utilizador = Depends(exigir_permissao("verificar"))) -> StreamingResponse:
    definicoes = get_settings()
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    plataforma = request.app.state.plataforma
    runner = PipelineRunner(
        definicoes, request.app.state.inference, request.app.state.lusa, get_exemplos(),
        lingua=lingua,
    )
    fila = request.app.state.fila
    run_id = uuid.uuid4().hex[:12]

    if runner.exemplo(payload) is None:
        if "redator" not in payload.model_fields_set:
            escolhido = plataforma.definicoes().redator_omissao
            payload.redator = escolhido if escolhido in definicoes.redatores else definicoes.redatores[0]
        elif payload.redator not in definicoes.redatores:
            raise HTTPException(
                status_code=422,
                detail=f"redator must be one of {', '.join(definicoes.redatores)}",
            )
        if "top_k" not in payload.model_fields_set:
            payload.top_k = plataforma.definicoes().top_k_omissao
        # The models run one run at a time, in the worker: the run waits its turn in the queue.
        # With `segundo_plano`, the run is the account's and goes on with nobody watching.
        conta = utilizador.id if plataforma.pode(utilizador, "segundo_plano") else None
        await pedir_na_fila(request, payload, lingua, run_id, definicoes.runs_per_session, conta)
    else:
        # A worked example runs no model and skips the queue: played back here, at once.
        await fila.visto(run_id)
        await fila.dono(run_id, quem(request))
        lancar(correr(definicoes, fila.redis, runner, request.app.state.runs, payload, lingua,
                      run_id))
    return StreamingResponse(fila.ler(run_id, lingua), media_type="text/event-stream",
                             headers=CABECALHOS_SSE)


@router.get("/execucoes")
async def execucoes(request: Request,
                    utilizador: Utilizador = Depends(exigir_permissao("segundo_plano"))) -> JSONResponse:
    """The account's runs in the background of the last day: waiting, under way or over, each
    one to open again."""
    lista = await request.app.state.fila.execucoes(utilizador.id)
    runs = request.app.state.runs
    for execucao in lista:
        execucao["guardada"] = execucao["estado"] == "terminada" \
            and runs.guardada(execucao["run_id"]) is not None
    return JSONResponse({"execucoes": lista}, headers={"Cache-Control": "no-store"})


@router.post("/execucoes/{run_id}/reiniciar")
async def reiniciar(run_id: str, request: Request,
                    utilizador: Utilizador = Depends(exigir_permissao("segundo_plano"))) -> JSONResponse:
    """Asks again for a run of the account that stopped without a verification (cancelled, failed
    or lost): the same request, in the queue under a new id, which takes the old one's place in the
    account's list."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    fila = request.app.state.fila
    anterior = await fila.execucao(run_id) if RUN_ID_VALIDO.match(run_id) else None
    if anterior is None or not await fila.e_dono(run_id, quem(request), utilizador.id):
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    parada = anterior["estado"] == "perdida" or (
        anterior["estado"] == "terminada" and request.app.state.runs.guardada(run_id) is None)
    if not parada:
        raise HTTPException(status_code=409, detail=texto("execucao_nao_parada", lingua))
    definicoes = get_settings()
    plataforma = request.app.state.plataforma.definicoes()
    redator = anterior.get("redator")
    if redator not in definicoes.redatores:
        redator = plataforma.redator_omissao             if plataforma.redator_omissao in definicoes.redatores else definicoes.redatores[0]
    payload = ClaimInput(
        claim=anterior["claim"], claim_date=anterior["claim_date"], context=anterior["context"],
        top_k=anterior.get("top_k") or plataforma.top_k_omissao, redator=redator)
    novo = uuid.uuid4().hex[:12]
    await pedir_na_fila(request, payload, lingua, novo, definicoes.runs_per_session, utilizador.id)
    await fila.retirar_da_conta(run_id, utilizador.id)
    return JSONResponse({"run_id": novo}, headers={"Cache-Control": "no-store"})


@router.get("/execucoes/{run_id}")
async def execucao(run_id: str, request: Request,
                   utilizador: Utilizador = Depends(utilizador_atual)) -> JSONResponse:
    """One run in the background, for its account: what was asked and how far it got, so the page
    can open it again under way (its events: `/runs/<id>/eventos`)."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    fila = request.app.state.fila
    resultado = await fila.execucao(run_id) if RUN_ID_VALIDO.match(run_id) else None
    if resultado is None or not await fila.e_dono(run_id, quem(request), utilizador.id):
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    return JSONResponse(resultado, headers={"Cache-Control": "no-store"})


@router.get("/runs/{run_id}/eventos")
async def eventos(run_id: str, request: Request, desde: str = "0",
                  utilizador: Utilizador = Depends(utilizador_atual)) -> StreamingResponse:
    """A run waiting, under way or just over, read from after event `desde` (a stream id): where
    the page picks it up again when its connection broke, or (a run in the background) where its
    account opens it again."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    fila = request.app.state.fila
    # Only who asked for the run reads it again; to anyone else it does not exist.
    if not RUN_ID_VALIDO.match(run_id) or not ID_DO_EVENTO.match(desde) \
            or not await fila.e_dono(run_id, quem(request), utilizador.id) \
            or not await fila.existe(run_id):
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    return StreamingResponse(fila.ler(run_id, lingua, desde), media_type="text/event-stream",
                             headers=CABECALHOS_SSE)


@router.delete("/runs/{run_id}", status_code=204)
async def cancelar(run_id: str, request: Request,
                   utilizador: Utilizador = Depends(utilizador_atual)) -> Response:
    """Cancels a run, waiting or under way: the page started another, or is closing, or its
    account stops it. Only who asked for it; `python -m app.fila` cancels any."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    fila = request.app.state.fila
    if not RUN_ID_VALIDO.match(run_id) \
            or not await fila.e_dono(run_id, quem(request), utilizador.id):
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    await fila.cancelar(run_id, lingua)
    return Response(status_code=204)


@router.get("/verificacoes/{run_id}")
async def verificacao(run_id: str, request: Request) -> JSONResponse:
    """A finished verification, as the events its run sent: the page's address for it,
    `/verificacao/<run_id>`, opens it from this. Any signed-in session reads it - the address is
    what is shared - but only a verification that ran to its end is kept; a run under way, or
    stopped, has none."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = request.app.state.runs.guardada(run_id) if RUN_ID_VALIDO.match(run_id) else None
    if resultado is None:
        raise HTTPException(status_code=404, detail=texto("verificacao_ausente", lingua))
    return JSONResponse(
        {
            "run_id": resultado.run_id,
            "guardada_em": resultado.saved_at,
            "input": resultado.input.model_dump(mode="json"),
            "eventos": guardadas.eventos(resultado),
        },
        # Behind the sign-in, so not for a shared cache.
        headers={"Cache-Control": "private, no-cache"},
    )


@router.get("/runs/{run_id}/documents/{doc_id}")
async def document(run_id: str, doc_id: str, request: Request,
                   utilizador: Utilizador = Depends(utilizador_atual)) -> dict:
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    if not RUN_ID_VALIDO.match(run_id):
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    runs = request.app.state.runs
    # A kept verification is read by whoever has its address; a run under way, only by who asked
    # for it - to anyone else it does not exist.
    resultado = runs.guardada(run_id)
    if resultado is None:
        if not await request.app.state.fila.e_dono(run_id, quem(request), utilizador.id):
            raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
        resultado = runs.get(run_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail=texto("execucao_expirada", lingua))
    for documento in resultado.documents:
        if documento.doc_id == doc_id:
            return {
                "doc_id": documento.doc_id,
                "headline": documento.headline,
                "published_at": documento.published_at,
                "genre": documento.genre,
                "topics": documento.topics,
                "byline": documento.byline,
                "word_count": documento.word_count,
                "content": documento.content,
                "found_by": [f.model_dump() for f in documento.found_by],
                "excerpts": [e.model_dump() for e in documento.excerpts],
            }
    raise HTTPException(status_code=404, detail=texto("noticia_ausente", lingua))


# ---- Editorial review ------------------------------------------------------------------------
# The automated result is never changed: these routes read and append to the review of a saved
# verification (`revisao.py`). The page edits a draft, with its own undo and redo, and a version is
# made only when a person saves it. Read-only accounts may read the review and every version;
# only an editor may save one or ask for a rewrite.

class PedidoRevisao(BaseModel):
    versao: int = Field(ge=0)
    estado: RevisaoEstado
    # The earlier version the draft was reopened from, when it is a restore.
    restaurada_de: Optional[int] = Field(default=None, ge=0)


class PedidoReescrita(BaseModel):
    versao: int = Field(ge=0)
    # A writer other than the run's own: the one it used may no longer be served.
    redator: Optional[str] = None


def _verificacao_guardada(request: Request, run_id: str, lingua: str) -> RunResult:
    resultado = request.app.state.runs.guardada(run_id) if RUN_ID_VALIDO.match(run_id) else None
    if resultado is None:
        raise HTTPException(status_code=404, detail=texto("verificacao_ausente", lingua))
    return resultado


def _revisao_publica(revisao, resultado: RunResult, plataforma, utilizador: Utilizador) -> dict:
    """The review as the page reads it: the automated and the current state with their text (the
    article included), the history as metadata only (a restore names its target; an older review's
    undo, redo or kind of edit is an edit), and where the current article came from."""
    origem = revisao.origem_do_artigo()
    candidatos, anteriores = artigos_da_evidencia(revisao, resultado)
    return {
        "run_id": revisao.run_id,
        "original": expandir(revisao.original, resultado).model_dump(mode="json"),
        "actual": expandir(revisao.estado_actual(), resultado).model_dump(mode="json"),
        "versao": revisao.versao_atual,
        "historico": [
            {
                "versao": versao.versao,
                "accao": "edicao" if versao.accao in ACCOES_ANTIGAS else versao.accao,
                "autor": versao.autor.model_dump(mode="json"),
                "em": versao.em,
                "alteracoes": versao.alteracoes,
                "restaurada_de": versao.restaurada_de,
                "redator": versao.redator,
            }
            for versao in revisao.historico
        ],
        # The version that put the article in place, and how; none while it is the run's own.
        "artigo_origem": None if origem is None else {
            "versao": origem.versao,
            "accao": "edicao" if origem.accao in ACCOES_ANTIGAS else origem.accao,
            "autor": origem.autor.model_dump(mode="json"),
            "redator": origem.redator,
        },
        # The articles written from the evidence as it stands, to compare and pick from, and how
        # many more were written from an earlier state of it (only the history reaches those).
        "artigos": [
            {**candidato, "autor": candidato["autor"].model_dump(mode="json")
             if candidato["autor"] is not None else None,
             "artigo": candidato["artigo"].model_dump(mode="json")}
            for candidato in candidatos
        ],
        "artigos_anteriores": anteriores,
        "redator": resultado.input.redator,
        "pedido": revisao.pedido.model_dump(mode="json") if revisao.pedido is not None else None,
        "pode_editar": plataforma.pode(utilizador, "editar_resultados"),
    }


def _conflito(conflito: Conflito, resultado: RunResult, request: Request,
              utilizador: Utilizador, lingua: str) -> JSONResponse:
    return JSONResponse(
        {"detail": texto("revisao_conflito", lingua),
         "revisao": _revisao_publica(conflito.revisao, resultado, request.app.state.plataforma,
                                     utilizador)},
        status_code=409, headers={"Cache-Control": "no-store"},
    )


@router.get("/verificacoes/{run_id}/revisao")
async def obter_revisao(
    run_id: str,
    request: Request,
    utilizador: Utilizador = Depends(exigir_permissao("ver_resultados")),
) -> JSONResponse:
    """The automated evidence, the current one and every revision, for any reader of results."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = _verificacao_guardada(request, run_id, lingua)
    revisao = request.app.state.revisoes.obter(resultado)
    return JSONResponse(
        _revisao_publica(revisao, resultado, request.app.state.plataforma, utilizador),
        headers={"Cache-Control": "private, no-cache"},
    )


@router.get("/verificacoes/{run_id}/revisao/versoes/{versao}")
async def obter_versao(
    run_id: str,
    versao: int,
    request: Request,
    utilizador: Utilizador = Depends(exigir_permissao("ver_resultados")),
) -> JSONResponse:
    """One saved version in full, for the page to show (and an editor to save again)."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = _verificacao_guardada(request, run_id, lingua)
    revisao = request.app.state.revisoes.obter(resultado)
    try:
        estado = revisao.estado_de(versao)
    except ErroRevisao as erro:
        raise HTTPException(status_code=404, detail=texto(erro.chave, lingua, **erro.valores))
    return JSONResponse(
        {"versao": versao, "estado": expandir(estado, resultado).model_dump(mode="json")},
        headers={"Cache-Control": "private, no-cache"},
    )


@router.patch("/verificacoes/{run_id}/revisao")
async def guardar_revisao(
    run_id: str,
    corpo: PedidoRevisao,
    request: Request,
    utilizador: Utilizador = Depends(exigir_permissao("editar_resultados")),
) -> JSONResponse:
    """Saves the draft as a new version, if it differs from the current one. `versao` is the one
    the page read: a mismatch is a 409, with the review as it is now."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = _verificacao_guardada(request, run_id, lingua)
    autor = Autor(**utilizador.resumo())
    try:
        revisao = request.app.state.revisoes.aplicar(
            resultado, corpo.estado, autor, corpo.versao, restaurada_de=corpo.restaurada_de)
    except Conflito as conflito:
        return _conflito(conflito, resultado, request, utilizador, lingua)
    except ErroRevisao as erro:
        raise HTTPException(status_code=422,
                            detail=texto(erro.chave, lingua, **erro.valores))
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return JSONResponse(
        _revisao_publica(revisao, resultado, request.app.state.plataforma, utilizador),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/verificacoes/{run_id}/revisao/artigo")
async def reescrever_artigo(
    run_id: str,
    corpo: PedidoReescrita,
    request: Request,
    utilizador: Utilizador = Depends(exigir_permissao("editar_resultados")),
) -> JSONResponse:
    """Queues the article rewrite from the saved evidence, with the run's own writer or the one
    asked for. The page polls the review while the worker writes; the article arrives as a version
    of its own."""
    lingua = lingua_do_pedido(request.headers.get("accept-language"))
    resultado = _verificacao_guardada(request, run_id, lingua)
    redator = corpo.redator or resultado.input.redator
    if redator not in get_settings().redatores:
        raise HTTPException(status_code=422, detail=texto("revisao_redator", lingua))
    revisao = request.app.state.revisoes.obter(resultado)
    if revisao.versao_atual != corpo.versao:
        return JSONResponse(
            {"detail": texto("revisao_conflito", lingua),
             "revisao": _revisao_publica(revisao, resultado, request.app.state.plataforma,
                                         utilizador)},
            status_code=409, headers={"Cache-Control": "no-store"},
        )
    if revisao.pedido is not None and revisao.pedido.estado in ("na-fila", "em-curso"):
        return JSONResponse(
            {"detail": texto("revisao_pedido", lingua),
             "revisao": _revisao_publica(revisao, resultado, request.app.state.plataforma,
                                         utilizador)},
            status_code=409, headers={"Cache-Control": "no-store"},
        )
    estado = expandir(revisao.estado_actual(), resultado)
    if not passagens_revistas(estado, resultado):
        raise HTTPException(status_code=422,
                            detail=texto("revisao_sem_evidencia", lingua))

    autor = Autor(**utilizador.resumo())
    try:
        job_id = await request.app.state.fila.enfileirar_artigo(
            resultado.run_id, corpo.versao, autor.model_dump(mode="json"), redator, utilizador.id,
        )
    except Exception:  # noqa: BLE001 - Redis down, queue unwritable: the page is told
        logger.exception("falha ao pôr a reescrita do artigo na fila")
        raise HTTPException(status_code=503, detail=texto("revisao_fila", lingua))

    pedido = PedidoArtigo(estado="na-fila", por=autor, em=agora(), job_id=job_id, redator=redator)
    try:
        revisao = request.app.state.revisoes.marcar_pedido(resultado, pedido)
    except FalhaAoGravar:
        raise HTTPException(status_code=503, detail=texto("falha_guardar", lingua))
    return JSONResponse(
        _revisao_publica(revisao, resultado, request.app.state.plataforma, utilizador),
        headers={"Cache-Control": "no-store"},
    )
