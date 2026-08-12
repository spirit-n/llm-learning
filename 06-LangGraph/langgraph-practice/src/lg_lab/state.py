"""图的共享状态：只保存可序列化的任务事实，不把服务对象塞进 checkpoint。"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict


CURRENT_STATE_VERSION = 1


class StateVersionError(ValueError):
    def __init__(self, version: object) -> None:
        super().__init__(f"不支持的状态版本: {version}")
        self.version = version


class ErrorRecord(TypedDict):
    code: str
    message: str
    node: str
    retryable: bool


class WorkflowState(TypedDict, total=False):
    state_version: int
    request_id: str
    question: str
    user_id: str
    role: str
    intent: Literal["knowledge", "data_query"]
    allowed_tables: list[str]
    schema: str
    sql: str
    sql_fingerprint: str
    risk_level: Literal["low", "medium", "high"]
    approved: bool
    rows: list[dict[str, object]]
    answer: str
    status: Literal["running", "completed", "failed", "cancelled"]
    error_code: str
    error: str
    attempts: int
    retries: int
    max_attempts: int
    failures_remaining: int
    execution_key: str
    execution_completed: bool
    verification_passed: bool
    # reducer 让节点只返回本次新增事件，避免循环时复制整段历史并造成状态膨胀。
    trace: Annotated[list[str], operator.add]
    error_history: Annotated[list[ErrorRecord], operator.add]
    # v0 checkpoint 的旧字段只用于迁移，v1 节点不得继续写入。
    max_retries: int
    retry_count: int
    allowed_table_names: list[str]


def migrate_state(state: WorkflowState) -> tuple[WorkflowState, list[str]]:
    """把持久化状态升级到当前版本；未来版本必须拒绝而不是猜测字段含义。"""

    version = state.get("state_version", CURRENT_STATE_VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise StateVersionError(version)
    if version > CURRENT_STATE_VERSION:
        raise StateVersionError(version)
    migrated: WorkflowState = dict(state)  # type: ignore[assignment]
    events: list[str] = []
    if version == 0:
        # v0: max_retries 表示“首次尝试之外的重试数”；v1 改为总尝试次数。
        if "max_attempts" not in migrated and "max_retries" in migrated:
            legacy_retries = migrated["max_retries"]
            migrated["max_attempts"] = (
                legacy_retries + 1
                if isinstance(legacy_retries, int) and not isinstance(legacy_retries, bool)
                else legacy_retries
            )
        if "retries" not in migrated and "retry_count" in migrated:
            migrated["retries"] = migrated["retry_count"]
        if "allowed_tables" not in migrated and "allowed_table_names" in migrated:
            migrated["allowed_tables"] = list(migrated["allowed_table_names"])
        migrated["state_version"] = CURRENT_STATE_VERSION
        events.append("state:migrated:v0->v1")
    return migrated, events
