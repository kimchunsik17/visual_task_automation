"""connectors/session.py — 공식 연동 노드가 외부 API 를 부르는 단일 경로 (ADR-0007).

타임아웃, 오류 정규화, 재시도, 페이지 넘기기를 한 군데로 모은다. 지금까지는 노드마다
`requests.post(..., timeout=10)` 을 직접 쓰고 status_code 를 손으로 비교했기 때문에,
타임아웃 값도 제각각이었고 재시도는 아예 없었으며 실패는 한국어 한 줄로 뭉개졌다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import errors
from .errors import ConnectorError
from .pagination import PaginationConfig, PaginationResult, collect_pages
from .retry import DEFAULT_POLICY, RetryPolicy, run_with_retry


@dataclass
class RateLimit:
    """같은 서비스로 나가는 호출 사이의 최소 간격만 지키는 아주 단순한 제한기.

    실행 워커 프로세스 안에서만 유효하다 — 여러 워커가 뜨면 전체 한도를 보장하지 못한다.
    상대 서비스가 429 를 주면 재시도 정책이 Retry-After 를 따르므로, 이건 '평소에 굳이
    한도까지 밀어붙이지 않기' 위한 완충일 뿐이다.
    """

    requests_per_minute: Optional[int] = None
    # "아직 한 번도 호출하지 않음"은 None 으로 표현한다 — 0.0 을 센티널로 쓰면 시계가 실제로
    # 0 을 돌려주는 경우(테스트의 가짜 시계, 부팅 직후)와 구분되지 않아 간격 유지가 통째로 꺼진다.
    _last_call: Optional[float] = field(default=None, repr=False)

    @property
    def min_interval(self) -> float:
        if not self.requests_per_minute or self.requests_per_minute <= 0:
            return 0.0
        return 60.0 / self.requests_per_minute

    def wait(self, *, now: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        interval = self.min_interval
        if interval <= 0:
            return
        current = now()
        if self._last_call is not None:
            elapsed = current - self._last_call
            if elapsed < interval:
                sleep(interval - elapsed)
                current += interval - elapsed
        self._last_call = current


@dataclass
class Response:
    status: int
    headers: Dict[str, Any]
    body: Any

    def json(self) -> Any:
        return self.body


class ResponseTooLarge(Exception):
    """선언된 한도를 넘는 본문(session.download).

    네트워크 오류가 아니라 **우리가 정한 정책**이라, 세션의 예외 분류(timeout/network/unknown)를
    타면 안 된다. 그래서 ConnectorError 와 함께 그대로 통과시키고, 서비스 모듈이 사용자가 읽을
    문구(한도 MB)로 바꾼다. 재시도해도 결과가 같으므로 재시도 대상도 아니다.
    """


class ConnectorSession:
    """서비스 하나에 대한 호출 창구.

    `transport` 는 `(method, url, **kwargs) -> Response` 형태면 무엇이든 된다. 기본값은
    requests 이지만, 테스트와 mock fixture 는 가짜 transport 를 끼워 넣어 네트워크 없이
    같은 경로를 통과시킨다(목업 서버 탭에서 쓸 자리이기도 하다).
    """

    def __init__(
        self,
        service: str,
        *,
        transport: Optional[Callable[..., Response]] = None,
        timeout: float = 15.0,
        retry_policy: RetryPolicy = DEFAULT_POLICY,
        rate_limit: Optional[RateLimit] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.service = service
        self.timeout = timeout
        self.retry_policy = retry_policy
        self.rate_limit = rate_limit or RateLimit()
        self._transport = transport or _requests_transport
        self._sleep = sleep
        # 노드 단위 telemetry 의 재료. 호출부가 실행 로그에 실어 보낸다.
        self.attempts = 0
        self.retries: List[Dict[str, Any]] = []

    # ── 단일 호출 ──────────────────────────────────────────────────────
    def request(
        self,
        method: str,
        url: str,
        *,
        idempotent: Optional[bool] = None,
        expected_status: Optional[set] = None,
        **kwargs: Any,
    ) -> Response:
        """호출하고, 실패는 ConnectorError 로 올린다. 성공 판정은 2xx 를 기본으로 한다 —
        노드마다 `== 200` 으로 좁게 비교하다 201/204 를 실패로 오해하는 일이 있었다."""

        def _call() -> Response:
            self.attempts += 1
            self.rate_limit.wait(sleep=self._sleep)
            try:
                response = self._transport(method, url, timeout=self.timeout, **kwargs)
            except (ConnectorError, ResponseTooLarge):
                raise
            except Exception as exc:  # 네트워크/타임아웃 계열
                raise errors.from_exception(exc, service=self.service) from exc

            ok = response.status in expected_status if expected_status else 200 <= response.status < 300
            if not ok:
                raise errors.from_response(
                    response.status, service=self.service, body=response.body, headers=response.headers
                )
            return response

        def _note_retry(attempt: int, delay: float, error: ConnectorError) -> None:
            self.retries.append({"attempt": attempt, "delay": round(delay, 3), "code": error.code})

        return run_with_retry(
            _call,
            policy=self.retry_policy,
            method=method,
            idempotent=idempotent,
            sleep=self._sleep,
            on_retry=_note_retry,
        )

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def download(self, url: str, *, stream_to: Any, max_bytes: int, **kwargs: Any) -> Response:
        """바이너리 본문을 `stream_to` 로 흘려 넣는다 (백로그 20번 잔여, §4.7).

        일반 호출과 나누는 이유: 기본 transport 는 본문을 json→text 로 해석하므로, 바이너리를
        그 경로로 받으면 인코딩 추정을 거치며 **조용히 깨진다**. 그래서 Google Drive 의
        download 모드가 그동안 빠져 있었다("깨진 파일을 돌려주는 것보다 기능이 없는 편이 낫다").

        본문을 메모리에 모으지 않고 chunk 단위로 넘긴다. `max_bytes` 를 넘으면 그 자리에서
        끊는다 — 다 받은 뒤 크기를 재면 이미 디스크를 쓴 뒤다. 응답 body 는 받은 바이트 수만
        담는다(파일 내용이 실행 로그·mock 기록으로 새지 않게 한다).
        """
        return self.request("GET", url, stream_to=stream_to, max_bytes=int(max_bytes), **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    # ── 목록 조회 ──────────────────────────────────────────────────────
    def collect(
        self,
        url: str,
        *,
        config: PaginationConfig = PaginationConfig(),
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> PaginationResult:
        base_params = dict(params or {})

        def _fetch(page_params: Dict[str, Any]) -> Any:
            merged = {**base_params, **page_params}
            return self.get(url, params=merged, **kwargs).json()

        return collect_pages(_fetch, config)

    def telemetry(self) -> Dict[str, Any]:
        return {"service": self.service, "attempts": self.attempts, "retries": self.retries}


def _stream_body(raw, sink: Any, max_bytes: int) -> int:
    written = 0
    for chunk in raw.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        written += len(chunk)
        if written > max_bytes:
            raise ResponseTooLarge(f"응답이 한도({max_bytes} bytes)를 넘었다")
        sink.write(chunk)
    return written


def _requests_transport(method: str, url: str, **kwargs: Any) -> Response:
    import requests

    stream_to = kwargs.pop("stream_to", None)
    max_bytes = kwargs.pop("max_bytes", None)

    if stream_to is None:
        raw = requests.request(method, url, **kwargs)
        try:
            body: Any = raw.json()
        except ValueError:
            body = raw.text
        return Response(status=raw.status_code, headers=dict(raw.headers), body=body)

    # 스트리밍 다운로드. 실패 응답은 대개 작은 JSON 이라 그대로 읽어 오류 분류에 넘긴다 —
    # 오류 본문을 파일로 저장해 버리면 사용자는 깨진 파일만 받고 이유를 알 수 없다.
    with requests.request(method, url, stream=True, **kwargs) as raw:
        if not (200 <= raw.status_code < 300):
            try:
                body = raw.json()
            except ValueError:
                body = raw.text[:2000]
            return Response(status=raw.status_code, headers=dict(raw.headers), body=body)
        written = _stream_body(raw, stream_to, int(max_bytes or 0) or (1 << 62))
        return Response(status=raw.status_code, headers=dict(raw.headers), body={"bytes": written})
