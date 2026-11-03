"""Pipeline data contracts, shared by the API and the model adapters."""

import os
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

StanceLabel = Literal["supported", "refuted", "nei"]
LABELS: tuple[StanceLabel, ...] = ("supported", "refuted", "nei")
StageName = Literal[
    "questions", "retrieval", "dedup", "relevance", "excerpts", "stance", "article"
]
StageStatus = Literal["pending", "running", "done", "skipped", "error"]
Provenance = Literal["model", "exemplo"]

STAGE_ORDER: tuple[StageName, ...] = (
    "questions", "retrieval", "dedup", "relevance", "excerpts", "stance", "article",
)

STAGE_LABELS: dict[StageName, str] = {
    "questions": "Geração de perguntas",
    "retrieval": "Recuperação na LUSA",
    "dedup": "Desduplicação de evidência",
    "relevance": "Relevância das notícias",
    "excerpts": "Divisão em excertos",
    "stance": "Classificação claim–excerto",
    "article": "Artigo de verificação",
}

# Distinct news items each question keeps, once reissues are merged: the choices a run has.
TOP_K_OPCOES: tuple[int, ...] = (5, 10, 15)

def nome_do_modelo(modelo: str) -> str:
    """A model's name as the page shows it, from its id on the API:
    `google/gemma-4-26b-a4b-it:free` is "Gemma 4 26B A4B (free)"."""
    base, _, variante = modelo.partition(":")
    partes = [p for p in base.rsplit("/", 1)[-1].split("-") if p and p.lower() != "it"]
    nome = " ".join(p.upper() if any(c.isdigit() for c in p) else p.capitalize() for p in partes)
    return f"{nome} ({variante})" if variante else nome


# The model the Gemma writer runs on OpenRouter (the inference service's ARTICLE_API_MODEL, which
# docker-compose.yml passes here too).
GEMMA_PADRAO = "google/gemma-4-31b-it"

# The models that can write the article, by the name a run chooses them with, and what each is
# called; the first one writes it when a run does not choose.
REDATORES: dict[str, str] = {
    "gemma": nome_do_modelo(os.environ.get("ARTICLE_API_MODEL") or GEMMA_PADRAO),
    "amalia": "AMALIA-9B-0626-DPO",
}
# Writers no longer offered, which runs saved while they were still name: those runs keep loading,
# but no new run can choose one.
REDATORES_ANTIGOS: dict[str, str] = {"amalia_q4": "AMALIA 9B Q4 (Ollama)"}


