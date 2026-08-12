import pytest
from langgraph.types import Command

from lg_lab.graph import build_graph
from lg_lab.nodes import execute, verify_result
from lg_lab.sql_policy import inspect_sql
from lg_lab.state import migrate_state
from lg_lab.warehouse import DemoWarehouse


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("", "SQL 为空"),
        ("DELETE FROM daily_metrics", "只允许 SELECT"),
        ("SELECT day FROM daily_metrics; DELETE FROM daily_metrics", "只允许单条"),
        ("SELECT * FROM daily_metrics LIMIT 1", "禁止 SELECT *"),
        ("SELECT d.* FROM daily_metrics AS d LIMIT 1", "通配符"),
        ("SELECT COUNT(*) FROM daily_metrics LIMIT 1", "通配符"),
        ("SELECT day FROM private_table LIMIT 1", "allowlist"),
        ("SELECT day FROM daily_metrics", "LIMIT"),
        ("SELECT day FROM daily_metrics LIMIT 1000", "1..100"),
    ],
)
def test_sql_policy_rejects_unsafe_shapes(sql: str, reason: str) -> None:
    result = inspect_sql(sql, allowed_tables={"daily_metrics"})
    assert result.allowed is False
    assert reason in result.reason


def test_sql_policy_ignores_keywords_inside_string_and_comment() -> None:
    sql = "SELECT 'delete' AS label, day FROM daily_metrics -- DROP TABLE x\nLIMIT 1"
    result = inspect_sql(sql, allowed_tables={"daily_metrics"})
    assert result.allowed is True
    assert result.tables == ["daily_metrics"]


def test_sql_policy_ast_rejects_obfuscated_alias_wildcard() -> None:
    result = inspect_sql(
        "SELECT\n d /* comment */ . * FROM daily_metrics d LIMIT 1",
        allowed_tables={"daily_metrics"},
    )
    assert result.allowed is False
    assert "通配符" in result.reason


def test_v0_checkpoint_state_is_migrated_explicitly() -> None:
    migrated, events = migrate_state(
        {
            "state_version": 0,
            "question": "查询收入",
            "max_retries": 2,
            "retry_count": 1,
            "allowed_table_names": ["daily_metrics"],
        }
    )
    assert migrated["state_version"] == 1
    assert migrated["max_attempts"] == 3
    assert migrated["retries"] == 1
    assert migrated["allowed_tables"] == ["daily_metrics"]
    assert events == ["state:migrated:v0->v1"]


