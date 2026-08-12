import json
import sys
from pathlib import Path

import pytest

from harness_lab.models import Observation, PlanDecision, TaskSpec, UserContext
from harness_lab.runtime import AgentHarness
from harness_lab.tools import build_demo_registry
from harness_lab.verifiers import verify_metric_answer


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from shared.live_llm import LiveLLMSettings, OpenAICompatibleChatClient  # noqa: E402


pytestmark = pytest.mark.live


class LivePlanner:
    def __init__(self, client: OpenAICompatibleChatClient):
        self.client = client

    def decide(self, task: TaskSpec, observations: list[Observation], tool_schemas: list[dict]) -> PlanDecision:
        message = self.client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 Agent Harness 中受约束的 Planner。没有 observation 时必须调用工具；"
                        "已有 observation 时直接给最终中文答案，不得编造数值。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"任务：{task.objective}\nobservations={json.dumps([item.model_dump() for item in observations], ensure_ascii=False)}",
                },
            ],
            tools=tool_schemas,
            tool_choice="required" if not observations else "none",
        )
        calls = message.get("tool_calls") or []
        if calls:
            call = calls[0]
            return PlanDecision(
                kind="tool",
                tool_name=call["function"]["name"],
                arguments=json.loads(call["function"]["arguments"]),
            )
        return PlanDecision(kind="final", answer=message.get("content") or "")


def test_live_model_is_constrained_by_the_same_harness():
    settings = LiveLLMSettings.from_env()
    planner = LivePlanner(OpenAICompatibleChatClient(settings))
    result = AgentHarness(build_demo_registry(), verify_metric_answer).run(
        planner,
        TaskSpec(
            task_id="live-harness",
            objective="查询 tenant-a 昨日 success_rate，并用百分比回答",
            expected_metric="success_rate",
            allowed_tools=frozenset({"query_metric"}),
        ),
        UserContext(
            user_id="live-user",
            tenant="tenant-a",
            permissions=frozenset({"metrics:query"}),
        ),
    )
    assert result.status == "succeeded", result
    assert result.observations[0].tool_name == "query_metric"
    assert any(event.event == "verification" for event in result.trace)
