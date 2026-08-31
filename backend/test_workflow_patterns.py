"""디자인 패턴 정본(workflow_patterns.json)의 정합성 검사.

패턴은 문서와 LLM 생성 프롬프트가 함께 읽으므로, 여기서 어긋나면 두 곳이 동시에
틀린다. 특히 노드 타입 오타는 2026-08-30 의 "카탈로그에는 있는데 출력 스키마가
거부" 사고와 같은 부류라 구조적으로 막는다.
"""

from typing import get_args

import pytest

import meta_agent
import workflow_patterns
from export_node_definitions import PATTERNS_BUNDLE_PATH, render_patterns_bundle

VALID_NODE_TYPES = set(get_args(meta_agent.NodeType))


def test_pattern_ids_are_unique():
    ids = [p["id"] for p in workflow_patterns.PATTERNS]
    assert len(ids) == len(set(ids)), "패턴 id 가 중복됐다"


@pytest.mark.parametrize("pattern", workflow_patterns.PATTERNS, ids=lambda p: p["id"])
def test_pattern_graph_uses_only_valid_node_types(pattern):
    """그래프의 노드 타입은 생성 스키마(NodeType)가 아는 타입이어야 한다 —
    아니면 문서에는 그려지는데 LLM 은 그 타입으로 생성할 수 없는 패턴이 된다."""
    unknown = {n["type"] for n in pattern["graph"]["nodes"]} - VALID_NODE_TYPES
    assert not unknown, f"{pattern['id']} 그래프에 스키마 밖 노드 타입: {unknown}"


@pytest.mark.parametrize("pattern", workflow_patterns.PATTERNS, ids=lambda p: p["id"])
def test_pattern_llm_text_mentions_only_valid_node_types(pattern):
    """llm 필드는 프롬프트에 그대로 들어간다 — 존재하지 않는 노드 타입 이름이
    섞여 있으면 생성 LLM 에게 거짓 목록을 가르치게 된다."""
    import re
    mentioned = set(re.findall(r"\b(\w+Node)\b", pattern["llm"]))
    unknown = mentioned - VALID_NODE_TYPES
    assert not unknown, f"{pattern['id']} llm 문구에 스키마 밖 노드 타입: {unknown}"


@pytest.mark.parametrize("pattern", workflow_patterns.PATTERNS, ids=lambda p: p["id"])
def test_pattern_graph_edges_reference_existing_nodes(pattern):
    node_ids = {n["id"] for n in pattern["graph"]["nodes"]}
    for edge in pattern["graph"]["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids, (
            f"{pattern['id']} 의 엣지 {edge} 가 없는 노드를 가리킨다"
        )


@pytest.mark.parametrize("pattern", workflow_patterns.PATTERNS, ids=lambda p: p["id"])
def test_pattern_graph_starts_with_exactly_one_trigger(pattern):
    """패턴은 생성 규칙의 모범이어야 한다 — 시작 노드 정확히 1개 규칙을 스스로 지킬 것."""
    triggers = [n for n in pattern["graph"]["nodes"] if n["type"] in meta_agent.START_NODE_TYPES]
    assert len(triggers) == 1, f"{pattern['id']} 의 시작 노드가 {len(triggers)}개다"


@pytest.mark.parametrize("pattern", workflow_patterns.PATTERNS, ids=lambda p: p["id"])
def test_pattern_required_fields(pattern):
    for key in ("id", "title", "summary", "when", "cautions", "llm", "graph"):
        assert pattern.get(key), f"{pattern['id']} 에 {key} 가 비었다"


def test_pattern_catalog_is_injected_into_generation_prompts():
    """패턴 블록이 실제 생성 프롬프트에 들어가는지 — 주입 코드가 리팩터링에서
    떨어져 나가면 문서와 생성이 조용히 갈라진다."""
    block = workflow_patterns.PATTERN_CATALOG
    assert block in meta_agent.SYSTEM
    assert block in meta_agent.MEDIUM_SYSTEM
    assert block in meta_agent.PRECISE_SYSTEM
    assert block in meta_agent.AGENT_SYSTEM_PROMPT


def test_pattern_catalog_stays_after_node_catalog():
    """트리밍은 SYSTEM.replace(NODE_CATALOG, trimmed, 1) 방식이라, NODE_CATALOG 가
    원문 그대로 프롬프트 안에 있어야 한다 — 패턴 블록이 그 안에 끼어들면 깨진다."""
    assert meta_agent.NODE_CATALOG in meta_agent.SYSTEM
    trimmed = meta_agent.SYSTEM.replace(meta_agent.NODE_CATALOG, "TRIMMED", 1)
    assert workflow_patterns.PATTERN_CATALOG in trimmed, "트리밍 후에도 패턴 블록은 남아야 한다"


def test_frontend_bundle_is_up_to_date():
    assert PATTERNS_BUNDLE_PATH.exists(), "python backend/export_node_definitions.py 를 실행하라"
    assert PATTERNS_BUNDLE_PATH.read_text(encoding="utf-8") == render_patterns_bundle(), (
        "workflowPatterns.json 번들이 정본과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    )
