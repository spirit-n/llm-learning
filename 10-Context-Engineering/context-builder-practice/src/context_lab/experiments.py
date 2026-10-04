"""可重复的 Context Engineering 对照实验。"""

from __future__ import annotations

from collections import Counter

from context_lab.builder import ContextBuilder, REQUEST_TASK_ID
from context_lab.models import BuildRequest, BuildResult, ContextItem
from context_lab.compaction import run_compaction_experiment
from context_lab.tool_discovery import run_tool_discovery_experiment


def sample_items() -> list[ContextItem]:
    return [
        ContextItem(
            id="system",
            layer="system",
            source="policy-v2",
            source_kind="system_policy",
            content="不得泄露跨租户数据。",
            required=True,
            priority=100,
        ),
        ContextItem(
            id="schema-needed",
            layer="domain",
            source="daily_metrics",
            source_kind="authoritative_catalog",
            content="daily_metrics(success_count, request_count)",
            relevance=1.0,
        ),
        ContextItem(
            id="schema-noise",
            layer="domain",
            source="inventory",
            source_kind="authoritative_catalog",
            content="inventory(sku, warehouse, stock)",
            relevance=0.1,
        ),
        ContextItem(
            id="metric-old",
            layer="retrieved",
            source="metric-v1",
            source_kind="authoritative_catalog",
            content="成功率=成功数/已完成数",
            version=1,
            trust=70,
            conflict_key="success-rate",
        ),
        ContextItem(
            id="metric-new",
            layer="retrieved",
            source="metric-v2",
            source_kind="authoritative_catalog",
            content="成功率=成功请求数/总请求数",
            version=2,
            trust=90,
            conflict_key="success-rate",
        ),
        ContextItem(
            id="history",
            layer="memory",
            source="turns-1-20",
            source_kind="memory",
            content="旧对话。" * 200,
            compressible=True,
            relevance=0.6,
        ),
    ]


def _request(items: list[ContextItem], *, budget: int = 2_000, **kwargs: object) -> BuildRequest:
    return BuildRequest(
        task="定义成功率",
        tenant="tenant-a",
        roles={"analyst"},
        token_budget=budget,
        items=items,
        **kwargs,
    )


def _summary(result: BuildResult) -> dict[str, object]:
    return {
        "tokens": result.manifest.total_tokens,
        "included_ids": [entry.id for entry in result.manifest.included],
        "drop_reasons": dict(Counter(entry.reason for entry in result.manifest.dropped)),
        "truncated_tokens": sum(entry.truncated_tokens for entry in result.manifest.included),
    }


def _selected_evidence_id(result: BuildResult) -> str:
    """对照实验关心候选证据胜者，跳过 Builder 自动加入的任务段。"""

    return next(entry.id for entry in result.manifest.included if entry.id != REQUEST_TASK_ID)


def compare_selection() -> dict[str, dict[str, object]]:
    """全量候选与按相关性选择的对照。"""

    items = sample_items()
    full = ContextBuilder(min_relevance=0).build(_request(items))
    selective = ContextBuilder(min_relevance=0.3).build(_request(items))
    return {"full": _summary(full), "selective": _summary(selective)}


def compare_history_strategies() -> dict[str, dict[str, object]]:
    """全历史、滑动窗口、结构化状态摘要三种策略的 token 对照。"""

    histories = {
        "full_history": "".join(f"第{i}轮：用户与助手讨论了大量中间细节。" for i in range(1, 41)),
        "sliding_window": "".join(f"第{i}轮：最近结论。" for i in range(37, 41)),
        "state_summary": "目标=排查失败率；已确认=接口无发布；待验证=数据库超时。",
    }
    results: dict[str, dict[str, object]] = {}
    for strategy, content in histories.items():
        history = ContextItem(
            id=strategy,
            layer="memory",
            source=strategy,
            source_kind="memory",
            content=content,
        )
        results[strategy] = _summary(ContextBuilder().build(_request([history], budget=4_000)))
    return results


def compare_tool_payloads() -> dict[str, dict[str, object]]:
    """工具原始明细与结构化摘要的对照，并记录究竟裁掉了多少。"""

    raw_rows = "\n".join(f"day=2026-08-{day:02d}, success={900 + day}, total=1000" for day in range(1, 29))
    structured = "period=2026-08-01..28; success=25606; total=28000; source_ref=query-42"
    raw = ContextItem(
        id="raw-tool",
        layer="tool",
        source="query-42",
        source_kind="tool_result",
        content=raw_rows,
        compressible=True,
    )
    summary = ContextItem(
        id="summary-tool",
        layer="tool",
        source="query-42-summary",
        source_kind="tool_result",
        content=structured,
    )
    builder = ContextBuilder(max_item_tokens=90)
    return {
        "raw_compressed": _summary(builder.build(_request([raw]))),
        "structured_summary": _summary(builder.build(_request([summary]))),
    }


def compare_source_priority() -> dict[str, str]:
    """说明“版本号更大”不能越过来源权威级别。"""

    authoritative = ContextItem(
        id="catalog-v2",
        layer="domain",
        source="metric-catalog",
        source_kind="authoritative_catalog",
        content="退款率=退款订单数/支付订单数",
        version=2,
        conflict_key="refund-rate",
    )
    suspicious_newer = ContextItem(
        id="web-v99",
        layer="retrieved",
        source="unverified-web",
        source_kind="retrieval",
        content="退款率=退款金额/营业额",
        version=99,
        conflict_key="refund-rate",
    )
    ranked = ContextBuilder().build(_request([authoritative, suspicious_newer]))

    # 这是故意构造的反例：来源都标成 unknown 时，系统只能依靠版本号判断。
    unranked_items = [
        authoritative.model_copy(update={"source_kind": "unknown"}),
        suspicious_newer.model_copy(update={"source_kind": "unknown"}),
    ]
    unranked = ContextBuilder().build(_request(unranked_items))
    return {
        "without_source_metadata": _selected_evidence_id(unranked),
        "with_source_priority": _selected_evidence_id(ranked),
    }


def compare_layer_budgets() -> dict[str, dict[str, object]]:
    """整体预算相同，比较是否给工具结果预留独立空间。"""

    retrieval = ContextItem(
        id="long-retrieval",
        layer="retrieved",
        source="docs",
        source_kind="retrieval",
        content="检索材料。" * 80,
        token_override=90,
        priority=100,
    )
    tool = ContextItem(
        id="tool-result",
        layer="tool",
        source="query-7",
        source_kind="tool_result",
        content="成功数=95，总数=100",
        token_override=35,
    )
    # v3 会把请求 task 作为必需段计入预算，因此这里为 task 留出额外空间，
    # 仍保持“长检索先占满后续证据”和“分层预算保护工具结果”的对照关系。
    no_quota = ContextBuilder().build(_request([retrieval, tool], budget=130))
    with_quota = ContextBuilder().build(
        _request([retrieval, tool], budget=130, layer_budgets={"retrieved": 60, "tool": 40})
    )
    return {"global_only": _summary(no_quota), "layer_quotas": _summary(with_quota)}


def run_all_experiments() -> dict[str, object]:
    return {
        "selection": compare_selection(),
        "history": compare_history_strategies(),
        "tool_payload": compare_tool_payloads(),
        "source_priority": compare_source_priority(),
        "layer_budget": compare_layer_budgets(),
        "compaction_recovery": run_compaction_experiment(),
        "deferred_tool_discovery": run_tool_discovery_experiment(),
    }
