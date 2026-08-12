import pytest

from mcp_lab.guard import GuardError, validate_readonly_sql


def rejects(sql: str, code: str, **kwargs) -> None:
    with pytest.raises(GuardError) as caught:
        validate_readonly_sql(sql, tenant=kwargs.get("tenant", "tenant-a"), max_rows=kwargs.get("max_rows", 100))
    assert caught.value.code == code


def test_valid_select_gets_forced_limit():
    result = validate_readonly_sql("SELECT day, revenue FROM analytics.daily_metrics", "tenant-a", 20)
    assert result.max_rows == 20
    assert "LIMIT 20" in result.normalized_sql


def test_existing_limit_is_clamped():
    result = validate_readonly_sql("SELECT day FROM analytics.daily_metrics LIMIT 999", "tenant-a", 10)
    assert "LIMIT 10" in result.normalized_sql


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("DELETE FROM analytics.daily_metrics", "READ_ONLY_REQUIRED"),
        ("/* harmless */ DROP TABLE analytics.daily_metrics", "READ_ONLY_REQUIRED"),
        ("SELECT day FROM analytics.daily_metrics; SELECT day FROM analytics.public_metrics", "MULTI_STATEMENT"),
        ("SELECT * FROM analytics.daily_metrics", "STAR_FORBIDDEN"),
        ("SELECT customer_email FROM analytics.daily_metrics", "SENSITIVE_COLUMN"),
        ("SELECT imaginary_column FROM analytics.daily_metrics", "COLUMN_NOT_FOUND"),
        ("SELECT day FROM system.query_log", "TABLE_FORBIDDEN"),
        ("SELECT day FROM analytics.daily_metrics WHERE url('https://evil') = 'x'", "DANGEROUS_FUNCTION"),
        ("SELECT sleep(10) FROM analytics.daily_metrics", "DANGEROUS_FUNCTION"),
        ("SELECT 1", "TABLE_REQUIRED"),
    ],
)
def test_attack_and_misuse_cases(sql: str, code: str):
    rejects(sql, code)


def test_tenant_table_isolation():
    rejects("SELECT day FROM analytics.daily_metrics", "TABLE_FORBIDDEN", tenant="tenant-b")


def test_invalid_row_budget():
    rejects("SELECT day FROM analytics.public_metrics", "ROW_LIMIT_INVALID", max_rows=1000)


def test_guard_returns_only_explicit_projection_for_the_executor():
    result = validate_readonly_sql(
        "SELECT day, revenue FROM analytics.daily_metrics WHERE request_count > 0",
        "tenant-a",
    )
    assert result.projected_columns == ("day", "revenue")
