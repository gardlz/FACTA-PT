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


class ClaimInput(BaseModel):
    claim: str = Field(min_length=8, max_length=2000)
    claim_date: date
    context: str = Field(default="", max_length=40000)
    # When set, the page shows the stored example and runs no model.
    exemplo_id: Optional[str] = Field(default=None, max_length=120)

    # Strip only the ends, before the length checks: inner spacing is kept as the question
    # generator saw it in training.
    @field_validator("claim", "context", mode="before")
    @classmethod
    def _limpar(cls, v):
        return v.strip() if isinstance(v, str) else v


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


class ArticleBlock(BaseModel):
    type: Literal["heading", "paragraph"]
    text: str


class Article(BaseModel):
    title: str
    lead: str
    blocks: list[ArticleBlock]
    citations: list[Citation]


class StageReport(BaseModel):
    name: StageName
    status: StageStatus
    # The failure message, shown on the page when the stage fails.
    detail: str = ""


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
    article: Optional[Article] = None
    error: Optional[str] = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    lusa: dict[str, str | bool]
    inference: dict[str, str | bool]
