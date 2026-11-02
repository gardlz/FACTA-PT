"""Data models of the pipeline, shared by the API, the stages and the run store."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

StanceLabel = Literal["supported", "refuted", "nei"]
LABELS: tuple[StanceLabel, ...] = ("supported", "refuted", "nei")
StageName = Literal[
    "questions", "retrieval", "dedup", "relevance", "excerpts", "stance", "article"
]
StageStatus = Literal["pending", "running", "done", "skipped", "error"]

STAGE_ORDER: tuple[StageName, ...] = (
    "questions", "retrieval", "dedup", "relevance", "excerpts", "stance", "article",
)

# Distinct news items each question keeps, once reissues are merged: the choices a run has.
TOP_K_OPCOES: tuple[int, ...] = (5, 10, 15)

# The models that can write the article, by the id a run picks them with, and their names. The
# first one writes it when a run does not choose.
REDATORES: dict[str, str] = {"gemma": "Gemma 4 E4B", "amalia": "AMALIA-9B-0626-DPO"}


class ClaimInput(BaseModel):
    claim: str = Field(min_length=8, max_length=2000)
    claim_date: date
    context: str = Field(default="", max_length=40000)
    # When set, the page shows the stored example and runs no model.
    exemplo_id: Optional[str] = Field(default=None, max_length=120)
    # Distinct news items each question keeps, one of TOP_K_OPCOES; unset, the configured default.
    top_k: Optional[int] = None
    # The model that writes the article, a key of REDATORES.
    redator: str = next(iter(REDATORES))

    # Strip only the ends, before the length checks: inner spacing is kept as the question
    # generator saw it in training.
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
        if v not in REDATORES:
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
    # The classifier's adjusted logits, one per label.
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
    # Highest `evidencia.prioridade` among its passages; when the article's prompt is full, the
    # passages worth least are left out first.
    priority: float = 0.0
    # Only on a passage the writer does not read (`RunResult.repeated_passages`): the id of the
    # writer's passage whose text it repeats.
    repeats: Optional[str] = None


class EvidenceDocument(BaseModel):
    doc_id: str
    headline: str
    published_at: str
    # None until the relevance stage runs.
    relevant: Optional[bool] = None
    genre: str = ""
    byline: str = ""
    word_count: Optional[int] = None
    content: str = ""
    found_by: list[FoundBy] = Field(default_factory=list)
    excerpts: list[Excerpt] = Field(default_factory=list)

    def resumo(self) -> dict:
        """What the page's timeline needs of a news item, without its text."""
        return {
            "doc_id": self.doc_id,
            "headline": self.headline,
            "published_at": self.published_at,
            "relevant": self.relevant,
        }


class CitedExcerpt(BaseModel):
    """A three-sentence window the entailment classifier labelled, inside a cited passage."""

    excerpt_id: str
    label: StanceLabel
    # Its offsets in the news item's text, and that stretch of the text.
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
    # The classified windows that lie whole inside the cited passage, in document order: one when
    # the passage is a window, several when it joins windows of one relation (`evidencia.juntar`),
    # with any nei window inside it. The page lists them in the news drawer.
    excerpts: list[CitedExcerpt] = Field(default_factory=list)


class ArticleBlock(BaseModel):
    type: Literal["heading", "paragraph"]
    text: str


class Article(BaseModel):
    # The name of the model that wrote it, a value of REDATORES.
    model: str = ""
    title: str
    lead: str
    blocks: list[ArticleBlock]
    citations: list[Citation]


class StageReport(BaseModel):
    name: StageName
    status: StageStatus
    # The failure message, shown on the page when the stage fails.
    detail: str = ""
    # What the page shows of a stage besides its status: the relevance stage's counts
    # (`notícias`, `relevantes`, `percentagem`), and why a skipped stage did not run (`motivo`:
    # `sem_corpus`, `indisponivel` or `por_gerar`), a code the page puts in its own language.
    stats: dict[str, int | float | str] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    input: ClaimInput
    stages: list[StageReport]
    questions: list[Question] = Field(default_factory=list)
    documents: list[EvidenceDocument] = Field(default_factory=list)
    stances: list[ExcerptStance] = Field(default_factory=list)
    # Every supported or refuted passage, as the page's timeline and balance show them.
    decisive_excerpt_ids: list[str] = Field(default_factory=list)
    # What the article writer reads, after evidence consolidation.
    evidence_passages: list[EvidencePassage] = Field(default_factory=list)
    # Passages the writer does not read, because the deduplication found their text in one it
    # does: kept so that no news item loses the last passage of a relation it has, and cited
    # right after the passage they repeat (`evidencia.consolidar`).
    repeated_passages: list[EvidencePassage] = Field(default_factory=list)
    # The article of the run's chosen model; empty when the article stage wrote none.
    articles: list[Article] = Field(default_factory=list)
    error: Optional[str] = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    lusa: dict[str, str | bool]
    inference: dict[str, str | bool]
