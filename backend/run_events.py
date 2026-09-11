"""run_events.py — 실행 진행 이벤트: 노드 경계 pub/sub + SSE (백로그 32 ENGINE-1 3단계, ADR-0028).

무엇을 하나
  실행이 노드 하나를 끝낼 때마다(그리고 인터프리터는 시작할 때도) 이벤트를 만들어 **실행한 사용자**의 구독자에게
  흘린다. 에디터·앱 빌더가 실행 중 진행 표시(33번 APP-2)를 그리는 원천이다.

정본은 DB 다
  workflow_runs·run_steps(run_records)가 정본이고 이 스트림은 지연 최적화다 — message_stream(ADR-0022)과 같은 원칙.
  구독이 늦었거나 워커가 달라 놓친 이벤트는 실행이 끝난 뒤 타임라인 API(/api/projects/{id}/runs/{run_id})로 메운다.
  그래서 이벤트 보존·재전송(Last-Event-ID)을 하지 않는다.

채널 키는 실행한 사용자다
  run id 는 실행이 시작돼야 생기고, 저장 전 그래프는 project id 가 없다. 실행 전에 구독해 둘 수 있는 유일한 키가
  executor_user_id 다. 이벤트에 runId·projectId·sessionId 를 실어 클라이언트가 고른다. 실행한 사용자를 모르는 경로
  (익명 공개 앱 등)는 이벤트가 없다 — APP-2 가 익명 세션 키를 더할 자리다.

두 엔진과 어떻게 이어지나
  생성 소스를 바꾸지 않는다. 프렐류드가 정의한 `log_step` 을 네임스페이스에서 감싸(attach_step_observer) 기록이 하나
  붙을 때마다 node_finished 를 낸다 — legacy exec·interpreter 모두 같은 프렐류드 위에서 돌므로 같은 이벤트가 나온다.
  node_started 는 인터프리터만 낸다(_Executor.run_item 이 노드 경계를 알기 때문). legacy 는 노드 시작 지점이 없다.

스레드 안전
  실행은 threadpool 이나 스케줄러 스레드에서 돌고 SSE 는 이벤트 루프에서 돈다. 구독자마다 thread-safe queue 를 두고
  publish 는 put_nowait, 스트림은 to_thread 로 get 한다. 큐가 가득 차면 그 구독자의 이벤트는 버린다(DB 가 정본이다).
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import json
import os
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Set

RUN_EVENTS_ENV = "RUN_EVENTS"       # "0" 이면 이벤트를 내지 않는다
HEARTBEAT_SECONDS = 15.0
MAX_STREAMS_PER_USER = 4
QUEUE_MAX = 500


def enabled() -> bool:
    return (os.getenv(RUN_EVENTS_ENV) or "1").strip().lower() not in {"0", "false", "off", "no"}


@dataclass(eq=False)
class Subscription:
    user_id: int
    queue: "queue.Queue[dict]" = field(default_factory=lambda: queue.Queue(maxsize=QUEUE_MAX))
    dropped: int = 0


_subscribers: Dict[int, Set[Subscription]] = collections.defaultdict(set)
_lock = threading.Lock()


def subscribe(user_id: int) -> Subscription:
    sub = Subscription(user_id=int(user_id))
    with _lock:
        _subscribers[sub.user_id].add(sub)
    return sub


def unsubscribe(sub: Subscription) -> None:
    with _lock:
        bucket = _subscribers.get(sub.user_id)
        if bucket is not None:
            bucket.discard(sub)
            if not bucket:
                _subscribers.pop(sub.user_id, None)


def stream_count(user_id: int) -> int:
    with _lock:
        return len(_subscribers.get(int(user_id), ()))


def publish(user_id, event: dict) -> int:
    """이 사용자의 구독자 전부에 이벤트를 넣는다. 돌려주는 값은 전달된 구독자 수(테스트·진단용)."""
    if user_id is None:
        return 0
    with _lock:
        targets = list(_subscribers.get(int(user_id), ()))
    delivered = 0
    for sub in targets:
        try:
            sub.queue.put_nowait(event)
            delivered += 1
        except queue.Full:
            sub.dropped += 1
    return delivered


# ── 관찰자 ──────────────────────────────────────────────────────────────────
class RunObserver:
    """실행 하나의 이벤트 발행자. execution.start 가 만들고 contextvar 로 엔진에 건넨다."""

    def __init__(self, *, run_id: Optional[int], project_id, executor_user_id, session_id, trigger_source: str,
                 engine: str):
        self.run_id = run_id
        self.project_id = project_id
        self.executor_user_id = executor_user_id
        self.session_id = str(session_id) if session_id is not None else None
        self.trigger_source = trigger_source
        self.engine = engine
        self.emitted = 0

    def _emit(self, event_type: str, **fields: Any) -> None:
        if self.executor_user_id is None:
            return
        event = {
            "type": event_type,
            "runId": self.run_id,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "triggerSource": self.trigger_source,
            "engine": self.engine,
            "at": datetime.datetime.utcnow().isoformat(),
        }
        event.update(fields)
        self.emitted += 1
        publish(self.executor_user_id, event)

    def node_started(self, node_id: str, node_type: Optional[str] = None) -> None:
        self._emit("node_started", nodeId=str(node_id), nodeType=node_type)

    def step_logged(self, entry: dict, sequence: int) -> None:
        """log_step 이 기록 하나를 붙였다 — run_steps 의 한 행과 같은 모양의 이벤트."""
        error = entry.get("error") or None
        preview = entry.get("result_data")
        self._emit(
            "node_finished",
            nodeId=str(entry.get("node_id") or ""),
            nodeType=entry.get("node_type"),
            sequence=sequence,
            status="pinned" if entry.get("pinned") else {"success": "succeeded", "error": "failed"}.get(
                str(entry.get("status") or ""), str(entry.get("status") or "")),
            outputPreview=(str(preview)[:500] if preview is not None else None),
            errorCode=error.get("code") if isinstance(error, dict) else None,
            errorMessage=entry.get("error_message"),
        )

    def node_retry(self, node_id: str, node_type: Optional[str], *, attempt: int, max_attempts: int,
                   error_code: Optional[str], delay_sec: float) -> None:
        """재시도 가능한 오류로 끝난 시도 뒤, 다음 시도 전에(ENGINE-3, node_retry) — 화면이 "재시도 중 (2/3)" 을 그릴 수 있게.
        실패한 시도의 node_finished(failed) 는 이미 나갔고, 최종 시도의 node_finished 가 뒤따른다."""
        self._emit("node_retry", nodeId=str(node_id), nodeType=node_type, attempt=int(attempt), maxAttempts=int(max_attempts),
                   errorCode=error_code, delaySec=round(float(delay_sec), 3))

    def finished(self, status: str, *, error_summary: Optional[str] = None, total_tokens: Optional[int] = None) -> None:
        self._emit("run_finished", status=status, errorSummary=error_summary, totalTokens=total_tokens)


def attach_step_observer(namespace: Dict[str, Any], observer: Optional[RunObserver]) -> None:
    """프렐류드가 정의한 log_step 을 감싼다. 생성 소스는 바꾸지 않는다 — 생성 코드와 인터프리터 본문은 `log_step` 을
    전역 이름으로 부르므로 네임스페이스의 값을 바꿔 끼우면 둘 다 감싸진다. 기록 목록은 매 호출 때 네임스페이스에서
    다시 읽는다 — legacy 의 run_workflow() 가 `__execution_logs__ = []` 로 전역을 새 리스트에 다시 묶기 때문이다."""
    if observer is None:
        return
    original = namespace.get("log_step")
    if original is None or getattr(original, "__run_observer_wrapped__", False):
        return

    def observed_log_step(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            entries = namespace.get("__execution_logs__") or []
            if entries:
                observer.step_logged(entries[-1], len(entries))
        except Exception:  # 이벤트는 부수 기능 — 실행을 막지 않는다
            pass
        return result

    observed_log_step.__run_observer_wrapped__ = True  # type: ignore[attr-defined]
    namespace["log_step"] = observed_log_step


# ── SSE ─────────────────────────────────────────────────────────────────────
def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def event_stream(user_id: int, heartbeat_seconds: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    """SSE 본문. 재전송은 없다 — 놓친 것은 타임라인 API 로 메운다. 하트비트는 프록시가 연결을 끊지 않게 한다."""
    sub = subscribe(user_id)
    try:
        yield _sse("ready", {"heartbeatSeconds": heartbeat_seconds})
        while True:
            try:
                event = await asyncio.to_thread(sub.queue.get, True, heartbeat_seconds)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield _sse("run", event)
    except asyncio.CancelledError:
        raise
    finally:
        unsubscribe(sub)
