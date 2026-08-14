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


def test_evaluation_suite_has_30_unique_scenarios():
    assert len(evaluation.TEST_CASES) == 30
    assert len({case["id"] for case in evaluation.TEST_CASES}) == 30
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
