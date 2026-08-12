import asyncio
from typing import Any

import pytest

from mcp_lab.host import LocalFastMCPTransport, SafeMCPHost
from mcp_lab.models import Principal, ToolCapability
from mcp_lab.server import mcp
from mcp_lab.server import AUTH_GATEWAY


ALL_SCOPES = frozenset({"metrics:read", "schema:read", "query:execute"})
AUTH_TOKEN = "gateway-issued-context-for-fake-transport"


class FakeTransport:
    def __init__(
        self,
        tools: list[ToolCapability],
        *,
        result: dict[str, Any] | None = None,
        delay: float = 0,
        error: Exception | None = None,
        discovery_delay: float = 0,
        discovery_error: Exception | None = None,
    ) -> None:
        self.tools = tools
        self.result = result if result is not None else {"ok": True}
        self.delay = delay
        self.error = error
        self.discovery_delay = discovery_delay
        self.discovery_error = discovery_error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[ToolCapability]:
        if self.discovery_delay:
            await asyncio.sleep(self.discovery_delay)
        if self.discovery_error:
            raise self.discovery_error
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def principal(scopes: frozenset[str] = ALL_SCOPES) -> Principal:
    return Principal(actor_id="user-1", tenant="tenant-a", scopes=scopes)


def query_capability() -> ToolCapability:
    return ToolCapability(
        name="run_readonly_sql",
        input_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "minLength": 1, "maxLength": 200},
                "auth_context": {"type": "string"},
                "request_id": {"type": "string"},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["sql", "auth_context", "request_id"],
        },
    )


@pytest.mark.asyncio
async def test_capability_discovery_is_allowlisted_and_fingerprinted():
    transport = FakeTransport(
        [
            query_capability(),
            ToolCapability(name="dangerous_admin", input_schema={"type": "object"}),
        ]
    )
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    catalog = await host.discover()

    assert [tool.name for tool in catalog.tools] == ["run_readonly_sql"]
    assert len(catalog.fingerprint) == 16
    model_schema = catalog.tools[0].input_schema
    assert "auth_context" not in model_schema["properties"]
    assert "request_id" not in model_schema["properties"]
    assert model_schema["required"] == ["sql"]


@pytest.mark.asyncio
async def test_explicit_empty_allowlist_exposes_no_tools():
    host = SafeMCPHost(
        FakeTransport([query_capability()]),
        principal(),
        auth_context=AUTH_TOKEN,
        allowed_tools=set(),
    )

    catalog = await host.discover()
    result = await host.call_tool("run_readonly_sql", {"sql": "SELECT 1"})

    assert catalog.tools == ()
    assert result.error.code == "TOOL_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_host_injects_trusted_tenant_and_request_id():
    transport = FakeTransport([query_capability()], result={"ok": True, "rows": []})
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    result = await host.call_tool(
        "run_readonly_sql",
        {"sql": "SELECT day FROM analytics.daily_metrics", "max_rows": 5},
        request_id="req-123",
    )

    assert result.ok is True
    assert transport.calls[0][1]["auth_context"] == AUTH_TOKEN
    assert transport.calls[0][1]["request_id"] == "req-123"


@pytest.mark.asyncio
async def test_protected_tool_fails_before_transport_without_gateway_context():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(transport, principal())
    result = await host.call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )
    assert result.category == "policy_error"
    assert result.error.code == "AUTH_CONTEXT_REQUIRED"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_model_cannot_override_trusted_identity_fields():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    result = await host.call_tool(
        "run_readonly_sql",
        {"sql": "SELECT day FROM analytics.public_metrics", "auth_context": "forged"},
    )

    assert result.category == "policy_error"
    assert result.error.code == "TRUSTED_ARGUMENT_FORBIDDEN"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_scope_is_checked_before_transport_call():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(
        transport,
        principal(frozenset({"metrics:read"})),
        auth_context=AUTH_TOKEN,
    )

    result = await host.call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )

    assert result.error.code == "SCOPE_REQUIRED"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_missing_and_unknown_arguments_are_protocol_errors():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    missing = await host.call_tool("run_readonly_sql", {})
    unknown = await host.call_tool(
        "run_readonly_sql",
        {"sql": "SELECT day FROM analytics.public_metrics", "surprise": True},
    )

    assert missing.error.code == unknown.error.code == "INVALID_ARGUMENTS"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_arguments_must_be_a_json_object():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    result = await host.call_tool("run_readonly_sql", ["not", "an", "object"])  # type: ignore[arg-type]

    assert result.error.code == "INVALID_ARGUMENTS"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_json_schema_bounds_are_checked_before_transport():
    transport = FakeTransport([query_capability()])
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    empty_sql = await host.call_tool("run_readonly_sql", {"sql": ""})
    too_many_rows = await host.call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics", "max_rows": 101}
    )

    assert empty_sql.error.code == too_many_rows.error.code == "INVALID_ARGUMENTS"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_json_schema_enum_is_checked_before_transport():
    capability = ToolCapability(
        name="get_metric_definition",
        input_schema={
            "type": "object",
            "properties": {"metric_name": {"type": "string", "enum": ["success_rate"]}},
            "required": ["metric_name"],
        },
    )
    transport = FakeTransport([capability])
    host = SafeMCPHost(transport, principal(), auth_context=AUTH_TOKEN)

    result = await host.call_tool("get_metric_definition", {"metric_name": "admin_secret"})

    assert result.error.code == "INVALID_ARGUMENTS"
    assert transport.calls == []


