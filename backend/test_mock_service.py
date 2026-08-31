"""Mock 탭 (ADR-0009) 테스트.

가장 중요한 성질 두 가지를 고정한다 — 목업 실행 중에는 바깥으로 나가는 요청이 하나도 없어야
하고, 요청 기록에 자격증명이 남지 않아야 한다.
"""

from __future__ import annotations

import json
import threading

import pytest

import mock_service
import node_definition
from connectors import mock_runtime
from connectors.mock import MockScenarioError


def graph(*, http=True, youtube=True, legacy=False):
    nodes = [{"id": "w1", "type": "webhookNode", "data": {}}]
    edges = []
    previous = "w1"
    if http:
        nodes.append({"id": "h1", "type": "httpRequestNode",
                      "data": {"method": "POST", "url": "https://api.example.com/notify", "body": '{"k":1}'}})
        edges.append({"id": f"e_{previous}_h1", "source": previous, "target": "h1"})
        previous = "h1"
    if youtube:
        nodes.append({"id": "y1", "type": "youtubeNode",
                      "data": {"mode": "create_comment", "videoId": "v1", "commentText": "댓글"}})
        edges.append({"id": f"e_{previous}_y1", "source": previous, "target": "y1"})
        previous = "y1"
    if legacy:
        nodes.append({"id": "k1", "type": "kakaoNode", "data": {"accessToken": "", "receiver": ""}})
        edges.append({"id": f"e_{previous}_k1", "source": previous, "target": "k1"})
        previous = "k1"
    nodes.append({"id": "o1", "type": "outputNode", "data": {}})
    edges.append({"id": f"e_{previous}_o1", "source": previous, "target": "o1"})
    return {"nodes": nodes, "edges": edges}


def run(scenario="success", **kwargs):
    return mock_service.run(graph(**kwargs), db=None, project_id=1, entry_node_id="w1",
                            payload={"event": "order.created"}, scenario=scenario)


# ── 탐지 ───────────────────────────────────────────────────────────────
def test_entry_nodes_and_sample_payloads_are_offered():
    described = mock_service.describe_graph(graph())
    entry = described["entries"][0]
    assert entry["node_id"] == "w1"
    assert [sample["id"] for sample in entry["samples"]] == ["order_created", "form_submitted", "plain_text"]


def test_mockable_nodes_come_from_their_definitions():
    """노드별로 화면을 하드코딩하지 않는다 — 노드가 늘어도 Mock 탭은 고칠 것이 없어야 한다."""
    described = mock_service.describe_graph(graph())
    by_id = {node["node_id"]: node for node in described["mockable_nodes"]}
    assert by_id["h1"]["service"] == "HTTP"
    assert by_id["y1"]["service"] == "YouTube"
    assert "auth_failed" in [scenario["id"] for scenario in by_id["y1"]["scenarios"]]


def test_nodes_that_still_call_out_for_real_are_flagged():
    """목업으로 대체되지 않는데 외부 통신을 하는 노드는 사용자에게 알려야 한다 —
    모르고 실행하면 목업인 줄 알았던 실행이 실제로 메시지를 보낸다."""
    described = mock_service.describe_graph(graph(legacy=True))
    assert [node["node_id"] for node in described["unsupported_nodes"]] == ["k1"]


def test_nodes_without_external_calls_are_not_listed_as_unsupported():
    described = mock_service.describe_graph({
        "nodes": [{"id": "n1", "type": "llmNode", "data": {}}, {"id": "c1", "type": "conditionNode", "data": {}}],
        "edges": [],
    })
    assert described["unsupported_nodes"] == []


# ── 실행 ───────────────────────────────────────────────────────────────
def test_workflow_runs_end_to_end_without_any_credential():
    """사용자가 API 센터에 아무것도 등록하지 않은 상태에서도 끝까지 돌아야 한다 —
    그게 이 기능의 존재 이유다."""
    result = run("success")
    assert result["success"] is True
    assert [request["node_id"] for request in result["requests"]] == ["h1", "y1"]
    assert result["failed_request_count"] == 0


def test_no_real_network_call_escapes_the_mock_run(monkeypatch):
    """목업 실행 중 실제 요청이 한 건이라도 나가면 사용자가 의도하지 않은 외부 영향이 생긴다."""
    import requests

    def explode(*args, **kwargs):
        raise AssertionError("목업 실행 중 실제 네트워크 호출이 나갔다")

    monkeypatch.setattr(requests, "request", explode)
    monkeypatch.setattr(requests, "post", explode)
    monkeypatch.setattr(requests, "get", explode)

    assert run("success")["success"] is True


def test_credentials_are_not_written_into_the_request_log():
    """요청 기록은 화면에 그대로 뿌려지고 나중에 fixture 로도 저장된다 — 토큰이 섞이면 안 된다."""
    dumped = json.dumps(run("success")["requests"], ensure_ascii=False)
    assert mock_runtime.MOCK_TOKEN not in dumped
    assert "Bearer" not in dumped
    assert mock_runtime.REDACTED_PLACEHOLDER in dumped


