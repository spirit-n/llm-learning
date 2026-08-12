"""可配置的 OpenAI-compatible Chat Completions 客户端。

这个模块只供 ``tests_live`` 和手工实验使用。业务示例仍可离线运行。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx


CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


class LiveLLMConfigurationError(RuntimeError):
    """真实模型连接配置不完整或不合法。"""


@dataclass(frozen=True)
class LiveLLMSettings:
    endpoint: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 60.0
    temperature: float = 0.0
    max_tokens: int = 512
    extra_headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "LiveLLMSettings":
        full_endpoint = os.getenv("LLM_CHAT_COMPLETIONS_URL", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        if not full_endpoint and not base_url:
            raise LiveLLMConfigurationError(
                "未配置模型端点：请设置 LLM_BASE_URL，或设置完整的 LLM_CHAT_COMPLETIONS_URL。"
            )
        endpoint = full_endpoint or _chat_completions_url(base_url)

        model = os.getenv("LLM_MODEL", "").strip()
        if not model:
            raise LiveLLMConfigurationError("未配置模型名：请设置 LLM_MODEL。")

        key_env_name = os.getenv("LLM_API_KEY_ENV", "").strip()
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if not api_key and key_env_name:
            api_key = os.getenv(key_env_name, "").strip()
        if not api_key:
            detail = (
                f"环境变量 {key_env_name} 中没有密钥。"
                if key_env_name
                else "请设置 LLM_API_KEY；或设置 LLM_API_KEY_ENV，并在它指向的变量中保存密钥。"
            )
            raise LiveLLMConfigurationError(f"未配置模型密钥：{detail}")

        extra_headers = _json_string_mapping(os.getenv("LLM_EXTRA_HEADERS_JSON", ""))
        return cls(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 60.0),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            max_tokens=_positive_int("LLM_MAX_TOKENS", 512),
            extra_headers=extra_headers,
        )

    def safe_summary(self) -> str:
        """可安全打印的连接摘要，刻意不包含 API Key。"""
        return f"endpoint={self.endpoint}, model={self.model}, timeout={self.timeout_seconds}s"

    @property
    def base_url(self) -> str:
        """供只接受 API 根地址的框架 SDK 使用。"""
        return (
            self.endpoint[: -len(CHAT_COMPLETIONS_SUFFIX)]
            if self.endpoint.endswith(CHAT_COMPLETIONS_SUFFIX)
            else self.endpoint
        )


class OpenAICompatibleChatClient:
    def __init__(self, settings: LiveLLMSettings):
        self.settings = settings

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": list(messages),
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": self.settings.max_tokens if max_tokens is None else max_tokens,
        }
        if tools is not None:
            payload["tools"] = list(tools)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = dict(response_format)

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            **self.settings.extra_headers,
        }
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(self.settings.endpoint, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _safe_error_body(exc.response)
            raise RuntimeError(f"模型接口返回 HTTP {exc.response.status_code}: {detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"模型请求失败（{self.settings.safe_summary()}）：{exc}") from exc

        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型响应缺少 choices[0].message：{_compact_json(body)}") from exc
        if not isinstance(message, dict):
            raise RuntimeError("choices[0].message 不是 JSON 对象")
        return message


def parse_json_content(message_or_content: Mapping[str, Any] | str) -> Any:
    """解析模型文本中的 JSON，并兼容常见 Markdown 围栏。"""
    content = (
        message_or_content.get("content", "")
        if isinstance(message_or_content, Mapping)
        else message_or_content
    )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型没有返回可解析的文本内容")
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _json_string_mapping(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError("LLM_EXTRA_HEADERS_JSON 必须是字符串到字符串的 JSON 对象")
    return value


def _chat_completions_url(base_url: str) -> str:
    return base_url if base_url.endswith(CHAT_COMPLETIONS_SUFFIX) else base_url + CHAT_COMPLETIONS_SUFFIX


def _positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


def _safe_error_body(response: httpx.Response) -> str:
    text = response.text[:800]
    auth = response.request.headers.get("Authorization", "")
    return text.replace(auth, "[REDACTED]") if auth else text


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:800]