@pytest.mark.asyncio
async def test_tool_business_error_is_distinct_from_transport_error():
    tool_error_transport = FakeTransport(
        [query_capability()],
        result={"ok": False, "error": {"code": "TABLE_FORBIDDEN", "message": "不可见"}},
    )
    tool_result = await SafeMCPHost(
        tool_error_transport, principal(), auth_context=AUTH_TOKEN
    ).call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )

    broken_transport = FakeTransport([query_capability()], error=ConnectionError("secret endpoint"))
    protocol_result = await SafeMCPHost(
        broken_transport, principal(), auth_context=AUTH_TOKEN
    ).call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )

    assert tool_result.category == "tool_error"
    assert tool_result.retryable is False
    assert protocol_result.category == "protocol_error"
    assert protocol_result.retryable is True
    assert "secret endpoint" not in protocol_result.error.message


@pytest.mark.asyncio
async def test_timeout_is_retryable_but_bounded():
    transport = FakeTransport([query_capability()], delay=0.05)
    host = SafeMCPHost(
        transport, principal(), auth_context=AUTH_TOKEN, timeout_seconds=0.01
    )

    result = await host.call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )

    assert result.error.code == "TOOL_TIMEOUT"
    assert result.retryable is True


@pytest.mark.asyncio
async def test_discovery_timeout_and_exception_are_sanitized_protocol_errors():
    timeout_host = SafeMCPHost(
        FakeTransport([query_capability()], discovery_delay=0.05),
        principal(),
        auth_context=AUTH_TOKEN,
        timeout_seconds=0.01,
    )
    broken_host = SafeMCPHost(
        FakeTransport(
            [query_capability()], discovery_error=ConnectionError("private discovery url")
        ),
        principal(),
        auth_context=AUTH_TOKEN,
    )

    timeout = await timeout_host.call_tool("run_readonly_sql", {"sql": "SELECT 1"})
    broken = await broken_host.call_tool("run_readonly_sql", {"sql": "SELECT 1"})

    assert timeout.error.code == "DISCOVERY_TIMEOUT"
    assert broken.error.code == "DISCOVERY_FAILED"
    assert timeout.retryable and broken.retryable
    assert "private discovery url" not in broken.error.message


@pytest.mark.asyncio
async def test_structured_result_without_boolean_ok_is_protocol_error():
    host = SafeMCPHost(
        FakeTransport([query_capability()], result={"rows": []}),
        principal(),
        auth_context=AUTH_TOKEN,
    )

    result = await host.call_tool(
        "run_readonly_sql", {"sql": "SELECT day FROM analytics.public_metrics"}
    )

    assert result.category == "protocol_error"
    assert result.error.code == "INVALID_TOOL_RESULT"


@pytest.mark.parametrize("timeout", [0, -1, float("inf")])
def test_invalid_host_timeout_fails_fast(timeout):
    with pytest.raises(ValueError):
        SafeMCPHost(
            FakeTransport([]), principal(), auth_context=AUTH_TOKEN, timeout_seconds=timeout
        )


@pytest.mark.asyncio
async def test_real_fastmcp_adapter_discovers_and_calls_structured_tool():
    actor = principal()
    host = SafeMCPHost(
        LocalFastMCPTransport(mcp),
        actor,
        auth_context=AUTH_GATEWAY.issue(actor),
    )

    result = await host.call_tool(
        "get_metric_definition", {"metric_name": "success_rate"}, request_id="metric-1"
    )

    assert result.ok is True
    assert result.data["metric"]["version"] == "v2"
