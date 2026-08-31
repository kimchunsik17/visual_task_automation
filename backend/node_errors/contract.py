"""node_errors/contract.py — NodeError v1 wire contract 와 NodeResult (ADR-0016).

    NodeError v1
      version, code, category, messageKey, userMessage, retryable,
      effectState, field, retryAfterMs, requestId, safeDetails

    NodeResult
      status: success | needs_input | waiting | error
      data | error 는 상호 배타 — 성공에 오류 문구를 섞을 수 없다

공개 payload 에는 catalog 문구와 허용된 safeDetails key 만 들어간다. 예외 원문·stack·provider
응답은 `records.ErrorRecord` 에 남고 requestId 로만 연결된다.

`str(NodeResult)` 는 **이행기 표시용 문자열**이다 — 노드 사이 값은 아직 문자열이라(ADR-0016 결과
절 참고) 실패 결과도 기존 `[⚠️ ...]` 관례로 렌더링해 하류 노드·evaluator 가 그대로 동작한다.
새 코드는 이 문자열을 검색하지 말고 `status/error` 를 읽는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import catalog, records
from .catalog import EFFECT_STATES, UNSAFE_TO_RETRY_EFFECT_STATES
from .redaction import redact_text

SCHEMA_VERSION = 1
RESULT_STATUSES = ("success", "needs_input", "waiting", "error")
# error 를 싣는 상태. needs_input 은 "실행하지 않았다"를 구분하는 오류다.
ERROR_STATUSES = frozenset({"error", "needs_input"})
MAX_SAFE_DETAIL_LENGTH = 200


class ContractViolation(ValueError):
    """계약을 어긴 호출 — 허용되지 않은 safeDetails key, 잘못된 effectState, data 와 error 동시 지정."""


@dataclass(frozen=True)
class NodeError:
    code: str
    category: str
    message_key: str
    user_message: str
    retryable: bool
    effect_state: str
    request_id: str
    field: Optional[str] = None
    retry_after_ms: Optional[int] = None
    safe_details: Optional[Dict[str, Any]] = None
    version: int = SCHEMA_VERSION

    # ── 파생 판단 ──────────────────────────────────────────────────────
    @property
    def safe_to_retry(self) -> bool:
        """자동 재시도 가능 여부. retryable 이어도 부수효과 상태가 불확실하면 False."""
        return bool(self.retryable) and self.effect_state not in UNSAFE_TO_RETRY_EFFECT_STATES

    @property
    def is_legacy(self) -> bool:
        return self.code == "LEGACY_NODE_ERROR"

    @property
    def resolution(self) -> str:
        try:
            return catalog.get(self.code).resolution
        except catalog.UnknownErrorCode:
            return "none"

    # ── 직렬화 ────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "code": self.code,
            "category": self.category,
            "messageKey": self.message_key,
            "userMessage": self.user_message,
            "retryable": self.retryable,
            "effectState": self.effect_state,
            "field": self.field,
            "retryAfterMs": self.retry_after_ms,
            "requestId": self.request_id,
            "safeDetails": self.safe_details,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NodeError":
        if not isinstance(payload, dict) or not payload.get("code"):
            raise ContractViolation("NodeError payload 에 code 가 없다")
        effect_state = payload.get("effectState") or "unknown"
        if effect_state not in EFFECT_STATES:
            raise ContractViolation(f"effectState '{effect_state}' 는 허용되지 않는다")
        version = int(payload.get("version") or SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ContractViolation(f"지원하지 않는 NodeError schema version {version}")
        return cls(
            code=str(payload["code"]),
            category=str(payload.get("category") or "runtime"),
            message_key=str(payload.get("messageKey") or "runtime.internal_unknown"),
            user_message=str(payload.get("userMessage") or ""),
            retryable=bool(payload.get("retryable", False)),
            effect_state=effect_state,
            request_id=str(payload.get("requestId") or records.new_request_id()),
            field=payload.get("field"),
            retry_after_ms=payload.get("retryAfterMs"),
            safe_details=payload.get("safeDetails"),
            version=version,
        )

    def legacy_note(self) -> str:
        """이행기 표시 문자열 — 기존 노드들이 쓰던 `[⚠️ ...]` 관례."""
        return f"[⚠️ {self.user_message}]"


def _filter_safe_details(code: str, details: Optional[Dict[str, Any]], allowed: List[str]) -> Optional[Dict[str, Any]]:
    if not details:
        return None
    unknown = [k for k in details if k not in allowed]
    if unknown:
        raise ContractViolation(
            f"{code}: safeDetails key {unknown} 는 catalog 허용 목록에 없다 — "
            f"허용: {allowed}. provider 원문·경로·credential 은 어떤 key 로도 넣지 않는다"
        )
    cleaned: Dict[str, Any] = {}
    for key, value in details.items():
        if value is None:
            continue
        if isinstance(value, str):
            cleaned[key] = redact_text(value, max_length=MAX_SAFE_DETAIL_LENGTH)
        elif isinstance(value, (int, float, bool)):
            cleaned[key] = value
        elif isinstance(value, (list, tuple)):
            cleaned[key] = [redact_text(v, max_length=MAX_SAFE_DETAIL_LENGTH) if isinstance(v, str) else v for v in value][:20]
        else:
            cleaned[key] = redact_text(str(value), max_length=MAX_SAFE_DETAIL_LENGTH)
    return cleaned or None


def make_error(
    code: str,
    *,
    field: Optional[str] = None,
    effect_state: Optional[str] = None,
    retryable: Optional[bool] = None,
    retry_after_ms: Optional[int] = None,
    safe_details: Optional[Dict[str, Any]] = None,
    user_message: Optional[str] = None,
    request_id: Optional[str] = None,
    cause: Optional[BaseException] = None,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    provider_code: Optional[str] = None,
    provider_status: Optional[int] = None,
    attempts: Optional[int] = None,
    internal_message: Any = None,
    record: bool = True,
) -> NodeError:
    """catalog 기본값 위에 이번 실패 인스턴스의 상태를 얹어 NodeError 를 만든다.

    - code 가 catalog 에 없으면 UnknownErrorCode(프로그래밍 오류 — 먼저 등록하라).
    - deprecated alias 는 대체 code 로 바꾼다(alias 는 내부 기록에 남긴다).
    - retryable 은 catalog 기본값 → 명시값 순이되, effectState 가 unknown/applied 면 항상 False.
    - safeDetails 는 허용 key 만 통과하고 문자열 값은 redaction 한다.
    - 항상 ErrorRecord 를 남긴다 — requestId 로 내부 진단을 찾을 수 있어야 하기 때문이다.
    """
    entry = catalog.resolve(code)
    alias = code if entry.code != code else None
    state = effect_state or entry.effectStateDefault
    if state not in EFFECT_STATES:
        raise ContractViolation(f"effectState '{state}' 는 허용되지 않는다 — {EFFECT_STATES}")
    final_retryable = entry.retryable if retryable is None else bool(retryable)
    if state in UNSAFE_TO_RETRY_EFFECT_STATES:
        final_retryable = False
    details = _filter_safe_details(entry.code, safe_details, entry.safeDetailKeys)
    message = user_message.strip() if isinstance(user_message, str) and user_message.strip() else entry.userMessage
    # 사용자 문구에 비밀이 실릴 일은 없어야 하지만, 호출자가 예외 문자열을 넘기는 실수는 막는다.
    message = redact_text(message, max_length=MAX_SAFE_DETAIL_LENGTH * 2)

    if record:
        final_request_id = records.remember(
            code=entry.code,
            request_id=request_id,
            node_type=node_type,
            node_id=node_id,
            cause=cause,
            message=internal_message,
            provider_code=provider_code,
            provider_status=provider_status,
            attempts=attempts,
            extra={"alias": alias} if alias else None,
        ).request_id
    else:
        # 재시도 판단처럼 표면화되지 않는 중간 변환 — 기록 없이 계약 객체만 만든다.
        final_request_id = request_id or records.new_request_id()
    return NodeError(
        code=entry.code,
        category=entry.category,
        message_key=entry.messageKey,
        user_message=message,
        retryable=final_retryable,
        effect_state=state,
        request_id=final_request_id,
        field=field,
        retry_after_ms=int(retry_after_ms) if retry_after_ms is not None else None,
        safe_details=details,
    )


def from_exception(
    exc: BaseException,
    *,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    field: Optional[str] = None,
    effect_state: Optional[str] = None,
) -> NodeError:
    """예상하지 못한 예외의 마지막 fallback. 절대 예외를 올리지 않는다.

    ConnectorError 는 canonical code 로 변환하고, 그 외 모든 예외는 내부 기록만 남긴 뒤
    INTERNAL_UNKNOWN 을 돌려준다. 새 분기를 여기 의존해 만들지 마라 — 발생률을 보고 반복 원인은
    구체적인 code 로 승격한다(ADR-0016 명명 규칙 6).
    """
    if isinstance(exc, NodeErrorException):
        return exc.error
    try:
        from connectors.errors import ConnectorError
        if isinstance(exc, ConnectorError):
            from .adapters import from_connector_error
            return from_connector_error(exc, node_type=node_type, node_id=node_id, field=field)
    except Exception:
        pass
    try:
        return make_error(
            "INTERNAL_UNKNOWN",
            field=field,
            effect_state=effect_state,
            cause=exc,
            node_type=node_type,
            node_id=node_id,
        )
    except Exception:  # catalog 조차 깨졌을 때 — 그래도 실행 로그는 남아야 한다
        record = records.remember(code="INTERNAL_UNKNOWN", cause=exc, node_type=node_type, node_id=node_id)
        return NodeError(
            code="INTERNAL_UNKNOWN", category="runtime", message_key="runtime.internal_unknown",
            user_message="예상하지 못한 오류가 발생했습니다. 요청 ID 와 함께 문의해주세요.",
            retryable=False, effect_state="unknown", request_id=record.request_id, field=field,
        )


class NodeErrorException(Exception):
    """NodeError 를 예외로 옮겨야 하는 경로용(실행기 → 생성 코드). `from_exception` 이 풀어낸다."""

    def __init__(self, error: NodeError):
        super().__init__(error.user_message)
        self.error = error


# ── NodeResult ───────────────────────────────────────────────────────────
@dataclass
class NodeResult:
    status: str
    data: Any = None
    error: Optional[NodeError] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    # 이행기 표시용. 하류 노드·API 결과 문자열이 아직 문자열이므로 성공/실패 각각의 표시를 정한다.
    display: Optional[str] = None
    # 발송 노드 관례 — 실패해도 만들려던 내용은 버리지 않는다. 표시 문자열 앞에 붙는다.
    passthrough: Optional[str] = None

    def __post_init__(self):
        if self.status not in RESULT_STATUSES:
            raise ContractViolation(f"NodeResult.status '{self.status}' 는 허용되지 않는다 — {RESULT_STATUSES}")
        if self.status in ERROR_STATUSES:
            if self.error is None:
                raise ContractViolation(f"status={self.status} 인 NodeResult 에는 error 가 있어야 한다")
            if self.data is not None:
                raise ContractViolation(f"status={self.status} 인 NodeResult 에 data 를 실을 수 없다 — 오류와 데이터는 상호 배타다")
        elif self.error is not None:
            raise ContractViolation(f"status={self.status} 인 NodeResult 에 error 를 실을 수 없다")

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @classmethod
    def success(cls, data: Any = None, *, display: Optional[str] = None, artifacts=None, metrics=None) -> "NodeResult":
        return cls(status="success", data=data, display=display, artifacts=list(artifacts or []), metrics=dict(metrics or {}))

    @classmethod
    def failure(cls, error: NodeError, *, passthrough: Optional[str] = None, display: Optional[str] = None, metrics=None) -> "NodeResult":
        return cls(status="error", error=error, passthrough=passthrough, display=display, metrics=dict(metrics or {}))

    @classmethod
    def needs_input(cls, error: NodeError, *, display: Optional[str] = None) -> "NodeResult":
        """입력이 비어 실행하지 않은 경우. 오류이되 status 로 구분한다 — 프론트가 '채워달라' 안내로 그린다."""
        return cls(status="needs_input", error=error, display=display)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "ok": self.ok,
            "status": self.status,
            "data": self.data,
            "artifacts": list(self.artifacts),
            "error": self.error.to_dict() if self.error else None,
            "metrics": dict(self.metrics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "NodeResult":
        version = int(payload.get("version") or SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ContractViolation(f"지원하지 않는 NodeResult schema version {version}")
        error = NodeError.from_dict(payload["error"]) if payload.get("error") else None
        status = payload.get("status") or ("success" if payload.get("ok", error is None) else "error")
        return cls(
            status=status,
            data=payload.get("data"),
            error=error,
            artifacts=list(payload.get("artifacts") or []),
            metrics=dict(payload.get("metrics") or {}),
        )

    def __str__(self) -> str:
        if self.display is not None:
            return self.display
        if self.error is not None:
            note = self.error.legacy_note()
            return f"{self.passthrough}\n\n{note}" if self.passthrough else note
        if self.data is None:
            return ""
        if isinstance(self.data, str):
            return self.data
        try:
            return json.dumps(self.data, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(self.data)
