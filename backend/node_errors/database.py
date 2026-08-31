"""node_errors/database.py — Database Query 예외를 DATABASE_* code 로 분류한다 (ADR-0016 ERROR-3).

드라이버·SQLAlchemy 예외는 종류가 많지만 사용자가 할 수 있는 일은 몇 가지다 — 접속 정보를
고친다(AUTH/CONNECTION), 드라이버가 없다(DRIVER_MISSING), 쿼리를 고친다(QUERY_*), 기다리거나
범위를 줄인다(TIMEOUT). 그 기준으로만 나눈다. 예외 원문·URI 는 내부 기록에만 남긴다.

라이브러리를 import 하지 않고 클래스 이름과 메시지로 판단한다 — 이 모듈이 특정 드라이버에
묶이지 않게 하려는 것이다(connectors.errors.from_exception 과 같은 이유).
"""

from __future__ import annotations

import re
from typing import Optional

from .contract import NodeError, make_error

_AUTH_RE = re.compile(
    r"password authentication failed|authentication failed|access denied|no password supplied|"
    r"role \"?[^\"]*\"? does not exist|fatal:\s+password|auth failed|invalid authorization|"
    r"login failed|permission denied for",
    re.IGNORECASE,
)
_STATEMENT_TIMEOUT_RE = re.compile(
    r"statement timeout|canceling statement|query execution was interrupted|max_execution_time|"
    r"querycanceled|query timed out|execution time exceeded|lock wait timeout",
    re.IGNORECASE,
)
_CONNECTION_RE = re.compile(
    r"could not connect|connection refused|could not translate host name|name or service not known|"
    r"nodename nor servname|unable to open database file|server closed the connection|"
    r"network is unreachable|no route to host|timeout expired|connection timed out|"
    r"connect timeout|is the server running|ssl|tls|connection reset|broken pipe|"
    r"database \"?[^\"]*\"? does not exist|unknown database|can't connect|"
    r"connection to server .* failed",
    re.IGNORECASE,
)
_DIALECT_RE = re.compile(r"^([a-zA-Z0-9]+)(?:\+[a-zA-Z0-9]+)?://")

SUPPORTED_DIALECTS = ["postgresql"]


def dialect_of(connection_string: Optional[str]) -> Optional[str]:
    if not connection_string:
        return None
    match = _DIALECT_RE.match(str(connection_string).strip())
    return match.group(1).lower() if match else None


def classify_database_exception(
    exc: BaseException,
    *,
    connection_string: Optional[str] = None,
    node_type: str = "databaseNode",
    node_id: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    rejected_reason: Optional[str] = None,
) -> NodeError:
    """예외 → DATABASE_* / CREDENTIAL_INVALID / INTERNAL_UNKNOWN. 절대 예외를 올리지 않는다."""
    # 드라이버·SQLAlchemy 계열의 이름 접미사로 판단한다(psycopg2.OperationalError, sqlalchemy.exc.OperationalError,
    # 테스트 대역 _OperationalError 모두). 라이브러리를 import 하지 않기 위한 선택이다.
    name = type(exc).__name__.lstrip("_")
    text = str(exc or "")
    lowered = text.lower()
    dialect = dialect_of(connection_string)
    common = dict(cause=exc, node_type=node_type, node_id=node_id)

    def _error(code, **kwargs):
        details = kwargs.pop("safe_details", {}) or {}
        details = {k: v for k, v in details.items() if v is not None}
        return make_error(code, safe_details=details or None, **common, **kwargs)

    # 1. 쿼리 자체를 실행하지 않은 경우(단일 statement/SELECT 검사)
    if rejected_reason is not None or (isinstance(exc, ValueError) and _is_query_rejection(lowered)):
        return _error(
            "DATABASE_QUERY_REJECTED", field="query",
            safe_details={"reason": rejected_reason or "guard", "allowedStatements": ["SELECT", "WITH"]},
        )

    # 2. 드라이버/dialect 가 없다
    if isinstance(exc, ImportError) or name in {"NoSuchModuleError"} or "can't load plugin" in lowered or "no module named" in lowered:
        return _error("DATABASE_DRIVER_MISSING", safe_details={"dialect": dialect, "supportedDialects": SUPPORTED_DIALECTS})

    # 3. 접속 문자열 자체가 잘못됐다(API 센터의 값) — 자격증명을 고쳐야 한다
    if name == "ArgumentError" or "could not parse" in lowered and "url" in lowered:
        return _error("CREDENTIAL_INVALID", safe_details={"provider": "database", "service": "Database"})

    # 4. 인증
    if _AUTH_RE.search(text):
        return _error("DATABASE_AUTH_FAILED", safe_details={"dialect": dialect})

    # 5. statement timeout (연결 timeout 과 구분)
    if _STATEMENT_TIMEOUT_RE.search(text) or name in {"QueryCanceledError", "QueryCanceled"}:
        return _error("DATABASE_TIMEOUT", field="query", safe_details={"dialect": dialect, "timeoutSeconds": timeout_seconds})

    # 6. 연결
    if _CONNECTION_RE.search(text) or name in {"OperationalError"} and ("connect" in lowered or "socket" in lowered):
        phase = "connect"
        return _error("DATABASE_CONNECTION_FAILED", safe_details={"dialect": dialect, "phase": phase, "timeoutSeconds": timeout_seconds})
    if isinstance(exc, (TimeoutError,)) or name in {"timeout", "Timeout"}:
        return _error("DATABASE_CONNECTION_FAILED", safe_details={"dialect": dialect, "phase": "connect", "timeoutSeconds": timeout_seconds})

    # 7. 쿼리 실행 실패(문법·없는 테이블·타입) — DBAPI 계열 전부
    if name in {
        "OperationalError", "ProgrammingError", "DataError", "IntegrityError", "StatementError",
        "DatabaseError", "InternalError", "NotSupportedError", "InvalidRequestError", "CompileError",
        "DBAPIError", "ResourceClosedError", "ObjectNotExecutableError",
    }:
        return _error("DATABASE_QUERY_FAILED", field="query", safe_details={"dialect": dialect})

    # 8. 마지막 fallback
    return _error("INTERNAL_UNKNOWN", safe_details={"phase": "database"})


def _is_query_rejection(lowered: str) -> bool:
    return "statement" in lowered or "읽기 전용" in lowered or "select" in lowered
