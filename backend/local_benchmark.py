from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import evaluation
from llm.routing import probe_local_provider


@contextmanager
def _temporary_environment(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _gpu_memory_mib() -> list[int]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return [int(line.strip()) for line in output.splitlines() if line.strip()]
    except Exception:
        return []


async def _consume_sse(stream: AsyncIterator[str]) -> dict:
    completed = None
    errors = []
    async for event in stream:
        line = event.strip()
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[5:].strip())
        if payload.get("type") == "complete":
            completed = payload
        elif payload.get("type") == "error":
            errors.append(payload.get("message"))
    if errors:
        return {"error": "; ".join(str(item) for item in errors)}
    return completed or {"error": "평가 완료 이벤트를 받지 못했습니다."}


async def benchmark_models(
    models: list[str],
    *,
    base_url: str,
    profile: str = "smoke",
    selected_ids: list[str] | None = None,
) -> dict:
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "profile": profile,
        "models": [],
    }
    for model in models:
        env = {
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": base_url,
            "LLM_LOCAL_BASE_URL": base_url,
            "LLM_ROUTING_MODE": "local",
            "LLM_MODEL_FAST": model,
            "LLM_MODEL_BALANCED": model,
            "LLM_MODEL_QUALITY": model,
            "LLM_LOCAL_MODEL_FAST": model,
            "LLM_LOCAL_MODEL_BALANCED": model,
            "LLM_LOCAL_MODEL_QUALITY": model,
        }
        with _temporary_environment(env):
            health = await asyncio.to_thread(probe_local_provider, 5.0)
            before_vram = _gpu_memory_mib()
            if health.get("healthy"):
                result = await _consume_sse(evaluation.run_evaluation_suite(
                    selected_ids,
                    profile=profile,
                    use_cache=False,
                    max_total_tokens=int(os.getenv("LOCAL_BENCHMARK_MAX_TOKENS", "100000")),
                ))
            else:
                result = {"error": health.get("error") or "로컬 provider health check 실패"}
            after_vram = _gpu_memory_mib()
        report["models"].append({
            "model": model,
            "health": health,
            "gpu_memory_before_mib": before_vram,
            "gpu_memory_after_mib": after_vram,
            "summary": result.get("summary"),
            "error": result.get("error"),
        })
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI-compatible 로컬 모델 품질 벤치마크")
    parser.add_argument("--base-url", default=os.getenv("LLM_LOCAL_BASE_URL", ""))
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--profile", choices=("smoke", "targeted", "full"), default="smoke")
    parser.add_argument("--ids", default="")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "evaluation_results" / "local-model-benchmark.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    models = args.models or [
        item.strip() for item in os.getenv("LOCAL_BENCHMARK_MODELS", "").split(",") if item.strip()
    ]
    if not args.base_url or not models:
        raise SystemExit("--base-url과 --models(또는 LOCAL_BENCHMARK_MODELS)가 필요합니다.")
    selected_ids = [item.strip() for item in args.ids.split(",") if item.strip()] or None
    report = asyncio.run(benchmark_models(
        models, base_url=args.base_url, profile=args.profile, selected_ids=selected_ids,
    ))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
