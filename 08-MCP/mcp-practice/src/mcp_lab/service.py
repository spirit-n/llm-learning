"""与 MCP SDK 解耦的查询服务：权限、幂等、执行和审计都在这一层。"""

import hashlib
from dataclasses import dataclass

from mcp_lab.domain import FIXTURE_ROWS, SCHEMAS, TENANT_TABLES
from mcp_lab.guard import GuardError, validate_readonly_sql
from mcp_lab.models import ErrorInfo, Principal, QueryResult, TableResult


@dataclass(frozen=True)
class CacheEntry:
    request_fingerprint: str
    result: QueryResult


class QueryService:
    def __init__(self) -> None:
        self.audit_log: list[dict] = []
        self._cache: dict[tuple[str, str, str, str], CacheEntry] = {}

    def clear(self) -> None:
        self.audit_log.clear()
        self._cache.clear()

    def execute(
        self,
        *,
        sql: str,
        principal: Principal,
        request_id: str,
        max_rows: int = 100,
    ) -> QueryResult:
        if "query:execute" not in principal.scopes:
            return self._rejected(request_id, principal, "SCOPE_REQUIRED", "缺少 query:execute 权限")
        if not request_id or len(request_id) > 100:
            return self._rejected(request_id, principal, "REQUEST_ID_INVALID", "request_id 不合法")

        fingerprint = _fingerprint(sql, max_rows)
        # actor + tenant + scopes 都属于授权上下文；不能只按 tenant 重放别人的结果。
        cache_key = (
            principal.actor_id,
            principal.tenant,
            ",".join(sorted(principal.scopes)),
            request_id,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            # 同一个幂等键只能代表同一个操作，否则返回旧结果会造成静默数据错误。
            if cached.request_fingerprint != fingerprint:
                return self._rejected(
                    request_id,
                    principal,
                    "IDEMPOTENCY_CONFLICT",
                    "同一 request_id 不能用于不同查询",
                )
            replay = cached.result.model_copy(update={"cached": True})
            self.audit_log.append(
                {
                    "request_id": request_id,
                    "actor_id": principal.actor_id,
                    "tenant": principal.tenant,
                    "status": "idempotent_replay",
                    "row_count": replay.row_count,
                }
            )
            return replay

        try:
            guarded = validate_readonly_sql(sql, tenant=principal.tenant, max_rows=max_rows)
        except GuardError as exc:
            return self._rejected(request_id, principal, exc.code, exc.message)

        rows = [
            {column: row[column] for column in guarded.projected_columns if column in row}
            for row in FIXTURE_ROWS[: guarded.max_rows]
        ]
        result = QueryResult(
            ok=True,
            normalized_sql=guarded.normalized_sql,
            tables=list(guarded.tables),
            rows=rows,
            row_count=len(rows),
        )
        self._cache[cache_key] = CacheEntry(fingerprint, result)
        self.audit_log.append(
            {
                "request_id": request_id,
                "actor_id": principal.actor_id,
                "tenant": principal.tenant,
                "status": "success",
                "tables": list(guarded.tables),
                "row_count": len(rows),
                "sql_digest": hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12],
            }
        )
        return result

    def _rejected(
        self, request_id: str, principal: Principal, code: str, message: str
    ) -> QueryResult:
        self.audit_log.append(
            {
                "request_id": request_id,
                "actor_id": principal.actor_id,
                "tenant": principal.tenant,
                "status": "rejected",
                "code": code,
            }
        )
        return QueryResult(ok=False, error={"code": code, "message": message})


def _fingerprint(sql: str, max_rows: int) -> str:
    canonical = f"{sql.strip()}\n{max_rows}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SchemaService:
    """即使 Server 已认证，这一层仍独立执行 scope、tenant 与字段投影。"""

    def describe(self, database: str, table: str, principal: Principal) -> TableResult:
        if "schema:read" not in principal.scopes:
            return TableResult(
                ok=False,
                error=ErrorInfo(code="SCOPE_REQUIRED", message="缺少 schema:read 权限"),
            )
        qualified = f"{database}.{table}"
        if qualified not in TENANT_TABLES.get(principal.tenant, set()):
            return TableResult(
                ok=False,
                error=ErrorInfo(code="TABLE_FORBIDDEN", message="表不存在或不可见"),
            )
        schema = SCHEMAS.get((database, table))
        if schema is None:
            return TableResult(
                ok=False,
                error=ErrorInfo(code="TABLE_NOT_FOUND", message="表不存在或不可见"),
            )
        sensitive = set(schema["sensitive_columns"])
        return TableResult(
            ok=True,
            database=database,
            table=table,
            columns=[column for column in schema["columns"] if column not in sensitive],
            redacted_column_count=len(sensitive),
        )
