"""execution.py — 워크플로우 실행의 단일 진입점 (백로그 32 실행 엔진 v2, ENGINE-0 1단계).

왜 이 모듈이 있나
  `graph.run_workflow` 는 이미 모든 실행 경로가 지나는 함수다. 그런데 "누가·왜 실행했는가"
  (trigger_source)는 호출부마다 session_id 접두('scheduled_'·'webhook_'…)로만 흩어져 있었고,
  엔진을 바꾸거나(섀도·인터프리터) 실행을 큐로 보내려면(ENGINE-2) 끼어들 자리가 없었다.
  TEAM-0 이 권한 판정에 한 것과 같은 수법이다 — **동작은 바꾸지 않고 자리만 하나로 모은다.**

이 모듈이 하는 것
  - start(...)          호출부가 쓰는 유일한 함수. trigger_source 를 받아 contextvar 에 두고
                        `graph.run_workflow` 로 넘긴다. 인자·반환·예외는 run_workflow 와 같다.
  - engine_mode()       EXECUTION_ENGINE 환경변수. 지금 실제로 있는 엔진은 legacy 하나다.
  - advisory_lock(...)  "같은 일을 두 곳에서 동시에 하지 않는다" 를 위한 잠금. 스케줄러 중복 발화
                        방지가 첫 소비자고, ENGINE-2 의 워커가 두 번째다.

하지 않는 것
  - 실행 의미론을 바꾸지 않는다. run_workflow 의 인자·반환·예외가 그대로다.
  - 큐·Run/Step 기록·재시도는 여기 없다 — 각각 ENGINE-2·1·3 의 몫이다.

호출부 규칙
  `graph.run_workflow` 를 직접 부르는 곳은 graph.py 와 이 모듈만이다. `test_execution_entry.py`
  가 AST 로 이를 강제한다 — 새 실행 경로를 만들면 반드시 여기를 지나게 하라. 그래야 ENGINE-2 에서
  큐로 보낼 때 한 곳만 바꾸면 된다.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import threading
from typing import Any, Generator, Optional, Tuple

logger = logging.getLogger("execution")

# ── 실행 출처 ──────────────────────────────────────────────────────────────
# ENGINE-1 의 workflow_runs.trigger_source 가 이 값을 그대로 저장한다. 문자열을 열어 두면
# 호출부마다 다른 표기('scheduler'/'schedule'/'cron')가 생겨 집계가 갈라진다 — 닫힌 목록으로 둔다.
TRIGGER_SOURCES = frozenset({
    "manual",      # 에디터 실행 버튼(/api/execute)
    "schedule",    # scheduleNode → APScheduler
    "webhook",     # /webhook/{endpoint_id}
    "bot",         # 디스코드·텔레그램 봇 수신
    "app",         # App Builder 공유 앱·커스텀 앱 실행
    "api",         # 배포된 프로젝트의 API 호출(/api/call/...)
    "approval",    # 승인 결정 뒤 재개(ADR-0015)
    "evaluation",  # 생성 품질 평가 러너
    "mock",        # 목업 탭
})

_current_trigger: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "execution_trigger_source", default=None)


def current_trigger_source() -> Optional[str]:
    """지금 실행 중인 워크플로우가 무엇으로 시작됐는가. 실행 밖에서는 None."""
    return _current_trigger.get()


# ── 엔진 모드 ─────────────────────────────────────────────────────────────
# graph.run_workflow 가 exec 지점에서 읽는다(ADR-0027). 세 값의 뜻:
#   legacy       compile_workflow → exec(). 기본값이고 출시 상태.
#   interpreter  engine_interpreter — 같은 프렐류드 네임스페이스 위에서 정적 계획을 따라 노드 본문을 직접 실행.
#   shadow       legacy 로 실행하되 인터프리터가 그 그래프의 계획을 세울 수 있는지만 확인해 실패를 기록
#                (부작용 없음). 두 엔진의 실행 결과 대조는 mock 모드 오프라인 도구 engine_shadow_diff.py 가 한다.
ENGINE_LEGACY = "legacy"
ENGINE_SHADOW = "shadow"
ENGINE_INTERPRETER = "interpreter"
KNOWN_ENGINES = (ENGINE_LEGACY, ENGINE_SHADOW, ENGINE_INTERPRETER)
AVAILABLE_ENGINES = frozenset(KNOWN_ENGINES)

_warned_engine_values: set = set()


def engine_mode() -> str:
    """EXECUTION_ENGINE 을 읽는다. 모르는 값은 legacy 로 가되 **경고를 남긴다** — 조용히 폴백하면
    운영자가 인터프리터를 켰다고 믿는 채로 옛 엔진이 돈다."""
    raw = (os.getenv("EXECUTION_ENGINE") or ENGINE_LEGACY).strip().lower()
    if raw in AVAILABLE_ENGINES:
        return raw
    if raw not in _warned_engine_values:
        _warned_engine_values.add(raw)
        logger.warning("EXECUTION_ENGINE=%r 는 모르는 값이다 — legacy 로 실행한다. 허용: %s",
                       raw, ", ".join(KNOWN_ENGINES))
    return ENGINE_LEGACY


# shadow 모드가 남기는 계획 실패 기록. 운영 로그(warning)에도 남지만, 테스트와 진단이 읽을 수 있게
# 프로세스 안에 최근 것을 조금 둔다.
SHADOW_PLAN_FAILURES_MAX = 50
shadow_plan_failures: list = []


def record_shadow_plan_failure(project_id, exc: BaseException) -> None:
    logger.warning("[engine-shadow] 인터프리터가 계획을 세우지 못했다 project=%s: %s: %s",
                   project_id, type(exc).__name__, exc)
    if len(shadow_plan_failures) < SHADOW_PLAN_FAILURES_MAX:
        shadow_plan_failures.append({"project_id": project_id, "error": f"{type(exc).__name__}: {exc}"})


# ── 진입점 ─────────────────────────────────────────────────────────────────
def start(nodes: list, edges: list, *, trigger_source: str, **kwargs: Any) -> Tuple[str, dict, list]:
    """워크플로우를 실행한다. `graph.run_workflow(nodes, edges, **kwargs)` 와 인자·반환·예외가 같다.

    trigger_source 만 추가 인자다 — 생성 코드의 runtime_inputs 로 새지 않게 여기서 떼어 contextvar 에
    둔다(사용자 입력 키와 충돌하지 않도록 kwargs 에 섞지 않는다).
    """
    if trigger_source not in TRIGGER_SOURCES:
        raise ValueError(f"trigger_source={trigger_source!r} 는 허용 목록에 없다: {sorted(TRIGGER_SOURCES)}")
    # 지연 import + 모듈 속성 조회: graph 는 무거운 모듈이고, 테스트가 graph.run_workflow 를
    # monkeypatch 하는 관례(test_mock_service)가 그대로 동작해야 한다.
    # 엔진 선택(legacy/interpreter/shadow)은 run_workflow 가 자격증명 치환 뒤 exec 지점에서 한다 — 두 엔진이
    # 같은 전처리를 거친 노드를 받아야 하기 때문이다(ADR-0027).
    import graph as _graph

    token = _current_trigger.set(trigger_source)
    try:
        return _graph.run_workflow(nodes, edges, **kwargs)
    finally:
        _current_trigger.reset(token)


# ── 배타 잠금 ─────────────────────────────────────────────────────────────
# PostgreSQL advisory lock 은 (int4, int4) 두 정수로 이름을 붙인다. 앞 정수가 "무슨 일"이고 뒤가
# "어느 대상"이다. 앞 정수를 여기 상수로만 만들어 소비자끼리 충돌하지 않게 한다.
SCHEDULE_LOCK_NAMESPACE = 320001   # 백로그 32 · 소비자 01: 스케줄 실행(project_id 단위)

_local_lock_guard = threading.Lock()
_local_locks: set = set()


def _dialect_name(bind) -> str:
    try:
        return str(bind.dialect.name)
    except Exception:  # pragma: no cover — bind 가 엔진이 아닌 경우
        return ""


@contextlib.contextmanager
def advisory_lock(namespace: int, key: int, *, bind=None) -> Generator[bool, None, None]:
    """`with advisory_lock(ns, key) as acquired:` — acquired 가 False 면 다른 곳이 같은 일을 하고 있다.

    PostgreSQL 이면 세션 수준 advisory lock 을 **전용 연결**로 잡는다. Session 의 연결은 commit 마다
    풀로 돌아가 다른 연결로 바뀔 수 있어, 그 위에서 잡은 잠금은 풀지 못하는 채로 남는다(다음 사람이
    영영 스킵된다). 그래서 잠금만을 위한 연결을 하나 열고 끝날 때 반드시 풀고 닫는다.

    PostgreSQL 이 아니면(테스트 sqlite) 프로세스 안의 집합으로 대신한다 — 인스턴스 간 배타는 못 하지만
    한 프로세스 안의 중복(APScheduler misfire·coalesce 후 재발화)은 같은 의미로 막힌다.
    """
    if bind is None:
        from database import engine as _engine
        bind = _engine

    if _dialect_name(bind) == "postgresql":
        from sqlalchemy import text

        conn = bind.connect()
        acquired = False
        try:
            acquired = bool(conn.execute(
                text("SELECT pg_try_advisory_lock(:ns, :key)"), {"ns": int(namespace), "key": int(key)}
            ).scalar())
            yield acquired
        finally:
            try:
                if acquired:
                    conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"),
                                 {"ns": int(namespace), "key": int(key)})
            finally:
                conn.close()
        return

    slot = (int(namespace), int(key))
    with _local_lock_guard:
        acquired = slot not in _local_locks
        if acquired:
            _local_locks.add(slot)
    try:
        yield acquired
    finally:
        if acquired:
            with _local_lock_guard:
                _local_locks.discard(slot)
