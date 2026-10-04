import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from harness_lab.persistence import SQLiteIdempotencyStore, SQLiteReportWorkflow
from harness_lab.usage import receipt_from_result


def test_store_reopens_replays_and_rejects_conflict(tmp_path):
    path = tmp_path / "state.sqlite"
    store = SQLiteIdempotencyStore(path)
    assert store.reserve("tenant:request", "sig")[0] == "reserved"
    store.complete("tenant:request", "sig", {"ok": True})
    reopened = SQLiteIdempotencyStore(path)
    assert reopened.lookup("tenant:request", "sig") == ("completed", {"ok": True})
    assert reopened.reserve("tenant:request", "different")[0] == "conflict"


def test_crashed_in_progress_is_not_automatically_reexecuted(tmp_path):
    path = tmp_path / "state.sqlite"
    SQLiteIdempotencyStore(path).reserve("request", "sig")
    reopened = SQLiteIdempotencyStore(path)
    assert reopened.reserve("request", "sig")[0] == "in_progress"
    reopened.mark_unknown("request", "sig")
    assert reopened.reserve("request", "sig")[0] == "unknown"


def test_concurrent_reservation_has_one_winner(tmp_path):
    store = SQLiteIdempotencyStore(tmp_path / "state.sqlite")
    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(lambda _: store.reserve("request", "sig")[0], range(4)))
    assert states.count("reserved") == 1


def test_real_process_restart_recovers_checkpoint_without_duplicate_effect(tmp_path):
    path = tmp_path / "state.sqlite"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    outputs = []
    for _ in range(3):
        result = subprocess.run([sys.executable, "-m", "harness_lab.persistence", "--db", str(path)],
                                check=True, capture_output=True, text=True, env=env)
        outputs.append(json.loads(result.stdout))
    assert [item["phase"] for item in outputs] == ["report_created", "completed", "completed"]
    assert outputs[-1]["replayed"] is True
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1


def test_budget_and_tenant_survive_restart(tmp_path):
    path = tmp_path / "state.sqlite"
    SQLiteReportWorkflow(path).advance("job", "tenant-a", max_cost_units=1)
    with pytest.raises(ValueError, match="预算"):
        SQLiteReportWorkflow(path).advance("job", "tenant-a", max_cost_units=1)
    with pytest.raises(PermissionError):
        SQLiteReportWorkflow(path).advance("job", "tenant-b")


def test_missing_provider_usage_is_unknown_not_free():
    from types import SimpleNamespace
    receipt = receipt_from_result(SimpleNamespace(response_id=None, model=None, usage=None, attempts=2))
    assert receipt.usage is None and receipt.cost_usd is None and receipt.attempts == 2
