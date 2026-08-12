"""确定性的 SQL 策略检查；不能让生成 SQL 的同一个模型负责最终放行。"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SQLPolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    reason: str
    tables: list[str] = Field(default_factory=list)
    limit: int | None = None
    fingerprint: str = ""
    risk_level: str = "high"


def inspect_sql(
    sql: str,
    *,
    allowed_tables: set[str],
    max_limit: int = 100,
) -> SQLPolicyResult:
    normalized = sql.strip()
    fingerprint = hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()[:16]
    if not normalized:
        return SQLPolicyResult(allowed=False, reason="SQL 为空", fingerprint=fingerprint)
    if len(normalized) > 2_000:
        return SQLPolicyResult(allowed=False, reason="SQL 过长", fingerprint=fingerprint)
    try:
        statements = parse(normalized, read="sqlite")
    except ParseError:
        return SQLPolicyResult(allowed=False, reason="SQL 语法无法解析", fingerprint=fingerprint)
    if len(statements) != 1:
        return SQLPolicyResult(allowed=False, reason="只允许单条语句", fingerprint=fingerprint)
    statement = statements[0]
    if not isinstance(statement, exp.Select):
        return SQLPolicyResult(allowed=False, reason="只允许 SELECT", fingerprint=fingerprint)

    # AST 能同时识别 SELECT *、alias.*、COUNT(*)，不会被换行/注释/大小写绕过。
    if any(True for _ in statement.find_all(exp.Star)):
        return SQLPolicyResult(
            allowed=False,
            reason="禁止 SELECT * 等通配符投影（包括 alias.* / COUNT(*)）",
            fingerprint=fingerprint,
        )

    tables = sorted(
        {
            f"{table.db}.{table.name}" if table.db else table.name
            for table in statement.find_all(exp.Table)
        }
    )
    unknown = sorted(set(tables) - allowed_tables)
    if not tables or unknown:
        reason = "未识别数据表" if not tables else f"表不在 allowlist: {', '.join(unknown)}"
        return SQLPolicyResult(
            allowed=False, reason=reason, tables=tables, fingerprint=fingerprint
        )

    limit_node = statement.args.get("limit")
    limit_expression = limit_node.expression if limit_node is not None else None
    if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
        return SQLPolicyResult(
            allowed=False, reason="必须显式设置 LIMIT", tables=tables, fingerprint=fingerprint
        )
    limit = int(limit_expression.this)
    if limit < 1 or limit > max_limit:
        return SQLPolicyResult(
            allowed=False,
            reason=f"LIMIT 必须在 1..{max_limit}",
            tables=tables,
            limit=limit,
            fingerprint=fingerprint,
        )
    risk = (
        "medium"
        if any(True for _ in statement.find_all(exp.AggFunc))
        else "low"
    )
    return SQLPolicyResult(
        allowed=True,
        reason="通过",
        tables=tables,
        limit=limit,
        fingerprint=fingerprint,
        risk_level=risk,
    )
