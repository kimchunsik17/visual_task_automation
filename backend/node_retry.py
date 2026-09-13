"""node_retry.py — 노드 재시도 규칙 (백로그 32 ENGINE-3 1단계, ADR-0030).

무엇을 재시도하나
  노드 설정 `data.retries`(재시도 횟수 0~5)·`data.backoffSec`(첫 대기 초, 시도마다 2배, 상한 60초)이 있는 노드가 **구조화 오류**로
  끝났고, 그 오류가 catalog 에서 retryable 이며 부수효과 상태가 안전할 때(effectState 가 unknown/applied 가 아닐 때)만.
  재시도 가능 여부를 노드 설정이 아니라 **오류 코드에서 읽는** 이유: 429 는 잠깐 뒤 다시 보내면 되지만 401 은 백 번 보내도 같고,
  메일 발송이 "보냈는지 모름(unknown)" 이면 한 번 더 보내는 것이 곧 중복 발송이다 — 멱등성은 재시도와 반드시 동시에 간다
  (로드맵 §3.1 ENGINE-3 4). 옛 방식 문자열 오류(LEGACY_NODE_ERROR)는 catalog 기본값이 retryable=False 라 재시도하지 않는다.

어디서 도나
  그래프 인터프리터(`engine_interpreter._Executor.run_item`)의 노드 본문 실행 지점 — 본문(Exec kind=body)만 다시 exec 한다.
  옛 엔진(생성 코드 exec)은 노드 본문과 하류 배선이 한 덩어리로 방출되어 본문만 다시 돌릴 자리가 없다 — **옛 엔진은 이 설정을
  무시한다**(전환된 프로젝트에서만 효과, 프로젝트별 flag 는 ENGINE-0 6단계). 생성 소스는 바뀌지 않으므로 코퍼스 대조는 그대로다.

기록
  실패한 시도의 log_step 기록은 접는다 — 최종 결과가 성공이면 outcome 도 성공이어야 한다(summarize_logs 가 error 를 세지 않게).
  대신 최종 기록(성공이든 마지막 실패든)에 `attempts` 와 `retried=[{attempt, code, message}]` 를 남긴다. 시도 사이마다 진행 이벤트
  `node_retry`(run_events.RunObserver.node_retry)가 나가 화면이 "재시도 중 (2/3)" 을 그릴 수 있다.

timeoutSec 은 여기 없다
  exec 중인 본문은 안전하게 끊을 수 없다(스레드로 감싸고 버리면 본문이 계속 돌며 이름공간을 건드린다). 연결 노드의 요청 시간 제한은
  커넥터(`connectors.services.*`)가 이미 갖고 있고 CONNECTOR_TIMEOUT 은 retryable 이라 여기서 재시도된다. 노드 단위 timeoutSec 은
  본문을 별도 프로세스로 돌릴 수 있게 되는 때(pythonNode 격리와 같은 방식)의 몫으로 남긴다 — ADR-0030.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # 정본은 catalog 의 상수 — 값이 바뀌면 여기도 따라간다
    from node_errors.catalog import UNSAFE_TO_RETRY_EFFECT_STATES as UNSAFE_EFFECT_STATES
except Exception:  # pragma: no cover — catalog 를 못 읽는 환경
    UNSAFE_EFFECT_STATES = frozenset({"unknown", "applied"})

RETRIES_KEY = "retries"
BACKOFF_KEY = "backoffSec"
RETRIES_MAX = 5
BACKOFF_DEFAULT_SEC = 1.0
BACKOFF_MAX_SEC = 60.0


@dataclass(frozen=True)
class RetrySettings:
    retries: int          # 재시도 횟수(첫 시도 제외)
    backoff_sec: float    # 첫 대기(초). 시도마다 2배, 상한 BACKOFF_MAX_SEC

    @property
    def max_attempts(self) -> int:
        return self.retries + 1


def _int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def retry_settings(node: dict) -> Optional[RetrySettings]:
    """노드 data 의 retries/backoffSec → RetrySettings. retries 가 0(또는 없음·잘못됨)이면 None — 재시도 없음."""
    data = (node or {}).get("data") or {}
    retries = max(0, min(RETRIES_MAX, _int(data.get(RETRIES_KEY), 0)))
    if retries == 0:
        return None
    backoff = max(0.0, min(BACKOFF_MAX_SEC, _float(data.get(BACKOFF_KEY), BACKOFF_DEFAULT_SEC)))
    return RetrySettings(retries=retries, backoff_sec=backoff)


def retryable_failure(logs: List[Any], since: int, node_id: str) -> Optional[Dict[str, Any]]:
    """`since` 뒤에 붙은 이 노드의 마지막 기록이 **재시도해도 되는 실패**이면 그 오류 dict, 아니면 None.

    성공·고정 출력·구조화되지 않은 오류·retryable=False·부수효과 상태 unknown/applied 는 전부 None 이다.
    """
    entries = [e for e in list(logs)[since:] if isinstance(e, dict) and str(e.get("node_id")) == str(node_id)]
    if not entries:
        return None
    last = entries[-1]
    if last.get("status") != "error" or last.get("pinned"):
        return None
    error = last.get("error")
    if not isinstance(error, dict) or not error.get("retryable"):
        return None
    if error.get("effectState") in UNSAFE_EFFECT_STATES:
        return None
    return error


def backoff_delay(settings: RetrySettings, attempt: int, error: Optional[Dict[str, Any]] = None) -> float:
    """attempt 번째(0부터) 실패 뒤의 대기. 지수 백오프이되 상대가 Retry-After 를 줬으면 그보다 짧게 기다리지 않는다."""
    delay = float(settings.backoff_sec) * (2 ** max(0, int(attempt)))
    retry_after_ms = (error or {}).get("retryAfterMs")
    if isinstance(retry_after_ms, (int, float)) and retry_after_ms > 0:
        delay = max(delay, float(retry_after_ms) / 1000.0)
    return min(BACKOFF_MAX_SEC, delay)


def fold_attempt(logs: List[Any], since: int, attempt: int, error: Dict[str, Any], retried: List[Dict[str, Any]]) -> None:
    """실패한 시도의 기록을 접고 retried 에 요약을 남긴다."""
    del logs[since:]
    retried.append({"attempt": int(attempt) + 1, "code": error.get("code"), "message": error.get("userMessage")})


def annotate_final(logs: List[Any], since: int, node_id: str, attempts: int, retried: List[Dict[str, Any]]) -> None:
    """최종 시도의 기록에 attempts·retried 를 붙인다(재시도가 있었을 때만)."""
    if not retried:
        return
    for entry in reversed(list(logs)[since:]):
        if isinstance(entry, dict) and str(entry.get("node_id")) == str(node_id):
            entry["attempts"] = int(attempts)
            entry["retried"] = list(retried)
            return


sleep = time.sleep   # 테스트가 바꿔 끼운다(실제 대기 없이 호출 여부만 본다)
