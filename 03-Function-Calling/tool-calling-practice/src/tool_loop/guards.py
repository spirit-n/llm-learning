from __future__ import annotations

import json
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class GuardDenied(Exception):
    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


ALLOWED_TABLES = {"sales", "customers"}
SENSITIVE_COLUMNS = {"email", "password", "password_hash", "api_key", "token"}
FORBIDDEN_NODE_NAMES = {
    "Alter",
    "Analyze",
    "Attach",
    "Command",
    "Commit",
    "Copy",
    "Create",
    "Delete",
    "Detach",
    "Drop",
    "Grant",
    "Insert",
    "LoadData",
    "Lock",
    "Merge",
    "Pragma",
    "Rollback",
    "Set",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
}
DANGEROUS_FUNCTIONS = {
    "load_extension",
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "sqlite_scan",
}
SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "authorization")


def validate_and_rewrite_readonly_sql(
    sql: str,
    max_rows: int,
    allowed_tables: set[str] | None = None,
) -> str:
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except ParseError as exc:
        raise GuardDenied("SQL_PARSE_ERROR", "SQL 无法解析") from exc

    if len(statements) != 1:
        raise GuardDenied("SQL_MULTIPLE_STATEMENTS", "只允许一条 SQL 语句")

    statement = statements[0]
    if statement is None or not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise GuardDenied("SQL_NOT_READONLY", "只允许 SELECT 查询")

    for node in statement.walk():
        if type(node).__name__ in FORBIDDEN_NODE_NAMES:
            raise GuardDenied("SQL_NOT_READONLY", "检测到非只读 SQL 操作")

    if statement.find(exp.Star):
        raise GuardDenied("SQL_STAR_DENIED", "禁止 SELECT *，请明确列名")

    for function in statement.find_all(exp.Func):
        if function.sql_name().lower() in DANGEROUS_FUNCTIONS:
            raise GuardDenied("SQL_FUNCTION_DENIED", "SQL 包含危险函数")

    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    table_names = {
        table.name.lower()
        for table in statement.find_all(exp.Table)
        if table.name.lower() not in cte_names
    }
    if not table_names:
        raise GuardDenied("SQL_TABLE_REQUIRED", "查询必须使用允许的数据表")
    table_allowlist = ALLOWED_TABLES if allowed_tables is None else allowed_tables
    disallowed_tables = table_names - table_allowlist
    if disallowed_tables:
        names = ", ".join(sorted(disallowed_tables))
        raise GuardDenied("SQL_TABLE_DENIED", f"无权访问数据表：{names}")

    selected_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
    blocked_columns = selected_columns & SENSITIVE_COLUMNS
    if blocked_columns:
        names = ", ".join(sorted(blocked_columns))
        raise GuardDenied("SQL_COLUMN_DENIED", f"无权访问敏感列：{names}")

    effective_limit = max_rows
    limit_node = statement.args.get("limit")
    if limit_node is not None:
        limit_expression = limit_node.expression
        if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
            raise GuardDenied("SQL_LIMIT_INVALID", "LIMIT 必须是整数")
        effective_limit = min(max_rows, int(limit_expression.this))

    return statement.limit(effective_limit, copy=True).sql(dialect="sqlite")


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def limit_output(value: Any, max_bytes: int) -> tuple[Any, bool, int]:
    redacted = redact_sensitive(value)
    encoded = json.dumps(redacted, ensure_ascii=False, default=str).encode("utf-8")
    original_bytes = len(encoded)
    if original_bytes <= max_bytes:
        return redacted, False, original_bytes

    preview = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return {
        "preview": preview,
        "notice": "工具输出已截断",
        "original_bytes": original_bytes,
    }, True, original_bytes
