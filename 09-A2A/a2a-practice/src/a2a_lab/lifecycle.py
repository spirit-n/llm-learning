"""框架无关的长任务生命周期、事件流与幂等存储。"""

import hashlib
import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskState(StrEnum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELED = "canceled"


TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.REJECTED,
    TaskState.CANCELED,
}

ALLOWED_TRANSITIONS = {
    TaskState.SUBMITTED: {TaskState.WORKING, TaskState.REJECTED, TaskState.CANCELED},
    TaskState.WORKING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED},
}


class LifecycleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FrozenSummary(dict[str, int | float]):
    """保持 dict/JSON 兼容，但阻止调用方在生成 digest 后篡改嵌套摘要。"""

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError("任务摘要是只读快照")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int = Field(ge=1)
    task_id: str
    state: TaskState
    event_type: str
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    tenant: str
    idempotency_key: str
    payload_digest: str
    trace_id: str
    summary: dict[str, int | float]
    state: TaskState
    version: int = Field(ge=1)
    artifact: str | None = None
    error_code: str | None = None

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> dict[str, int | float]:
        """领域模型自身也守住边界，避免绕过 service 直接构造脏记录。"""

        return _normalize_summary(value)

    @model_validator(mode="after")
    def freeze_summary(self) -> "TaskRecord":
        # ConfigDict(frozen=True) 只冻结字段赋值；嵌套 dict 还需要显式只读包装。
        object.__setattr__(self, "summary", FrozenSummary(self.summary))
        return self


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: TaskRecord
    replayed: bool


class TaskLifecycleService:
    """内存实现便于学习；接口边界可替换成数据库和消息队列。"""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self._idempotency_index: dict[tuple[str, str], str] = {}
        self._events: dict[str, list[TaskEvent]] = {}

    def clear(self) -> None:
        self.tasks.clear()
        self._idempotency_index.clear()
        self._events.clear()

    def submit(
        self,
        *,
        tenant: str,
        idempotency_key: str,
        summary: dict[str, int | float],
        trace_id: str,
    ) -> Submission:
        if not isinstance(tenant, str) or not tenant.strip() or len(tenant) > 100:
            raise LifecycleError("TENANT_INVALID", "租户标识不合法")
        if not isinstance(trace_id, str) or not trace_id.strip() or len(trace_id) > 100:
            raise LifecycleError("TRACE_ID_INVALID", "trace_id 不合法")
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 100
        ):
            raise LifecycleError("IDEMPOTENCY_KEY_INVALID", "幂等键不能为空且不能超过 100 字符")
        try:
            normalized_summary = _normalize_summary(summary)
        except ValueError as exc:
            raise LifecycleError("SUMMARY_INVALID", str(exc)) from exc
        digest = _payload_digest(normalized_summary)
        index_key = (tenant, idempotency_key)
        existing_id = self._idempotency_index.get(index_key)
        if existing_id is not None:
            existing = self.tasks[existing_id]
            if existing.payload_digest != digest:
                raise LifecycleError(
                    "IDEMPOTENCY_CONFLICT", "同一租户的幂等键不能代表不同任务输入"
                )
            return Submission(task=existing, replayed=True)

        task = TaskRecord(
            id=uuid4().hex,
            tenant=tenant,
            idempotency_key=idempotency_key,
            payload_digest=digest,
            trace_id=trace_id,
            # 哈希、内存记录和 HTTP JSON 都使用同一份规范化摘要，禁止校验后再隐式转换。
            summary=normalized_summary,
            state=TaskState.SUBMITTED,
            version=1,
        )
        self.tasks[task.id] = task
        self._idempotency_index[index_key] = task.id
        self._append_event(task, "task_submitted")
        return Submission(task=task, replayed=False)

    def get(self, task_id: str, tenant: str) -> TaskRecord:
        task = self.tasks.get(task_id)
        # 对跨租户查询统一返回 NOT_FOUND，避免泄露另一个租户是否存在该 task_id。
        if task is None or task.tenant != tenant:
            raise LifecycleError("TASK_NOT_FOUND", "任务不存在")
        return task

    def events(self, task_id: str, tenant: str, *, after: int = 0) -> tuple[TaskEvent, ...]:
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise LifecycleError("INVALID_CURSOR", "事件游标必须是非负整数")
        self.get(task_id, tenant)
        return tuple(event for event in self._events[task_id] if event.sequence > after)

    def start(self, task_id: str, tenant: str) -> TaskRecord:
        return self._transition(task_id, tenant, TaskState.WORKING, "task_started")

    def complete(self, task_id: str, tenant: str, artifact: str) -> TaskRecord:
        if not artifact.strip():
            raise LifecycleError("ARTIFACT_EMPTY", "完成任务必须包含 artifact")
        return self._transition(
            task_id,
            tenant,
            TaskState.COMPLETED,
            "artifact_ready",
            artifact=artifact,
        )

    def fail(self, task_id: str, tenant: str, error_code: str) -> TaskRecord:
        return self._transition(
            task_id,
            tenant,
            TaskState.FAILED,
            "task_failed",
            error_code=error_code,
        )

    def reject(self, task_id: str, tenant: str, error_code: str) -> TaskRecord:
        return self._transition(
            task_id,
            tenant,
            TaskState.REJECTED,
            "task_rejected",
            error_code=error_code,
        )

    def cancel(self, task_id: str, tenant: str) -> TaskRecord:
        return self._transition(task_id, tenant, TaskState.CANCELED, "task_canceled")

    def _transition(
        self,
        task_id: str,
        tenant: str,
        target: TaskState,
        event_type: str,
        **changes: Any,
    ) -> TaskRecord:
        current = self.get(task_id, tenant)
        if target not in ALLOWED_TRANSITIONS.get(current.state, set()):
            raise LifecycleError(
                "INVALID_STATE_TRANSITION",
                f"不能从 {current.state.value} 迁移到 {target.value}",
            )
        updated = current.model_copy(
            update={"state": target, "version": current.version + 1, **changes}
        )
        self.tasks[task_id] = updated
        self._append_event(updated, event_type)
        return updated

    def _append_event(self, task: TaskRecord, event_type: str) -> None:
        events = self._events.setdefault(task.id, [])
        details: dict[str, Any] = {"version": task.version, "trace_id": task.trace_id}
        if task.error_code:
            details["error_code"] = task.error_code
        if task.artifact is not None:
            details["artifact_bytes"] = len(task.artifact.encode("utf-8"))
        events.append(
            TaskEvent(
                sequence=len(events) + 1,
                task_id=task.id,
                state=task.state,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                details=details,
            )
        )


def _normalize_summary(value: object) -> dict[str, int | float]:
    """返回可稳定 JSON 化的摘要；bool 虽是 int 子类，也必须显式拒绝。"""

    if not isinstance(value, dict) or not value or len(value) > 20:
        raise ValueError("任务摘要必须包含 1～20 个聚合指标")
    normalized: dict[str, int | float] = {}
    for key, number in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 100:
            raise ValueError("指标名必须是 1～100 字符的非空字符串")
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"指标 {key} 必须是整数或浮点数，不能是布尔值")
        if not math.isfinite(number):
            raise ValueError(f"指标 {key} 必须是有限数，不能是 NaN 或 Infinity")
        normalized[key] = number
    # 排序不仅让 digest 稳定，也让内存快照和 API JSON 的字段顺序一致，便于审计比对。
    return {key: normalized[key] for key in sorted(normalized)}


def _payload_digest(summary: dict[str, int | float]) -> str:
    payload = json.dumps(summary, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
