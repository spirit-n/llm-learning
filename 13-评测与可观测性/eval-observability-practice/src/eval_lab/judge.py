from __future__ import annotations

import json
from typing import Any

from .models import JudgeDecision


def parse_judge_decision(value: Any) -> JudgeDecision:
    """把模型 JSON 立即收口到严格契约，禁止下游读取未经验证的 dict。"""
    return JudgeDecision.model_validate(value)


def judge_contract_instruction() -> str:
    """由 Pydantic schema 生成提示，避免手写契约与代码约束逐渐不一致。"""
    schema = json.dumps(JudgeDecision.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    return (
        "只输出一个 JSON 对象，不要 Markdown。JSON 必须严格匹配以下 schema；"
        "不能省略字段，也不能增加字段：" + schema
    )
