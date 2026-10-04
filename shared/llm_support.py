"""模型调用的公共结果、有限重试和元数据日志；不读取或修改环境变量。"""

from __future__ import annotations

import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx


@dataclass(frozen=True)
class ModelCapabilities:
    """由调用方根据供应商文档选择；不能仅凭 model 名猜测能力。"""

    supports_temperature: bool = True
    supports_tools: bool = True
    supports_json_schema: bool = True
    max_tokens_parameter: str = "max_tokens"

    def __post_init__(self) -> None:
        if self.max_tokens_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("Chat Completions 输出预算字段不受支持")


@dataclass(frozen=True)
class RetryPolicy:
    # 只重试明确的瞬时 HTTP 错误；超时可能已产生推理费用，默认不重试。
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    total_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts 必须在 1～10 之间")
        for value in (self.initial_delay_seconds, self.max_delay_seconds):
            if not math.isfinite(value) or value < 0:
                raise ValueError("退避时间必须是有限非负数")
        if self.total_timeout_seconds is not None and (
            not math.isfinite(self.total_timeout_seconds) or self.total_timeout_seconds <= 0
        ):
            raise ValueError("总等待预算必须是有限正数")


class LiveLLMRequestError(RuntimeError):
    def __init__(self, code: str, *, status_code: int | None = None, attempts: int = 1):
        self.code = code
        self.status_code = status_code
        self.attempts = attempts
        self.retryable = code in {"RATE_LIMITED", "MODEL_UNAVAILABLE"}
        http = f" HTTP {status_code}" if status_code else ""
        # 不回显供应商响应正文、请求 URL、Authorization 或原始异常。
        super().__init__(f"模型请求失败{http}：{code}（已尝试 {attempts} 次）")


@dataclass(frozen=True)
class ChatResult:
    message: dict[str, Any] = field(repr=False)
    usage: dict[str, Any]
    model: str | None
    response_id: str | None
    finish_reason: str | None
    latency_seconds: float
    attempts: int
    request_id: str | None = None
    # Responses 继续对话时必须回传所有 items，不只回传最终文本。
    output_items: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def metadata(self) -> dict[str, Any]:
        return {
            "model": self.model, "response_id": self.response_id,
            "request_id": self.request_id, "finish_reason": self.finish_reason,
            "usage": self.usage, "latency_seconds": self.latency_seconds,
            "attempts": self.attempts,
        }


_USAGE_KEYS = {
    "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
    "cached_tokens", "cache_write_tokens", "reasoning_tokens", "audio_tokens",
    "accepted_prediction_tokens", "rejected_prediction_tokens",
    "prompt_tokens_details", "completion_tokens_details", "input_tokens_details", "output_tokens_details",
}


def normalize_usage(value: Any) -> dict[str, Any]:
    """保留供应商提供的计数，缺失不造 0，reasoning 不重复加总。"""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key not in _USAGE_KEYS:
            continue
        if isinstance(item, Mapping):
            result[key] = normalize_usage(item)
        elif isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            result[key] = item
    return result


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """用于显式保存学习报告；字段脱敏＋已知凭据替换，不承诺任意 PII 检测。"""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if re.search(r"key|secret|password|authorization|cookie", str(key), re.I)
            else redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    return value


class JsonlEventSink:
    """只持久化白名单元数据，不记录提示词、工具参数和模型正文。"""

    FIELDS = frozenset({
        "event", "api_style", "model", "response_id", "request_id", "finish_reason",
        "attempt", "attempts", "latency_seconds", "status_code", "error_code", "usage",
        "retry_delay_seconds",
    })

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def __call__(self, event: Mapping[str, Any]) -> None:
        record = {key: value for key, value in event.items() if key in self.FIELDS}
        record["recorded_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


class JSONTransport:
    def __init__(
        self, *, endpoint: str, api_key: str, timeout_seconds: float,
        extra_headers: Mapping[str, str], policy: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        event_sink: Callable[[Mapping[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.policy = policy or RetryPolicy()
        self.transport = transport
        self.sleep, self.clock = sleep, clock
        self.event_sink = event_sink
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **extra_headers}
        self.secrets = tuple({api_key, *extra_headers.values(), self.headers["Authorization"]})

    def emit(self, event: Mapping[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(redact(event, self.secrets))

    def post(self, payload: dict[str, Any], *, api_style: str) -> tuple[dict, float, int, str | None]:
        start = self.clock()
        budget = self.policy.total_timeout_seconds or self.timeout_seconds
        deadline = start + budget
        with httpx.Client(transport=self.transport) as client:
            for attempt in range(1, self.policy.max_attempts + 1):
                remaining = deadline - self.clock()
                if remaining <= 0:
                    self.emit({"event": "request_failed", "api_style": api_style, "attempts": attempt - 1, "error_code": "MODEL_DEADLINE"})
                    raise LiveLLMRequestError("MODEL_DEADLINE", attempts=attempt - 1)
                try:
                    response = client.post(self.endpoint, headers=self.headers, json=payload, timeout=min(self.timeout_seconds, remaining))
                except httpx.TimeoutException:
                    self.emit({"event": "request_failed", "api_style": api_style, "attempt": attempt, "error_code": "MODEL_TIMEOUT"})
                    raise LiveLLMRequestError("MODEL_TIMEOUT", attempts=attempt) from None
                except httpx.HTTPError:
                    self.emit({"event": "request_failed", "api_style": api_style, "attempt": attempt, "error_code": "MODEL_CONNECTION_ERROR"})
                    raise LiveLLMRequestError("MODEL_CONNECTION_ERROR", attempts=attempt) from None
                if response.is_success:
                    try:
                        body = response.json()
                    except ValueError:
                        self.emit({"event": "request_failed", "api_style": api_style, "attempt": attempt, "error_code": "INVALID_RESPONSE"})
                        raise LiveLLMRequestError("INVALID_RESPONSE", attempts=attempt) from None
                    if not isinstance(body, dict):
                        self.emit({"event": "request_failed", "api_style": api_style, "attempt": attempt, "error_code": "INVALID_RESPONSE"})
                        raise LiveLLMRequestError("INVALID_RESPONSE", attempts=attempt)
                    return body, round(self.clock() - start, 6), attempt, response.headers.get("x-request-id")

                status = response.status_code
                code = "RATE_LIMITED" if status == 429 else "MODEL_AUTH_FAILED" if status in {401, 403} else "MODEL_UNAVAILABLE" if status in {500, 502, 503, 504} else "MODEL_HTTP_ERROR"
                self.emit({"event": "request_failed", "api_style": api_style, "attempt": attempt, "status_code": status, "error_code": code})
                if code not in {"RATE_LIMITED", "MODEL_UNAVAILABLE"} or attempt == self.policy.max_attempts:
                    raise LiveLLMRequestError(code, status_code=status, attempts=attempt)
                retry_after = _retry_after(response.headers.get("Retry-After"))
                delay = retry_after if retry_after is not None else min(
                    self.policy.max_delay_seconds,
                    self.policy.initial_delay_seconds * 2 ** (attempt - 1) * random.uniform(0.8, 1.2),
                )
                # 不把 Retry-After 截短后提前冲击接口；超出预算则明确结束。
                if delay > self.policy.max_delay_seconds or delay >= deadline - self.clock():
                    raise LiveLLMRequestError(code, status_code=status, attempts=attempt)
                self.emit({"event": "request_retry", "api_style": api_style, "attempt": attempt, "retry_delay_seconds": delay})
                self.sleep(delay)
        raise AssertionError("unreachable")


def safe_identifier(value: Any) -> str | None:
    return value[:200] if isinstance(value, str) else None
