"""connectors/errors.py — 연동 노드 오류를 하나의 어휘로 정규화한다 (ADR-0007).

지금까지는 노드마다 실패를 제각각 다뤘다 — 어떤 노드는 status_code == 200 만 성공으로 보고
나머지를 한 줄짜리 한국어 문구로 뭉쳤고, 어떤 노드는 예외 메시지를 그대로 결과에 실었다.
그래서 "인증이 안 된 것"과 "잠깐 막힌 것"과 "요청이 잘못된 것"을 코드로 구분할 수 없었고,
재시도해도 되는 실패인지 판단할 근거도, 노드별 오류 코드 telemetry 를 모을 방법도 없었다.

여기서 정하는 코드는 세 곳에서 같은 의미로 쓰인다 — 실행 엔진의 재시도 판단, 사용자에게
보여줄 안내 문구, 그리고 운영 지표(오류 코드별 발생률).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# ── 오류 코드 ───────────────────────────────────────────────────────────
# 사용자가 할 수 있는 일이 서로 다른 것들만 나눈다. 더 잘게 쪼개면 안내 문구만 늘고
# 정작 "그래서 내가 뭘 해야 하나"는 answered 되지 않는다.
AUTH_MISSING = "auth_missing"          # 자격증명이 아예 없다 — API 센터에 등록해야 한다
AUTH_INVALID = "auth_invalid"          # 401 — 값이 틀렸거나 만료됐다
AUTH_FORBIDDEN = "auth_forbidden"      # 403 — 권한/scope 가 모자란다
NOT_FOUND = "not_found"                # 404 — 대상이 없다(시트 id, 채널 id 오타 등)
INVALID_REQUEST = "invalid_request"    # 400/422 — 보낸 값이 잘못됐다
RATE_LIMITED = "rate_limited"          # 429 — 잠깐 뒤 다시 하면 된다
QUOTA_EXCEEDED = "quota_exceeded"      # 402 등 — 기다린다고 풀리지 않는다
TIMEOUT = "timeout"                    # 응답이 제때 오지 않았다
NETWORK = "network"                    # 연결 자체가 안 됐다
SERVER_ERROR = "server_error"          # 5xx — 상대 서비스 문제
TERMS_BLOCKED = "terms_blocked"        # 자동 처리 허용 근거가 없거나 만료됐다 — 기다려도 안 풀린다
UNKNOWN = "unknown"

# 기다렸다 다시 시도하면 결과가 달라질 수 있는 코드.
RETRYABLE_CODES = frozenset({RATE_LIMITED, TIMEOUT, NETWORK, SERVER_ERROR})

# 사용자가 자격증명을 손봐야 풀리는 코드. 실행 엔진이 "API 센터에서 연결하세요" 안내를
# 띄울지 판단하는 데 쓴다.
CREDENTIAL_CODES = frozenset({AUTH_MISSING, AUTH_INVALID, AUTH_FORBIDDEN})

_STATUS_MAP = {
    400: INVALID_REQUEST,
    401: AUTH_INVALID,
    402: QUOTA_EXCEEDED,
    403: AUTH_FORBIDDEN,
    404: NOT_FOUND,
    408: TIMEOUT,
    409: INVALID_REQUEST,
    413: INVALID_REQUEST,
    422: INVALID_REQUEST,
    429: RATE_LIMITED,
}

# 사용자에게 보여줄 안내. 서비스 이름을 앞에 붙여 쓴다.
_USER_MESSAGE = {
    AUTH_MISSING: "{service} 자격증명이 등록되어 있지 않습니다. API 센터에서 먼저 연결해주세요.",
    AUTH_INVALID: "{service} 인증에 실패했습니다. API 센터에 등록한 값이 만료됐거나 잘못됐습니다.",
    AUTH_FORBIDDEN: "{service} 접근 권한이 없습니다. 필요한 권한(scope)이 있는지, 대상이 이 계정과 공유되어 있는지 확인해주세요.",
    NOT_FOUND: "{service}에서 대상을 찾지 못했습니다. 입력한 ID나 주소를 확인해주세요.",
    INVALID_REQUEST: "{service}가 요청을 거절했습니다. 노드에 입력한 값을 확인해주세요.",
    RATE_LIMITED: "{service} 호출 한도에 걸렸습니다. 잠시 뒤 다시 시도됩니다.",
    QUOTA_EXCEEDED: "{service} 사용 한도를 초과했습니다. 요금제나 할당량을 확인해주세요.",
    TIMEOUT: "{service} 응답이 제한 시간 안에 오지 않았습니다.",
    NETWORK: "{service}에 연결하지 못했습니다. 네트워크 상태를 확인해주세요.",
    SERVER_ERROR: "{service} 쪽에 일시적인 문제가 있습니다. 잠시 뒤 다시 시도됩니다.",
    TERMS_BLOCKED: "{service} 자동 처리 허용 근거가 만료됐습니다. 공식 API·RSS 또는 서면 제휴를 다시 확인한 뒤 사용할 수 있습니다.",
    UNKNOWN: "{service} 호출 중 알 수 없는 오류가 발생했습니다.",
}


@dataclass
class ConnectorError(Exception):
    """정규화된 연동 오류. 실행 엔진과 사용자 안내와 telemetry 가 같은 값을 본다."""

    code: str
    service: str = "연동 서비스"
    status: Optional[int] = None
    # 상대 서비스가 준 원문. 사용자 안내에는 쓰지 않고 로그/디버깅용으로만 남긴다 —
    # 영어 스택트레이스를 그대로 보여주는 것이 지금까지의 문제였다.
    detail: Optional[str] = None
    # 429/503 의 Retry-After. 재시도 대기 시간을 우리가 임의로 정하지 않고 상대가 시킨 만큼 기다린다.
    retry_after: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        super().__init__(self.user_message)

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES

    @property
    def needs_credential(self) -> bool:
        return self.code in CREDENTIAL_CODES

    @property
    def user_message(self) -> str:
        template = _USER_MESSAGE.get(self.code, _USER_MESSAGE[UNKNOWN])
        return template.format(service=self.service)

    def to_dict(self) -> Dict[str, Any]:
        """공개 표현. 상대 서비스 원문(`detail`)은 여기 싣지 않는다(ADR-0016 ERROR-2.3) — 내부
        ErrorRecord 에만 남고 `to_node_error().request_id` 로 찾는다."""
        return {
            "code": self.code,
            "service": self.service,
            "status": self.status,
            "retryable": self.retryable,
            "needs_credential": self.needs_credential,
            "message": self.user_message,
            "retry_after": self.retry_after,
            **({"context": self.context} if self.context else {}),
        }

    def to_node_error(self, *, domain: str = "connector", node_type: Optional[str] = None,
                      node_id: Optional[str] = None, field: Optional[str] = None, record: bool = True):
        """제품 전체 계약 NodeError v1 로 승격한다(ADR-0016). `domain` 이 'delivery' 면 같은 429 도
        DELIVERY_RATE_LIMITED 가 되고 timeout/5xx 의 effectState 가 unknown 으로 잡힌다."""
        from node_errors.adapters import from_connector_error

        return from_connector_error(self, domain=domain, node_type=node_type, node_id=node_id, field=field, record=record)


def parse_retry_after(value: Any) -> Optional[float]:
    """Retry-After 헤더는 초 단위 숫자 또는 HTTP-date 다. 숫자만 해석하고, 날짜 형식이면
    None 을 돌려 재시도 정책의 기본 backoff 를 쓰게 한다(날짜 파싱 실패로 재시도 자체가
    깨지는 것보다 낫다)."""
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def code_for_status(status: int) -> str:
    if status in _STATUS_MAP:
        return _STATUS_MAP[status]
    if 500 <= status < 600:
        return SERVER_ERROR
    if 400 <= status < 500:
        return INVALID_REQUEST
    return UNKNOWN


def from_response(status: int, *, service: str, body: Any = None, headers: Any = None) -> ConnectorError:
    """HTTP 응답을 정규화된 오류로 바꾼다."""
    headers = headers or {}
    retry_after = parse_retry_after(
        headers.get("Retry-After") or headers.get("retry-after")
    )
    detail = body if isinstance(body, str) else (None if body is None else str(body))
    return ConnectorError(
        code=code_for_status(status),
        service=service,
        status=status,
        detail=(detail[:500] if detail else None),
        retry_after=retry_after,
    )


def from_exception(exc: BaseException, *, service: str) -> ConnectorError:
    """requests/urllib 계열 예외를 정규화한다. 라이브러리를 import 하지 않고 클래스 이름으로
    판단한다 — 이 모듈이 특정 HTTP 클라이언트에 묶이지 않게 하려는 것이다."""
    if isinstance(exc, ConnectorError):
        return exc
    name = type(exc).__name__
    if "Timeout" in name:
        code = TIMEOUT
    elif "ConnectionError" in name or "SSLError" in name or "DNS" in name:
        code = NETWORK
    else:
        code = UNKNOWN
    return ConnectorError(code=code, service=service, detail=str(exc)[:500])
