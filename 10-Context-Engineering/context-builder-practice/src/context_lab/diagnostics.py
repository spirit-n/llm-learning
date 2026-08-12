"""用 manifest 定位错误属于 Context 构建还是模型使用阶段。"""

from collections import Counter

from pydantic import BaseModel, Field

from context_lab.models import ContextManifest


class TruncationRecord(BaseModel):
    id: str
    source: str
    original_tokens: int
    final_tokens: int
    removed_tokens: int
    retained_ratio: float


class BuildDiagnostics(BaseModel):
    budget_utilization: float
    remaining_tokens: int
    drop_counts: dict[str, int]
    truncations: list[TruncationRecord]
    total_truncated_tokens: int
    warnings: list[str] = Field(default_factory=list)


def diagnose_build(manifest: ContextManifest) -> BuildDiagnostics:
    """把机器可读 manifest 汇总成人能快速排查的诊断结果。"""

    drop_counts = Counter(entry.reason for entry in manifest.dropped)
    truncations = [
        TruncationRecord(
            id=entry.id,
            source=entry.source,
            original_tokens=entry.original_tokens,
            final_tokens=entry.tokens,
            removed_tokens=entry.truncated_tokens,
            retained_ratio=round(entry.tokens / entry.original_tokens, 4) if entry.original_tokens else 1.0,
        )
        for entry in manifest.included
        if entry.truncated_tokens > 0
    ]
    available = manifest.budget.available_tokens
    utilization = manifest.total_tokens / available if available else 0.0
    warnings: list[str] = []

    if drop_counts["token_budget"]:
        warnings.append("整体预算导致证据未进入上下文；先检查排序和 reserved_tokens。")
    if drop_counts["layer_token_budget"]:
        warnings.append("分层预算已触顶；检查该层配额是否符合当前任务。")
    if drop_counts["expired"] or drop_counts["stale"]:
        warnings.append("存在过期或陈旧证据；应刷新来源，而不是简单提高优先级。")
    if any(record.retained_ratio < 0.5 for record in truncations):
        warnings.append("有内容保留不足一半；回答失败时应回查 source 原文。")
    if utilization < 0.5 and (drop_counts["layer_token_budget"] or drop_counts["low_relevance"]):
        warnings.append("整体预算仍有空间但内容被策略过滤；这是选择策略问题，不是窗口不够。")

    return BuildDiagnostics(
        budget_utilization=round(utilization, 4),
        remaining_tokens=manifest.budget.remaining_tokens,
        drop_counts=dict(sorted(drop_counts.items())),
        truncations=truncations,
        total_truncated_tokens=sum(value.removed_tokens for value in truncations),
        warnings=warnings,
    )


def diagnose_evidence(
    manifest: ContextManifest,
    evidence_id: str,
    *,
    expected_version: int | None = None,
    answer_used_evidence: bool = True,
) -> str:
    """针对一条证据给出稳定诊断码，便于评测和告警聚合。"""

    included = next((item for item in manifest.included if item.id == evidence_id), None)
    if included is None:
        dropped = next((item for item in manifest.dropped if item.id == evidence_id), None)
        return f"evidence_not_seen:{dropped.reason if dropped else 'not_selected'}"
    if expected_version is not None and included.version != expected_version:
        return "wrong_version_seen"
    if "compressed_with_source" in included.transformations:
        return "evidence_compressed_check_original"
    if not answer_used_evidence:
        return "model_unfaithful_to_visible_context"
    return "evidence_visible_and_used"
