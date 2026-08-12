import json
import sys
from pathlib import Path

import pytest

from mcp_lab.host import LocalFastMCPTransport, SafeMCPHost
from mcp_lab.models import Principal
from mcp_lab.server import AUTH_GATEWAY, mcp


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
)


pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_live_model_acts_as_host_and_calls_an_mcp_tool():
    settings = LiveLLMSettings.from_env()
    client = OpenAICompatibleChatClient(settings)

    principal = Principal(
        actor_id="live-learner",
        tenant="tenant-a",
        scopes=frozenset({"metrics:read", "schema:read", "query:execute"}),
    )
    host = SafeMCPHost(
        LocalFastMCPTransport(mcp),
        principal,
        auth_context=AUTH_GATEWAY.issue(principal),
    )
    catalog = await host.discover()
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in catalog.tools
    ]
    messages = [
        {"role": "system", "content": "你是 MCP Host。用户问指标定义时必须调用合适的 MCP Tool。"},
        {"role": "user", "content": "success_rate 的正式定义是什么？"},
    ]
    first = client.chat(messages, tools=tools, tool_choice="required")
    calls = first.get("tool_calls") or []
    assert calls, first
    call = calls[0]
    assert call["function"]["name"] == "get_metric_definition"
    arguments = json.loads(call["function"]["arguments"])
    result = await host.call_tool(call["function"]["name"], arguments)
    assert result.ok is True, result
    structured = result.data

    messages.extend(
        [
            first,
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(structured, ensure_ascii=False),
            },
        ]
    )
    final = client.chat(messages, tools=tools)
    assert "成功请求数" in final.get("content", "")
    assert "总请求数" in final.get("content", "")
