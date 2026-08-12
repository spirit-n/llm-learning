import json
import sys

import pytest


VALID_CASES = [
    ("SELECT day FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev"),
    ("select day from analytics.public_metrics limit 10", "tenant-b", None, "dev"),
    ("/* comment */ SELECT day, revenue FROM analytics.daily_metrics LIMIT 50", "tenant-a", "revenue", "dev"),
    (
        "SELECT success_count / nullIf(request_count, 0) AS success_rate "
        "FROM analytics.daily_metrics LIMIT 20",
        "tenant-a",
        "success_rate",
        "dev",
    ),
    ("SELECT count(DISTINCT user_id) FROM analytics.orders LIMIT 1", "tenant-a", "active_users", "dev"),
    ("SELECT day, sum(revenue) FROM analytics.daily_metrics GROUP BY day LIMIT 30", "tenant-a", "revenue", "dev"),
    (
        "WITH x AS (SELECT day FROM analytics.public_metrics LIMIT 5) "
        "SELECT day FROM x LIMIT 5",
        "tenant-b",
        None,
        "dev",
    ),
    ("SELECT day AS d FROM analytics.public_metrics ORDER BY d LIMIT 100", "tenant-a", None, "dev"),
    ("SELECT revenue FROM analytics.orders WHERE revenue > 0 LIMIT 100", "tenant-a", "revenue", "dev"),
    ("SELECT success_rate FROM analytics.public_metrics LIMIT 7", "tenant-b", "success_rate", "dev"),
    ("SELECT day FROM analytics.public_metrics LIMIT 500", "tenant-b", None, "staging"),
    ("SELECT day FROM analytics.public_metrics WHERE day >= today() - 7 LIMIT 200", "tenant-a", None, "prod"),
]

