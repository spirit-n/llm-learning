"""把自建检索逻辑适配为 LangChain Retriever。"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field


TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_]*|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


class KeywordRetriever(BaseRetriever):
    documents: list[Document]
    tenant: str = "demo"
    allowed_sources: set[str] | None = None
    k: int = Field(default=4, ge=1, le=20)
    min_score: float = Field(default=0.1, ge=0)

    def search_with_scores(self, query: str) -> list[tuple[Document, float]]:
        query_terms = _tokens(query)
        if not query_terms:
            return []
        scored: list[tuple[Document, float]] = []
        for document in self.documents:
            metadata = document.metadata
            if metadata.get("tenant", "demo") != self.tenant:
                continue
            if self.allowed_sources is not None and metadata.get("source") not in self.allowed_sources:
                continue
            document_terms = _tokens(document.page_content)
            overlap = len(query_terms & document_terms) / len(query_terms)
            exact_bonus = 0.5 if query.lower() in document.page_content.lower() else 0.0
            score = overlap + exact_bonus
            if score >= self.min_score:
                copy = Document(
                    page_content=document.page_content,
                    metadata={**metadata, "retrieval_score": round(score, 4)},
                )
                scored.append((copy, score))
        return sorted(
            scored,
            key=lambda item: (-item[1], str(item[0].metadata.get("id", ""))),
        )[: self.k]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        return [document for document, _ in self.search_with_scores(query)]


def demo_retriever() -> KeywordRetriever:
    return KeywordRetriever(
        documents=[
            Document(
                page_content="success rate equals successful requests divided by all requests",
                metadata={"id": "metric-success", "tenant": "demo", "source": "metric-spec-v2"},
            ),
            Document(
                page_content="revenue excludes tax and completed refunds",
                metadata={"id": "metric-revenue", "tenant": "demo", "source": "metric-spec-v2"},
            ),
            Document(
                page_content="revenue forecast for acme only",
                metadata={"id": "acme-revenue", "tenant": "acme", "source": "private"},
            ),
        ]
    )
