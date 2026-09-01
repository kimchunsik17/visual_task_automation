"""OpenRouter 경유 라우팅 (채팅만; 임베딩·이미지는 OpenAI 직결 유지).

지원처 정책이 바뀌어 GPT 키 대신 OpenRouter 로 지원받게 되면서 추가했다. OpenRouter 는 OpenAI
호환 chat completions API 라 ChatOpenAI 에 base_url 만 바꿔 쓴다. 여기서 지키는 문장:

  1. LLM_PROVIDER=openrouter 면 채팅 모델이 openrouter.ai 로, 모델명은 vendor 네임스페이스로 간다.
  2. 임베딩·이미지 생성은 OpenRouter 에 API 가 없으므로 LLM_PROVIDER 와 무관하게 OpenAI 로 간다.
  3. 기본값(LLM_PROVIDER 미설정/openai)에서는 동작이 그대로다.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_providers():
    """provider 모듈은 import 시점에 env 를 읽으므로 테스트마다 다시 읽게 한다."""
    def _reload():
        import llm.providers.config as cfg
        import llm.providers.adapters as ad
        import llm.providers as pkg
        importlib.reload(cfg)
        importlib.reload(ad)
        importlib.reload(pkg)
        return pkg
    return _reload


def test_model_namespacing():
    from llm.providers.adapters import openrouter_model_id
    assert openrouter_model_id("gpt-4o-mini") == "openai/gpt-4o-mini"
    assert openrouter_model_id("gpt-5.6-terra") == "openai/gpt-5.6-terra"
    assert openrouter_model_id("claude-3.5-sonnet") == "anthropic/claude-3.5-sonnet"
    assert openrouter_model_id("gemini-2.0-flash") == "google/gemini-2.0-flash"
    # 이미 네임스페이스가 있으면 그대로
    assert openrouter_model_id("openai/gpt-4o") == "openai/gpt-4o"
    assert openrouter_model_id("") == ""


def test_openrouter_settings_use_openrouter_key_not_openai(monkeypatch, reload_providers):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-not-be-used")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    pkg = reload_providers()

    settings = pkg.load_llm_settings()
    assert settings.provider == "openrouter"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    # OPENAI_API_KEY 로 폴백하면 안 된다(openrouter.ai 에서 무효라 401 이 난다).
    assert settings.api_key == "sk-or-xxx"


def test_openrouter_chat_model_targets_openrouter(monkeypatch, reload_providers):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-xxx")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    pkg = reload_providers()

    model = pkg.create_runtime_chat_model(model="gpt-4o-mini")
    assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"
    assert model.model_name == "openai/gpt-4o-mini"
    # 런타임(노드 실행) 라우팅도 openrouter 로 가야 한다
    assert pkg.provider_name_for_model("gpt-4o-mini") == "openrouter"
    assert pkg.provider_name_for_model("claude-3.5-sonnet") == "openrouter"


def test_openrouter_without_key_is_a_clear_error(monkeypatch, reload_providers):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    pkg = reload_providers()

    from llm.providers.base import ProviderConfigurationError
    with pytest.raises(ProviderConfigurationError):
        pkg.create_runtime_chat_model(model="gpt-4o-mini")


def test_default_provider_still_openai(monkeypatch, reload_providers):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    pkg = reload_providers()

    model = pkg.create_runtime_chat_model(model="gpt-4o-mini")
    # 기본은 openai 직결 — base_url 이 openrouter 가 아니어야 한다
    assert "openrouter" not in str(model.openai_api_base or "")
    assert model.model_name == "gpt-4o-mini"  # 네임스페이스 안 붙음
    assert pkg.provider_name_for_model("gpt-4o-mini") == "openai"


def test_embeddings_never_go_through_openrouter(monkeypatch):
    """임베딩은 OpenRouter 에 API 가 없다. LLM_PROVIDER 와 무관하게 OpenAI 로 가야 한다."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    import rag_utils
    emb = rag_utils.OpenAIEmbeddings(model="text-embedding-3-small")
    base = str(getattr(emb, "openai_api_base", "") or "")
    assert "openrouter" not in base, "임베딩이 OpenRouter 로 샜다 — 거기엔 임베딩 API 가 없다"
