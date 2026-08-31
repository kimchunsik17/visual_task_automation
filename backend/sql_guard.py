"""sql_guard.py — Database Query 의 read-only SQL 판별기 (ADR-0017, 우선 백로그 19 DB-2).

예전 판별은 "첫 단어가 SELECT/WITH 인가 + 세미콜론이 없는가" 였다. 필요조건이지 충분조건이
아니다 — PostgreSQL 은 `WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d` 처럼 WITH 로
시작하는 데이터 변경 CTE 를 허용하고, `SELECT ... INTO`, `SELECT ... FOR UPDATE`, `COPY`,
`pg_read_file()` 같은 것도 첫 단어 검사로는 잡히지 않는다.

여기서는 sqlglot 으로 AST 를 만들고 **허용 목록** 방식으로 판정한다: 최상위가 SELECT/집합 연산
하나뿐이고, 트리 어디에도 DML/DDL/락/파일/세션 변경 노드와 위험 함수가 없어야 한다. 해석하지
못하는 구문은 거부한다(fail closed) — 오탐이면 사용자가 쿼리를 고칠 수 있지만, 미탐은 대상 DB 를
바꾼다. read-only 세션(db_query_runtime)은 이 판별기 뒤의 두 번째 방어선으로 그대로 남는다.

같은 판별기를 생성 시점 검증(meta_agent)과 실행 시점(db_query_runtime)이 함께 쓴다 — 두 판정이
어긋나면 "에디터에선 통과인데 실행에서 막히는" 일이 생긴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import sqlglot
from sqlglot import exp

# `:name` — PostgreSQL 의 타입 캐스트(`value::int`)는 제외한다. 순서를 세는 데만 쓰고, 무엇이
# 자리표시자인지는 AST 가 정한다.
_TEXT_PLACEHOLDER_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")

DEFAULT_ALLOWED_SCHEMAS = ("public",)
# 허용 schema 를 명시하지 않으면 절대 열리지 않는 시스템 schema.
SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

# 트리 어디에 있어도 거부하는 노드 종류. sqlglot 버전에 따라 없는 이름은 건너뛴다.
_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
    "Command", "Copy", "Lock", "Into", "Grant", "Revoke", "Set", "SetItem", "Transaction", "Commit",
    "Rollback", "Use", "Pragma", "LoadData", "Refresh", "Analyze", "Cache", "Uncache", "Comment",
    "Kill", "Describe", "Show", "Declare", "Prepare", "Execute", "Fetch",
)
FORBIDDEN_NODE_TYPES = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if isinstance(getattr(exp, name, None), type)
)

# 파일·세션·서버 상태를 건드리거나 실행 시간을 임의로 늘리는 함수. 소문자 비교.
FORBIDDEN_FUNCTIONS = frozenset({
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_ls_logdir", "pg_ls_waldir", "pg_stat_file",
    "lo_import", "lo_export", "lo_unlink", "lo_put", "lo_from_bytea",
    "pg_sleep", "pg_sleep_for", "pg_sleep_until",
    "set_config", "pg_reload_conf", "pg_rotate_logfile", "pg_terminate_backend", "pg_cancel_backend",
    "pg_advisory_lock", "pg_advisory_xact_lock", "pg_try_advisory_lock", "pg_advisory_unlock",
    "pg_advisory_unlock_all", "pg_try_advisory_xact_lock",
    "setval", "nextval", "dblink", "dblink_exec", "dblink_connect", "pg_notify", "txid_current",
    "pg_logical_emit_message", "pg_create_restore_point", "pg_switch_wal", "pg_promote",
    "current_setting",  # 서버 경로·설정 노출 — 조회 노드에 필요하지 않다
})


class QueryRejected(ValueError):
    """외부 호출 전에 거부된 쿼리. `reason` 은 telemetry 용 짧은 식별자, 문구는 사용자용이다."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class QueryAnalysis:
    statement: str                      # 실행할 statement 하나(뒤 세미콜론 제거)
    placeholders: List[str] = field(default_factory=list)   # `:name` 바인드 파라미터 이름(등장 순, 중복 제거)
    tables: List[Tuple[Optional[str], str]] = field(default_factory=list)  # (schema, table) — CTE 이름 제외


def _single_statement(query: str) -> str:
    stripped = (query or "").strip().rstrip(";").strip()
    if not stripped:
        raise QueryRejected("empty", "쿼리가 비어 있습니다.")
    if ";" in stripped:
        raise QueryRejected("multiple_statements", "statement 는 하나만 실행할 수 있습니다. 세미콜론으로 쿼리를 이어붙일 수 없습니다.")
    return stripped


def _root_is_read(statement: exp.Expression) -> bool:
    set_operation = getattr(exp, "SetOperation", None) or getattr(exp, "Union")
    return isinstance(statement, (exp.Select, set_operation))


def _cte_names(statement: exp.Expression) -> set:
    names = set()
    for cte in statement.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias.lower())
    return names


