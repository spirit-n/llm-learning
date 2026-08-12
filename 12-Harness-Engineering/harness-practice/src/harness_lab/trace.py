from __future__ import annotations

import re
from typing import Any

from .models import TraceEvent


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "token",
    "id_token",
    "access_token",
    "refresh_token",
    "auth_token",
    "credential",
    "credentials",
}
SENSITIVE_VALUE = re.compile(r"(?i)\b(?:bearer\s+|sk-)[a-z0-9._-]{8,}")


class TraceRecorder:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def add(self, event: str, status: str = "ok", **details: Any) -> None:
        self.events.append(
            TraceEvent(
                sequence=len(self.events) + 1,
                event=event,
                status=status,
                details=_redact(details),
            )
        )


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_key(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        value = SENSITIVE_VALUE.sub("[REDACTED]", value)
        if len(value) > 500:
            return value[:500] + "…[TRUNCATED]"
    return value


def _is_sensitive_key(key: Any) -> bool:
    """精确识别凭据字段，避免把 prompt_tokens 等正常指标误删。"""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return normalized in SENSITIVE_KEYS or any(
        normalized.endswith("_" + suffix) for suffix in SENSITIVE_KEYS
    )
