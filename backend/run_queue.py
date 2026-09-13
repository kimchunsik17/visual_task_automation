"""run_queue.py — 실행 큐: workflow_runs 를 큐로 쓴다 (백로그 32 ENGINE-2 1단계, ADR-0029).

왜 별도 큐 표가 아닌가
  run 은 이미 실행에 필요한 것(그래프 스냅샷·런타임 입력·재개 상태·출처·소유자)을 갖는다(ADR-0028). status=queued 인 run 이
  곧 큐 항목이고, 워커가 잡으면 running, 끝나면 succeeded/failed/paused 다 — "한 논리적 실행은 run 하나" 가 큐 단계에서도
  지켜지고, 타임라인 API·진행 이벤트·FlowExecutionLog 연결이 그대로 통한다.

동시성
  PostgreSQL 에서는 `SELECT … FOR UPDATE SKIP LOCKED` 로 워커 여럿이 같은 run 을 두 번 잡지 않는다(Redis/Celery 를 먼저
  권하지 않는 이유: 이미 PostgreSQL 이 있고 단일 VM 규모에서 새 인프라 하나는 운영 부담 하나다 — 로드맵 §3.1 ENGINE-2 1).
  sqlite(테스트)는 SKIP LOCKED 가 없어 단순 select+update 로 같은 의미를 낸다(한 프로세스 안에서만 배타).

세션 소유
  run_records 는 호출자 세션에 flush 만 하지만, 이 모듈의 claim·heartbeat·reclaim 은 **커밋한다** — 워커가 자기 세션을 소유하고,
  잡았다는 사실은 다른 워커가 즉시 봐야 하기 때문이다. enqueue 는 생산자(호출부)의 트랜잭션에 들어가므로 flush 만 한다.

회수
  heartbeat 가 끊긴 running run 은 failed 로 **확정**한다(재실행하지 않는다). 어디까지 갔는지 — 부작용 노드(메일·게시)를
  지났는지 — 모르기 때문이다. 마지막 완료 step 부터의 재개는 노드 멱등성(ENGINE-3)과 함께 온다.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

import models
import run_records

RESERVED_OPTION_KEYS = ("stop_node_id", "scope_node_ids", "pinned_outputs", "user_inputs")
STALE_AFTER_SECONDS_DEFAULT = 120.0

# 생산자 스위치(ENGINE-2 2단계). 켜면 결과를 기다리지 않는 경로(스케줄·웹훅)가 인라인 실행 대신 enqueue 한다.
# 결과를 동기로 기다리는 경로(에디터 수동 실행·dry-run·앱·봇·/api/call)는 그대로 인라인이다 — 큐로 보내면 클라이언트가
# 폴링·구독으로 바뀌어야 하고 그건 33번 APP-2 의 몫이다. 켰으면 워커가 있어야 한다(run_worker.py 프로세스 또는
# EXECUTION_WORKER_INPROCESS=1) — 없으면 queued 가 쌓이기만 한다. main 이 시작할 때 경고한다.
QUEUE_ENV = "EXECUTION_QUEUE"


def queue_enabled() -> bool:
    return (os.getenv(QUEUE_ENV) or "0").strip().lower() in {"1", "true", "on", "yes"}


# 큐 정지 판정(/api/ready checks.queue, ENGINE-2 3단계 · 로드맵 37번 O-2). queued 가 이 시간 넘게 기다리는데 heartbeat 를 찍는
# running 이 하나도 없으면 "일은 쌓이는데 워커가 없다" 다. 한 워커가 긴 run 을 잡고 있어 queued 가 기다리는 것은 적체지 정지가
# 아니다 — 그건 depth 로만 보인다.
STALL_ENV = "RUN_QUEUE_STALL_SECONDS"
STALL_AFTER_SECONDS_DEFAULT = 300.0


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def stall_threshold_seconds() -> float:
    return _float_env(STALL_ENV, STALL_AFTER_SECONDS_DEFAULT)


def worker_stale_seconds() -> float:
    """run_worker 가 stale 확정에 쓰는 것과 같은 값 — 이보다 오래된 heartbeat 는 "살아 있는 워커" 의 증거가 아니다."""
    return _float_env("RUN_WORKER_STALE_SECONDS", STALE_AFTER_SECONDS_DEFAULT)


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _is_postgres(db) -> bool:
    try:
        return str(db.get_bind().dialect.name) == "postgresql"
    except Exception:  # pragma: no cover — bind 가 없는 세션
        return False


def enqueue(db, *, nodes: list, edges: list, trigger_source: str, project_id=None, executor_user_id=None,
            session_id=None, runtime_inputs: Optional[dict] = None, options: Optional[dict] = None,
            engine: Optional[str] = None, idempotency_key: Optional[str] = None) -> models.WorkflowRun:
    """queued run 을 만든다(flush 만 — 커밋은 생산자가). 워커가 잡아 실행한다.

    runtime_inputs 는 직렬화 가능한 것만 저장된다(approval_service.serializable_runtime_inputs). options 는 stop_node_id·
    scope_node_ids·pinned_outputs·user_inputs — 실행 시 execution.start 의 명시 인자로 들어간다.
    idempotency_key 는 unique 컬럼이다 — 같은 키가 이미 있으면 flush/commit 에서 IntegrityError. 생산자가 미리 find_by_idempotency_key
    로 보고, 경쟁에서 진 쪽은 IntegrityError 를 "이미 들어갔다" 로 읽는다(스케줄 슬롯 키 — schedule_slot_key; 웹훅·RSS 는 ENGINE-3).
    """
    import execution
    from approval_service import serializable_runtime_inputs

    if trigger_source not in execution.TRIGGER_SOURCES:
        raise ValueError(f"trigger_source={trigger_source!r} 는 허용 목록에 없다: {sorted(execution.TRIGGER_SOURCES)}")
    pid = None
    if project_id is not None:
        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            pid = None
    owner_user_id = None
    if pid is not None:
        project = db.query(models.Project).filter(models.Project.id == pid).first()
        owner_user_id = project.user_id if project is not None else None
    unknown = set(options or {}) - set(RESERVED_OPTION_KEYS)
    if unknown:
        raise ValueError(f"options 에 모르는 키가 있다: {sorted(unknown)} — 허용: {RESERVED_OPTION_KEYS}")
    now = _now()
    run = models.WorkflowRun(
        project_id=pid,
        trigger_source=trigger_source,
        engine=engine or execution.engine_mode(pid),
        status=run_records.STATUS_QUEUED,
        executor_user_id=executor_user_id,
        owner_user_id=owner_user_id if owner_user_id is not None else executor_user_id,
        session_id=str(session_id) if session_id is not None else None,
        started_at=now,          # claim 때 실제 시작 시각으로 덮는다(NOT NULL 컬럼)
        queued_at=now,
        graph_snapshot={"nodes": list(nodes or []), "edges": list(edges or [])},
        runtime_inputs=serializable_runtime_inputs(dict(runtime_inputs or {})),
        run_options=dict(options or {}),
        idempotency_key=str(idempotency_key) if idempotency_key else None,
    )
    db.add(run)
    db.flush()
    return run


def claim(db, worker_id: str) -> Optional[models.WorkflowRun]:
    """queued 하나를 이 워커의 running 으로 바꾼다. 없으면 None. **커밋한다.**"""
    if _is_postgres(db):
        row = db.execute(
            text("SELECT id FROM workflow_runs WHERE status = :queued ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"),
            {"queued": run_records.STATUS_QUEUED},
        ).first()
        run = db.get(models.WorkflowRun, row[0]) if row else None
    else:
        run = (db.query(models.WorkflowRun).filter(models.WorkflowRun.status == run_records.STATUS_QUEUED)
               .order_by(models.WorkflowRun.id.asc()).first())
    if run is None:
        db.rollback()  # 트랜잭션을 닫아 잠금·스냅샷을 남기지 않는다
        return None
    now = _now()
    run.status = run_records.STATUS_RUNNING
    run.worker_id = str(worker_id)
    run.claimed_at = now
    run.started_at = now
    run.heartbeat_at = now
    run.attempts = int(run.attempts or 0) + 1
    db.commit()
    db.refresh(run)
    return run


def heartbeat(db, run_id: int, worker_id: str) -> bool:
    """이 워커가 잡고 있는 running run 의 heartbeat_at 을 갱신한다. 남의 run 이거나 running 이 아니면 False. **커밋한다.**"""
    updated = (db.query(models.WorkflowRun)
               .filter(models.WorkflowRun.id == int(run_id), models.WorkflowRun.worker_id == str(worker_id),
                       models.WorkflowRun.status == run_records.STATUS_RUNNING)
               .update({"heartbeat_at": _now()}, synchronize_session=False))
    db.commit()
    return bool(updated)


def reclaim_stale(db, *, older_than_seconds: float = STALE_AFTER_SECONDS_DEFAULT, now=None) -> List[int]:
    """heartbeat 가 끊긴 running run 을 failed 로 확정한다. 돌려주는 값은 확정한 run id 목록. **커밋한다.**"""
    cutoff = (now or _now()) - datetime.timedelta(seconds=float(older_than_seconds))
    rows = (db.query(models.WorkflowRun)
            .filter(models.WorkflowRun.status == run_records.STATUS_RUNNING,
                    models.WorkflowRun.worker_id.isnot(None),
                    models.WorkflowRun.heartbeat_at.isnot(None),
                    models.WorkflowRun.heartbeat_at < cutoff)
            .all())
    finished = now or _now()
    ids: List[int] = []
    for run in rows:
        last = run.heartbeat_at.isoformat() if run.heartbeat_at else "?"
        run.status = run_records.STATUS_FAILED
        run.finished_at = finished
        run.error_summary = (f"워커 heartbeat 끊김 — worker={run.worker_id}, 마지막 heartbeat {last}. "
                             f"어디까지 실행됐는지 알 수 없어 실패로 확정했다(재실행은 하지 않는다).")[:run_records.ERROR_SUMMARY_CHARS]
        ids.append(run.id)
    if ids:
        db.commit()
    return ids


def execute_arguments(run: models.WorkflowRun) -> Dict[str, Any]:
    """claim 한 run 을 execution.start 로 돌릴 때의 인자. 예약 키는 runtime_inputs 에서 빼고 명시 인자로 준다."""
    snapshot = run.graph_snapshot or {}
    options = dict(run.run_options or {})
    inputs = {k: v for k, v in (run.runtime_inputs or {}).items()
              if k not in run_records.RESERVED_RUNTIME_KEYS and k not in RESERVED_OPTION_KEYS}
    kwargs: Dict[str, Any] = {
        "session_id": run.session_id,
        "project_id": run.project_id,
        "executor_user_id": run.executor_user_id,
    }
    for key in ("stop_node_id", "scope_node_ids", "pinned_outputs", "user_inputs"):
        if options.get(key) is not None:
            kwargs[key] = options[key]
    if run.resume_node_id:
        kwargs["entry_node_id"] = run.resume_node_id
        kwargs["approval_payload"] = run.resume_payload if run.resume_payload is not None else ""
    kwargs.update(inputs)
    return {"nodes": list(snapshot.get("nodes") or []), "edges": list(snapshot.get("edges") or []), "kwargs": kwargs}


def execute_claimed(db, run: models.WorkflowRun) -> Tuple[str, dict, list]:
    """claim 한 run 을 실행한다 — 같은 run 행에 기록이 이어진다(execution.start(existing_run_id=…))."""
    import execution

    args = execute_arguments(run)
    return execution.start(args["nodes"], args["edges"], trigger_source=run.trigger_source, existing_run_id=run.id,
                           db=db, **args["kwargs"])


def queue_depth(db) -> int:
    return db.query(models.WorkflowRun).filter(models.WorkflowRun.status == run_records.STATUS_QUEUED).count()


def schedule_slot_key(project_id, now=None) -> str:
    """스케줄 발화 슬롯의 idempotency_key — 분 단위(cron 의 최소 단위). 같은 슬롯은 인스턴스가 몇 개든 run 하나다."""
    stamp = (now or _now()).strftime("%Y-%m-%dT%H:%M")
    return f"schedule:{int(project_id)}:{stamp}"


def find_by_idempotency_key(db, key: str) -> Optional[models.WorkflowRun]:
    return run_records.find_by_idempotency_key(db, key)


def enqueue_or_existing(db, *, idempotency_key: str, **enqueue_kwargs) -> Tuple[models.WorkflowRun, bool]:
    """같은 키의 run 이 있으면 (그것, False), 없으면 새로 넣고 (새 run, True) — 웹훅 재전송·스케줄 슬롯의 중복 제거(ENGINE-3 4단계).
    조회와 INSERT 사이의 경쟁은 unique 가 막는다 — IntegrityError 면 롤백 뒤 기존 run 을 읽는다(호출자 세션에 미커밋 작업이 없어야
    한다 — 생산자 경로는 그렇다)."""
    from sqlalchemy.exc import IntegrityError

    existing = find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        return existing, False
    try:
        return enqueue(db, idempotency_key=idempotency_key, **enqueue_kwargs), True
    except IntegrityError:
        db.rollback()
        existing = find_by_idempotency_key(db, idempotency_key)
        if existing is None:
            raise
        return existing, False


def queue_health(db, *, stall_after_seconds: Optional[float] = None, heartbeat_fresh_seconds: Optional[float] = None,
                 now=None) -> Dict[str, Any]:
    """큐가 살아 있는가 — /api/ready 와 배포 스모크가 본다.

    stalled = queued 가 stall 임계보다 오래 기다리는데, 최근(heartbeat_fresh_seconds 안) heartbeat 를 찍은 running 이 없다 —
    "일은 쌓이는데 워커가 없다". 워커가 긴 run 을 잡고 있어 queued 가 기다리는 것은 적체(depth)일 뿐 정지가 아니다.
    worker_id 가 없는 running 은 인라인 실행이라 워커의 증거로 세지 않는다.
    """
    now = now or _now()
    stall = float(stall_after_seconds if stall_after_seconds is not None else stall_threshold_seconds())
    fresh = float(heartbeat_fresh_seconds if heartbeat_fresh_seconds is not None else worker_stale_seconds())
    queued = db.query(models.WorkflowRun).filter(models.WorkflowRun.status == run_records.STATUS_QUEUED)
    depth = queued.count()
    oldest_wait: Optional[float] = None
    if depth:
        oldest = queued.order_by(models.WorkflowRun.queued_at.asc(), models.WorkflowRun.id.asc()).first()
        since = oldest.queued_at or oldest.started_at
        oldest_wait = max(0.0, (now - since).total_seconds()) if since is not None else None
    running_q = db.query(models.WorkflowRun).filter(models.WorkflowRun.status == run_records.STATUS_RUNNING,
                                                     models.WorkflowRun.worker_id.isnot(None))
    running = running_q.count()
    running_fresh = running_q.filter(models.WorkflowRun.heartbeat_at.isnot(None),
                                     models.WorkflowRun.heartbeat_at >= now - datetime.timedelta(seconds=fresh)).count()
    stalled = bool(depth and oldest_wait is not None and oldest_wait >= stall and running_fresh == 0)
    return {
        "enabled": queue_enabled(),
        "depth": depth,
        "oldest_wait_seconds": None if oldest_wait is None else int(oldest_wait),
        "running": running,
        "running_fresh": running_fresh,
        "stalled": stalled,
        "stall_after_seconds": int(stall),
    }
