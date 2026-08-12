"""多 Agent 协作使用的框架无关领域模型。"""

from dataclasses import dataclass
from typing import Literal


AgentName = Literal["metric_agent", "knowledge_agent", "review_agent"]
RunStatus = Literal["completed", "rejected", "failed"]


@dataclass(frozen=True)
class MessageRecord:
    """一条跨 Agent 消息的可观测摘要。

    这里保留发送方、接收方和消息类型，但内容会在工作流入口统一脱敏、截断。
    这样既能学习消息如何流动，也不会把完整用户数据直接写进日志。
    """

    sequence: int
    sender: str
    receiver: str
    kind: Literal["request", "handoff", "draft", "review", "error"]
    content: str


@dataclass(frozen=True)
class CollaborationResult:
    request_id: str
    status: RunStatus
    specialist: Literal["metric_agent", "knowledge_agent"] | None
    answer: str | None
    messages: tuple[MessageRecord, ...]
    error_code: str | None = None
    error_message: str | None = None

