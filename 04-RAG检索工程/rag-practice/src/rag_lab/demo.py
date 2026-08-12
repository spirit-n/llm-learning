from __future__ import annotations

from .data import GOLDEN_CASES
from .evaluation import evaluate_rankings
from .models import RetrievalFilters
from .pipeline import build_demo_pipeline


def main() -> None:
    pipeline = build_demo_pipeline()
    for strategy in ("dense", "bm25", "hybrid", "rerank"):
        rankings = [pipeline.retrieve(case.question, strategy=strategy, top_k=3, tenant=case.tenant) for case in GOLDEN_CASES]
        print(evaluate_rankings(strategy, GOLDEN_CASES, rankings, k=3).model_dump())

    answer = pipeline.ask("E102 是什么报错？")
    print("\n带引用答案：")
    print(answer.model_dump_json(indent=2))

    traced = pipeline.retrieve_with_trace(
        "E102 是什么报错？",
        strategy="rerank",
        top_k=3,
        filters=RetrievalFilters(tenant="demo"),
    )
    print("\n检索阶段观测：")
    for stage in traced.traces:
        print(stage.model_dump())


if __name__ == "__main__":
    main()
