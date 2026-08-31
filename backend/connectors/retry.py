"""connectors/retry.py — 연동 호출 재시도 정책 (ADR-0007).

■ 가장 중요한 결정: 쓰기 요청은 기본적으로 재시도하지 않는다.

카카오 메시지 발송이 timeout 났을 때 다시 보내면, 상대에게 메시지가 두 번 갈 수 있다.
요청이 서버에 닿았는지 아닌지를 클라이언트가 알 방법이 없기 때문이다. 자동화 제품에서
"중복 발송"은 "한 번 실패"보다 훨씬 나쁜 결과다.

그래서 재시도 여부를 두 축으로 나눠 판단한다.

    메서드가 멱등한가(GET/HEAD/PUT/DELETE)  →  재시도해도 결과가 같다
    실패가 '서버가 처리하지 않았음이 확실한가'  →  429 는 상대가 거절한 것이라 안전하다

POST 같은 비멱등 요청은 429 만 재시도한다. timeout/5xx 는 재시도하지 않는다 —
정말 필요하면 노드가 멱등 키를 갖춘 뒤 `idempotent=True` 로 선언해서 열어야 한다.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from .errors import RATE_LIMITED, ConnectorError

T = TypeVar("T")

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
# 비멱등 요청에서도 재시도해도 되는 코드 — 상대가 요청을 '처리하지 않고' 거절한 경우.
SAFE_FOR_NON_IDEMPOTENT = frozenset({RATE_LIMITED})


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3          # 최초 시도를 포함한 횟수
    base_delay: float = 0.5        # 지수 백오프의 기준 간격(초)
    max_delay: float = 20.0
    # 여러 워크플로우가 같은 순간에 같은 서비스로 재시도가 몰리는 것을 흩뜨린다.
    jitter: float = 0.25
    # 상대가 Retry-After 로 알려준 시간이 max_delay 보다 길면 재시도를 포기한다 —
    # 워크플로우 실행이 몇 분씩 멈춰 있는 것보다 실패로 끝내는 편이 낫다.
    respect_retry_after: bool = True

    def delay_for(self, attempt: int, error=None) -> float:
        """attempt 는 1부터. 다음 시도까지 기다릴 초. `error` 는 ConnectorError(retry_after 초) 또는
        NodeError(retryAfterMs) — 상대가 알려준 값이 있으면 그것을 우선한다."""
        retry_after = _retry_after_seconds(error)
        if self.respect_retry_after and retry_after is not None:
            return min(retry_after, self.max_delay)
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter:
            delay += random.uniform(0, self.jitter * delay)
        return delay


DEFAULT_POLICY = RetryPolicy()


def _retry_after_seconds(error) -> Optional[float]:
    if error is None:
        return None
    retry_after_ms = getattr(error, "retry_after_ms", None)
    if retry_after_ms is not None:
        return float(retry_after_ms) / 1000.0
    retry_after = getattr(error, "retry_after", None)
    return float(retry_after) if retry_after is not None else None


def should_retry(
    error,
    *,
    attempt: int,
    policy: RetryPolicy,
    method: str = "GET",
    idempotent: Optional[bool] = None,
) -> bool:
    """이 실패를 다시 시도해도 되는지. idempotent 를 명시하면 메서드 판단보다 우선한다
    (멱등 키를 갖춘 POST 를 재시도 대상으로 열어주기 위한 통로).

    판단은 NodeError v1 의 `retryable` + `effectState` + `retryAfterMs` 로 한다(ADR-0016 ERROR-2.2).
    멱등 요청은 connector 맥락(effectState=not_applicable)으로, 비멱등 요청은 delivery 맥락으로
    변환하므로 — 상대가 거절한 429 는 not_started 라 재시도되고, timeout/5xx/network 는 unknown 이라
    재시도되지 않는다. ADR-0007 이 정한 동작과 정확히 같되 근거가 한 곳(catalog)으로 모인다.
    """
    if attempt >= policy.max_attempts:
        return False
    is_idempotent = IDEMPOTENT_METHODS.__contains__(method.upper()) if idempotent is None else idempotent
    node_error = _as_node_error(error, is_idempotent=is_idempotent)
    if not node_error.safe_to_retry:
        return False
    retry_after = _retry_after_seconds(node_error)
    if retry_after is not None and retry_after > policy.max_delay:
        return False
    return True


def _as_node_error(error, *, is_idempotent: bool):
    if hasattr(error, "safe_to_retry"):
        return error
    if isinstance(error, ConnectorError):
        # 재시도 판단마다 내부 기록을 남기지는 않는다 — 기록은 최종 실패가 표면화될 때 한 번.
        return error.to_node_error(domain="connector" if is_idempotent else "delivery", record=False)
    from node_errors import from_exception
    return from_exception(error)


def run_with_retry(
    call: Callable[[], T],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    method: str = "GET",
    idempotent: Optional[bool] = None,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Optional[Callable[[int, float, ConnectorError], None]] = None,
) -> T:
    """`call` 을 정책에 따라 재시도한다. ConnectorError 가 아닌 예외는 재시도하지 않고
    그대로 올린다 — 정규화되지 않은 실패를 조용히 반복 호출하지 않으려는 것이다."""
    attempt = 1
    while True:
        try:
            return call()
        except ConnectorError as error:
            if not should_retry(error, attempt=attempt, policy=policy, method=method, idempotent=idempotent):
                raise
            delay = policy.delay_for(attempt, error)
            if on_retry:
                on_retry(attempt, delay, error)
            sleep(delay)
            attempt += 1
