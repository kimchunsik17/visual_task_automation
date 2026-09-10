"""run_worker.py — 큐 워커 (백로그 32 ENGINE-2 1단계, ADR-0029).

무엇을 하나
  workflow_runs 의 queued 를 하나씩 잡아(run_queue.claim) 실행하고(run_queue.execute_claimed → execution.start), 실행 중에는
  별도 스레드가 heartbeat 를 찍고, 끝나면 과금 기록(usage_tracking.record_usage — 인라인 호출부가 하던 것)을 남기고 커밋한다.
  주기적으로 heartbeat 가 끊긴 run 을 failed 로 확정한다(run_queue.reclaim_stale).

어디서 도나
  - 별도 프로세스: `python run_worker.py --worker-id w1` (systemd 유닛은 배포 문서에서). 여러 개 띄워도 SKIP LOCKED 가 중복을 막는다.
  - 인프로세스 스레드: 다음 PR(생산자 전환)에서 API 프로세스 시작 시 켤 수 있게 한다 — 배포 단위를 바꾸지 않고 큐 경로를 먼저 검증하기 위해.

세션
  워커는 실행마다 세션을 새로 열고 닫는다(SessionLocal). execution.start 는 그 세션에 기록을 flush 만 하고 워커가 커밋한다 —
  실패해도 run_records.fail 이 남긴 failed 기록을 커밋한다(rollback 하면 실패했다는 사실이 사라진다).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading
import uuid
from typing import Callable, Optional

import run_queue

logger = logging.getLogger("run_worker")

# run.trigger_source → FlowExecutionLog.trigger_type. 인라인 호출부가 쓰던 표기를 따른다(scheduler.py 는 'scheduler').
TRIGGER_TYPE_BY_SOURCE = {"schedule": "scheduler", "app": "shared_app"}


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


class Worker:
    def __init__(self, session_factory: Callable, *, worker_id: Optional[str] = None, poll_seconds: float = 1.0,
                 heartbeat_seconds: float = 10.0, stale_after_seconds: float = run_queue.STALE_AFTER_SECONDS_DEFAULT,
                 reclaim_every_polls: int = 30):
        self.session_factory = session_factory
        self.worker_id = worker_id or default_worker_id()
        self.poll_seconds = float(poll_seconds)
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.stale_after_seconds = float(stale_after_seconds)
        self.reclaim_every_polls = max(1, int(reclaim_every_polls))
        self.processed = 0
        self.failures = 0
        self.reclaimed = 0
        self._polls = 0

    # ── 한 바퀴 ─────────────────────────────────────────────────────────────
    def run_once(self) -> Optional[int]:
        """queued 하나를 잡아 끝까지 처리한다. 잡은 run 의 id, 없으면 None. 실행 예외는 여기서 끝난다(워커는 죽지 않는다)."""
        self._polls += 1
        db = self.session_factory()
        try:
            if (self._polls - 1) % self.reclaim_every_polls == 0:
                self._reclaim(db)
            run = run_queue.claim(db, self.worker_id)
            if run is None:
                return None
            self._execute(db, run)
            return run.id
        finally:
            db.close()

    def _reclaim(self, db) -> None:
        try:
            ids = run_queue.reclaim_stale(db, older_than_seconds=self.stale_after_seconds)
            if ids:
                self.reclaimed += len(ids)
                logger.warning("[run-worker %s] heartbeat 끊긴 run %s 을 failed 로 확정", self.worker_id, ids)
        except Exception as exc:  # 회수 실패는 다음 바퀴에 다시
            logger.warning("[run-worker %s] stale 회수 실패: %s: %s", self.worker_id, type(exc).__name__, exc)
            db.rollback()

    def _execute(self, db, run) -> None:
        from node_errors import runtime as node_error_runtime
        from usage_tracking import EVENT_WORKFLOW_EXECUTION, record_usage

        stop = threading.Event()
        beat = threading.Thread(target=self._heartbeat_loop, args=(run.id, stop), daemon=True,
                                name=f"run-heartbeat-{run.id}")
        beat.start()
        try:
            result_text, tokens, logs = run_queue.execute_claimed(db, run)
        except Exception as exc:
            # execution.start 가 run_records.fail 로 failed 를 flush 해 두었다 — 커밋해서 남긴다.
            self.failures += 1
            logger.error("[run-worker %s] run %s 실행 예외: %s: %s", self.worker_id, run.id, type(exc).__name__, exc)
            try:
                db.commit()
            except Exception:
                db.rollback()
            return
        finally:
            stop.set()
            beat.join(timeout=self.heartbeat_seconds + 1.0)

        # 과금·사용량 기록 — 인라인 호출부(에디터·스케줄러·웹훅…)가 실행 뒤 하던 것을 워커가 한다. run_id 는 record_usage 가 붙인다.
        try:
            record_usage(
                db,
                billable_user_id=run.owner_user_id if run.owner_user_id is not None else run.executor_user_id,
                actor_user_id=run.executor_user_id,
                project_id=run.project_id,
                token_usage=tokens if isinstance(tokens, dict) else None,
                payload=json.dumps({"queued": True, "trigger": run.trigger_source, "worker": self.worker_id}, ensure_ascii=False),
                result=result_text,
                event_type=EVENT_WORKFLOW_EXECUTION,
                outcome=node_error_runtime.flow_outcome(result_text, logs),
                trigger_type=str(TRIGGER_TYPE_BY_SOURCE.get(run.trigger_source, run.trigger_source)),
            )
        except Exception as exc:
            logger.warning("[run-worker %s] run %s 과금 기록 실패(실행 기록은 남긴다): %s: %s",
                           self.worker_id, run.id, type(exc).__name__, exc)
        db.commit()
        self.processed += 1

    def _heartbeat_loop(self, run_id: int, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            db = self.session_factory()
            try:
                run_queue.heartbeat(db, run_id, self.worker_id)
            except Exception as exc:  # heartbeat 실패는 다음 주기에 다시 — 실행을 막지 않는다
                logger.warning("[run-worker %s] heartbeat 실패 run=%s: %s", self.worker_id, run_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

    # ── 루프 ────────────────────────────────────────────────────────────────
    def run_forever(self, stop_event: Optional[threading.Event] = None) -> None:
        stop_event = stop_event or threading.Event()
        logger.info("[run-worker %s] 시작 (poll %.1fs, heartbeat %.1fs, stale %.0fs)", self.worker_id, self.poll_seconds,
                    self.heartbeat_seconds, self.stale_after_seconds)
        while not stop_event.is_set():
            try:
                claimed = self.run_once()
            except Exception as exc:  # 세션 열기 실패 등 — 죽지 않고 다음 바퀴
                logger.error("[run-worker %s] 바퀴 실패: %s: %s", self.worker_id, type(exc).__name__, exc)
                claimed = None
            if claimed is None:
                stop_event.wait(self.poll_seconds)
        logger.info("[run-worker %s] 종료 — 처리 %d, 실패 %d, 회수 %d", self.worker_id, self.processed, self.failures,
                    self.reclaimed)


# ── 인프로세스 워커 (배포 단위를 바꾸지 않고 큐 경로를 검증하기 위한 것) ─────────────────
# EXECUTION_WORKER_INPROCESS=1 이면 API 프로세스가 시작할 때 워커 스레드를 하나 띄운다. 실행이 API 와 같은 프로세스에서 도는 것은
# 인라인과 같지만, 경로(큐 → claim → 같은 run 행)는 별도 프로세스와 같다. 제대로 된 분리는 run_worker.py 프로세스(systemd 유닛).
INPROCESS_ENV = "EXECUTION_WORKER_INPROCESS"
_inprocess: dict = {"thread": None, "stop": None, "worker": None}


def inprocess_enabled() -> bool:
    return (os.getenv(INPROCESS_ENV) or "0").strip().lower() in {"1", "true", "on", "yes"}


def start_inprocess_worker(session_factory: Callable, **worker_kwargs) -> Worker:
    """워커 스레드를 띄운다(이미 떠 있으면 그것을 돌려준다). daemon 스레드라 프로세스 종료를 막지 않는다."""
    if _inprocess["thread"] is not None and _inprocess["thread"].is_alive():
        return _inprocess["worker"]
    worker_kwargs.setdefault("worker_id", f"inprocess:{default_worker_id()}")
    worker = Worker(session_factory, **worker_kwargs)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run_forever, args=(stop,), name="run-worker-inprocess", daemon=True)
    thread.start()
    _inprocess.update(thread=thread, stop=stop, worker=worker)
    logger.info("[run-worker] 인프로세스 워커 시작 %s", worker.worker_id)
    return worker


def stop_inprocess_worker(timeout: float = 5.0) -> None:
    """현재 run 을 마치고 멈춘다(최대 timeout 초 기다린다)."""
    stop, thread = _inprocess.get("stop"), _inprocess.get("thread")
    if stop is not None:
        stop.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    _inprocess.update(thread=None, stop=None, worker=None)


def inprocess_worker() -> Optional[Worker]:
    thread = _inprocess.get("thread")
    return _inprocess.get("worker") if thread is not None and thread.is_alive() else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="workflow_runs 큐 워커 (ENGINE-2)")
    ap.add_argument("--worker-id", default=None)
    ap.add_argument("--poll", type=float, default=float(os.getenv("RUN_WORKER_POLL_SECONDS", "1.0")))
    ap.add_argument("--heartbeat", type=float, default=float(os.getenv("RUN_WORKER_HEARTBEAT_SECONDS", "10")))
    ap.add_argument("--stale", type=float, default=float(os.getenv("RUN_WORKER_STALE_SECONDS", "120")))
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from database import SessionLocal

    stop = threading.Event()

    def _stop(signum, _frame):
        logger.info("[run-worker] 신호 %s — 현재 run 을 마치고 종료한다", signum)
        stop.set()

    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _stop)

    Worker(SessionLocal, worker_id=args.worker_id, poll_seconds=args.poll, heartbeat_seconds=args.heartbeat,
           stale_after_seconds=args.stale).run_forever(stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
