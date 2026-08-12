"""显式编排专家 Agent 与审核 Agent，并把失败限制在单次请求内。"""

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from agentscope.message import Msg, UserMsg

from as_lab.agents import build_knowledge_agent, build_metric_agent, build_review_agent
from as_lab.domain import CollaborationResult, MessageRecord
from as_lab.routing import choose_agent


class ReplyAgent(Protocol):
    async def reply(self, message: Msg) -> Msg: ...


class InvalidAgentResponse(ValueError):
    """AgentScope 边界收到非 Msg、不可读或空文本。"""


@dataclass(frozen=True)
class AgentTeam:
    metric_agent: ReplyAgent
    knowledge_agent: ReplyAgent
    review_agent: ReplyAgent


def build_default_team() -> AgentTeam:
    return AgentTeam(
        metric_agent=build_metric_agent(),
        knowledge_agent=build_knowledge_agent(),
        review_agent=build_review_agent(),
    )


class MultiAgentCoordinator:
    """两阶段协作：专家产出草稿，审核 Agent 决定是否交付。

    Agent 的输出是不可信输入，因此超时、空响应、超长响应和审核协议错误都在
    coordinator 中确定性处理，而不是继续让 Agent 自由对话或无限互相转交。
    """

    def __init__(
        self,
        team: AgentTeam | None = None,
        *,
        reply_timeout_seconds: float = 3.0,
        max_question_chars: int = 1_000,
        max_answer_chars: int = 4_000,
    ) -> None:
        if not math.isfinite(reply_timeout_seconds) or reply_timeout_seconds <= 0:
            raise ValueError("reply_timeout_seconds 必须是大于 0 的有限数")
        if isinstance(max_question_chars, bool) or max_question_chars <= 0:
            raise ValueError("max_question_chars 必须是正整数")
        if isinstance(max_answer_chars, bool) or max_answer_chars <= 0:
            raise ValueError("max_answer_chars 必须是正整数")
        # 默认按请求创建 Agent，避免 AgentScope memory 把上一个用户/请求的消息带入本次审核。
        # 测试或显式会话可以注入固定 team，自行承担 session 隔离责任。
        self._team = team
        self._reply_timeout_seconds = reply_timeout_seconds
        self._max_question_chars = max_question_chars
        self._max_answer_chars = max_answer_chars

    async def run(self, question: str, *, request_id: str | None = None) -> CollaborationResult:
        run_id = request_id or uuid4().hex
        records: list[MessageRecord] = []

        normalized = question.strip()
        if not normalized or len(normalized) > self._max_question_chars:
            return self._failed(
                run_id,
                None,
                records,
                "INVALID_REQUEST",
                f"问题不能为空且不能超过 {self._max_question_chars} 个字符",
            )

        team = self._team or build_default_team()
        specialist_name = choose_agent(normalized)
        specialist = getattr(team, specialist_name)
        self._record(records, "learner", "coordinator", "request", normalized)
        self._record(records, "coordinator", specialist_name, "handoff", normalized)

        try:
            draft_message = await self._reply_with_timeout(
                specialist,
                UserMsg(name="coordinator", content=normalized),
            )
            draft = _extract_agent_text(draft_message)
        except TimeoutError:
            return self._failed(
                run_id, specialist_name, records, "SPECIALIST_TIMEOUT", "专家 Agent 响应超时"
            )
        except Exception as exc:  # Agent/模型异常不能击穿整个服务进程
            if isinstance(exc, InvalidAgentResponse):
                return self._failed(
                    run_id,
                    specialist_name,
                    records,
                    "INVALID_AGENT_RESPONSE",
                    "专家 Agent 返回了无效消息",
                )
            return self._failed(
                run_id,
                specialist_name,
                records,
                "SPECIALIST_FAILED",
                f"专家 Agent 执行失败：{type(exc).__name__}",
            )

        if len(draft) > self._max_answer_chars:
            return self._failed(
                run_id,
                specialist_name,
                records,
                "INVALID_DRAFT",
                "专家输出为空或超过长度限制",
            )
        self._record(records, specialist_name, "coordinator", "draft", draft)

        # 审核 Agent 只接收完成任务所需的原问题和草稿，不继承专家的全部内部历史。
        review_input = f"[request]\n{normalized}\n[draft]\n{draft}"
        self._record(records, "coordinator", "review_agent", "handoff", review_input)
        try:
            review_message = await self._reply_with_timeout(
                team.review_agent,
                UserMsg(name="coordinator", content=review_input),
            )
            review = _extract_agent_text(review_message)
        except TimeoutError:
            return self._failed(run_id, specialist_name, records, "REVIEW_TIMEOUT", "审核 Agent 响应超时")
        except Exception as exc:
            if isinstance(exc, InvalidAgentResponse):
                return self._failed(
                    run_id,
                    specialist_name,
                    records,
                    "INVALID_AGENT_RESPONSE",
                    "审核 Agent 返回了无效消息",
                )
            return self._failed(
                run_id,
                specialist_name,
                records,
                "REVIEW_FAILED",
                f"审核 Agent 执行失败：{type(exc).__name__}",
            )

        self._record(records, "review_agent", "coordinator", "review", review)
        if review.startswith("REJECTED:"):
            return CollaborationResult(
                request_id=run_id,
                status="rejected",
                specialist=specialist_name,
                answer=None,
                messages=tuple(records),
                error_code="REVIEW_REJECTED",
                error_message=review.removeprefix("REJECTED:").strip() or "审核未通过",
            )
        if not review.startswith("APPROVED\n"):
            return self._failed(
                run_id,
                specialist_name,
                records,
                "REVIEW_PROTOCOL_ERROR",
                "审核输出必须以 APPROVED 或 REJECTED 开头",
            )
        answer = review.removeprefix("APPROVED\n").strip()
        if not answer or len(answer) > self._max_answer_chars:
            return self._failed(
                run_id, specialist_name, records, "INVALID_REVIEWED_ANSWER", "审核后的答案不合法"
            )
        return CollaborationResult(
            request_id=run_id,
            status="completed",
            specialist=specialist_name,
            answer=answer,
            messages=tuple(records),
        )

    async def _reply_with_timeout(self, agent: ReplyAgent, message: Msg) -> Msg:
        return await asyncio.wait_for(agent.reply(message), timeout=self._reply_timeout_seconds)

    @staticmethod
    def _record(
        records: list[MessageRecord], sender: str, receiver: str, kind: str, content: str
    ) -> None:
        records.append(
            MessageRecord(
                sequence=len(records) + 1,
                sender=sender,
                receiver=receiver,
                kind=kind,  # type: ignore[arg-type]
                content=_safe_message_summary(content),
            )
        )

    @staticmethod
    def _failed(
        request_id: str,
        specialist: str | None,
        records: list[MessageRecord],
        code: str,
        message: str,
    ) -> CollaborationResult:
        MultiAgentCoordinator._record(records, "coordinator", "caller", "error", f"{code}: {message}")
        return CollaborationResult(
            request_id=request_id,
            status="failed",
            specialist=specialist,  # type: ignore[arg-type]
            answer=None,
            messages=tuple(records),
            error_code=code,
            error_message=message,
        )


def _safe_message_summary(text: str, limit: int = 500) -> str:
    """日志只保留脱敏摘要；Agent 实际收到的消息不会因此被篡改。"""

    redacted = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<redacted-email>", text)
    redacted = re.sub(r"\b1\d{10}\b", "<redacted-phone>", redacted)
    redacted = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted-token>", redacted
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "<redacted-api-key>", redacted)
    return redacted if len(redacted) <= limit else f"{redacted[:limit]}…"


def _extract_agent_text(reply: object) -> str:
    """Agent 输出进入编排状态前先做运行时类型验证，避免鸭子类型异常击穿服务。"""

    if not isinstance(reply, Msg):
        raise InvalidAgentResponse("reply 必须是 agentscope.message.Msg")
    try:
        text = reply.get_text_content()
    except Exception as exc:
        raise InvalidAgentResponse("Msg 文本不可读取") from exc
    if not isinstance(text, str) or not text.strip():
        raise InvalidAgentResponse("Msg 文本必须是非空字符串")
    return text.strip()
