from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


ToolHandler = Callable[[BaseModel], Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    required_permission: str | None = None
    has_side_effect: bool = False
    timeout_seconds: float = 2.0
    output_limit_bytes: int = 8_000
    version: str = "1.0"

    def as_model_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
            "metadata": {
                "version": self.version,
                "has_side_effect": self.has_side_effect,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def model_schemas(self) -> list[dict[str, Any]]:
        return [tool.as_model_schema() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