REJECT_CASES = [
    ("DELETE FROM analytics.daily_metrics", "tenant-a", None, "dev", "READ_ONLY_SELECT_REQUIRED"),
    ("INSERT INTO analytics.daily_metrics VALUES (1)", "tenant-a", None, "dev", "READ_ONLY_SELECT_REQUIRED"),
    ("UPDATE analytics.daily_metrics SET revenue=0", "tenant-a", None, "dev", "READ_ONLY_SELECT_REQUIRED"),
    ("DROP TABLE analytics.daily_metrics", "tenant-a", None, "dev", "READ_ONLY_SELECT_REQUIRED"),
    (
        "SELECT day FROM analytics.public_metrics; SELECT day FROM analytics.public_metrics",
        "tenant-a",
        None,
        "dev",
        "MULTI_STATEMENT",
    ),
    (
        "SELECT day FROM analytics.public_metrics UNION ALL SELECT day FROM analytics.public_metrics LIMIT 5",
        "tenant-a",
        None,
        "dev",
        "READ_ONLY_SELECT_REQUIRED",
    ),
    ("SELECT * FROM analytics.daily_metrics LIMIT 10", "tenant-a", None, "dev", "STAR_FORBIDDEN"),
    ("SELECT customer_email FROM analytics.daily_metrics LIMIT 10", "tenant-a", None, "dev", "SENSITIVE_COLUMN"),
    ("SELECT phone FROM analytics.orders LIMIT 10", "tenant-a", None, "dev", "SENSITIVE_COLUMN"),
    ("SELECT api_secret FROM analytics.orders LIMIT 10", "tenant-a", None, "dev", "SENSITIVE_COLUMN"),
    ("SELECT password_hash FROM analytics.orders LIMIT 10", "tenant-a", None, "dev", "SENSITIVE_COLUMN"),
    ("SELECT day FROM private.payroll LIMIT 10", "tenant-a", None, "dev", "TABLE_FORBIDDEN"),
    ("SELECT event_time FROM system.query_log LIMIT 10", "tenant-a", None, "dev", "TABLE_FORBIDDEN"),
    ("SELECT day FROM analytics.public_metrics", "tenant-a", None, "dev", "LIMIT_REQUIRED"),
    ("SELECT day FROM analytics.public_metrics LIMIT 1001", "tenant-a", None, "dev", "LIMIT_TOO_LARGE"),
    ("SELECT day FROM analytics.public_metrics LIMIT 201", "tenant-a", None, "prod", "LIMIT_TOO_LARGE"),
    ("SELECT day FROM analytics.public_metrics LIMIT toUInt32(10)", "tenant-a", None, "dev", "DYNAMIC_LIMIT"),
    ("SELECT day FROM analytics.public_metrics LIMIT 0", "tenant-a", None, "dev", "LIMIT_NON_POSITIVE"),
    (
        "SELECT day FROM analytics.public_metrics LIMIT 10 OFFSET 10001",
        "tenant-a",
        None,
        "dev",
        "OFFSET_TOO_LARGE",
    ),
    (
        "SELECT day FROM analytics.public_metrics LIMIT 10 OFFSET toUInt64(1)",
        "tenant-a",
        None,
        "dev",
        "DYNAMIC_OFFSET",
    ),
    ("SELECT file('/tmp/x') FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "DANGEROUS_FUNCTION"),
    ("SELECT url('https://evil') FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "DANGEROUS_FUNCTION"),
    ("SELECT remote('host') FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "DANGEROUS_FUNCTION"),
    ("SELECT s3('bucket') FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "DANGEROUS_FUNCTION"),
    ("SELECT sleep(10) FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "DANGEROUS_FUNCTION"),
    (
        "SELECT day FROM analytics.public_metrics LIMIT 10 SETTINGS max_execution_time=0",
        "tenant-a",
        None,
        "dev",
        "QUERY_SETTINGS_FORBIDDEN",
    ),
    ("SELECT 1 LIMIT 1", "tenant-a", None, "dev", "TABLE_REQUIRED"),
    ("SELECT day FROM analytics.public_metrics LIMIT 1", "unknown", None, "dev", "UNKNOWN_TENANT"),
    ("SELECT day FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "local", "UNKNOWN_ENVIRONMENT"),
    ("SELECT unknown_field FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev", "COLUMN_FORBIDDEN"),
    ("SELECT o.success_rate FROM analytics.orders o LIMIT 1", "tenant-a", None, "dev", "COLUMN_FORBIDDEN"),
    ("SELECT FROM", "tenant-a", None, "dev", "SQL_PARSE_ERROR"),
    ("   ", "tenant-a", None, "dev", "EMPTY_SQL"),
]

METRIC_CONFLICTS = [
    ("SELECT success_count FROM analytics.daily_metrics LIMIT 1", "success_rate", "METRIC_MISMATCH"),
    (
        "SELECT success_count, request_count FROM analytics.daily_metrics LIMIT 1",
        "success_rate",
        "METRIC_EXPRESSION_MISMATCH",
    ),
    (
        "SELECT success_count / request_count FROM analytics.daily_metrics LIMIT 1",
        "success_rate",
        "METRIC_EXPRESSION_MISMATCH",
    ),
    (
        "SELECT request_count / nullIf(success_count, 0) FROM analytics.daily_metrics LIMIT 1",
        "success_rate",
        "METRIC_EXPRESSION_MISMATCH",
    ),
    ("SELECT day FROM analytics.daily_metrics LIMIT 1", "revenue", "METRIC_MISMATCH"),
    (
        "SELECT day FROM analytics.daily_metrics WHERE revenue > 0 LIMIT 1",
        "revenue",
        "METRIC_MISMATCH",
    ),
    ("SELECT count(user_id) FROM analytics.orders LIMIT 1", "active_users", "METRIC_EXPRESSION_MISMATCH"),
    ("SELECT user_id FROM analytics.orders LIMIT 1", "missing_metric", "UNKNOWN_METRIC"),
]


@pytest.mark.parametrize(("sql", "tenant", "metric", "environment"), VALID_CASES)
def test_valid_queries_are_stable_passes(validator, sql, tenant, metric, environment):
    first = validator(sql, tenant, metric, environment)
    second = validator(sql, tenant, metric, environment)
    assert first == second
    assert first.decision == "pass"
    assert first.normalized_sql
    assert first.policy_version
    assert first.effective_max_limit is not None


@pytest.mark.parametrize(("sql", "tenant", "metric", "environment", "reason"), REJECT_CASES)
def test_unsafe_or_unsupported_queries_are_rejected(validator, sql, tenant, metric, environment, reason):
    result = validator(sql, tenant, metric, environment)
    assert result.decision == "reject"
    assert reason in result.reason_codes
    assert result.normalized_sql is None


@pytest.mark.parametrize(("sql", "metric", "reason"), METRIC_CONFLICTS)
def test_metric_semantics_are_checked_beyond_field_presence(validator, sql, metric, reason):
    result = validator(sql, "tenant-a", metric, "dev")
    assert result.decision == "reject"
    assert reason in result.reason_codes


def test_environment_specific_limit_is_exposed_in_result(validator):
    assert validator("SELECT day FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "dev").effective_max_limit == 1000
    assert validator("SELECT day FROM analytics.public_metrics LIMIT 1", "tenant-a", None, "prod").effective_max_limit == 200


@pytest.mark.parametrize(
    ("sql", "warning_fragment"),
    [
        ("SELECT day FROM analytics.public_metrics FINAL LIMIT 1", "FINAL"),
        (
            "SELECT o.order_id FROM analytics.orders o "
            "JOIN analytics.daily_metrics d ON o.day = d.day LIMIT 10",
            "join_count=1",
        ),
        ("SELECT DISTINCT day FROM analytics.public_metrics LIMIT 10", "DISTINCT"),
        (
            "SELECT dictGet('geo', 'country', user_id) FROM analytics.orders LIMIT 10",
            "dictionary access detected: dictget",
        ),
    ],
)
def test_expensive_but_read_only_shapes_emit_warnings(validator, sql, warning_fragment):
    result = validator(sql, "tenant-a", None, "dev")
    assert result.decision == "pass"
    assert any(warning_fragment in warning for warning in result.warnings)


def test_prod_query_without_filter_warns_but_does_not_override_guard(validator):
    result = validator("SELECT day FROM analytics.public_metrics LIMIT 100", "tenant-a", None, "prod")
    assert result.decision == "pass"
    assert "production query has no WHERE filter" in result.warnings


def test_too_long_sql_is_rejected_before_parser_work(validator):
    result = validator("SELECT " + "x" * 20_001, "tenant-a")
    assert result.reason_codes == ["SQL_TOO_LONG"]


def test_rejection_can_report_multiple_independent_failures(validator):
    result = validator(
        "SELECT *, customer_email, sleep(1) FROM analytics.daily_metrics LIMIT 5000",
        "tenant-a",
        environment="prod",
    )
    assert {"STAR_FORBIDDEN", "SENSITIVE_COLUMN", "DANGEROUS_FUNCTION", "LIMIT_TOO_LARGE"}.issubset(
        result.reason_codes
    )
    assert result.normalized_sql is None


def test_cli_pass_prints_json_without_error(validator_module, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_sql.py",
            "--sql",
            "SELECT day FROM analytics.public_metrics LIMIT 1",
            "--tenant",
            "tenant-a",
        ],
    )
    validator_module.main()
    assert json.loads(capsys.readouterr().out)["decision"] == "pass"


def test_cli_reject_uses_exit_code_two_and_keeps_machine_readable_json(
    validator_module,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_sql.py",
            "--sql",
            "DROP TABLE analytics.public_metrics",
            "--tenant",
            "tenant-a",
        ],
    )
    with pytest.raises(SystemExit) as captured:
        validator_module.main()
    assert captured.value.code == 2
    assert json.loads(capsys.readouterr().out)["decision"] == "reject"
