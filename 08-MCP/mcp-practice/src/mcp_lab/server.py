"""FastMCP Server：同一能力可通过 stdio 或 Streamable HTTP 暴露。"""

import argparse
import json
import os
import secrets

from mcp.server.fastmcp import FastMCP

from mcp_lab.auth import AuthenticationError, SignedRequestContext
from mcp_lab.domain import METRICS, SCHEMAS, metric_definition
from mcp_lab.models import MetricResult, Principal, QueryResult, TableResult
from mcp_lab.service import QueryService, SchemaService


mcp = FastMCP(
    "secure-metric-server",
    instructions="只提供指标定义、只读 schema 和受控查询。",
    json_response=True,
)

QUERY_SERVICE = QueryService()
SCHEMA_SERVICE = SchemaService()
# 未配置时每个 Server 进程使用随机密钥；跨进程部署必须由认证网关配置同一密钥。
AUTH_GATEWAY = SignedRequestContext(
    os.environ.get("MCP_AUTH_SECRET", "").encode("utf-8") or secrets.token_bytes(32)
)
# 保留两个只读教学入口，方便 demo/测试观察；生产环境应写入外部审计与幂等存储。
AUDIT_LOG = QUERY_SERVICE.audit_log
REQUEST_CACHE = QUERY_SERVICE._cache


@mcp.tool(structured_output=True)
def get_metric_definition(metric_name: str) -> MetricResult:
    """查询指标正式定义；未知指标返回稳定错误码。"""
    return MetricResult.model_validate(metric_definition(metric_name))


@mcp.tool(structured_output=True)
def describe_table(database: str, table: str, auth_context: str) -> TableResult:
    """读取授权 schema；Server 校验网关签名，不相信客户端自报 tenant。"""
    principal = _authenticate(auth_context, "schema:read")
    if principal is None:
        return TableResult(
            ok=False,
            error={"code": "AUTHENTICATION_FAILED", "message": "请求上下文认证失败"},
        )
    return SCHEMA_SERVICE.describe(database, table, principal)


@mcp.tool(structured_output=True)
def run_readonly_sql(
    sql: str, auth_context: str, request_id: str, max_rows: int = 100
) -> QueryResult:
    """模拟只读查询；认证上下文/request_id 由 Host 注入，模型看不到这些字段。"""
    principal = _authenticate(auth_context, "query:execute")
    if principal is None:
        return QueryResult(
            ok=False,
            error={"code": "AUTHENTICATION_FAILED", "message": "请求上下文认证失败"},
        )
    return QUERY_SERVICE.execute(
        sql=sql,
        principal=principal,
        request_id=request_id,
        max_rows=max_rows,
    )


@mcp.resource("metric://definitions")
def metric_resource() -> str:
    """返回全部教学指标定义。"""
    return json.dumps(METRICS, ensure_ascii=False)


@mcp.resource("schema://{database}/{table}")
def schema_resource(database: str, table: str) -> str:
    """无认证 Resource 只返回公开投影，敏感表/敏感列绝不从这里暴露。"""
    schema = SCHEMAS.get((database, table))
    if schema is None or schema["sensitive_columns"]:
        result = {"ok": False, "error": {"code": "TABLE_NOT_PUBLIC", "message": "无公开 schema"}}
    else:
        result = {
            "ok": True,
            "database": database,
            "table": table,
            "columns": list(schema["columns"]),
        }
    return json.dumps(result, ensure_ascii=False)


def _authenticate(auth_context: str, required_scope: str) -> Principal | None:
    try:
        principal = AUTH_GATEWAY.verify(auth_context)
    except AuthenticationError:
        return None
    # Server 先做一次 coarse-grained 授权；Service 还会独立复核。
    return principal if required_scope in principal.scopes else None


@mcp.prompt()
def review_query(sql: str) -> str:
    """生成查询评审提示；安全仍由代码 Guard 执行。"""
    return f"解释下面 SQL 的用途和风险，但不要执行：\n{sql}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
