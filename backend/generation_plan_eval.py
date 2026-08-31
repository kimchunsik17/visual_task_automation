"""generation_plan_eval.py — adaptive candidate 실험 비교 (우선 백로그 10번, §4.4 배포 게이트).

같은 평가 케이스를 단일 후보(기존)와 adaptive 후보(실험) 두 모드로 돌려 structural/dry-run
통과율·지연을 비교한다. 캐시는 끈다(두 모드가 같은 캐시를 읽으면 비교가 무의미하다).

실행:
  ./venv/bin/python generation_plan_eval.py                  # smoke 3케이스
  ./venv/bin/python generation_plan_eval.py --cases 4,26,27  # 지정 케이스
  ./venv/bin/python generation_plan_eval.py --profile full   # 전체 30케이스 (비용 큼)

게이트(§4.4): adaptive가 단일 대비 채택률 또는 dry-run 통과율을 유의미하게 개선하고
accepted workflow당 비용 상한을 지킬 때만 기본값(GENERATION_ADAPTIVE_CANDIDATES=1)으로
전환한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from evaluation import RESULTS_DIR, run_evaluation_suite


async def run_mode(mode: str, selected_ids, profile):
    os.environ["GENERATION_ADAPTIVE_CANDIDATES"] = "1" if mode == "adaptive" else "0"
    summary, results = None, []
    async for event_text in run_evaluation_suite(selected_ids=selected_ids, profile=profile, use_cache=False):
        payload = json.loads(event_text.removeprefix("data: ").strip())
        if payload.get("type") == "complete":
            summary = payload.get("summary")
            results = payload.get("results") or []
        elif payload.get("type") == "error":
            raise RuntimeError(payload.get("message"))
        elif payload.get("type") == "progress":
            row = payload.get("result") or {}
            print(f"  [{mode}] case {row.get('id')}: score={row.get('score')} "
                  f"structural={row.get('structural_passed')} dry_run={row.get('dry_run_passed')}")
    return summary, results


def main() -> None:
    parser = argparse.ArgumentParser(description="GenerationPlan adaptive 후보 비교")
    parser.add_argument("--cases", help="쉼표로 구분한 케이스 id (기본: smoke)")
    parser.add_argument("--profile", default=None, help="smoke | full")
    args = parser.parse_args()
    selected = [int(x) for x in args.cases.split(",")] if args.cases else None

    comparison = {}
    for mode in ("single", "adaptive"):
        print(f"\n== {mode} 모드 ==")
        summary, results = asyncio.run(run_mode(mode, selected, args.profile))
        comparison[mode] = {"summary": summary, "results": results}

    single, adaptive = comparison["single"]["summary"], comparison["adaptive"]["summary"]
    print("\n== 비교 ==")
    keys = ["pass_count", "average_score", "structural_pass_rate", "dry_run_pass_rate",
            "intent_coverage", "average_latency_sec"]
    print(f"{'지표':<24}{'단일':>12}{'adaptive':>12}")
    for key in keys:
        print(f"{key:<24}{str(single.get(key)):>12}{str(adaptive.get(key)):>12}")
    single_tokens = (single.get("token_usage") or {}).get("total_tokens", 0)
    adaptive_tokens = (adaptive.get("token_usage") or {}).get("total_tokens", 0)
    print(f"{'total_tokens(관측)':<24}{single_tokens:>12}{adaptive_tokens:>12}")
    print("(주의: 도구 내부 생성 호출의 토큰은 usage에 완전히 잡히지 않는다 — 후보 수가 비용의 근사 지표다)")

    output = RESULTS_DIR / f"generation-plan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {output}")


if __name__ == "__main__":
    main()
