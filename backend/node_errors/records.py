"""node_errors/records.py — 공개 payload 와 분리된 내부 진단 기록 (ADR-0016).

사용자에게는 code 와 userMessage, requestId 만 보인다. 예외 type, redaction 된 메시지·stack,
provider 원문 코드는 여기 남고 requestId 로만 연결된다. 프로세스 안 ring buffer 와
`node_errors` logger 두 곳에 남긴다 — 지원 문의가 오면 requestId 로 로그를 찾는다.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import traceback
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Deque, Dict, List, Optional

from .redaction import redact_stack, redact_text

logger = logging.getLogger("node_errors")

RING_SIZE = 1000
_records: Deque["ErrorRecord"] = deque(maxlen=RING_SIZE)
_lock = threading.Lock()


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class ErrorRecord:
    request_id: str
    code: str
    node_type: Optional[str] = None
    node_id: Optional[str] = None
    exception_type: Optional[str] = None
    message: str = ""            # redaction 후, 길이 제한
    stack: str = ""              # redaction 후, 길이 제한
    provider_code: Optional[str] = None
    provider_status: Optional[int] = None
    attempts: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def remember(
    *,
    code: str,
    request_id: Optional[str] = None,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    cause: Optional[BaseException] = None,
    message: Any = None,
    provider_code: Optional[str] = None,
    provider_status: Optional[int] = None,
    attempts: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> ErrorRecord:
    """기록을 남기고 돌려준다. 절대 예외를 올리지 않는다 — 오류 처리 경로 안에서 불리기 때문이다."""
    request_id = request_id or new_request_id()
    stack = ""
    exception_type = None
    if cause is not None:
        exception_type = type(cause).__name__
        if message is None:
            message = str(cause)
        try:
            stack = redact_stack("".join(traceback.format_exception(type(cause), cause, cause.__traceback__)))
        except Exception:
            stack = ""
    record = ErrorRecord(
        request_id=request_id,
        code=code,
        node_type=node_type,
        node_id=node_id,
        exception_type=exception_type,
        message=redact_text(message) if message is not None else "",
        stack=stack,
        provider_code=provider_code,
        provider_status=provider_status,
        attempts=attempts,
        extra={k: redact_text(v) if isinstance(v, str) else v for k, v in (extra or {}).items()},
    )
    with _lock:
        _records.append(record)
    try:
        logger.warning("node_error %s", json.dumps(record.to_dict(), ensure_ascii=False, default=str))
    except Exception:
        pass
    return record


def find(request_id: str) -> Optional[ErrorRecord]:
    with _lock:
        for record in reversed(_records):
            if record.request_id == request_id:
                return record
    return None


def recent(limit: int = 50) -> List[ErrorRecord]:
    with _lock:
        return list(_records)[-limit:]


def clear() -> None:
    """테스트용."""
    with _lock:
        _records.clear()
