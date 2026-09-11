"""웹훅 중복 제거 — idempotency_key (백로그 32 ENGINE-3 4단계, ADR-0030 추기).

계약: (1) 키는 전달 id 헤더(X-GitHub-Delivery·X-GitLab-Event-UUID·Idempotency-Key) → webhookNode 가 켠 경우 payload 해시 → 없으면 None ·
(2) `execution.start(idempotency_key=)` 는 같은 키의 run 이 있으면 실행하지 않고 DuplicateRun · (3) 실행 기록이 없으면(RUN_RECORDS=0)
걸러낼 수 없어 그대로 실행한다 · (4) `run_queue.enqueue_or_existing` 은 같은 키를 두 번 넣지 않는다 · (5) 웹훅 엔드포인트 — 인라인은
200 duplicate + 원래 run_id, 큐는 202 duplicate + 같은 run_id, 워커는 한 번만 실행 · (6) 키가 없는 웹훅은 예전처럼 매번 실행.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import idempotency
import models
import run_queue
import run_records
from database import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

GRAPH = ([{"id": "w", "type": "webhookNode", "data": {}}, {"id": "o", "type": "outputNode", "data": {}}],
         [{"source": "w", "target": "o"}])


# ── 1. 키 ───────────────────────────────────────────────────────────────────

def test_키는_전달_id_헤더에서_먼저_읽는다():
    assert idempotency.webhook_key(7, {"X-GitHub-Delivery": " 72d3162e-cc78 "}, {"a": 1}) == "webhook:7:x-github-delivery:72d3162e-cc78"
    assert idempotency.webhook_key(7, {"x-gitlab-event-uuid": "u-1"}, {}) == "webhook:7:x-gitlab-event-uuid:u-1"
    assert idempotency.webhook_key(7, {"Idempotency-Key": "k"}, {}) == "webhook:7:idempotency-key:k"
    assert idempotency.webhook_key(7, {"X-GitHub-Delivery": "x" * 500}, {}).endswith("x" * 200), "헤더 값은 200자에서 자른다"
    assert idempotency.webhook_key(7, {"X-GitHub-Delivery": "   "}, {}) is None
    assert idempotency.webhook_key(7, {}, {"a": 1}) is None, "헤더도 설정도 없으면 중복 제거 없음"
    assert idempotency.webhook_key(7, None, {"a": 1}) is None


def test_payload_해시는_webhookNode_가_켠_경우에만_쓰고_키_순서에_무관하다():
    node = {"id": "w", "type": "webhookNode", "data": {"dedupeByPayload": True}}
    k1 = idempotency.webhook_key(7, {}, {"a": 1, "b": [1, 2]}, node=node)
    k2 = idempotency.webhook_key(7, {}, {"b": [1, 2], "a": 1}, node=node)
    assert k1 == k2 and k1.startswith("webhook:7:sha256:") and len(k1.split(":")[-1]) == 32
    assert idempotency.webhook_key(7, {}, {"a": 2}, node=node) != k1
    assert idempotency.webhook_key(8, {}, {"a": 1}, node=node) != k1, "프로젝트가 다르면 다른 사건"
    assert idempotency.webhook_key(7, {"X-GitHub-Delivery": "d"}, {"a": 1}, node=node) == "webhook:7:x-github-delivery:d", "헤더가 우선"
    assert idempotency.webhook_key(7, {}, {"a": 1}, node={"data": {"dedupeByPayload": "false"}}) is None
    assert idempotency.webhook_key(7, {}, {"a": 1}, node={"data": {"dedupeByPayload": "yes"}}) is not None


# ── 2·3·4. 실행 진입점과 큐 ─────────────────────────────────────────────────

@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    db = make()
    db.add_all([models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000),
                models.Project(id=1, user_id=1, title="웹훅", graph_data={"nodes": GRAPH[0], "edges": GRAPH[1]})])
    db.commit()
    db.close()
    yield make
    engine.dispose()


def _start(db, key, payload="ping"):
    return execution.start(GRAPH[0], GRAPH[1], trigger_source="webhook", db=db, project_id=1, session_id="webhook_1",
                           idempotency_key=key, w=payload)


def test_같은_키의_두_번째_실행은_DuplicateRun_이고_실행되지_않는다(factory):
    db = factory()
    result, _t, _l = _start(db, "webhook:1:x-github-delivery:abc")
    db.commit()
    assert "ping" in result
    first = db.query(models.WorkflowRun).one()
    assert first.idempotency_key == "webhook:1:x-github-delivery:abc"

    with pytest.raises(execution.DuplicateRun) as info:
        _start(db, "webhook:1:x-github-delivery:abc", payload="again")
    assert info.value.run_id == first.id and info.value.status == "succeeded"
    assert db.query(models.WorkflowRun).count() == 1, "실행되지 않았다"

    _start(db, "webhook:1:x-github-delivery:def")
    db.commit()
    assert db.query(models.WorkflowRun).count() == 2, "다른 키는 새 실행"
    db.close()


def test_실행_기록이_없으면_걸러낼_수_없어_그대로_실행한다(factory, monkeypatch):
    monkeypatch.setenv(run_records.RUN_RECORDS_ENV, "0")
    db = factory()
    _start(db, "webhook:1:x-github-delivery:abc")
    result, _t, _l = _start(db, "webhook:1:x-github-delivery:abc", payload="again")
    assert "again" in result and db.query(models.WorkflowRun).count() == 0
    db.close()
    # db 가 없어도 같다
    result, _t, _l = execution.start(GRAPH[0], GRAPH[1], trigger_source="webhook", idempotency_key="k", w="x")
    assert "x" in result


def test_enqueue_or_existing_은_같은_키를_두_번_넣지_않는다(factory):
    db = factory()
    kw = dict(nodes=GRAPH[0], edges=GRAPH[1], trigger_source="webhook", project_id=1, session_id="webhook_1",
              runtime_inputs={"w": "ping"})
    run, created = run_queue.enqueue_or_existing(db, idempotency_key="webhook:1:x-github-delivery:abc", **kw)
    db.commit()
    again, created_again = run_queue.enqueue_or_existing(db, idempotency_key="webhook:1:x-github-delivery:abc", **kw)
    assert created is True and created_again is False and again.id == run.id
    assert db.query(models.WorkflowRun).count() == 1
    other, created_other = run_queue.enqueue_or_existing(db, idempotency_key="webhook:1:x-github-delivery:xyz", **kw)
    db.commit()
    assert created_other is True and other.id != run.id
    db.close()


# ── 5·6. 엔드포인트 ─────────────────────────────────────────────────────────

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER",
          "OPENROUTER_BASE_URL", "PICKLE_API_KEY", "EXECUTION_QUEUE", "EXECUTION_WORKER_INPROCESS"):
    os.environ[k] = ""
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models, run_worker
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
db.add(owner); db.commit()
plain = models.Project(user_id=owner.id, title="웹훅", graph_data={"is_live": True,
    "nodes": [{"id": "w", "type": "webhookNode", "data": {}}, {"id": "o", "type": "outputNode", "data": {}}],
    "edges": [{"source": "w", "target": "o"}]})
hashed = models.Project(user_id=owner.id, title="해시 웹훅", graph_data={"is_live": True,
    "nodes": [{"id": "w", "type": "webhookNode", "data": {"dedupeByPayload": True}}, {"id": "o", "type": "outputNode", "data": {}}],
    "edges": [{"source": "w", "target": "o"}]})
db.add_all([plain, hashed]); db.commit()
runs = lambda pid: db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == pid).count()

# 인라인: 같은 전달 id 는 200 duplicate + 원래 run_id, 실행 한 번
h = {"X-GitHub-Delivery": "d-1"}
r1 = client.post(f"/webhook/{plain.id}", json={"event": "ping"}, headers=h); assert r1.status_code == 200 and r1.json()["status"] == "success", r1.text
r2 = client.post(f"/webhook/{plain.id}", json={"event": "ping"}, headers=h); assert r2.status_code == 200, r2.text
assert r2.json()["status"] == "duplicate" and r2.json()["project_id"] == plain.id
db.expire_all()
assert runs(plain.id) == 1
first = db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == plain.id).one()
assert r2.json()["run_id"] == first.id and first.idempotency_key == f"webhook:{plain.id}:x-github-delivery:d-1"
assert db.query(models.FlowExecutionLog).count() == 1, "과금도 한 번"

# 헤더가 없고 설정도 없으면 예전처럼 매번 실행
client.post(f"/webhook/{plain.id}", json={"event": "ping"}); client.post(f"/webhook/{plain.id}", json={"event": "ping"})
db.expire_all(); assert runs(plain.id) == 3

# payload 해시 설정: 같은 본문은 duplicate, 다른 본문은 새 실행
a = client.post(f"/webhook/{hashed.id}", json={"n": 1}); b = client.post(f"/webhook/{hashed.id}", json={"n": 1}); c = client.post(f"/webhook/{hashed.id}", json={"n": 2})
assert a.json()["status"] == "success" and b.json()["status"] == "duplicate" and c.json()["status"] == "success", (a.text, b.text, c.text)
db.expire_all(); assert runs(hashed.id) == 2

# 큐: 같은 전달 id 는 202 duplicate + 같은 run_id, 워커는 한 번만
os.environ["EXECUTION_QUEUE"] = "1"
q1 = client.post(f"/webhook/{plain.id}", json={"event": "order"}, headers={"X-GitHub-Delivery": "d-2"}); assert q1.status_code == 202 and q1.json()["status"] == "queued", q1.text
q2 = client.post(f"/webhook/{plain.id}", json={"event": "order"}, headers={"X-GitHub-Delivery": "d-2"}); assert q2.status_code == 202 and q2.json()["status"] == "duplicate", q2.text
assert q1.json()["run_id"] == q2.json()["run_id"]
worker = run_worker.Worker(SessionLocal, worker_id="w-idem", heartbeat_seconds=60)
assert worker.run_once() == q1.json()["run_id"] and worker.run_once() is None
db.expire_all()
assert db.query(models.WorkflowRun).filter(models.WorkflowRun.id == q1.json()["run_id"]).one().status == "succeeded"
print("WEBHOOK IDEMPOTENCY OK")
'''


def test_webhook_endpoint_dedupes_end_to_end(tmp_path):
    scenario_path = tmp_path / "webhook_idempotency_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'idem.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout[-3000:]}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "WEBHOOK IDEMPOTENCY OK" in result.stdout
