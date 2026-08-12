from __future__ import annotations

import math
from collections import defaultdict

from .models import EvaluationReport, GoldenCase, SearchHit


def evaluate_rankings(strategy: str, cases: list[GoldenCase], rankings: list[list[SearchHit]], *, k: int) -> EvaluationReport:
    if not cases:
        raise ValueError("评测集不能为空")
    if len(cases) != len(rankings):
        raise ValueError("cases 与 rankings 数量必须一致")
    if k <= 0:
        raise ValueError("k 必须大于 0")
    recall_total = 0.0
    precision_total = 0.0
    reciprocal_rank_total = 0.0
    ndcg_total = 0.0
    hit_total = 0.0
    tag_recalls: defaultdict[str, list[float]] = defaultdict(list)
    for case, hits in zip(cases, rankings, strict=True):
        expected = set(case.evidence_chunk_ids)
        retrieved = [hit.chunk.chunk_id for hit in hits[:k]]
        relevant_count = sum(chunk_id in expected for chunk_id in retrieved)
        recall = relevant_count / max(len(expected), 1)
        recall_total += recall
        # 返回不足 k 条时按实际展示数量计算 precision，避免凭空加入负样本。
        precision_total += relevant_count / max(len(retrieved), 1)
        hit_total += float(relevant_count > 0)
        first_rank = next((rank for rank, chunk_id in enumerate(retrieved, start=1) if chunk_id in expected), None)
        reciprocal_rank_total += 0 if first_rank is None else 1 / first_rank
        dcg = sum(
            1 / math.log2(rank + 1)
            for rank, chunk_id in enumerate(retrieved, start=1)
            if chunk_id in expected
        )
        ideal_count = min(len(expected), k)
        ideal_dcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcg_total += dcg / ideal_dcg if ideal_dcg else 0.0
        for tag in case.tags:
            tag_recalls[tag].append(recall)
    samples = len(cases)
    return EvaluationReport(
        strategy=strategy,
        samples=samples,
        recall_at_k=round(recall_total / samples, 3),
        precision_at_k=round(precision_total / samples, 3),
        mrr=round(reciprocal_rank_total / samples, 3),
        ndcg_at_k=round(ndcg_total / samples, 3),
        hit_rate_at_k=round(hit_total / samples, 3),
        tag_recall_at_k={
            tag: round(sum(values) / len(values), 3)
            for tag, values in sorted(tag_recalls.items())
        },
    )
