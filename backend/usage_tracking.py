"""Canonical usage logging and compatibility migration helpers."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import models


EVENT_WORKFLOW_EXECUTION = "workflow_execution"
EVENT_WORKFLOW_GENERATION = "workflow_generation"
EVENT_APP_GENERATION = "app_generation"
EVENT_EVALUATION = "evaluation"

OUTCOME_SUCCESS = "success"
OUTCOME_ERROR = "error"
OUTCOME_CANCELLED = "cancelled"


def total_tokens_from_usage(token_usage: Any) -> int:
    if not isinstance(token_usage, dict):
        return 0
    try:
        return max(0, int(token_usage.get("total_tokens", 0) or 0))
    except (TypeError, ValueError):
        return 0


def outcome_from_result(result: Any, error_message: Optional[str] = None) -> str:
    if error_message:
        return OUTCOME_ERROR
    text_result = str(result or "")
    error_markers = ("❌", "Error", "error", "실패", "오류")
    return OUTCOME_ERROR if any(marker in text_result for marker in error_markers) else OUTCOME_SUCCESS


def legacy_event_type(status: Optional[str], token_usage_details: Any = None) -> str:
    details = token_usage_details if isinstance(token_usage_details, dict) else {}
    explicit_type = details.get("usage_type")
    raw_type = explicit_type or status
    if raw_type in {"agent", "workflow_generation"}:
        return EVENT_WORKFLOW_GENERATION
    if raw_type in {"app_builder", "app_agent", "app_generation"}:
        return EVENT_APP_GENERATION
    if raw_type == "evaluation":
        return EVENT_EVALUATION
    return EVENT_WORKFLOW_EXECUTION


def usage_bucket(event_type: Optional[str], status: Optional[str] = None, token_usage_details: Any = None) -> str:
    normalized = event_type or legacy_event_type(status, token_usage_details)
    return {
        EVENT_WORKFLOW_EXECUTION: "execution",
        EVENT_WORKFLOW_GENERATION: "agent",
        EVENT_APP_GENERATION: "app_builder",
        EVENT_EVALUATION: "evaluation",
    }.get(normalized, "execution")


def usage_outcome(outcome: Optional[str], status: Optional[str], error_message: Optional[str] = None) -> str:
    if outcome in {OUTCOME_SUCCESS, OUTCOME_ERROR, OUTCOME_CANCELLED}:
        return outcome
    if status in {OUTCOME_SUCCESS, OUTCOME_ERROR, OUTCOME_CANCELLED}:
        return status
    return OUTCOME_ERROR if error_message else OUTCOME_SUCCESS


def redact_payload_secrets(payload: Optional[str]) -> Optional[str]:
    """실행 로그로 저장되는 payload JSON에서 자격증명성 값을 마스킹한다 (P0,
    INCOMPLETE_NODE_STRUCTURE_REVIEW §4.2 — "실행 로그는 전체 실행 payload를 기록하므로
    비밀번호가 포함된 DB URI도 기록 대상"이던 문제).

    노드 data 의 키 이름이 자격증명 패턴(connectionString, accessToken, apiKey 등 —
    generation_trace 와 같은 정규식)에 걸리면 값을 통째로 치환한다. API 센터 reference
    (`{{API_CENTER:...}}`)는 비밀이 아니므로 그대로 둔다. JSON 이 아니면 원문을 반환한다
    (기존 호출부 중 문자열 payload 를 넘기는 곳이 있어도 깨지지 않게).
    """
    if not payload:
        return payload
    from generation_trace import _SENSITIVE_DATA_KEY

    def _redact(value):
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED_CREDENTIAL]"
                    if isinstance(val, str) and val and not val.startswith("{{API_CENTER:")
                    and _SENSITIVE_DATA_KEY.search(str(key))
                    else _redact(val)
                )
                for key, val in value.items()
            }
        if isinstance(value, list):
            return [_redact(item) for item in value]
        return value

    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return payload
    return json.dumps(_redact(parsed), ensure_ascii=False)


def record_usage(
    db: Session,
    *,
    billable_user_id: Optional[int],
    actor_user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    token_usage: Optional[dict] = None,
    total_tokens: Optional[int] = None,
    payload: Optional[str] = None,
    result: Optional[str] = None,
    event_type: str = EVENT_WORKFLOW_EXECUTION,
    outcome: Optional[str] = None,
    trigger_type: str = "editor",
    error_message: Optional[str] = None,
    request_id: Optional[str] = None,
    deduct_balance: bool = True,
) -> models.FlowExecutionLog:
    """Add one usage event and its balance debit to the caller's transaction.

    The function intentionally does not commit. Callers may add node logs or other
    state and commit everything atomically.
    """

    normalized_usage = token_usage if isinstance(token_usage, dict) else {}
    normalized_total = total_tokens_from_usage(normalized_usage) if total_tokens is None else max(0, int(total_tokens or 0))
    normalized_outcome = outcome or outcome_from_result(result, error_message)

    if deduct_balance and billable_user_id is not None and normalized_total > 0:
        user = (
            db.query(models.User)
            .filter(models.User.id == billable_user_id)
            .with_for_update()
            .first()
        )
        if user is None:
            raise ValueError(f"Billable user {billable_user_id} does not exist")
        user.token_balance = int(user.token_balance or 0) - normalized_total

    log = models.FlowExecutionLog(
        # Legacy readers still treat user_id as the billed account.
        user_id=billable_user_id,
        actor_user_id=actor_user_id,
        billable_user_id=billable_user_id,
        project_id=project_id,
        payload=redact_payload_secrets(payload),
        result=result,
        total_tokens=normalized_total,
        token_usage_details=normalized_usage or None,
        event_type=event_type,
        outcome=normalized_outcome,
        trigger_type=trigger_type,
        request_id=request_id or uuid.uuid4().hex,
        status=normalized_outcome,
        error_message=error_message,
    )
    db.add(log)

    # 템플릿 품질 신호 (ADR-0023). 가져간 뒤 **실제로 돌았는지**가 설치 수·별점보다 정직하다.
    # 첫 실행 결과만 기록하고, 실패해도 실행 기록 자체에는 영향을 주지 않는다.
    if event_type == EVENT_WORKFLOW_EXECUTION and project_id:
        try:
            import community_templates

            community_templates.record_first_run(db, project_id, normalized_outcome)
        except Exception as exc:
            print(f"[templates] 첫 실행 결과 기록 실패: {exc}")

    return log


_USAGE_COLUMNS = {
    "actor_user_id": "INTEGER",
    "billable_user_id": "INTEGER",
    "event_type": "VARCHAR",
    "outcome": "VARCHAR",
    "trigger_type": "VARCHAR",
    "request_id": "VARCHAR",
}


def ensure_usage_tracking_schema(engine: Engine) -> None:
    """Add usage columns to installations created before this schema existed."""

    inspector = inspect(engine)
    if "flow_execution_logs" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("flow_execution_logs")}
    with engine.begin() as connection:
        # 두 인스턴스가 동시에 뜨면(배포 중 겹침 등) 같은 CREATE INDEX 를 나란히 실행해
        # 데드락이 나고, 이 함수는 import 시점에 불리므로 프로세스가 통째로 죽는다.
        # 실제로 배포 두 번 연속 발생했다 — advisory lock 으로 한 번에 하나만 들어오게 한다.
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 883120001})

        for name, sql_type in _USAGE_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE flow_execution_logs ADD COLUMN {name} {sql_type}"))

        connection.execute(text(
            "UPDATE flow_execution_logs "
            "SET billable_user_id = user_id "
            "WHERE billable_user_id IS NULL AND user_id IS NOT NULL"
        ))
        connection.execute(text(
            "UPDATE flow_execution_logs SET actor_user_id = user_id "
            "WHERE actor_user_id IS NULL AND user_id IS NOT NULL"
        ))
        connection.execute(text(
            "UPDATE flow_execution_logs SET event_type = CASE "
            "WHEN status = 'agent' THEN 'workflow_generation' "
            "WHEN status IN ('app_builder', 'app_agent') THEN 'app_generation' "
            "WHEN status = 'evaluation' THEN 'evaluation' "
            "ELSE 'workflow_execution' END "
            "WHERE event_type IS NULL"
        ))
        connection.execute(text(
            "UPDATE flow_execution_logs SET outcome = CASE "
            "WHEN status = 'error' THEN 'error' "
            "ELSE 'success' END "
            "WHERE outcome IS NULL"
        ))

        for column in ("billable_user_id", "actor_user_id", "event_type", "outcome", "trigger_type", "request_id"):
            connection.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_flow_execution_logs_{column} "
                f"ON flow_execution_logs ({column})"
            ))
