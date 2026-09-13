"""error 출력 핸들 (백로그 32 ENGINE-3 2단계, ADR-0030 추기) — 두 엔진 테스트.

계약: (1) 노드가 실패하면 흐름이 `sourceHandle='error'` 간선으로 가고 보통 하류는 건너뛴다 · (2) 성공하면 보통 하류로 가고
error 갈래는 건너뛴다 · (3) error 갈래의 첫 노드는 오류 계약 공개 필드(nodeId·nodeType·code·message·requestId·retryable) JSON 을
입력으로 받는다 · (4) 두 갈래에서 만나는 재합류 노드는 한 번만 실행된다 · (5) 두 엔진이 같은 결과·같은 로그를 낸다 ·
(6) error 간선이 없는 그래프의 생성 소스는 바뀌지 않는다(헬퍼도 방출되지 않는다) · (7) 재시도를 다 써도 실패면 error 갈래(인터프리터).
"""

from __future__ import annotations

import copy
import json
import re

import pytest

import graph
import node_retry
from connectors import errors as connector_errors
from connectors.services import http_request


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    return e


HTTP = {"url": "https://api.example.test/items", "method": "GET"}


class FlakyHttp:
    def __init__(self, failures: int, code: str = connector_errors.AUTH_INVALID, status: int = 401):
        self.remaining, self.code, self.status, self.calls = failures, code, status, 0

    def __call__(self, definition, *, method, url, headers=None, body=None, session=None):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise connector_errors.ConnectorError(code=self.code, service="테스트 API", status=self.status)
        return '{"ok": true}'


def split_graph(**http_extra):
    """s → h ─(보통)→ ok(valueNode) → o_ok(output) / h ─(error)→ o_err(output)."""
    nodes = [N("s", "startNode"), N("h", "httpRequestNode", **HTTP, **http_extra), N("ok", "valueNode", value="정상 경로"),
             N("o_ok", "outputNode"), N("o_err", "outputNode")]
    edges = [E("s", "h"), E("h", "ok"), E("ok", "o_ok"), E("h", "o_err", "error")]
    return nodes, edges


def join_graph():
    """s → h ─(보통)→ ok(value) ─┐ / h ─(error)→ bad(value) ─┘ → o(output) — 두 갈래가 o 에서 만난다."""
    nodes = [N("s", "startNode"), N("h", "httpRequestNode", **HTTP), N("ok", "valueNode", value="정상 경로"),
             N("bad", "valueNode", value="오류 경로"), N("o", "outputNode")]
    edges = [E("s", "h"), E("h", "ok"), E("h", "bad", "error"), E("ok", "o"), E("bad", "o")]
    return nodes, edges


def _norm(logs):
    return [(s["node_id"], s["status"]) for s in logs]


_REQUEST_ID = re.compile(r'"requestId": "[0-9a-f]+"')


def _norm_result(result):
    """오류 payload 의 requestId 는 실행마다 새로 나온다 — 엔진 비교에서는 지운다."""
    return _REQUEST_ID.sub('"requestId": "*"', str(result))


def run_both(monkeypatch, nodes, edges, failures):
    out = {}
    for engine in ("legacy", "interpreter"):
        flaky = FlakyHttp(failures)
        monkeypatch.setattr(http_request, "call", flaky)
        monkeypatch.setenv("EXECUTION_ENGINE", engine)
        result, _tokens, logs = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges))
        out[engine] = (result, logs, flaky.calls)
    (l_res, l_logs, l_calls), (i_res, i_logs, i_calls) = out["legacy"], out["interpreter"]
    assert _norm_result(i_res) == _norm_result(l_res), "두 엔진의 결과가 다르다"
    assert _norm(i_logs) == _norm(l_logs), "두 엔진의 실행 로그가 다르다"
    assert i_calls == l_calls
    return l_res, l_logs


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(node_retry, "sleep", lambda _s: None)


# ── 1·2·3·5. 갈래 선택과 payload ─────────────────────────────────────────────

def test_실패하면_error_갈래로_가고_보통_하류는_건너뛴다(monkeypatch):
    nodes, edges = split_graph()
    result, logs = run_both(monkeypatch, nodes, edges, failures=10)
    ids = [s["node_id"] for s in logs]
    assert "o_err" in ids and "ok" not in ids and "o_ok" not in ids
    assert next(s for s in logs if s["node_id"] == "h")["status"] == "error"

    payload = json.loads(result)
    assert payload["nodeId"] == "h" and payload["nodeType"] == "httpRequestNode"
    assert payload["code"] == "CREDENTIAL_INVALID" and payload["retryable"] is False
    assert payload["message"] and payload["requestId"]
    assert set(payload) == {"nodeId", "nodeType", "code", "message", "requestId", "retryable"}, "공개 필드만 — 원문 예외·비밀 없음"


