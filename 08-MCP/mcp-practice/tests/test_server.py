import json
import os
import socket
import subprocess
import sys
import asyncio

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from mcp_lab.auth import SignedRequestContext
from mcp_lab.models import Principal
from mcp_lab.server import (
    AUDIT_LOG,
    AUTH_GATEWAY,
    REQUEST_CACHE,
    describe_table,
    mcp,
    run_readonly_sql,
    schema_resource,
)


def actor(tenant: str = "tenant-a") -> Principal:
    return Principal(
        actor_id="server-test",
        tenant=tenant,
        scopes=frozenset({"schema:read", "query:execute"}),
    )


@pytest.mark.asyncio
async def test_server_exposes_tools_resources_templates_and_prompt():
    assert {tool.name for tool in await mcp.list_tools()} == {
        "get_metric_definition", "describe_table", "run_readonly_sql"
    }
    assert len(await mcp.list_resources()) == 1
    assert len(await mcp.list_resource_templates()) == 1
    assert {prompt.name for prompt in await mcp.list_prompts()} == {"review_query"}


@pytest.mark.asyncio
async def test_unknown_metric_returns_structured_error():
    result = await mcp.call_tool("get_metric_definition", {"metric_name": "missing"})
    assert result[1]["error"]["code"] == "METRIC_NOT_FOUND"


def test_duplicate_request_is_idempotent():
    REQUEST_CACHE.clear()
    AUDIT_LOG.clear()
    args = {
        "sql": "SELECT day, revenue FROM analytics.daily_metrics",
        "auth_context": AUTH_GATEWAY.issue(actor()),
        "request_id": "same-id",
        "max_rows": 10,
    }
    first = run_readonly_sql(**args)
    second = run_readonly_sql(**args)
    assert first.cached is False
    assert second.cached is True
    assert [event["status"] for event in AUDIT_LOG] == ["success", "idempotent_replay"]


def test_server_rejects_client_claim_without_valid_gateway_signature():
    forged = run_readonly_sql(
        sql="SELECT day FROM analytics.public_metrics",
        auth_context="tenant-a.query:execute.forged",
        request_id="forged-id",
    )
    assert forged.ok is False
    assert forged.error.code == "AUTHENTICATION_FAILED"


def test_signed_tenant_b_context_cannot_access_tenant_a_table():
    result = run_readonly_sql(
        sql="SELECT day FROM analytics.daily_metrics",
        auth_context=AUTH_GATEWAY.issue(actor("tenant-b")),
        request_id="cross-tenant",
    )
    assert result.error.code == "TABLE_FORBIDDEN"


def test_schema_tool_projects_sensitive_columns_and_public_resource_hides_table():
    result = describe_table(
        "analytics", "daily_metrics", AUTH_GATEWAY.issue(actor())
    )
    assert result.ok is True
    assert "customer_email" not in result.columns
    assert result.redacted_column_count == 1
    public = json.loads(schema_resource("analytics", "daily_metrics"))
    assert public["error"]["code"] == "TABLE_NOT_PUBLIC"
    assert "customer_email" not in json.dumps(public)


@pytest.mark.asyncio
async def test_real_stdio_client_can_initialize_discover_and_call():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_lab.server", "--transport", "stdio"],
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("get_metric_definition", {"metric_name": "success_rate"})
    assert initialized.serverInfo.name == "secure-metric-server"
    assert "get_metric_definition" in {tool.name for tool in tools.tools}
    assert result.structuredContent["ok"] is True


@pytest.mark.asyncio
async def test_real_stdio_transport_verifies_signed_context_for_protected_tool():
    secret = "stdio-integration-secret-at-least-32-bytes"
    gateway = SignedRequestContext(secret)
    token = gateway.issue(actor())
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_lab.server", "--transport", "stdio"],
        env={**os.environ, "MCP_AUTH_SECRET": secret},
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "run_readonly_sql",
                {
                    "sql": "SELECT day FROM analytics.public_metrics",
                    "auth_context": token,
                    "request_id": "stdio-protected",
                },
            )
    assert result.structuredContent["ok"] is True


@pytest.mark.asyncio
async def test_real_streamable_http_transport_uses_same_authenticated_boundary():
    """不是进程内 mock：启动真实 FastMCP HTTP 子进程并走 ClientSession。"""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    secret = "http-integration-secret-at-least-32-bytes"
    token = SignedRequestContext(secret).issue(actor())
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mcp_lab.server",
            "--transport",
            "streamable-http",
            "--port",
            str(port),
        ],
        env={**os.environ, "MCP_AUTH_SECRET": secret},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        for _ in range(60):
            if process.poll() is not None:
                pytest.fail(f"HTTP Server 提前退出: {process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            pytest.fail("HTTP Server 未在时限内启动")

        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "describe_table",
                    {
                        "database": "analytics",
                        "table": "daily_metrics",
                        "auth_context": token,
                    },
                )
        assert result.structuredContent["ok"] is True
        assert "customer_email" not in result.structuredContent["columns"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
