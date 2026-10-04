import json
import sys
from pathlib import Path

import pytest

from tool_loop.models import Message, ModelResponse, ToolCall, UserContext
from tool_loop.runtime import ToolRuntime
from tool_loop.tools import build_default_registry


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import (  # noqa: E402
    LiveLLMSettings,
    OpenAICompatibleChatClient,
)


from shared.llm_support import JsonlEventSink  # noqa: E402

pytestmark = pytest.mark.live


class LiveToolCallingModel:
    """把 OpenAI-compatible 响应适配到手写运行时的 ChatModel 协议。"""

    def __init__(self, client: OpenAICompatibleChatClient):
        self.client = client

    def complete(self, messages: list[Message], tool_schemas: list[dict]) -> ModelResponse:
        has_tool_result = any(message.role == "tool" for message in messages)
        response = self.client.chat(
            _to_provider_messages(messages),
            tools=[{"type": item["type"], "function": item["function"]} for item in tool_schemas],
            tool_choice=None if has_tool_result else "required",
        )
        calls = response.get("tool_calls") or []
        if calls:
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        id=call["id"],
                        name=call["function"]["name"],
                        arguments=json.loads(call["function"]["arguments"]),
                    )
                    for call in calls
                ]
            )
        return ModelResponse(final_answer=response.get("content") or "模型未返回文本")


def _to_provider_messages(messages: list[Message]) -> list[dict]:
    converted = []
    for message in messages:
        if message.role == "assistant":
            try:
                calls = json.loads(message.content)["tool_calls"]
            except (json.JSONDecodeError, KeyError, TypeError):
                converted.append({"role": "assistant", "content": message.content})
            else:
                converted.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                                },
                            }
                            for call in calls
                        ],
                    }
                )
        elif message.role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "name": message.name,
                    "content": message.content,
                }
            )
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


def test_live_model_runs_inside_the_guarded_tool_runtime():
    settings = LiveLLMSettings.from_env()
    log_path = Path(__file__).resolve().parents[1] / "artifacts" / "live_requests.jsonl"
    client = OpenAICompatibleChatClient(settings, event_sink=JsonlEventSink(log_path))
    print(f"调用元数据日志：{log_path}")

    runtime = ToolRuntime(build_default_registry(), max_steps=4)
    result = runtime.run(
        LiveToolCallingModel(client),
        "必须调用 get_metric_definition 工具查询‘营业收入’的正式口径，再根据工具结果回答。",
        UserContext(user_id="live-student", permissions=frozenset({"metrics:read"})),
    )
    assert result.status == "completed", result
    assert result.tool_call_count >= 1
    assert result.invalid_call_count == 0
    assert result.audit_log[0].tool_name == "get_metric_definition"
    assert result.audit_log[0].outcome == "ok"
    assert "退款" in (result.final_answer or "")
