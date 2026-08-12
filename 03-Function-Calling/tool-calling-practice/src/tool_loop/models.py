from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCall(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]


class ModelResponse(StrictModel):
    final_answer: str | None = Field(default=None, min_length=1, max_length=10_000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def exactly_one_response_kind(self) -> "ModelResponse":
        has_final = self.final_answer is not None
        has_calls = bool(self.tool_calls)
        if has_final == has_calls:
            raise ValueError("模型响应必须且只能包含 final_answer 或 tool_calls")
        return self


class Message(StrictModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ToolResult(StrictModel):
    status: Literal["ok", "error", "denied"]
    data: Any | None = None
    error_code: str | None = None
    message: str | None = None
    truncated: bool = False
    original_bytes: int | None = None


class UserContext(StrictModel):
    user_id: str = Field(min_length=1, max_length=100)
    permissions: frozenset[str] = Field(default_factory=frozenset)


class AuditEvent(StrictModel):
    step: int = Field(ge=1)
    call_id: str
    tool_name: str
    arguments_digest: str
    outcome: Literal["ok", "error", "denied"]
    error_code: str | None = None
    duration_ms: float = Field(ge=0)
    truncated: bool = False


class RunResult(StrictModel):
    status: Literal["completed", "stopped", "max_steps"]
    final_answer: str | None = None
    error_code: str | None = None
    steps: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    invalid_call_count: int = Field(ge=0)
    messages: list[Message]
    audit_log: list[AuditEvent]