def test_failure_scenarios_are_reproducible_without_a_real_account():
    for scenario in ("auth_failed", "not_found", "server_error"):
        result = run(scenario)
        assert result["success"] is False, scenario
        assert result["failed_request_count"] >= 1, scenario


def test_success_is_judged_from_recorded_requests_not_from_the_result_text():
    """예전 방식(결과 문자열에 '❌' 가 있는지)은 노드마다 실패 표기가 달라서 전부 실패했는데도
    성공으로 보고했다."""
    result = run("auth_failed")
    assert "❌" not in str(result["result"])  # 실패 표기가 다른 형태다
    assert result["success"] is False


def test_rate_limit_scenario_does_not_make_the_user_wait():
    """재시도 대기를 실제로 자면 429 시나리오 한 번 보려고 10초를 기다려야 한다.
    기다린 척만 하고, 얼마나 기다리게 될지는 숫자로 알려준다."""
    result = run("rate_limited")
    assert result["simulated_wait_seconds"] > 0
    assert result["duration_ms"] < 3000


def test_timeout_scenario_is_reported_as_a_failed_request():
    result = run("timeout")
    assert result["success"] is False
    assert any(request["error_code"] for request in result["requests"])


def test_run_reports_which_scenario_was_used():
    assert run("not_found")["scenario"] == "not_found"


def test_a_run_that_executes_nothing_is_not_reported_as_success():
    """아무 노드도 실행되지 않았는데 초록 체크를 보여주면 사용자는 검증이 끝났다고 오해한다."""
    result = mock_service.run({"nodes": "그래프가 아님"}, db=None, project_id=1)
    assert result["success"] is False
    assert result["executed_node_count"] == 0


def test_engine_failure_is_surfaced_instead_of_crashing_the_tab(monkeypatch):
    import graph as graph_module

    monkeypatch.setattr(graph_module, "run_workflow", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("엔진 폭발")))
    result = mock_service.run(graph(), db=None, project_id=1, entry_node_id="w1")
    assert result["success"] is False
    assert "엔진 폭발" in str(result["result"])


# ── mock 모드 자체 ─────────────────────────────────────────────────────
def test_mock_mode_is_off_by_default():
    assert mock_runtime.is_active() is False
    assert mock_runtime.token_for("google_oauth") is None


