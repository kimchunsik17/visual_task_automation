"""시연 노드 비가시화(hidden_nodes)의 게이트·카탈로그 제거·정의/갤러리 필터 검사."""

from __future__ import annotations

import re

import hidden_nodes
import meta_agent
import node_definition


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HIDDEN_NODE_TYPES", raising=False)
    assert hidden_nodes.hidden_types() == set()
    catalog = meta_agent.NODE_CATALOG
    assert hidden_nodes.strip_catalog(catalog) == catalog          # 문자열 무변경 — 스냅샷과 동일
    payload = node_definition.definitions_payload()
    assert hidden_nodes.filter_definitions(payload) == payload


def test_strip_catalog_removes_entry_and_fixes_count(monkeypatch):
    monkeypatch.setenv("HIDDEN_NODE_TYPES", "databaseNode, posterGeneratorNode")
    full = meta_agent.NODE_CATALOG   # 테스트 환경은 env 없이 로드돼 전체 카탈로그다
    before = int(re.search(r"이 (\d+)종만 사용한다", full).group(1))

    stripped = hidden_nodes.strip_catalog(full)
    assert re.search(r"(?m)^- databaseNode\s*:", stripped) is None
    assert re.search(r"(?m)^- posterGeneratorNode\s*:", stripped) is None
    # 이웃 항목과 뒤쪽 섹션은 살아 있다 — 블록 제거가 과하게 먹으면 생성 규칙이 통째로 사라진다.
    assert re.search(r"(?m)^- llmNode\s*:", stripped) is not None
    assert "[생성 원칙]" in stripped
    after = int(re.search(r"이 (\d+)종만 사용한다", stripped).group(1))
    assert after == before - 2

    # 항목 수 선언과 실제 항목 수가 계속 일치한다 (test_node_definitions 의 불변식과 동일)
    section = stripped[:stripped.index("\n[생성 원칙]")]
    assert after == len(re.findall(r"(?m)^- \w+\s*:", section))


def test_filter_definitions_and_templates(monkeypatch):
    monkeypatch.setenv("HIDDEN_NODE_TYPES", "formatNode")
    payload = hidden_nodes.filter_definitions(node_definition.definitions_payload())
    assert "formatNode" not in payload and "llmNode" in payload

    class Row:
        def __init__(self, node_types):
            self.node_types = node_types

    rows = [Row(["startNode", "formatNode"]), Row(["startNode", "llmNode"]), Row(None)]
    kept = hidden_nodes.filter_templates(rows)
    assert len(kept) == 2 and all("formatNode" not in (r.node_types or []) for r in kept)


def test_warn_unknown_never_raises(monkeypatch, capsys):
    monkeypatch.setenv("HIDDEN_NODE_TYPES", "notARealNode, llmNode")
    hidden_nodes.warn_unknown(["llmNode", "startNode"])
    out = capsys.readouterr().out
    assert "notARealNode" in out and "llmNode" in out