class ClaimInput(BaseModel):
    claim: str = Field(min_length=8, max_length=2000)
    claim_date: date
    context: str = Field(default="", max_length=40000)
    # When set, the page shows the stored example and runs no model.
    exemplo_id: Optional[str] = Field(default=None, max_length=120)
    # Distinct news items each question keeps, one of TOP_K_OPCOES; unset, the service's default.
    top_k: Optional[int] = None
    # The model that writes the article, one of REDATORES (or of REDATORES_ANTIGOS, in a run saved
    # while it was offered).
    redator: str = next(iter(REDATORES))

    # Only the edges, and before the length limits apply: the inner spacing of claim and
    # context is part of what the question generator was trained on.
    @field_validator("claim", "context", mode="before")
    @classmethod
    def _limpar(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("top_k")
    @classmethod
    def _top_k_previsto(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in TOP_K_OPCOES:
            raise ValueError(f"top_k must be one of {', '.join(map(str, TOP_K_OPCOES))}")
        return v

    @field_validator("redator")
    @classmethod
    def _redator_previsto(cls, v: str) -> str:
        if v not in REDATORES and v not in REDATORES_ANTIGOS:
            raise ValueError(f"redator must be one of {', '.join(REDATORES)}")
        return v


class Question(BaseModel):
    id: str
    index: int
    text: str


class FoundBy(BaseModel):
    question_id: str
    rank: int


class Excerpt(BaseModel):
    id: str
    doc_id: str
    begin: int
    end: int
    text: str


class ExcerptStance(BaseModel):
    excerpt_id: str
    label: StanceLabel
    # The classifier's adjusted logits, one per label. None on the example path, where the
    # label comes from the annotation.
    logits: Optional[dict[StanceLabel, float]] = None

    @field_validator("logits")
    @classmethod
    def _tres_classes(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None and set(v) != set(LABELS):
            raise ValueError(f"logits must cover {LABELS}")
        return v


class EvidencePassage(BaseModel):
    """What the article writer reads: one classified passage, or several consecutive ones of the
    same news item with the same relation, joined."""

    id: str
    doc_id: str
    label: StanceLabel
    begin: int
    end: int
    # The classified passages it is made of, in document order.
    excerpt_ids: list[str]
    # What it is worth to the article, the most of any of its passages (`evidencia.prioridade`).
    # Ranks which passages the article leaves out when they do not fit.
    priority: float = 0.0
    # Only on a passage the writer does not read (`RunResult.repeated_passages`): the id of the
    # writer's passage whose text it repeats.
    repeats: Optional[str] = None


class EvidenceDocument(BaseModel):
    doc_id: str
    headline: str
    published_at: str
    # None until the relevance stage rules; on the example path it applies the annotation.
    relevant: Optional[bool] = None
    genre: str = ""
    topics: list[str] = Field(default_factory=list)
    byline: str = ""
    word_count: Optional[int] = None
    content: str = ""
    found_by: list[FoundBy] = Field(default_factory=list)
    excerpts: list[Excerpt] = Field(default_factory=list)

    def resumo(self) -> dict:
        """The news item without its text, as the page's stage events carry it."""
        return {
            "doc_id": self.doc_id,
            "headline": self.headline,
            "published_at": self.published_at,
            "genre": self.genre,
            "topics": self.topics,
            "byline": self.byline,
            "word_count": self.word_count,
            "relevant": self.relevant,
            "found_by": [f.model_dump() for f in self.found_by],
        }


class CitedExcerpt(BaseModel):
    """One three-sentence window the stance classifier labelled, inside a cited passage."""

    excerpt_id: str
    label: StanceLabel
    # Where it stands in the news item's text, and that stretch of the text.
    begin: int
    end: int
    text: str


class Citation(BaseModel):
    marker: str
    excerpt_id: str
    doc_id: str
    headline: str
    published_at: str
    label: StanceLabel
    excerpt_text: str
    begin: int
    end: int
    # The classified windows that lie inside the cited passage, in document order: one when the
    # passage is a window, several when it joins windows of one relation (`evidencia.juntar`),
    # with any `nei` window that lies inside it (the join never takes in an opposite one). The
    # article cites the passage; these keep each window the classifier read within reach.
    excerpts: list[CitedExcerpt] = Field(default_factory=list)


class ArticleBlock(BaseModel):
    type: Literal["heading", "paragraph"]
    text: str


class Article(BaseModel):
    # The model that wrote it.
    model: str = ""
    title: str
    lead: str
    blocks: list[ArticleBlock]
    citations: list[Citation]


class StageReport(BaseModel):
    name: StageName
    label: str
    status: StageStatus
    provenance: Optional[Provenance] = None
    detail: str = ""
    duration_ms: Optional[int] = None
    stats: dict[str, int | float | str] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    input: ClaimInput
    stages: list[StageReport]
    questions: list[Question] = Field(default_factory=list)
    documents: list[EvidenceDocument] = Field(default_factory=list)
    stances: list[ExcerptStance] = Field(default_factory=list)
    # Every supported or refuted passage. They paint the timeline and count in the balance.
    decisive_excerpt_ids: list[str] = Field(default_factory=list)
    # What the article writers read, after evidence consolidation (model path only).
    evidence_passages: list[EvidencePassage] = Field(default_factory=list)
    # Passages the writers do not read, because the deduplication found their text in one they
    # do, kept so that no news item loses the last passage of a relation it has: listed with
    # their news item in the example files and cited next to the passage they repeat
    # (`evidencia.consolidar`).
    repeated_passages: list[EvidencePassage] = Field(default_factory=list)
    # One article per writer, all from the same evidence.
    articles: list[Article] = Field(default_factory=list)
    error: Optional[str] = None
    # When the finished verification was kept (UTC, ISO 8601); unset on a run under way.
    saved_at: Optional[str] = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    lusa: dict[str, str | bool]
    inference: dict[str, str | bool]
