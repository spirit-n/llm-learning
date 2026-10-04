"""Local durable checkpoint + transactional teaching-result ledger.

The ledger transaction covers the local demo result only. It cannot make an
arbitrary remote side effect exactly-once; that requires downstream idempotency
or an outbox/transaction protocol.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from .graph import build_graph
from .warehouse import DemoWarehouse, TransientWarehouseError


class SqliteWarehouse:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("durable ledger requires a file path")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS executions ("
                               "execution_key TEXT PRIMARY KEY, sql_text TEXT NOT NULL, "
                               "result_json TEXT NOT NULL)")

    @property
    def execution_count(self) -> int:
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

    def query(self, sql: str, *, idempotency_key: str, simulate_transient: bool = False):
        if not idempotency_key:
            raise ValueError("idempotency key must not be empty")
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT sql_text, result_json FROM executions WHERE execution_key = ?",
                (idempotency_key,),
            ).fetchone()
            if previous:
                if previous[0] != sql:
                    raise ValueError("idempotency key reused with a different SQL payload")
                return json.loads(previous[1]), True
            if simulate_transient:
                raise TransientWarehouseError("数据库暂时不可用")
            rows, _ = DemoWarehouse().query(sql, idempotency_key=idempotency_key)
            connection.execute("INSERT INTO executions VALUES (?, ?, ?)",
                               (idempotency_key, sql, json.dumps(rows, ensure_ascii=False)))
            return rows, False


@contextmanager
def persistent_graph(checkpoint_path: str | Path, ledger_path: str | Path, *, warehouse=None):
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as exc:
        raise RuntimeError("SQLite checkpoint requires the optional [persistence] extra") from exc
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    # State consists of built-in JSON-like values; no arbitrary module revival.
    with closing(sqlite3.connect(str(checkpoint_path), check_same_thread=False)) as connection:
        saver = SqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
        yield build_graph(checkpointer=saver, warehouse=warehouse or SqliteWarehouse(ledger_path))
