"""run_queue · run_worker — workflow_runs 를 큐로 쓰는 실행 큐와 워커 (백로그 32 ENGINE-2 1단계, ADR-0029) 테스트.

계약: (1) enqueue 는 실행에 필요한 것을 가진 queued run 을 만들고 claim 은 그것을 이 워커의 running 으로 바꾼다 — 두 번 잡히지
않는다 · (2) 워커는 잡은 run 을 같은 행 위에서 실행해 기록·과금(FlowExecutionLog, run_id 연결)을 남기고, 실행 예외에도 죽지
않는다 · (3) heartbeat 는 자기 run 만 갱신하고, 끊긴 run 은 failed 로 확정된다(재실행 없음) · (4) claim 안 된 queued 나 끝난
run 위에서 실행하려 하면 거부한다 · (5) 마이그레이션만으로 만든 스키마에 큐 컬럼이 있다 · (6) PostgreSQL 에서는 두 세션이
동시에 claim 해도 다른 run 을 잡는다(SKIP LOCKED — TEST_POSTGRES_URL 이 있을 때만).
"""

from __future__ import annotations

import datetime
import os
import threading

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import models
import run_queue
import run_records
import run_worker
from database import Base


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    return e


LINEAR = ([N("s", "startNode"), N("v", "valueNode", value="값"), N("o", "outputNode")], [E("s", "v"), E("v", "o")])


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    db = make()
    db.add_all([models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000),
                models.Project(id=10, user_id=1, title="큐 테스트", graph_data={})])
    db.commit()
    db.close()
    yield make
    engine.dispose()


@pytest.fixture
def db(factory):
    session = factory()
    yield session
    session.close()


def _enqueue(db, **kw):
    kw.setdefault("trigger_source", "schedule")
    kw.setdefault("project_id", 10)
    kw.setdefault("session_id", "scheduled_10")
    kw.setdefault("runtime_inputs", {"default_input": ""})
    run = run_queue.enqueue(db, nodes=LINEAR[0], edges=LINEAR[1], **kw)
    db.commit()
    return run


def _worker(factory, **kw):
    kw.setdefault("worker_id", "w-test")
    kw.setdefault("heartbeat_seconds", 60.0)   # 테스트 중 heartbeat 스레드가 sqlite 연결을 같이 쓰지 않게
    return run_worker.Worker(factory, **kw)


# ── 1. enqueue · claim ──────────────────────────────────────────────────────

def test_enqueue_는_실행에_필요한_것을_가진_queued_run_을_만든다(db):
    run = _enqueue(db, executor_user_id=1, options={"stop_node_id": "v"}, runtime_inputs={"default_input": "", "x": 1})
    assert run.status == "queued" and run.queued_at is not None and run.worker_id is None and run.attempts == 0
    assert (run.trigger_source, run.engine, run.project_id, run.owner_user_id, run.executor_user_id) == ("schedule", "legacy", 10, 1, 1)
    assert [n["id"] for n in run.graph_snapshot["nodes"]] == ["s", "v", "o"] and len(run.graph_snapshot["edges"]) == 2
    assert run.runtime_inputs == {"default_input": "", "x": 1} and run.run_options == {"stop_node_id": "v"}
    assert run_queue.queue_depth(db) == 1


def test_enqueue_는_출처와_옵션_키를_검사한다(db):
    with pytest.raises(ValueError, match="trigger_source"):
        run_queue.enqueue(db, nodes=[], edges=[], trigger_source="cron")
    with pytest.raises(ValueError, match="options"):
        run_queue.enqueue(db, nodes=[], edges=[], trigger_source="schedule", options={"bogus": 1})


