import json

import pytest

import evaluation


def _perfect_linear_graph():
    return {
        "title": "요약",
        "description": "입력을 요약한다.",
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "dynamicInputNode", "data": {"inputLabel": "원문"}},
            {"id": "n3", "type": "promptNode", "data": {"userPrompt": "세 문장으로 요약해줘"}},
            {"id": "n4", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "요약가"}},
            {"id": "n5", "type": "outputNode", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
            {"id": "e3", "source": "n3", "target": "n4"},
            {"id": "e4", "source": "n4", "target": "n5"},
        ],
    }


def test_evaluation_suite_has_unique_scenarios():
    # 케이스를 늘릴 때 이 수도 함께 올린다 — id 중복·누락을 막는 것이 목적이다.
    # 31·32 는 포맷 스튜디오 계획 Phase 3(새 문서·디자인물은 formatNode 로) 회귀 케이스다.
    # 33: 데이터 흐름 분리 계획 §6-4 의 FieldBinding 케이스를 더했다
    assert len(evaluation.TEST_CASES) == 33
    assert len({case["id"] for case in evaluation.TEST_CASES}) == 33
    assert evaluation.TEST_CASES[27]["expected_outcome"] == "clarification"


def test_deterministic_score_checks_schema_paths_data_and_compilation():
    result = evaluation.score_generated_graph(evaluation.TEST_CASES[0], _perfect_linear_graph())

    assert result["passed"] is True
    assert result["score"] == 100
    assert result["structural_passed"] is True
    assert result["compile_passed"] is True


def test_deterministic_score_reports_missing_path_and_node():
    graph = _perfect_linear_graph()
    graph["nodes"] = [node for node in graph["nodes"] if node["type"] != "llmNode"]
    graph["edges"] = [edge for edge in graph["edges"] if edge["source"] != "n4" and edge["target"] != "n4"]
    result = evaluation.score_generated_graph(evaluation.TEST_CASES[0], graph)

    assert result["passed"] is False
    assert "llmNode" in result["missing_nodes"]
    assert result["missing_paths"]


