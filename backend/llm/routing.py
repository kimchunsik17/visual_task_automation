from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import deque
from typing import Any, Optional

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict


TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_HIGH_RISK_KEYWORDS = (
    "결제", "송금", "구매", "환불", "삭제", "게시", "배포", "payment", "transfer",
    "purchase", "refund", "delete", "publish", "deploy",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


def _clamp_percentage(value: Any, default: int = 100) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


class RoutingMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.started_at = time.time()
            self.local_attempts = 0
            self.local_successes = 0
            self.hosted_attempts = 0
            self.hosted_successes = 0
            self.fallback_attempts = 0
            self.fallback_successes = 0
            self.forced_hosted = 0
            self.errors = 0
            self.latencies_ms = deque(maxlen=500)

    def record(self, route: str, *, success: bool, latency_ms: int, fallback: bool = False) -> None:
        with self._lock:
            if route == "local":
                self.local_attempts += 1
                self.local_successes += int(success)
            else:
                self.hosted_attempts += 1
                self.hosted_successes += int(success)
            if fallback:
                self.fallback_attempts += 1
                self.fallback_successes += int(success)
            if not success:
                self.errors += 1
            self.latencies_ms.append(max(0, int(latency_ms)))

    def record_forced_hosted(self) -> None:
        with self._lock:
            self.forced_hosted += 1

    def snapshot(self) -> dict:
        with self._lock:
            latencies = sorted(self.latencies_ms)

            def percentile(fraction: float) -> int:
                if not latencies:
                    return 0
                index = min(len(latencies) - 1, round((len(latencies) - 1) * fraction))
                return latencies[index]

            return {
                "started_at_epoch": self.started_at,
                "local_attempts": self.local_attempts,
                "local_successes": self.local_successes,
                "hosted_attempts": self.hosted_attempts,
                "hosted_successes": self.hosted_successes,
                "fallback_attempts": self.fallback_attempts,
                "fallback_successes": self.fallback_successes,
                "fallback_rate": round(
                    self.fallback_attempts / max(1, self.local_attempts) * 100, 2
                ),
                "forced_hosted": self.forced_hosted,
                "errors": self.errors,
                "p50_latency_ms": percentile(0.5),
                "p95_latency_ms": percentile(0.95),
                "sample_count": len(latencies),
            }


routing_metrics = RoutingMetrics()


def _last_user_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        role = str(value.get("role") or "").lower()
        if role in {"user", "human"}:
            return str(value.get("content") or "")
        for key in ("messages", "input"):
            if key in value:
                found = _last_user_text(value[key])
                if found:
                    return found
        return ""
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            if isinstance(item, BaseMessage):
                if item.type == "human":
                    return str(item.content)
            elif isinstance(item, tuple) and len(item) >= 2 and str(item[0]).lower() in {"user", "human"}:
                return str(item[1])
            elif isinstance(item, dict) and str(item.get("role") or "").lower() in {"user", "human"}:
                return str(item.get("content") or "")
        return ""
    return ""


def is_high_risk_input(value: Any) -> bool:
    if not _env_bool("LLM_HIGH_RISK_FORCE_HOSTED", True):
        return False
    configured = os.getenv("LLM_HIGH_RISK_KEYWORDS", "").strip()
    keywords = tuple(part.strip().lower() for part in configured.split(",") if part.strip())
    keywords = keywords or DEFAULT_HIGH_RISK_KEYWORDS
    text = _last_user_text(value).lower()
    return any(keyword in text for keyword in keywords)


def _use_local_for_input(value: Any, percentage: int) -> bool:
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    text = _last_user_text(value) or repr(value)
    bucket = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < percentage


class HybridRunnable(Runnable):
    def __init__(self, primary: Any, fallback: Any, local_percentage: int = 100):
        self.primary = primary
        self.fallback = fallback
        self.local_percentage = _clamp_percentage(local_percentage)

    def _target(self, value: Any) -> tuple[Any, str]:
        if is_high_risk_input(value):
            routing_metrics.record_forced_hosted()
            return self.fallback, "hosted"
        if _use_local_for_input(value, self.local_percentage):
            return self.primary, "local"
        return self.fallback, "hosted"

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs):
        target, route = self._target(input)
        started = time.perf_counter()
        try:
            result = target.invoke(input, config=config, **kwargs)
            routing_metrics.record(route, success=True, latency_ms=(time.perf_counter() - started) * 1000)
            return result
        except Exception:
            routing_metrics.record(route, success=False, latency_ms=(time.perf_counter() - started) * 1000)
            if route != "local":
                raise
        started = time.perf_counter()
        try:
            result = self.fallback.invoke(input, config=config, **kwargs)
            routing_metrics.record(
                "hosted", success=True, latency_ms=(time.perf_counter() - started) * 1000, fallback=True,
            )
            return result
        except Exception:
            routing_metrics.record(
                "hosted", success=False, latency_ms=(time.perf_counter() - started) * 1000, fallback=True,
            )
            raise

    async def ainvoke(self, input: Any, config: Optional[dict] = None, **kwargs):
        target, route = self._target(input)
        started = time.perf_counter()
        try:
            result = await target.ainvoke(input, config=config, **kwargs)
            routing_metrics.record(route, success=True, latency_ms=(time.perf_counter() - started) * 1000)
            return result
        except Exception:
            routing_metrics.record(route, success=False, latency_ms=(time.perf_counter() - started) * 1000)
            if route != "local":
                raise
        started = time.perf_counter()
        try:
            result = await self.fallback.ainvoke(input, config=config, **kwargs)
            routing_metrics.record(
                "hosted", success=True, latency_ms=(time.perf_counter() - started) * 1000, fallback=True,
            )
            return result
        except Exception:
            routing_metrics.record(
                "hosted", success=False, latency_ms=(time.perf_counter() - started) * 1000, fallback=True,
            )
            raise

    def bind_tools(self, *args, **kwargs):
        return HybridRunnable(
            self.primary.bind_tools(*args, **kwargs),
            self.fallback.bind_tools(*args, **kwargs),
            self.local_percentage,
        )

    def with_structured_output(self, *args, **kwargs):
        return HybridRunnable(
            self.primary.with_structured_output(*args, **kwargs),
            self.fallback.with_structured_output(*args, **kwargs),
            self.local_percentage,
        )


