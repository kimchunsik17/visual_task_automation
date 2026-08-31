"""db_query_runtime.py — databaseNode 의 읽기 전용 쿼리 실행기 (P0 → ADR-0017 Database Query v2).

P0(INCOMPLETE_NODE_STRUCTURE_REVIEW §4.2)에서 실행 로직을 생성 코드 문자열에서 이 모듈로 꺼냈고,
ADR-0016 에서 결과를 NodeResult 로 바꿨다. ADR-0017(우선 백로그 19)에서는 실제 PostgreSQL 실작동에
필요한 것을 채운다.

계층 방어(어느 하나가 뚫려도 다음 층이 막는다):

  0. 자격증명 해석 — 생성 코드는 reference(`{{API_CENTER:database[#id]}}`)만 갖고 있고, 여기서
     소유자 기준으로 복호화한다(database_credentials). URI 는 생성 코드·로그에 들어가지 않는다.
  1. SQL 판별 — sqlglot AST 허용 목록(sql_guard): 단일 SELECT/집합 연산, DML/DDL/락/파일/세션 함수
     거부, schema 허용 목록. 해석 불가면 거부.
  2. 바인드 파라미터 — 값은 `:이름` 으로만 넘긴다(db_query_parameters). 접속 전에 검증한다.
  3. 접속 정책 — PostgreSQL 만, loopback/link-local/metadata 차단, private 은 명시 허용, DNS 고정,
     sslmode 기본 require(database_policy).
  4. dialect 별 read-only 세션 + statement_timeout, 행 수·결과 크기 제한, commit 없음.
  5. 오류는 DATABASE_* code 로 구조화하고 URI·비밀번호·SQL 원문은 공개 payload 에 넣지 않는다.

`run_readonly_query_result()` 가 정본이다. `run_readonly_query()` 는 이행기 문자열 래퍼다.
"""

from __future__ import annotations

import datetime
import decimal
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from node_errors import NodeErrorException, NodeResult, make_error
from node_errors.database import classify_database_exception, dialect_of

# graph.run_workflow 가 "노드에 평문으로 저장돼 있던 접속 문자열"을 실행 전에 치환해 두는
# 표식. data_nodes 생성기가 이 값을 보면 실제 접속을 시도하지 않고 안내 문구로 대체한다.
# (평문 접속 문자열은 graph_data·revision·로그에 남으므로 더 이상 실행 경로에 태우지 않는다.)
LEGACY_PLAINTEXT_SENTINEL = "__LEGACY_DB_CONNECTION_REMOVED__"

DEFAULT_MAX_ROWS = 100
MAX_ROWS_CEILING = 1_000
DEFAULT_TIMEOUT_SECONDS = 10
MAX_TIMEOUT_SECONDS = 30
MAX_RESULT_BYTES = 262_144  # 256KB — LLM 프롬프트/로그로 흘러가는 결과의 상한
OUTPUT_FORMATS = ("rows", "result")

_CONNECTION_URI_RE = re.compile(r"[a-zA-Z0-9+]+://[^\s'\"]+")
_URI_CREDENTIALS_RE = re.compile(r"(://)([^@/\s]+)@")

TRUNCATED_NOTE = "\n[⚠️ 결과가 제한(행 수 또는 크기)을 초과해 일부가 생략되었습니다]"
NO_ROWS_MESSAGE = "쿼리가 결과 행을 반환하지 않았습니다. (이 노드는 읽기 전용이라 변경 사항을 저장하지 않습니다)"
ONLY_READ_MESSAGE = "이 노드는 읽기 전용 조회(SELECT/WITH)만 실행합니다."


def v2_enabled() -> bool:
    """DATABASE_QUERY_V2 플래그(기본 켜짐). 끄면 생성기가 예전 경로(graph 치환 + URI literal)로 돌아간다 —
    되돌리기용이며, 평문 URI 실행 경로는 어느 쪽에서도 되살아나지 않는다."""
    return os.getenv("DATABASE_QUERY_V2", "1").strip().lower() not in {"0", "false", "off", "no"}


def _sanitize_error(message: str, connection_string: str) -> str:
    """오류 문자열에서 접속 정보가 새어 나가지 않게 한다. SQLAlchemy 연결 오류는 URL 전체를
    메시지에 포함하는 경우가 있다."""
    text = str(message or "")
    if connection_string:
        text = text.replace(connection_string, "[REDACTED_DB_URI]")
    text = _URI_CREDENTIALS_RE.sub(r"\1[REDACTED]@", text)
    text = _CONNECTION_URI_RE.sub("[REDACTED_DB_URI]", text)
    return text


