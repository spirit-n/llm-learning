"""可替换的数据执行端口及确定性离线实现。"""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol


class TransientWarehouseError(RuntimeError):
    pass


class Warehouse(Protocol):
    def query(
        self, sql: str, *, idempotency_key: str, simulate_transient: bool = False
    ) -> tuple[list[dict[str, object]], bool]: ...


class DemoWarehouse:
    """缓存 execution key，模拟 checkpoint 重放时不重复触发外部查询。"""

    def __init__(self) -> None:
        self._results: dict[str, list[dict[str, object]]] = {}
        self.execution_count = 0

    def query(
        self, sql: str, *, idempotency_key: str, simulate_transient: bool = False
    ) -> tuple[list[dict[str, object]], bool]:
        if idempotency_key in self._results:
            return deepcopy(self._results[idempotency_key]), True
        if simulate_transient:
            raise TransientWarehouseError("数据库暂时不可用")

        self.execution_count += 1
        if "success_rate" in sql.lower():
            rows: list[dict[str, object]] = [
                {"day": "2026-07-31", "success_rate": 0.975}
            ]
        elif "no_rows" in sql.lower():
            rows = []
        else:
            # value 保留早期教程的通用字段，revenue 则展示真实列名。
            rows = [{"day": "2026-07-31", "revenue": 128000.0, "value": 128000.0}]
        self._results[idempotency_key] = deepcopy(rows)
        return rows, False
