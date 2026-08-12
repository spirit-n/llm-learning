import pytest

from shared.live_llm import LiveLLMConfigurationError, LiveLLMSettings, parse_json_content


def test_settings_allow_endpoint_model_and_key_variable_to_change(monkeypatch):
    monkeypatch.delenv("LLM_CHAT_COMPLETIONS_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY_ENV", "TEST_PROVIDER_KEY")
    monkeypatch.setenv("TEST_PROVIDER_KEY", "not-a-real-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1/")
    monkeypatch.setenv("LLM_MODEL", "new-model")
    settings = LiveLLMSettings.from_env()
    assert settings.endpoint == "https://provider.example/v1/chat/completions"
    assert settings.base_url == "https://provider.example/v1"
    assert settings.model == "new-model"
    assert "not-a-real-secret" not in settings.safe_summary()


def test_full_endpoint_takes_priority(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://ignored.example/v1")
    monkeypatch.setenv("LLM_CHAT_COMPLETIONS_URL", "https://gateway.example/custom/chat/completions")
    assert LiveLLMSettings.from_env().endpoint == "https://gateway.example/custom/chat/completions"


def test_missing_key_stops_before_network(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY_ENV", "KEY_THAT_DOES_NOT_EXIST")
    monkeypatch.delenv("KEY_THAT_DOES_NOT_EXIST", raising=False)
    with pytest.raises(LiveLLMConfigurationError):
        LiveLLMSettings.from_env()


@pytest.mark.parametrize(
    ("missing_name", "message"),
    [
        ("LLM_BASE_URL", "模型端点"),
        ("LLM_MODEL", "模型名"),
    ],
)
def test_endpoint_and_model_are_required(monkeypatch, missing_name, message):
    monkeypatch.delenv("LLM_CHAT_COMPLETIONS_URL", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-secret")
    monkeypatch.delenv(missing_name, raising=False)
    with pytest.raises(LiveLLMConfigurationError, match=message):
        LiveLLMSettings.from_env()


def test_parse_json_content_accepts_markdown_fence():
    assert parse_json_content("```json\n{\"ok\": true}\n```") == {"ok": True}
