"""Optional real retrieval adapters. Imports never download or initialize models."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from .models import SearchHit


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model) -> None:
        self.model = model

    @classmethod
    def from_local(cls, path: str):
        """Only use an already downloaded model; never fetch a Hub model implicitly."""
        if not Path(path).is_dir():
            raise ValueError("embedding model must be an existing local directory")
        from sentence_transformers import SentenceTransformer

        return cls(SentenceTransformer(path, local_files_only=True))

    def embed(self, text: str) -> list[float]:
        vector = [float(value) for value in self.model.encode(text, normalize_embeddings=True)]
        if not vector or not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding must be a nonempty finite vector")
        return vector


class CrossEncoderReranker:
    def __init__(self, model) -> None:
        self.model = model

    @classmethod
    def from_local(cls, path: str):
        if not Path(path).is_dir():
            raise ValueError("reranker model must be an existing local directory")
        from sentence_transformers import CrossEncoder

        return cls(CrossEncoder(path, local_files_only=True))

    def __call__(self, query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not hits:
            return []
        scores = [float(value) for value in self.model.predict(
            [(query, f"{hit.chunk.title}\n{hit.chunk.text}") for hit in hits]
        )]
        if len(scores) != len(hits) or not all(math.isfinite(value) for value in scores):
            raise ValueError("reranker must return one finite scalar per candidate")
        ranked = sorted(zip(hits, scores, strict=True), key=lambda pair: (-pair[1], pair[0].chunk.chunk_id))
        return [hit.model_copy(update={
            "score": score, "rank": rank, "retriever": "rerank",
            "component_scores": {**hit.component_scores, "rerank": score},
        }) for rank, (hit, score) in enumerate(ranked[:top_k], start=1)]
