from __future__ import annotations

import math
import re
from collections import Counter


TOKEN_PATTERN = re.compile(r"[A-Za-z]+\d*|\d+(?:\.\d+)?|[\u4e00-\u9fff]")
SYNONYMS = {
    "营收": "营业收入",
    "收入": "营业收入",
    "成交": "支付",
    "存货": "库存",
    "报错": "错误码",
    # 教学语料中的“RAG/幻觉”与用户口语建立显式同义关系，避免门控只认字面。
    "检索增强": "rag",
    "胡编": "幻觉",
}


def normalize(text: str) -> str:
    normalized = text.lower().strip()
    for source, target in SYNONYMS.items():
        normalized = normalized.replace(source, target)
    return normalized


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(normalize(text))


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def term_counts(text: str) -> Counter[str]:
    return Counter(tokenize(text))
