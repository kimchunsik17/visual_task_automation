"""Trigger cursor 저장소 계약 테스트 (한국형 노드 계획 Phase 0, §7).

이 파일이 지키는 문장은 하나다 — **cursor 를 잃어버리면 과거를 다시 통지한다.**

트리거는 빈 cursor 를 "첫 실행"으로 읽고 아무것도 알리지 않는다
(`rss.poll_new_items` 의 `first_run = not cursor`). 뒤집으면, 있는 cursor 를 못 읽고 `{}` 로
강등하는 순간 **사용자에게 지난 글이 전부 새 글로 쏟아진다.** 그래서

  - 마이그레이션이 옛 값을 옮기는지,
  - 옮기기 전 값도 이행기 읽기로 살아나는지,
  - 못 읽는 값이 조용히 `{}` 가 되지 않는지

를 각각 고정한다. lease 는 같은 노드를 두 워커가 동시에 폴링하는 경우를 막는다.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors import cursor as cursor_store
from database import Base

PROJECT = 7
NODE = "n-trigger"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(models.User(id=1, name="u", email="u@t.com", role="user"))
    session.add(models.Project(id=PROJECT, user_id=1, title="p",
                               graph_data={"nodes": [], "edges": []}, visibility="private"))
    session.commit()
    yield session
    session.close()


def _legacy(db, value, *, project_id=PROJECT, node_id=NODE):
    """마이그레이션 0017 이전 자리에 값을 넣는다."""
    db.add(models.NodeMemory(session_id=cursor_store.LEGACY_SESSION_ID,
                             project_id=project_id, node_id=node_id,
                             history=json.dumps(value, ensure_ascii=False)))
    db.commit()


# ── 기본 왕복 ───────────────────────────────────────────────────────────

def test_저장한_값을_그대로_읽는다(db):
    cursor_store.save(db, {"seen_ids": ["a", "b"]}, project_id=PROJECT, node_id=NODE, provider="rss")
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"seen_ids": ["a", "b"]}


def test_정말_없을_때만_빈_dict다(db):
    assert cursor_store.load(db, project_id=PROJECT, node_id="처음보는노드") == {}


def test_같은_노드는_행이_하나다(db):
    cursor_store.save(db, {"v": 1}, project_id=PROJECT, node_id=NODE)
    cursor_store.save(db, {"v": 2}, project_id=PROJECT, node_id=NODE)
    assert db.query(models.ConnectorCursor).filter_by(project_id=PROJECT, node_id=NODE).count() == 1
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"v": 2}


def test_provider와_workspace가_함께_기록된다(db):
    workspace = models.Workspace(id=3, slug="w", name="W", owner_id=1, plan="free")
    db.add(workspace)
    db.query(models.Project).filter_by(id=PROJECT).update({"workspace_id": 3})
    db.commit()

    cursor_store.save(db, {"v": 1}, project_id=PROJECT, node_id=NODE, provider="youtube")
    row = db.query(models.ConnectorCursor).filter_by(project_id=PROJECT, node_id=NODE).one()
    assert row.provider == "youtube"
    assert row.workspace_id == 3, "workspace 소유가 프로젝트에서 따라와야 격리가 성립한다"
    assert row.cursor_version == cursor_store.CURRENT_VERSION


def test_다른_프로젝트의_같은_node_id는_섞이지_않는다(db):
    db.add(models.Project(id=8, user_id=1, title="p2",
                          graph_data={"nodes": [], "edges": []}, visibility="private"))
    db.commit()
    cursor_store.save(db, {"who": "7"}, project_id=PROJECT, node_id=NODE)
    cursor_store.save(db, {"who": "8"}, project_id=8, node_id=NODE)
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"who": "7"}
    assert cursor_store.load(db, project_id=8, node_id=NODE) == {"who": "8"}


# ── 이관: 과거를 다시 통지하지 않는다 ───────────────────────────────────

def test_옛_자리의_값을_이행기_읽기로_살린다(db):
    """마이그레이션 전에 만들어진 행이 남아 있어도 첫 실행으로 강등되면 안 된다."""
    _legacy(db, {"seen_ids": ["old-1", "old-2"]})
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"seen_ids": ["old-1", "old-2"]}


def test_새_표에_값이_있으면_옛_자리는_보지_않는다(db):
    _legacy(db, {"seen_ids": ["old"]})
    cursor_store.save(db, {"seen_ids": ["new"]}, project_id=PROJECT, node_id=NODE)
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"seen_ids": ["new"]}


def test_이관된_cursor로는_첫_실행이_아니다(db):
    """RSS 트리거의 실제 판정(`first_run = not cursor`)이 뒤집히지 않는지 본다."""
    _legacy(db, {"seen_ids": ["old-1"]})
    loaded = cursor_store.load(db, project_id=PROJECT, node_id=NODE)
    assert not (not loaded), "이관된 cursor 가 falsy 면 트리거가 과거를 다시 통지한다"


# ── 못 읽는 값을 조용히 삼키지 않는다 ───────────────────────────────────

def test_깨진_cursor는_첫_실행으로_강등하지_않는다(db):
    cursor_store.save(db, {"v": 1}, project_id=PROJECT, node_id=NODE)
    db.query(models.ConnectorCursor).filter_by(project_id=PROJECT, node_id=NODE).update(
        {"cursor_json": "{깨진 JSON"})
    db.commit()
    with pytest.raises(cursor_store.CursorUnreadable):
        cursor_store.load(db, project_id=PROJECT, node_id=NODE)


def test_모르는_형식_버전은_거부한다(db):
    cursor_store.save(db, {"v": 1}, project_id=PROJECT, node_id=NODE)
    db.query(models.ConnectorCursor).filter_by(project_id=PROJECT, node_id=NODE).update(
        {"cursor_version": cursor_store.CURRENT_VERSION + 1})
    db.commit()
    with pytest.raises(cursor_store.CursorUnreadable) as exc:
        cursor_store.load(db, project_id=PROJECT, node_id=NODE)
    assert "형식" in str(exc.value)


def test_깨진_옛_값도_조용히_넘어가지_않는다(db):
    db.add(models.NodeMemory(session_id=cursor_store.LEGACY_SESSION_ID,
                             project_id=PROJECT, node_id=NODE, history="{깨진"))
    db.commit()
    with pytest.raises(cursor_store.CursorUnreadable):
        cursor_store.load(db, project_id=PROJECT, node_id=NODE)


# ── lease: 두 워커가 같은 노드를 동시에 폴링하지 않는다 ─────────────────

def test_먼저_잡은_쪽만_진행한다(db):
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A") is True
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-B") is False


def test_같은_주인은_다시_잡을_수_있다(db):
    """한 실행 안에서 load/save 가 여러 번 일어나도 스스로를 막으면 안 된다."""
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A") is True
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A") is True


def test_만료된_lease는_남이_가져간다(db):
    past = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="죽은-워커",
                               seconds=5, now=past)
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-B") is True


def test_놓으면_바로_남이_가져간다(db):
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A")
    cursor_store.release_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A")
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-B") is True


def test_남의_lease는_놓지_못한다(db):
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A")
    cursor_store.release_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-B")
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-C") is False


def test_lease를_잡아도_cursor_값은_건드리지_않는다(db):
    cursor_store.save(db, {"seen_ids": ["a"]}, project_id=PROJECT, node_id=NODE)
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="worker-A")
    assert cursor_store.load(db, project_id=PROJECT, node_id=NODE) == {"seen_ids": ["a"]}


def test_만료된_lease를_청소한다(db):
    past = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id=NODE, owner="죽은-워커",
                               seconds=5, now=past)
    cursor_store.acquire_lease(db, project_id=PROJECT, node_id="다른노드", owner="산-워커", seconds=600)
    assert cursor_store.purge_stale_leases(db) == 1
    assert cursor_store.acquire_lease(db, project_id=PROJECT, node_id="다른노드", owner="남") is False


def test_워커_이름이_프로세스마다_다르다():
    assert cursor_store.worker_identity() == cursor_store.worker_identity()
    assert ":" in cursor_store.worker_identity()


# ── db 가 없는 실행(에디터 미리보기 등)에서도 죽지 않는다 ───────────────

def test_db가_없으면_조용히_넘어간다():
    assert cursor_store.load(None, project_id=PROJECT, node_id=NODE) == {}
    cursor_store.save(None, {"v": 1}, project_id=PROJECT, node_id=NODE)
    assert cursor_store.acquire_lease(None, project_id=PROJECT, node_id=NODE) is True


# ── 마이그레이션 0017: 값이 실제로 넘어오는가 ───────────────────────────
# 여기가 이 작업에서 가장 위험한 지점이다. 표만 만들고 값을 안 옮기면 배포 직후 YouTube·RSS·
# Gmail 트리거가 일제히 "첫 실행"으로 판단해 과거 항목을 한 번씩 다시 통지한다.

import pathlib
import subprocess
import sys

from sqlalchemy import text

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def _alembic(args, database_url):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": database_url, "PYTHONPATH": str(BACKEND_DIR)},
        capture_output=True, text=True, timeout=600,
    )


def test_마이그레이션이_옛_cursor를_옮긴다(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"

    up = _alembic(["upgrade", "0016_oauth_states"], url)
    assert up.returncode == 0, up.stderr[-2000:]

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO workspaces (id, slug, name, owner_id, plan) VALUES (5, 'w', 'W', 1, 'free')"))
        conn.execute(text(
            "INSERT INTO projects (id, user_id, title, graph_data, visibility, workspace_id) "
            "VALUES (11, 1, 'p', '{}', 'private', 5)"))
        conn.execute(text(
            "INSERT INTO projects (id, user_id, title, graph_data, visibility) "
            "VALUES (12, 1, 'p2', '{}', 'private')"))
        # 옮겨져야 하는 값 두 개
        conn.execute(text(
            "INSERT INTO node_memory (session_id, project_id, node_id, history) "
            "VALUES ('__cursor__', 11, 'rss-1', '{\"seen_ids\": [\"a\", \"b\"]}')"))
        conn.execute(text(
            "INSERT INTO node_memory (session_id, project_id, node_id, history) "
            "VALUES ('__cursor__', 12, 'gm-1', '{\"last_id\": \"m9\"}')"))
        # 대화 기억은 cursor 가 아니므로 옮기면 안 된다
        conn.execute(text(
            "INSERT INTO node_memory (session_id, project_id, node_id, history) "
            "VALUES ('sess-abc', 11, 'llm-1', '[{\"role\": \"user\"}]')"))
        # 프로젝트가 이미 지워진 cursor 는 다시 실행될 일이 없어 옮기지 않는다
        conn.execute(text(
            "INSERT INTO node_memory (session_id, project_id, node_id, history) "
            "VALUES ('__cursor__', 999, 'gone', '{\"x\": 1}')"))

    up = _alembic(["upgrade", "head"], url)
    assert up.returncode == 0, up.stderr[-2000:]

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT project_id, node_id, cursor_json, cursor_version, workspace_id "
            "FROM connector_cursors ORDER BY project_id")).fetchall()

    assert len(rows) == 2, f"옮겨진 행이 2개여야 한다: {rows}"
    assert rows[0][:2] == (11, "rss-1")
    assert json.loads(rows[0][2]) == {"seen_ids": ["a", "b"]}
    assert rows[0][3] == 1, "형식 버전이 1로 찍혀야 읽는 쪽이 거부하지 않는다"
    assert rows[0][4] == 5, "workspace 소유가 프로젝트에서 따라와야 한다"
    assert rows[1][:2] == (12, "gm-1")
    assert rows[1][4] is None, "개인 프로젝트는 workspace 가 비어 있다"

    # 그리고 실제 읽기 경로로도 살아나야 한다 — 첫 실행으로 강등되면 안 된다
    session = sessionmaker(bind=engine)()
    try:
        loaded = cursor_store.load(session, project_id=11, node_id="rss-1")
        assert loaded == {"seen_ids": ["a", "b"]}
        assert not (not loaded), "falsy 면 트리거가 과거를 다시 통지한다"
    finally:
        session.close()


def test_마이그레이션은_옛_값을_지우지_않는다(tmp_path):
    """되돌릴 때 필요하고, 이행기 읽기의 근거도 된다."""
    url = f"sqlite:///{tmp_path / 'keep.db'}"
    assert _alembic(["upgrade", "0016_oauth_states"], url).returncode == 0
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO projects (id, user_id, title, graph_data, visibility) "
                          "VALUES (11, 1, 'p', '{}', 'private')"))
        conn.execute(text("INSERT INTO node_memory (session_id, project_id, node_id, history) "
                          "VALUES ('__cursor__', 11, 'n1', '{\"a\": 1}')"))
    assert _alembic(["upgrade", "head"], url).returncode == 0
    with engine.begin() as conn:
        remaining = conn.execute(text(
            "SELECT COUNT(*) FROM node_memory WHERE session_id = '__cursor__'")).scalar()
    assert remaining == 1


# ── 시작 모드와 겹침 창 (F3, 2026-08-30) ────────────────────────────────
#
# 이 정책이 `rss.py` 와 `naver_search.py` 에 **따로 구현돼 있었다.** 그래서 한쪽에서 찾은
# 결함(겹침 창 없음)이 다른 쪽에는 이미 고쳐진 채로 오래 남았다. 여기로 올렸으니
# 여기서 지킨다.

from connectors import cursor as cursor_store  # noqa: E402


def _items(*ids):
    return [{"id": i, "at": f"2026-08-{20 + n:02d}T00:00:00"} for n, i in enumerate(ids)]


def _pick(cur, items, **kw):
    kw.setdefault("key", "id")
    return cursor_store.select_new(cur, items, **kw)


# ── baseline: 켜자마자 과거가 쏟아지지 않는다 ───────────────────────────

def test_baseline_첫_실행은_아무것도_알리지_않는다():
    r = _pick(None, _items("a", "b", "c"))
    assert r["items"] == [] and r["first_run"] is True
    assert set(r["cursor"]["seen_ids"]) == {"a", "b", "c"}, "기준선에 현재 항목이 다 들어가야 한다"


def test_baseline_두_번째부터_새것만_알린다():
    first = _pick(None, _items("a", "b"))
    second = _pick(first["cursor"], _items("c", "a", "b"))
    assert [i["id"] for i in second["items"]] == ["c"]


# ── backfill: 지난 것부터 처리한다 ──────────────────────────────────────

def test_backfill_첫_실행은_전부_알린다():
    r = _pick(None, _items("a", "b", "c"), start_mode="backfill")
    assert [i["id"] for i in r["items"]] == ["a", "b", "c"]


def test_backfill_도_두_번째부터는_새것만이다():
    first = _pick(None, _items("a", "b"), start_mode="backfill")
    second = _pick(first["cursor"], _items("c", "a", "b"), start_mode="backfill")
    assert [i["id"] for i in second["items"]] == ["c"]


# ── since: 중간부터 이어받는다 ──────────────────────────────────────────

def test_since_기준_시각_이후만_알린다():
    r = _pick(None, _items("old", "new"), start_mode="since",
              since="2026-08-20T12:00:00", time_key="at")
    assert [i["id"] for i in r["items"]] == ["new"]


def test_since_기준을_못_읽으면_아무것도_안_보낸다():
    """잘못 읽고 전부 보내는 것보다 한 번 조용한 편이 낫다."""
    r = _pick(None, _items("a", "b"), start_mode="since", since="어제", time_key="at")
    assert r["items"] == []


def test_모르는_시작_모드는_거부한다():
    with pytest.raises(ValueError):
        _pick(None, _items("a"), start_mode="언젠가")


# ── 겹침 창 — 세 모드 모두에 걸린다 ─────────────────────────────────────

@pytest.mark.parametrize("mode", ["baseline", "backfill"])
def test_밀려났다_돌아온_항목을_다시_알리지_않는다(mode):
    first = _pick(None, _items("a", "b", "c"), start_mode=mode)
    gone = _pick(first["cursor"], _items("d", "b", "c"), start_mode=mode)
    assert [i["id"] for i in gone["items"]] == ["d"]
    back = _pick(gone["cursor"], _items("a", "d", "b", "c"), start_mode=mode)
    assert back["items"] == [], f"{mode}: 돌아온 항목이 재통지됐다"


def test_응답이_잠깐_비어도_기억을_잃지_않는다():
    first = _pick(None, _items("a", "b", "c"))
    empty = _pick(first["cursor"], [])
    assert empty["items"] == []
    back = _pick(empty["cursor"], _items("a", "b", "c"))
    assert back["items"] == [], "복구 후 전부 재통지됐다"


def test_창_크기를_넘으면_오래된_것부터_잊는다():
    cur = {"version": 1, "seen_ids": [f"old{i}" for i in range(10)]}
    r = _pick(cur, _items("new"), window=5)
    assert len(r["cursor"]["seen_ids"]) == 5
    assert "new" in r["cursor"]["seen_ids"]


# ── limit: 잘라낸 것이 사라지지 않는다 ──────────────────────────────────

def test_한도를_넘은_항목은_다음_실행에서_온다():
    first = _pick(None, _items("base"))
    second = _pick(first["cursor"], _items("n1", "n2", "n3", "base"), limit=2)
    assert [i["id"] for i in second["items"]] == ["n1", "n2"]
    assert second["pending"] == 1
    third = _pick(second["cursor"], _items("n1", "n2", "n3", "base"), limit=2)
    assert [i["id"] for i in third["items"]] == ["n3"], "잘린 항목이 사라졌다"


# ── cursor 형식 ─────────────────────────────────────────────────────────

def test_모르는_형식은_첫_실행으로_강등하지_않는다():
    with pytest.raises(cursor_store.CursorUnreadable):
        _pick({"version": 99, "seen_ids": []}, _items("a"))


def test_version_없는_예전_cursor도_읽는다():
    r = _pick({"seen_ids": ["a"]}, _items("a", "b"))
    assert r["first_run"] is False
    assert [i["id"] for i in r["items"]] == ["b"]
    assert r["cursor"]["version"] == cursor_store.CURRENT_VERSION


def test_저장_필드_이름을_바꾸지_않는다():
    """네이버 트리거는 `seen_links` 로 저장돼 있다 — 이름을 바꾸면 과거를 다시 알린다."""
    r = _pick({"version": 1, "seen_links": ["x"]}, [{"id": "x"}, {"id": "y"}],
              seen_field="seen_links")
    assert [i["id"] for i in r["items"]] == ["y"]
    assert "seen_links" in r["cursor"] and "seen_ids" not in r["cursor"]


def test_식별자가_없는_항목은_버린다():
    """중복 제거가 불가능한 항목을 통지하면 매번 새 글이 된다."""
    r = _pick({"version": 1, "seen_ids": []}, [{"id": ""}, {"id": "ok"}, {}])
    assert [i["id"] for i in r["items"]] == ["ok"]


# ── 두 트리거가 같은 정책을 쓴다 ────────────────────────────────────────

def test_rss와_네이버_트리거가_같은_함수를_쓴다():
    """따로 구현하면 한쪽만 고쳐지는 날이 온다 — 실제로 그랬다."""
    import inspect

    from connectors.services import naver_search, rss

    for module in (rss.poll_new_items, naver_search.poll_new_results):
        source = inspect.getsource(module)
        assert "cursor_store.select_new" in source, f"{module.__name__} 가 정책을 따로 갖고 있다"
