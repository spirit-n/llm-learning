from __future__ import annotations

from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .chunking import chunk_documents
from .context import answer_from_context
from .data import DOCUMENTS
from .indexes import BM25Index, DenseIndex, reciprocal_rank_fusion, rerank
from .models import (
    Document,
    RAGAnswer,
    RetrievalFilters,
    RetrievalResult,
    SearchHit,
    StageTrace,
)


Strategy = Literal["dense", "bm25", "hybrid", "rerank"]


class RAGConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_multiplier: int = Field(default=3, ge=1, le=20)
    min_candidates: int = Field(default=10, ge=1, le=100)
    chunk_tokens: int = Field(default=120, ge=20, le=2000)
    chunk_overlap: int = Field(default=20, ge=0)
    min_answer_relevance: float = Field(default=0.2, ge=0.0, le=1.0)


class RAGPipeline:
    def __init__(self, documents: list[Document], *, config: RAGConfig | None = None) -> None:
        self.config = config or RAGConfig()
        if self.config.chunk_overlap >= self.config.chunk_tokens:
            raise ValueError("chunk_overlap 必须小于 chunk_tokens")
        self.chunks = chunk_documents(
            documents,
            max_tokens=self.config.chunk_tokens,
            overlap_tokens=self.config.chunk_overlap,
        )
        self.dense = DenseIndex(self.chunks)
        self.bm25 = BM25Index(self.chunks)

    def retrieve_with_trace(
        self,
        query: str,
        *,
        strategy: Strategy = "hybrid",
        top_k: int = 5,
        filters: RetrievalFilters,
    ) -> RetrievalResult:
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空")
        if top_k <= 0 or top_k > 50:
            raise ValueError("top_k 必须在 1..50")
        if strategy not in {"dense", "bm25", "hybrid", "rerank"}:
            raise ValueError(f"未知检索策略: {strategy}")

        candidate_k = max(
            top_k * self.config.candidate_multiplier, self.config.min_candidates
        )
        search_args = {
            "top_k": candidate_k,
            "tenant": filters.tenant,
            "allowed_sources": filters.allowed_sources,
            "latest_only": filters.latest_only,
            "min_score": filters.min_score,
        }
        traces: list[StageTrace] = []
        if strategy == "dense":
            started = perf_counter()
            dense_hits = self.dense.search(query, **search_args)
            traces.append(
                StageTrace(
                    stage="dense",
                    input_count=len(self.chunks),
                    output_count=len(dense_hits),
                    elapsed_ms=(perf_counter() - started) * 1000,
                    details={"candidate_k": candidate_k},
                )
            )
            hits = dense_hits[:top_k]
            return RetrievalResult(query=query, strategy=strategy, hits=hits, traces=traces)

        if strategy == "bm25":
            started = perf_counter()
            bm25_hits = self.bm25.search(query, **search_args)
            traces.append(
                StageTrace(
                    stage="bm25",
                    input_count=len(self.chunks),
                    output_count=len(bm25_hits),
                    elapsed_ms=(perf_counter() - started) * 1000,
                    details={"candidate_k": candidate_k},
                )
            )
            hits = bm25_hits[:top_k]
            return RetrievalResult(query=query, strategy=strategy, hits=hits, traces=traces)

        # hybrid/rerank 才需要两路召回；单路策略不应默默支付另一条索引的成本。
        started = perf_counter()
        dense_hits = self.dense.search(query, **search_args)
        traces.append(
            StageTrace(
                stage="dense",
                input_count=len(self.chunks),
                output_count=len(dense_hits),
                elapsed_ms=(perf_counter() - started) * 1000,
                details={"candidate_k": candidate_k},
            )
        )
        started = perf_counter()
        bm25_hits = self.bm25.search(query, **search_args)
        traces.append(
            StageTrace(
                stage="bm25",
                input_count=len(self.chunks),
                output_count=len(bm25_hits),
                elapsed_ms=(perf_counter() - started) * 1000,
                details={"candidate_k": candidate_k},
            )
        )
        started = perf_counter()
        hybrid_hits = reciprocal_rank_fusion([dense_hits, bm25_hits], top_k=candidate_k)
        traces.append(
            StageTrace(
                stage="rrf",
                input_count=len(dense_hits) + len(bm25_hits),
                output_count=len(hybrid_hits),
                elapsed_ms=(perf_counter() - started) * 1000,
            )
        )
        if strategy == "hybrid":
            hits = hybrid_hits[:top_k]
            return RetrievalResult(query=query, strategy=strategy, hits=hits, traces=traces)

        started = perf_counter()
        hits = rerank(query, hybrid_hits, top_k=top_k)
        traces.append(
            StageTrace(
                stage="rerank",
                input_count=len(hybrid_hits),
                output_count=len(hits),
                elapsed_ms=(perf_counter() - started) * 1000,
            )
        )
        return RetrievalResult(query=query, strategy=strategy, hits=hits, traces=traces)

    def retrieve(
        self,
        query: str,
        *,
        strategy: Strategy = "hybrid",
        top_k: int = 5,
        tenant: str = "demo",
        allowed_sources: set[str] | None = None,
    ) -> list[SearchHit]:
        return self.retrieve_with_trace(
            query,
            strategy=strategy,
            top_k=top_k,
            filters=RetrievalFilters(
                tenant=tenant,
                allowed_sources=allowed_sources,
            ),
        ).hits

    def ask(
        self,
        query: str,
        *,
        strategy: Strategy = "rerank",
        top_k: int = 3,
        tenant: str = "demo",
        token_budget: int = 160,
    ) -> RAGAnswer:
        return answer_from_context(
            self.retrieve(query, strategy=strategy, top_k=top_k, tenant=tenant),
            token_budget=token_budget,
            query=query,
            min_relevance=self.config.min_answer_relevance,
        )


def build_demo_pipeline() -> RAGPipeline:
    return RAGPipeline(DOCUMENTS)
