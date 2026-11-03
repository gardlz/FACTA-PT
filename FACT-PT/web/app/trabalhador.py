"""The worker: takes the runs from the queue one at a time and runs them (`fila.py`).

    python -m app.trabalhador

Each job runs in a process of its own, forked by RQ, with clients of its own for the inference
service and the LUSA API; the results go to the run store, shared with the website.
"""

from __future__ import annotations

import asyncio
import logging

from redis import Redis
from redis.asyncio import Redis as RedisAssincrono
from rq import Queue, Worker

from .demo.store import get_exemplos
from .fila import NOME_DA_FILA, correr
from .pipeline import article as article_stage
from .pipeline.orchestrator import PipelineRunner
from .revisao import (
    Autor, Conflito, PedidoArtigo, ReviewStore, agora, expandir, passagens_revistas,
)
from .runstore import RunStore
from .schemas import REDATORES, ClaimInput
from .services.inference import InferenceClient, InferenceUnavailable
from .services.lusa import LusaClient
from .settings import get_settings

logger = logging.getLogger(__name__)


async def _executar(entrada: dict, lingua: str, run_id: str) -> None:
    definicoes = get_settings()
    redis = RedisAssincrono.from_url(definicoes.redis_url, decode_responses=True)
    inferencia, lusa = InferenceClient(definicoes), LusaClient(definicoes)
    try:
        runner = PipelineRunner(definicoes, inferencia, lusa, get_exemplos(), lingua=lingua)
        store = RunStore(definicoes.run_retention, definicoes.run_store_dir,
                         definicoes.saved_retention)
        await correr(definicoes, redis, runner, store, ClaimInput.model_validate(entrada), lingua,
                     run_id)
    finally:
        await inferencia.aclose()
        await lusa.aclose()
        await redis.aclose()


def executar(entrada: dict, lingua: str, run_id: str) -> None:
    """The job: one run, from the queue."""
    asyncio.run(_executar(entrada, lingua, run_id))


async def _reescrever(run_id: str, versao: int, autor: dict, redator: str) -> None:
    """Writes the article again from the evidence the review keeps, with the run's own writer,
    and files it as a revision. The review's `pedido` says how it went; the page polls it."""
    definicoes = get_settings()
    inferencia = InferenceClient(definicoes)
    store = RunStore(definicoes.run_retention, definicoes.run_store_dir,
                     definicoes.saved_retention)
    revisoes = ReviewStore(definicoes.revisoes_dir)
    quem = Autor.model_validate(autor)
    resultado = None

    def pedido(estado: str, erro: str = "", detalhe: str = "") -> PedidoArtigo:
        return PedidoArtigo(estado=estado, por=quem, em=agora(), erro=erro, detalhe=detalhe,
                            redator=redator)

    try:
        resultado = store.guardada(run_id)
        if resultado is None:
            logger.warning("reescrita pedida para a execução %s, que não está guardada", run_id)
            return
        revisao = revisoes.ler(run_id) or revisoes.obter(resultado)
        if revisao.versao_atual != versao:
            revisoes.marcar_pedido(resultado, pedido("erro", "revisao_artigo_desatualizado"))
            return
        revisoes.marcar_pedido(resultado, pedido("em-curso"))
        estado = expandir(revisao.estado_actual(), resultado)
        passagens = passagens_revistas(estado, resultado)
        if not passagens:
            revisoes.marcar_pedido(resultado, pedido("erro", "revisao_sem_evidencia"))
            return
        resposta = await inferencia.write_article(
            resultado.input.claim, resultado.input.claim_date.isoformat(),
            resultado.input.context, passagens, redator,
        )
        artigo = article_stage.do_modelo(
            resposta, resultado.documents, REDATORES.get(redator, redator),
            resultado.repeated_passages, {s.excerpt_id: s.label for s in resultado.stances})
        revisoes.registar_artigo(resultado, artigo, quem, redator, versao)
        revisoes.marcar_pedido(resultado, pedido("feito"))
    except Conflito:
        logger.info("a evidência de %s mudou durante a reescrita", run_id)
        revisoes.marcar_pedido(resultado, pedido("erro", "revisao_artigo_desatualizado"))
    except InferenceUnavailable as erro:
        # The writer is not served (an inference service without it, or not up yet): the page
        # says so, and offers another writer.
        logger.warning("reescrita de %s sem o modelo %s: %s", run_id, redator, erro)
        revisoes.marcar_pedido(resultado, pedido("erro", "revisao_artigo_indisponivel", str(erro)))
    except Exception:  # noqa: BLE001 - the job must leave the review saying it failed
        logger.exception("falha ao reescrever o artigo de %s", run_id)
        if resultado is not None:
            try:
                revisoes.marcar_pedido(resultado, pedido("erro", "revisao_artigo_falhou"))
            except Exception:  # noqa: BLE001
                logger.exception("falha ao registar o erro da reescrita de %s", run_id)
    finally:
        await inferencia.aclose()


def reescrever(run_id: str, versao: int, autor: dict, redator: str) -> None:
    """The job: the article written again from a review."""
    asyncio.run(_reescrever(run_id, versao, autor, redator))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    ligacao = Redis.from_url(get_settings().redis_url)
    Worker([Queue(NOME_DA_FILA, connection=ligacao)], connection=ligacao).work()
