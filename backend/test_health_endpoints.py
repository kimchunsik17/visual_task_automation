"""/api/health · /api/ready — 배포 스모크가 성공·실패를 가르는 두 프로브 (1단계).

이 저장소의 배포 사고는 "반영이 안 됐는데 화면이 200 으로 떠서 몰랐다" 는 모양이었다.
스모크가 볼 수 있는 것이 index.html 뿐이면 그 사고를 못 잡는다. 여기서 지키는 문장은 셋이다.

  1. /api/health 는 프로세스만 본다 — DB 가 죽어도 200 이다(재기동 판단을 DB 에 묶지 않는다).
  2. /api/ready 는 스키마가 head 가 아니면 503 이다 — 리비전이 밀린 채로 트래픽을 받지 않는다.
  3. 실패해도 스택트레이스가 아니라 어디가 깨졌는지를 돌려준다.
"""

import os

os.environ.setdefault("DISABLE_SCHEDULER", "1")

from fastapi.testclient import TestClient  # noqa: E402

import db_migrate  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)


def test_health_reports_ok_without_touching_the_database(monkeypatch):
    """DB 를 못 쓰게 만들어도 200 이어야 한다. 여기서 DB 를 보면 DB 가 잠깐 흔들릴 때
    멀쩡한 프로세스가 재기동 대상이 된다."""
    def _boom(*a, **k):
        raise RuntimeError("database is down")

    monkeypatch.setattr(main.engine, "connect", _boom)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_is_200_when_schema_matches_head():
    r = client.get("/api/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["schema"] is True


def test_ready_is_503_when_the_schema_revision_is_behind(monkeypatch):
    """리비전을 한 칸 뒤로 돌린 상태를 '준비됨' 으로 보면 안 된다 — 그 상태로 트래픽을
    받으면 첫 쿼리에서 사용자에게 오류로 드러난다."""
    monkeypatch.setattr(db_migrate, "current_revision", lambda _engine: "0001_baseline")

    r = client.get("/api/ready")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["schema"] is False
    # 무엇이 어긋났는지 알려줘야 운영자가 판단할 수 있다.
    assert body["detail"]["schema"]["current"] == "0001_baseline"
    assert body["detail"]["schema"]["head"] == db_migrate.head_revision()


def test_ready_is_503_when_the_database_is_unreachable(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main.engine, "connect", _boom)

    r = client.get("/api/ready")
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["checks"]["database"] is False
    # 예외 종류만 나가고 메시지(접속 문자열이 실릴 수 있다)는 나가지 않는다.
    assert body["detail"]["database"] == "RuntimeError"
    assert "connection refused" not in r.text


def test_head_revision_is_readable_without_a_database():
    """head 는 스크립트만 읽으면 나온다 — DB 가 없어도 배포 도구가 기대값을 알 수 있다."""
    assert db_migrate.head_revision() is not None


# ── 실행 큐 (ENGINE-2 3단계, 로드맵 37번 O-2 "큐 적체") ────────────────────────────

def test_ready_reports_queue_as_not_applicable_when_the_queue_is_off(monkeypatch):
    monkeypatch.delenv("EXECUTION_QUEUE", raising=False)
    r = client.get("/api/ready")
    assert r.status_code == 200, r.text
    assert r.json()["checks"]["queue"] is None


def test_ready_is_503_when_queued_runs_wait_with_no_worker_heartbeat(monkeypatch):
    """큐를 켰는데 워커가 없으면 스케줄·웹훅 실행이 조용히 멈춘다 — 그것을 ready 가 503 으로 드러내야 한다.
    워커가 잡아 heartbeat 를 찍기 시작하면(정지가 아니라 적체) 다시 200 이다."""
    import datetime

    import models
    import run_queue
    from database import SessionLocal

    monkeypatch.setenv("EXECUTION_QUEUE", "1")
    db = SessionLocal()
    try:
        run = run_queue.enqueue(db, nodes=[], edges=[], trigger_source="schedule", runtime_inputs={}, session_id="ready-test")
        run.queued_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        db.commit()
        run_id = run.id

        r = client.get("/api/ready")
        assert r.status_code == 503, r.text
        body = r.json()
        assert body["checks"]["queue"] is False
        assert body["detail"]["queue"]["stalled"] is True and body["detail"]["queue"]["depth"] >= 1

        run = db.get(models.WorkflowRun, run_id)
        run.status, run.worker_id, run.heartbeat_at = "running", "w-test", datetime.datetime.utcnow()
        db.commit()
        r = client.get("/api/ready")
        assert r.status_code == 200, r.text
        assert r.json()["checks"]["queue"] is True
    finally:
        db.query(models.WorkflowRun).filter(models.WorkflowRun.session_id == "ready-test").delete()
        db.commit()
        db.close()
