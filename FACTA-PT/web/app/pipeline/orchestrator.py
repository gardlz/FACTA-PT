"""Runs the pipeline stages, emitting one event per stage.

Two exclusive paths. A picked example is a recorded run of the models on that claim, replayed as
it happened. A new claim runs the models; a stage that cannot run is reported as skipped.
"""

from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from ..demo.store import ExemploStore
from ..mensagens import Texto, traduzir
from ..schemas import (
    STAGE_ORDER,
    ClaimInput,
    EvidenceDocument,
    ExcerptStance,
    Question,
    RunResult,
    StageName,
    StageReport,
)
from ..services.inference import InferenceClient, InferenceError, InferenceUnavailable
from ..services.lusa import LusaClient, LusaError
from ..settings import Settings
from . import article as article_stage
from . import evidencia
from . import questions as questions_stage
from . import retrieval as retrieval_stage
from .excerpts import build_excerpts

logger = logging.getLogger(__name__)

# Stages skipped when the LUSA credentials are not set: all of them depend on the retrieved
# news, the article included.
DEPENDEM_DO_CORPUS: frozenset[StageName] = frozenset(
    {"retrieval", "dedup", "relevance", "excerpts", "stance", "article"}
)


class StageSkipped(RuntimeError):
    """A stage that cannot run now, without the run having failed: its model is not loaded."""


class StageFailure(RuntimeError):
    """A stage that failed. `message` is a `Texto`, or an error carrying one, put in the
    language of the request when the failure is reported; or a plain string."""

    def __init__(self, stage: StageName, message: object) -> None:
        super().__init__(message)
        self.stage = stage


