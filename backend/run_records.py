"""run_records.py — 실행 상태 기록: workflow_runs · run_steps (백로그 32 ENGINE-1 1단계, ADR-0028).

왜 이 모듈이 있나
  FlowExecutionLog 는 "누가 얼마를 썼나"(과금·사용량)의 사건이고 호출부 11곳이 각자 기록한다. 그 표에는 어느 경로로
  시작했는지(trigger_source)·어느 엔진이 돌았는지·대기 중인지·어디까지 갔는지 같은 **실행 상태**가 없다. 큐/워커
  (ENGINE-2)와 재시도·멱등성(ENGINE-3)은 실행 상태 위에서만 만들 수 있다. 그래서 실행의 단일 진입점(execution.start)
  이 실행마다 하나의 run 을 만들고, 끝나면 노드 단위 step 을 남긴다.

어디에 쓰나
  **호출자의 세션(db)에, flush 만 한다.** 커밋은 호출자가 FlowExecutionLog 를 남길 때 함께 한다 — 실행 기록과 과금
  기록이 같은 트랜잭션에 있어야 한 쪽만 남는 일이 없다. 별도 세션으로 즉시 커밋하지 않는 이유는 sqlite(테스트)에서
  연결이 공유되고, PostgreSQL 에서는 호출자의 트랜잭션과 엇갈린 상태가 남기 때문이다. 실시간 진행 표시는 DB 를
  폴링하지 않고 프로세스 안 SSE(ENGINE-1 3단계)로 한다 — 그래서 여기 행이 트랜잭션 끝까지 보이지 않아도 된다.

step 은 실행이 끝난 뒤 __execution_logs__ 에서 만든다
  두 엔진(legacy exec·interpreter)이 같은 log_step 기록을 남기므로 엔진과 무관하게 같은 step 이 나온다. 노드 경계에서
  실시간으로 쓰는 것은 인터프리터의 _Executor.run_item 에 얹을 수 있지만(ENGINE-1 3단계), 기록의 정본은 이 사후
  변환이다 — legacy 엔진이 살아 있는 동안 두 경로가 같은 표를 채워야 하기 때문이다.

실패해도 실행을 막지 않는다
  기록은 부수 기능이다. begin/finish/fail 이 던진 예외는 execution.start 가 잡아 경고만 남기고 실행 결과는 그대로 돌려준다.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import models
from node_errors import runtime as node_error_runtime

RUN_RECORDS_ENV = "RUN_RECORDS"   # "0" 이면 기록하지 않는다(장애 시 끄는 스위치)

STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_PAUSED = "paused"

# log_step 의 status → run_steps.status. 고정 출력(pinned)은 별도 상태다 — "실제 실행이 아니다" 를 표에서도 구분한다.
STEP_STATUS = {"success": "succeeded", "error": "failed", "waiting": "waiting"}
OUTPUT_PREVIEW_CHARS = 2000
ERROR_SUMMARY_CHARS = 500


def enabled() -> bool:
    return (os.getenv(RUN_RECORDS_ENV) or "1").strip().lower() not in {"0", "false", "off", "no"}


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _parse_time(value) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None


def begin(db, *, trigger_source: str, engine: str, project_id=None, executor_user_id=None,
          session_id=None) -> models.WorkflowRun:
    """실행 시작 — status=running 행을 만들고 flush 해 id 를 얻는다. 소유자는 프로젝트가 있으면 프로젝트 소유자."""
    owner_user_id = None
    pid = None
    if project_id is not None:
        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            pid = None
    if pid is not None:
        project = db.query(models.Project).filter(models.Project.id == pid).first()
        owner_user_id = project.user_id if project is not None else None
    now = _now()
    run = models.WorkflowRun(
        project_id=pid,
        trigger_source=trigger_source,
        engine=engine,
        status=STATUS_RUNNING,
        executor_user_id=executor_user_id,
        owner_user_id=owner_user_id if owner_user_id is not None else executor_user_id,
        session_id=str(session_id) if session_id is not None else None,
        started_at=now,
        heartbeat_at=now,
    )
    db.add(run)
    db.flush()
    return run


def run_status(result_text: Any, logs: Optional[List[dict]]) -> str:
    """'paused' | 'failed' | 'succeeded'. 승인 대기(waiting step)가 있으면 paused, 아니면 flow_outcome 을 따른다."""
    for step in logs or []:
        if isinstance(step, dict) and step.get("status") == "waiting":
            return STATUS_PAUSED
    return STATUS_FAILED if node_error_runtime.flow_outcome(result_text, logs) == "error" else STATUS_SUCCEEDED


def error_summary(result_text: Any, logs: Optional[List[dict]]) -> Optional[str]:
    """실패 요약 한 줄. 실행 엔진 수준 실패(노드가 잡지 못한 예외)는 결과 문자열('► Flow N Error: …')이 예외 문구를
    그대로 담고 있어 그것이 가장 쓸모 있다. 노드 수준 실패는 첫 구조화 오류의 사용자 문구, 둘 다 없으면 결과 앞부분."""
    summary = node_error_runtime.summarize_logs(logs)
    text = str(result_text or "").strip()
    if summary["runtime_failed"] and text:
        return text[:ERROR_SUMMARY_CHARS]
    for item in summary["errors"]:
        error = item.get("error") or {}
        message = error.get("userMessage") or item.get("error_message")
        if message:
            return str(message)[:ERROR_SUMMARY_CHARS]
    return text[:ERROR_SUMMARY_CHARS] if text else None


def steps_from_logs(run_id: int, logs: Optional[List[dict]], tokens: Optional[dict]) -> List[models.RunStep]:
    node_tokens: Dict[str, Any] = {}
    if isinstance(tokens, dict) and isinstance(tokens.get("nodes"), dict):
        node_tokens = tokens["nodes"]
    steps: List[models.RunStep] = []
    for sequence, step in enumerate((s for s in (logs or []) if isinstance(s, dict)), start=1):
        node_id = str(step.get("node_id") or "")
        raw_status = str(step.get("status") or "success")
        status = "pinned" if step.get("pinned") else STEP_STATUS.get(raw_status, raw_status)
        result = step.get("result_data")
        preview = str(result)[:OUTPUT_PREVIEW_CHARS] if result is not None else None
        steps.append(models.RunStep(
            run_id=run_id,
            sequence=sequence,
            node_id=node_id,
            node_type=step.get("node_type"),
            attempt=1,
            status=status,
            started_at=_parse_time(step.get("start_time")),
            finished_at=_parse_time(step.get("end_time")),
            output_preview=preview,
            tokens=node_tokens.get(node_id),
            error=step.get("error"),
        ))
    return steps


def finish(db, run: models.WorkflowRun, *, result_text: Any, tokens: Optional[dict], logs: Optional[List[dict]]) -> models.WorkflowRun:
    """실행이 결과를 돌려준 뒤 — 상태·요약·토큰·step 을 채운다. 커밋은 호출자가."""
    from usage_tracking import total_tokens_from_usage

    now = _now()
    run.status = run_status(result_text, logs)
    run.finished_at = None if run.status == STATUS_PAUSED else now
    run.heartbeat_at = now
    run.total_tokens = total_tokens_from_usage(tokens if isinstance(tokens, dict) else {})
    run.error_summary = error_summary(result_text, logs) if run.status == STATUS_FAILED else None
    steps = steps_from_logs(run.id, logs, tokens)
    db.add_all(steps)
    run.step_count = len(steps)
    db.flush()
    return run


def fail(db, run: models.WorkflowRun, exc: BaseException) -> models.WorkflowRun:
    """실행 엔진이 예외를 밖으로 던졌다(호출자에게 그대로 올라간다) — 기록만 실패로 닫는다."""
    now = _now()
    run.status = STATUS_FAILED
    run.finished_at = now
    run.heartbeat_at = now
    run.error_summary = f"{type(exc).__name__}: {exc}"[:ERROR_SUMMARY_CHARS]
    db.flush()
    return run


def looks_like_session(db) -> bool:
    """호출자가 넘긴 db 가 기록을 받을 수 있는 세션인가 — 테스트가 문자열 자리표시자를 넘기는 경우가 있다."""
    return all(hasattr(db, name) for name in ("add", "flush", "query"))


# ── 조회 · 직렬화 (타임라인 API) ─────────────────────────────────────────────
def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def public_step(step: models.RunStep) -> Dict[str, Any]:
    return {
        "sequence": step.sequence,
        "nodeId": step.node_id,
        "nodeType": step.node_type,
        "attempt": step.attempt,
        "status": step.status,
        "startedAt": _iso(step.started_at),
        "finishedAt": _iso(step.finished_at),
        "outputPreview": step.output_preview,
        "tokens": step.tokens,
        "error": step.error,
    }


def public_run(run: models.WorkflowRun, *, with_steps: bool = False) -> Dict[str, Any]:
    payload = {
        "id": run.id,
        "projectId": run.project_id,
        "triggerSource": run.trigger_source,
        "engine": run.engine,
        "status": run.status,
        "executorUserId": run.executor_user_id,
        "ownerUserId": run.owner_user_id,
        "sessionId": run.session_id,
        "startedAt": _iso(run.started_at),
        "finishedAt": _iso(run.finished_at),
        "heartbeatAt": _iso(run.heartbeat_at),
        "errorSummary": run.error_summary,
        "totalTokens": run.total_tokens,
        "stepCount": run.step_count,
    }
    if with_steps:
        payload["steps"] = [public_step(step) for step in run.steps]
    return payload


def list_runs(db, project_id: int, *, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """프로젝트의 실행 목록, 최신 먼저. step 은 싣지 않는다(상세에서)."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    rows = (db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == int(project_id))
            .order_by(models.WorkflowRun.id.desc()).offset(offset).limit(limit).all())
    return [public_run(run) for run in rows]
