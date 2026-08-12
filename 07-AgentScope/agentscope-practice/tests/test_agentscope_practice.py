import pytest

from agentscope.message import TextBlock, UserMsg

from as_lab.agents import build_metric_agent
from as_lab.routing import choose_agent, route_request
from as_lab.tools import build_toolkit, get_metric_definition


def test_message_has_explicit_role_and_content_blocks():
    message = UserMsg(name="learner", content="hello")
    assert message.role == "user"
    assert isinstance(message.content[0], TextBlock)


@pytest.mark.asyncio
async def test_toolkit_generates_json_schema():
    schema = (await build_toolkit().get_tool_schemas())[0]["function"]
    assert schema["name"] == "get_metric_definition"
    assert schema["parameters"]["required"] == ["metric_name"]


def test_business_function_can_be_tested_without_agent():
    assert "成功请求数" in get_metric_definition("success_rate")


def test_restricted_metric_is_rejected():
    with pytest.raises(PermissionError):
        get_metric_definition("admin_secret")


@pytest.mark.asyncio
async def test_one_agent_completes_tool_loop():
    reply = await build_metric_agent().reply(UserMsg(name="learner", content="收入是什么？"))
    assert reply.role == "assistant"
    assert "营业收入" in reply.get_text_content()


def test_deterministic_router():
    assert choose_agent("成功率是什么") == "metric_agent"
    assert choose_agent("RAG 是什么") == "knowledge_agent"


@pytest.mark.asyncio
async def test_metric_route_uses_metric_agent():
    result = await route_request("success_rate 指标怎么定义？")
    assert result.target == "metric_agent"
    assert "成功率" in result.response.get_text_content()


@pytest.mark.asyncio
async def test_knowledge_route_skips_metric_tool():
    result = await route_request("RAG 是什么？")
    assert result.target == "knowledge_agent"
    assert "外部证据" in result.response.get_text_content()
