from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from .models import EvalCase


def load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(EvalCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            # 标出具体行号，数据集维护者才能快速定位坏样本，而不是得到一个笼统解析失败。
            raise ValueError(f"数据集第 {line_number} 行无效：{exc}") from exc
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("数据集 case id 重复")
    if not cases:
        raise ValueError("数据集不能为空")
    return cases


def dataset_fingerprint(cases: list[EvalCase]) -> str:
    """对规范化后的样本求指纹，确保基线与候选比较的是同一份数据。"""
    payload = "\n".join(case.model_dump_json(exclude_none=False) for case in sorted(cases, key=lambda item: item.id))
    return sha256(payload.encode("utf-8")).hexdigest()