def test_claim_은_가장_오래된_queued_를_이_워커의_running_으로_바꾸고_두_번_잡히지_않는다(db):
    first = _enqueue(db)
    second = _enqueue(db)
    claimed = run_queue.claim(db, "w1")
    assert claimed.id == first.id and claimed.status == "running" and claimed.worker_id == "w1"
    assert claimed.claimed_at is not None and claimed.heartbeat_at is not None and claimed.attempts == 1
    assert claimed.started_at >= claimed.queued_at
    assert run_queue.claim(db, "w2").id == second.id
    assert run_queue.claim(db, "w3") is None and run_queue.queue_depth(db) == 0


# ── 2. 워커 ──────────────────────────────────────────────────────────────────

def test_워커는_잡은_run_을_같은_행에서_실행하고_과금_기록을_남긴다(factory, db):
    run = _enqueue(db, executor_user_id=1)
    worker = _worker(factory)
    assert worker.run_once() == run.id
    assert worker.run_once() is None and worker.processed == 1

    db.expire_all()
    fresh = db.query(models.WorkflowRun).one()
    assert fresh.status == "succeeded" and fresh.worker_id == "w-test" and fresh.step_count == 3
    assert [s.node_id for s in fresh.steps] == ["s", "v", "o"] and fresh.steps[1].output_preview == "값"
    log = db.query(models.FlowExecutionLog).one()
    assert log.run_id == fresh.id and log.trigger_type == "scheduler" and log.outcome == "success"
    assert log.billable_user_id == 1 and log.project_id == 10


def test_옵션과_재개_상태가_실행_인자로_들어간다(factory, db):
    _enqueue(db, options={"stop_node_id": "v"})
    _worker(factory).run_once()
    db.expire_all()
    run = db.query(models.WorkflowRun).one()
    assert [s.node_id for s in run.steps] == ["s", "v"], "stop_node_id 까지만"

    args = run_queue.execute_arguments(run)
    assert args["kwargs"]["stop_node_id"] == "v" and "entry_node_id" not in args["kwargs"]
    run.resume_node_id, run.resume_payload = "v", "견본"
    args = run_queue.execute_arguments(run)
    assert args["kwargs"]["entry_node_id"] == "v" and args["kwargs"]["approval_payload"] == "견본"


def test_워커는_실행_예외에도_죽지_않고_run_을_failed_로_남긴다(factory, db, monkeypatch):
    import graph

    def boom(*a, **k):
        raise RuntimeError("엔진 폭발")

    monkeypatch.setattr(graph, "run_workflow", boom)
    run = _enqueue(db)
    worker = _worker(factory)
    assert worker.run_once() == run.id and worker.failures == 1 and worker.processed == 0
    db.expire_all()
    fresh = db.query(models.WorkflowRun).one()
    assert fresh.status == "failed" and "엔진 폭발" in fresh.error_summary and fresh.finished_at is not None
    assert db.query(models.FlowExecutionLog).count() == 0, "실행이 예외로 끝나면 과금 사건은 남기지 않는다(인라인 호출부와 같다)"


def test_run_forever_는_stop_event_로_멈추고_그동안_큐를_비운다(factory, db):
    for _ in range(3):
        _enqueue(db)
    worker = _worker(factory, poll_seconds=0.05)
    stop = threading.Event()
    threading.Timer(0.6, stop.set).start()
    worker.run_forever(stop)
    assert worker.processed == 3 and run_queue.queue_depth(db) == 0


# ── 3. heartbeat · 회수 ─────────────────────────────────────────────────────

def test_heartbeat_는_자기_running_run_만_갱신한다(db):
    run = _enqueue(db)
    run_queue.claim(db, "w1")
    old = db.query(models.WorkflowRun).one().heartbeat_at
    run.heartbeat_at = old - datetime.timedelta(seconds=30)
    db.commit()
    assert run_queue.heartbeat(db, run.id, "w1") is True
    db.expire_all()
    assert db.query(models.WorkflowRun).one().heartbeat_at > old - datetime.timedelta(seconds=30)
    assert run_queue.heartbeat(db, run.id, "someone-else") is False
    queued = _enqueue(db)
    assert run_queue.heartbeat(db, queued.id, "w1") is False, "queued 는 heartbeat 대상이 아니다"