@pytest.mark.asyncio
async def test_runner_awaits_four_value_contract_and_emits_valid_sse(monkeypatch, tmp_path):
    async def fake_run_agent_turn(graph_data, message, thread_id, complexity_level):
        return "완료", _perfect_linear_graph(), {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}, None

    monkeypatch.setattr(evaluation, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(evaluation, "RESULTS_DIR", tmp_path)
    events = [chunk async for chunk in evaluation.run_evaluation_suite([1], use_cache=False)]

    assert all(event.startswith("data: ") and event.endswith("\n\n") for event in events)
    payloads = [json.loads(event.removeprefix("data: ").strip()) for event in events]
    assert [payload["type"] for payload in payloads] == ["start", "progress", "complete"]
    assert payloads[-1]["summary"]["pass_count"] == 1
    assert payloads[-1]["summary"]["token_usage"]["total_tokens"] == 5
    assert list(tmp_path.glob("*.json"))


def test_default_profile_uses_three_smoke_cases(monkeypatch):
    monkeypatch.delenv("EVALUATION_SMOKE_CASE_IDS", raising=False)

    profile, tests, budget = evaluation._resolve_evaluation_run()

    assert profile == "smoke"
    assert [test["id"] for test in tests] == [1, 6, 28]
    assert budget == 60_000


@pytest.mark.asyncio
async def test_targeted_profile_rejects_more_than_configured_case_limit(monkeypatch):
    monkeypatch.setenv("EVALUATION_TARGETED_MAX_CASES", "2")

    events = [
        chunk async for chunk in evaluation.run_evaluation_suite([1, 2, 3], use_cache=False)
    ]
    payload = json.loads(events[0].removeprefix("data: ").strip())

    assert payload["type"] == "error"
    assert "최대 2개" in payload["message"]


@pytest.mark.asyncio
async def test_token_budget_stops_before_next_estimated_case(monkeypatch, tmp_path):
    calls = 0

    async def fake_run_agent_turn(graph_data, message, thread_id, complexity_level):
        nonlocal calls
        calls += 1
        return "완료", _perfect_linear_graph(), {
            "input_tokens": 6_000, "output_tokens": 4_000, "total_tokens": 10_000,
        }, None

    monkeypatch.setattr(evaluation, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(evaluation, "RESULTS_DIR", tmp_path)
    monkeypatch.setenv("EVALUATION_ESTIMATED_CASE_TOKENS", "20_000")
    events = [
        chunk async for chunk in evaluation.run_evaluation_suite(
            [1, 2], use_cache=False, max_total_tokens=25_000,
        )
    ]
    complete = json.loads(events[-1].removeprefix("data: ").strip())

    assert calls == 1
    assert complete["summary"]["total_tests"] == 1
    assert complete["summary"]["planned_tests"] == 2
    assert "토큰 예산" in complete["summary"]["stopped_reason"]


@pytest.mark.asyncio
async def test_passed_evaluation_result_is_reused_from_cache(monkeypatch, tmp_path):
    calls = 0

    async def fake_run_agent_turn(graph_data, message, thread_id, complexity_level):
        nonlocal calls
        calls += 1
        return "완료", _perfect_linear_graph(), {
            "input_tokens": 3, "output_tokens": 2, "total_tokens": 5,
        }, None

    monkeypatch.setattr(evaluation, "run_agent_turn", fake_run_agent_turn)
    monkeypatch.setattr(evaluation, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(evaluation, "CACHE_DIR", tmp_path / "cache")

    first = [chunk async for chunk in evaluation.run_evaluation_suite([1], use_cache=True)]
    second = [chunk async for chunk in evaluation.run_evaluation_suite([1], use_cache=True)]
    second_complete = json.loads(second[-1].removeprefix("data: ").strip())

    assert first
    assert calls == 1
    assert second_complete["summary"]["cached_count"] == 1
    assert second_complete["summary"]["token_usage"]["total_tokens"] == 0


def test_binding_case_deducts_when_values_are_moved_by_llm():
    """값을 옮기기만 하는 자리에 LLM/파서를 끼우면 감점 — 바인딩으로 처리하면 만점 후보다.
    감점은 expected_bindings 를 선언한 케이스에만 적용되므로 기존 케이스 점수는 변하지 않는다."""
    case = next(c for c in evaluation.TEST_CASES if c["id"] == 33)
    assert case["expected_bindings"] == [["emailNode", "toEmail"]]

    graph_without = {"nodes": [
        {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/incident"}},
        {"id": "n2", "type": "formatNode", "data": {"formatId": "incident-report", "output": "hwpx"}},
        {"id": "n3", "type": "emailNode", "data": {"toEmail": "manager@example.com", "subject": "시말서"}},
    ], "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
    ]}
    graph_with = {"nodes": [
        graph_without["nodes"][0],
        graph_without["nodes"][1],
        {"id": "n3", "type": "emailNode", "data": {
            "toEmail": "", "subject": "시말서",
            "bindings": {"toEmail": {"source": "n1", "path": "managerEmail"}}}},
    ], "edges": graph_without["edges"]}

    without = evaluation.score_generated_graph(case, graph_without)
    with_bindings = evaluation.score_generated_graph(case, graph_with)
    assert without["missing_bindings"] == [["emailNode", "toEmail"]]
    assert not without["passed"]
    assert with_bindings["missing_bindings"] == []
    assert with_bindings["score"] > without["score"], (with_bindings["score"], without["score"])


def test_existing_cases_have_no_binding_expectations():
    """감점 항목이 기존 케이스에 조용히 번지면 과거 결과와 비교가 깨진다."""
    for case in evaluation.TEST_CASES:
        if case["id"] != 33:
            assert case["expected_bindings"] == [], case["id"]
