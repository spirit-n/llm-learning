import asyncio

import pytest
from agentscope.message import AssistantMsg, Msg

from as_lab.workflow import AgentTeam, MultiAgentCoordinator


class StubAgent:
    def __init__(self, text: str = "", *, delay: float = 0, error: Exception | None = None):
        self.text = text
        self.delay = delay
        self.error = error
        self.received: list[Msg] = []

    async def reply(self, message: Msg) -> Msg:
        self.received.append(message)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return AssistantMsg(name="stub", content=self.text)


class MalformedAgent(StubAgent):
    def __init__(self, value):
        super().__init__()
        self.value = value

    async def reply(self, message: Msg) -> Msg:
        self.received.append(message)
        return self.value  # type: ignore[return-value]


def team(*, metric: StubAgent, knowledge: StubAgent, reviewer: StubAgent) -> AgentTeam:
    return AgentTeam(metric_agent=metric, knowledge_agent=knowledge, review_agent=reviewer)


@pytest.mark.asyncio
async def test_default_team_runs_specialist_then_reviewer():
    result = await MultiAgentCoordinator().run("营业收入的正式定义是什么？", request_id="req-1")

    assert result.status == "completed"
    assert result.specialist == "metric_agent"
    assert "已完成退款" in result.answer
    assert [(item.sender, item.receiver) for item in result.messages] == [
        ("learner", "coordinator"),
        ("coordinator", "metric_agent"),
        ("metric_agent", "coordinator"),
        ("coordinator", "review_agent"),
        ("review_agent", "coordinator"),
    ]


@pytest.mark.asyncio
async def test_default_coordinator_does_not_leak_agent_memory_between_requests():
    coordinator = MultiAgentCoordinator()

    metric = await coordinator.run("成功率是什么？")
    knowledge = await coordinator.run("RAG 是什么？")

    assert "成功请求数" in metric.answer
    assert knowledge.answer == "RAG 通过检索外部证据来补充模型上下文。"
    assert "成功请求数" not in knowledge.answer


@pytest.mark.asyncio
async def test_reviewer_receives_minimal_handoff_not_specialist_internal_history():
    metric = StubAgent("正式口径")
    reviewer = StubAgent("APPROVED\n正式口径")
    coordinator = MultiAgentCoordinator(
        team(metric=metric, knowledge=StubAgent(), reviewer=reviewer)
    )

    await coordinator.run("成功率是什么？")

    handoff = reviewer.received[0].get_text_content()
    assert handoff == "[request]\n成功率是什么？\n[draft]\n正式口径"


@pytest.mark.asyncio
async def test_reviewer_can_reject_a_draft_without_another_handoff():
    coordinator = MultiAgentCoordinator(
        team(
            metric=StubAgent("NOT_FOUND"),
            knowledge=StubAgent(),
            reviewer=StubAgent("REJECTED: 没有正式口径"),
        )
    )

    result = await coordinator.run("未知指标是什么？")

    assert result.status == "rejected"
    assert result.error_code == "REVIEW_REJECTED"
    assert result.answer is None
    assert len(result.messages) == 5


@pytest.mark.asyncio
async def test_specialist_timeout_is_contained_and_reviewer_is_not_called():
    reviewer = StubAgent("APPROVED\n不应执行")
    coordinator = MultiAgentCoordinator(
        team(metric=StubAgent(delay=0.05), knowledge=StubAgent(), reviewer=reviewer),
        reply_timeout_seconds=0.01,
    )

    result = await coordinator.run("成功率是什么？")

    assert result.status == "failed"
    assert result.error_code == "SPECIALIST_TIMEOUT"
    assert reviewer.received == []


@pytest.mark.asyncio
async def test_agent_exception_is_returned_as_stable_boundary_error():
    coordinator = MultiAgentCoordinator(
        team(
            metric=StubAgent(error=RuntimeError("provider secret detail")),
            knowledge=StubAgent(),
            reviewer=StubAgent(),
        )
    )

    result = await coordinator.run("收入是什么？")

    assert result.error_code == "SPECIALIST_FAILED"
    assert "provider secret detail" not in result.error_message
    assert "RuntimeError" in result.error_message


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_reply", [None, {"content": "伪造消息"}, "plain text"])
async def test_malformed_specialist_reply_is_normalized(bad_reply):
    reviewer = StubAgent("APPROVED\n不应执行")
    coordinator = MultiAgentCoordinator(
        team(
            metric=MalformedAgent(bad_reply),
            knowledge=StubAgent(),
            reviewer=reviewer,
        )
    )
    result = await coordinator.run("收入是什么？")
    assert result.status == "failed"
    assert result.error_code == "INVALID_AGENT_RESPONSE"
    assert reviewer.received == []


@pytest.mark.asyncio
async def test_malformed_reviewer_reply_is_normalized():
    coordinator = MultiAgentCoordinator(
        team(
            metric=StubAgent("正式口径"),
            knowledge=StubAgent(),
            reviewer=MalformedAgent(None),
        )
    )
    result = await coordinator.run("收入是什么？")
    assert result.status == "failed"
    assert result.error_code == "INVALID_AGENT_RESPONSE"


@pytest.mark.asyncio
async def test_malformed_review_protocol_is_not_delivered_to_user():
    coordinator = MultiAgentCoordinator(
        team(
            metric=StubAgent("正式口径"),
            knowledge=StubAgent(),
            reviewer=StubAgent("看起来没问题"),
        )
    )

    result = await coordinator.run("成功率是什么？")

    assert result.status == "failed"
    assert result.error_code == "REVIEW_PROTOCOL_ERROR"
    assert result.answer is None


@pytest.mark.asyncio
async def test_observation_message_is_redacted_and_truncated():
    question = (
        "请分析 alice@example.com 的收入，Authorization: Bearer abc.def_123，"
        "key=sk-abcdefghijklmnopqrstuvwxyz"
    )
    coordinator = MultiAgentCoordinator(
        team(
            metric=StubAgent("正式口径"),
            knowledge=StubAgent(),
            reviewer=StubAgent("APPROVED\n正式口径"),
        )
    )

    result = await coordinator.run(question)

    assert all("alice@example.com" not in item.content for item in result.messages)
    assert any("<redacted-email>" in item.content for item in result.messages)
    assert all("abc.def_123" not in item.content for item in result.messages)
    assert all("sk-abcdefghijklmnopqrstuvwxyz" not in item.content for item in result.messages)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reply_timeout_seconds": 0},
        {"reply_timeout_seconds": float("inf")},
        {"max_question_chars": 0},
        {"max_answer_chars": -1},
    ],
)
def test_invalid_coordinator_limits_fail_fast(kwargs):
    with pytest.raises(ValueError):
        MultiAgentCoordinator(**kwargs)


@pytest.mark.asyncio
async def test_empty_and_oversized_requests_fail_before_any_agent_call():
    metric = StubAgent("unused")
    knowledge = StubAgent("unused")
    reviewer = StubAgent("unused")
    coordinator = MultiAgentCoordinator(
        team(metric=metric, knowledge=knowledge, reviewer=reviewer), max_question_chars=5
    )

    empty = await coordinator.run("   ")
    oversized = await coordinator.run("123456")

    assert empty.error_code == oversized.error_code == "INVALID_REQUEST"
    assert not metric.received and not knowledge.received and not reviewer.received
