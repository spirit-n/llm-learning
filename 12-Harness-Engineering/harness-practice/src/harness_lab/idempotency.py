from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Literal, Protocol


IdempotencyState = Literal["missing", "reserved", "in_progress", "completed", "unknown", "conflict"]


class IdempotencyStore(Protocol):
    def lookup(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]: ...
    def reserve(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]: ...
    def complete(self, key: str, signature: str, data: Any) -> None: ...
    def mark_unknown(self, key: str, signature: str) -> None: ...


class InMemoryIdempotencyStore:
    """教学用幂等结果表。

    生产环境应换成带唯一约束和 TTL 的持久化存储；单纯在 Prompt 中要求
    “不要重复执行”无法抵御进程重启、网络重试或两个并发 worker。
    """

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def lookup(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return "missing", None
            if record["signature"] != signature:
                return "conflict", None
            return record["state"], deepcopy(record.get("data"))

    def reserve(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        """原子占用请求 ID，避免两个 worker 同时通过“先查后写”的竞态。"""
        with self._lock:
            record = self._records.get(key)
            if record is None:
                self._records[key] = {"signature": signature, "state": "in_progress"}
                return "reserved", None
            if record["signature"] != signature:
                return "conflict", None
            return record["state"], deepcopy(record.get("data"))

    def complete(self, key: str, signature: str, data: Any) -> None:
        with self._lock:
            record = self._records.get(key)
            if record is None or record["signature"] != signature:
                raise RuntimeError("幂等记录不存在或签名不一致")
            record.update(state="completed", data=deepcopy(data))

    def mark_unknown(self, key: str, signature: str) -> None:
        """执行已开始却未得到可信结果时封存 key，等待人工对账而不是自动重试。"""
        with self._lock:
            record = self._records.get(key)
            if record is not None and record["signature"] == signature and record["state"] != "completed":
                record.update(state="unknown")
