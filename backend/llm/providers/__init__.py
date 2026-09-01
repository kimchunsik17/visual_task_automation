from __future__ import annotations

import os
from dataclasses import replace
from typing import Optional, Set

from .adapters import AnthropicProvider, GoogleProvider, MockProvider, OpenAICompatibleProvider, OpenAIProvider, OpenRouterProvider
from .base import (
    GenerationRequest,
    GenerationResult,
    ModelProvider,
    ProviderCapabilities,
    ProviderConfigurationError,
)
from .config import LLMSettings, load_llm_settings
from llm.routing import HybridChatModel, routing_metrics


def get_model_provider(provider_name: Optional[str] = None, settings: Optional[LLMSettings] = None):
    settings = settings or load_llm_settings()
    name = (provider_name or settings.provider).strip().lower()
    providers = {
        "openai": OpenAIProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "local": OpenAICompatibleProvider,
        "openrouter": OpenRouterProvider,
        "google": GoogleProvider,
        "anthropic": AnthropicProvider,
        "mock": MockProvider,
    }
    provider_cls = providers.get(name)
    if provider_cls is None:
        allowed = ", ".join(sorted(providers))
        raise ProviderConfigurationError(f"알 수 없는 LLM_PROVIDER '{name}'입니다. 허용값: {allowed}")
    return provider_cls(settings)


def create_chat_model(
    *,
    profile: str = "balanced",
    model: Optional[str] = None,
    provider_name: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: Optional[int] = None,
    api_key: Optional[str] = None,
    required_capabilities: Optional[Set[str]] = None,
):
    settings = load_llm_settings()
    routing_mode = os.getenv("LLM_ROUTING_MODE", "provider").strip().lower()
    if provider_name == "mock" or settings.provider == "mock":
        routing_mode = "provider"

    if routing_mode in {"local", "hybrid"} and provider_name is None:
        local_base_url = os.getenv("LLM_LOCAL_BASE_URL", "").strip() or settings.base_url
        if not local_base_url:
            raise ProviderConfigurationError(
                f"LLM_ROUTING_MODE={routing_mode}일 때 LLM_LOCAL_BASE_URL이 필요합니다."
            )
        local_models = {
            key: os.getenv(f"LLM_LOCAL_MODEL_{key.upper()}", "").strip() or value
            for key, value in settings.models.items()
        }
        local_settings = replace(
            settings,
            provider="openai_compatible",
            base_url=local_base_url,
            api_key=os.getenv("LLM_LOCAL_API_KEY", "").strip() or "local",
            models=local_models,
        )
        local_provider = get_model_provider("openai_compatible", local_settings)
        required = required_capabilities or set()
        try:
            local_provider.require(required)
        except ProviderConfigurationError:
            if routing_mode == "local":
                raise
            routing_metrics.record_forced_hosted()
            local_provider = None

        if local_provider is not None:
            local_model = local_settings.model_for(profile)
            primary = local_provider.create_chat_model(
                model=local_model,
                temperature=temperature,
                max_retries=max_retries,
                api_key=None,
            )
            if routing_mode == "local":
                return primary

        fallback_name = os.getenv("LLM_FALLBACK_PROVIDER", "openai").strip().lower()
        fallback_settings = replace(
            settings,
            provider=fallback_name,
            base_url=os.getenv("LLM_FALLBACK_BASE_URL", "").strip() or None,
            api_key=os.getenv("LLM_FALLBACK_API_KEY", "").strip() or settings.api_key,
        )
        fallback_provider = get_model_provider(fallback_name, fallback_settings)
        fallback_provider.require(required)
        fallback = fallback_provider.create_chat_model(
            model=model or settings.model_for(profile),
            temperature=temperature,
            max_retries=max_retries,
            api_key=api_key,
        )
        if local_provider is None:
            return fallback
        return HybridChatModel(
            primary=primary,
            fallback=fallback,
            local_percentage=os.getenv("LLM_LOCAL_TRAFFIC_PERCENT", "100"),
        )

    provider = get_model_provider(provider_name, settings)
    provider.require(required_capabilities or set())
    selected_model = model or settings.model_for(profile)
    return provider.create_chat_model(
        model=selected_model,
        temperature=temperature,
        max_retries=max_retries,
        api_key=api_key,
    )


def provider_name_for_model(model: str) -> str:
    # OpenRouter 를 쓰기로 설정했으면 vendor 를 가리지 않고 전부 OpenRouter 로 보낸다 —
    # OpenRouter 가 openai/anthropic/google 모델을 모두 한 API 로 서빙하기 때문이다.
    # (provider 는 여전히 모델명으로 네임스페이스를 붙인다: claude-* → anthropic/claude-*)
    if os.getenv("LLM_PROVIDER", "openai").strip().lower() == "openrouter":
        return "openrouter"
    lowered = model.lower()
    if "claude" in lowered:
        return "anthropic"
    if "gemini" in lowered:
        return "google"
    return "openai"


def create_runtime_chat_model(
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = 0,
):
    """Create an execution model while allowing a global local-provider override."""
    runtime_provider = os.getenv("LLM_EXECUTION_PROVIDER", "auto").strip().lower()
    routing_mode = os.getenv("LLM_ROUTING_MODE", "provider").strip().lower()
    if runtime_provider == "hybrid" or (runtime_provider == "auto" and routing_mode in {"local", "hybrid"}):
        return create_chat_model(
            profile="fast",
            model=model,
            max_retries=max_retries,
            api_key=api_key,
            required_capabilities=set(),
        )
    if runtime_provider in {"local", "openai_compatible"}:
        return create_chat_model(
            profile="fast",
            provider_name="openai_compatible",
            max_retries=max_retries,
            required_capabilities=set(),
        )
    selected_model = model or load_llm_settings().model_for("fast")
    return create_chat_model(
        model=selected_model,
        provider_name=provider_name_for_model(selected_model),
        api_key=api_key,
        max_retries=max_retries,
    )


__all__ = [
    "GenerationRequest",
    "GenerationResult",
    "LLMSettings",
    "ModelProvider",
    "ProviderCapabilities",
    "ProviderConfigurationError",
    "create_chat_model",
    "create_runtime_chat_model",
    "get_model_provider",
    "load_llm_settings",
]
