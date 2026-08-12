import pytest
from pydantic import ValidationError

from lc_lab.agent import ask_metric, build_agent
from lc_lab.retriever import demo_retriever
from lc_lab.runnables import intent_chain, word_stream
from lc_lab.structured import Intent, parse_intent
from lc_lab.tools import get_metric_definition, lookup_metric


def test_plain_business_function_is_framework_independent():
    assert "成功请求数" in lookup_metric("success_rate")


def test_tool_has_generated_schema():
    schema = get_metric_definition.args_schema.model_json_schema()
    assert schema["required"] == ["metric_name"]


def test_tool_rejects_missing_argument():
    with pytest.raises(Exception):
        get_metric_definition.invoke({})


def test_permission_error_is_not_hidden():
    with pytest.raises(PermissionError):
        get_metric_definition.invoke({"metric_name": "admin_secret"})


def test_agent_completes_a_real_tool_loop():
    result = build_agent().invoke({"messages": [{"role": "user", "content": "收入怎么定义？"}]})
    messages = result["messages"]
    assert len(messages) == 4
    assert "营业收入" in messages[-1].content


def test_structured_parser_accepts_valid_json():
    result = parse_intent('{"category":"knowledge","reason":"询问定义"}')
    assert result == Intent(category="knowledge", reason="询问定义")


def test_structured_parser_rejects_extra_field():
    with pytest.raises(Exception):
        parse_intent('{"category":"other","reason":"不足","extra":1}')


def test_retriever_uses_standard_invoke_interface():
    results = demo_retriever().invoke("revenue refunds")
    assert results[0].metadata["id"] == "metric-revenue"


def test_runnable_branch():
    assert intent_chain.invoke("Revenue") == "data_query"
    assert intent_chain.invoke("成功率是什么") == "knowledge"


def test_streaming_is_incremental():
    assert list(word_stream.stream("a b")) == ["a ", "b "]

