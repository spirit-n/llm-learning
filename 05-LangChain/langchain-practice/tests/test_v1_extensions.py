import pytest

from lc_lab.agent import build_agent
from lc_lab.structured import Intent
from lc_lab.structured_agent import OfflineStructuredModel, build_structured_agent


def test_middleware_actually_wraps_agent_tool_execution():
    events = []
    result = build_agent(tool_audit=events).invoke({"messages": [{"role": "user", "content": "收入怎么定义？"}]})
    assert "营业收入" in result["messages"][-1].content
    assert events == [{"tool": "get_metric_definition", "stage": "started"},
                      {"tool": "get_metric_definition", "stage": "completed"}]
    assert "args" not in str(events)


def test_middleware_does_not_hide_authorization_failure():
    events = []
    with pytest.raises(PermissionError):
        build_agent(tool_audit=events).invoke({"messages": [{"role": "user", "content": "admin"}]})
    assert events[-1]["stage"] == "failed"


@pytest.mark.parametrize("strategy", ["provider", "tool"])
def test_both_strategies_return_validated_structured_response(strategy):
    result = build_structured_agent(OfflineStructuredModel(), strategy=strategy,
                                   provider_native_supported=True).invoke(
        {"messages": [{"role": "user", "content": "成功率是什么"}]}, config={"recursion_limit": 6})
    assert isinstance(result["structured_response"], Intent)
    assert result["structured_response"].category == "knowledge"


def test_provider_strategy_requires_capability_confirmation():
    with pytest.raises(ValueError, match="verified"):
        build_structured_agent(OfflineStructuredModel(), strategy="provider")
