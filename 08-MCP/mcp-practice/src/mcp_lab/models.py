"""MCP 协议适配层与业务层共享的稳定结构化模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    metric: dict[str, str] | None = None
    error: ErrorInfo | None = None


class TableResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    database: str | None = None
    table: str | None = None
    columns: list[str] = Field(default_factory=list)
    # 对模型只说明有多少列被隐藏，不泄露敏感列名本身。
    redacted_column_count: int = Field(default=0, ge=0)
    error: ErrorInfo | None = None


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    normalized_sql: str | None = None
    tables: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    cached: bool = False
    error: ErrorInfo | None = None


class Principal(BaseModel):
    """由 Host/网关建立的可信身份，不能让模型从工具参数中自行声明。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: str = Field(min_length=1, max_length=100)
    tenant: str = Field(min_length=1, max_length=100)
    scopes: frozenset[str] = Field(default_factory=frozenset)


class ToolCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str | None = None
    input_schema: dict[str, Any]


class CapabilityCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tools: tuple[ToolCapability, ...]
    fingerprint: str


class HostCallResult(BaseModel):
    """把传输异常、协议错误和工具业务错误分开，供上层决定是否重试。"""

    model_config = ConfigDict(extra="forbid")
    ok: bool
    category: Literal["success", "policy_error", "protocol_error", "tool_error"]
    request_id: str
    data: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    retryable: bool = False