def test_성공하면_보통_하류로_가고_error_갈래는_건너뛴다(monkeypatch):
    nodes, edges = split_graph()
    result, logs = run_both(monkeypatch, nodes, edges, failures=0)
    ids = [s["node_id"] for s in logs]
    assert result.endswith("정상 경로") and '{"ok": true}' in result, "valueNode 는 입력 뒤에 값을 덧붙인다"
    assert "ok" in ids and "o_ok" in ids and "o_err" not in ids


# ── 4. 재합류 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("failures, expected", [(10, "오류 경로"), (0, "정상 경로")])
def test_두_갈래에서_만나는_재합류는_한_번만_실행된다(monkeypatch, failures, expected):
    nodes, edges = join_graph()
    result, logs = run_both(monkeypatch, nodes, edges, failures=failures)
    assert result.endswith(expected)
    if failures:
        assert '"code": "CREDENTIAL_INVALID"' in result, "error 갈래의 valueNode 는 payload 를 입력으로 받았다"
    assert [s["node_id"] for s in logs].count("o") == 1
    executed = {s["node_id"] for s in logs}
    assert ("bad" in executed) == (failures > 0) and ("ok" in executed) == (failures == 0)


# ── 6. 생성 소스 ────────────────────────────────────────────────────────────

def test_error_간선이_없으면_생성_소스에_헬퍼도_분기도_없다():
    nodes, edges = split_graph()
    plain_edges = [e for e in edges if e.get("sourceHandle") != "error"]
    src = graph.compile_workflow(copy.deepcopy(nodes), copy.deepcopy(plain_edges))
    assert "_node_failed" not in src and "_node_error_payload" not in src

    with_error = graph.compile_workflow(copy.deepcopy(nodes), copy.deepcopy(edges))
    assert "def _node_failed(node_id):" in with_error and "def _node_error_payload(node_id):" in with_error
    assert "if _node_failed('h'):" in with_error and "_error_payload_h = _node_error_payload('h')" in with_error


def test_흐름_노드의_error_간선은_무시되고_두_엔진이_같다(monkeypatch):
    """conditionNode 는 감쌀 수 없는 본문이라 error 간선을 만들 자리가 없다 — 조용히 무시하고 보통 방출로 간다."""
    nodes = [N("s", "startNode"), N("c", "conditionNode", rules=[]), N("a", "valueNode", value="A"),
             N("z", "valueNode", value="Z"), N("o", "outputNode")]
    edges = [E("s", "c"), E("c", "a", "else"), E("c", "z", "error"), E("a", "o")]
    result, logs = run_both(monkeypatch, nodes, edges, failures=0)
    assert result.endswith("A") and "z" not in {s["node_id"] for s in logs}
    # 규칙 id 가 'error' 인 conditionNode(큐레이션 템플릿에 실제로 있다)는 에러 핸들이 아니다 — 생성 소스도 그대로여야 한다
    rules = [N("s", "startNode"), N("c", "conditionNode", rules=[{"id": "error", "operator": "Contains", "value": "Error"}]),
             N("a", "valueNode", value="A"), N("o", "outputNode")]
    src = graph.compile_workflow(rules, [E("s", "c"), E("c", "a", "error"), E("a", "o")])
    assert "_node_failed" not in src


# ── 7. 재시도와의 결합 ──────────────────────────────────────────────────────

def test_재시도를_다_써도_실패면_error_갈래로_간다(monkeypatch):
    flaky = FlakyHttp(10, code=connector_errors.RATE_LIMITED, status=429)
    monkeypatch.setattr(http_request, "call", flaky)
    monkeypatch.setenv("EXECUTION_ENGINE", "interpreter")
    nodes, edges = split_graph(retries=1, backoffSec=0)
    result, _tokens, logs = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges))

    assert flaky.calls == 2, "재시도 1회 뒤 포기"
    step = next(s for s in logs if s["node_id"] == "h")
    assert step["status"] == "error" and step["attempts"] == 2
    assert json.loads(result)["code"] == "CONNECTOR_RATE_LIMITED"
    assert "ok" not in {s["node_id"] for s in logs}


def test_재시도_끝에_성공하면_보통_하류로_간다(monkeypatch):
    flaky = FlakyHttp(1, code=connector_errors.RATE_LIMITED, status=429)
    monkeypatch.setattr(http_request, "call", flaky)
    monkeypatch.setenv("EXECUTION_ENGINE", "interpreter")
    nodes, edges = split_graph(retries=2, backoffSec=0)
    result, _tokens, logs = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges))

    assert flaky.calls == 2 and result.endswith("정상 경로")
    assert "o_err" not in {s["node_id"] for s in logs}
    assert next(s for s in logs if s["node_id"] == "h")["attempts"] == 2
