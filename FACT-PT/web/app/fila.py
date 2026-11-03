"""The queue of runs: Redis, with RQ.

A run that uses the models is a job: the website puts it in the queue and the worker (the compose
service `worker`, `python -m app.trabalhador`) takes the jobs one at a time - the inference service
holds the models, and two runs at once would only take turns on them. A worked example runs no
model and skips the queue: the website plays it back itself.

Each run writes its events, numbered, to a Redis stream, apart from any connection: the page reads
it from the start and, when its connection breaks - browsers drop long streams -, reads on from the
last event it saw. While the job waits, the page is told how many are ahead of it.

A run is cancelled when the page asks (it started another, or is closing), or when nobody has read
it for `run_detached_grace` seconds: waiting, it leaves the queue; under way, it stops and says why.
A run in the background (the account's `segundo_plano` permission) is never abandoned: it belongs
to the account, which lists it (`execucoes`) and may open it again from any session while it runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from redis import Redis
from redis.asyncio import Redis as RedisAssincrono
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from rq.registry import StartedJobRegistry
from rq.worker import Worker

from .mensagens import texto
from .runstore import RunStore
from .schemas import ClaimInput, RunResult
from .settings import Settings

logger = logging.getLogger(__name__)

NOME_DA_FILA = "facta-pt"
# Seconds of silence after which the stream says it is still working: a proxy in front of the site
# closes an idle connection. A line starting with ":" is an SSE comment: the page ignores it.
SINAL_DE_VIDA = 15.0
# How long a reader waits on the stream for new events, and how often it marks the run as watched.
ESPERA_MS = 1000
VISTO_A_CADA = 5.0
# How often a run checks whether it was cancelled or abandoned.
VIGIAR_A_CADA = 2.0
# How long a run's events are kept once it is over: what a late reconnection can still read.
GUARDAR_DEPOIS = 24 * 3600
# A worker running a job renews its heartbeat every half minute (RQ's job monitoring): past this
# many seconds without one, it is gone - killed, or its container restarted - and its run with it.
SEM_BATIMENTO = 120
# The status of a job whose worker is gone (`Fila._situacao`).
PERDIDA = "perdida"
# The record that closes a run's events, whatever the last one was.
FIM = {"type": "fim"}
TERMINAIS = ("done", "error")


def _chave(run_id: str, coisa: str) -> str:
    return f"facta-pt:execucao:{run_id}:{coisa}"


def _chave_conta(utilizador_id: str) -> str:
    """The account's runs of the last day, by the time they were asked for."""
    return f"facta-pt:conta:{utilizador_id}:execucoes"


def sem_conteudo(resultado: dict) -> dict:
    """Drop the news and excerpt text, keeping the ids and offsets that link a citation.

    The full run is in the store; the page fetches a news item when its reader opens it, so the
    final event stays small."""
    aligeirado = dict(resultado)
    aligeirado["documents"] = [
        {
            **{k: v for k, v in documento.items() if k not in ("content", "excerpts")},
            "excerpts": [{k: v for k, v in e.items() if k != "text"}
                         for e in documento.get("excerpts", [])],
        }
        for documento in resultado.get("documents", [])
    ]
    return aligeirado


def _de_exemplo(resultado: RunResult) -> bool:
    """Whether the run is a stored example played back, not one the models made."""
    return any(etapa.provenance == "exemplo" for etapa in resultado.stages)


