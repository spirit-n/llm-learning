from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskSpec(StrictModel):
    task_id: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=10_000)
    context: str = ""
    # 领域 Verifier 使用显式验收目标，不从自然语言 objective 猜指标。
    expected_metric: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_tools: frozenset[str] = Field(default_factory=frozenset)
    max_steps: int = Field(default=6, ge=1, le=50)
    max_cost_units: int = Field(default=20, ge=1)
    max_context_chars: int = Field(default=8_000, ge=1)
    deadline_seconds: float = Field(default=30, gt=0, le=3_600)
    planner_timeout_seconds: float = Field(default=10, gt=0)
    cancel_check_timeout_seconds: float = Field(default=1, gt=0)
    approval_timeout_seconds: float = Field(default=30, gt=0)
    verifier_timeout_seconds: float = Field(default=10, gt=0)
    max_transient_retries: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0, ge=0, le=10)


class UserContext(StrictModel):
    user_id: str = Field(min_length=1, max_length=100)
    tenant: str = Field(min_length=1, max_length=100)
    permissions: frozenset[str] = Field(default_factory=frozenset)


class PlanDecision(StrictModel):
    kind: Literal["tool", "final"]
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PlanDecision":
        if self.kind == "tool" and (not self.tool_name or self.answer is not None):
            raise ValueError("tool 决策必须有 tool_name 且不能包含 answer")
        if self.kind == "final" and (not self.answer or self.tool_name is not None or self.arguments):
            raise ValueError("final 决策必须只有非空 answer")
        return self


class Observation(StrictModel):
    tool_name: str
    status: Literal["ok", "error"]
    data: Any | None = None
    error_code: str | None = None


class TraceEvent(StrictModel):
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: str
    status: Literal["ok", "error", "pending"]
    details: dict[str, Any] = Field(default_factory=dict)


class Verification(StrictModel):
    passed: bool
    code: str
    message: str


class RunResult(StrictModel):
    run_id: str
    task_id: str
    status: Literal["succeeded", "failed", "cancelled", "waiting_approval"]
    answer: str | None = None
    error_code: str | None = None
    steps: int = Field(ge=0)
    cost_units: int = Field(ge=0)
    observations: list[Observation] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
