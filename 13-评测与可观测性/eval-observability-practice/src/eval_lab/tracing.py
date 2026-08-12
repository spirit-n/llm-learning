from __future__ import annotations

import re
import time
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

from .models import Span


# 字段名要精确判断。直接搜索 ``token`` 会误伤 prompt_tokens、completion_tokens
# 这类本来就应该保留的观测指标，导致导出的评测报告无法核算成本。
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_token",
    "credential",
    "credentials",
}
SENSITIVE_VALUE = re.compile(r"(?i)\b(?:bearer\s+|sk-)[a-z0-9._-]{8,}")
INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\b\s*[:=]\s*[^\s,;\"']+"
)
CHINESE_SECRET = re.compile(r"(?:密钥|口令|密码)\s*(?:是|为|[:：=])\s*[^\s,，;；\"']+")


SPAN_KINDS = {"model", "retrieval", "tool", "guard", "workflow"}


class TraceCollector:
    def __init__(self) -> None:
        self.trace_id = uuid4().hex
        self.spans: list[Span] = []

    @contextmanager
    def span(
        self,
        name: str,
        *,
        parent_id: str | None = None,
        kind: str | None = None,
        **attributes: Any,
    ) -> Iterator[str]:
        span_id = uuid4().hex
        started = time.perf_counter()
        status = "ok"
        try:
            yield span_id
        except Exception:
            status = "error"
            attributes["exception_type"] = "captured"
            raise
        finally:
            self.spans.append(
                Span(
                    span_id=span_id,
                    parent_id=parent_id,
                    name=name,
                    kind=kind if kind in SPAN_KINDS else "other",
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    attributes=redact(attributes),
                )
            )


def redact(value: Any) -> Any:
    """递归清洗准备写入磁盘的对象。

    字段名脱敏覆盖嵌套 tool arguments；字符串模式脱敏覆盖 output、异常文本等
    自由文本。TraceCollector 和报告导出共用这一条规则，避免两套规则漂移。
    """
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = SENSITIVE_VALUE.sub("[REDACTED]", value)
        value = INLINE_SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
        value = CHINESE_SECRET.sub("密钥=[REDACTED]", value)
        if len(value) > 300:
            return value[:300] + "…[TRUNCATED]"
    return value


def _is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    if normalized in SENSITIVE_KEYS:
        return True
    # 允许业务对象使用前缀，例如 provider_api_key；但不会把 max_tokens 当成密钥。
    return any(normalized.endswith("_" + suffix) for suffix in SENSITIVE_KEYS)


# 兼容旧教学代码中的内部函数名；新代码统一使用公开的 redact。
_redact = redact
