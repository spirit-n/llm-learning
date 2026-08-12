from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from .models import Observation, PlanDecision, TaskSpec


class Planner(Protocol):
    def decide(
        self,
        task: TaskSpec,
        observations: list[Observation],
        tool_schemas: list[dict],
    ) -> PlanDecision: ...


class ScriptedPlanner:
    """按顺序返回决策或抛出异常，便于稳定注入故障。"""

    def __init__(self, script: list[PlanDecision | Exception]):
        if not script:
            raise ValueError("script 不能为空")
        self.script = list(script)
        self.calls = 0
        self.seen_observations: list[list[Observation]] = []

    def decide(self, task: TaskSpec, observations: list[Observation], tool_schemas: list[dict]) -> PlanDecision:
        del task, tool_schemas
        self.seen_observations.append(deepcopy(observations))
        if self.calls >= len(self.script):
            raise RuntimeError("planner 脚本已耗尽")
        item = self.script[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item

