import json

import pytest
from pydantic import BaseModel

from llm.providers import (
    GenerationRequest,
    ProviderConfigurationError,
    create_chat_model,
    get_model_provider,
    load_llm_settings,
)


class MockShape(BaseModel):
    value: str


def test_model_profile_aliases_keep_existing_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_FAST", raising=False)
    monkeypatch.delenv("LLM_MODEL_BALANCED", raising=False)
    monkeypatch.delenv("LLM_MODEL_QUALITY", raising=False)
    settings = load_llm_settings()

    # 코드 기본값(config.load_llm_settings)과 맞춘다. 이 값이 바뀌면 여기도 함께 바꾼다 —
    # 서버 .env 에는 LLM_MODEL_* 가 없어 이 기본값이 그대로 운영에 쓰인다.
    assert settings.model_for("low") == "gpt-5.4-mini"
    assert settings.model_for("medium") == "gpt-5.6-terra"
    assert settings.model_for("high") == "gpt-5.6-sol"


def test_openai_compatible_provider_requires_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    with pytest.raises(ProviderConfigurationError, match="LLM_BASE_URL"):
        get_model_provider()


def test_local_capability_check_is_explicit(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LLM_LOCAL_SUPPORTS_TOOL_CALLING", "false")
    provider = get_model_provider()

    with pytest.raises(ProviderConfigurationError, match="tool_calling"):
        provider.require({"tool_calling"})


def test_mock_provider_supports_text_and_structured_output(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", json.dumps({"value": "ok"}))
    model = create_chat_model(profile="fast", required_capabilities={"structured_output", "tool_calling"})

    assert json.loads(model.invoke("hello").content) == {"value": "ok"}
    assert model.with_structured_output(MockShape).invoke("hello") == MockShape(value="ok")


@pytest.mark.asyncio
async def test_provider_generate_returns_common_result(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", "hello")
    provider = get_model_provider()

    result = await provider.generate(GenerationRequest(
        task_type="test", system_prompt="system", user_prompt="user", model_profile="fast"
    ))

    assert result.text == "hello"
    assert result.provider == "mock"
    # 'fast' 프로파일의 실제 기본 모델과 맞춘다(하드코딩된 옛 이름 대신).
    assert result.model == load_llm_settings().model_for("fast")
