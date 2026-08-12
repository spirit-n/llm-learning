"""Context Builder 的输入、输出和审计模型。

模型里刻意保留来源、时效、预算和裁剪信息。只返回一个拼接后的字符串，
出了错时很难判断到底是“没选中证据”还是“证据被截掉了”。
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


Layer = Literal["system", "task", "domain", "retrieved", "tool", "memory", "runtime", "output"]
SourceKind = Literal[
    "system_policy",
    "runtime_state",
    "authoritative_catalog",
    "tool_result",
    "retrieval",
    "memory",
    "user_content",
    "unknown",
]


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128, pattern=r"^[^\r\n]+$")
    layer: Layer
    source: str = Field(min_length=1, max_length=256, pattern=r"^[^\r\n]+$")
    source_kind: SourceKind = "unknown"
    content: str = Field(min_length=1, max_length=1_000_000)
    tenant: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[^\r\n]+$")
    allowed_roles: set[str] = Field(default_factory=set)
    version: int = 1
    trust: int = Field(default=50, ge=0, le=100)
    priority: int = 50
    relevance: float = Field(default=1.0, ge=0, le=1)
    required: bool = False
    untrusted: bool = False
    sensitive: bool = False
    compressible: bool = False
    conflict_key: str | None = None
    dedupe_key: str | None = None
    updated_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    max_age_seconds: int | None = Field(default=None, ge=1)
    token_override: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_freshness_window(self) -> "ContextItem":
        if self.expires_at is not None and self.updated_at is not None:
            if self.expires_at <= self.updated_at:
                raise ValueError("expires_at 必须晚于 updated_at")
        if self.max_age_seconds is not None and self.updated_at is None:
            raise ValueError("设置 max_age_seconds 时必须同时提供 updated_at")
        return self


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=8_000)
    tenant: str = Field(min_length=1, max_length=128, pattern=r"^[^\r\n]+$")
    roles: set[str]
    token_budget: int = Field(ge=1)
    # reserved_tokens 给模型回答和协议包装留余量，避免输入恰好塞满窗口。
    reserved_tokens: int = Field(default=0, ge=0)
    layer_budgets: dict[Layer, int] = Field(default_factory=dict)
    as_of: AwareDatetime | None = None
    items: list[ContextItem]

    @field_validator("task", "tenant")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        # min_length 只能挡住空字符串；这里再挡住只含空格的任务/租户，避免
        # 生成一个看似存在、实际上无法审计归属或目标的 Context。
        normalized = value.strip()
        if not normalized:
            raise ValueError("task 和 tenant 不能是空白字符串")
        return normalized

    @model_validator(mode="after")
    def validate_budget(self) -> "BuildRequest":
        if self.reserved_tokens >= self.token_budget:
            raise ValueError("reserved_tokens 必须小于 token_budget")
        if any(value < 0 for value in self.layer_budgets.values()):
            raise ValueError("layer_budgets 不能包含负数")
        return self


class IncludedEntry(BaseModel):
    id: str
    layer: Layer
    source: str
    source_kind: SourceKind
    version: int
    tokens: int
    original_tokens: int
    truncated_tokens: int = 0
    transformations: list[str] = Field(default_factory=list)
    required: bool
    priority: int
    position: int


class DroppedEntry(BaseModel):
    id: str
    source: str
    reason: str
    estimated_tokens: int | None = None
    detail: str | None = None


class BudgetReport(BaseModel):
    input_limit: int
    reserved_tokens: int
    available_tokens: int
    used_tokens: int
    structural_tokens: int
    remaining_tokens: int
    used_by_layer: dict[Layer, int]
    layer_limits: dict[Layer, int]


class ContextManifest(BaseModel):
    context_version: Literal["v3"] = "v3"
    tenant: str
    task_source: str
    task_sha256: str
    token_budget: int
    total_tokens: int
    budget: BudgetReport
    included: list[IncludedEntry]
    dropped: list[DroppedEntry]


class BuildResult(BaseModel):
    context: str
    manifest: ContextManifest
