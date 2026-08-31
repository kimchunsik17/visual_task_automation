"""binding_stabilization_eval.py — 필드 데이터 바인딩 안정화 측정 도구 (ADR-0026).

계획: `Documents/plans/DATA_FLOW_SEPARATION_PLAN.md` §안정화 남은 작업.

2026-08-31 안정화 1차에서 쓴 측정을 그대로 재실행할 수 있게 모아 둔 것이다. 네 모드 모두
**생성 LLM 을 호출하므로 비용이 든다** — 1차 측정 당시 소요는 아래 각 모드 설명에 적어 둔다.

실행:
  ./venv/bin/python binding_stabilization_eval.py --self-test
      LLM 없이 판정 로직만 검사한다(경로 환각 분류기). 먼저 이걸 돌려 스크립트가 살아 있는지 본다.

  ./venv/bin/python binding_stabilization_eval.py --ab
      33케이스 전체를 [데이터 바인딩] 가이드 유무로 두 번 돌린다(캐시 끔).
      1차 측정: 각 33케이스 ≈ 11분, 입력 토큰 약 75만 × 2.
      게이트: 통과 수·평균 점수가 이전 이하로 내려가지 않을 것.
      1차 결과(2026-08-31): 통과 22→24, 평균 92.6→93.5, intent 90.5→92.6, 입력 토큰 +2.7%.

  ./venv/bin/python binding_stabilization_eval.py --repeat 31,32,33 --times 3
      특정 케이스를 현재 프롬프트로 반복한다. **1회 결과로는 잡음과 회귀가 구분되지 않는다** —
      1차에서 case1·8 이 회귀로 보였다가 3회 만점으로 잡음임이 드러났다. 최소 3회.
      1차 결과: case31 2/3, case32 2/3, case33 2~3/3. 목표는 3/3.

  ./venv/bin/python binding_stabilization_eval.py --selection 31,32,33 --times 3
      노드 **선별** 단계만 본다(생성보다 훨씬 싸다 — 케이스당 LLM 1회).
      1차에서 case31 의 formatNode 누락 원인이 여기였다(3/3 선별 실패 → 카탈로그에 항목 없음
      → 설명을 고쳐도 프롬프트에 안 들어감). apply_selection_augmentation 이 그 보정이다.

  ./venv/bin/python binding_stabilization_eval.py --path-hallucination
      **아직 측정하지 않은 항목.** 가이드는 "출력 형식이 문서화된 노드이거나 사용자가 키 이름을
      말한 경우에만 path 를 쓰고, 아니면 빈 문자열로 둬라"고 지시한다. 지켜지는지 잰다.
      키 이름을 말하지 않은 요청에서 path 가 붙으면 그건 모델이 지어낸 것이고, 실행 시
      BINDING_PATH_MISSING 으로 그 자리에서 멈춘다 — 이 기능의 가장 아픈 실패 방식이다.
      게이트(제안): 환각 경로 0건. 1건이라도 나오면 가이드 문구를 강화하고 다시 잰다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import evaluation
import meta_agent
import node_bindings

# 키 이름을 **말하지 않은** 요청 — path 를 쓰면 지어낸 것이다(출력 형식이 문서화된 소스는 예외).
PATH_PROBE_PROMPTS = [
    "웹훅으로 주문이 들어오면 주문한 사람에게 확인 메일을 보내줘.",
    "웹훅으로 문의가 접수되면 담당자 슬랙 채널로 알려줘.",
    "웹훅으로 배송 요청을 받아서 요청자에게 안내 메일을 보내줘.",
]

# 대조군 — 요청이 키 이름을 알려주므로 path 를 쓰는 것이 옳다.
PATH_CONTROL_PROMPTS = [
    "웹훅으로 문의가 들어오면 문의한 사람 이메일로 접수 확인 메일 보내줘. "
    "본문에 email, name 키가 들어와.",
]


def classify_binding_paths(prompt: str, graph: Dict[str, Any]) -> Dict[str, List[str]]:
    """생성된 그래프의 바인딩 경로를 근거 있는 것 / 지어낸 것으로 나눈다.

    가이드가 허용하는 근거는 둘뿐이다:
      1. 소스 노드의 출력 형식이 카탈로그에 문서화돼 있다(PATH_DOCUMENTED_SOURCES).
      2. 사용자가 요청에서 그 키 이름을 직접 말했다.
    """
    by_id = {str(n.get("id")): n for n in graph.get("nodes") or []}
    lowered = prompt.lower()
    grounded: List[str] = []
    invented: List[str] = []
    empty: List[str] = []
    for node in graph.get("nodes") or []:
        for field, spec in ((node.get("data") or {}).get("bindings") or {}).items():
            if not isinstance(spec, dict):
                continue
            path = str(spec.get("path") or "")
            label = f'{node.get("type")}.{field} ← {spec.get("source")}:{path or "(전체)"}'
            if not path:
                empty.append(label)
                continue
            source_type = str((by_id.get(str(spec.get("source"))) or {}).get("type") or "")
            if source_type in node_bindings.PATH_DOCUMENTED_SOURCES:
                grounded.append(label)
                continue
            # 경로의 마지막 토큰 하나라도 요청에 등장하면 사용자가 말한 키로 본다.
            tokens = [t for t in path.replace("[", ".").replace("]", ".").split(".") if t]
            if any(token.lower() in lowered for token in tokens):
                grounded.append(label)
            else:
                invented.append(label)
    return {"grounded": grounded, "invented": invented, "empty": empty}


def _strip_binding_guide() -> None:
    """[데이터 바인딩] 블록과 바인딩 few-shot 예시를 프롬프트에서 뺀다(A/B 의 '이전' 조건)."""
    block = node_bindings.BINDING_CATALOG
    for name in ("SYSTEM", "MEDIUM_SYSTEM", "PRECISE_SYSTEM", "AGENT_SYSTEM_PROMPT"):
        setattr(meta_agent, name, getattr(meta_agent, name).replace(block, ""))
    for name in ("FEWSHOT_FAST", "FEWSHOT_PRECISE"):
        text = getattr(meta_agent, name)
        marker = '[예시19] 요청:'
        if marker in text:
            setattr(meta_agent, name, text[:text.index(marker)])


async def _run_suite(label: str, selected_ids: Optional[List[str]], profile: Optional[str]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    summary: Optional[Dict[str, Any]] = None
    async for chunk in evaluation.run_evaluation_suite(
            selected_ids, profile=profile, use_cache=False, max_total_tokens=5_000_000):
        payload = json.loads(chunk[len("data: "):])
        if payload.get("type") == "progress":
            row = payload["result"]
            rows.append(row)
            print(f'  [{label}] {payload["current"]}/{payload["total"]} case{row["id"]}'
                  f'({row["category"]}) score={row["score"]} passed={row["passed"]} '
                  f'nodes={",".join(row.get("generated_nodes") or [])[:70]}', flush=True)
        elif payload.get("type") == "complete":
            summary = payload["summary"]
        elif payload.get("type") == "error":
            print(f'  [{label}] 오류: {payload["message"]}', flush=True)
    return {"summary": summary, "results": rows}


async def run_ab() -> None:
    print("=== 이후(현재 프롬프트) ===", flush=True)
    after = await _run_suite("after", None, "full")
    print("=== 이전(가이드·예시 제거) ===", flush=True)
    _strip_binding_guide()
    before = await _run_suite("before", None, "full")

    keys = ("total_tests", "pass_count", "average_score", "structural_pass_rate",
            "compile_pass_rate", "dry_run_pass_rate", "intent_coverage")
    print("\n=== 요약 ===", flush=True)
    for key in keys:
        print(f'  {key:22} 이전 {before["summary"].get(key)} → 이후 {after["summary"].get(key)}')
    print(f'  token_usage 이전 {before["summary"].get("token_usage")} '
          f'→ 이후 {after["summary"].get("token_usage")}')

    b = {r["id"]: r for r in before["results"]}
    a = {r["id"]: r for r in after["results"]}
    print("\n=== 점수 변화(차이 있는 것만) — 회귀로 보이면 --repeat 로 3회 확인할 것 ===")
    for case_id in sorted(set(b) & set(a)):
        if b[case_id]["score"] != a[case_id]["score"]:
            mark = "↑" if a[case_id]["score"] > b[case_id]["score"] else "↓"
            print(f'  {mark} case{case_id}({a[case_id]["category"]}): '
                  f'{b[case_id]["score"]} → {a[case_id]["score"]}')


async def run_repeat(ids: List[int], times: int) -> None:
    tally: Dict[int, List[int]] = {i: [] for i in ids}
    for rep in range(1, times + 1):
        run = await _run_suite(f"{rep}회", [str(i) for i in ids], None)
        for row in run["results"]:
            tally[row["id"]].append(row["score"])
    print("\n=== 반복 요약 ===")
    for case_id in ids:
        scores = tally[case_id]
        if not scores:
            continue
        print(f'  case{case_id}: 점수 {scores} · 평균 {sum(scores) / len(scores):.1f} · '
              f'만점 {sum(1 for s in scores if s == 100)}/{len(scores)}')


def run_selection(ids: List[int], times: int) -> None:
    watched = set(node_bindings.PATH_DOCUMENTED_SOURCES) | {
        "formatNode", "hwpxDocumentNode", "posterGeneratorNode",
        "templateAnalyzerNode", "fileModifierNode",
    }
    for case_id in ids:
        prompt = next(c for c in evaluation.TEST_CASES if c["id"] == case_id)["prompt"]
        print(f'--- case{case_id}')
        for attempt in range(times):
            selected, error, _usage, _latency = meta_agent._llm_select_node_types(prompt)
            picked = [t for t in (selected or []) if t in watched]
            augmented = meta_agent.apply_selection_augmentation(selected or [])
            added = [t for t in augmented if t not in (selected or [])]
            print(f'  {attempt + 1}회 선별 {picked or "없음"} · 보강 추가 {added or "없음"}'
                  f'{" 오류:" + str(error) if error else ""}')


async def run_path_hallucination(times: int) -> None:
    total_invented = 0
    for label, prompts in (("탐침(키 미언급)", PATH_PROBE_PROMPTS), ("대조군(키 언급)", PATH_CONTROL_PROMPTS)):
        print(f'=== {label}')
        for prompt in prompts:
            for attempt in range(times):
                graph = meta_agent.generate_flow(prompt).model_dump()
                verdict = classify_binding_paths(prompt, graph)
                total_invented += len(verdict["invented"])
                print(f'  {attempt + 1}회 "{prompt[:34]}…"')
                print(f'      노드 {",".join(n["type"] for n in graph["nodes"])}')
                print(f'      근거 있는 경로 {verdict["grounded"] or "없음"}')
                print(f'      빈 경로(출력 전체) {verdict["empty"] or "없음"}')
                print(f'      **지어낸 경로** {verdict["invented"] or "없음"}')
    print(f'\n=== 환각 경로 합계 {total_invented}건 (게이트: 0건)')


def self_test() -> None:
    """LLM 없이 분류기만 검사한다."""
    prompt = "웹훅으로 주문이 들어오면 주문한 사람에게 메일 보내줘."
    graph = {"nodes": [
        {"id": "n1", "type": "webhookNode", "data": {}},
        {"id": "n2", "type": "emailNode", "data": {
            "bindings": {"toEmail": {"source": "n1", "path": "customer.email"}}}},
    ]}
    verdict = classify_binding_paths(prompt, graph)
    assert verdict["invented"] and not verdict["grounded"], verdict

    # 요청이 키를 말했으면 근거 있는 경로다
    named = "웹훅으로 문의가 오면 email 키의 주소로 메일 보내줘."
    verdict = classify_binding_paths(named, graph)
    assert not verdict["invented"], verdict

    # 출력 형식이 문서화된 소스는 요청에 키가 없어도 허용된다
    documented = {"nodes": [
        {"id": "n1", "type": "naverSearchNode", "data": {}},
        {"id": "n2", "type": "webCrawlerNode", "data": {
            "bindings": {"url": {"source": "n1", "path": "items[0].link"}}}},
    ]}
    verdict = classify_binding_paths("네이버에서 찾아서 첫 글 크롤링해줘", documented)
    assert verdict["grounded"] and not verdict["invented"], verdict

    # 빈 경로는 어느 쪽도 아니다(가이드가 권하는 안전한 기본값)
    empty = {"nodes": [
        {"id": "n1", "type": "webhookNode", "data": {}},
        {"id": "n2", "type": "emailNode", "data": {
            "bindings": {"toEmail": {"source": "n1", "path": ""}}}},
    ]}
    verdict = classify_binding_paths(prompt, empty)
    assert verdict["empty"] and not verdict["invented"] and not verdict["grounded"], verdict
    print("self-test 통과 — 분류기 정상")


def main() -> None:
    parser = argparse.ArgumentParser(description="필드 데이터 바인딩 안정화 측정 (ADR-0026)")
    parser.add_argument("--self-test", action="store_true", help="LLM 없이 판정 로직만 검사")
    parser.add_argument("--ab", action="store_true", help="33케이스 전체 A/B (가이드 유무)")
    parser.add_argument("--repeat", help="반복 측정할 케이스 id 목록 (예: 31,32,33)")
    parser.add_argument("--selection", help="노드 선별만 볼 케이스 id 목록")
    parser.add_argument("--path-hallucination", action="store_true", help="경로 환각 측정")
    parser.add_argument("--times", type=int, default=3, help="반복 횟수 (기본 3)")
    args = parser.parse_args()

    os.environ.setdefault("EVALUATION_CACHE_ENABLED", "false")

    if args.self_test:
        self_test()
        return
    if args.ab:
        asyncio.run(run_ab())
        return
    if args.repeat:
        asyncio.run(run_repeat([int(x) for x in args.repeat.split(",") if x.strip()], args.times))
        return
    if args.selection:
        run_selection([int(x) for x in args.selection.split(",") if x.strip()], args.times)
        return
    if args.path_hallucination:
        asyncio.run(run_path_hallucination(args.times))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
