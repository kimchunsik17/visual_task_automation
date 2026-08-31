"""node_errors/adapters.py — 기존 오류 표현을 canonical NodeError 로 변환한다 (ADR-0016 ERROR-2).

1. `from_connector_error` — ADR-0007 의 lowercase ConnectorError code → 제품 code.
   실행 맥락(domain)에 따라 같은 429 가 CONNECTOR_RATE_LIMITED(조회) 또는
   DELIVERY_RATE_LIMITED(발송) 가 된다. 발송 맥락에서는 effectState 를 보수적으로 잡는다 —
   timeout·network·5xx 는 상대가 받았는지 모르므로 `unknown` 이고 자동 재시도하지 않는다.
2. `legacy_error_from_text` — 아직 이전되지 않은 노드가 결과에 남기는 `[⚠️ ...]`,
   `Database Error:`, `► Flow N Error:` 문구를 LEGACY_NODE_ERROR 로 감싼다. 한 릴리스 동안의
   이행용이며, 신규 코드는 이 패턴을 검색해 분기하지 않는다.
"""

from __future__ import annotations

import re
from typing import Optional

from .contract import NodeError, make_error

CONNECTOR_DOMAIN = "connector"
DELIVERY_DOMAIN = "delivery"

# ConnectorError code → (연동/조회 맥락 code, 발송 맥락 code)
_CANONICAL = {
    "auth_missing": ("CREDENTIAL_MISSING", "CREDENTIAL_MISSING"),
    "auth_invalid": ("CREDENTIAL_INVALID", "CREDENTIAL_INVALID"),
    "auth_forbidden": ("CREDENTIAL_FORBIDDEN", "CREDENTIAL_FORBIDDEN"),
    "not_found": ("CONNECTOR_NOT_FOUND", "DELIVERY_INVALID_RECIPIENT"),
    "invalid_request": ("CONNECTOR_INVALID_REQUEST", "DELIVERY_PROVIDER_REJECTED"),
    "rate_limited": ("CONNECTOR_RATE_LIMITED", "DELIVERY_RATE_LIMITED"),
    "quota_exceeded": ("CONNECTOR_QUOTA_EXCEEDED", "CONNECTOR_QUOTA_EXCEEDED"),
    "timeout": ("CONNECTOR_TIMEOUT", "DELIVERY_TIMEOUT"),
    "network": ("CONNECTOR_NETWORK_ERROR", "DELIVERY_RESULT_UNKNOWN"),
    "server_error": ("CONNECTOR_PROVIDER_ERROR", "DELIVERY_RESULT_UNKNOWN"),
    # 기다린다고 풀리지 않고 사용자가 고칠 값도 아니다. 전용 code
    # (COMMUNITY_PARTNERSHIP_REQUIRED)는 커뮤니티 connector 가 실제로 나올 때 등록한다 —
    # 지금 만들면 사용자 조치가 다르지 않은 code 를 늘리는 셈이다(error_catalog.json 의 규칙).
    "terms_blocked": ("CONNECTOR_INVALID_REQUEST", "DELIVERY_PROVIDER_REJECTED"),
    "unknown": ("INTERNAL_UNKNOWN", "INTERNAL_UNKNOWN"),
}

# 발송 맥락에서 "상대가 처리하지 않았음이 확실한" 실패 — 재시도해도 중복 발송이 없다.
_DELIVERY_NOT_STARTED = frozenset({
    "CREDENTIAL_MISSING", "CREDENTIAL_INVALID", "CREDENTIAL_FORBIDDEN",
    "DELIVERY_INVALID_RECIPIENT", "DELIVERY_PROVIDER_REJECTED", "DELIVERY_RATE_LIMITED",
    "CONNECTOR_QUOTA_EXCEEDED",
})


def canonical_code(connector_code: str, *, domain: str = CONNECTOR_DOMAIN) -> str:
    pair = _CANONICAL.get(connector_code, _CANONICAL["unknown"])
    return pair[1] if domain == DELIVERY_DOMAIN else pair[0]