class Fila:
    """The queue and the runs' events, for the website: put a run in, read its events, cancel it."""

    def __init__(self, definicoes: Settings) -> None:
        self._definicoes = definicoes
        self.redis = RedisAssincrono.from_url(definicoes.redis_url, decode_responses=True)
        # RQ speaks to Redis synchronously; its calls are short and go off the event loop.
        self._sincrono = Redis.from_url(definicoes.redis_url)
        self._fila = Queue(NOME_DA_FILA, connection=self._sincrono)

    async def aclose(self) -> None:
        await self.redis.aclose()
        self._sincrono.close()

    async def visto(self, run_id: str) -> None:
        """Marks the run as watched for the grace period: past it, unwatched, it is abandoned."""
        await self.redis.set(_chave(run_id, "visto"), "1",
                             ex=max(1, int(self._definicoes.run_detached_grace)))

    async def dono(self, run_id: str, quem: str) -> None:
        """Records who asked for the run: only they read it again or cancel it from the page."""
        await self.redis.set(_chave(run_id, "dono"), quem, ex=GUARDAR_DEPOIS)

    async def e_dono(self, run_id: str, quem: str, utilizador_id: str | None = None) -> bool:
        """Who asked for the run, from that session; or, for a run in the background, the account
        that asked for it, from any session."""
        if await self.redis.get(_chave(run_id, "dono")) == quem:
            return True
        return bool(utilizador_id) and \
            await self.redis.get(_chave(run_id, "conta")) == utilizador_id

    async def _da_conta(self, run_id: str, utilizador_id: str, entrada: ClaimInput) -> None:
        """Files a run in the background under its account: what was asked, and when."""
        agora = datetime.now(timezone.utc)
        meta = {
            "run_id": run_id,
            "claim": entrada.claim,
            "claim_date": entrada.claim_date.isoformat(),
            "context": entrada.context,
            # What a restart needs to ask for the same run again.
            "top_k": entrada.top_k,
            "redator": entrada.redator,
            "pedida_em": agora.isoformat(timespec="seconds"),
        }
        conta = _chave_conta(utilizador_id)
        async with self.redis.pipeline(transaction=True) as tubo:
            tubo.set(_chave(run_id, "conta"), utilizador_id, ex=GUARDAR_DEPOIS)
            tubo.set(_chave(run_id, "fundo"), "1", ex=GUARDAR_DEPOIS)
            tubo.set(_chave(run_id, "meta"), json.dumps(meta, ensure_ascii=False), ex=GUARDAR_DEPOIS)
            tubo.zadd(conta, {run_id: agora.timestamp()})
            # Past a day the run's events are gone too: nothing to open again.
            tubo.zremrangebyscore(conta, "-inf", agora.timestamp() - GUARDAR_DEPOIS)
            tubo.expire(conta, GUARDAR_DEPOIS)
            await tubo.execute()

    async def execucao(self, run_id: str) -> dict | None:
        """A run in the background, as its account's list shows it: what was asked, and how far it
        got (`na-fila`, with how many are ahead; `em-curso`; `terminada`; `perdida`)."""
        bruto = await self.redis.get(_chave(run_id, "meta"))
        if bruto is None:
            return None
        meta = json.loads(bruto)
        fechada = await self.redis.get(_chave(run_id, "fechada"))
        frente = None
        if fechada == "1":
            estado = "terminada"
        else:
            situacao, frente = await asyncio.to_thread(self._situacao, run_id)
            if situacao == JobStatus.QUEUED:
                estado = "na-fila"
            elif situacao == JobStatus.STARTED or fechada == "0":
                estado = "em-curso"
            else:
                estado = "perdida"
        return {**meta, "estado": estado, "frente": frente}

    async def execucoes(self, utilizador_id: str) -> list[dict]:
        """The account's runs in the background of the last day, newest first."""
        conta = _chave_conta(utilizador_id)
        limite = datetime.now(timezone.utc).timestamp() - GUARDAR_DEPOIS
        ids = await self.redis.zrevrangebyscore(conta, "+inf", limite)
        lista = []
        for run_id in ids:
            execucao = await self.execucao(run_id)
            if execucao is not None:
                lista.append(execucao)
        return lista

    async def retirar_da_conta(self, run_id: str, utilizador_id: str) -> None:
        """Takes a run off the account's list: a restart replaces the run it restarts."""
        await self.redis.zrem(_chave_conta(utilizador_id), run_id)

    def _activos(self) -> list[Job]:
        """The jobs waiting and under way."""
        ids = [*StartedJobRegistry(queue=self._fila).get_job_ids(), *self._fila.job_ids]
        return [t for t in Job.fetch_many(ids, connection=self._sincrono) if t is not None]

    async def por_na_fila(self, payload: ClaimInput, lingua: str, run_id: str, quem: str,
                          endereco: str, limite_sessao: int | None = None,
                          conta: str | None = None) -> str | None:
        """Queues a run that uses the models, recording who asked and from where. None when it is
        in; else why not: the queue is full (`fila`), or this session or address already has as
        many runs waiting or under way as it may (`sessao`, `endereco`). `limite_sessao` overrides
        `RUNS_PER_SESSION` for this request. `conta`, an account id, runs it in the background,
        under that account."""
        definicoes = self._definicoes
        limite = definicoes.runs_per_session if limite_sessao is None else limite_sessao
        # One request at a time per session, so two quick ones cannot both slip under the limit.
        async with self.redis.lock(f"facta-pt:pedido:{quem}", timeout=30, blocking_timeout=10):
            activos = await asyncio.to_thread(self._activos)
            if sum(t.get_status(refresh=False) == JobStatus.QUEUED for t in activos) \
                    >= definicoes.queue_max:
                return "fila"
            if limite and sum(
                    t.meta.get("quem") == quem for t in activos) >= limite:
                return "sessao"
            if definicoes.runs_per_address and sum(
                    t.meta.get("endereco") == endereco for t in activos) >= definicoes.runs_per_address:
                return "endereco"
            await self.visto(run_id)
            await self.dono(run_id, quem)
            if conta:
                await self._da_conta(run_id, conta, payload)
            await asyncio.to_thread(
                self._fila.enqueue, "app.trabalhador.executar",
                payload.model_dump(mode="json"), lingua, run_id,
                job_id=run_id, job_timeout=int(definicoes.run_timeout),
                result_ttl=GUARDAR_DEPOIS, failure_ttl=GUARDAR_DEPOIS,
                meta={"quem": quem, "endereco": endereco},
            )
        return None

    async def enfileirar_artigo(self, run_id: str, versao: int, autor: dict, redator: str,
                                quem: str) -> str:
        """Queues a rewrite of the article from the reviewed evidence. It shares the run's queue,
        so it waits behind any run under way: the models write one thing at a time."""
        job_id = f"{run_id}-artigo-{versao}-{uuid.uuid4().hex[:6]}"
        await asyncio.to_thread(
            self._fila.enqueue, "app.trabalhador.reescrever",
            run_id, versao, autor, redator,
            job_id=job_id,
            job_timeout=int(self._definicoes.article_timeout) + 120,
            result_ttl=GUARDAR_DEPOIS, failure_ttl=GUARDAR_DEPOIS,
            meta={"quem": quem, "tipo": "artigo", "run_id": run_id},
        )
        return job_id

    def _trabalho(self, run_id: str) -> Job | None:
        try:
            return Job.fetch(run_id, connection=self._sincrono)
        except NoSuchJobError:
            return None

    def _perdida(self, trabalho: Job) -> bool:
        """Whether a job under way lost its worker: no record of it, or no heartbeat for a while."""
        if trabalho.get_status(refresh=False) != JobStatus.STARTED or not trabalho.worker_name:
            return False
        trabalhador = Worker.find_by_key(Worker.redis_worker_namespace_prefix + trabalho.worker_name,
                                         connection=self._sincrono)
        batimento = trabalhador.last_heartbeat if trabalhador is not None else None
        if batimento is None:
            return True
        if batimento.tzinfo is None:
            batimento = batimento.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - batimento).total_seconds() > SEM_BATIMENTO

    def _arrumar(self) -> None:
        """Has RQ file the jobs whose worker is gone as abandoned, now rather than at its next
        round. Housekeeping only: a failure here must not break a page's stream."""
        try:
            StartedJobRegistry(queue=self._fila).cleanup()
        except Exception:  # noqa: BLE001
            logger.exception("falha ao arrumar as execuções perdidas")

    def _situacao(self, run_id: str) -> tuple[str | None, int | None]:
        """The job's status (`PERDIDA` when its worker is gone) and, while it waits, how many are
        ahead of it."""
        trabalho = self._trabalho(run_id)
        if trabalho is None:
            return None, None
        estado = trabalho.get_status(refresh=True)
        if self._perdida(trabalho):
            self._arrumar()
            return PERDIDA, None
        frente = trabalho.get_position() if estado == JobStatus.QUEUED else None
        return estado, frente

    async def existe(self, run_id: str) -> bool:
        return bool(await self.redis.exists(_chave(run_id, "eventos"))) or (
            await asyncio.to_thread(self._trabalho, run_id) is not None)

    async def fechar(self, run_id: str, mensagem: str, comecada: bool = False) -> None:
        """Closes a run that cannot close itself with an error and the closing record: one that
        never started (it left the queue) or, `comecada`, one whose worker died. Once: the mark
        `fechada` is absent before a run starts, 0 while it runs, 1 once it is closed."""
        anterior = await self.redis.set(_chave(run_id, "fechada"), "1", ex=GUARDAR_DEPOIS,
                                        get=True)
        if anterior is None or (anterior == "0" and comecada):
            eventos = _chave(run_id, "eventos")
            await self.redis.xadd(eventos, {"evento": json.dumps(
                {"type": "error", "message": mensagem}, ensure_ascii=False)})
            await self.redis.xadd(eventos, {"evento": json.dumps(FIM)})
            await self.redis.expire(eventos, GUARDAR_DEPOIS)

    async def cancelar(self, run_id: str, lingua: str) -> None:
        """The page cancels a run: waiting, it leaves the queue here; under way, the worker sees
        the mark and stops it (`correr`)."""
        await self.redis.set(_chave(run_id, "cancelar"), "1", ex=GUARDAR_DEPOIS)
        trabalho = await asyncio.to_thread(self._trabalho, run_id)
        if trabalho is None:
            return
        if trabalho.get_status(refresh=True) == JobStatus.QUEUED:
            await asyncio.to_thread(trabalho.cancel)
            await self.fechar(run_id, texto("execucao_cancelada", lingua))
        elif await asyncio.to_thread(self._perdida, trabalho):
            # Nobody is left to see the mark: it is closed here.
            await asyncio.to_thread(self._arrumar)
            await self.fechar(run_id, texto("execucao_cancelada", lingua), comecada=True)

    async def ler(self, run_id: str, lingua: str, desde: str = "0") -> AsyncIterator[str]:
        """The run's events after `desde` (a stream id), as server-sent events whose `id:` is the
        stream id, until the closing record. While the job waits, how many are ahead (`queue`),
        each time that changes; keep-alives in the silences."""
        eventos = _chave(run_id, "eventos")
        loop = asyncio.get_running_loop()
        sinal = visto = loop.time()
        frente_dita: int | None = -1
        await self.visto(run_id)
        yield f"data: {json.dumps({'type': 'queue', 'run_id': run_id, 'ahead': None})}\n\n"
        while True:
            resposta = await self.redis.xread({eventos: desde}, block=ESPERA_MS, count=100)
            agora = loop.time()
            for _, entradas in resposta:
                for id_, campos in entradas:
                    desde = id_
                    evento = json.loads(campos["evento"])
                    if evento == FIM:
                        yield f"data: {json.dumps(FIM)}\n\n"
                        return
                    yield f"id: {id_}\ndata: {json.dumps(evento, ensure_ascii=False)}\n\n"
                    sinal = agora
            if agora - visto >= VISTO_A_CADA:
                await self.visto(run_id)
                visto = agora
            if not resposta:
                estado, frente = await asyncio.to_thread(self._situacao, run_id)
                if estado == JobStatus.QUEUED and frente != frente_dita:
                    frente_dita = frente
                    yield f"data: {json.dumps({'type': 'queue', 'run_id': run_id, 'ahead': frente})}\n\n"
                    sinal = agora
                elif estado in (PERDIDA, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED):
                    # The job ended without closing its events - its worker was killed, say: the
                    # stream says so instead of waiting forever. A closed run returns above.
                    motivo = "execucao_perdida" if estado == PERDIDA else "erro_inesperado"
                    await self.fechar(run_id, texto(motivo, lingua), comecada=True)
                    continue
            if agora - sinal >= SINAL_DE_VIDA:
                yield ": a trabalhar\n\n"
                sinal = agora


