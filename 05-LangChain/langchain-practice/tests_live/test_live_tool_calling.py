import json
import sys
from pathlib import Path

import pytest

from lc_lab.tools import get_metric_definition


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
)


pytestmark = pytest.mark.live


def test_live_model_uses_langchain_tool_then_answers():
    settings = LiveLLMSettings.from_env()
    client = OpenAICompatibleChatClient(settings)

    function_schema = {
        "name": get_metric_definition.name,
        "description": get_metric_definition.description,
        "parameters": get_metric_definition.args_schema.model_json_schema(),
    }
    tools = [{"type": "function", "function": function_schema}]
    messages = [
        {"role": "system", "content": "指标口径必须先调用工具查询，不能凭记忆回答。"},
        {"role": "user", "content": "success_rate 的正式定义是什么？"},
    ]
    first = client.chat(messages, tools=tools, tool_choice="required")
    tool_calls = first.get("tool_calls") or []
    assert tool_calls, first
    call = tool_calls[0]
    assert call["function"]["name"] == get_metric_definition.name
    arguments = json.loads(call["function"]["arguments"])
    result = get_metric_definition.invoke(arguments)

    messages.extend(
        [
            first,
            {"role": "tool", "tool_call_id": call["id"], "content": result},
        ]
    )
    final = client.chat(messages, tools=tools)
    assert "成功请求数" in final.get("content", "")
    assert "总请求数" in final.get("content", "")
