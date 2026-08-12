"""MCP Host 侧的能力发现、参数边界、授权与错误归一化。"""

import asyncio
import hashlib
import json
import math
from typing import Any, Protocol
from uuid import uuid4

from mcp_lab.models import (
    CapabilityCatalog,
    HostCallResult,
    Principal,
    ToolCapability,
)


class MCPTransport(Protocol):
    async def list_tools(self) -> list[ToolCapability]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class CapabilityDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class LocalFastMCPTransport:
    """进程内教学适配器；网络/stdio ClientSession 可实现同一个接口。"""

    def __init__(self, server: Any) -> None:
        self._server = server

    async def list_tools(self) -> list[ToolCapability]:
        return [
            ToolCapability(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
            )
            for tool in await self._server.list_tools()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._server.call_tool(name, arguments)
        structured = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else None
        if not isinstance(structured, dict):
            raise ValueError("MCP Tool 没有返回 structured content")
        return structured


DEFAULT_SCOPES = {
    "get_metric_definition": "metrics:read",
    "describe_table": "schema:read",
    "run_readonly_sql": "query:execute",
}


class SafeMCPHost:
    """模型只能提出业务参数，身份、租户和 request_id 由 Host 注入。"""

    def __init__(
        self,
        transport: MCPTransport,
        principal: Principal,
        *,
        auth_context: str | None = None,
        allowed_tools: set[str] | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须是大于 0 的有限数")
        self._transport = transport
        self._principal = principal
        self._auth_context = auth_context
        self._allowed_tools = set(DEFAULT_SCOPES) if allowed_tools is None else set(allowed_tools)
        self._timeout_seconds = timeout_seconds
        self._catalog: CapabilityCatalog | None = None
        self._server_capabilities: dict[str, ToolCapability] = {}

    async def discover(self, *, refresh: bool = False) -> CapabilityCatalog:
        if self._catalog is not None and not refresh:
            return self._catalog
        try:
            discovered = await asyncio.wait_for(
                self._transport.list_tools(), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            raise CapabilityDiscoveryError(
                "DISCOVERY_TIMEOUT", "MCP 能力发现超时", retryable=True
            ) from exc
        except Exception as exc:
            raise CapabilityDiscoveryError(
                "DISCOVERY_FAILED",
                f"MCP 能力发现失败：{type(exc).__name__}",
                retryable=True,
            ) from exc
        server_tools = tuple(
            sorted(
                (tool for tool in discovered if tool.name in self._allowed_tools),
                key=lambda item: item.name,
            )
        )
        if len({tool.name for tool in server_tools}) != len(server_tools):
            raise CapabilityDiscoveryError(
                "DUPLICATE_CAPABILITY", "Server 返回了重名工具", retryable=False
            )
        self._server_capabilities = {tool.name: tool for tool in server_tools}
        # 给模型看的 schema 不暴露身份字段；调用前仍使用 Server 原始 schema 做完整校验。
        tools = tuple(_model_safe_capability(tool) for tool in server_tools)
        canonical = json.dumps(
            [tool.model_dump(mode="json") for tool in server_tools],
            sort_keys=True,
            ensure_ascii=False,
        )
        self._catalog = CapabilityCatalog(
            tools=tools,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        )
        return self._catalog

    async def call_tool(
        self,
        name: str,
        model_arguments: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> HostCallResult:
        call_id = request_id or uuid4().hex
        try:
            catalog = await self.discover()
        except CapabilityDiscoveryError as exc:
            return _error(
                "protocol_error",
                call_id,
                exc.code,
                exc.message,
                retryable=exc.retryable,
            )
        if name not in {tool.name for tool in catalog.tools}:
            return _error("policy_error", call_id, "TOOL_NOT_ALLOWED", "工具未发现或不在 allowlist")
        capability = self._server_capabilities[name]

        required_scope = DEFAULT_SCOPES.get(name)
        if required_scope and required_scope not in self._principal.scopes:
            return _error("policy_error", call_id, "SCOPE_REQUIRED", f"缺少 {required_scope} 权限")

        if not isinstance(model_arguments, dict):
            return _error(
                "protocol_error", call_id, "INVALID_ARGUMENTS", "工具参数必须是 JSON object"
            )
        trusted_fields = {
            key
            for key in ("auth_context", "request_id")
            if key in capability.input_schema.get("properties", {})
        }
        if trusted_fields & model_arguments.keys():
            return _error(
                "policy_error",
                call_id,
                "TRUSTED_ARGUMENT_FORBIDDEN",
                "模型不能设置 auth_context 或 request_id",
            )

        arguments = dict(model_arguments)
        if "auth_context" in trusted_fields:
            if not self._auth_context:
                return _error(
                    "policy_error",
                    call_id,
                    "AUTH_CONTEXT_REQUIRED",
                    "缺少认证网关签发的请求上下文",
                )
            arguments["auth_context"] = self._auth_context
        if "request_id" in trusted_fields:
            arguments["request_id"] = call_id
        validation_error = _validate_arguments(capability.input_schema, arguments)
        if validation_error:
            return _error("protocol_error", call_id, "INVALID_ARGUMENTS", validation_error)

        try:
            data = await asyncio.wait_for(
                self._transport.call_tool(name, arguments), timeout=self._timeout_seconds
            )
        except TimeoutError:
            return _error(
                "protocol_error", call_id, "TOOL_TIMEOUT", "工具调用超时", retryable=True
            )
        except Exception as exc:
            # 不把 SDK、网络或 Server 的内部异常正文直接暴露给模型。
            return _error(
                "protocol_error",
                call_id,
                "TRANSPORT_ERROR",
                f"MCP 调用失败：{type(exc).__name__}",
                retryable=True,
            )

        if not isinstance(data.get("ok"), bool):
            return _error(
                "protocol_error",
                call_id,
                "INVALID_TOOL_RESULT",
                "工具 structured content 缺少布尔字段 ok",
            )
        if data["ok"] is False:
            error = data.get("error") or {}
            return _error(
                "tool_error",
                call_id,
                str(error.get("code", "TOOL_FAILED")),
                str(error.get("message", "工具执行失败")),
            )
        return HostCallResult(
            ok=True,
            category="success",
            request_id=call_id,
            data=data,
        )


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    properties = schema.get("properties", {})
    missing = [name for name in schema.get("required", []) if name not in arguments]
    if missing:
        return f"缺少必填参数：{', '.join(sorted(missing))}"
    unknown = set(arguments) - set(properties)
    if unknown:
        return f"包含未知参数：{', '.join(sorted(unknown))}"
    python_types = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
    for name, value in arguments.items():
        constraints = properties.get(name, {})
        expected = python_types.get(constraints.get("type"))
        if expected and (not isinstance(value, expected) or isinstance(value, bool) and expected != bool):
            return f"参数 {name} 类型不正确"
        if "enum" in constraints and value not in constraints["enum"]:
            return f"参数 {name} 不在允许枚举中"
        if isinstance(value, str):
            if "minLength" in constraints and len(value) < constraints["minLength"]:
                return f"参数 {name} 长度小于下限"
            if "maxLength" in constraints and len(value) > constraints["maxLength"]:
                return f"参数 {name} 长度超过上限"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in constraints and value < constraints["minimum"]:
                return f"参数 {name} 小于下限"
            if "maximum" in constraints and value > constraints["maximum"]:
                return f"参数 {name} 超过上限"
    return None


def _model_safe_capability(capability: ToolCapability) -> ToolCapability:
    schema = json.loads(json.dumps(capability.input_schema))
    properties = schema.get("properties", {})
    trusted_fields = {"auth_context", "request_id"} & set(properties)
    for field in trusted_fields:
        properties.pop(field, None)
    schema["required"] = [
        field for field in schema.get("required", []) if field not in trusted_fields
    ]
    return capability.model_copy(update={"input_schema": schema})


def _error(
    category: str,
    request_id: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> HostCallResult:
    return HostCallResult(
        ok=False,
        category=category,  # type: ignore[arg-type]
        request_id=request_id,
        error={"code": code, "message": message},
        retryable=retryable,
    )
