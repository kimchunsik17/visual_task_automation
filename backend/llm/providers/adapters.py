from __future__ import annotations

import os
import json
import time
from typing import Any, Optional, Set

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .base import (
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    ProviderConfigurationError,
)
from .config import LLMSettings


class BaseLangChainProvider:
    name = "base"
    capabilities = ProviderCapabilities()

    def require(self, capabilities: Set[str]) -> None:
        missing = [name for name in sorted(capabilities) if not getattr(self.capabilities, name, False)]
        if missing:
            joined = ", ".join(missing)
            raise ProviderConfigurationError(
                f"LLM provider '{self.name}'가 필요한 capability를 지원하지 않습니다: {joined}"
            )

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        required = {"structured_output"} if request.output_schema else set()
        self.require(required)
        model_name = self.settings.model_for(request.model_profile)
        model = self.create_chat_model(model=model_name, temperature=0)
        if request.output_schema:
            model = model.with_structured_output(request.output_schema)
        messages = [("system", request.system_prompt)]
        if request.context:
            messages.append(("system", f"Context:\n{json.dumps(request.context, ensure_ascii=False)}"))
        messages.append(("user", request.user_prompt))
        started = time.perf_counter()
        response = await model.ainvoke(messages)
        latency_ms = round((time.perf_counter() - started) * 1000)
        structured = None
        text = ""
        if request.output_schema:
            structured = response.model_dump() if hasattr(response, "model_dump") else response
        else:
            text = str(getattr(response, "content", response))
        usage = getattr(response, "usage_metadata", None) or {}
        metadata = getattr(response, "response_metadata", None) or {}
        return GenerationResult(
            text=text,
            structured_output=structured,
            model=model_name,
            provider=self.name,
            latency_ms=latency_ms,
            usage=usage,
            finish_reason=metadata.get("finish_reason"),
        )


class OpenAIProvider(BaseLangChainProvider):
    name = "openai"
    capabilities = ProviderCapabilities(image_input=True)

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def create_chat_model(
        self,
        *,
        model: str,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model,
            "api_key": api_key or self.settings.api_key or os.getenv("OPENAI_API_KEY"),
            "timeout": self.settings.timeout_seconds,
        }
        if temperature is not None and "gpt-5" not in model:
            kwargs["temperature"] = temperature
        if max_retries is not None:
            kwargs["max_retries"] = max_retries
        return ChatOpenAI(**kwargs)


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai_compatible"

    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        if not settings.base_url:
            raise ProviderConfigurationError(
                "LLM_PROVIDER=openai_compatible일 때 LLM_BASE_URL이 필요합니다."
            )
        self.capabilities = ProviderCapabilities(
            structured_output=settings.local_supports_structured_output,
            tool_calling=settings.local_supports_tool_calling,
            streaming=True,
            image_input=settings.local_supports_image_input,
            usage_metadata=True,
        )

    def create_chat_model(self, **kwargs):
        from langchain_openai import ChatOpenAI

        params = {
            "model": kwargs["model"],
            "api_key": kwargs.get("api_key") or self.settings.api_key or "local",
            "base_url": self.settings.base_url,
            "timeout": self.settings.timeout_seconds,
        }
        temperature = kwargs.get("temperature")
        if temperature is not None:
            params["temperature"] = temperature
        if kwargs.get("max_retries") is not None:
            params["max_retries"] = kwargs["max_retries"]
        return ChatOpenAI(**params)


class GoogleProvider(BaseLangChainProvider):
    name = "google"
    capabilities = ProviderCapabilities(image_input=True)

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def create_chat_model(self, *, model: str, temperature=None, max_retries=None, api_key=None):
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": model}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_retries is not None:
            kwargs["max_retries"] = max_retries
        key = api_key or os.getenv("GEMINI_API_KEY")
        if key:
            kwargs["google_api_key"] = key
        return ChatGoogleGenerativeAI(**kwargs)


class AnthropicProvider(BaseLangChainProvider):
    name = "anthropic"
    capabilities = ProviderCapabilities(image_input=True)

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def create_chat_model(self, *, model: str, temperature=None, max_retries=None, api_key=None):
        from langchain_anthropic import ChatAnthropic

        kwargs = {"model_name": model}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_retries is not None:
            kwargs["max_retries"] = max_retries
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if key:
            kwargs["api_key"] = key
        return ChatAnthropic(**kwargs)


class MockChatModel(BaseChatModel):
    """Small Runnable-compatible model for offline application tests."""

    response: str = "{}"

    @property
    def _llm_type(self) -> str:
        return "workflow-mock"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.response))])

    def bind_tools(self, *args, **kwargs):
        return self

    def with_structured_output(self, schema: Any, **kwargs):
        from langchain_core.runnables import RunnableLambda

        def parse(_input):
            import json

            value = json.loads(self.response)
            if hasattr(schema, "model_validate"):
                return schema.model_validate(value)
            return value

        return RunnableLambda(parse)


class MockProvider(BaseLangChainProvider):
    name = "mock"
    capabilities = ProviderCapabilities(image_input=False)

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def create_chat_model(self, *, model: str, temperature=None, max_retries=None, api_key=None):
        return MockChatModel(response=os.getenv("LLM_MOCK_RESPONSE", "{}"))
