"""Opt-in real MySQL tests, each isolated in a disposable database."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(os.getenv("RUN_MYSQL_INTEGRATION") != "1", reason="set RUN_MYSQL_INTEGRATION=1 to use real MySQL")


@pytest.fixture
def mysql_url(monkeypatch):
    from learning_db import database_url
    url = make_url(database_url())
    name = "llm_test_" + uuid4().hex
    admin = create_engine(url.set(database=None), isolation_level="AUTOCOMMIT")
    with admin.connect() as db:
        db.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"))
    test_url = url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", test_url)
    try:
        yield test_url
    finally:
        with admin.connect() as db:
            db.execute(text(f"DROP DATABASE `{name}`"))
        admin.dispose()


def test_analytics_is_persistent_and_seed_does_not_overwrite(mysql_url):
    from tool_loop.tools import AnalyticsStore
    store = AnalyticsStore()
    with store.db.transaction() as db:
        db.execute(text("UPDATE sales SET amount=123.0 WHERE order_id='A100'"))
    reopened = AnalyticsStore()
    assert reopened.query("SELECT amount FROM sales WHERE order_id='A100' LIMIT 1") == [{"amount": 123.0}]
    assert len(reopened.query("SELECT order_id FROM sales LIMIT 10")) == 3
    assert reopened.query("SELECT channel FROM sales WHERE channel LIKE 'we%' LIMIT 1") == [{"channel": "wechat"}]
    assert reopened.query("SELECT ':literal' AS label FROM sales LIMIT 1") == [{"label": ":literal"}]
    from tool_loop.guards import GuardDenied
    for sql in ["DELETE FROM sales", "SELECT amount FROM mysql.sales", "SELECT SLEEP(10) FROM sales", "SELECT amount INTO OUTFILE '/tmp/test' FROM sales", "SELECT /*+ MAX_EXECUTION_TIME(0) */ amount FROM sales"]:
        with pytest.raises(GuardDenied):
            reopened.query(sql)


def test_idempotency_concurrency_reopen_and_conflict(mysql_url):
    from harness_lab.persistence import IdempotencyStore
    store = IdempotencyStore()
    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(lambda _: store.reserve("请求:中文", "sig")[0], range(8)))
    assert states.count("reserved") == 1
    store.complete("请求:中文", "sig", {"报告": "完成"})
    reopened = IdempotencyStore()
    assert reopened.lookup("请求:中文", "sig") == ("completed", {"报告": "完成"})
    assert reopened.reserve("请求:中文", "other")[0] == "conflict"
    store.reserve("crashed", "sig")
    assert reopened.reserve("crashed", "sig")[0] == "in_progress"
    reopened.mark_unknown("crashed", "sig")
    assert reopened.reserve("crashed", "sig")[0] == "unknown"


def test_report_concurrent_steps_tenant_and_budget(mysql_url):
    from harness_lab.persistence import ReportWorkflow
    store = ReportWorkflow()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.advance("job", "tenant-a"), range(4)))
    assert store.advance("job", "tenant-a") == {"phase": "completed", "cost_units": 2, "replayed": True}
    with store.store.db.connection() as db:
        assert db.execute(text("SELECT COUNT(*) FROM reports")).scalar_one() == 1
    with pytest.raises(PermissionError):
        store.advance("job", "tenant-b")
    store.advance("limited", "tenant-a", max_cost_units=1)
    with pytest.raises(ValueError, match="预算"):
        ReportWorkflow().advance("limited", "tenant-a", max_cost_units=1)


def test_warehouse_rollback_replay_and_concurrency(mysql_url):
    from lg_lab.persistence import PersistentWarehouse
    from lg_lab.warehouse import TransientWarehouseError
    store = PersistentWarehouse()
    sql = "SELECT day,revenue FROM daily_metrics LIMIT 1"
    with pytest.raises(TransientWarehouseError):
        store.query(sql, idempotency_key="rollback", simulate_transient=True)
    assert store.execution_count == 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.query(sql, idempotency_key="once"), range(8)))
    assert sum(not replayed for _, replayed in results) == 1
    assert PersistentWarehouse().execution_count == 1
    with pytest.raises(ValueError, match="different SQL"):
        store.query("SELECT day FROM daily_metrics LIMIT 1", idempotency_key="once")


def test_mysql_executable_comment_cannot_change_validated_query(mysql_url):
    from lg_lab.persistence import PersistentWarehouse
    from tool_loop.tools import AnalyticsStore
    # MySQL would execute the embedded LIMIT 0; the parsed AST treats it as a comment.
    rows, replayed = PersistentWarehouse().query(
        "SELECT day,revenue FROM daily_metrics /*!50000 LIMIT 0 */ LIMIT 1", idempotency_key="comment")
    assert not replayed and len(rows) == 1
    assert len(AnalyticsStore().query("SELECT amount FROM sales /*!50000 LIMIT 0 */")) == 3


def test_langgraph_pause_resume_in_separate_processes(mysql_url):
    def run(action):
        result = subprocess.run([sys.executable, "-m", "lg_lab.persistent_demo", action, "--thread", "restart"],
                                check=True, capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout)
    assert run("pause") == {"paused": True, "status": "running", "execution_count": 0}
    assert run("approve") == {"paused": False, "status": "completed", "execution_count": 1}


def test_crash_after_commit_replays_result(mysql_url):
    from lg_lab.persistence import PersistentWarehouse, persistent_graph
    from langgraph.types import Command
    store = PersistentWarehouse()
    config = {"configurable": {"thread_id": "crash"}}
    class CrashAfterCommit:
        def query(self, *args, **kwargs):
            store.query(*args, **kwargs)
            raise RuntimeError("simulated crash")
    with persistent_graph(warehouse=CrashAfterCommit()) as graph:
        graph.invoke({"question": "查询昨天收入"}, config)
        with pytest.raises(RuntimeError, match="simulated crash"):
            graph.invoke(Command(resume=True), config)
    with persistent_graph() as graph:
        result = graph.invoke(None, config)
    assert result["status"] == "completed"
    assert "execute:idempotent_replay" in result["trace"]
    assert store.execution_count == 1


def test_deployment_ready_detects_missing_table(mysql_url):
    from deploy_lab.app import PersistentStore, create_app
    from fastapi.testclient import TestClient
    store = PersistentStore()
    with TestClient(create_app(store)) as client:
        response = client.post("/demo", json={"question": "test"})
        assert response.status_code == 200
        with store.db.connection() as db:
            assert db.execute(text("SELECT COUNT(*) FROM requests")).scalar_one() == 1
        with store.db.transaction() as db:
            db.execute(text("DROP TABLE requests"))
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/demo", json={"question": "test"}).status_code == 503