def from_connector_error(
    error,
    *,
    domain: str = CONNECTOR_DOMAIN,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    field: Optional[str] = None,
    attempts: Optional[int] = None,
    record: bool = True,
) -> NodeError:
    """ConnectorError → NodeError. 사용자 문구는 ADR-0007 이 이미 서비스 이름을 넣어 만든 것을
    그대로 쓴다(provider 원문이 새지 않음은 test_connectors 가 보증). 원문 detail 은 내부 기록으로만."""
    code = canonical_code(error.code, domain=domain)
    if domain == DELIVERY_DOMAIN:
        effect_state = "not_started" if code in _DELIVERY_NOT_STARTED else "unknown"
    else:
        effect_state = "not_applicable"
    context = getattr(error, "context", None) or {}
    safe_details = {
        "service": getattr(error, "service", None),
        "status": getattr(error, "status", None),
        "provider": context.get("provider"),
    }
    if getattr(error, "retry_after", None) is not None and code.endswith("RATE_LIMITED"):
        safe_details["retryAfterMs"] = int(error.retry_after * 1000)
    # code 마다 허용 key 가 다르다 — catalog 가 허용하는 것만 남긴다.
    from . import catalog
    allowed = set(catalog.resolve(code).safeDetailKeys)
    safe_details = {k: v for k, v in safe_details.items() if v is not None and k in allowed}
    return make_error(
        code,
        field=field,
        effect_state=effect_state,
        retry_after_ms=int(error.retry_after * 1000) if getattr(error, "retry_after", None) is not None else None,
        safe_details=safe_details or None,
        user_message=getattr(error, "user_message", None),
        cause=error,
        node_type=node_type,
        node_id=node_id,
        provider_code=getattr(error, "code", None),
        provider_status=getattr(error, "status", None),
        attempts=attempts,
        internal_message=getattr(error, "detail", None),
        record=record,
    )


# ── legacy 문구 감지 ─────────────────────────────────────────────────────
# (패턴 이름, 정규식). 이름은 telemetry 의 safeDetails.legacyPattern 으로 남아 어떤 종류의
# legacy 문구가 얼마나 남았는지 측정하는 데 쓴다.
LEGACY_PATTERNS = (
    ("flow_error", re.compile(r"► Flow \d+ Error:.*", re.DOTALL)),
    ("dynamic_execution_error", re.compile(r"^Dynamic Execution Error:.*", re.DOTALL)),
    ("execution_failed", re.compile(r"^Execution failed:.*", re.DOTALL)),
    ("database_error", re.compile(r"^Database Error:.*", re.DOTALL)),
    ("warning_note", re.compile(r"\[⚠️[^\]]*\]")),
    ("prefixed_error", re.compile(r"^(?:JSON Parser|HTTP Request|Security|Dynamic|Template|File|Poster|Image)?\s*Error(?: [A-Za-z ]+)?:.*", re.DOTALL)),
    ("cross_mark", re.compile(r"^❌.*", re.DOTALL)),
)
_MAX_LEGACY_MESSAGE = 300


def detect_legacy_pattern(text: Optional[str]) -> Optional[tuple]:
    """(패턴 이름, 일치 문구) 또는 None. 앞뒤 공백은 무시한다."""
    if not text:
        return None
    value = str(text).strip()
    if not value:
        return None
    for name, pattern in LEGACY_PATTERNS:
        match = pattern.search(value)
        if match:
            return name, match.group(0)
    return None


def legacy_error_from_text(
    text: Optional[str],
    *,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    source: str = "result",
) -> Optional[NodeError]:
    """legacy 오류 문구를 LEGACY_NODE_ERROR 로 감싼다. 문구가 없으면 None.

    source='error' 면 호출자가 명시적으로 오류라고 넘긴 문자열이므로 패턴 일치와 무관하게 감싼다.
    """
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    detected = detect_legacy_pattern(value)
    if detected is None:
        if source != "error":
            return None
        detected = ("explicit_error", value)
    pattern_name, snippet = detected
    snippet = snippet.strip()
    if snippet.startswith("[⚠️") and snippet.endswith("]"):
        snippet = snippet[len("[⚠️"):-1].strip()
    return make_error(
        "LEGACY_NODE_ERROR",
        user_message=snippet[:_MAX_LEGACY_MESSAGE],
        safe_details={"legacyPattern": pattern_name},
        node_type=node_type,
        node_id=node_id,
        internal_message=value,
    )
