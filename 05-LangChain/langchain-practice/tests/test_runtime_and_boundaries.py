import time

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ValidationError

from lc_lab.domain import (
    DEFAULT_CATALOG,
    MetricCatalog,
    MetricDefinition,
    MetricPermissionError,
    UserContext,
)
from lc_lab.model import DemoChatModel, LoopingChatModel
from lc_lab.retriever import KeywordRetriever, demo_retriever
from lc_lab.runnables import request_pipeline
from lc_lab.runtime import AgentPolicy, run_metric_agent
from lc_lab.structured import safe_parse_intent
from lc_lab.tools import (
    MetricLookupInput,
    ToolCallBudget,
    ToolBudgetExceeded,
    build_metric_definition_tool,
    lookup_metric,
)


def test_catalog_does_not_fall_back_to_another_tenant() -> None:
    assert lookup_metric("revenue", context=UserContext(tenant="acme")) == "NOT_FOUND"


def test_domain_permission_is_enforced_without_langchain() -> None:
    with pytest.raises(MetricPermissionError):
        DEFAULT_CATALOG.get("admin_secret", UserContext(tenant="demo"))
    item = DEFAULT_CATALOG.get(
        "admin_secret", UserContext(tenant="demo", roles=frozenset({"admin"}))
    )
    assert item.required_role == "admin"


@pytest.mark.parametrize("name", ["", "Revenue", "../secret", "a" * 65])
def test_tool_schema_rejects_noncanonical_metric_names(name: str) -> None:
    with pytest.raises(ValidationError):
        MetricLookupInput(metric_name=name)


def test_tool_budget_is_checked_before_business_call() -> None:
    budget = ToolCallBudget(1)
    tool = build_metric_definition_tool(budget=budget)
    assert "成功请求数" in tool.invoke({"metric_name": "success_rate"})
    with pytest.raises(ToolBudgetExceeded):
        tool.invoke({"metric_name": "revenue"})
    assert budget.used == 1


def test_runtime_returns_auditable_success() -> None:
    run = run_metric_agent("收入怎么定义？")
    assert run.status == "completed"
    assert run.tool_calls == 1
    assert run.successful_tool_results == 1
    assert [event.kind for event in run.events] == [
        "tool_call",
        "tool_result",
        "model",
    ]
    assert run.elapsed_ms >= 0


class DirectAnswerModel(DemoChatModel):
    """故意绕过工具，用于证明模型自然语言不能伪造任务完成。"""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="我猜成功率是 100%"))]
        )


class SlowAnswerModel(DemoChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        time.sleep(0.08)
        return super()._generate(messages, stop, run_manager, **kwargs)


class SlowCatalog(MetricCatalog):
    def get(self, metric_name: str, context: UserContext):
        time.sleep(0.08)
        return DEFAULT_CATALOG.get(metric_name, context)


def test_direct_model_answer_cannot_satisfy_metric_task_contract() -> None:
    run = run_metric_agent("成功率是什么？", model=DirectAnswerModel())
    assert run.status == "failed"
    assert run.error_code == "REQUIRED_TOOL_EVIDENCE_MISSING"
    assert run.successful_tool_results == 0
    assert run.events[-1].kind == "contract_error"


def test_wall_clock_timeout_bounds_model_or_tool_loop() -> None:
    started = time.perf_counter()
    run = run_metric_agent(
        "成功率是什么？",
        model=SlowAnswerModel(),
        policy=AgentPolicy(wall_clock_timeout_seconds=0.01),
    )
    elapsed = time.perf_counter() - started
    assert run.status == "failed"
    assert run.error_code == "AGENT_TIMEOUT"
    assert elapsed < 0.06
    assert run.events[0].kind == "runtime_error"


def test_wall_clock_timeout_also_bounds_slow_tool_backend() -> None:
    run = run_metric_agent(
        "成功率是什么？",
        catalog=SlowCatalog([]),
        policy=AgentPolicy(wall_clock_timeout_seconds=0.01),
    )
    assert run.status == "failed"
    assert run.error_code == "AGENT_TIMEOUT"


def test_runtime_accepts_catalog_dependency_instead_of_using_hidden_global() -> None:
    catalog = MetricCatalog(
        [
            MetricDefinition(
                name="revenue",
                definition="ACME 营业收入口径",
                tenant="acme",
                version="1",
            )
        ]
    )
    run = run_metric_agent(
        "收入怎么定义？",
        context=UserContext(tenant="acme"),
        catalog=catalog,
    )
    assert "ACME 营业收入口径" in run.answer


def test_runtime_rejects_invalid_input_without_model_call() -> None:
    run = run_metric_agent("   ")
    assert run.status == "rejected"
    assert run.error_code == "INVALID_INPUT"
    assert run.events == []


def test_runtime_reports_permission_error_and_redacts_metric_name() -> None:
    run = run_metric_agent("admin 的秘密指标是什么？")
    assert run.error_code == "PERMISSION_DENIED"
    assert "admin_secret" not in run.events[0].detail


def test_runtime_stops_a_model_that_never_finishes() -> None:
    run = run_metric_agent(
        "成功率",
        model=LoopingChatModel(),
        policy=AgentPolicy(recursion_limit=20, max_tool_calls=1),
    )
    assert run.error_code == "TOOL_BUDGET_EXCEEDED"
    assert run.tool_calls == 1


def test_unknown_metric_is_an_explicit_refusal() -> None:
    run = run_metric_agent("unknown 不存在的指标是什么？")
    assert run.status == "completed"
    assert "没有找到" in run.answer


def test_retriever_filters_tenant_and_returns_score_metadata() -> None:
    results = demo_retriever().invoke("revenue forecast")
    assert [item.metadata["id"] for item in results] == ["metric-revenue"]
    assert results[0].metadata["retrieval_score"] > 0


def test_retriever_source_allowlist_can_remove_all_candidates() -> None:
    base = demo_retriever()
    retriever = KeywordRetriever(
        documents=base.documents,
        tenant="demo",
        allowed_sources={"missing-source"},
    )
    assert retriever.invoke("revenue") == []


def test_safe_structured_parse_keeps_failure_as_data() -> None:
    invalid_json = safe_parse_intent("not-json")
    invalid_schema = safe_parse_intent('{"category":"wrong","reason":"x"}')
    assert invalid_json.ok is False
    assert invalid_schema.ok is False


def test_request_pipeline_exposes_normalization_and_route() -> None:
    result = request_pipeline.invoke("  查询 Revenue  ")
    assert result == {
        "normalized_question": "查询 revenue",
        "route": "data_query",
        "char_count": len("查询 revenue"),
    }


def test_metric_definition_model_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MetricDefinition(
            name="x",
            definition="x",
            tenant="demo",
            version="1",
            unexpected=True,
        )