class HybridChatModel(BaseChatModel):
    primary: Any
    fallback: Any
    local_percentage: int = 100

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "hybrid-local-first"

    def _runner(self) -> HybridRunnable:
        return HybridRunnable(self.primary, self.fallback, self.local_percentage)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self._runner().invoke(messages, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = await self._runner().ainvoke(messages, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, *args, **kwargs):
        return self._runner().bind_tools(*args, **kwargs)

    def with_structured_output(self, *args, **kwargs):
        return self._runner().with_structured_output(*args, **kwargs)


def local_endpoint_settings() -> dict:
    base_url = os.getenv("LLM_LOCAL_BASE_URL", "").strip()
    if not base_url and os.getenv("LLM_PROVIDER", "").strip().lower() in {"local", "openai_compatible"}:
        base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_LOCAL_MODEL_BALANCED", "").strip()
    if not model:
        model = os.getenv("LLM_MODEL_BALANCED", "").strip()
    return {
        "configured": bool(base_url),
        "base_url": base_url,
        "model": model,
    }


def probe_local_provider(timeout_seconds: float = 3.0) -> dict:
    settings = local_endpoint_settings()
    if not settings["configured"]:
        return {**settings, "healthy": False, "error": "LLM_LOCAL_BASE_URL이 설정되지 않았습니다."}
    url = settings["base_url"].rstrip("/") + "/models"
    headers = {}
    api_key = os.getenv("LLM_LOCAL_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.perf_counter()
    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        models = [str(item.get("id")) for item in payload.get("data", []) if item.get("id")]
        return {
            **settings,
            "healthy": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "available_models": models,
            "model_available": not settings["model"] or settings["model"] in models,
        }
    except Exception as exc:
        return {
            **settings,
            "healthy": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def routing_config_snapshot() -> dict:
    return {
        "mode": os.getenv("LLM_ROUTING_MODE", "provider").strip().lower(),
        "local_traffic_percent": _clamp_percentage(os.getenv("LLM_LOCAL_TRAFFIC_PERCENT", "100")),
        "fallback_provider": os.getenv("LLM_FALLBACK_PROVIDER", "openai").strip().lower(),
        "high_risk_force_hosted": _env_bool("LLM_HIGH_RISK_FORCE_HOSTED", True),
        **local_endpoint_settings(),
    }
