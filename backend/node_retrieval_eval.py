"""node_retrieval_eval.py — 노드 선별 Recall 오프라인 평가 (ADR-0013, RAG Phase A·B).

evaluation.TEST_CASES의 expected/forbidden 노드 라벨로 hybrid retrieval(node_knowledge)의
후보 품질을 잰다. 생성 LLM은 호출하지 않으므로 기본 실행은 embedding 쿼리 비용(케이스당
1회, 캐시됨)만 든다. LLM selector와의 직접 비교가 필요하면 --with-llm을 붙인다.

출시 게이트(로드맵 §4.7): expected node Recall@10 ≥ 95%가 되기 전에는 hybrid를 기본
selector로 승격하지 않는다. 이 스크립트가 그 게이트의 측정 도구다.

실행:
  ./venv/bin/python node_retrieval_eval.py            # lexical / hybrid 비교
  ./venv/bin/python node_retrieval_eval.py --sync     # 색인 동기화 후 평가
  ./venv/bin/python node_retrieval_eval.py --with-llm # LLM selector까지 비교(LLM 비용 발생)
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import node_knowledge
from evaluation import RESULTS_DIR, TEST_CASES

# 생성 프롬프트에 항상 포함되는 기본형(meta_agent._ALWAYS_INCLUDE_NODE_TYPES와 동일 취지).
# selector가 못 골라도 생성기는 이 노드들을 볼 수 있으므로 recall 계산에서 후보로 인정한다.
ALWAYS_INCLUDED = {"startNode", "outputNode", "promptNode", "llmNode"}


def _graph_cases() -> List[dict]:
    return [case for case in TEST_CASES if case.get("expected_outcome") == "graph"]


def _evaluate_selector(name: str, select: Callable[[str], List[str]]) -> Dict:
    """케이스마다 selector를 돌려 expected 회수율과 forbidden 선택률을 계산한다."""
    rows = []
    for case in _graph_cases():
        started = time.perf_counter()
        selected = list(select(case["prompt"]))
        latency_ms = round((time.perf_counter() - started) * 1000)
        offered = set(selected) | ALWAYS_INCLUDED
        expected = set(case["expected_nodes"])
        forbidden = set(case.get("forbidden_nodes", []))
        missing = sorted(expected - offered)
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "selected_count": len(offered),
            "recall": round((len(expected) - len(missing)) / len(expected), 4) if expected else 1.0,
            "missing": missing,
            "forbidden_selected": sorted(offered & forbidden),
            "latency_ms": latency_ms,
        })
    expected_total = sum(len(case["expected_nodes"]) for case in _graph_cases())
    missing_total = sum(len(row["missing"]) for row in rows)
    forbidden_total = sum(len(case.get("forbidden_nodes", [])) for case in _graph_cases())
    forbidden_selected_total = sum(len(row["forbidden_selected"]) for row in rows)
    latencies = [row["latency_ms"] for row in rows]
    return {
        "selector": name,
        # micro: 전체 expected 노드 중 회수 비율(게이트 지표), macro: 케이스 평균.
        "recall_micro": round((expected_total - missing_total) / expected_total, 4) if expected_total else 1.0,
        "recall_macro": round(statistics.mean(row["recall"] for row in rows), 4) if rows else 1.0,
        "perfect_recall_cases": sum(1 for row in rows if not row["missing"]),
        "case_count": len(rows),
        "forbidden_selected_rate": round(forbidden_selected_total / forbidden_total, 4) if forbidden_total else 0.0,
        "avg_selected_count": round(statistics.mean(row["selected_count"] for row in rows), 1) if rows else 0,
        "latency_ms_p50": round(statistics.median(latencies)) if latencies else 0,
        "latency_ms_max": max(latencies, default=0),
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="노드 선별 Recall 평가")
    parser.add_argument("--k", type=int, default=None, help="vector top-k (기본: NODE_RETRIEVAL_TOP_K 또는 10)")
    parser.add_argument("--sync", action="store_true", help="평가 전에 색인을 동기화한다")
    parser.add_argument("--with-llm", action="store_true", help="LLM selector도 함께 평가한다(LLM 호출 비용 발생)")
    parser.add_argument("--output", help="결과 JSON 저장 경로(기본: evaluation_results/node-retrieval-<ts>.json)")
    args = parser.parse_args()

    if args.sync:
        print(json.dumps(node_knowledge.sync_node_index(), ensure_ascii=False))

    provider = node_knowledge.resolve_embedding_provider()
    reports = [
        _evaluate_selector("lexical-only", lambda prompt: node_knowledge.lexical_candidates(prompt)),
        _evaluate_selector(
            "hybrid",
            lambda prompt: node_knowledge.hybrid_select_node_types(prompt, k=args.k, provider=provider)["selected_types"],
        ),
    ]
    if args.with_llm:
        from meta_agent import select_relevant_node_types

        reports.append(_evaluate_selector("llm", select_relevant_node_types))

    k = args.k or node_knowledge.retrieval_top_k()
    payload = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "top_k": k,
        "embedding_model": provider.model_id if provider else None,
        "always_included": sorted(ALWAYS_INCLUDED),
        "reports": reports,
    }

    print(f"\n== 노드 선별 Recall 평가 (top-k={k}, embedding={payload['embedding_model'] or '없음(lexical 폴백)'}) ==")
    header = f"{'selector':<14} {'recall@k':>9} {'macro':>7} {'완전회수':>7} {'금지선택':>7} {'평균후보':>7} {'p50 ms':>7}"
    print(header)
    for report in reports:
        print(
            f"{report['selector']:<14} {report['recall_micro']:>9.1%} {report['recall_macro']:>7.1%} "
            f"{report['perfect_recall_cases']:>4}/{report['case_count']:<2} "
            f"{report['forbidden_selected_rate']:>7.1%} {report['avg_selected_count']:>7} {report['latency_ms_p50']:>7}"
        )
    for report in reports:
        gaps = [(row["id"], row["missing"]) for row in report["cases"] if row["missing"]]
        if gaps:
            print(f"\n[{report['selector']}] 누락 케이스:")
            for case_id, missing in gaps:
                print(f"  #{case_id}: {', '.join(missing)}")

    output = Path(args.output) if args.output else (
        RESULTS_DIR / f"node-retrieval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {output}")


if __name__ == "__main__":
    main()
