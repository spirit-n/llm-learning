from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import Any, Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], Any]
    required_permission: str | None = None
    cost_units: int = 1
    timeout_seconds: float = 3
    has_side_effect: bool = False
    version: str = "1.0"
    risk_level: Literal["low", "medium", "high"] = "low"
    tenant_argument: str | None = None
    idempotency_field: str | None = None
    max_output_chars: int = 20_000

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("工具 name 不能为空")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("工具 description 不能为空")
        if not isinstance(self.args_model, type) or not issubclass(self.args_model, BaseModel):
            raise ValueError("args_model 必须是 Pydantic BaseModel 子类")
        if not callable(self.handler):
            raise ValueError("handler 必须可调用")
        if isinstance(self.cost_units, bool) or not isinstance(self.cost_units, int) or self.cost_units < 1:
            raise ValueError("cost_units 必须大于 0")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds 必须大于 0")
        if isinstance(self.max_output_chars, bool) or not isinstance(self.max_output_chars, int) or self.max_output_chars < 1:
            raise ValueError("max_output_chars 必须大于 0")
        if self.risk_level not in {"low", "medium", "high"}:
            raise ValueError("risk_level 必须是 low/medium/high")
        model_fields = self.args_model.model_fields
        if self.tenant_argument and self.tenant_argument not in model_fields:
            raise ValueError(f"tenant_argument 不存在于参数模型：{self.tenant_argument}")
        if self.idempotency_field and self.idempotency_field not in model_fields:
            raise ValueError(f"idempotency_field 不存在于参数模型：{self.idempotency_field}")
        if self.idempotency_field and not self.has_side_effect:
            raise ValueError("只有副作用工具才需要幂等字段")

    def model_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def audit_metadata(self) -> dict[str, Any]:
        """返回给 Harness/审计系统使用的元数据，不混入模型工具 schema。"""
        return {
            "name": self.name,
            "version": self.version,
            "risk_level": self.risk_level,
            "required_permission": self.required_permission,
            "has_side_effect": self.has_side_effect,
            "timeout_seconds": self.timeout_seconds,
            "cost_units": self.cost_units,
        }


class ToolRegistry:
    def __init__(self, tools: list[ToolSpec] | None = None):
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def schemas(self, allowed_tools: frozenset[str]) -> list[dict]:
        return [self._tools[name].model_schema() for name in sorted(allowed_tools) if name in self._tools]
