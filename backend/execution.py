"""execution.py — 워크플로우 실행의 단일 진입점 (백로그 32 실행 엔진 v2, ENGINE-0 1단계).

왜 이 모듈이 있나
  `graph.run_workflow` 는 이미 모든 실행 경로가 지나는 함수다. 그런데 "누가·왜 실행했는가"
  (trigger_source)는 호출부마다 session_id 접두('scheduled_'·'webhook_'…)로만 흩어져 있었고,
  엔진을 바꾸거나(섀도·인터프리터) 실행을 큐로 보내려면(ENGINE-2) 끼어들 자리가 없었다.
  TEAM-0 이 권한 판정에 한 것과 같은 수법이다 — **동작은 바꾸지 않고 자리만 하나로 모은다.**

이 모듈이 하는 것
  - start(...)          호출부가 쓰는 유일한 함수. trigger_source 를 받아 contextvar 에 두고
                        `graph.run_workflow` 로 넘긴다. 인자·반환·예외는 run_workflow 와 같다.
                        실행마다 workflow_runs 행을 만들고 끝나면 step 을 채운다(run_records, ENGINE-1).
  - engine_mode(pid)    EXECUTION_ENGINE 기본값 + 프로젝트별 예외. legacy | shadow | interpreter.
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
    "error_trigger",  # 실패한 실행 뒤 지정 워크플로우(graph_data.errorWorkflowId) 실행 — error_trigger.py (ENGINE-3)
})

_current_trigger: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "execution_trigger_source", default=None)


def current_trigger_source() -> Optional[str]:
    """지금 실행 중인 워크플로우가 무엇으로 시작됐는가. 실행 밖에서는 None."""
    return _current_trigger.get()


# ── 실행 기록 (ENGINE-1, ADR-0028) ──────────────────────────────────────────
# start 가 실행마다 workflow_runs 행을 만들고(run_records.begin) 끝나면 step 을 채운다(finish/fail). 호출자의 세션에
# flush 만 하고 커밋은 호출자가 FlowExecutionLog 를 남길 때 함께 한다. 직전 실행의 run id 는 contextvar 에 두어
# usage_tracking.record_usage 가 **한 번만** 꺼내 FlowExecutionLog.run_id 에 붙인다 — 호출부 11곳을 고치지 않고 두 표를 잇는다.
_last_run: contextvars.ContextVar[Optional[tuple]] = contextvars.ContextVar("execution_last_run", default=None)


def take_last_run_id(project_id=None) -> Optional[int]:
    """직전 start 가 만든 실행 기록 id 를 한 번만 꺼낸다. 프로젝트가 다르면(다른 사건이다) None."""
    value = _last_run.get()
    if value is None:
        return None
    _last_run.set(None)
    run_id, run_project_id = value
    if project_id is not None and run_project_id is not None:
        try:
            if int(project_id) != int(run_project_id):
                return None
        except (TypeError, ValueError):
            return None
    return run_id


@contextlib.contextmanager
def preserving_last_run():
    """안에서 다른 start 가 돌아도(에러 트리거의 인라인 실행) 직전 실행의 run id 슬롯은 그대로 남긴다 — 덮이면 원래 실행의
    호출부 record_usage 가 FlowExecutionLog.run_id 를 잇지 못한다."""
    saved = _last_run.get()
    try:
        yield
    finally:
        _last_run.set(saved)


# 진행 이벤트(run_events.RunObserver, ENGINE-1 3단계). start 가 만들어 contextvar 로 두고, graph.run_workflow 가
# 프렐류드 네임스페이스의 log_step 을 감싸는 데 쓴다(생성 소스 무변경). 인터프리터는 노드 시작 이벤트도 낸다.
_current_observer: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("execution_run_observer", default=None)


def current_observer():
    """지금 실행 중인 워크플로우의 진행 이벤트 발행자. 실행 밖이거나 발행자가 없으면 None."""
    return _current_observer.get()


def _record_guarded(action, *args, **kwargs):
    """기록은 부수 기능이다 — 실패해도 실행 결과를 바꾸지 않고 경고만 남긴다."""
    try:
        return action(*args, **kwargs)
    except Exception as exc:
        logger.warning("[run-records] %s 실패(실행은 영향 없음): %s: %s", getattr(action, "__name__", action),
                       type(exc).__name__, exc)
        return None


record_guarded = _record_guarded  # graph._pause_for_approval 등 바깥에서 기록을 남길 때 같은 규칙으로

# 지금 실행 중인 run 행(ENGINE-1). graph._pause_for_approval 이 durable 대기로 전환하며 재개 상태를 여기 남긴다.
_current_run: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("execution_current_run", default=None)


def current_run():
    """지금 실행 중인 워크플로우의 workflow_runs 행. 기록이 꺼져 있거나 db 가 없으면 None."""
    return _current_run.get()


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


def default_engine_mode() -> str:
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


# ── 프로젝트별 예외 (ENGINE-0 6단계, 점진 전환) ────────────────────────────
# EXECUTION_ENGINE_PROJECT_OVERRIDES="12:interpreter,7:legacy" — 기본값(EXECUTION_ENGINE)이 무엇이든 이 프로젝트는
# 지정한 엔진으로 돈다. 전환 순서(로드맵 §3.1: 몇 프로젝트 → 커뮤니티 템플릿 설치분 → 전체)와 되돌리기(문제
# 프로젝트만 legacy)를 배포 없이 환경변수로 한다. DB 컬럼을 두지 않은 이유: 켜고 끄는 주체가 운영자 한 사람이고,
# 값이 바뀌는 시점이 배포와 같기 때문이다. 사용자 수만큼 늘어나면 그때 컬럼으로 옮긴다.
# 매 호출마다 읽는다 — 값이 짧아 비용이 없고, 환경변수를 바꾼 뒤 재시작 없이 다음 실행부터 적용된다.
PROJECT_OVERRIDES_ENV = "EXECUTION_ENGINE_PROJECT_OVERRIDES"
_warned_override_items: set = set()


def project_engine_overrides() -> dict:
    """{project_id: mode}. 형식이 틀린 항목은 한 번 경고하고 무시한다 — 오타 하나가 전체를 무너뜨리면 안 된다."""
    raw = os.getenv(PROJECT_OVERRIDES_ENV) or ""
    overrides: dict = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        project_part, sep, mode = item.partition(":")
        mode = mode.strip().lower()
        if not sep or not project_part.strip().isdigit() or mode not in AVAILABLE_ENGINES:
            if item not in _warned_override_items:
                _warned_override_items.add(item)
                logger.warning("%s 의 항목 %r 은 무시한다 — 형식은 '<project_id>:<%s>' 이다",
                               PROJECT_OVERRIDES_ENV, item, "|".join(KNOWN_ENGINES))
            continue
        overrides[int(project_part.strip())] = mode
    return overrides


def engine_mode(project_id=None) -> str:
    """이 실행이 쓸 엔진. 프로젝트별 예외가 있으면 그것, 없으면 EXECUTION_ENGINE 기본값.
    project_id 가 없거나(저장 전 그래프·평가 러너) 정수가 아니면 기본값이다."""
    default = default_engine_mode()
    if project_id is None:
        return default
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return default
    return project_engine_overrides().get(pid, default)


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
def start(nodes: list, edges: list, *, trigger_source: str, existing_run_id: Optional[int] = None,
          **kwargs: Any) -> Tuple[str, dict, list]:
    """워크플로우를 실행한다. `graph.run_workflow(nodes, edges, **kwargs)` 와 인자·반환·예외가 같다.

    trigger_source 만 추가 인자다 — 생성 코드의 runtime_inputs 로 새지 않게 여기서 떼어 contextvar 에
    둔다(사용자 입력 키와 충돌하지 않도록 kwargs 에 섞지 않는다).
    existing_run_id 를 주면 새 run 을 만들지 않고 그 행 위에서 실행한다 — paused 는 다시 열고(resume), 워커가 claim 한
    running 은 그대로(run_queue). 같은 행에 기록이 이어 붙는다.
    """
    if trigger_source not in TRIGGER_SOURCES:
        raise ValueError(f"trigger_source={trigger_source!r} 는 허용 목록에 없다: {sorted(TRIGGER_SOURCES)}")
    # 지연 import + 모듈 속성 조회: graph 는 무거운 모듈이고, 테스트가 graph.run_workflow 를
    # monkeypatch 하는 관례(test_mock_service)가 그대로 동작해야 한다.
    # 엔진 선택(legacy/interpreter/shadow)은 run_workflow 가 자격증명 치환 뒤 exec 지점에서 한다 — 두 엔진이
    # 같은 전처리를 거친 노드를 받아야 하기 때문이다(ADR-0027).
    import graph as _graph
    import run_events
    import run_records

    db = kwargs.get("db")
    project_id = kwargs.get("project_id")
    executor_user_id = kwargs.get("executor_user_id")
    engine = engine_mode(project_id)
    run = None
    if db is not None and run_records.enabled() and run_records.looks_like_session(db):
        if existing_run_id is not None:
            # 기록 실패로 삼키지 않는다 — 이어서 실행할 수 없는 상태의 run 을 주는 것은 호출자의 상태 오류다.
            run = run_records.adopt(db, existing_run_id)
        else:
            run = _record_guarded(
                run_records.begin, db, trigger_source=trigger_source, engine=engine, project_id=project_id,
                executor_user_id=executor_user_id, session_id=kwargs.get("session_id"))
        if run is not None:
            _last_run.set((run.id, run.project_id))
    elif existing_run_id is not None:
        raise ValueError("existing_run_id 는 db 가 있는 실행에서만 쓸 수 있다")

    observer = None
    if run_events.enabled() and executor_user_id is not None:
        observer = run_events.RunObserver(run_id=run.id if run is not None else None, project_id=project_id,
                                          executor_user_id=executor_user_id, session_id=kwargs.get("session_id"),
                                          trigger_source=trigger_source, engine=engine)

    token = _current_trigger.set(trigger_source)
    observer_token = _current_observer.set(observer)
    run_token = _current_run.set(run)
    try:
        result = _graph.run_workflow(nodes, edges, **kwargs)
    except Exception as exc:
        if run is not None:
            _record_guarded(run_records.fail, db, run, exc)
        if observer is not None:
            _record_guarded(observer.finished, run_records.STATUS_FAILED,
                            error_summary=f"{type(exc).__name__}: {exc}"[:500])
        _record_guarded(_fire_error_trigger, db, project_id=project_id, trigger_source=trigger_source, run=run, exc=exc,
                        executor_user_id=executor_user_id)
        raise
    finally:
        _current_trigger.reset(token)
        _current_observer.reset(observer_token)
        _current_run.reset(run_token)
    result_text, tokens, logs = result
    if run is not None:
        _record_guarded(run_records.finish, db, run, result_text=result_text, tokens=tokens, logs=logs)
    status = run.status if run is not None else run_records.run_status(result_text, logs)
    if observer is not None:
        _record_guarded(observer.finished, status, error_summary=run.error_summary if run is not None else None,
                        total_tokens=run.total_tokens if run is not None else None)
    if status == run_records.STATUS_FAILED:
        # 에러 트리거(ENGINE-3 3단계) — failed 로 닫힌 뒤, 결과를 돌려주기 전에. 실패해도 원래 결과를 바꾸지 않는다.
        _record_guarded(_fire_error_trigger, db, project_id=project_id, trigger_source=trigger_source, run=run,
                        result_text=result_text, logs=logs, executor_user_id=executor_user_id)
    return result


def _fire_error_trigger(db, **kwargs) -> None:
    """failed 로 끝난 실행 뒤 graph_data.errorWorkflowId 의 워크플로우를 부른다(error_trigger.fire). 지연 import — error_trigger 가
    run_queue·usage_tracking 을 쓰고 그쪽이 다시 이 모듈을 본다."""
    import error_trigger

    error_trigger.fire(db, **kwargs)


def resume(run_id: int, *, db, trigger_source: str, extra_inputs: Optional[dict] = None) -> Tuple[str, dict, list]:
    """paused 인 run 을 그 run 이 가진 재개 상태(스냅샷·입력·재개 노드·직전 값)로 이어서 실행한다 (ENGINE-1 2단계).

    승인 결정(approval_service)·대기 노드·워커 재시작(ENGINE-2)이 전부 이 함수를 쓴다 — 재개 방법이 한 곳에 있어야
    "승인한 견본이 그대로 이어진다" 같은 불변식이 경로마다 다르게 깨지지 않는다. extra_inputs 는 재개하는 쪽이 더하는
    런타임 입력(예: approval_decisions)이다. 기록은 같은 run 행에 이어 붙는다(existing_run_id).
    """
    import run_records

    run = db.query(_models().WorkflowRun).filter(_models().WorkflowRun.id == int(run_id)).first()
    if run is None:
        raise LookupError(f"실행 기록 {run_id} 를 찾을 수 없다")
    if run.status != run_records.STATUS_PAUSED:
        raise ValueError(f"paused 상태만 재개할 수 있다 (현재 {run.status})")
    args = run_records.resume_arguments(run)
    inputs = dict(args["runtime_inputs"])
    inputs.update(extra_inputs or {})
    return start(
        args["nodes"], args["edges"], trigger_source=trigger_source, existing_run_id=run.id, db=db,
        session_id=args["session_id"], project_id=args["project_id"], executor_user_id=args["executor_user_id"],
        entry_node_id=args["entry_node_id"], approval_payload=args["approval_payload"], **inputs,
    )


def _models():
    import models
    return models


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
