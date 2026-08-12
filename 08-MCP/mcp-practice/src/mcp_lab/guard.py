"""在执行前进行确定性的 SQL AST 与权限检查。"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from mcp_lab.domain import SCHEMAS, TENANT_TABLES


class GuardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GuardResult:
    normalized_sql: str
    tables: tuple[str, ...]
    projected_columns: tuple[str, ...]
    max_rows: int


DANGEROUS_FUNCTIONS = {"file", "url", "remote", "remotesecure", "s3", "hdfs", "sleep"}
SENSITIVE_COLUMNS = {
    column
    for schema in SCHEMAS.values()
    for column in schema["sensitive_columns"]
}


def validate_readonly_sql(sql: str, tenant: str, max_rows: int = 100) -> GuardResult:
    if tenant not in TENANT_TABLES:
        raise GuardError("UNKNOWN_TENANT", "未知租户")
    if not 1 <= max_rows <= 100:
        raise GuardError("ROW_LIMIT_INVALID", "max_rows 必须在 1 到 100 之间")

    try:
        statements = sqlglot.parse(sql, read="clickhouse")
    except sqlglot.errors.ParseError as exc:
        raise GuardError("SQL_PARSE_ERROR", "SQL 无法解析") from exc

    if len(statements) != 1:
        raise GuardError("MULTI_STATEMENT", "只允许一条 SQL")
    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise GuardError("READ_ONLY_REQUIRED", "只允许 SELECT")

    tables = tuple(sorted({_qualified_table(table) for table in statement.find_all(exp.Table)}))
    if not tables:
        raise GuardError("TABLE_REQUIRED", "查询必须指定表")
    denied = [table for table in tables if table not in TENANT_TABLES[tenant]]
    if denied:
        raise GuardError("TABLE_FORBIDDEN", "请求包含无权访问的表")

    if any(isinstance(node, exp.Star) for node in statement.walk()):
        raise GuardError("STAR_FORBIDDEN", "禁止 SELECT *，请显式选择字段")
    selected_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
    if selected_columns & SENSITIVE_COLUMNS:
        raise GuardError("SENSITIVE_COLUMN", "请求包含敏感字段")

    allowed_columns = {
        column.lower()
        for table in tables
        for column in SCHEMAS[tuple(table.split(".", 1))]["columns"]
    }
    unknown_columns = selected_columns - allowed_columns
    if unknown_columns:
        raise GuardError("COLUMN_NOT_FOUND", "请求包含不存在或不可见的字段")

    functions = {_function_name(node) for node in statement.find_all(exp.Func)}
    if functions & DANGEROUS_FUNCTIONS:
        raise GuardError("DANGEROUS_FUNCTION", "请求包含禁止函数")

    existing_limit = statement.args.get("limit")
    if existing_limit is not None:
        expression = existing_limit.expression
        if not isinstance(expression, exp.Literal) or not expression.is_int:
            raise GuardError("DYNAMIC_LIMIT", "LIMIT 必须是整数常量")
        max_rows = min(max_rows, int(expression.this))
    statement.set("limit", None)
    normalized = statement.limit(max_rows).sql(dialect="clickhouse")
    projected_columns = tuple(
        dict.fromkeys(
            column.name.lower()
            for projection in statement.expressions
            for column in projection.find_all(exp.Column)
        )
    )
    return GuardResult(
        normalized_sql=normalized,
        tables=tables,
        projected_columns=projected_columns,
        max_rows=max_rows,
    )


def _qualified_table(table: exp.Table) -> str:
    database = table.db or "analytics"
    return f"{database}.{table.name}".lower()


def _function_name(function: exp.Func) -> str:
    name = function.sql_name().lower()
    if name == "anonymous":
        return str(function.name).lower()
    return name
