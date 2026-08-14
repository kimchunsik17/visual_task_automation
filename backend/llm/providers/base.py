from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Set

from pydantic import BaseModel, Field


class ProviderCapabilities(BaseModel):
    structured_output: bool = True
    tool_calling: bool = True
    streaming: bool = True
    image_input: bool = False
    usage_metadata: bool = True


class GenerationRequest(BaseModel):
    task_type: str
    system_prompt: str
    user_prompt: str
    context: list[dict] = Field(default_factory=list)
    output_schema: Optional[dict] = None
    model_profile: str = "balanced"


class GenerationResult(BaseModel):
    text: str = ""
    structured_output: Optional[dict] = None
    model: str
    provider: str
    latency_ms: int
    usage: Dict[str, Any] = Field(default_factory=dict)
    finish_reason: Optional[str] = None


class ModelProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def create_chat_model(
        self,
        *,
        model: str,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> Any:
        ...

    def require(self, capabilities: Set[str]) -> None:
        ...

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        ...


class ProviderConfigurationError(RuntimeError):
    pass