def test_끊긴_heartbeat_는_failed_로_확정되고_살아_있는_것과_queued_는_건드리지_않는다(db):
    stale = _enqueue(db)
    alive = _enqueue(db)
    queued = _enqueue(db)
    run_queue.claim(db, "dead-worker")     # stale
    run_queue.claim(db, "live-worker")     # alive
    now = datetime.datetime.utcnow()
    stale.heartbeat_at = now - datetime.timedelta(seconds=600)
    db.commit()

    ids = run_queue.reclaim_stale(db, older_than_seconds=120, now=now)
    assert ids == [stale.id]
    db.expire_all()
    rows = {r.id: r for r in db.query(models.WorkflowRun).all()}
    assert rows[stale.id].status == "failed" and "heartbeat" in rows[stale.id].error_summary and rows[stale.id].finished_at is not None
    assert rows[alive.id].status == "running" and rows[queued.id].status == "queued"
    assert run_queue.reclaim_stale(db, older_than_seconds=120, now=now) == [], "두 번 확정하지 않는다"


def test_워커_바퀴는_주기적으로_stale_을_회수한다(factory, db):
    stale = _enqueue(db)
    run_queue.claim(db, "dead-worker")
    stale.heartbeat_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=600)
    db.commit()
    worker = _worker(factory, stale_after_seconds=120, reclaim_every_polls=1)
    assert worker.run_once() is None and worker.reclaimed == 1
    db.expire_all()
    assert db.query(models.WorkflowRun).one().status == "failed"


# ── 4. adopt ────────────────────────────────────────────────────────────────

def test_claim_되지_않은_queued_나_끝난_run_위에서는_실행할_수_없다(db):
    queued = _enqueue(db)
    with pytest.raises(ValueError, match="이어서 실행할 수 없는"):
        execution.start(*LINEAR, trigger_source="schedule", existing_run_id=queued.id, db=db)
    claimed = run_queue.claim(db, "w1")
    result, _t, _l = run_queue.execute_claimed(db, claimed)
    db.commit()
    assert result == "값"
    with pytest.raises(ValueError, match="이어서 실행할 수 없는"):
        execution.start(*LINEAR, trigger_source="schedule", existing_run_id=claimed.id, db=db)


# ── 5. 마이그레이션 ─────────────────────────────────────────────────────────

def test_마이그레이션만으로_만든_스키마에_큐_컬럼이_있다(tmp_path):
    import db_migrate

    url = f"sqlite:///{tmp_path / 'queue.db'}"
    engine = create_engine(url)
    db_migrate.ensure_schema(engine, url)
    columns = {c["name"] for c in inspect(engine).get_columns("workflow_runs")}
    assert {"queued_at", "claimed_at", "worker_id", "run_options", "attempts"} <= columns
    engine.dispose()


# ── 6. PostgreSQL SKIP LOCKED ───────────────────────────────────────────────

@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="SKIP LOCKED 는 실 PostgreSQL 에서만")
def test_postgres_에서_두_세션이_동시에_claim_해도_다른_run_을_잡는다():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    setup = make()
    try:
        ids = [run_queue.enqueue(setup, nodes=LINEAR[0], edges=LINEAR[1], trigger_source="schedule").id for _ in range(2)]
        setup.commit()
        barrier = threading.Barrier(2)
        claimed = {}

        def go(name):
            s = make()
            try:
                barrier.wait()
                run = run_queue.claim(s, name)
                claimed[name] = run.id if run else None
            finally:
                s.close()

        threads = [threading.Thread(target=go, args=(n,)) for n in ("w1", "w2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(claimed.values()) == sorted(ids), claimed
    finally:
        for run_id in setup.query(models.WorkflowRun.id).filter(models.WorkflowRun.trigger_source == "schedule").all():
            setup.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id[0]).delete()
        setup.commit()
        setup.close()
        engine.dispose()
