"""node_retry · 인터프리터 노드 재시도 (백로그 32 ENGINE-3 1단계, ADR-0030) 테스트.

계약: (1) 설정은 data.retries/backoffSec 에서 읽고 상한으로 자른다 · (2) 재시도 판정은 오류 코드(retryable)와 부수효과 상태에서 —
성공·고정·비구조화·unknown/applied 는 재시도하지 않는다 · (3) 대기는 지수 백오프, Retry-After 보다 짧지 않고 상한 60초 ·
(4) 인터프리터는 재시도 가능한 실패를 retries 만큼 다시 돌리고 성공하면 기록 **하나**에 attempts·retried 를 남긴다 — outcome 은
success · (5) retries 를 다 써도 실패면 마지막 기록이 error 이고 attempts 가 남는다 · (6) 재시도 불가 오류는 한 번만 ·
(7) 옛 엔진은 설정을 무시한다(생성 소스 무변경) · (8) 시도 사이마다 진행 이벤트 node_retry.
"""

from __future__ import annotations

import copy

import pytest

import execution
import graph
import node_retry
from connectors import errors as connector_errors
from connectors.services import http_request
from node_errors import runtime as node_error_runtime


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target):
    return {"source": source, "target": target}


def http_graph(**http_data):
    data = {"url": "https://api.example.test/items", "method": "GET"}
    data.update(http_data)
    return ([N("s", "startNode"), N("h", "httpRequestNode", **data), N("o", "outputNode")], [E("s", "h"), E("h", "o")])


class FlakyHttp:
    """처음 `failures` 번은 ConnectorError, 그 뒤는 성공 — connectors.services.http_request.call 자리에 끼운다."""

    def __init__(self, failures: int, code: str = connector_errors.RATE_LIMITED, status: int = 429, retry_after=None):
        self.remaining = failures
        self.code, self.status, self.retry_after = code, status, retry_after
        self.calls = 0

    def __call__(self, definition, *, method, url, headers=None, body=None, session=None):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise connector_errors.ConnectorError(code=self.code, service="테스트 API", status=self.status,
                                                  retry_after=self.retry_after)
        return '{"ok": true}'


@pytest.fixture
def slept(monkeypatch):
    calls = []
    monkeypatch.setattr(node_retry, "sleep", lambda seconds: calls.append(seconds))
    return calls


def _run(monkeypatch, engine, nodes, edges):
    monkeypatch.setenv("EXECUTION_ENGINE", engine)
    return graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges))


def _http_steps(logs):
    return [s for s in logs if s.get("node_id") == "h"]


# ── 1. 설정 ─────────────────────────────────────────────────────────────────

def test_설정은_retries_와_backoffSec_에서_읽고_상한으로_자른다():
    assert node_retry.retry_settings(N("x", "httpRequestNode")) is None
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries=0)) is None
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries="3")) == node_retry.RetrySettings(3, 1.0)
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries=9, backoffSec=1000)) == node_retry.RetrySettings(5, 60.0)
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries="많이")) is None
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries=2, backoffSec="bad")) == node_retry.RetrySettings(2, 1.0)
    assert node_retry.retry_settings(N("x", "httpRequestNode", retries=-3)) is None
    assert node_retry.RetrySettings(2, 0.5).max_attempts == 3


# ── 2. 재시도 판정 ──────────────────────────────────────────────────────────

def _entry(status="error", **error):
    return {"node_id": "h", "node_type": "httpRequestNode", "status": status,
            "error": {"code": "CONNECTOR_RATE_LIMITED", "retryable": True, "effectState": "not_applicable", **error}}


def test_재시도_판정은_오류_코드와_부수효과_상태에서_읽는다():
    assert node_retry.retryable_failure([_entry()], 0, "h")["code"] == "CONNECTOR_RATE_LIMITED"
    assert node_retry.retryable_failure([_entry(status="success")], 0, "h") is None
    assert node_retry.retryable_failure([dict(_entry(), pinned=True)], 0, "h") is None
    assert node_retry.retryable_failure([_entry(retryable=False, code="CONNECTOR_AUTH_INVALID")], 0, "h") is None
    assert node_retry.retryable_failure([_entry(effectState="unknown")], 0, "h") is None, "보냈는지 모르면 다시 보내지 않는다"
    assert node_retry.retryable_failure([_entry(effectState="applied")], 0, "h") is None
    assert node_retry.retryable_failure([{"node_id": "h", "status": "error", "error": None}], 0, "h") is None, "비구조화 오류"
    assert node_retry.retryable_failure([_entry()], 1, "h") is None, "since 앞의 기록은 이번 시도가 아니다"
    other = {"node_id": "z", "status": "error", "error": {"retryable": True, "effectState": "not_applicable"}}
    assert node_retry.retryable_failure([other], 0, "h") is None, "다른 노드의 실패는 내 것이 아니다"


def test_대기는_지수_백오프이되_retry_after_보다_짧지_않고_상한이_있다():
    s = node_retry.RetrySettings(retries=3, backoff_sec=1.0)
    assert [node_retry.backoff_delay(s, a) for a in range(3)] == [1.0, 2.0, 4.0]
    assert node_retry.backoff_delay(s, 0, {"retryAfterMs": 10_000}) == 10.0
    assert node_retry.backoff_delay(node_retry.RetrySettings(3, 50.0), 3) == node_retry.BACKOFF_MAX_SEC
    assert node_retry.backoff_delay(node_retry.RetrySettings(1, 0.0), 0) == 0.0


# ── 3. 인터프리터 실행 ──────────────────────────────────────────────────────

