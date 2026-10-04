"""SQLite teaching stores. No automatic reclaim of ambiguous side effects."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .idempotency import IdempotencyState


class SQLiteIdempotencyStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS idempotency (
                key TEXT PRIMARY KEY, signature TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('in_progress','completed','unknown')),
                data TEXT)""")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def lookup(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        with self.connection() as db:
            row = db.execute("SELECT signature,state,data FROM idempotency WHERE key=?", (key,)).fetchone()
        if row is None:
            return "missing", None
        if row[0] != signature:
            return "conflict", None
        return row[1], json.loads(row[2]) if row[2] is not None else None

    def reserve(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        with self.connection() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO idempotency(key,signature,state) VALUES (?,?,'in_progress')",
                (key, signature),
            )
            reserved = cursor.rowcount == 1
        return ("reserved", None) if reserved else self.lookup(key, signature)

    def complete(self, key: str, signature: str, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE idempotency SET state='completed',data=? WHERE key=? AND signature=?",
                (payload, key, signature),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("幂等记录不存在或签名不一致")

    def mark_unknown(self, key: str, signature: str) -> None:
        with self.connection() as db:
            db.execute("UPDATE idempotency SET state='unknown' WHERE key=? AND signature=? AND state!='completed'",
                       (key, signature))


class SQLiteReportWorkflow:
    """Two durable steps; report insertion and checkpoint share one local DB transaction.

    This is NOT an exactly-once promise for external HTTP/payment/email effects.
    """
    def __init__(self, path: str | Path):
        self.store = SQLiteIdempotencyStore(path)
        with self.store.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, phase TEXT NOT NULL, cost_units INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS reports (job_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, body TEXT NOT NULL)")

    def advance(self, job_id: str, tenant: str, *, max_cost_units: int = 2) -> dict[str, Any]:
        if not job_id or not tenant or max_cost_units < 1:
            raise ValueError("job_id/tenant/预算必须有效")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,'pending',0)", (job_id, tenant))
            owner, phase, cost = db.execute("SELECT tenant,phase,cost_units FROM jobs WHERE id=?", (job_id,)).fetchone()
            if owner != tenant:
                raise PermissionError("任务不属于当前租户")
            if phase == "completed":
                return {"phase": phase, "cost_units": cost, "replayed": True}
            if cost + 1 > max_cost_units:
                raise ValueError("教学预算耗尽，重启不会清零")
            if phase == "pending":
                db.execute("INSERT INTO reports VALUES (?,?,?)", (job_id, tenant, "离线报告：营业收入口径"))
                phase = "report_created"
            else:
                phase = "completed"
            db.execute("UPDATE jobs SET phase=?,cost_units=? WHERE id=?", (phase, cost + 1, job_id))
            return {"phase": phase, "cost_units": cost + 1, "replayed": False}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="每次运行推进一个持久化步骤；重复运行不会重复写报告")
    parser.add_argument("--db", required=True)
    parser.add_argument("--job", default="demo")
    args = parser.parse_args()
    print(json.dumps(SQLiteReportWorkflow(args.db).advance(args.job, "tenant-a"), ensure_ascii=False))


if __name__ == "__main__":
    main()
