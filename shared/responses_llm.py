"""可选 Responses 协议实验；不会替换现有 Chat Completions 配置。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from shared.live_llm import LiveLLMSettings
from shared.llm_support import ChatResult, JSONTransport, LiveLLMRequestError, normalize_usage, safe_identifier


class ResponsesClient:
    """端点显式传入。仅在供应商和所选模型支持 Responses 时使用。"""

    def __init__(self, settings: LiveLLMSettings, *, endpoint: str, **transport_options: Any):
        if not endpoint:
            raise ValueError("Responses 实验必须显式传入端点")
        self.settings = settings
        self._http = JSONTransport(
            endpoint=endpoint, api_key=settings.api_key, timeout_seconds=settings.timeout_seconds,
            extra_headers=settings.extra_headers, **transport_options,
        )

    def respond(
        self, input_items: Sequence[Mapping[str, Any]], *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        instructions: str | None = None, text_format: Mapping[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.settings.model, "input": list(input_items), "store": False,
            "max_output_tokens": self.settings.max_tokens if max_output_tokens is None else max_output_tokens,
            # 无服务端存储时，保留推理延续所需的 opaque items；不展示推理正文。
            "include": ["reasoning.encrypted_content"],
        }
        if tools is not None:
            payload["tools"] = list(tools)
        if instructions is not None:
            payload["instructions"] = instructions
        if text_format is not None:
            payload["text"] = {"format": dict(text_format)}
        body, latency, attempts, request_id = self._http.post(payload, api_style="responses")
        items = body.get("output")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            self._http.emit({"event": "request_failed", "api_style": "responses", "attempt": attempts, "error_code": "INVALID_RESPONSE"})
            raise LiveLLMRequestError("INVALID_RESPONSE", attempts=attempts)
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        for item in items:
            if item.get("type") == "message":
                content = item.get("content")
                if not isinstance(content, list):
                    raise LiveLLMRequestError("INVALID_RESPONSE", attempts=attempts)
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
            elif item.get("type") == "function_call":
                if not all(isinstance(item.get(key), str) and item[key] for key in ("call_id", "name", "arguments")):
                    raise LiveLLMRequestError("INVALID_RESPONSE", attempts=attempts)
                calls.append({
                    "id": item.get("call_id"), "type": "function",
                    "function": {"name": item.get("name"), "arguments": item.get("arguments")},
                })
        message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
        if calls:
            message["tool_calls"] = calls
        result = ChatResult(
            message=message, usage=normalize_usage(body.get("usage")), model=safe_identifier(body.get("model")),
            response_id=safe_identifier(body.get("id")), finish_reason=safe_identifier(body.get("status")),
            latency_seconds=latency, attempts=attempts, request_id=safe_identifier(request_id), output_items=items,
        )
        self._http.emit({"event": "request_completed", "api_style": "responses", **result.metadata()})
        return result
