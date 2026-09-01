"""프로젝트 저장 이력과 낙관적 동시성 (ADR-0006) 테스트."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import db_migrate
import models
import project_revisions
from database import Base

from conftest import minimal_subprocess_env

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def graph(*node_ids, edges=(), data=None):
    return {
        "nodes": [
            {"id": node_id, "type": "llmNode", "position": {"x": 0, "y": 0}, "data": (data or {})}
            for node_id in node_ids
        ],
        "edges": [{"id": edge_id, "source": s, "target": t} for edge_id, s, t in edges],
    }


def seed_project(db, graph_data=None):
    user = models.User(id=1, name="Owner")
    project = models.Project(
        id=10, user_id=1, title="워크플로우", description="설명",
        graph_data=graph_data if graph_data is not None else graph("n1"),
        current_revision=0,
    )
    db.add_all([user, project])
    db.commit()
    return project


# ── 스냅샷 기록 ────────────────────────────────────────────────────────
def test_first_save_records_revision_one():
    db, _ = make_session()
    project = seed_project(db)

    revision = project_revisions.record_revision(db, project, author_user_id=1)
    db.commit()

    assert revision.revision == 1
    assert project.current_revision == 1
    assert revision.summary == {"nodes": 1, "edges": 0, "node_types": {"llmNode": 1}}
    assert revision.source == "user"


def test_identical_save_does_not_create_a_new_revision():
    """배포 전 저장처럼 같은 그래프를 연달아 저장하는 경로가 있어서, 그대로 두면
    이력이 의미 없이 불어난다."""
    db, _ = make_session()
    project = seed_project(db)
    project_revisions.record_revision(db, project, author_user_id=1)
    db.commit()

    assert project_revisions.record_revision(db, project, author_user_id=1) is None
    db.commit()
    assert project.current_revision == 1
    assert db.query(models.ProjectRevision).count() == 1


def test_changed_graph_creates_the_next_revision():
    db, _ = make_session()
    project = seed_project(db)
    project_revisions.record_revision(db, project, author_user_id=1)
    db.commit()

    project.graph_data = graph("n1", "n2")
    second = project_revisions.record_revision(db, project, author_user_id=1, source="ai")
    db.commit()

    assert second.revision == 2
    assert project.current_revision == 2
    assert second.source == "ai"
    assert [r.revision for r in project.revisions] == [2, 1]


def test_title_change_alone_is_recorded():
    db, _ = make_session()
    project = seed_project(db)
    project_revisions.record_revision(db, project, author_user_id=1)
    db.commit()

    project.title = "이름만 바꿈"
    assert project_revisions.record_revision(db, project, author_user_id=1) is not None


def test_deleting_a_project_removes_its_revisions():
    db, _ = make_session()
    project = seed_project(db)
    project_revisions.record_revision(db, project, author_user_id=1)
    db.commit()

    db.delete(project)
    db.commit()
    assert db.query(models.ProjectRevision).count() == 0


# ── diff ───────────────────────────────────────────────────────────────
def test_diff_reports_added_removed_and_changed_nodes():
    before = graph("n1", "n2", edges=[("e1", "n1", "n2")])
    after = graph("n2", "n3", edges=[("e2", "n2", "n3")])
    after["nodes"][0]["data"] = {"systemPrompt": "바뀜"}

    diff = project_revisions.diff_graphs(before, after)

    assert diff["nodes"] == {"added": ["n3"], "removed": ["n1"], "changed": ["n2"]}
    assert diff["edges"] == {"added": ["e2"], "removed": ["e1"]}


def test_moving_a_node_is_not_reported_as_a_change():
    """캔버스에서 노드를 옮기기만 한 것은 설정 변경과 성격이 다르고, 충돌 화면에서
    알려줘 봐야 판단에 도움이 안 된다."""
    before = graph("n1")
    after = graph("n1")
    after["nodes"][0]["position"] = {"x": 900, "y": 400}

    assert project_revisions.diff_graphs(before, after)["nodes"]["changed"] == []


def test_diff_tolerates_malformed_graphs():
    assert project_revisions.diff_graphs(None, {"nodes": "이건 리스트가 아니다"})["nodes"]["added"] == []


# ── 충돌 응답 ──────────────────────────────────────────────────────────
def test_conflict_detail_shows_what_changed_on_the_server():
    db, _ = make_session()
    project = seed_project(db)
    project_revisions.record_revision(db, project, author_user_id=1)  # revision 1
    db.commit()

    project.graph_data = graph("n1", "n2")  # 다른 곳에서 저장된 변경
    project_revisions.record_revision(db, project, author_user_id=1)  # revision 2
    db.commit()

    detail = project_revisions.conflict_detail(db, project, base_revision=1, incoming_graph=graph("n1", "n9"))

    assert detail["code"] == "REVISION_CONFLICT"
    assert (detail["base_revision"], detail["current_revision"]) == (1, 2)
    assert detail["server_changes_since_base"]["nodes"]["added"] == ["n2"]
    assert detail["my_changes_since_base"]["nodes"]["added"] == ["n9"]


def test_conflict_detail_without_base_snapshot_still_reports_current_state():
    """버전 기록 도입 전에 만들어져 base 스냅샷이 없는 프로젝트도 안내는 되어야 한다."""
    db, _ = make_session()
    project = seed_project(db)

    detail = project_revisions.conflict_detail(db, project, base_revision=99, incoming_graph=graph("n1"))

    assert "server_changes_since_base" not in detail
    assert detail["current_summary"]["nodes"] == 1


# ── 마이그레이션 ───────────────────────────────────────────────────────
def _alembic(args, database_url):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=minimal_subprocess_env(DATABASE_URL=database_url, PYTHONPATH=str(BACKEND_DIR)),
        capture_output=True,
        text=True,
    )


def test_migrations_directory_does_not_shadow_the_alembic_package():
    """서버는 cwd 를 backend/ 로 두고 뜬다. 그 자리에 'alembic' 디렉터리가 있으면 파이썬이
    실제 alembic 라이브러리 대신 그걸 import 해서 서버가 아예 뜨지 못한다(배포에서 겪었다)."""
    assert not (BACKEND_DIR / "alembic").exists()
    assert (BACKEND_DIR / "migrations" / "versions").is_dir()


def test_migrations_are_a_single_linear_chain():
    """분기된 마이그레이션 이력은 `alembic upgrade head` 를 실패시킨다."""
    versions = sorted((BACKEND_DIR / "migrations" / "versions").glob("*.py"))
    assert len(versions) >= 2
    down_revisions = []
    for path in versions:
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.startswith("down_revision"):
                down_revisions.append(line.split("=", 1)[1].strip())
                break
    # 루트(None)는 정확히 하나여야 하고, 나머지는 서로 다른 부모를 가리켜야 한다.
    roots = [d for d in down_revisions if "None" in d]
    assert len(roots) == 1
    assert len(set(down_revisions)) == len(down_revisions)


def test_ensure_schema_adopts_a_database_created_by_create_all(tmp_path):
    """create_all 로 만들어져 마이그레이션 이력이 없는 기존 DB 도 인계받아야 한다."""
    db_path = tmp_path / "legacy.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)

    # 기준선 시점의 스키마를 흉내 낸다 — projects 는 있지만 project_revisions 는 없는 상태.
    # 이후 마이그레이션이 기준선 테이블을 ALTER 하는 경우(예: 0004의 generation_traces)도
    # 검증해야 하므로, 그 대상 테이블은 실제 create_all 레거시 DB 처럼 함께 만들어 둔다.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, description TEXT, graph_data TEXT, visibility TEXT)"))
        connection.execute(text("CREATE TABLE generation_traces (id INTEGER PRIMARY KEY, trace_id TEXT, graph_summary TEXT, token_usage TEXT)"))
        # 0008(ADR-0016)이 telemetry 컬럼을, 0009(ADR-0017)가 label 을 덧붙이는 기준선 테이블.
        connection.execute(text(
            "CREATE TABLE node_execution_logs (id INTEGER PRIMARY KEY, flow_execution_id INTEGER, node_id TEXT, node_type TEXT, "
            "start_time DATETIME, end_time DATETIME, status TEXT, result_data TEXT, error_message TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE user_api_keys (id INTEGER PRIMARY KEY, user_id INTEGER, provider TEXT, api_key TEXT, "
            "refresh_token TEXT, created_at DATETIME, updated_at DATETIME)"
        ))
        # 0011(ADR-0020)이 users.role 과 friend_requests.greeting 을 덧붙이는 기준선 테이블.
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, google_id TEXT, email TEXT, name TEXT, "
            "picture TEXT, token_balance INTEGER)"
        ))
        connection.execute(text(
            "CREATE TABLE friend_requests (id INTEGER PRIMARY KEY, from_user_id INTEGER, "
            "to_user_id INTEGER, status TEXT, created_at DATETIME)"
        ))

    result = db_migrate.ensure_schema(engine, url)

    assert "stamp" in result
    tables = set(inspect(engine).get_table_names())
    assert "project_revisions" in tables and "alembic_version" in tables
    columns = {c["name"] for c in inspect(engine).get_columns("projects")}
    assert "current_revision" in columns
    trace_columns = {c["name"] for c in inspect(engine).get_columns("generation_traces")}
    assert "node_selection" in trace_columns
    assert "role" in {c["name"] for c in inspect(engine).get_columns("users")}
    assert "greeting" in {c["name"] for c in inspect(engine).get_columns("friend_requests")}
    log_columns = {c["name"] for c in inspect(engine).get_columns("node_execution_logs")}
    assert {"error_code", "error_category", "effect_state", "error_legacy", "error_request_id"} <= log_columns


def test_ensure_schema_refuses_to_guess_an_ambiguous_database(tmp_path):
    """이력은 없는데 신규 테이블이 이미 있으면, 어디로 stamp 할지 추측하지 않고 멈춘다 —
    절반만 적용된 스키마로 서비스가 뜨는 것이 더 나쁘다."""
    db_path = tmp_path / "ambiguous.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE project_revisions (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError, match="alembic stamp"):
        db_migrate.ensure_schema(engine, url)


def test_ensure_schema_creates_a_fresh_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)

    db_migrate.ensure_schema(engine, url)

    tables = set(inspect(engine).get_table_names())
    assert {"projects", "project_revisions", "users", "alembic_version"} <= tables
