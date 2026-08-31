"""database_diagnostics.py — 연결 테스트와 schema 탐색 (ADR-0017, DB-1.3 · DB-3.2).

연결 테스트는 실패를 **단계**로 구분해 돌려준다 — driver → dns → tcp → auth(tls 포함) →
readonly_probe. "안 된다" 대신 "DNS 는 풀렸는데 포트가 닫혀 있다" 를 보여주려는 것이다. 원문
예외와 URI 는 응답에 없다(node_errors.database 가 code 와 사용자 문구로 바꾼다).

schema 탐색은 information_schema 만 읽고, 데이터 sample 은 절대 읽지 않는다. 결과는 짧은 TTL 로
캐시하고 자격증명이 바뀌거나 지워지면 즉시 무효화한다(database_credentials 가 호출).
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any, Dict, List, Optional

from database_policy import PolicyViolation, prepare_connection
from db_query_runtime import _apply_readonly_session
from node_errors import make_error
from node_errors.database import classify_database_exception

SCHEMA_CACHE_TTL_SECONDS = 300
MAX_TABLES = 500
MAX_COLUMNS_PER_TABLE = 200

_schema_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _stage(name: str, ok: bool, message: str, **extra) -> Dict[str, Any]:
    return {"stage": name, "ok": ok, "message": message, **extra}


def test_connection(connection_string: str, *, timeout_seconds: int = 5) -> Dict[str, Any]:
    """접속 단계별 결과. 첫 실패 단계에서 멈추고 error(NodeError v1 dict)를 함께 돌려준다."""
    stages: List[Dict[str, Any]] = []
    error = None
    engine = None
    try:
        try:
            spec = prepare_connection(connection_string, timeout_seconds=timeout_seconds)
        except PolicyViolation as exc:
            node_error = make_error(exc.code, user_message=exc.message, safe_details=exc.safe_details or None, field=exc.field,
                                    node_type="databaseNode")
            stage_name = "dns" if exc.safe_details.get("phase") in {"dns", "egress_policy"} else "driver"
            stages.append(_stage(stage_name, False, exc.message, code=node_error.code))
            return {"ok": False, "stages": stages, "error": node_error.to_dict(), "dialect": None}
        stages.append(_stage("driver", True, f"{spec.dialect} 드라이버 사용 가능"))

        if spec.dialect == "postgresql":
            stages.append(_stage("dns", True, "호스트 이름을 해석했습니다"))
            try:
                with socket.create_connection((spec.resolved_ip, spec.port), timeout=timeout_seconds):
                    pass
                stages.append(_stage("tcp", True, f"포트 {spec.port} 에 연결됐습니다"))
            except OSError as exc:
                node_error = classify_database_exception(exc, connection_string=connection_string, timeout_seconds=timeout_seconds)
                if node_error.code not in {"DATABASE_CONNECTION_FAILED"}:
                    node_error = make_error("DATABASE_CONNECTION_FAILED",
                                            safe_details={"dialect": "postgresql", "phase": "tcp", "timeoutSeconds": timeout_seconds},
                                            cause=exc, node_type="databaseNode")
                stages.append(_stage("tcp", False, "포트에 연결하지 못했습니다(방화벽·보안 그룹·포트 번호를 확인해주세요)", code=node_error.code))
                return {"ok": False, "stages": stages, "error": node_error.to_dict(), "dialect": spec.dialect}

        from sqlalchemy import create_engine, text

        engine = create_engine(spec.url, connect_args=spec.connect_args)
        try:
            with engine.connect() as conn:
                stages.append(_stage("auth", True, "인증에 성공했습니다" + (" (TLS)" if spec.connect_args.get("sslmode") in {"require", "verify-ca", "verify-full"} else "")))
                try:
                    _apply_readonly_session(conn, spec.dialect, timeout_seconds)
                    conn.execute(text("SELECT 1"))
                    stages.append(_stage("readonly_probe", True, "읽기 전용 세션에서 조회가 동작합니다"))
                except Exception as exc:
                    node_error = classify_database_exception(exc, connection_string=connection_string, timeout_seconds=timeout_seconds)
                    stages.append(_stage("readonly_probe", False, node_error.user_message, code=node_error.code))
                    return {"ok": False, "stages": stages, "error": node_error.to_dict(), "dialect": spec.dialect}
        except Exception as exc:
            node_error = classify_database_exception(exc, connection_string=connection_string, timeout_seconds=timeout_seconds)
            stages.append(_stage("auth", False, node_error.user_message, code=node_error.code))
            return {"ok": False, "stages": stages, "error": node_error.to_dict(), "dialect": spec.dialect}
        return {"ok": True, "stages": stages, "error": None, "dialect": spec.dialect}
    finally:
        if engine is not None:
            engine.dispose()


def invalidate_schema_cache(credential_id: Optional[int] = None) -> None:
    with _cache_lock:
        if credential_id is None:
            _schema_cache.clear()
            return
        prefix = f"{credential_id}:"
        for key in [k for k in _schema_cache if k.startswith(prefix)]:
            _schema_cache.pop(key, None)


def fetch_schema(
    credential_id: int,
    connection_string: str,
    *,
    schema: str = "public",
    timeout_seconds: int = 10,
    refresh: bool = False,
) -> Dict[str, Any]:
    """schema 의 table/view/column metadata. 캐시 hit 이면 접속하지 않는다. 실패는 NodeError dict 로."""
    schema = (schema or "public").strip()
    key = f"{credential_id}:{schema}"
    now = time.time()
    if not refresh:
        with _cache_lock:
            cached = _schema_cache.get(key)
        if cached and cached["expires_at"] > now:
            return {**cached["payload"], "cached": True}

    engine = None
    try:
        spec = prepare_connection(connection_string, timeout_seconds=timeout_seconds)
        from sqlalchemy import create_engine, text

        engine = create_engine(spec.url, connect_args=spec.connect_args)
        with engine.connect() as conn:
            _apply_readonly_session(conn, spec.dialect, timeout_seconds)
            if spec.dialect == "sqlite":
                tables = _sqlite_schema(conn)
            else:
                tables = _postgres_schema(conn, schema)
        payload = {"schema": schema, "tables": tables, "truncated": len(tables) >= MAX_TABLES,
                   "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)), "ttl_seconds": SCHEMA_CACHE_TTL_SECONDS,
                   "ok": True, "error": None}
        with _cache_lock:
            _schema_cache[key] = {"expires_at": now + SCHEMA_CACHE_TTL_SECONDS, "payload": payload}
        return {**payload, "cached": False}
    except PolicyViolation as exc:
        error = make_error(exc.code, user_message=exc.message, safe_details=exc.safe_details or None, node_type="databaseNode")
        return {"schema": schema, "tables": [], "ok": False, "error": error.to_dict(), "cached": False}
    except Exception as exc:
        error = classify_database_exception(exc, connection_string=connection_string, timeout_seconds=timeout_seconds)
        return {"schema": schema, "tables": [], "ok": False, "error": error.to_dict(), "cached": False}
    finally:
        if engine is not None:
            engine.dispose()


def _postgres_schema(conn, schema: str) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT c.table_name, t.table_type, c.column_name, c.data_type, c.is_nullable, c.ordinal_position "
        "FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = :schema "
        "ORDER BY c.table_name, c.ordinal_position"
    ), {"schema": schema}).fetchall()
    tables: Dict[str, Dict[str, Any]] = {}
    for table_name, table_type, column, data_type, nullable, _position in rows:
        entry = tables.get(table_name)
        if entry is None:
            if len(tables) >= MAX_TABLES:
                break
            entry = tables[table_name] = {"schema": schema, "name": table_name,
                                          "kind": "view" if (table_type or "").upper() == "VIEW" else "table", "columns": []}
        if len(entry["columns"]) < MAX_COLUMNS_PER_TABLE:
            entry["columns"].append({"name": column, "type": data_type, "nullable": (nullable or "").upper() == "YES"})
    return list(tables.values())


def _sqlite_schema(conn) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    names = conn.execute(text("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")).fetchall()
    tables: List[Dict[str, Any]] = []
    for name, kind in names[:MAX_TABLES]:
        columns = conn.exec_driver_sql(f'PRAGMA table_info("{name}")').fetchall()
        tables.append({"schema": "main", "name": name, "kind": kind,
                       "columns": [{"name": c[1], "type": c[2], "nullable": not c[3]} for c in columns[:MAX_COLUMNS_PER_TABLE]]})
    return tables
