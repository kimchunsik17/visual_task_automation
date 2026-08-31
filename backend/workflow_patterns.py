"""workflow_patterns.py — 워크플로우 디자인 패턴 정본 로더.

정본은 저장소 루트 workflow_patterns.json 하나다. 두 곳이 함께 읽는다:

  1. LLM 생성 프롬프트 — meta_agent 의 SYSTEM/MEDIUM/PRECISE/AGENT 프롬프트에
     `PATTERN_CATALOG`([디자인 패턴] 블록)가 NODE_CATALOG 바로 뒤에 붙는다.
     NODE_CATALOG 자체는 건드리지 않으므로 test_node_definitions.py 의
     스냅샷 드리프트 테스트와 무관하다.
  2. 제품 문서(/documents/patterns) — export_node_definitions.py 가
     frontend/src/generated/workflowPatterns.json 으로 내보낸 번들을 읽는다.

패턴을 고치면: 이 JSON 만 고치고 `python backend/export_node_definitions.py` 를
다시 돌린다. llm 필드는 프롬프트에 그대로 들어가므로 노드 타입 이름을 정확히 쓰고
2~3문장으로 압축한다 — test_workflow_patterns.py 가 타입 오타를 잡는다.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERNS_PATH = REPO_ROOT / "workflow_patterns.json"

_data: Dict[str, Any] = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))

PATTERNS: List[Dict[str, Any]] = _data["patterns"]
PATTERNS_BY_ID: Dict[str, Dict[str, Any]] = {p["id"]: p for p in PATTERNS}


def payload() -> Dict[str, Any]:
    """프론트엔드 번들로 내보낼 원문 그대로의 payload."""
    return _data


def pattern_node_types(pattern: Dict[str, Any]) -> List[str]:
    """패턴 그래프에 등장하는 노드 타입(중복 제거, 등장 순서 유지)."""
    seen: List[str] = []
    for node in pattern.get("graph", {}).get("nodes", []):
        if node["type"] not in seen:
            seen.append(node["type"])
    return seen


def render_pattern_catalog() -> str:
    """생성 프롬프트에 붙일 [디자인 패턴] 블록.

    카탈로그 트리밍(build_trimmed_catalog)과 달리 항상 전체를 넣는다 — 패턴은
    타입별 카탈로그 항목보다 훨씬 짧아서(패턴당 2~3줄) 트리밍의 실익이 없고,
    "이 요청이 어느 패턴에 해당하는가"의 판단 자체를 생성 LLM 에게 맡기는 편이
    선별 LLM 의 실수(관련 패턴 누락)보다 안전하다.
    """
    lines = [
        "[디자인 패턴 — 자주 쓰는 검증된 노드 조합. 요청이 아래 상황과 맞으면 해당 골격을 "
        "우선 따르되, 요청에 없는 단계를 패턴에 있다는 이유로 억지로 추가하지는 마라]"
    ]
    for pattern in PATTERNS:
        lines.append(f"- {pattern['title']}: {pattern['llm']}")
    return "\n".join(lines) + "\n"


PATTERN_CATALOG = "\n" + render_pattern_catalog()
