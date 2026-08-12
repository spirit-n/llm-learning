"""A2A Executor 背后的幂等执行账本；协议 Task 与业务执行不是同一对象。"""

import hashlib
from dataclasses import dataclass, replace
from typing import Literal
from uuid import uuid4


ExecutionState = Literal["submitted", "working", "completed", "failed", "rejected", "canceled"]


class ExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExecutionRecord:
    id: str
    tenant: str
    idempotency_key: str
    input_digest: str
    trace_id: str
    state: ExecutionState
    report: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class ExecutionClaim:
    record: ExecutionRecord
    replayed: bool


class ReportExecutionLedger:
    """演示用内存账本；生产环境需原子唯一键和持久化事务。"""

    def __init__(self) -> None:
        self.records: dict[str, ExecutionRecord] = {}
        self._keys: dict[tuple[str, str], str] = {}
        self.events: list[dict] = []

    def claim(
        self, *, tenant: str, idempotency_key: str, summary: str, trace_id: str
    ) -> ExecutionClaim:
        if not isinstance(tenant, str) or not tenant.strip() or len(tenant) > 100:
            raise ExecutionError("TENANT_INVALID", "租户标识不合法")
        if not isinstance(trace_id, str) or not trace_id.strip() or len(trace_id) > 100:
            raise ExecutionError("TRACE_ID_INVALID", "trace ID 不合法")
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 100
        ):
            raise ExecutionError("IDEMPOTENCY_KEY_INVALID", "幂等键不合法")
        if not isinstance(summary, str) or not summary.strip():
            raise ExecutionError("SUMMARY_INVALID", "委托内容不能为空")
        digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
        key = (tenant, idempotency_key)
        existing_id = self._keys.get(key)
        if existing_id:
            existing = self.records[existing_id]
            if existing.input_digest != digest:
                raise ExecutionError(
                    "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同的委托内容"
                )
            self._event(existing, "execution_replayed")
            return ExecutionClaim(existing, replayed=True)

        record = ExecutionRecord(
            id=uuid4().hex,
            tenant=tenant,
            idempotency_key=idempotency_key,
            input_digest=digest,
            trace_id=trace_id,
            state="submitted",
        )
        self.records[record.id] = record
        self._keys[key] = record.id
        self._event(record, "execution_claimed")
        return ExecutionClaim(record, replayed=False)

    def start(self, execution_id: str) -> ExecutionRecord:
        return self._transition(execution_id, {"submitted"}, "working", "execution_started")

    def complete(self, execution_id: str, report: str) -> ExecutionRecord:
        return self._transition(
            execution_id, {"working"}, "completed", "execution_completed", report=report
        )

    def fail(self, execution_id: str, code: str) -> ExecutionRecord:
        return self._transition(
            execution_id, {"working"}, "failed", "execution_failed", error_code=code
        )

    def reject(self, execution_id: str, code: str) -> ExecutionRecord:
        return self._transition(
            execution_id, {"submitted"}, "rejected", "execution_rejected", error_code=code
        )

    def cancel(self, execution_id: str) -> ExecutionRecord:
        return self._transition(
            execution_id, {"submitted", "working"}, "canceled", "execution_canceled"
        )

    def _transition(
        self,
        execution_id: str,
        allowed_from: set[ExecutionState],
        target: ExecutionState,
        event_type: str,
        **changes: str,
    ) -> ExecutionRecord:
        current = self.records[execution_id]
        if current.state not in allowed_from:
            raise ExecutionError(
                "INVALID_EXECUTION_STATE", f"不能从 {current.state} 迁移到 {target}"
            )
        updated = replace(current, state=target, **changes)
        self.records[execution_id] = updated
        self._event(updated, event_type)
        return updated

    def _event(self, record: ExecutionRecord, event_type: str) -> None:
        # 事件只记录摘要和关联 ID，不复制原始委托正文或完整报告。
        self.events.append(
            {
                "sequence": len(self.events) + 1,
                "execution_id": record.id,
                "tenant": record.tenant,
                "trace_id": record.trace_id,
                "event_type": event_type,
                "state": record.state,
                "error_code": record.error_code,
            }
        )
