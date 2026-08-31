"""connectors/mock_runtime.py — 실제 자격증명 없이 워크플로우를 끝까지 돌리는 실행 모드 (ADR-0009).

■ 왜 필요한가
  지금까지 사용자가 워크플로우를 처음 만들고 나서 "정말 도는지" 확인하려면 실제 API 키를
  등록하고 실제로 메시지를 보내야 했다. 그 벽 때문에 첫 성공까지의 시간이 길고, 실패해도
  원인이 설정 문제인지 그래프 문제인지 구분되지 않았다. 그리고 인증 실패나 호출 한도 같은
  실패 경로는 진짜 계정으로는 재현조차 어렵다.

■ 어떻게 동작하는가
  실행 스레드에 "지금은 mock 모드"라는 표시를 켜두면, 커넥터 노드가 세션을 만들 때 실제
  네트워크 transport 대신 노드 정의의 `mock` 시나리오를 재생하는 transport 를 받는다.
  바깥으로 나가는 요청이 하나도 없으므로, 로드맵이 지적한 SSRF 경로(임의 URL 을 서버가
  대신 호출하는 구조) 자체가 생기지 않는다.

■ 동시 실행
  모드는 스레드 로컬이다. 여러 사용자의 mock 실행이 동시에 돌아도 서로의 시나리오나 요청
  기록이 섞이지 않는다. 전역 플래그나 sys.modules 패치를 쓰지 않는 이유가 이것이다.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import mock as mock_fixtures
from .session import Response

# 실행 중 기록을 무한정 쌓지 않기 위한 상한. 반복 노드가 있는 그래프는 요청이 빠르게 불어난다.
MAX_RECORDED_REQUESTS = 200
MAX_BODY_CHARS = 4000

# 요청 기록에서 지워야 하는 헤더. 값이 짧아도 남기지 않는다 — 마스킹한 토큰도 사고가 났을 때
# 어느 계정인지 특정하는 데 쓰일 수 있고, 기록에 남길 이유가 없다.
REDACTED_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "x-goog-api-key", "proxy-authorization"}
REDACTED_PLACEHOLDER = "[redacted]"

# mock 모드에서 자격증명 대신 흘려보내는 값. 실제 토큰 자리에 들어가지만 어디로도 나가지 않는다.
MOCK_TOKEN = "mock-token-not-a-real-credential"


@dataclass
class RecordedRequest:
    node_id: str
    node_type: str
    service: str
    method: str
    url: str
    status: Optional[int]
    latency_ms: int
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_body: Any = None
    response_body: Any = None
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id, "node_type": self.node_type, "service": self.service,
            "method": self.method, "url": self.url, "status": self.status,
            "latency_ms": self.latency_ms, "request_headers": self.request_headers,
            "request_body": self.request_body, "response_body": self.response_body,
            "error_code": self.error_code,
        }


def redact_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {
        key: (REDACTED_PLACEHOLDER if key.lower() in REDACTED_HEADERS else str(value))
        for key, value in (headers or {}).items()
    }


def _truncate(value: Any) -> Any:
    text = value if isinstance(value, str) else None
    if text is None:
        return value
    return text if len(text) <= MAX_BODY_CHARS else text[:MAX_BODY_CHARS] + "…(생략)"


@dataclass
class MockContext:
    """한 번의 mock 실행. 어떤 시나리오로 돌릴지와, 무엇이 오갔는지를 담는다."""

    scenario: str = "success"
    # 노드별로 다른 시나리오를 쓰고 싶을 때(예: 한 노드만 인증 실패로 만들어 분기 확인).
    scenario_by_node: Dict[str, str] = field(default_factory=dict)
    requests: List[RecordedRequest] = field(default_factory=list)
    # 시나리오에 없는 요청이 나갔을 때 어느 노드였는지 알려주기 위한 현재 노드 표시.
    current_node_id: str = ""
    current_node_type: str = ""
    truncated: bool = False
    # 재시도 대기로 "실제 실행이었다면" 흘렀을 시간. 목업에서는 실제로 자지 않는다 —
    # rate limit 시나리오를 확인하려고 사용자가 10초씩 기다릴 이유가 없다. 대신 얼마나
    # 기다리게 될지는 숫자로 보여준다.
    simulated_wait_seconds: float = 0.0

    def scenario_for(self, node_id: str) -> str:
        return self.scenario_by_node.get(node_id, self.scenario)

    def record(self, request: RecordedRequest) -> None:
        if len(self.requests) >= MAX_RECORDED_REQUESTS:
            self.truncated = True
            return
        self.requests.append(request)


_state = threading.local()


def current() -> Optional[MockContext]:
    return getattr(_state, "context", None)


def is_active() -> bool:
    return current() is not None


@contextmanager
def activate(context: MockContext):
    previous = current()
    _state.context = context
    try:
        yield context
    finally:
        _state.context = previous


@contextmanager
def node(node_id: str, node_type: str):
    """지금 실행 중인 노드를 표시한다. 요청 기록이 어느 노드에서 나왔는지 알려면 필요하다."""
    context = current()
    if context is None:
        yield
        return
    before = (context.current_node_id, context.current_node_type)
    context.current_node_id, context.current_node_type = node_id, node_type
    try:
        yield
    finally:
        context.current_node_id, context.current_node_type = before


class RecordingTransport:
    """mock 시나리오를 재생하면서 오간 내용을 기록한다."""

    def __init__(self, inner, service: str, context: MockContext):
        self._inner = inner
        self._service = service
        self._context = context

    def __call__(self, method: str, url: str, **kwargs: Any) -> Response:
        started = time.monotonic()
        status: Optional[int] = None
        body: Any = None
        error_code: Optional[str] = None
        try:
            response = self._inner(method, url, **kwargs)
            status, body = response.status, response.body
            return response
        except Exception as exc:
            error_code = type(exc).__name__
            raise
        finally:
            self._context.record(RecordedRequest(
                node_id=self._context.current_node_id,
                node_type=self._context.current_node_type,
                service=self._service,
                method=method.upper(),
                url=url,
                status=status,
                latency_ms=int((time.monotonic() - started) * 1000),
                request_headers=redact_headers(kwargs.get("headers")),
                request_body=_truncate(kwargs.get("json") if kwargs.get("json") is not None else kwargs.get("params")),
                response_body=_truncate(body),
                error_code=error_code,
            ))


def transport_for(definition) -> Optional[RecordingTransport]:
    """mock 모드가 켜져 있으면 이 노드 정의의 시나리오를 재생할 transport 를 돌려준다.
    꺼져 있으면 None — 호출부는 평소대로 실제 네트워크를 쓴다."""
    context = current()
    if context is None:
        return None
    scenario = context.scenario_for(context.current_node_id)
    inner = mock_fixtures.transport_for(definition.mock, scenario)
    service = definition.connector.service if definition.connector else definition.type
    return RecordingTransport(inner, service, context)


def sleeper():
    """목업 실행용 sleep 대체. 기다린 척만 하고 누적 시간을 기록한다."""
    context = current()
    if context is None:
        return None

    def _record(seconds: float) -> None:
        context.simulated_wait_seconds += float(seconds or 0)

    return _record


def token_for(provider_id: str) -> Optional[str]:
    """mock 모드에서는 실제 자격증명을 읽지 않는다 — 없어도 끝까지 돌아야 하기 때문이다.
    인증 실패 자체는 자격증명이 아니라 `auth_failed` 시나리오로 재현한다."""
    return MOCK_TOKEN if is_active() else None
