from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict

from .models import Chunk, SearchHit
from .text import cosine, term_counts, tokenize


class HashingEmbedder:
    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            # Python 内置 hash 每个进程会随机化；索引落盘后会失配，所以用稳定摘要。
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self.dimensions
            sign = 1.0 if digest[0] & 1 else -1.0
            vector[bucket] += sign
        return vector


class DenseIndex:
    def __init__(self, chunks: list[Chunk], embedder: HashingEmbedder | None = None) -> None:
        self.chunks = chunks
        self.embedder = embedder or HashingEmbedder()
        self.vectors = {
            chunk.chunk_id: self.embedder.embed(f"{chunk.title} {chunk.section} {chunk.text}")
            for chunk in chunks
        }

    def search(
        self,
        query: str,
        *,
        top_k: int,
        tenant: str,
        allowed_sources: set[str] | None = None,
        latest_only: bool = True,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        query_vector = self.embedder.embed(query)
        scored = [
            (chunk, cosine(query_vector, self.vectors[chunk.chunk_id]))
            for chunk in self.chunks
            if chunk.tenant == tenant
            and (not latest_only or chunk.is_latest)
            and (allowed_sources is None or chunk.source in allowed_sources)
        ]
        scored = [item for item in scored if item[1] > min_score]
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [
            SearchHit(
                chunk=chunk,
                score=score,
                rank=rank,
                retriever="dense",
                component_scores={"dense": score},
            )
            for rank, (chunk, score) in enumerate(scored[:top_k], start=1)
        ]


class BM25Index:
    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.term_frequencies = {chunk.chunk_id: term_counts(chunk.text) for chunk in chunks}
        self.lengths = {
            chunk_id: sum(counts.values())
            for chunk_id, counts in self.term_frequencies.items()
        }

    def search(
        self,
        query: str,
        *,
        top_k: int,
        tenant: str,
        allowed_sources: set[str] | None = None,
        latest_only: bool = True,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        query_terms = tokenize(query)
        candidates = [
            chunk
            for chunk in self.chunks
            if chunk.tenant == tenant
            and (not latest_only or chunk.is_latest)
            and (allowed_sources is None or chunk.source in allowed_sources)
        ]
        scores: list[tuple[Chunk, float]] = []
        # DF 也按权限后的候选集计算，避免其他租户文档影响当前租户排序。
        document_frequency: Counter[str] = Counter()
        for chunk in candidates:
            document_frequency.update(self.term_frequencies[chunk.chunk_id].keys())
        total_documents = len(candidates)
        average_length = (
            sum(self.lengths[chunk.chunk_id] for chunk in candidates)
            / max(total_documents, 1)
        )
        for chunk in candidates:
            score = 0.0
            frequencies = self.term_frequencies[chunk.chunk_id]
            length = self.lengths[chunk.chunk_id]
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = document_frequency[term]
                idf = math.log(1 + (total_documents - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / average_length
                )
                score += idf * frequency * (self.k1 + 1) / denominator
            if score > min_score:
                scores.append((chunk, score))
        scores.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [
            SearchHit(
                chunk=chunk,
                score=score,
                rank=rank,
                retriever="bm25",
                component_scores={"bm25": score},
            )
            for rank, (chunk, score) in enumerate(scores[:top_k], start=1)
        ]


def reciprocal_rank_fusion(rankings: list[list[SearchHit]], *, top_k: int, k: int = 60) -> list[SearchHit]:
    scores: defaultdict[str, float] = defaultdict(float)
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        for hit in ranking:
            chunks[hit.chunk.chunk_id] = hit.chunk
            scores[hit.chunk.chunk_id] += 1 / (k + hit.rank)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:top_k]
    return [
        SearchHit(
            chunk=chunks[chunk_id],
            score=scores[chunk_id],
            rank=rank,
            retriever="hybrid",
            component_scores={
                hit.retriever: hit.score
                for ranking in rankings
                for hit in ranking
                if hit.chunk.chunk_id == chunk_id
            },
        )
        for rank, chunk_id in enumerate(ordered, start=1)
    ]


def rerank(query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
    query_terms = set(tokenize(query))
    rescored = []
    for hit in hits:
        chunk_terms = set(tokenize(hit.chunk.text + " " + hit.chunk.title))
        overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
        exact_bonus = sum(1 for term in query_terms if len(term) > 1 and term in hit.chunk.text)
        rescored.append((hit.chunk, overlap + exact_bonus + hit.score))
    rescored.sort(key=lambda item: (-item[1], item[0].chunk_id))
    component_scores = {hit.chunk.chunk_id: hit.component_scores for hit in hits}
    return [
        SearchHit(
            chunk=chunk,
            score=score,
            rank=rank,
            retriever="rerank",
            component_scores={**component_scores[chunk.chunk_id], "rerank": score},
        )
        for rank, (chunk, score) in enumerate(rescored[:top_k], start=1)
    ]
