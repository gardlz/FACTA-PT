"""Runs the pipeline stages, emitting one event per stage.

Two exclusive paths. A picked example is served from the stored data: what a recorded run of the
models on that claim produced, with the number of news items per question the reader chose
(`demo/corrida.py`). A new claim runs the models; a stage whose model is not wired is reported as
skipped.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from ..demo import corrida
from ..demo.store import ExemploStore
from ..mensagens import Texto, traduzir
from ..schemas import (
    REDATORES,
    STAGE_LABELS,
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
from . import stance as stance_stage
from .excerpts import build_excerpts

logger = logging.getLogger(__name__)

# Stages with no model on the model path. Wiring one up means removing it from here and
# writing its branch.
SEM_MODELO: dict[StageName, str] = {}

# Without corpus credentials these are declared skipped. The article too: its limits say it
# rests on the Lusa news retrieved, and with no retrieval there is nothing it could rest on.
DEPENDEM_DO_CORPUS: dict[StageName, str] = {
    "retrieval": "corpus LUSA por configurar",
    "dedup": "depende da recuperação",
    "relevance": "depende da recuperação",
    "excerpts": "depende da recuperação",
    "stance": "depende da recuperação",
    "article": "depende da recuperação",
}


class StageSkipped(RuntimeError):
    """A stage that cannot run now, without the run having failed: its model is not loaded."""


class StageFailure(RuntimeError):
    """A stage that failed. `message` is a `Texto`, or an error carrying one, put in the
    language of the request when the failure is reported; or a plain string."""

    def __init__(self, stage: StageName, message: object) -> None:
        super().__init__(message)
        self.stage = stage


def _contagem_de_relevancia(documentos: list[EvidenceDocument]) -> dict:
    """How many of the news items retrieved count as evidence, also as a whole percentage,
    rounded half up once, from the counts."""
    total = len(documentos)
    relevantes = sum(1 for d in documentos if d.relevant)
    return {"notícias": total, "relevantes": relevantes, "irrelevantes": total - relevantes,
            "percentagem": (200 * relevantes + total) // (2 * total) if total else 0}


def _detalhe_do_artigo(metadados: dict, lidas: int) -> str:
    """How the article was written: from how many passages, why some were left out, and which
    parts the inference service had to put together without the model."""
    recebidas = metadados.get("passagens_recebidas", lidas)
    detalhe = (f"escrito pelo {metadados.get('modelo_nome', 'modelo de redação')} a partir de "
               f"{lidas} {'passagem' if lidas == 1 else 'passagens'}")
    if recebidas > lidas:
        fora = metadados.get("fora_pelo_limite", 0)
        motivos = [f"{fora} não cabiam no limite da prompt"] if fora else []
        if recebidas - fora > lidas:
            motivos.append("a última tentativa leu metade")
        detalhe += f" de {recebidas} ({'; '.join(motivos)})"
    detalhe += ", com a conclusão calculada das relações"
    completadas = metadados.get("completadas") or []
    if completadas:
        detalhe += "; sem o modelo: " + ", ".join(f"«{t}»" for t in completadas)
    if metadados.get("prazo_esgotado"):
        detalhe += "; o prazo não deu para todas as tentativas"
    return detalhe


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

    def top_k(self, data: ClaimInput) -> int:
        """Distinct news items each question keeps: the run's choice, else the default."""
        return data.top_k or self._settings.top_k_per_question

    def exemplo(self, data: ClaimInput) -> dict | None:
        """The stored example this run serves - the picked claim, recorded with the run's number
        of news items per question - or None, and the models run."""
        if not data.exemplo_id:
            return None
        return self._exemplos.get(data.exemplo_id, self.top_k(data), self._lingua)

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

    async def _relevancia_do_modelo(self, claim: str, documentos: list[EvidenceDocument]) -> dict:
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
        return _contagem_de_relevancia(documentos)

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
            return [stance_stage.to_stance(r["id"], r) for r in resultados]
        except (KeyError, TypeError, ValidationError) as erro:
            raise StageFailure("stance", Texto("classificador_invalido", erro=erro)) from erro

    async def _artigo_do_modelo(self, data: ClaimInput, resultado: RunResult) -> dict:
        """The article the chosen model writes from the consolidated evidence, with what it needs
        to know of each passage: its relation, its offsets, and the news item's headline and
        date."""
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
                data.claim, data.claim_date.isoformat(), data.context, passagens, data.redator
            )
        except InferenceUnavailable as erro:
            raise StageSkipped(f"modelo de redação indisponível: {erro}") from erro
        except InferenceError as erro:
            raise StageFailure("article", erro) from erro

    # --- Execution ----------------------------------------------------------- #

    async def run(self, data: ClaimInput, run_id: str | None = None) -> AsyncIterator[dict]:
        # The queue names the run when it takes it in (`fila.py`).
        run_id = run_id or uuid.uuid4().hex[:12]
        # The run records the number of news items per question it used, chosen or not.
        top_k = self.top_k(data)
        data = data.model_copy(update={"top_k": top_k})
        exemplo = self.exemplo(data)
        if exemplo is not None:
            for evento in corrida.eventos(exemplo, run_id, data):
                yield evento
            return

        relatorios: dict[StageName, StageReport] = {
            nome: StageReport(name=nome, label=STAGE_LABELS[nome], status="pending")
            for nome in STAGE_ORDER
        }
        resultado = RunResult(run_id=run_id, input=data, stages=list(relatorios.values()))

        yield {"type": "start", "run_id": run_id,
               "stages": [r.model_dump() for r in relatorios.values()]}

        documentos: list[EvidenceDocument] = []

        try:
            for nome in STAGE_ORDER:
                motivo = SEM_MODELO.get(nome)
                if motivo is None and not self._settings.lusa_configured:
                    motivo = DEPENDEM_DO_CORPUS.get(nome)
                if motivo is not None:
                    relatorios[nome].status = "skipped"
                    relatorios[nome].detail = motivo
                    yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                    continue

                relatorios[nome].status = "running"
                yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                inicio = time.perf_counter()
                dados: dict[str, Any] = {}

                if nome == "questions":
                    resultado.questions = await self._perguntas_do_modelo(data)
                    detalhe = "geradas pelo modelo de question generation"
                    relatorios[nome].stats = {"perguntas": len(resultado.questions)}
                    dados = {"questions": [q.model_dump() for q in resultado.questions]}

                elif nome == "retrieval":
                    try:
                        documentos, estatisticas = await retrieval_stage.retrieve(
                            self._lusa, resultado.questions, data.claim_date,
                            top_k, self._settings.lusa_concurrency,
                        )
                    except LusaError as erro:
                        raise StageFailure("retrieval", erro) from erro
                    detalhe = "notícias recuperadas no corpus LUSA"
                    relatorios[nome].stats = estatisticas

                elif nome == "dedup":
                    # The search asked for more than the cut, which applies here, once versions
                    # are merged.
                    resultado.documents, estatisticas = retrieval_stage.deduplicate(
                        documentos, top_k
                    )
                    detalhe = (
                        f"{estatisticas['repetidos']} repetições e "
                        f"{estatisticas['reemissoes']} reemissões da mesma notícia"
                    )
                    relatorios[nome].stats = estatisticas
                    dados = {"documents": [d.resumo() for d in resultado.documents]}

                elif nome == "relevance":
                    estatisticas = await self._relevancia_do_modelo(data.claim, resultado.documents)
                    detalhe = (
                        f"{estatisticas['relevantes']} de {estatisticas['notícias']} notícias "
                        f"({estatisticas['percentagem']}%) falam do assunto da claim "
                        "(relevância do modelo)"
                    )
                    relatorios[nome].stats = estatisticas
                    dados = {"documents": [d.resumo() for d in resultado.documents]}

                elif nome == "excerpts":
                    for documento in resultado.documents:
                        documento.excerpts = (
                            build_excerpts(documento.doc_id, documento.content)
                            if documento.relevant else []
                        )
                    detalhe = "janelas de 3 frases, a avançar uma frase de cada vez"
                    relatorios[nome].stats = {
                        "documentos": sum(1 for d in resultado.documents if d.relevant),
                        "excertos": sum(len(d.excerpts) for d in resultado.documents),
                    }

                elif nome == "stance":
                    stances = await self._classificar_com_modelo(data.claim, resultado.documents)
                    consolidacao = evidencia.consolidar(resultado.documents, stances)
                    decisivos = consolidacao.decisivos
                    resultado.evidence_passages = consolidacao.evidencia
                    resultado.repeated_passages = consolidacao.repetidas
                    estatisticas = consolidacao.contagem
                    n = estatisticas["evidencia"]
                    detalhe = (
                        f"{estatisticas['supported']} apoiam, "
                        f"{estatisticas['refuted']} contrariam, "
                        f"{estatisticas['nei']} de contexto (um por notícia que não decide); "
                        f"{n} {'passagem segue' if n == 1 else 'passagens seguem'} para o artigo"
                    )
                    if estatisticas["juntos"]:
                        detalhe += ", com as seguidas da mesma notícia e relação juntas numa só"
                    resultado.stances = stances
                    resultado.decisive_excerpt_ids = decisivos
                    relatorios[nome].stats = estatisticas
                    dados = {
                        "stances": [s.model_dump() for s in stances],
                        "decisive": decisivos,
                    }

                else:
                    try:
                        resposta = await self._artigo_do_modelo(data, resultado)
                    except StageSkipped as motivo:
                        relatorios[nome].status = "skipped"
                        relatorios[nome].detail = str(motivo)
                        yield {"type": "stage", "stage": relatorios[nome].model_dump()}
                        continue
                    artigo = article_stage.do_modelo(resposta, resultado.documents,
                                                     REDATORES[data.redator],
                                                     resultado.repeated_passages,
                                                     {s.excerpt_id: s.label for s in resultado.stances})
                    resultado.articles = [artigo]
                    metadados = resposta.get("metadata") or {}
                    lidas = len(resposta["evidence"])
                    detalhe = _detalhe_do_artigo(metadados, lidas)
                    relatorios[nome].stats = {
                        "citacoes": len(artigo.citations),
                        "evidencias": lidas,
                        "recebidas": metadados.get("passagens_recebidas", lidas),
                        "tentativas": len(metadados.get("tentativas") or []),
                        "completadas": len(metadados.get("completadas") or []),
                        "prazo": int(bool(metadados.get("prazo_esgotado"))),
                    }
                    dados = {"articles": [a.model_dump() for a in resultado.articles]}

                relatorios[nome].status = "done"
                relatorios[nome].provenance = "model"
                relatorios[nome].detail = detalhe
                relatorios[nome].duration_ms = int((time.perf_counter() - inicio) * 1000)
                yield {"type": "stage", "stage": relatorios[nome].model_dump(), **dados}
                if nome == "stance":
                    # The page opens the news items from the stored run, and the article takes
                    # minutes: they are stored now, not only when it is done.
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
                    relatorios[nome].detail = "não executada"
                    yield {"type": "stage", "stage": relatorios[nome].model_dump()}
            resultado.stages = list(relatorios.values())
            resultado.error = mensagem
            yield {"type": "error", "message": mensagem,
                   "result": resultado.model_dump(mode="json")}
