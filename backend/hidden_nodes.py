"""hidden_nodes.py — 시연 노드 비가시화 (opt-in, 시연 플래그 계획 §비가시화).

미완성 노드를 시연 기간 동안 **보이는 표면에서만** 감춘다. 실행은 막지 않는다 —
숨긴 노드가 이미 놓인 워크플로우·설치된 템플릿은 그대로 돈다(계획 원칙 2).

    HIDDEN_NODE_TYPES=nodeA,nodeB     # 미설정 = 현행과 동일. 제거 = 원상 복구.

가리는 표면 3곳:
  1. 생성 카탈로그 — meta_agent.NODE_CATALOG 조립 직후 strip_catalog() 로 항목 제거
     ("이 N종만 사용한다" 카운트도 함께 고친다). LLM 이 숨긴 노드를 그래프에 넣지 않는다.
  2. 정의 API — /api/node-definitions 응답에서 filter_definitions() 로 제외.
     (/api/features 의 hidden_nodes 목록을 보고 프론트가 팔레트·교체 후보를 필터한다.)
  3. 커뮤니티 갤러리 — 목록/검색에서 숨긴 노드를 쓰는 템플릿을 filter_templates() 로 제외.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List


def hidden_types() -> set:
    return {t.strip() for t in os.getenv("HIDDEN_NODE_TYPES", "").split(",") if t.strip()}


def strip_catalog(catalog: str) -> str:
    """조립된 NODE_CATALOG 에서 숨긴 노드의 항목 블록을 제거하고 종수 선언을 고친다."""
    hidden = hidden_types()
    if not hidden:
        return catalog
    out = catalog
    for node_type in sorted(hidden):
        # 항목 블록 = '- 타입 :' 줄부터 다음 항목(또는 다음 [섹션]) 직전까지.
        out = re.sub(rf"(?ms)^- {re.escape(node_type)}\s*:.*?(?=^- \w+\s*:|^\[)", "", out)
    # "이 N종만 사용한다" 가 실제 항목 수와 어긋나면 LLM 에게 거짓을 말하게 된다.
    boundary = out.find("\n[생성 원칙]")
    section = out[:boundary] if boundary != -1 else out
    count = len(re.findall(r"(?m)^- \w+\s*:", section))
    return re.sub(r"이 \d+종만 사용한다", f"이 {count}종만 사용한다", out, count=1)


def filter_definitions(payload: Dict) -> Dict:
    hidden = hidden_types()
    if not hidden:
        return payload
    return {node_type: defn for node_type, defn in payload.items() if node_type not in hidden}


def filter_templates(rows: Iterable) -> List:
    """숨긴 노드를 쓰는 템플릿을 갤러리 목록에서 뺀다. 이미 설치된 프로젝트는 무관하다."""
    hidden = hidden_types()
    if not hidden:
        return list(rows)
    return [row for row in rows if not (set(row.node_types or []) & hidden)]


def warn_unknown(known_types: Iterable[str]) -> None:
    """오타 방어 — 존재하지 않는 타입이 목록에 있으면 기동 로그로 알린다(막지는 않는다)."""
    unknown = hidden_types() - set(known_types)
    if unknown:
        print(f"[hidden-nodes] 경고: HIDDEN_NODE_TYPES 에 알 수 없는 타입이 있다(오타?): {sorted(unknown)}")
    active = hidden_types() - unknown
    if active:
        print(f"[hidden-nodes] 시연 비가시화 활성: {sorted(active)} — 팔레트·생성 카탈로그·갤러리에서 숨김 (실행은 허용)")
