"""node_errors/delivery.py — Discord·SMTP 발송 실패를 DELIVERY_* code 로 분류한다 (ADR-0016 ERROR-3).

발송 노드에서 가장 중요한 것은 code 가 아니라 **effectState** 다. 상대가 요청을 거절한 것이
확실하면(4xx) `not_started` 라 다시 보내도 안전하고, 응답을 못 받았거나 5xx 면(`unknown`)
다시 보내면 두 번 갈 수 있다. 이 모듈은 그 판단을 한 곳에서 한다 — 채널 adapter 가 늘어도
(백로그 20) 같은 규칙을 쓴다.

Discord 웹훅 URL·봇 토큰과 SMTP 비밀번호는 노드 설정 또는 .env 에서 오는 "채널 자격증명"이라
API 센터 자격증명(CREDENTIAL_*)과 구분해 DELIVERY_AUTH_FAILED / DELIVERY_FORBIDDEN 을 쓴다.
"""

from __future__ import annotations

from typing import Any, Optional

from .contract import NodeError, make_error

_SMTP_AUTH = {"SMTPAuthenticationError"}
_SMTP_RECIPIENT = {"SMTPRecipientsRefused", "SMTPSenderRefused", "SMTPNotSupportedError"}
_SMTP_CONNECT = {"SMTPConnectError", "gaierror", "ConnectionRefusedError", "herror"}
_SMTP_DISCONNECT = {"SMTPServerDisconnected", "ConnectionResetError", "BrokenPipeError"}
_SMTP_REJECTED = {"SMTPDataError", "SMTPResponseException", "SMTPHeloError"}
_TIMEOUTS = {"timeout", "TimeoutError", "SMTPTimeoutError", "ReadTimeout", "ConnectTimeout", "Timeout"}


def _retry_after_ms(headers: Any) -> Optional[int]:
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return int(seconds * 1000) if seconds >= 0 else None


def error_from_status(
    status: int,
    *,
    provider: str,
    headers: Any = None,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    body: Any = None,
) -> NodeError:
    """HTTP 발송 응답의 상태 코드 → DELIVERY_*. 응답 본문은 내부 기록으로만 남긴다."""
    status = int(status)
    common = dict(node_type=node_type, node_id=node_id, provider_status=status,
                  internal_message=(str(body)[:500] if body is not None else None))
    if status == 401:
        return make_error("DELIVERY_AUTH_FAILED", effect_state="not_started",
                          safe_details={"provider": provider, "status": status}, **common)
    if status == 403:
        return make_error("DELIVERY_FORBIDDEN", effect_state="not_started",
                          safe_details={"provider": provider, "status": status}, **common)
    if status == 404:
        return make_error("DELIVERY_INVALID_RECIPIENT", effect_state="not_started", field="channelId",
                          safe_details={"provider": provider, "status": status}, **common)
    if status == 429:
        retry_after = _retry_after_ms(headers)
        details = {"provider": provider, "status": status}
        if retry_after is not None:
            details["retryAfterMs"] = retry_after
        return make_error("DELIVERY_RATE_LIMITED", effect_state="not_started", retry_after_ms=retry_after,
                          safe_details=details, **common)
    if 400 <= status < 500:
        reason = "payload_too_large" if status == 413 else ("invalid_payload" if status in (400, 422) else "rejected")
        return make_error("DELIVERY_PROVIDER_REJECTED", effect_state="not_started",
                          safe_details={"provider": provider, "status": status, "reason": reason}, **common)
    # 5xx 와 그 밖의 상태 — 상대가 받았는지 알 수 없다
    return make_error("DELIVERY_RESULT_UNKNOWN", effect_state="unknown",
                      safe_details={"provider": provider, "status": status}, **common)


def error_from_exception(
    exc: BaseException,
    *,
    provider: str,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    credential_provider: Optional[str] = None,
) -> NodeError:
    """발송 중 예외 → DELIVERY_* / CREDENTIAL_MISSING / VALIDATION_REQUIRED / INTERNAL_UNKNOWN.

    SMTP 예외는 smtplib 클래스 이름으로, HTTP 라이브러리 예외는 이름에 담긴 Timeout/Connection 으로
    판단한다. 절대 예외를 올리지 않는다.
    """
    name = type(exc).__name__
    text = str(exc or "")
    lowered = text.lower()
    common = dict(cause=exc, node_type=node_type, node_id=node_id)

    # 우리 코드가 외부 호출 전에 던진 설정 오류들
    if isinstance(exc, ValueError):
        if "credential" in lowered or "자격증명" in lowered:
            return make_error("CREDENTIAL_MISSING", effect_state="not_started",
                              safe_details={"provider": credential_provider or provider, "service": provider}, **common)
        if "channel id" in lowered or "channelid" in lowered:
            return make_error("VALIDATION_REQUIRED", field="channelId", effect_state="not_started",
                              safe_details={"field": "channelId"}, **common)
        if "recipient" in lowered or "수신자" in lowered or "toemail" in lowered:
            return make_error("VALIDATION_REQUIRED", field="toEmail", effect_state="not_started",
                              safe_details={"field": "toEmail"}, **common)

    if name in _SMTP_AUTH:
        return make_error("DELIVERY_AUTH_FAILED", effect_state="not_started",
                          safe_details={"provider": provider}, **common)
    if name in _SMTP_RECIPIENT:
        return make_error("DELIVERY_INVALID_RECIPIENT", effect_state="not_started", field="toEmail",
                          safe_details={"provider": provider}, **common)
    if name in _TIMEOUTS or "timeout" in name.lower() or "timed out" in lowered:
        details = {"provider": provider}
        if timeout_seconds is not None:
            details["timeoutSeconds"] = timeout_seconds
        return make_error("DELIVERY_TIMEOUT", effect_state="unknown", safe_details=details, **common)
    if name in _SMTP_CONNECT or ("connection" in name.lower() and "refused" in lowered) or "name or service not known" in lowered:
        # 연결 자체가 안 됐다 — 요청이 나가지 않았음이 확실하다
        return make_error("CONNECTOR_NETWORK_ERROR", effect_state="not_started",
                          safe_details={"service": provider}, **common)
    if name in _SMTP_DISCONNECT or "connection" in name.lower() or "ssl" in name.lower():
        return make_error("DELIVERY_RESULT_UNKNOWN", effect_state="unknown",
                          safe_details={"provider": provider}, **common)
    if name in _SMTP_REJECTED:
        return make_error("DELIVERY_PROVIDER_REJECTED", effect_state="not_started",
                          safe_details={"provider": provider, "reason": "rejected"}, **common)
    return make_error("INTERNAL_UNKNOWN", effect_state="unknown", safe_details={"phase": "delivery"}, **common)


def credential_missing(provider: str, *, node_type: Optional[str] = None, node_id: Optional[str] = None,
                       user_message: Optional[str] = None, credential_provider: Optional[str] = None) -> NodeError:
    """토큰·웹훅이 비어 발송을 시도하지 않은 경우."""
    return make_error(
        "CREDENTIAL_MISSING", effect_state="not_started", user_message=user_message,
        safe_details={"provider": credential_provider or provider, "service": provider},
        node_type=node_type, node_id=node_id,
    )