class PipelineRunner:
    def __init__(
        self,
        settings: Settings,
        inference: InferenceClient,
        lusa: LusaClient,
        exemplos: ExemploStore,
        lingua: str = "pt",
    ) -> None:
        self._settings = settings
        self._inference = inference
        self._lusa = lusa
        self._exemplos = exemplos
        # Language of the failure messages the page shows: "pt" or "en".
        self._lingua = lingua

    # --- Example path -------------------------------------------------------- #

    @staticmethod
    def _repetir(eventos: list[dict], run_id: str, data: ClaimInput) -> list[dict]:
        """A recorded run of the models on this claim, replayed as it happened: the same events,
        under this run's id."""
        repetidos = copy.deepcopy(eventos)
        for evento in repetidos:
            if evento["type"] == "start":
                evento["run_id"] = run_id
            resultado = evento.get("result")
            if isinstance(resultado, dict):
                resultado["run_id"] = run_id
                resultado["input"] = data.model_dump(mode="json")
        return repetidos

    # --- Model path ---------------------------------------------------------- #

    async def _perguntas_do_modelo(self, data: ClaimInput) -> list[Question]:
        try:
            brutas = await self._inference.generate_questions(
                data.claim, data.claim_date.isoformat(), data.context
            )
        except InferenceUnavailable as erro:
            logger.info("geração de perguntas indisponível: %s", erro)
            raise StageFailure("questions", Texto("perguntas_sem_modelo")) from erro
        except InferenceError as erro:
            raise StageFailure("questions", erro) from erro
        perguntas = questions_stage.to_questions(brutas, self._settings.max_questions)
        if not perguntas:
            raise StageFailure("questions", Texto("sem_perguntas"))
        return perguntas

    async def _relevancia_do_modelo(self, claim: str, documentos: list[EvidenceDocument]) -> None:
        """Marks each news item relevant or not. The unrelated ones stay in the result, with
        `relevant=False`, and produce no passages."""
        try:
            resultados = await self._inference.relevance(
                claim,
                [
                    {"doc_id": d.doc_id, "headline": d.headline, "content": d.content}
                    for d in documentos
                ],
            )
        except InferenceUnavailable as erro:
            raise StageFailure("relevance", Texto("relevancia_sem_modelo")) from erro
        except InferenceError as erro:
            raise StageFailure("relevance", erro) from erro

        por_id = {r["doc_id"]: r for r in resultados}
        for documento in documentos:
            veredito = por_id.get(documento.doc_id)
            documento.relevant = bool(veredito and veredito.get("relevant"))

    async def _classificar_com_modelo(
        self, claim: str, documentos: list[EvidenceDocument]
    ) -> list[ExcerptStance]:
        excertos = [{"id": e.id, "text": e.text} for d in documentos for e in d.excerpts]
        if not excertos:
            return []
        try:
            resultados = await self._inference.classify(claim, excertos)
        except InferenceUnavailable as erro:
            raise StageFailure("stance", Texto("relacao_sem_modelo")) from erro
        except InferenceError as erro:
            raise StageFailure("stance", erro) from erro
        try:
            return [
                ExcerptStance(excerpt_id=r["id"], label=r["label"], logits=r["logits"])
                for r in resultados
            ]
        except (KeyError, TypeError, ValidationError) as erro:
            raise StageFailure("stance", Texto("classificador_invalido", erro=erro)) from erro

    async def _artigo_do_modelo(self, data: ClaimInput, resultado: RunResult) -> dict:
        """The article written from the consolidated evidence, with what it needs to know of
        each passage: its relation, its offsets, and the news item's headline and date."""
        por_doc = {documento.doc_id: documento for documento in resultado.documents}
        posicoes = {
            excerto.id: posicao
            for documento in resultado.documents
            for posicao, excerto in enumerate(documento.excerpts, 1)
        }
        passagens = []
        for passagem in resultado.evidence_passages:
            documento = por_doc[passagem.doc_id]
            passagens.append({
                "id": passagem.id, "doc_id": passagem.doc_id, "label": passagem.label,
                "text": documento.content[passagem.begin:passagem.end],
                "begin": passagem.begin, "end": passagem.end,
                "headline": documento.headline, "published_at": documento.published_at,
                "index": posicoes[passagem.excerpt_ids[0]], "priority": passagem.priority,
            })
        try:
            return await self._inference.write_article(
                data.claim, data.claim_date.isoformat(), data.context, passagens
            )
        except InferenceUnavailable as erro:
            raise StageSkipped() from erro
        except InferenceError as erro:
            raise StageFailure("article", erro) from erro

    # --- Execution ----------------------------------------------------------- #

    async def run(self, data: ClaimInput) -> AsyncIterator[dict]:
        run_id = uuid.uuid4().hex[:12]
        exemplo = self._exemplos.get(data.exemplo_id) if data.exemplo_id else None
        if exemplo is not None:
            for evento in self._repetir(exemplo["eventos"], run_id, data):
                yield evento
            return

        relatorios: dict[StageName, StageReport] = {
            nome: StageReport(name=nome, status="pending") for nome in STAGE_ORDER
        }
        resultado = RunResult(run_id=run_id, input=data, stages=list(relatorios.values()))

        yield {"type": "start", "run_id": run_id,
               "stages": [r.model_dump() for r in relatorios.values()]}

        documentos: list[EvidenceDocument] = []

        try:
            for nome in STAGE_ORDER:
                if not self._settings.lusa_configured and nome in DEPENDEM_DO_CORPUS:
                    relatorios[nome].status = "skipped"
                    yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                    continue

                relatorios[nome].status = "running"
                yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                dados: dict[str, Any] = {}

                if nome == "questions":
                    resultado.questions = await self._perguntas_do_modelo(data)
                    dados = {"questions": [q.model_dump() for q in resultado.questions]}

                elif nome == "retrieval":
                    try:
                        documentos = await retrieval_stage.retrieve(
                            self._lusa, resultado.questions, data.claim_date,
                            self._settings.top_k_per_question, self._settings.lusa_concurrency,
                        )
                    except LusaError as erro:
                        raise StageFailure("retrieval", erro) from erro

                elif nome == "dedup":
                    # The search over-fetched; the cut applies here, after merging.
                    resultado.documents = retrieval_stage.deduplicate(
                        documentos, self._settings.top_k_per_question
                    )
                    dados = {"documents": [self._resumo(d) for d in resultado.documents]}

                elif nome == "relevance":
                    await self._relevancia_do_modelo(data.claim, resultado.documents)
                    dados = {"documents": [self._resumo(d) for d in resultado.documents]}

                elif nome == "excerpts":
                    for documento in resultado.documents:
                        documento.excerpts = (
                            build_excerpts(documento.doc_id, documento.content)
                            if documento.relevant else []
                        )

                elif nome == "stance":
                    stances = await self._classificar_com_modelo(data.claim, resultado.documents)
                    consolidacao = evidencia.consolidar(resultado.documents, stances)
                    resultado.stances = stances
                    resultado.decisive_excerpt_ids = consolidacao.decisivos
                    resultado.evidence_passages = consolidacao.evidencia
                    dados = {
                        "stances": [s.model_dump() for s in stances],
                        "decisive": consolidacao.decisivos,
                    }

                else:
                    try:
                        resposta = await self._artigo_do_modelo(data, resultado)
                    except StageSkipped:
                        relatorios[nome].status = "skipped"
                        yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                        continue
                    resultado.article = article_stage.do_modelo(resposta, resultado.documents)
                    dados = {"article": resultado.article.model_dump()}

                relatorios[nome].status = "done"
                yield {"type": "stage", "stage": relatorios[nome].model_dump(), **dados}
                if nome == "stance":
                    # Store the run before the slow article stage, so the page can already open
                    # the news items.
                    resultado.stages = list(relatorios.values())
                    yield {"type": "snapshot", "result": resultado.model_dump(mode="json")}

            resultado.stages = list(relatorios.values())
            yield {"type": "done", "result": resultado.model_dump(mode="json")}

        except StageFailure as falha:
            mensagem = traduzir(falha, self._lingua)
            relatorios[falha.stage].status = "error"
            relatorios[falha.stage].detail = mensagem
            yield {"type": "stage", "stage": relatorios[falha.stage].model_dump()}
            for nome in STAGE_ORDER[STAGE_ORDER.index(falha.stage) + 1 :]:
                if relatorios[nome].status == "pending":
                    relatorios[nome].status = "skipped"
                    yield {"type": "stage", "stage": relatorios[nome].model_dump()}
            resultado.stages = list(relatorios.values())
            resultado.error = mensagem
            yield {"type": "error", "message": mensagem,
                   "result": resultado.model_dump(mode="json")}

    @staticmethod
    def _resumo(documento: EvidenceDocument) -> dict:
        """What the page's timeline needs of a news item."""
        return {
            "doc_id": documento.doc_id,
            "headline": documento.headline,
            "published_at": documento.published_at,
            "relevant": documento.relevant,
        }