def test_인터프리터는_재시도_가능한_실패를_다시_돌리고_성공하면_기록_하나에_시도_내역을_남긴다(monkeypatch, slept):
    flaky = FlakyHttp(failures=2)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=2, backoffSec=0)
    result, _tokens, logs = _run(monkeypatch, "interpreter", nodes, edges)

    assert flaky.calls == 3
    assert '"ok": true' in result
    steps = _http_steps(logs)
    assert len(steps) == 1 and steps[0]["status"] == "success"
    assert steps[0]["attempts"] == 3
    assert [r["code"] for r in steps[0]["retried"]] == ["CONNECTOR_RATE_LIMITED", "CONNECTOR_RATE_LIMITED"]
    assert [r["attempt"] for r in steps[0]["retried"]] == [1, 2]
    assert node_error_runtime.flow_outcome(result, logs) == "success", "접힌 실패 시도가 outcome 을 더럽히면 안 된다"
    assert slept == [0.0, 0.0]


def test_retries_를_다_써도_실패면_마지막_기록이_error_이고_attempts_가_남는다(monkeypatch, slept):
    flaky = FlakyHttp(failures=10)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=2, backoffSec=0.5)
    result, _tokens, logs = _run(monkeypatch, "interpreter", nodes, edges)

    assert flaky.calls == 3
    steps = _http_steps(logs)
    assert len(steps) == 1 and steps[0]["status"] == "error" and steps[0]["error"]["code"] == "CONNECTOR_RATE_LIMITED"
    assert steps[0]["attempts"] == 3 and len(steps[0]["retried"]) == 2
    assert node_error_runtime.flow_outcome(result, logs) == "error"
    assert slept == [0.5, 1.0], "지수 백오프"


def test_retry_after_가_있으면_그만큼은_기다린다(monkeypatch, slept):
    flaky = FlakyHttp(failures=1, retry_after=3)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=1, backoffSec=0)
    _run(monkeypatch, "interpreter", nodes, edges)
    assert flaky.calls == 2 and slept == [3.0]


def test_재시도_불가_오류는_한_번만_돌린다(monkeypatch, slept):
    flaky = FlakyHttp(failures=10, code=connector_errors.AUTH_INVALID, status=401)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=3, backoffSec=0)
    _result, _tokens, logs = _run(monkeypatch, "interpreter", nodes, edges)

    assert flaky.calls == 1
    steps = _http_steps(logs)
    assert steps[0]["status"] == "error" and "attempts" not in steps[0] and "retried" not in steps[0]
    assert slept == []


def test_설정이_없으면_재시도하지_않고_기록도_그대로다(monkeypatch, slept):
    flaky = FlakyHttp(failures=10)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph()
    _result, _tokens, logs = _run(monkeypatch, "interpreter", nodes, edges)
    assert flaky.calls == 1 and "attempts" not in _http_steps(logs)[0] and slept == []


def test_옛_엔진은_설정을_무시한다(monkeypatch, slept):
    """생성 소스는 바뀌지 않는다 — 재시도는 전환된 프로젝트(인터프리터)에서만 효과가 있다."""
    flaky = FlakyHttp(failures=10)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=2, backoffSec=0)
    result, _tokens, logs = _run(monkeypatch, "legacy", nodes, edges)
    assert flaky.calls == 1 and slept == []
    assert _http_steps(logs)[0]["status"] == "error" and "attempts" not in _http_steps(logs)[0]
    assert "HTTP Request Error" in result


def test_시도_사이마다_node_retry_진행_이벤트가_나간다(monkeypatch, slept):
    class Recorder:
        def __init__(self):
            self.events = []

        def node_started(self, node_id, node_type=None):
            self.events.append(("started", node_id))

        def step_logged(self, entry, sequence):
            self.events.append(("finished", entry["node_id"], entry["status"], sequence))

        def node_retry(self, node_id, node_type, *, attempt, max_attempts, error_code, delay_sec):
            self.events.append(("retry", node_id, attempt, max_attempts, error_code, delay_sec))

        def finished(self, status, **_):
            self.events.append(("run", status))

    recorder = Recorder()
    monkeypatch.setattr(execution, "current_observer", lambda: recorder)
    flaky = FlakyHttp(failures=2)
    monkeypatch.setattr(http_request, "call", flaky)
    nodes, edges = http_graph(retries=2, backoffSec=0)
    _run(monkeypatch, "interpreter", nodes, edges)

    retries = [e for e in recorder.events if e[0] == "retry"]
    assert retries == [("retry", "h", 1, 3, "CONNECTOR_RATE_LIMITED", 0.0), ("retry", "h", 2, 3, "CONNECTOR_RATE_LIMITED", 0.0)]
    # 실패한 시도의 node_finished(failed) 뒤에 retry, 마지막에 succeeded — 화면은 이 순서로 그린다
    http_events = [e for e in recorder.events if len(e) > 1 and e[1] == "h"]
    assert [e[0] for e in http_events] == ["started", "finished", "retry", "finished", "retry", "finished"]
    assert http_events[-1][2] == "success"


def test_run_events_관찰자는_node_retry_이벤트를_발행한다():
    import run_events

    got = []
    observer = run_events.RunObserver(run_id=7, project_id=1, executor_user_id=42, session_id="s", trigger_source="manual",
                                      engine="interpreter")
    sub = run_events.subscribe(42)
    try:
        observer.node_retry("h", "httpRequestNode", attempt=1, max_attempts=3, error_code="CONNECTOR_RATE_LIMITED", delay_sec=2.0)
        event = sub.queue.get_nowait()
    finally:
        run_events.unsubscribe(sub)
    assert event["type"] == "node_retry" and event["runId"] == 7
    assert (event["nodeId"], event["attempt"], event["maxAttempts"], event["errorCode"], event["delaySec"]) == ("h", 1, 3, "CONNECTOR_RATE_LIMITED", 2.0)
