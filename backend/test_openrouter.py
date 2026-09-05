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
    # delenv 가 아니라 빈 문자열 — 지우면 reload 의 load_dotenv 가 로컬 .env 값을 다시 채운다.
    # load_llm_settings 는 빈 문자열을 "미설정"(=openai)으로 읽는다.
    monkeypatch.setenv("LLM_PROVIDER", "")
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


# ── PICKLE 게이트웨이 (OpenRouter 호환, 허용 필드 화이트리스트) ─────────────

PICKLE_BASE_URL = "https://llm.pcl.kr/v1"


def _payload_keys(model, messages=None):
    from langchain_core.messages import HumanMessage, SystemMessage
    msgs = messages or [SystemMessage(content="s"), HumanMessage(content="u")]
    return model._get_request_payload(msgs)


def test_gateway_uses_pickle_key_and_base_url(monkeypatch, reload_providers):
    """지원처 문서의 변수명(PICKLE_API_KEY) 그대로 받고, base_url 은 게이트웨이로 간다."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_BASE_URL", PICKLE_BASE_URL)
    monkeypatch.setenv("PICKLE_API_KEY", "pk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    pkg = reload_providers()

    settings = pkg.load_llm_settings()
    assert settings.base_url == PICKLE_BASE_URL and settings.api_key == "pk-test"
    model = pkg.create_runtime_chat_model(model="gpt-5.6-luna")
    assert str(model.openai_api_base) == PICKLE_BASE_URL
    assert model.model_name == "openai/gpt-5.6-luna"     # OpenRouter 식 vendor 접두


def test_gateway_payload_stays_inside_allowed_fields(monkeypatch, reload_providers):
    """게이트웨이는 허용 17개 필드 밖이면 400 이다 — gpt-5 계열에 붙이던 reasoning_effort 를
    보내지 않아야 하고, Responses API 로 자동 전환되면 안 된다(chat/completions 만 제공)."""
    from llm.providers.adapters import GATEWAY_ALLOWED_FIELDS
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_BASE_URL", PICKLE_BASE_URL)
    monkeypatch.setenv("PICKLE_API_KEY", "pk-test")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    pkg = reload_providers()

    for name in ("gpt-4o-mini", "gpt-5.6-luna", "openai/gpt-5.4-mini", "gpt-5.4-pro"):
        model = pkg.create_runtime_chat_model(model=name)
        payload = _payload_keys(model)
        extra = set(payload) - GATEWAY_ALLOWED_FIELDS
        assert not extra, f"{name}: 게이트웨이 비허용 필드 {sorted(extra)}"
        assert model._use_responses_api(payload) is False, f"{name}: Responses API 로 전환됐다"

    # 구조화 출력(response_format)도 허용 필드 안이다
    model = pkg.create_runtime_chat_model(model="gpt-5.6-luna")
    schema = {"title": "T", "type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    bound = model.with_structured_output(schema, include_raw=True)
    # RunnableAssign(raw=bound model | ...) 안의 bound 모델 kwargs 를 꺼내 실제 페이로드를 본다
    def _find_bound(x, depth=0):
        if depth > 6:
            return None
        if hasattr(x, "bound") and hasattr(x, "kwargs"):
            return x
        for attr in ("first", "last", "default", "mapper", "steps__", "steps"):
            v = getattr(x, attr, None)
            if v is None:
                continue
            items = v.values() if isinstance(v, dict) else (v if isinstance(v, (list, tuple)) else [v])
            for vv in items:
                found = _find_bound(vv, depth + 1)
                if found is not None:
                    return found
        return None
    b = _find_bound(bound)
    assert b is not None
    # ls_structured_output_format 은 LangSmith 추적 인자 — langchain_core 가 전송 전에 제거한다.
    kwargs = {k: v for k, v in b.kwargs.items() if k != "ls_structured_output_format"}
    payload = b.bound._get_request_payload([("system", "s"), ("user", "u")], **kwargs)
    assert "response_format" in payload
    assert not (set(payload) - GATEWAY_ALLOWED_FIELDS), sorted(set(payload) - GATEWAY_ALLOWED_FIELDS)


def test_official_openrouter_keeps_reasoning_effort(monkeypatch, reload_providers):
    """엄격 모드는 게이트웨이(openrouter.ai 아님)에서만 — 공식 OpenRouter 동작은 그대로다."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-xxx")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    pkg = reload_providers()

    model = pkg.create_runtime_chat_model(model="gpt-5.6-luna")
    assert "reasoning_effort" in _payload_keys(model)


def test_strict_mode_can_be_forced_either_way(monkeypatch, reload_providers):
    from llm.providers.adapters import is_strict_gateway
    monkeypatch.setenv("OPENROUTER_STRICT_FIELDS", "")
    assert is_strict_gateway(PICKLE_BASE_URL) is True
    assert is_strict_gateway("https://openrouter.ai/api/v1") is False
    monkeypatch.setenv("OPENROUTER_STRICT_FIELDS", "1")
    assert is_strict_gateway("https://openrouter.ai/api/v1") is True
    monkeypatch.setenv("OPENROUTER_STRICT_FIELDS", "0")
    assert is_strict_gateway(PICKLE_BASE_URL) is False
