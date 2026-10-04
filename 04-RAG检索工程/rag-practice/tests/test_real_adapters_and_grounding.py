import pytest

from rag_lab.adapters import CrossEncoderReranker, SentenceTransformerEmbedder
from rag_lab.data import DOCUMENTS
from rag_lab.grounding import ClaimReview, evaluate_grounding
from rag_lab.pipeline import RAGPipeline


class FakeEmbedding:
    def encode(self, text, *, normalize_embeddings):
        assert normalize_embeddings
        return [1.0, float("E102" in text)]


class FakeReranker:
    def predict(self, pairs):
        return list(range(len(pairs)))


def test_optional_models_are_injected_without_import_or_download():
    pipeline = RAGPipeline(DOCUMENTS, embedder=SentenceTransformerEmbedder(FakeEmbedding()),
                           reranker=CrossEncoderReranker(FakeReranker()))
    hits = pipeline.retrieve("E102 是什么报错", strategy="rerank", top_k=3)
    assert hits and all(hit.retriever == "rerank" for hit in hits)
    assert [hit.score for hit in hits] == sorted([hit.score for hit in hits], reverse=True)
    assert all(hit.chunk.tenant == "demo" for hit in hits)


def test_invalid_embedding_and_reranker_outputs_fail():
    class InvalidEmbedding:
        def encode(self, *args, **kwargs):
            return [float("nan")]
    with pytest.raises(ValueError, match="finite"):
        SentenceTransformerEmbedder(InvalidEmbedding()).embed("text")
    hits = RAGPipeline(DOCUMENTS).retrieve("E102", top_k=2)
    class WrongCount:
        def predict(self, pairs):
            return []
    with pytest.raises(ValueError, match="per candidate"):
        CrossEncoderReranker(WrongCount())("E102", hits, top_k=2)


def test_local_model_paths_cannot_implicitly_download(tmp_path):
    for adapter in (SentenceTransformerEmbedder, CrossEncoderReranker):
        with pytest.raises(ValueError, match="local directory"):
            adapter.from_local(str(tmp_path / "missing-model"))


def test_legal_citation_does_not_make_unsupported_claim_faithful():
    answer = "E102 表示支付成功 [manual#h1]"
    def human_review(claim, evidence):
        assert evidence["manual#h1"] == "E102 表示连接超时"
        return ClaimReview(claim=claim, citation_ids=["manual#h1"], supported=False,
                           reason="引用存在，但证据说连接超时，而非支付成功")
    result = evaluate_grounding(answer, {"manual#h1": "E102 表示连接超时"},
                                claims=["E102 表示支付成功"], judge=human_review)
    assert result.citation_ids_valid and result.all_claims_reviewed
    assert not result.faithful


def test_supported_claim_and_review_coverage():
    evidence = {"manual#h1": "E102 表示连接超时"}
    def judge(claim, evidence):
        return ClaimReview(claim=claim, citation_ids=["manual#h1"], supported=True, reason="原文支持")
    report = evaluate_grounding("E102 表示连接超时 [manual#h1]", evidence,
                                claims=["E102 表示连接超时"], judge=judge)
    assert report.faithful
    with pytest.raises(ValueError, match="inventory"):
        evaluate_grounding("x", evidence, claims=[], judge=judge)
