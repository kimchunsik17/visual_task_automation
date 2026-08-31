"""node_errors/runtime.py — 실행 엔진·API 가 문자열을 검색하지 않고 결과를 판정하는 통로 (ADR-0016 ERROR-1.4).

    step log 항목(graph.log_step 이 만든다)
      node_id, node_type, start_time, end_time, status, result_data, error_message,
      error: NodeError v1 dict | None

이 모듈의 함수들은 그 `error` 필드만 본다. 결과 문자열의 `❌`/`Error` 검색은 legacy 문구가 남은
경로의 fallback 으로만 남겨두고(`flow_outcome`), 그 fallback 이 발화한 횟수를 telemetry 로 셀 수
있게 `legacy_fallback` 을 함께 돌려준다 — 제거 시점을 수치로 정하기 위해서다.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

from .adapters import detect_legacy_pattern
from .contract import NodeError

FLAG_ENV = "NODE_ERROR_V1"
WORKFLOW_NODE_TYPE = "workflow"   # 노드가 아닌 실행 엔진 수준의 실패를 기록하는 step 의 node_type


def is_enabled() -> bool:
    """클라이언트 표시를 새 error 객체로 할지. 기본 켜짐. 문제가 생기면 0 으로 표시만 legacy 로 되돌린다 —
    내부 분기는 플래그와 무관하게 항상 구조화 객체를 우선한다(ADR-0016 되돌리기 절)."""
    return os.getenv(FLAG_ENV, "1").strip().lower() not in {"0", "false", "off", "no"}


def error_step(
    error: NodeError,
    *,
    node_id: str = "flow",
    node_type: str = WORKFLOW_NODE_TYPE,
    start_time: Optional[str] = None,
    result_data: Optional[str] = None,
) -> Dict[str, Any]:
    """생성 코드 바깥(실행 엔진 수준)에서 실패했을 때 로그에 넣는 step. 프론트는 node_id 가 그래프에
    없으면 노드 강조 없이 오류 카드만 그린다."""
    now = datetime.datetime.utcnow().isoformat()
    return {
        "node_id": node_id,
        "node_type": node_type,
        "start_time": start_time or now,
        "end_time": now,
        "status": "error",
        "result_data": result_data,
        "error_message": error.user_message,
        "error": error.to_dict(),
    }


def step_error(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    error = step.get("error") if isinstance(step, dict) else None
    return error if isinstance(error, dict) and error.get("code") else None


def summarize_logs(logs: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """구조화된 오류만 본 실행 요약. API 응답과 outcome 판정의 근거다."""
    errors: List[Dict[str, Any]] = []
    legacy = 0
    runtime_failed = False
    for step in logs or []:
        if not isinstance(step, dict):
            continue
        error = step_error(step)
        if error is None and step.get("status") == "error":
            # 구조화 없이 status 만 error 인 step(옛 경로) — 있으면 legacy 로 센다.
            legacy += 1
            errors.append({"node_id": step.get("node_id"), "node_type": step.get("node_type"), "error": None,
                           "error_message": step.get("error_message")})
            continue
        if error is None:
            continue
        if error.get("code") == "LEGACY_NODE_ERROR":
            legacy += 1
        if step.get("node_type") == WORKFLOW_NODE_TYPE:
            runtime_failed = True
        errors.append({"node_id": step.get("node_id"), "node_type": step.get("node_type"), "error": error,
                       "error_message": step.get("error_message")})
    return {
        "error_count": len(errors),
        "legacy_count": legacy,
        "runtime_failed": runtime_failed,
        "errors": errors,
        "first_error": errors[0]["error"] if errors else None,
    }


def flow_outcome(result_text: Any, logs: Optional[List[Dict[str, Any]]]) -> str:
    """'error' | 'success'. 구조화 step 을 먼저 보고, 없을 때만 legacy 문구 패턴으로 판정한다."""
    outcome, _ = flow_outcome_with_source(result_text, logs)
    return outcome


def flow_outcome_with_source(result_text: Any, logs: Optional[List[Dict[str, Any]]]) -> tuple:
    """(outcome, source) — source 는 'structured' | 'legacy_fallback' | 'none'. telemetry 용."""
    summary = summarize_logs(logs)
    if summary["error_count"]:
        return "error", "structured"
    if detect_legacy_pattern(str(result_text or "")) is not None:
        return "error", "legacy_fallback"
    return "success", "none"


def runtime_failure_message(logs: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """실행 엔진 수준 실패(생성 코드의 root except, exec 실패)의 사용자 문구. 없으면 None."""
    for step in logs or []:
        if isinstance(step, dict) and step.get("node_type") == WORKFLOW_NODE_TYPE and step_error(step):
            return step.get("error_message") or step["error"].get("userMessage")
    return None


def has_node_error(logs: Optional[List[Dict[str, Any]]], node_type: str) -> bool:
    """특정 노드 종류가 오류로 끝났는지 — discord_bot 처럼 결과 문자열을 뒤지던 곳의 대체."""
    return any(
        isinstance(step, dict) and step.get("node_type") == node_type and step.get("status") == "error"
        for step in logs or []
    )


def step_columns(step: Dict[str, Any]) -> Dict[str, Any]:
    """NodeExecutionLog 의 telemetry 컬럼 — node type·code·category·effectState 만. 사용자 입력·
    provider 원문은 여기 없다(ADR-0016 ERROR-4.3)."""
    error = step_error(step) or {}
    return {
        "error_code": error.get("code"),
        "error_category": error.get("category"),
        "effect_state": error.get("effectState"),
        "error_legacy": bool(error.get("code") == "LEGACY_NODE_ERROR") if error else (step.get("status") == "error"),
        "error_request_id": error.get("requestId"),
    }


def response_fields(result_text: Any, logs: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """`/api/execute` 등 실행 응답에 덧붙이는 구조화 필드."""
    summary = summarize_logs(logs)
    outcome, source = flow_outcome_with_source(result_text, logs)
    return {
        "error_schema": 1,
        "node_error_v1": is_enabled(),
        "outcome": outcome,
        "outcome_source": source,
        "errors": summary["errors"],
    }
