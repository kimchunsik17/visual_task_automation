"""error_trigger.py — 실패한 실행 뒤 지정 워크플로우를 부른다 (백로그 32 ENGINE-3 3단계, ADR-0030 추기).

설정
  실패하는 프로젝트의 `graph_data['errorWorkflowId']`(정수 project id). `is_live` 처럼 graph_data 안에 둔다 — 편집기가 그래프와 함께
  저장하고, 별도 컬럼·마이그레이션이 없다. 없거나 0 이면 꺼짐.

언제
  `execution.start` 가 실행을 **failed** 로 닫은 뒤 — 노드 오류로 결과가 error 인 경우와 엔진이 예외를 던진 경우 둘 다. 성공·paused 는
  아니다. 출처가 mock·evaluation(시험 실행)이거나 error_trigger(에러 워크플로우 자신)면 부르지 않는다.

무엇을
  에러 워크플로우를 `default_input` = 실패 payload JSON 으로 실행한다(webhookNode·봇 트리거가 읽는 키 — 에러 워크플로우는 보통
  "웹훅/시작 → 알림 노드" 모양이다). 큐가 켜져 있으면 enqueue 만 하고(워커가 실행·과금) 아니면 여기서 인라인으로 `execution.start` 를
  부르고 과금(record_usage, trigger_type 'error_trigger')도 남긴다 — 인라인 호출부가 자기 실행에 하는 것과 같다.

막는 것
  (1) 연쇄 금지 — 에러 워크플로우 자체의 실패는 다시 트리거하지 않는다(trigger_source == 'error_trigger'). (2) 자기 자신을 가리키면
  무시. (3) 소유자가 다르면 무시 — 남의 워크플로우를 내 실패로 돌릴 수 없다. (4) 에러 워크플로우의 예외·과금 실패는 원래 실패를 바꾸지
  않는다(로그만). (5) 인라인 실행이 직전 실행의 run id 슬롯(execution.take_last_run_id)을 덮지 않게 보존한다 — 덮이면 원래 실행의
  FlowExecutionLog 가 run 과 이어지지 않는다.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

import models
import run_records
from node_errors import runtime as node_error_runtime

logger = logging.getLogger("error_trigger")

SETTING_KEY = "errorWorkflowId"
TRIGGER_SOURCE = "error_trigger"
# 시험 실행은 알림을 내지 않는다 — 목업 탭·평가 러너의 실패는 사용자가 보고 있는 화면 안의 일이다.
SILENT_SOURCES = frozenset({"mock", "evaluation", TRIGGER_SOURCE})
MAX_FAILED_NODES = 20


def configured_error_workflow_id(project) -> Optional[int]:
    """graph_data 의 설정값. 없거나 0 이거나 정수가 아니면 None."""
    data = project.graph_data if isinstance(getattr(project, "graph_data", None), dict) else {}
    raw = data.get(SETTING_KEY)
    if raw in (None, "", 0, "0", False):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def build_payload(*, project, run, trigger_source: str, result_text: Any, logs: Optional[List[dict]],
                  exc: Optional[BaseException] = None) -> Dict[str, Any]:
    """에러 워크플로우가 받는 입력. 오류 계약의 공개 필드만 — 원문 예외 스택·비밀은 없다."""
    summary = node_error_runtime.summarize_logs(logs)
    failed_nodes = []
    for step in summary["errors"][:MAX_FAILED_NODES]:
        error = step.get("error") or {}
        failed_nodes.append({
            "nodeId": step.get("node_id"),
            "nodeType": step.get("node_type"),
            "code": error.get("code") or "LEGACY_NODE_ERROR",
            "message": error.get("userMessage") or step.get("error_message"),
        })
    if run is not None and run.error_summary:
        error_summary = run.error_summary
    elif exc is not None:
        error_summary = f"{type(exc).__name__}: {exc}"
    else:
        error_summary = run_records.error_summary(result_text, logs)
    return {
        "event": "workflow_failed",
        "failedProjectId": project.id,
        "failedProjectTitle": project.title,
        "runId": run.id if run is not None else None,
        "triggerSource": trigger_source,
        "errorSummary": (str(error_summary)[:500] if error_summary else None),
        "failedNodes": failed_nodes,
        "at": datetime.datetime.utcnow().isoformat(),
    }


def fire(db, *, project_id, trigger_source: str, run=None, result_text: Any = None, logs: Optional[List[dict]] = None,
         exc: Optional[BaseException] = None, executor_user_id=None) -> Optional[int]:
    """실패한 실행 뒤 호출된다. 조건이 맞으면 에러 워크플로우 run 을 만들고 그 id 를 돌려준다(큐: queued run, 인라인: 끝난 run).
    조건이 안 맞으면 None — 실행을 부르지 않은 이유는 로그로만."""
    if db is None or project_id is None or trigger_source in SILENT_SOURCES:
        return None
    if not run_records.looks_like_session(db):   # 테스트가 자리표시자 문자열을 db 로 넘기는 경우
        return None
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None
    project = db.query(models.Project).filter(models.Project.id == pid).first()
    if project is None:
        return None
    target_id = configured_error_workflow_id(project)
    if target_id is None:
        return None
    if target_id == project.id:
        logger.warning("[error-trigger] project %s 의 errorWorkflowId 가 자기 자신이다 — 무시", project.id)
        return None
    target = db.query(models.Project).filter(models.Project.id == target_id).first()
    if target is None:
        logger.warning("[error-trigger] project %s 의 errorWorkflowId=%s 가 없는 프로젝트다 — 무시", project.id, target_id)
        return None
    if target.user_id != project.user_id:
        logger.warning("[error-trigger] project %s 의 errorWorkflowId=%s 는 다른 소유자의 것이다 — 무시", project.id, target_id)
        return None

    graph_data = target.graph_data if isinstance(target.graph_data, dict) else {}
    nodes = list(graph_data.get("nodes") or [])
    edges = list(graph_data.get("edges") or [])
    payload = build_payload(project=project, run=run, trigger_source=trigger_source, result_text=result_text, logs=logs, exc=exc)
    payload_json = json.dumps(payload, ensure_ascii=False)
    session_id = f"error_{project.id}"

    import run_queue

    if run_queue.queue_enabled():
        queued = run_queue.enqueue(db, nodes=nodes, edges=edges, trigger_source=TRIGGER_SOURCE, project_id=target.id,
                                   executor_user_id=executor_user_id, session_id=session_id,
                                   runtime_inputs={"default_input": payload_json})
        logger.info("[error-trigger] project %s 실패 → 에러 워크플로우 %s 를 큐에 넣었다(run %s)", project.id, target.id, queued.id)
        return queued.id
    return _run_inline(db, target, nodes, edges, payload_json, session_id=session_id, executor_user_id=executor_user_id,
                       failed_project_id=project.id)


def _run_inline(db, target, nodes, edges, payload_json: str, *, session_id: str, executor_user_id, failed_project_id) -> Optional[int]:
    import execution
    from usage_tracking import EVENT_WORKFLOW_EXECUTION, record_usage

    with execution.preserving_last_run():
        try:
            result_text, tokens, logs = execution.start(nodes, edges, trigger_source="error_trigger", db=db, project_id=target.id,
                                                        session_id=session_id, executor_user_id=executor_user_id,
                                                        default_input=payload_json)
        except Exception as inner:  # 원래 실패를 바꾸지 않는다 — execution.start 가 failed 기록은 flush 해 두었다
            logger.error("[error-trigger] 에러 워크플로우 %s 실행 예외: %s: %s", target.id, type(inner).__name__, inner)
            return None
        run_id = _last_run_id_for(db, target.id)
        try:
            record_usage(
                db,
                billable_user_id=target.user_id,
                actor_user_id=executor_user_id,
                project_id=target.id,
                token_usage=tokens if isinstance(tokens, dict) else None,
                payload=json.dumps({"errorTrigger": True, "failedProjectId": failed_project_id}, ensure_ascii=False),
                result=result_text,
                event_type=EVENT_WORKFLOW_EXECUTION,
                outcome=node_error_runtime.flow_outcome(result_text, logs),
                trigger_type=TRIGGER_SOURCE,
            )
        except Exception as billing:
            logger.warning("[error-trigger] 에러 워크플로우 %s 과금 기록 실패(실행 기록은 남긴다): %s: %s", target.id,
                           type(billing).__name__, billing)
    logger.info("[error-trigger] project %s 실패 → 에러 워크플로우 %s 인라인 실행(run %s)", failed_project_id, target.id, run_id)
    return run_id


def _last_run_id_for(db, project_id) -> Optional[int]:
    try:
        run = (db.query(models.WorkflowRun)
               .filter(models.WorkflowRun.project_id == int(project_id), models.WorkflowRun.trigger_source == TRIGGER_SOURCE)
               .order_by(models.WorkflowRun.id.desc()).first())
        return run.id if run is not None else None
    except Exception:  # 실행 기록이 꺼져 있거나(RUN_RECORDS=0) 표가 없다
        return None
