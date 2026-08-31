"""node_errors/redaction.py — 내부 진단 기록과 legacy 문구에서 비밀·개인정보를 가린다 (ADR-0016).

공개 payload(userMessage/safeDetails) 는 catalog 문구와 허용 key 만 쓰므로 원래 비밀이 들어갈
자리가 없다. 이 redactor 는 그 바깥 — 내부 ErrorRecord, legacy 오류 문구, safeDetails 문자열 값 —
에 적용하는 마지막 방어선이다. 과하게 가리는 쪽이 덜 가리는 쪽보다 안전하다.
"""

from __future__ import annotations

import re
from typing import Any

MAX_MESSAGE_LENGTH = 500
MAX_STACK_LENGTH = 4000

# 순서가 중요하다 — URI userinfo(`user:pw@host`) 를 이메일 규칙보다 먼저 처리해야 한다.
_URI_USERINFO_RE = re.compile(r"(://)([^/\s@'\"]+)@")
_URL_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^/\s'\"<>]+)(/[^\s'\"<>]*)?")
_AUTH_SCHEME_RE = re.compile(r"\b(Bearer|Bot|Basic|Token)\s+[A-Za-z0-9\-._~+/=]{6,}", re.IGNORECASE)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|x-api-key|token|secret|password|passwd|pwd|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|authorization|credential[s]?)\b(\s*[=:]\s*)['\"]?([^\s'\"&,;]+)"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# 절대 경로(unix/windows)와 uploads/ 상대 경로. URL 은 위에서 먼저 정리한다.
_UNIX_PATH_RE = re.compile(r"(?<![\w:/])/(?:[\w.\-]+/)+[\w.\-]*")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s'\"<>]+\\)*[^\\\s'\"<>]*")
_UPLOADS_PATH_RE = re.compile(r"\buploads[\\/][^\s'\"<>]+")
_SQL_KEYWORD_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|VALUES|FROM|WITH)\b", re.IGNORECASE)
_SQL_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
_API_CENTER_REF_RE = re.compile(r"\{\{API_CENTER:[\w-]+(?:#\d+)?\}\}")


def redact_text(text: Any, *, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """credential, Authorization, URI userinfo, 이메일, SQL 리터럴, 로컬 경로를 가리고 길이를 제한한다."""
    if text is None:
        return ""
    value = str(text)
    value = _URI_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    value = _AUTH_SCHEME_RE.sub(lambda m: f"{m.group(1)} [REDACTED]", value)
    value = _KEY_VALUE_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", value)
    value = _EMAIL_RE.sub("[EMAIL]", value)
    # URL 은 scheme://host 만 남긴다 — path 에 id·토큰이 실리는 서비스가 많다.
    value = _URL_RE.sub(lambda m: m.group(1) + ("/[PATH]" if m.group(2) else ""), value)
    value = _WINDOWS_PATH_RE.sub("[PATH]", value)
    value = _UPLOADS_PATH_RE.sub("[PATH]", value)
    value = _UNIX_PATH_RE.sub("[PATH]", value)
    if _SQL_KEYWORD_RE.search(value):
        value = _SQL_LITERAL_RE.sub("'?'", value)
    if max_length and len(value) > max_length:
        value = value[: max_length - 1] + "…"
    return value


def redact_stack(stack: Any) -> str:
    return redact_text(stack, max_length=MAX_STACK_LENGTH)


def is_credential_reference(value: Any) -> bool:
    return isinstance(value, str) and bool(_API_CENTER_REF_RE.match(value.strip()))
