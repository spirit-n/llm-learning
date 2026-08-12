from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Document(StrictModel):
    doc_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$")
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    is_latest: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(StrictModel):
    chunk_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+#[A-Za-z0-9_.:-]+$")
    doc_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$")
    text: str = Field(min_length=1)
    source: str
    title: str
    section: str
    version: str
    tenant: str
    is_latest: bool
    position: int = Field(ge=0)
    token_count: int = Field(default=0, ge=0)
    content_hash: str = ""


class SearchHit(StrictModel):
    chunk: Chunk
    score: float
    rank: int = Field(ge=1)
    retriever: Literal["dense", "bm25", "hybrid", "rerank"]
    component_scores: dict[str, float] = Field(default_factory=dict)


class RetrievalFilters(StrictModel):
    """必须在召回阶段执行的过滤条件，而不是生成答案后再补救。"""

    tenant: str = Field(min_length=1)
    latest_only: bool = True
    allowed_sources: set[str] | None = None
    min_score: float = Field(default=0.0, ge=0.0)


class StageTrace(StrictModel):
    stage: str
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievalResult(StrictModel):
    query: str
    strategy: Literal["dense", "bm25", "hybrid", "rerank"]
    hits: list[SearchHit]
    traces: list[StageTrace]


class ContextBundle(StrictModel):
    text: str
    citation_ids: list[str]
    used_tokens: int = Field(ge=0)
    dropped_chunk_ids: list[str] = Field(default_factory=list)
    contains_untrusted_instructions: bool = False


class CitationCheck(StrictModel):
    valid: bool
    cited_ids: list[str]
    unknown_ids: list[str]


class GoldenCase(StrictModel):
    case_id: str
    question: str
    evidence_chunk_ids: list[str]
    tenant: str = "demo"
    tags: list[str] = Field(default_factory=list)


class EvaluationReport(StrictModel):
    strategy: str
    samples: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float = 0.0
    hit_rate_at_k: float = 0.0
    tag_recall_at_k: dict[str, float] = Field(default_factory=dict)


class RAGAnswer(StrictModel):
    answer: str
    citations: list[str]
    context: str
    insufficient_evidence: bool
    citation_check: CitationCheck | None = None
    # 拒答时给调用方一个稳定、可观测的原因，而不只返回一句自然语言。
    evidence_reason: str | None = None
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
