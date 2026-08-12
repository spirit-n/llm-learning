from rag_lab.context import build_context
from rag_lab.data import GOLDEN_CASES
from rag_lab.evaluation import evaluate_rankings
from rag_lab.indexes import reciprocal_rank_fusion
from rag_lab.pipeline import build_demo_pipeline


def test_chunk_ids_and_versions_are_preserved() -> None:
    pipeline = build_demo_pipeline()
    ids = {chunk.chunk_id for chunk in pipeline.chunks}
    assert "revenue-v2#h1" in ids
    assert next(chunk for chunk in pipeline.chunks if chunk.chunk_id == "revenue-v1#h1").is_latest is False


def test_retrieval_filters_old_versions() -> None:
    hits = build_demo_pipeline().retrieve("营业收入定义", strategy="bm25", top_k=5)
    assert all(hit.chunk.doc_id != "revenue-v1" for hit in hits)


def test_retrieval_filters_other_tenants() -> None:
    pipeline = build_demo_pipeline()
    demo_hits = pipeline.retrieve("企业折扣", strategy="bm25", top_k=5, tenant="demo")
    acme_hits = pipeline.retrieve("企业折扣", strategy="bm25", top_k=5, tenant="acme")
    assert all(hit.chunk.doc_id != "private-policy" for hit in demo_hits)
    assert acme_hits[0].chunk.doc_id == "private-policy"


def test_bm25_recalls_exact_error_code() -> None:
    hits = build_demo_pipeline().retrieve("E102 是什么错误", strategy="bm25", top_k=3)
    assert hits[0].chunk.chunk_id == "error-e102#h1"


def test_rrf_uses_ranks_instead_of_raw_scores() -> None:
    pipeline = build_demo_pipeline()
    dense = pipeline.retrieve("E102", strategy="dense", top_k=3)
    bm25 = pipeline.retrieve("E102", strategy="bm25", top_k=3)
    fused = reciprocal_rank_fusion([dense, bm25], top_k=3)
    assert fused[0].chunk.chunk_id == "error-e102#h1"
    assert fused[0].retriever == "hybrid"


def test_context_builder_deduplicates_and_keeps_citations() -> None:
    hits = build_demo_pipeline().retrieve("营业收入", strategy="hybrid", top_k=3)
    context, citations = build_context([hits[0], hits[0]], token_budget=100)
    assert citations == [hits[0].chunk.chunk_id]
    assert context.count(hits[0].chunk.chunk_id) == 1


def test_evaluation_reports_recall_and_mrr() -> None:
    pipeline = build_demo_pipeline()
    rankings = [pipeline.retrieve(case.question, strategy="hybrid", top_k=3) for case in GOLDEN_CASES]
    report = evaluate_rankings("hybrid", GOLDEN_CASES, rankings, k=3)
    assert report.samples == len(GOLDEN_CASES)
    assert report.recall_at_k >= 0.8
    assert report.mrr > 0


def test_answer_contains_existing_citation() -> None:
    pipeline = build_demo_pipeline()
    answer = pipeline.ask("E102 是什么报错？")
    chunk_ids = {chunk.chunk_id for chunk in pipeline.chunks}
    assert answer.citations
    assert set(answer.citations) <= chunk_ids
    assert answer.citations[0] in answer.answer

