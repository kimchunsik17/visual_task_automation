"""export_community_graphs — DB 전용 코퍼스(갤러리 템플릿·사용자 프로젝트)를 섀도 대조 입력으로 내보내기 테스트.

계약: (1) 게시된 템플릿의 최신 게시 버전 그래프만 나간다(초안·yank 제외) · (2) 평문 비밀은 나가지 않는다 —
접속 문자열은 run_workflow 와 같은 sentinel, apiKey 류는 빈 값 · (3) 출력 형식은 engine_shadow_diff --projects-json 이 읽는
[{title, nodes, edges}] 다.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import export_community_graphs as exporter
import models
from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _graph(connection_string="postgresql://user:pw@db.internal/prod", api_key="sk-plain"):
    return {
        "nodes": [
            {"id": "s", "type": "startNode", "data": {}},
            {"id": "d", "type": "databaseNode", "data": {"connectionString": connection_string, "query": "select 1"}},
            {"id": "l", "type": "llmNode", "data": {"apiKey": api_key, "model": "gpt-4o-mini"}},
            {"id": "k", "type": "kakaoNode", "data": {"accessToken": "{{API_CENTER:kakao_token}}"}},
        ],
        "edges": [{"source": "s", "target": "d"}, {"source": "d", "target": "l"}, {"source": "l", "target": "k"}],
    }


def _publish(db, slug, version="1.0.0", status="published", graph=None, mark_latest=True):
    share = models.WorkflowShare(owner_type="template", owner_id=0, graph_snapshot=graph or _graph())
    db.add(share)
    db.flush()
    template = models.Template(slug=slug, title=slug, status=status)
    db.add(template)
    db.flush()
    ver = models.TemplateVersion(template_id=template.id, version=version, workflow_share_id=share.id,
                                 status="published", published_at=datetime.datetime(2026, 9, 1))
    db.add(ver)
    db.flush()
    share.owner_id = template.id
    if mark_latest:
        template.latest_version_id = ver.id
    db.commit()
    return template, ver


def test_게시된_템플릿의_최신_버전만_나간다(db):
    _publish(db, "weekly-report")
    _publish(db, "draft-only", status="draft")
    yanked_template, _ = _publish(db, "two-versions", version="1.0.0", mark_latest=False)
    # 두 번째 버전이 최신 — latest_version_id 없이도 published_at·id 순으로 고른다.
    share2 = models.WorkflowShare(owner_type="template", owner_id=yanked_template.id, graph_snapshot=_graph())
    db.add(share2)
    db.flush()
    db.add(models.TemplateVersion(template_id=yanked_template.id, version="1.1.0", workflow_share_id=share2.id,
                                  status="published", published_at=datetime.datetime(2026, 9, 5)))
    db.commit()

    out = exporter.export_graphs(db)
    assert [g["title"] for g in out] == ["template:weekly-report@1.0.0", "template:two-versions@1.1.0"]
    assert all(set(g) == {"title", "nodes", "edges"} for g in out)
    assert len(out[0]["edges"]) == 3


def test_평문_비밀은_나가지_않고_placeholder_는_남는다(db):
    _publish(db, "secrets")
    from db_query_runtime import LEGACY_PLAINTEXT_SENTINEL

    nodes = {n["id"]: n for n in exporter.export_graphs(db)[0]["nodes"]}
    assert nodes["d"]["data"]["connectionString"] == LEGACY_PLAINTEXT_SENTINEL
    assert nodes["l"]["data"]["apiKey"] == ""
    assert nodes["k"]["data"]["accessToken"] == "{{API_CENTER:kakao_token}}", "placeholder 는 비밀이 아니다"
    # 원본 행은 건드리지 않는다(깊은 복사).
    share = db.query(models.WorkflowShare).first()
    assert share.graph_snapshot["nodes"][1]["data"]["connectionString"].startswith("postgresql://")


def test_placeholder_접속_문자열은_그대로_두고_빈_그래프는_건너뛴다(db):
    _publish(db, "ref-only", graph=_graph(connection_string="{{API_CENTER:database#3}}", api_key=""))
    _publish(db, "empty", graph={"nodes": [], "edges": []})
    out = exporter.export_graphs(db)
    assert [g["title"] for g in out] == ["template:ref-only@1.0.0"]
    assert {n["id"]: n for n in out[0]["nodes"]}["d"]["data"]["connectionString"] == "{{API_CENTER:database#3}}"


def test_프로젝트는_옵션이고_같은_가림_규칙을_거친다(db):
    db.add(models.User(id=1, name="Owner", email="owner@example.com"))
    db.add(models.Project(id=7, user_id=1, title="주간 보고", graph_data=_graph()))
    db.add(models.Project(id=8, user_id=1, title="빈 프로젝트", graph_data={"nodes": [], "edges": []}))
    db.commit()

    assert exporter.export_graphs(db) == []
    out = exporter.export_graphs(db, include_projects=True)
    assert [g["title"] for g in out] == ["project:7:주간 보고"]
    assert {n["id"]: n for n in out[0]["nodes"]}["l"]["data"]["apiKey"] == ""
