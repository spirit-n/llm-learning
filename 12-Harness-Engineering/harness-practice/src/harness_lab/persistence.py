"""Transactional MySQL stores; explicit SQLite paths support offline tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from learning_db import Database
from sqlalchemy import text

from .idempotency import IdempotencyState


class IdempotencyStore:
    def __init__(self, url: str | Path | None = None):
        self.db = Database(url)
        self.db.create_tables(["""CREATE TABLE IF NOT EXISTS idempotency (
            idem_key VARCHAR(191) PRIMARY KEY, signature VARCHAR(191) NOT NULL,
            state VARCHAR(20) NOT NULL, data LONGTEXT, reservation VARCHAR(32) NOT NULL)"""])

    def lookup(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        with self.db.connection() as db:
            row = db.execute(text("SELECT signature,state,data FROM idempotency WHERE idem_key=:key"), {"key": key}).fetchone()
        if row is None:
            return "missing", None
        if row[0] != signature:
            return "conflict", None
        return row[1], json.loads(row[2]) if row[2] is not None else None

    def reserve(self, key: str, signature: str) -> tuple[IdempotencyState, Any | None]:
        reservation = uuid4().hex
        with self.db.transaction() as db:
            self.db.insert_once(db, "idempotency", "idem_key,signature,state,reservation",
                                ":key,:signature,'in_progress',:reservation",
                                {"key": key, "signature": signature, "reservation": reservation})
            row = db.execute(text("SELECT signature,state,data,reservation FROM idempotency WHERE idem_key=:key" + self.db.for_update), {"key": key}).one()
            if row[3] == reservation:
                return "reserved", None
            if row[0] != signature:
                return "conflict", None
            return row[1], json.loads(row[2]) if row[2] is not None else None

    def complete(self, key: str, signature: str, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
        with self.db.transaction() as db:
            result = db.execute(text("UPDATE idempotency SET state='completed',data=:data WHERE idem_key=:key AND signature=:sig"),
                                {"data": payload, "key": key, "sig": signature})
            if result.rowcount != 1:
                raise RuntimeError("幂等记录不存在或签名不一致")

    def mark_unknown(self, key: str, signature: str) -> None:
        with self.db.transaction() as db:
            db.execute(text("UPDATE idempotency SET state='unknown' WHERE idem_key=:key AND signature=:sig AND state!='completed'"), {"key": key, "sig": signature})


class ReportWorkflow:
    """Report insertion and checkpoint commit together; external effects need their own protocol."""
    def __init__(self, url: str | Path | None = None):
        self.store = IdempotencyStore(url)
        self.store.db.create_tables([
            "CREATE TABLE IF NOT EXISTS jobs (id VARCHAR(191) PRIMARY KEY, tenant VARCHAR(191) NOT NULL, phase VARCHAR(32) NOT NULL, cost_units INTEGER NOT NULL)",
            "CREATE TABLE IF NOT EXISTS reports (job_id VARCHAR(191) PRIMARY KEY, tenant VARCHAR(191) NOT NULL, body TEXT NOT NULL)",
        ])

    def advance(self, job_id: str, tenant: str, *, max_cost_units: int = 2) -> dict[str, Any]:
        if not job_id or not tenant or max_cost_units < 1:
            raise ValueError("job_id/tenant/预算必须有效")
        database = self.store.db
        with database.transaction() as db:
            params = {"job": job_id, "tenant": tenant}
            database.insert_once(db, "jobs", "id,tenant,phase,cost_units", ":job,:tenant,'pending',0", params)
            owner, phase, cost = db.execute(text("SELECT tenant,phase,cost_units FROM jobs WHERE id=:job" + database.for_update), params).one()
            if owner != tenant:
                raise PermissionError("任务不属于当前租户")
            if phase == "completed":
                return {"phase": phase, "cost_units": cost, "replayed": True}
            if cost + 1 > max_cost_units:
                raise ValueError("教学预算耗尽，重启不会清零")
            if phase == "pending":
                db.execute(text("INSERT INTO reports VALUES (:job,:tenant,:body)"), {**params, "body": "离线报告：营业收入口径"})
                phase = "report_created"
            else:
                phase = "completed"
            db.execute(text("UPDATE jobs SET phase=:phase,cost_units=:cost WHERE id=:job"), {**params, "phase": phase, "cost": cost + 1})
            return {"phase": phase, "cost_units": cost + 1, "replayed": False}


SQLiteIdempotencyStore = IdempotencyStore
SQLiteReportWorkflow = ReportWorkflow


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="每次运行推进一个 MySQL 持久化步骤")
    parser.add_argument("--db", help="数据库 URL；默认读取 DATABASE_URL")
    parser.add_argument("--job", default="demo")
    args = parser.parse_args()
    print(json.dumps(ReportWorkflow(args.db).advance(args.job, "tenant-a"), ensure_ascii=False))


if __name__ == "__main__":
    main()