async def correr(definicoes: Settings, redis: RedisAssincrono, runner, store: RunStore,
                 payload: ClaimInput, lingua: str, run_id: str) -> None:
    """A run, from start to finish, writing its events to its stream: the worker's job, and a
    worked example in the website itself. It stops when the page cancels it or nobody watches
    it any more, and always closes its events."""
    eventos = _chave(run_id, "eventos")

    async def registar(evento: dict) -> None:
        await redis.xadd(eventos, {"evento": json.dumps(evento, ensure_ascii=False)})

    async def percorrer() -> None:
        async for evento in runner.run(payload, run_id=run_id):
            if evento["type"] == "snapshot":
                try:
                    store.put(RunResult.model_validate(evento["result"]))
                except Exception:
                    logger.exception("falha ao guardar a execução a meio")
                continue
            if evento["type"] in TERMINAIS and evento.get("result"):
                try:
                    resultado = RunResult.model_validate(evento["result"])
                    store.put(resultado)
                    # A verification that ran to its end keeps its address; a worked example
                    # has the one it came with.
                    if evento["type"] == "done" and not _de_exemplo(resultado):
                        evento["guardada"] = store.guardar(resultado)
                    evento["result"] = sem_conteudo(evento["result"])
                except Exception:
                    logger.exception("falha inesperada ao guardar a execução")
                    evento = {"type": "error", "message": texto("erro_inesperado", lingua)}
            await registar(evento)

    async def motivo_para_parar() -> str | None:
        if await redis.exists(_chave(run_id, "cancelar")):
            return "execucao_cancelada"
        # A run in the background goes on with nobody watching.
        if not await redis.exists(_chave(run_id, "visto")) \
                and not await redis.exists(_chave(run_id, "fundo")):
            return "execucao_abandonada"
        return None

    if not await redis.set(_chave(run_id, "fechada"), "0", nx=True, ex=GUARDAR_DEPOIS):
        return  # Closed before it started (it left the queue).
    try:
        motivo = await motivo_para_parar()
        if motivo is None:
            tarefa = asyncio.create_task(percorrer())
            while not tarefa.done():
                await asyncio.wait({tarefa}, timeout=VIGIAR_A_CADA)
                if not tarefa.done() and (motivo := await motivo_para_parar()):
                    logger.info("execução %s parada: %s", run_id, motivo)
                    tarefa.cancel()
                    break
            try:
                await tarefa
            except asyncio.CancelledError:
                if motivo is None:
                    raise
            except Exception:
                logger.exception("falha inesperada na pipeline")
                await registar({"type": "error", "message": texto("erro_inesperado", lingua)})
        if motivo is not None:
            await registar({"type": "error", "message": texto(motivo, lingua)})
    finally:
        await registar(FIM)
        await redis.expire(eventos, GUARDAR_DEPOIS)
        await redis.set(_chave(run_id, "fechada"), "1", ex=GUARDAR_DEPOIS)