def analyze_read_query(
    query: str,
    *,
    allowed_schemas: Optional[Iterable[str]] = None,
    dialect: str = "postgres",
) -> QueryAnalysis:
    """읽기 전용으로 실행할 수 있는 statement 하나인지 판정하고 분석 결과를 돌려준다.
    아니면 QueryRejected. 예외를 사용자 문구에 그대로 싣지 않는다."""
    statement_text = _single_statement(query)
    allowed = {s.strip().lower() for s in (allowed_schemas or DEFAULT_ALLOWED_SCHEMAS) if s and s.strip()}
    if not allowed:
        allowed = set(DEFAULT_ALLOWED_SCHEMAS)

    # 첫 단어 검사는 그대로 둔다 — 파서보다 먼저, 파서와 무관하게 막는 층이다.
    first_word = statement_text.split(None, 1)[0].upper()
    if first_word not in {"SELECT", "WITH"}:
        raise QueryRejected("not_a_read_query", "이 노드는 읽기 전용 조회(SELECT/WITH)만 실행합니다.")

    try:
        parsed = sqlglot.parse(statement_text, read=dialect)
    except Exception:
        raise QueryRejected("unparseable", "쿼리 구문을 해석하지 못했습니다. 문법을 확인해주세요 — 해석되지 않는 쿼리는 안전을 위해 실행하지 않습니다.")
    statements = [s for s in parsed if s is not None]
    if len(statements) != 1:
        raise QueryRejected("multiple_statements", "statement 는 하나만 실행할 수 있습니다.")
    root = statements[0]
    if not _root_is_read(root):
        raise QueryRejected("not_a_read_query", "이 노드는 읽기 전용 조회(SELECT/WITH)만 실행합니다.")

    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODE_TYPES):
            kind = type(node).__name__
            if kind == "Lock":
                raise QueryRejected("locking_clause", "FOR UPDATE/SHARE 같은 잠금 절은 읽기 전용 조회에서 쓸 수 없습니다.")
            if kind == "Into":
                raise QueryRejected("select_into", "SELECT ... INTO 는 테이블을 만들기 때문에 허용되지 않습니다.")
            raise QueryRejected("write_statement", f"데이터나 스키마를 바꾸는 구문({kind.upper()})은 이 노드에서 실행할 수 없습니다. 조회(SELECT)만 가능합니다.")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = (node.name or getattr(node, "sql_name", lambda: "")() or "").lower()
            if isinstance(node, exp.Anonymous):
                name = str(node.this).lower()
            if name in FORBIDDEN_FUNCTIONS:
                raise QueryRejected("forbidden_function", f"함수 {name}() 은 파일·세션·서버 상태에 접근하므로 허용되지 않습니다.")

    cte_names = _cte_names(root)
    tables: List[Tuple[Optional[str], str]] = []
    for table in root.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        schema = table.db or None
        if schema is None and name.lower() in cte_names:
            continue
        schema_key = schema.lower() if schema else None
        if schema_key is not None and schema_key not in allowed:
            if schema_key in SYSTEM_SCHEMAS:
                raise QueryRejected("system_schema", f"시스템 schema '{schema}' 는 조회 대상으로 허용되지 않습니다.")
            raise QueryRejected("schema_not_allowed", f"schema '{schema}' 는 이 노드의 허용 목록({', '.join(sorted(allowed))})에 없습니다.")
        tables.append((schema, name))

    found: List[str] = []
    for node in root.find_all(exp.Placeholder, exp.Parameter):
        if isinstance(node, exp.Parameter):
            raise QueryRejected("positional_parameter", "위치 파라미터($1, ?)는 지원하지 않습니다. `:이름` 형식의 이름 있는 파라미터를 써주세요.")
        raw = node.this
        name = str(raw) if raw is not None else ""
        if not name or name == "?":
            raise QueryRejected("positional_parameter", "위치 파라미터(?)는 지원하지 않습니다. `:이름` 형식의 이름 있는 파라미터를 써주세요.")
        if name not in found:
            found.append(name)

    return QueryAnalysis(statement=statement_text, placeholders=_in_text_order(found, statement_text), tables=tables)


def _in_text_order(names: Sequence[str], statement: str) -> List[str]:
    """AST 순회 순서는 트리 모양을 따라가므로(CTE 안의 자리표시자가 뒤로 밀린다) 쿼리에 쓰인 순서로
    다시 세운다 — Inspector 의 파라미터 목록과 오류 문구가 사용자가 읽는 순서와 같아야 한다.
    무엇이 자리표시자인지는 AST 가 정하고(문자열 리터럴 속 `:x` 는 여기 없다), 순서만 본문에서 온다."""
    if len(names) < 2:
        return list(names)
    positions = {}
    for match in _TEXT_PLACEHOLDER_RE.finditer(statement):
        name = match.group(1)
        positions.setdefault(name, match.start())
    return sorted(names, key=lambda name: positions.get(name, len(statement)))


def describe_rejection(exc: QueryRejected) -> Tuple[str, str]:
    return exc.reason, exc.message
