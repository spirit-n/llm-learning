import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from langgraph.types import Command

from lg_lab.persistence import SqliteWarehouse, persistent_graph
from lg_lab.warehouse import TransientWarehouseError


HAS_SQLITE_SAVER = importlib.util.find_spec("langgraph.checkpoint.sqlite") is not None
needs_saver = pytest.mark.skipif(not HAS_SQLITE_SAVER, reason="install optional [persistence] extra")
SQL = "SELECT day, revenue FROM daily_metrics LIMIT 1"


def test_ledger_survives_new_instance_and_rejects_payload_collision(tmp_path):
    path = tmp_path / "ledger.sqlite"
    first, replayed = SqliteWarehouse(path).query(SQL, idempotency_key="request:sql")
    assert not replayed
    second, replayed = SqliteWarehouse(path).query(SQL, idempotency_key="request:sql")
    assert replayed and first == second
    assert SqliteWarehouse(path).execution_count == 1
    with pytest.raises(ValueError, match="different SQL"):
        SqliteWarehouse(path).query("SELECT day FROM daily_metrics LIMIT 1", idempotency_key="request:sql")


def test_failed_transaction_does_not_consume_idempotency_key(tmp_path):
    store = SqliteWarehouse(tmp_path / "ledger.sqlite")
    with pytest.raises(TransientWarehouseError):
        store.query(SQL, idempotency_key="retry", simulate_transient=True)
    assert store.execution_count == 0
    assert not store.query(SQL, idempotency_key="retry")[1]


@needs_saver
def test_pause_resume_across_processes(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    common = ["--checkpoint", str(tmp_path / "checkpoints.sqlite"), "--ledger",
              str(tmp_path / "ledger.sqlite"), "--thread", "restart-1"]
    def run(action):
        completed = subprocess.run([sys.executable, "-m", "lg_lab.persistent_demo", action, *common],
                                   env=env, check=True, capture_output=True, text=True, timeout=30)
        return json.loads(completed.stdout)
    assert run("pause") == {"paused": True, "status": "running", "execution_count": 0}
    assert run("approve") == {"paused": False, "status": "completed", "execution_count": 1}


@needs_saver
def test_crash_after_result_commit_before_checkpoint_replays_without_duplicate(tmp_path):
    checkpoint, ledger = tmp_path / "checkpoint.sqlite", tmp_path / "ledger.sqlite"
    store = SqliteWarehouse(ledger)
    config = {"configurable": {"thread_id": "crash"}}
    class CrashAfterCommit:
        def query(self, *args, **kwargs):
            store.query(*args, **kwargs)
            raise RuntimeError("simulated crash after durable result commit")
    with persistent_graph(checkpoint, ledger, warehouse=CrashAfterCommit()) as graph:
        graph.invoke({"question": "查询昨天收入"}, config)
        with pytest.raises(RuntimeError, match="simulated crash"):
            graph.invoke(Command(resume=True), config)
    assert store.execution_count == 1
    with persistent_graph(checkpoint, ledger) as graph:
        result = graph.invoke(None, config)
    assert result["status"] == "completed"
    assert "execute:idempotent_replay" in result["trace"]
    assert SqliteWarehouse(ledger).execution_count == 1
