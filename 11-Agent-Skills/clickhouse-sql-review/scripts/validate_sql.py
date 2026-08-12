"""Deterministically review ClickHouse SQL without executing it."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field

import sqlglot
from sqlglot import exp


POLICY_VERSION = "2026-08-v2"
MAX_SQL_CHARS = 20_000
MAX_OFFSET = 10_000
MAX_LIMIT_BY_ENVIRONMENT = {"dev": 1000, "staging": 500, "prod": 200}

ALLOWED_TABLES = {
    "tenant-a": {"analytics.daily_metrics", "analytics.orders", "analytics.public_metrics"},
    "tenant-b": {"analytics.public_metrics"},
}
TABLE_COLUMNS = {
    "analytics.daily_metrics": {"day", "revenue", "success_count", "request_count", "success_rate"},
    "analytics.orders": {"day", "order_id", "user_id", "revenue", "status"},
    "analytics.public_metrics": {"day", "success_rate", "success_count", "request_count"},
}
SENSITIVE_COLUMNS = {"customer_email", "phone", "api_secret", "password_hash"}
DANGEROUS_FUNCTIONS = {
    "file",
    "url",
    "remote",
    "remotesecure",
    "s3",
    "hdfs",
    "azureblobstorage",
    "mysql",
    "postgresql",
    "jdbc",
    "odbc",
    "sleep",
}
DICTIONARY_FUNCTIONS = {
    "dictget",
    "dictgetordefault",
    "dicthas",
    "dictgethierarchy",
    "dictisin",
    "dictgetchildren",
    "dictgetdescendants",
}
METRIC_REQUIREMENTS = {
    "success_rate": {"success_count", "request_count"},
    "revenue": {"revenue"},
    "active_users": {"user_id"},
}


@dataclass(frozen=True)
class ReviewResult:
    decision: str
    reason_codes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    suggested_fix: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_sql: str | None = None
    checked_tables: list[str] = field(default_factory=list)
    checked_columns: list[str] = field(default_factory=list)
    effective_max_limit: int | None = None
    environment: str = "dev"
    policy_version: str = POLICY_VERSION


def validate_sql(sql: str, tenant: str, metric: str | None = None, environment: str = "dev") -> ReviewResult:
    """解析并静态评审 SQL；函数本身绝不连接数据库。"""

    if not isinstance(sql, str) or not sql.strip():
        return _reject("EMPTY_SQL", "SQL is empty", "provide one SELECT statement", environment)
    if len(sql) > MAX_SQL_CHARS:
        return _reject(
            "SQL_TOO_LONG",
            f"characters={len(sql)}",
            f"reduce SQL to at most {MAX_SQL_CHARS} characters",
            environment,
        )
    if tenant not in ALLOWED_TABLES:
        return _reject("UNKNOWN_TENANT", "tenant is not configured", "provide an authorized tenant", environment)
    if environment not in MAX_LIMIT_BY_ENVIRONMENT:
        return _reject("UNKNOWN_ENVIRONMENT", environment, "use dev, staging, or prod", environment)

    try:
        statements = [value for value in sqlglot.parse(sql, read="clickhouse") if value is not None]
    except sqlglot.errors.ParseError:
        return _reject("SQL_PARSE_ERROR", "parser rejected SQL", "fix syntax before review", environment)
    if len(statements) != 1:
        return _reject("MULTI_STATEMENT", f"statement_count={len(statements)}", "submit one SELECT statement", environment)

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        # 只接受根节点为 SELECT，宁可明确拒绝 UNION/EXPLAIN 等未建模形态，也不靠
        # startswith("select") 猜测只读性。
        return _reject(
            "READ_ONLY_SELECT_REQUIRED",
            statement.key.upper(),
            "rewrite as one bounded SELECT or add explicit validator support for this shape",
            environment,
        )

    reasons: list[str] = []
    evidence: list[str] = []
    fixes: list[str] = []
    warnings: list[str] = []
    max_limit = MAX_LIMIT_BY_ENVIRONMENT[environment]

    if statement.args.get("settings"):
        reasons.append("QUERY_SETTINGS_FORBIDDEN")
        evidence.append("query-level SETTINGS")
        fixes.append("remove SETTINGS; execution service owns timeout and resource settings")

    cte_names = {cte.alias_or_name.casefold() for cte in statement.find_all(exp.CTE)}
    table_nodes = [
        table for table in statement.find_all(exp.Table) if table.name.casefold() not in cte_names
    ]
    tables = sorted({_qualified_table(table) for table in table_nodes})
    if not tables:
        reasons.append("TABLE_REQUIRED")
        evidence.append("no table reference")
        fixes.append("query an authorized analytics table")

    forbidden_tables = [table for table in tables if table not in ALLOWED_TABLES[tenant]]
    if forbidden_tables:
        reasons.append("TABLE_FORBIDDEN")
        evidence.extend(forbidden_tables)
        fixes.append("remove tables outside the tenant allowlist")

    if any(isinstance(node, exp.Star) for node in statement.walk()):
        reasons.append("STAR_FORBIDDEN")
        evidence.append("SELECT *")
        fixes.append("list only required non-sensitive columns")

    column_nodes = list(statement.find_all(exp.Column))
    columns = {column.name.casefold() for column in column_nodes}
    projection_aliases = {
        expression.alias.casefold()
        for expression in statement.expressions
        if expression.alias
    }
    forbidden_columns = sorted(columns & SENSITIVE_COLUMNS)
    if forbidden_columns:
        reasons.append("SENSITIVE_COLUMN")
        evidence.extend(forbidden_columns)
        fixes.append("remove or replace sensitive columns with approved aggregates")

    unauthorized_columns = _unauthorized_columns(
        column_nodes,
        table_nodes,
        tables,
        cte_names=cte_names,
        projection_aliases=projection_aliases,
    )
    unauthorized_columns -= SENSITIVE_COLUMNS
    if unauthorized_columns:
        reasons.append("COLUMN_FORBIDDEN")
        evidence.extend(sorted(unauthorized_columns))
        fixes.append("use only allowlisted columns for the referenced table")

    functions = {_function_name(function) for function in statement.find_all(exp.Func)}
    forbidden_functions = sorted(functions & DANGEROUS_FUNCTIONS)
    if forbidden_functions:
        reasons.append("DANGEROUS_FUNCTION")
        evidence.extend(forbidden_functions)
        fixes.append("remove external-I/O, external-database, or delay functions")

    limit = statement.args.get("limit")
    if limit is None:
        reasons.append("LIMIT_REQUIRED")
        evidence.append("missing LIMIT")
        fixes.append(f"add LIMIT no greater than {max_limit} for {environment}")
    elif not isinstance(limit.expression, exp.Literal) or not limit.expression.is_int:
        reasons.append("DYNAMIC_LIMIT")
        evidence.append(limit.sql(dialect="clickhouse"))
        fixes.append("use a positive integer LIMIT literal")
    else:
        limit_value = int(limit.expression.this)
        if limit_value <= 0:
            reasons.append("LIMIT_NON_POSITIVE")
            evidence.append(f"LIMIT {limit_value}")
            fixes.append("use a positive LIMIT")
        elif limit_value > max_limit:
            reasons.append("LIMIT_TOO_LARGE")
            evidence.append(f"LIMIT {limit_value}; {environment}_maximum={max_limit}")
            fixes.append(f"reduce LIMIT to {max_limit} or less")

    offset = statement.args.get("offset")
    if offset is not None:
        if not isinstance(offset.expression, exp.Literal) or not offset.expression.is_int:
            reasons.append("DYNAMIC_OFFSET")
            evidence.append(offset.sql(dialect="clickhouse"))
            fixes.append("use an integer OFFSET literal")
        elif int(offset.expression.this) > MAX_OFFSET:
            reasons.append("OFFSET_TOO_LARGE")
            evidence.append(f"OFFSET {offset.expression.this}")
            fixes.append(f"reduce OFFSET to {MAX_OFFSET} or less; prefer keyset pagination")

    if metric:
        metric_reason = _validate_metric(statement, metric)
        if metric_reason is not None:
            code, metric_evidence, fix = metric_reason
            reasons.append(code)
            evidence.append(metric_evidence)
            fixes.append(fix)

    # 这些形态不一定越权，但会让扫描成本或结果语义发生明显变化，所以单独告警，
    # 交给执行端的超时、扫描量和并发预算做最终约束。
    if statement.find(exp.Final):
        warnings.append("FINAL may trigger expensive merge-time reads")
    join_count = sum(1 for _ in statement.find_all(exp.Join))
    if join_count:
        warnings.append(f"join_count={join_count}; enforce scan and timeout budgets")
    if statement.args.get("distinct"):
        warnings.append("DISTINCT may require high-cardinality aggregation")
    if any(True for _ in statement.find_all(exp.Window)):
        warnings.append("window function detected; bound partition size at execution time")
    dictionary_functions = sorted(functions & DICTIONARY_FUNCTIONS)
    if dictionary_functions:
        # Dictionary lookup 通常不会越权，但可能放大远端/缓存访问成本，必须可观测。
        warnings.append(
            "dictionary access detected: "
            + ", ".join(dictionary_functions)
            + "; enforce lookup and scan budgets"
        )
    if environment == "prod" and not statement.args.get("where"):
        warnings.append("production query has no WHERE filter")

    common = {
        "warnings": _unique(warnings),
        "checked_tables": tables,
        "checked_columns": sorted(columns),
        "effective_max_limit": max_limit,
        "environment": environment,
    }
    if reasons:
        return ReviewResult(
            decision="reject",
            reason_codes=_unique(reasons),
            evidence=_unique(evidence),
            suggested_fix=_unique(fixes),
            **common,
        )
    return ReviewResult(
        decision="pass",
        normalized_sql=statement.sql(dialect="clickhouse"),
        **common,
    )


def _validate_metric(
    statement: exp.Select,
    metric: str,
) -> tuple[str, str, str] | None:
    required = METRIC_REQUIREMENTS.get(metric)
    if required is None:
        return "UNKNOWN_METRIC", metric, "use a registered metric definition"
    projected_columns = {
        column.name.casefold()
        for expression in statement.expressions
        for column in expression.find_all(exp.Column)
    }
    if metric == "success_rate" and any(
        column.name.casefold() == "success_rate"
        for expression in statement.expressions
        for column in expression.find_all(exp.Column)
    ):
        # 已批准的物化指标列可以直接读取；否则必须在 SQL 中显式展示分子和分母。
        return None
    if not required.issubset(projected_columns):
        return (
            "METRIC_MISMATCH",
            f"{metric} requires projected fields {sorted(required)}",
            "align selected fields and expression with the metric reference",
        )
    if metric == "success_rate":
        division = any(_is_approved_success_rate(expression) for expression in statement.expressions)
        if not division:
            return (
                "METRIC_EXPRESSION_MISMATCH",
                "success_rate requires success_count / nullIf(request_count, 0) or approved success_rate",
                "divide success_count by a zero-safe request_count denominator",
            )
    if metric == "active_users":
        has_distinct_count = any(
            isinstance(count.this, exp.Distinct)
            and any(column.name.casefold() == "user_id" for column in count.find_all(exp.Column))
            for expression in statement.expressions
            for count in expression.find_all(exp.Count)
        )
        if not has_distinct_count:
            return (
                "METRIC_EXPRESSION_MISMATCH",
                "active_users requires count(DISTINCT user_id)",
                "use count(DISTINCT user_id) for the approved definition",
            )
    return None


def _is_approved_success_rate(projection: exp.Expression) -> bool:
    for division in projection.find_all(exp.Div):
        numerator_columns = {column.name.casefold() for column in division.this.find_all(exp.Column)}
        denominator_columns = {column.name.casefold() for column in division.expression.find_all(exp.Column)}
        zero_safe = any(True for _ in division.expression.find_all(exp.Nullif))
        if "success_count" in numerator_columns and "request_count" in denominator_columns and zero_safe:
            return True
    return False


def _unauthorized_columns(
    columns: list[exp.Column],
    table_nodes: list[exp.Table],
    tables: list[str],
    *,
    cte_names: set[str],
    projection_aliases: set[str],
) -> set[str]:
    aliases: dict[str, str] = {}
    for table_node in table_nodes:
        qualified = _qualified_table(table_node)
        aliases[table_node.name.casefold()] = qualified
        aliases[table_node.alias_or_name.casefold()] = qualified
        aliases[qualified] = qualified
    allowed_union = set().union(*(TABLE_COLUMNS.get(table, set()) for table in tables))
    unauthorized: set[str] = set()
    for column in columns:
        name = column.name.casefold()
        qualifier = column.table.casefold() if column.table else ""
        if name in projection_aliases:
            continue
        if qualifier in cte_names:
            # CTE 的底层列仍会被遍历检查；这里只允许引用它公开的投影名。
            continue
        table = aliases.get(qualifier) if qualifier else None
        allowed = TABLE_COLUMNS.get(table, set()) if table else allowed_union
        if name not in allowed:
            unauthorized.add(f"{qualifier + '.' if qualifier else ''}{name}")
    return unauthorized


def _reject(code: str, evidence: str, fix: str, environment: str) -> ReviewResult:
    return ReviewResult(
        decision="reject",
        reason_codes=[code],
        evidence=[evidence],
        suggested_fix=[fix],
        environment=environment,
        effective_max_limit=MAX_LIMIT_BY_ENVIRONMENT.get(environment),
    )


def _qualified_table(table: exp.Table) -> str:
    if isinstance(table.this, exp.Func):
        return f"<table-function:{_function_name(table.this)}>"
    return f"{table.db or 'analytics'}.{table.name}".casefold()


def _function_name(function: exp.Func) -> str:
    name = function.sql_name().casefold()
    return str(function.name).casefold() if name == "anonymous" else name


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def main() -> None:
    parser = argparse.ArgumentParser(description="Review ClickHouse SQL without executing it.")
    parser.add_argument("--sql", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--metric")
    parser.add_argument("--environment", default="dev")
    args = parser.parse_args()
    result = validate_sql(args.sql, args.tenant, args.metric, args.environment)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    if result.decision == "reject":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
