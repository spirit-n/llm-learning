from __future__ import annotations

from copy import deepcopy

from .models import Message, ModelResponse


class ScriptedFakeModel:
    """按预设顺序返回响应，让运行时测试不受模型随机性影响。"""

    def __init__(self, responses: list[ModelResponse]) -> None:
        if not responses:
            raise ValueError("至少需要一个 fake model 响应")
        self._responses = list(responses)
        self.calls = 0
        self.seen_messages: list[list[Message]] = []
        self.seen_tool_schemas: list[list[dict]] = []

    def complete(
        self,
        messages: list[Message],
        tool_schemas: list[dict],
    ) -> ModelResponse:
        self.seen_messages.append(deepcopy(messages))
        self.seen_tool_schemas.append(deepcopy(tool_schemas))
        if self.calls >= len(self._responses):
            raise RuntimeError("fake model 响应已耗尽")
        response = self._responses[self.calls]
        self.calls += 1
        return response

