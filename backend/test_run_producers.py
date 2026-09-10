"""생산자 전환 — EXECUTION_QUEUE 가 켜지면 스케줄·웹훅이 큐에 넣고 워커가 실행한다; 인프로세스 워커 (ENGINE-2 2단계, ADR-0029).

계약: (1) 꺼져 있으면 스케줄러·웹훅은 예전처럼 인라인 실행한다 · (2) 켜지면 스케줄러는 실행하지 않고 queued run 을 만들고,
웹훅은 202 + run_id 로 곧바로 답한다 · (3) 워커가 그 run 을 같은 행 위에서 실행하고 과금 기록(trigger_type 표기 유지)을 남긴다 ·
(4) 인프로세스 워커 스레드는 켜고 끌 수 있고 큐를 비운다 · (5) /api/features 가 큐 스위치를 알린다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import models
import run_queue
import run_worker
import scheduler
from database import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    db = make()
    db.add_all([
        models.User(id=1, name="Owner", email="owner@example.com", token_balance=10_000),
        models.Project(id=77, user_id=1, title="아침 브리핑", graph_data={
            "is_live": True,
            "nodes": [{"id": "s", "type": "scheduleNode", "data": {"cronExpression": "0 7 * * *"}},
                      {"id": "v", "type": "valueNode", "data": {"value": "브리핑"}},
                      {"id": "o", "type": "outputNode", "data": {}}],
            "edges": [{"source": "s", "target": "v"}, {"source": "v", "target": "o"}],
        }),
    ])
    db.commit()
    db.close()
    yield make
    engine.dispose()


# ── 1·2. 스케줄러 ───────────────────────────────────────────────────────────

def test_큐가_꺼져_있으면_스케줄러는_예전처럼_인라인_실행한다(factory, monkeypatch):
    monkeypatch.delenv(run_queue.QUEUE_ENV, raising=False)
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    calls = []
    monkeypatch.setattr(execution, "start", lambda *a, **k: calls.append(k) or ("브리핑", {"total_tokens": 0}, []))
    scheduler.execute_scheduled_project(77)
    assert len(calls) == 1 and calls[0]["trigger_source"] == "schedule"
    db = factory()
    assert db.query(models.WorkflowRun).count() == 0
    db.close()


def test_큐가_켜져_있으면_스케줄러는_실행하지_않고_queued_run_을_만든다(factory, monkeypatch):
    monkeypatch.setenv(run_queue.QUEUE_ENV, "1")
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    monkeypatch.setattr(execution, "start", lambda *a, **k: pytest.fail("큐가 켜져 있으면 스케줄러가 직접 실행하면 안 된다"))
    scheduler.execute_scheduled_project(77)

    db = factory()
    run = db.query(models.WorkflowRun).one()
    assert (run.status, run.trigger_source, run.project_id, run.session_id, run.owner_user_id) == ("queued", "schedule", 77, "scheduled_77", 1)
    assert [n["type"] for n in run.graph_snapshot["nodes"]] == ["scheduleNode", "valueNode", "outputNode"]
    assert db.query(models.FlowExecutionLog).count() == 0, "과금은 워커가 실행한 뒤에 남긴다"
    db.close()


def test_스케줄러가_넣은_run_을_워커가_실행하고_scheduler_표기로_과금한다(factory, monkeypatch):
    monkeypatch.setenv(run_queue.QUEUE_ENV, "1")
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    scheduler.execute_scheduled_project(77)
    worker = run_worker.Worker(factory, worker_id="w-test", heartbeat_seconds=60)
    assert worker.run_once() is not None and worker.run_once() is None

    db = factory()
    run = db.query(models.WorkflowRun).one()
    assert run.status == "succeeded" and [s.node_id for s in run.steps] == ["s", "v", "o"] and run.worker_id == "w-test"
    log = db.query(models.FlowExecutionLog).one()
    assert log.run_id == run.id and log.trigger_type == "scheduler" and log.billable_user_id == 1 and log.outcome == "success"
    db.close()


def test_advisory_lock_은_큐_모드에서도_중복_enqueue_를_막는다(factory, monkeypatch):
    monkeypatch.setenv(run_queue.QUEUE_ENV, "1")
    monkeypatch.setattr(scheduler, "SessionLocal", factory)
    with execution.advisory_lock(execution.SCHEDULE_LOCK_NAMESPACE, 77) as held:
        assert held
        scheduler.execute_scheduled_project(77)   # 잠금이 잡혀 있어 조용히 스킵
    db = factory()
    assert db.query(models.WorkflowRun).count() == 0
    db.close()


# ── 4. 인프로세스 워커 ──────────────────────────────────────────────────────

def test_인프로세스_워커는_켜고_끌_수_있고_큐를_비운다(factory, monkeypatch):
    db = factory()
    for _ in range(2):
        run_queue.enqueue(db, nodes=[{"id": "s", "type": "startNode", "data": {}}, {"id": "o", "type": "outputNode", "data": {}}],
                          edges=[{"source": "s", "target": "o"}], trigger_source="schedule", project_id=77,
                          runtime_inputs={"default_input": ""})
    db.commit()
    try:
        worker = run_worker.start_inprocess_worker(factory, poll_seconds=0.05, heartbeat_seconds=60)
        assert run_worker.inprocess_worker() is worker
        assert run_worker.start_inprocess_worker(factory) is worker, "두 번 켜도 하나다"
        deadline = time.time() + 5
        while worker.processed < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert worker.processed == 2 and run_queue.queue_depth(db) == 0
    finally:
        run_worker.stop_inprocess_worker()
    assert run_worker.inprocess_worker() is None
    db.expire_all()
    assert {r.status for r in db.query(models.WorkflowRun).all()} == {"succeeded"}
    db.close()


def test_스위치_기본값은_꺼짐이다(monkeypatch):
    monkeypatch.delenv(run_queue.QUEUE_ENV, raising=False)
    monkeypatch.delenv(run_worker.INPROCESS_ENV, raising=False)
    assert run_queue.queue_enabled() is False and run_worker.inprocess_enabled() is False
    monkeypatch.setenv(run_queue.QUEUE_ENV, "true")
    monkeypatch.setenv(run_worker.INPROCESS_ENV, "1")
    assert run_queue.queue_enabled() is True and run_worker.inprocess_enabled() is True


# ── 2·3·5. 웹훅 (실제 앱, 서브프로세스 시나리오) ─────────────────────────────

SCENARIO = r'''
import os, sys, json
os.environ["DATABASE_URL"] = sys.argv[1]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER",
          "OPENROUTER_BASE_URL", "PICKLE_API_KEY", "EXECUTION_QUEUE", "EXECUTION_WORKER_INPROCESS"):
    os.environ[k] = ""
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models, run_queue, run_worker
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
db.add(owner); db.commit()
graph = {"is_live": True,
         "nodes": [{"id": "w", "type": "webhookNode", "data": {}}, {"id": "o", "type": "outputNode", "data": {}}],
         "edges": [{"source": "w", "target": "o"}]}
project = models.Project(user_id=owner.id, title="웹훅", graph_data=graph)
db.add(project); db.commit()

# 꺼져 있으면 인라인 — 200 과 결과
r = client.post(f"/webhook/{project.id}", json={"event": "ping"}); assert r.status_code == 200, r.text
assert r.json()["status"] == "success" and "ping" in r.json()["result"]
assert client.get("/api/features").json()["execution_queue"] is False
inline_runs = db.query(models.WorkflowRun).count()

# 켜면 202 + run_id, queued run, 과금은 아직 없음
os.environ["EXECUTION_QUEUE"] = "1"
assert client.get("/api/features").json()["execution_queue"] is True
r = client.post(f"/webhook/{project.id}", json={"event": "order.created"}); assert r.status_code == 202, r.text
body = r.json(); assert body["status"] == "queued" and body["project_id"] == project.id
db.expire_all()
run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == body["run_id"]).one()
assert run.status == "queued" and run.trigger_source == "webhook" and run.session_id == f"webhook_{project.id}"
assert "order.created" in run.runtime_inputs["w"]
before_logs = db.query(models.FlowExecutionLog).count()

# 워커가 실행 — 같은 run, webhook 표기 과금, 타임라인에서 결과가 보인다
worker = run_worker.Worker(SessionLocal, worker_id="w-scenario", heartbeat_seconds=60)
assert worker.run_once() == run.id
db.expire_all()
run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == body["run_id"]).one()
assert run.status == "succeeded" and run.worker_id == "w-scenario" and [s.node_id for s in run.steps] == ["w", "o"]
assert db.query(models.FlowExecutionLog).count() == before_logs + 1
log = db.query(models.FlowExecutionLog).order_by(models.FlowExecutionLog.id.desc()).first()
assert log.run_id == run.id and log.trigger_type == "webhook" and log.billable_user_id == owner.id
import datetime as _dt
tok = main.jwt.encode({"user_id": owner.id, "email": owner.email, "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1)}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
d = client.get(f"/api/projects/{project.id}/workflow-runs/{run.id}", headers={"Authorization": f"Bearer {tok}"}); assert d.status_code == 200, d.text
assert d.json()["status"] == "succeeded" and "order.created" in d.json()["steps"][-1]["outputPreview"]
print("RUN PRODUCERS OK")
'''


def test_webhook_producer_end_to_end(tmp_path):
    scenario_path = tmp_path / "run_producers_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'producers.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "RUN PRODUCERS OK" in result.stdout
