"""MySQL checkpoints and a transactional result ledger."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from learning_db import Database, database_url
from sqlalchemy import text
from sqlalchemy.engine import make_url

from .graph import build_graph
from .warehouse import DemoWarehouse, TransientWarehouseError


class PersistentWarehouse:
    def __init__(self, url: str | Path | None = None):
        self.db = Database(url)
        if self.db.url.endswith(":memory:"):
            raise ValueError("durable ledger requires a file path or MySQL URL")
        self.db.create_tables(["CREATE TABLE IF NOT EXISTS executions (execution_key VARCHAR(191) PRIMARY KEY, sql_text TEXT NOT NULL, result_json LONGTEXT)"])
        if self.db.mysql:
            self.db.create_tables(["CREATE TABLE IF NOT EXISTS daily_metrics (day VARCHAR(10) PRIMARY KEY, revenue DOUBLE NOT NULL, success_rate DOUBLE NOT NULL, value DOUBLE NOT NULL)"])
            with self.db.transaction() as connection:
                self.db.insert_once(connection, "daily_metrics", "day,revenue,success_rate,value",
                                    ":day,128000.0,0.975,128000.0", {"day": "2026-07-31"})

    @property
    def execution_count(self) -> int:
        with self.db.connection() as connection:
            return connection.execute(text("SELECT COUNT(*) FROM executions WHERE result_json IS NOT NULL")).scalar_one()

    def query(self, sql: str, *, idempotency_key: str, simulate_transient: bool = False):
        if not idempotency_key:
            raise ValueError("idempotency key must not be empty")
        with self.db.transaction() as connection:
            params = {"key": idempotency_key, "sql": sql}
            self.db.insert_once(connection, "executions", "execution_key,sql_text", ":key,:sql", params)
            previous = connection.execute(text("SELECT sql_text,result_json FROM executions WHERE execution_key=:key" + self.db.for_update), params).one()
            if previous[0] != sql:
                raise ValueError("idempotency key reused with a different SQL payload")
            if previous[1] is not None:
                return json.loads(previous[1]), True
            if simulate_transient:
                raise TransientWarehouseError("数据库暂时不可用")
            if self.db.mysql:
                from .sql_policy import inspect_sql
                policy = inspect_sql(sql, allowed_tables={"daily_metrics"})
                if not policy.allowed:
                    raise ValueError(policy.reason)
                connection.execute(text("SET SESSION MAX_EXECUTION_TIME=2000"))
                rows = [dict(row) for row in connection.exec_driver_sql(policy.normalized_sql, execution_options={"no_parameters": True}).mappings()]
            else:
                rows, _ = DemoWarehouse().query(sql, idempotency_key=idempotency_key)
            connection.execute(text("UPDATE executions SET result_json=:result WHERE execution_key=:key"), {**params, "result": json.dumps(rows, ensure_ascii=False)})
            return rows, False


SqliteWarehouse = PersistentWarehouse


@contextmanager
def persistent_graph(checkpoint_path: str | Path | None = None, ledger_path: str | Path | None = None, *, warehouse=None):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    url = database_url(checkpoint_path)
    serde = JsonPlusSerializer(allowed_msgpack_modules=[])
    if url.startswith("mysql"):
        import pymysql
        from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
        parsed = make_url(url)
        with pymysql.connect(host=parsed.host, port=parsed.port or 3306, user=parsed.username,
                             password=parsed.password, database=parsed.database, charset="utf8mb4",
                             connect_timeout=5, read_timeout=10, write_timeout=10, autocommit=True) as connection:
            saver = PyMySQLSaver(connection, serde=serde)
            saver.setup()
            yield build_graph(checkpointer=saver, warehouse=warehouse if warehouse is not None else PersistentWarehouse(ledger_path or url))
    else:
        import sqlite3
        from contextlib import closing
        from langgraph.checkpoint.sqlite import SqliteSaver
        with closing(sqlite3.connect(make_url(url).database, check_same_thread=False)) as connection:
            saver = SqliteSaver(connection, serde=serde)
            yield build_graph(checkpointer=saver, warehouse=warehouse if warehouse is not None else PersistentWarehouse(ledger_path or url))
