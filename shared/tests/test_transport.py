import json

import httpx
import pytest

from shared.live_llm import LiveLLMSettings, OpenAICompatibleChatClient
from shared.llm_support import JsonlEventSink, LiveLLMRequestError, ModelCapabilities, RetryPolicy
from shared.responses_llm import ResponsesClient


SETTINGS = LiveLLMSettings("https://example.invalid/v1/chat/completions", "test-model", "fake-secret")
MESSAGES = [{"role": "user", "content": "private prompt"}]


def completion(**overrides):
    return {
        "id": "r1", "model": "test-model", "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 120, "total_tokens": 320,
                  "completion_tokens_details": {"reasoning_tokens": 100}},
        **overrides,
    }


def test_old_chat_contract_and_new_metadata():
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=completion())))
    assert client.chat(MESSAGES) == {"role": "assistant", "content": "ok"}
    result = client.chat_result(MESSAGES)
    assert result.usage["total_tokens"] == 320
    assert result.usage["completion_tokens_details"]["reasoning_tokens"] == 100
    assert result.finish_reason == "stop"
    assert result.attempts == 1


def test_missing_usage_is_unknown_not_zero():
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=completion(usage=None))))
    assert client.chat_result(MESSAGES).usage == {}


def test_rate_limit_retry_after_then_success():
    requests, sleeps = [], []
    def handle(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "2"}) if len(requests) == 1 else httpx.Response(200, json=completion())
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(handle), sleep=sleeps.append)
    assert client.chat_result(MESSAGES).attempts == 2
    assert sleeps == [2.0]


@pytest.mark.parametrize("status,attempts,code", [(429, 3, "RATE_LIMITED"), (503, 3, "MODEL_UNAVAILABLE"), (401, 1, "MODEL_AUTH_FAILED"), (400, 1, "MODEL_HTTP_ERROR")])
def test_errors_are_bounded_and_do_not_expose_provider_body(status, attempts, code):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="fake-secret private prompt", headers={"Retry-After": "0"})
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(handle), sleep=lambda _: None)
    with pytest.raises(LiveLLMRequestError) as error:
        client.chat(MESSAGES)
    assert error.value.code == code
    assert error.value.attempts == attempts == len(calls)
    assert "fake-secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_excessive_retry_after_is_not_shortened():
    sleeps = []
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "300"})), sleep=sleeps.append)
    with pytest.raises(LiveLLMRequestError) as error:
        client.chat(MESSAGES)
    assert error.value.attempts == 1
    assert sleeps == []


def test_timeout_is_not_automatically_retried():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("fake-secret", request=request)
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(handle))
    with pytest.raises(LiveLLMRequestError, match="MODEL_TIMEOUT"):
        client.chat(MESSAGES)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [[], {}, {"choices": []}, {"choices": [{"message": "wrong"}]}])
def test_bad_response_structure(body):
    client = OpenAICompatibleChatClient(SETTINGS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(LiveLLMRequestError, match="INVALID_RESPONSE"):
        client.chat(MESSAGES)


def test_capabilities_omit_unsupported_parameter_without_changing_environment():
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=completion())
    client = OpenAICompatibleChatClient(SETTINGS, capabilities=ModelCapabilities(supports_temperature=False, supports_tools=False, supports_json_schema=False, max_tokens_parameter="max_completion_tokens"), transport=httpx.MockTransport(handle))
    client.chat(MESSAGES)
    assert "temperature" not in captured[0]
    assert captured[0]["max_completion_tokens"] == 512
    for kwargs in ({"temperature": 0}, {"tools": []}, {"response_format": {"type": "json_schema"}}):
        with pytest.raises(ValueError):
            client.chat(MESSAGES, **kwargs)
    assert len(captured) == 1


def test_metadata_log_does_not_include_prompts_or_credentials(tmp_path):
    path = tmp_path / "requests.jsonl"
    body = completion(model="echo:fake-secret")
    client = OpenAICompatibleChatClient(SETTINGS, event_sink=JsonlEventSink(path), transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    client.chat(MESSAGES)
    text = path.read_text(encoding="utf-8")
    assert "fake-secret" not in text and "private prompt" not in text
    assert json.loads(text)["usage"]["total_tokens"] == 320
    assert "message" not in json.loads(text)


def test_safe_summary_removes_url_credentials_query_and_secret():
    settings = LiveLLMSettings("https://user:password@example.invalid/fake-secret?key=hidden#fragment", "model", "fake-secret")
    summary = settings.safe_summary()
    assert all(value not in summary for value in ("user:password", "hidden", "fake-secret", "fragment"))


def test_responses_preserves_reasoning_and_call_id_for_continuation():
    output = [{"type": "reasoning", "id": "reason1", "encrypted_content": "opaque"},
              {"type": "function_call", "id": "item1", "call_id": "call1", "name": "lookup", "arguments": "{}"}]
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "resp1", "status": "completed", "output": output, "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}})
    client = ResponsesClient(SETTINGS, endpoint="https://example.invalid/v1/responses", transport=httpx.MockTransport(handle))
    result = client.respond(MESSAGES)
    assert result.output_items == output
    assert result.message["tool_calls"][0]["id"] == "call1"
    client.respond([*MESSAGES, *result.output_items, {"type": "function_call_output", "call_id": "call1", "output": "found"}])
    assert captured[1]["input"][1] == output[0]
    assert captured[0]["store"] is False
    assert "messages" not in captured[0]
    assert result.usage["total_tokens"] == 15


def test_responses_incomplete_is_not_disguised_as_completed():
    client = ResponsesClient(SETTINGS, endpoint="https://example.invalid/v1/responses", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "incomplete", "output": []})))
    assert client.respond(MESSAGES).finish_reason == "incomplete"


@pytest.mark.parametrize("attempts", [0, 11, True])
def test_retry_policy_rejects_unbounded_or_invalid_attempts(attempts):
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=attempts)


def test_retry_budget_prevents_further_waiting():
    now, calls, waits = [0.0], [], []
    def handle(request):
        calls.append(request)
        now[0] += 2
        return httpx.Response(429, headers={"Retry-After": "2"})
    client = OpenAICompatibleChatClient(SETTINGS, retry_policy=RetryPolicy(total_timeout_seconds=3), transport=httpx.MockTransport(handle), clock=lambda: now[0], sleep=waits.append)
    with pytest.raises(LiveLLMRequestError) as error:
        client.chat(MESSAGES)
    assert len(calls) == 1 and waits == [] and error.value.code == "RATE_LIMITED"


def test_malformed_json_records_sanitized_failure():
    events = []
    client = OpenAICompatibleChatClient(SETTINGS, event_sink=events.append, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="fake-secret")))
    with pytest.raises(LiveLLMRequestError, match="INVALID_RESPONSE"):
        client.chat(MESSAGES)
    assert events[-1]["error_code"] == "INVALID_RESPONSE"
    assert "fake-secret" not in str(events)


def test_settings_repr_omits_custom_auth_headers():
    settings = LiveLLMSettings("https://example.invalid", "model", "fake-secret", extra_headers={"X-Key": "custom-secret"})
    assert "custom-secret" not in repr(settings) and "fake-secret" not in repr(settings)