def test_future_checkpoint_version_is_rejected_before_routing() -> None:
    result = build_graph().invoke(
        {"state_version": 99, "question": "查询昨天收入"},
        config=config("future-version"),
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "UNSUPPORTED_STATE_VERSION"
    assert "intent" not in result


def test_graph_records_v0_checkpoint_migration_before_interrupt() -> None:
    result = build_graph().invoke(
        {
            "state_version": 0,
            "question": "查询昨天收入",
            "max_retries": 2,
            "allowed_table_names": ["daily_metrics"],
        },
        config=config("migrate-v0-checkpoint"),
    )
    assert result["state_version"] == 1
    assert result["max_attempts"] == 3
    assert result["trace"][:2] == ["state:migrated:v0->v1", "validate:passed"]
    assert "__interrupt__" in result


def test_sql_policy_fingerprint_is_stable_without_leaking_sql() -> None:
    first = inspect_sql(
        "SELECT day FROM daily_metrics LIMIT 1", allowed_tables={"daily_metrics"}
    )
    second = inspect_sql(
        "SELECT day FROM daily_metrics LIMIT 1", allowed_tables={"daily_metrics"}
    )
    assert first.fingerprint == second.fingerprint
    assert "SELECT" not in first.fingerprint


def test_schema_permission_failure_never_reaches_human_review() -> None:
    result = build_graph().invoke(
        {"question": "查询昨天收入", "allowed_tables": []},
        config=config("no-schema"),
    )
    assert result["error_code"] == "SCHEMA_PERMISSION_DENIED"
    assert result["status"] == "failed"
    assert "__interrupt__" not in result


def test_review_payload_contains_risk_and_sql_fingerprint() -> None:
    result = build_graph().invoke(
        {"question": "查询昨天收入"}, config=config("review-payload")
    )
    payload = result["__interrupt__"][0].value
    assert payload["risk_level"] in {"low", "medium"}
    assert payload["sql_fingerprint"]
    assert payload["sql_fingerprint"] == result["sql_fingerprint"]


def test_user_rejection_has_explicit_terminal_status() -> None:
    graph = build_graph()
    cfg = config("cancelled")
    graph.invoke({"question": "查询昨天收入"}, config=cfg)
    result = graph.invoke(Command(resume=False), config=cfg)
    assert result["status"] == "cancelled"
    assert result["error_code"] == "USER_REJECTED"
    assert result["trace"][-1] == "answer:cancelled"


def test_review_resume_value_must_be_boolean() -> None:
    graph = build_graph()
    cfg = config("invalid-review")
    graph.invoke({"question": "查询昨天收入"}, config=cfg)
    result = graph.invoke(Command(resume="yes"), config=cfg)
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_REVIEW_DECISION"


def test_retry_trace_uses_reducer_without_copying_previous_history() -> None:
    graph = build_graph()
    cfg = config("reducer")
    graph.invoke(
        {"question": "查询昨天收入", "failures_remaining": 2}, config=cfg
    )
    result = graph.invoke(Command(resume=True), config=cfg)
    assert result["trace"].count("validate:passed") == 1
    assert result["trace"].count("execute:transient:1") == 1
    assert result["trace"].count("execute:transient:2") == 1
    assert result["error_history"][0]["retryable"] is True
    assert result["verification_passed"] is True


def test_retry_policy_is_validated_before_graph_loop() -> None:
    result = build_graph().invoke(
        {"question": "查询昨天收入", "max_attempts": 0},
        config=config("bad-retry-policy"),
    )
    assert result["error_code"] == "INVALID_RETRY_POLICY"
    assert "intent" not in result


@pytest.mark.parametrize(
    "state,error_code",
    [
        ({"max_attempts": "3"}, "INVALID_RETRY_POLICY"),
        ({"failures_remaining": -1}, "INVALID_RETRY_POLICY"),
        ({"allowed_tables": "daily_metrics"}, "INVALID_TABLE_POLICY"),
    ],
)
def test_unvalidated_typed_dict_input_is_checked_at_boundary(
    state: dict, error_code: str
) -> None:
    result = build_graph().invoke(
        {"question": "查询昨天收入", **state},
        config=config(f"bad-input-{error_code}-{state}"),
    )
    assert result["error_code"] == error_code


def test_execute_uses_idempotency_key_on_replay() -> None:
    warehouse = DemoWarehouse()
    state = {
        "sql": "SELECT day, revenue FROM daily_metrics LIMIT 1",
        "execution_key": "request:fingerprint",
        "trace": [],
    }
    first = execute(state, warehouse=warehouse)
    second = execute({**state, **first}, warehouse=warehouse)
    assert warehouse.execution_count == 1
    assert second["trace"] == ["execute:idempotent_replay"]
    assert first["rows"] == second["rows"]


def test_independent_threads_do_not_share_idempotency_key() -> None:
    warehouse = DemoWarehouse()
    graph = build_graph(warehouse=warehouse)
    for thread_id in ("same-question-a", "same-question-b"):
        cfg = config(thread_id)
        graph.invoke({"question": "查询昨天收入"}, config=cfg)
        graph.invoke(Command(resume=True), config=cfg)
    assert warehouse.execution_count == 2


def test_result_verifier_rejects_empty_or_impossible_ratio() -> None:
    empty = verify_result({"rows": []})
    invalid = verify_result({"rows": [{"success_rate": 1.5}]})
    assert empty["error_code"] == "NO_DATA"
    assert invalid["error_code"] == "RESULT_VALIDATION_FAILED"


def test_checkpoint_keeps_inspectable_state_history() -> None:
    graph = build_graph()
    cfg = config("history")
    graph.invoke({"question": "查询昨天收入"}, config=cfg)
    graph.invoke(Command(resume=True), config=cfg)
    history = list(graph.get_state_history(cfg))
    assert len(history) >= 4
    assert history[0].values["status"] == "completed"
    assert any("sql_fingerprint" in snapshot.values for snapshot in history)


def test_stream_updates_exposes_node_boundaries() -> None:
    graph = build_graph()
    updates = list(
        graph.stream(
            {"question": "成功率是什么"},
            config=config("stream"),
            stream_mode="updates",
        )
    )
    node_names = [next(iter(update)) for update in updates]
    assert node_names == ["validate", "classify", "answer"]
