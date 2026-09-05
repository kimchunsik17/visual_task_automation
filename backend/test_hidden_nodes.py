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


def test_filter_definitions(monkeypatch):
    monkeypatch.setenv("HIDDEN_NODE_TYPES", "formatNode")
    payload = hidden_nodes.filter_definitions(node_definition.definitions_payload())
    assert "formatNode" not in payload and "llmNode" in payload


def _sqlite_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import models

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _publish(db, slug, node_types):
    """실제 갤러리 행 모양 — Template → latest TemplateVersion → WorkflowShare.node_types."""
    import models

    share = models.WorkflowShare(owner_type="template", owner_id=0, node_types=node_types,
                                 graph_snapshot={"nodes": [], "edges": []})
    db.add(share); db.flush()
    template = models.Template(slug=slug, title=slug, status="published")
    db.add(template); db.flush()
    version = models.TemplateVersion(template_id=template.id, version="1.0.0", workflow_share_id=share.id)
    db.add(version); db.flush()
    template.latest_version_id = version.id
    db.commit()
    return template


def test_filter_templates_reads_node_types_from_latest_version(monkeypatch):
    """2026-09-05 운영 회귀: Template 에는 node_types 열이 없다(WorkflowShare 에 있다). 가짜 행으로
    통과하던 테스트가 놓쳤으므로 실제 모델 행과 실제 갤러리 경로(list_templates)로 확인한다."""
    import models
    import community_templates

    db = _sqlite_session()
    _publish(db, "with-juso", ["startNode", "jusoNode", "llmNode"])
    _publish(db, "without-juso", ["startNode", "llmNode"])
    db.add(models.Template(slug="no-version", title="no-version", status="published")); db.commit()
    rows = db.query(models.Template).order_by(models.Template.id).all()

    monkeypatch.delenv("HIDDEN_NODE_TYPES", raising=False)
    assert hidden_nodes.filter_templates(rows, db) == rows                 # 꺼져 있으면 무변경

    monkeypatch.setenv("HIDDEN_NODE_TYPES", "jusoNode")
    kept = hidden_nodes.filter_templates(rows, db)
    assert [t.slug for t in kept] == ["without-juso", "no-version"]        # 버전 없는 행은 판단 불가 → 남김
    listed = community_templates.list_templates(db, sort="installs", limit=8)
    assert {t.slug for t in listed} == {"without-juso", "no-version"}


def test_warn_unknown_never_raises(monkeypatch, capsys):
    monkeypatch.setenv("HIDDEN_NODE_TYPES", "notARealNode, llmNode")
    hidden_nodes.warn_unknown(["llmNode", "startNode"])
    out = capsys.readouterr().out
    assert "notARealNode" in out and "llmNode" in out
