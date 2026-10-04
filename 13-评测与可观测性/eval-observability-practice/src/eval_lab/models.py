from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalInput(BaseModel):
    """交给被测系统的公开输入，不包含任何评分 oracle。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    user_input: str = Field(min_length=1)


class ToolExpectation(StrictModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    argument_match: Literal["exact", "contains"] = "exact"


class EvalCase(StrictModel):
    id: str
    input: str
    expected_behavior: Literal["answer", "refuse", "clarify"]
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_tool: str | None = None
    expected_arguments: dict[str, Any] = Field(default_factory=dict)
    argument_match: Literal["exact", "contains"] = "exact"
    expected_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=3, ge=0)
    tags: list[str] = Field(min_length=1)
    weight: float = Field(default=1, gt=0, le=10)
    required_tools: list[ToolExpectation] = Field(default_factory=list)
    required_order: list[tuple[str, str]] = Field(default_factory=list)
    allow_retries: bool = False
    max_retry_attempts: int = Field(default=1, ge=1, le=5)
    retryable_error_codes: tuple[str, ...] = ("transient",)

    @model_validator(mode="after")
    def validate_expectations(self) -> "EvalCase":
        names = [item.name for item in self.required_tools]
        if self.required_tools and self.expected_tool is not None:
            raise ValueError("required_tools 与单工具 expected_tool 不能同时使用")
        if len(names) != len(set(names)) or set(names).intersection(self.forbidden_tools):
            raise ValueError("required_tools 不可重复或包含禁止工具")
        if self.required_tools and self.expected_behavior != "answer":
            raise ValueError("多工具样本必须是 answer 行为")
        if any(a == b or a not in names or b not in names for a, b in self.required_order):
            raise ValueError("required_order 必须引用不同的 required_tools")
        if self.expected_arguments and self.expected_tool is None:
            raise ValueError("expected_arguments 只能和 expected_tool 一起使用")
        if self.expected_tool is None and self.argument_match != "exact":
            raise ValueError("没有 expected_tool 时无需放宽参数匹配策略")
        if self.expected_tool and self.expected_tool in self.forbidden_tools:
            raise ValueError("同一个工具不能既 expected 又 forbidden")
        if self.expected_behavior != "answer" and self.expected_tool is not None:
            raise ValueError("refuse/clarify 样本不应要求调用工具")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags 不能重复")
        return self


class ToolCallRecord(StrictModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["ok", "error"] = "ok"
    duration_ms: float = Field(default=0, ge=0)
    error_code: str | None = None


class Span(StrictModel):
    span_id: str
    parent_id: str | None = None
    name: str
    kind: Literal["model", "retrieval", "tool", "guard", "workflow", "other"] = "other"
    status: Literal["ok", "error"]
    duration_ms: float = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(StrictModel):
    trace_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    status: Literal["ok", "error"]
    behavior: Literal["answer", "refuse", "clarify", "error"]
    output: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    system_version: str = Field(default="unknown", min_length=1)
    prompt_version: str = Field(default="unknown", min_length=1)
    error_code: str | None = None


class Scores(StrictModel):
    behavior: float = Field(ge=0, le=1)
    answer: float = Field(ge=0, le=1)
    tool_selection: float = Field(ge=0, le=1)
    tool_execution: float = Field(ge=0, le=1)
    arguments: float = Field(ge=0, le=1)
    trajectory: float = Field(ge=0, le=1)
    trace_quality: float = Field(ge=0, le=1)
    evidence: float = Field(ge=0, le=1)
    safety: float = Field(ge=0, le=1)
    system_ok: float = Field(ge=0, le=1)
    goal_success: float = Field(ge=0, le=1)


class CaseResult(StrictModel):
    case: EvalCase
    trace: AgentTrace
    scores: Scores
    failure_reasons: list[str] = Field(default_factory=list)


class EvalReport(StrictModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    variant: str
    system_version: str
    dataset_fingerprint: str
    dataset_size: int
    metrics: dict[str, float]
    by_tag: dict[str, dict[str, float]]
    failures: list[str]
    results: list[CaseResult]


class RegressionPolicy(StrictModel):
    min_goal_success: float = Field(default=0.9, ge=0, le=1)
    min_safety: float = Field(default=1.0, ge=0, le=1)
    max_goal_regression: float = Field(default=0, ge=0, le=1)
    max_p95_latency_ratio: float = Field(default=1.25, ge=1)
    protected_tags: tuple[str, ...] = ("safety", "permission", "secret")
    allow_case_regressions: int = Field(default=0, ge=0)


class GateResult(StrictModel):
    passed: bool
    failures: list[str]
    metric_deltas: dict[str, float]
    case_regressions: list[str]
    case_improvements: list[str]


class JudgeDecision(BaseModel):
    """LLM Judge 的严格输出契约；多字段、错类型或漏字段都会拒绝。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    score: float = Field(ge=0, le=1)
    passed: bool
    reasons: list[str] = Field(min_length=1)
    critical_fact_errors: list[str]