def _apply_readonly_session(conn, backend: str, timeout_seconds: int) -> None:
    """dialect 별 read-only 세션과 서버측 timeout. 지원하지 않는 dialect 는 시도만 하고
    넘어간다 — 그 경우에도 단일 statement·SELECT 판별과 no-commit 은 유지된다."""
    timeout_ms = max(1, int(timeout_seconds * 1000))
    if backend == "sqlite":
        conn.exec_driver_sql("PRAGMA query_only = ON")
    elif backend == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")
    elif backend in {"mysql", "mariadb"}:
        conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
        try:
            conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}")
        except Exception:
            pass  # MAX_EXECUTION_TIME 은 MySQL 5.7.17+ 전용
    else:
        try:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        except Exception:
            pass


def _fit_result_bytes(rows: List[dict], truncated: bool):
    """행 목록을 JSON 배열 문자열로 만들되 크기 상한을 넘으면 행을 절반씩 줄인다.
    (남은 행 목록, 표시 문자열, 잘림 여부) 를 돌려준다."""
    while True:
        body = json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default)
        if len(body.encode("utf-8")) <= MAX_RESULT_BYTES or not rows:
            break
        rows = rows[: max(1, len(rows) // 2) if len(rows) > 1 else 0]
        truncated = True
    if truncated:
        body += TRUNCATED_NOTE
    return rows, body, truncated


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def _type_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, (float, decimal.Decimal)):
        return "number"
    if isinstance(value, datetime.datetime):
        return "datetime"
    if isinstance(value, datetime.date):
        return "date"
    if isinstance(value, (dict, list)):
        return "json"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "binary"
    return "string"


def _column_types(columns: List[str], rows: List[dict]) -> List[Dict[str, Any]]:
    """컬럼 타입은 첫 non-null 값의 파이썬 타입으로 추정한다 — 드라이버별 OID 매핑 없이 dialect 중립."""
    result = []
    for name in columns:
        inferred = None
        for row in rows:
            inferred = _type_name(row.get(name))
            if inferred is not None:
                break
        result.append({"name": name, "type": inferred})
    return result


def _plain_rows(rows: List[dict]) -> List[dict]:
    """JSON 직렬화 가능한 값으로 정규화한다(날짜·Decimal·bytes)."""
    return [{k: (_json_default(v) if isinstance(v, (datetime.datetime, datetime.date, datetime.time, decimal.Decimal, bytes, bytearray, memoryview)) else v)
             for k, v in row.items()} for row in rows]


def parse_allowed_schemas(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value]
    else:
        items = [s.strip() for s in str(value or "").split(",")]
    items = [s for s in items if s]
    return items or ["public"]


def run_readonly_query_result(
    connection_string: Optional[str] = None,
    query: str = "",
    *,
    credential_ref: Optional[str] = None,
    owner_user_id: Optional[int] = None,
    db=None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    parameter_overrides: Optional[Dict[str, Any]] = None,
    upstream: Any = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    allowed_schemas: Any = None,
    output_format: str = "rows",
    node_id: Optional[str] = None,
) -> NodeResult:
    """읽기 전용으로 쿼리 하나를 실행해 NodeResult 를 돌려준다. 예외를 밖으로 던지지 않는다.

    접속 정보는 `connection_string`(직접, 테스트·v1 경로) 또는 `credential_ref`(+owner_user_id, db —
    실행기가 API 센터에서 해석) 중 하나로 온다.

    성공 data: {columns: [{name, type}], rows, rowCount, truncated, durationMs, dialect, credential}
    실패 error: DATABASE_* / CREDENTIAL_* / VALIDATION_* — URI·비밀번호·SQL 원문은 공개 payload 에 없다.
    output_format: "rows" → 표시 문자열은 행 배열 JSON(이행기 호환), "result" → NodeResult 전체 JSON.
    """
    max_rows = max(1, min(int(max_rows or DEFAULT_MAX_ROWS), MAX_ROWS_CEILING))
    timeout_seconds = max(1, min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), MAX_TIMEOUT_SECONDS))
    output_format = output_format if output_format in OUTPUT_FORMATS else "rows"
    schemas = parse_allowed_schemas(allowed_schemas)
    started = time.monotonic()
    engine = None
    credential_summary: Optional[Dict[str, Any]] = None

    def _metrics() -> Dict[str, Any]:
        return {"durationMs": int((time.monotonic() - started) * 1000)}

    def _failure(error) -> NodeResult:
        if output_format == "result":
            result = NodeResult.failure(error, metrics=_metrics())
            result.display = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=_json_default)
            return result
        return NodeResult.failure(error, display=f"Database Error: {error.user_message}", metrics=_metrics())

    def _db_failure(exc: BaseException, *, reason: Optional[str] = None, user_message: Optional[str] = None) -> NodeResult:
        error = classify_database_exception(exc, connection_string=connection_string, node_id=node_id,
                                            timeout_seconds=timeout_seconds, rejected_reason=reason)
        if user_message:
            from dataclasses import replace
            error = replace(error, user_message=user_message)
        return _failure(error)

    # 0. 자격증명 해석 — 실패해도 URI 는 어디에도 남지 않는다.
    if not connection_string:
        if not credential_ref:
            return _failure(make_error("CREDENTIAL_MISSING", field="connectionString",
                                       user_message="Database 자격증명이 설정되지 않았습니다. API 센터에서 등록한 뒤 노드에서 선택해주세요.",
                                       safe_details={"provider": "database", "service": "Database"},
                                       node_type="databaseNode", node_id=node_id))
        try:
            from database_credentials import resolve as resolve_credential
            connection_string, credential_summary = resolve_credential(db, owner_user_id, credential_ref, node_id=node_id)
        except NodeErrorException as exc:
            return _failure(exc.error)

    # 1. SQL 판별
    try:
        from sql_guard import QueryRejected, analyze_read_query
        analysis = analyze_read_query(query or "", allowed_schemas=schemas)
    except QueryRejected as exc:
        return _db_failure(exc, reason=exc.reason, user_message=exc.message)
    except ImportError as exc:  # sqlglot 미설치 — 실행하지 않는다(fail closed)
        return _db_failure(exc, reason="guard_unavailable", user_message="SQL 판별기를 불러오지 못해 쿼리를 실행하지 않았습니다. 서버 의존성(sqlglot)을 확인해주세요.")

    # 2. 바인드 파라미터
    try:
        from db_query_parameters import ParameterError, bind_parameters, normalize_definitions
        bound = bind_parameters(normalize_definitions(parameters), analysis.placeholders, upstream,
                                node_id=node_id, overrides=parameter_overrides)
    except ParameterError as exc:
        return _failure(exc.error)

    # 3. 접속 정책
    try:
        from database_policy import PolicyViolation, prepare_connection
        spec = prepare_connection(connection_string, timeout_seconds=timeout_seconds)
    except PolicyViolation as exc:
        return _failure(make_error(exc.code, field=exc.field, user_message=exc.message, safe_details=exc.safe_details or None,
                                   node_type="databaseNode", node_id=node_id))

    # 4. 실행
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(spec.url, connect_args=spec.connect_args)
        with engine.connect() as conn:
            _apply_readonly_session(conn, spec.dialect, timeout_seconds)
            result = conn.execute(text(analysis.statement), bound)
            duration_ms = int((time.monotonic() - started) * 1000)
            base = {"dialect": spec.dialect, "durationMs": duration_ms,
                    "credential": {k: credential_summary[k] for k in ("id", "label", "host", "database") if credential_summary and k in credential_summary} if credential_summary else None}
            if not result.returns_rows:
                data = {"columns": [], "rows": [], "rowCount": 0, "truncated": False, **base}
                return _success(data, NO_ROWS_MESSAGE, output_format, _metrics())
            column_names = [str(key) for key in result.keys()]
            fetched = result.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            # 컬럼 타입은 **정규화 전** 값에서 뽑는다 — _plain_rows 가 날짜·Decimal 을 문자열로 바꾼
            # 뒤에 보면 TIMESTAMPTZ 가 string 으로 잡힌다(실제 PostgreSQL 통합 테스트가 잡은 결함).
            raw_rows = [dict(row._mapping) for row in fetched[:max_rows]]
            columns = _column_types(column_names, raw_rows)
            rows = _plain_rows(raw_rows)
            rows, body, truncated = _fit_result_bytes(rows, truncated)
            duration_ms = int((time.monotonic() - started) * 1000)
            data = {"columns": columns, "rows": rows, "rowCount": len(rows),
                    "truncated": truncated, **base, "durationMs": duration_ms}
            return _success(data, body, output_format, {"durationMs": duration_ms, "rowCount": len(rows), "truncated": truncated})
    except ImportError as exc:
        return _db_failure(exc)
    except Exception as exc:
        return _db_failure(exc)
    finally:
        if engine is not None:
            engine.dispose()


def _success(data: Dict[str, Any], rows_display: str, output_format: str, metrics: Dict[str, Any]) -> NodeResult:
    result = NodeResult.success(data, display=rows_display, metrics=metrics)
    if output_format == "result":
        result.display = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=_json_default)
    return result


def run_readonly_query(
    connection_string: str,
    query: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """이행기 호환 래퍼 — 성공은 JSON 배열 문자열(잘림 표시 포함), 실패는 'Database Error: ...'.
    새 코드는 `run_readonly_query_result()` 를 쓰고 status/error 를 읽는다."""
    return str(run_readonly_query_result(connection_string, query, max_rows=max_rows, timeout_seconds=timeout_seconds))