def _listar(fila: Fila) -> list[tuple[str, str, Job]]:
    """The runs under way and those waiting, in the order they will run. A run whose worker is
    gone shows as lost (`perdida`): cancelling it closes it."""
    fila_rq = fila._fila
    em_curso = StartedJobRegistry(queue=fila_rq).get_job_ids()
    linhas = []
    for estado, ids in (("em curso", em_curso), ("na fila", fila_rq.job_ids)):
        for trabalho in Job.fetch_many(ids, connection=fila._sincrono):
            if trabalho is not None:
                linhas.append((PERDIDA if fila._perdida(trabalho) else estado, trabalho.id,
                               trabalho))
    return linhas


async def _gerir(argumentos: list[str]) -> None:
    from .settings import get_settings

    fila = Fila(get_settings())
    try:
        linhas = await asyncio.to_thread(_listar, fila)
        if not argumentos:
            if not linhas:
                print("Não há verificações em curso nem na fila.")
            for estado, run_id, trabalho in linhas:
                quando = trabalho.enqueued_at if estado == "na fila" else trabalho.started_at
                argumento = trabalho.args[0] if trabalho.args else None
                claim = argumento.get("claim", "") if isinstance(argumento, dict) else ""
                if trabalho.meta.get("tipo") == "artigo":
                    claim = f"artigo de {trabalho.meta.get('run_id', '?')}"
                quem = trabalho.meta.get("quem", "?")
                endereco = trabalho.meta.get("endereco", "?")
                print(f"{run_id}  {estado:8}  {quando:%Y-%m-%d %H:%M} UTC  "
                      f"sessão {quem[:12]:12}  {endereco:15}  {claim[:60]}")
            return
        if argumentos[0] != "cancelar" or len(argumentos) < 2:
            raise SystemExit(__doc_gerir__)
        alvos = [run_id for _, run_id, _ in linhas] if argumentos[1:] == ["--todas"] \
            else argumentos[1:]
        for run_id in alvos:
            await fila.cancelar(run_id, "pt")
            print(f"{run_id}: cancelada")
    finally:
        await fila.aclose()


__doc_gerir__ = """Lists and cancels the runs that use the models:

    python -m app.fila                       the runs under way and waiting, in order, with the
                                             session and address that asked for each
    python -m app.fila cancelar ID [ID ...]  cancels those runs, waiting or under way
    python -m app.fila cancelar --todas      cancels them all

In Docker: docker compose exec worker python -m app.fila ...
A cancelled run's page says so; one under way stops within a couple of seconds."""


if __name__ == "__main__":
    import sys

    asyncio.run(_gerir(sys.argv[1:]))