def test_mock_mode_does_not_leak_between_threads():
    """여러 사용자의 목업 실행이 동시에 돌아도 시나리오와 요청 기록이 섞이면 안 된다."""
    observed = {}

    def worker(name, scenario):
        with mock_runtime.activate(mock_runtime.MockContext(scenario=scenario)):
            import time as _t
            _t.sleep(0.01)
            observed[name] = mock_runtime.current().scenario

    outside = []

    def bystander():
        outside.append(mock_runtime.is_active())

    threads = [threading.Thread(target=worker, args=("a", "success")),
               threading.Thread(target=worker, args=("b", "auth_failed")),
               threading.Thread(target=bystander)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert observed == {"a": "success", "b": "auth_failed"}
    assert outside == [False]
    assert mock_runtime.is_active() is False


def test_mock_mode_restores_the_previous_context():
    with mock_runtime.activate(mock_runtime.MockContext(scenario="outer")):
        with mock_runtime.activate(mock_runtime.MockContext(scenario="inner")):
            assert mock_runtime.current().scenario == "inner"
        assert mock_runtime.current().scenario == "outer"
    assert mock_runtime.current() is None


def test_request_log_is_capped_so_a_loop_cannot_fill_memory():
    context = mock_runtime.MockContext()
    for index in range(mock_runtime.MAX_RECORDED_REQUESTS + 20):
        context.record(mock_runtime.RecordedRequest(
            node_id="n", node_type="t", service="s", method="GET",
            url=f"https://x.dev/{index}", status=200, latency_ms=1,
        ))
    assert len(context.requests) == mock_runtime.MAX_RECORDED_REQUESTS
    assert context.truncated is True


def test_long_bodies_are_truncated_in_the_log():
    from connectors.mock_runtime import _truncate

    assert len(_truncate("x" * 99999)) < 99999


def test_redaction_covers_the_headers_the_roadmap_names():
    redacted = mock_runtime.redact_headers({
        "Authorization": "Bearer secret", "Cookie": "session=abc",
        "X-Api-Key": "key", "Content-Type": "application/json",
    })
    assert redacted["Authorization"] == mock_runtime.REDACTED_PLACEHOLDER
    assert redacted["Cookie"] == mock_runtime.REDACTED_PLACEHOLDER
    assert redacted["X-Api-Key"] == mock_runtime.REDACTED_PLACEHOLDER
    assert redacted["Content-Type"] == "application/json"


def test_node_scoped_scenarios_let_one_node_fail_while_others_succeed():
    """분기 검증에 필요하다 — 한 노드만 실패시켜 오류 경로가 실제로 도는지 본다."""
    result = mock_service.run(graph(), db=None, project_id=1, entry_node_id="w1",
                              payload={}, scenario="success", scenario_by_node={"y1": "auth_failed"})
    by_node = {request["node_id"]: request["status"] for request in result["requests"]}
    assert by_node["h1"] == 200
    assert by_node["y1"] == 401


def test_unknown_scenario_fails_loudly_rather_than_silently_succeeding():
    with pytest.raises(MockScenarioError):
        from connectors import mock as fixtures

        fixtures.transport_for(node_definition.get_definition("youtubeNode").mock, "없는시나리오")


# ── httpRequestNode 이전 ───────────────────────────────────────────────
def test_http_request_node_output_shape_is_unchanged():
    """이 노드의 출력을 뒤 노드(jsonParserNode 등)가 그대로 받아 쓴다 — 형태가 바뀌면
    기존 워크플로우가 조용히 깨진다."""
    from connectors.services import http_request

    definition = node_definition.get_definition("httpRequestNode")
    with mock_runtime.activate(mock_runtime.MockContext(scenario="success")):
        body = http_request.call(definition, method="GET", url="https://api.example.com/x")

    assert json.loads(body) == {"ok": True, "message": "목업 응답입니다"}


def test_http_request_node_rejects_malformed_json_fields():
    from connectors.errors import ConnectorError
    from connectors.services import http_request

    definition = node_definition.get_definition("httpRequestNode")
    with mock_runtime.activate(mock_runtime.MockContext(scenario="success")):
        with pytest.raises(ConnectorError):
            http_request.call(definition, method="POST", url="https://x.dev", body="{이건 JSON 이 아니다")


def test_http_get_is_read_only_and_writes_are_not():
    """dry-run 은 이 등급으로 무엇을 막을지 판단한다."""
    connector = node_definition.get_definition("httpRequestNode").connector
    assert connector.writes_externally("GET") is False
    assert connector.writes_externally("POST") is True


# ── 범위 실행 × 목업 (EDITOR_SHORTCUTS §7.4, Slice 4 완료 기준) ──────────
def test_한_노드만_목업으로_돌려도_외부_요청은_나가지_않는다():
    """Slice 4 완료 기준 — 외부 API 를 실제 호출하지 않고 한 노드의 입력부터 출력까지 검증한다.

    예전에는 두 축이 분리돼 있었다: 목업은 트리거에서 전체 실행만, 진입점 실행은 실제 자격증명.
    이제 목업 실행이 임의 노드를 진입점으로 받는다.
    """
    result = mock_service.run(graph(), db=None, project_id=1, start_node_id="y1",
                              sample_input="요약된 본문", scenario="success")
    executed = [step["node_id"] for step in result["logs"]]
    assert executed == ["y1", "o1"]                      # 상류(w1·h1)는 실행되지 않았다
    assert result["success"] is True
    assert result["requests"], "목업 요청 기록이 있어야 한다"
    assert all(request["node_id"] == "y1" for request in result["requests"])


def test_이_노드만_목업_실행은_하류도_돌리지_않는다():
    result = mock_service.run(graph(), db=None, project_id=1, start_node_id="y1", stop_node_id="y1",
                              sample_input="본문", scenario="success")
    assert [step["node_id"] for step in result["logs"]] == ["y1"]
    assert result["success"] is True


def test_목업_실패_시나리오도_노드_단위로_재현된다():
    result = mock_service.run(graph(), db=None, project_id=1, start_node_id="y1",
                              sample_input="본문", scenario="auth_failed")
    step = next(s for s in result["logs"] if s["node_id"] == "y1")
    assert step["status"] == "error" and step["error"]["code"] == "CREDENTIAL_INVALID"
    assert result["success"] is False


def test_고정_출력이_있으면_그_노드는_목업_요청조차_보내지_않는다():
    """§7.3 — 하류를 반복 테스트할 때 상류 노드를 아예 실행하지 않는다."""
    result = mock_service.run(graph(), db=None, project_id=1, entry_node_id="w1", payload={"event": "x"},
                              pinned_outputs={"h1": '{"ok": true}'}, scenario="success")
    pinned = next(step for step in result["logs"] if step["node_id"] == "h1")
    assert pinned["pinned"] is True and pinned["result_data"] == '{"ok": true}'
    assert all(request["node_id"] != "h1" for request in result["requests"])


def test_선택_영역만_목업으로_돌린다():
    result = mock_service.run(graph(), db=None, project_id=1, scope_node_ids=["y1", "o1"],
                              start_node_id="y1", sample_input="본문", scenario="success")
    assert [step["node_id"] for step in result["logs"]] == ["y1", "o1"]
