from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    base_url: Optional[str]
    api_key: Optional[str]
    timeout_seconds: float
    models: dict[str, str]
    local_supports_structured_output: bool
    local_supports_tool_calling: bool
    local_supports_image_input: bool

    def model_for(self, profile: str) -> str:
        normalized = profile.strip().lower()
        aliases = {"low": "fast", "medium": "balanced", "high": "quality"}
        key = aliases.get(normalized, normalized)
        if key not in self.models:
            raise ValueError(f"지원하지 않는 LLM model profile입니다: {profile}")
        return self.models[key]


def load_llm_settings() -> LLMSettings:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    api_key = os.getenv("LLM_API_KEY", "").strip() or None
    if provider == "openai" and not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    return LLMSettings(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        models={
            "fast": os.getenv("LLM_MODEL_FAST", "gpt-5.4-mini"),
            "balanced": os.getenv("LLM_MODEL_BALANCED", "gpt-5.6-terra"),
            "quality": os.getenv("LLM_MODEL_QUALITY", "gpt-5.6-sol"),
            "evaluation": os.getenv("LLM_MODEL_EVALUATION", "gpt-5.4-mini"),
            "title": os.getenv("LLM_MODEL_TITLE", "gpt-5.4-mini"),
        },
        local_supports_structured_output=_env_bool("LLM_LOCAL_SUPPORTS_STRUCTURED_OUTPUT", True),
        local_supports_tool_calling=_env_bool("LLM_LOCAL_SUPPORTS_TOOL_CALLING", True),
        local_supports_image_input=_env_bool("LLM_LOCAL_SUPPORTS_IMAGE_INPUT", False),
    )
