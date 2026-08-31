import json

import pytest

from llm.task_spec import TaskSpec, task_coverage_issues
from meta_agent import (
    FlowEdge,
    FlowGraph,
    FlowNode,
    FlowRepairPlan,
    apply_flow_repair_plan,
    repair_flow_partially,
    repair_flow_after_agent,
    repair_disconnected_flow,
    repair_task_coverage_deterministically,
    validate_flow,
    validate_flow_detailed,
)


def _condition_graph():
    return FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="conditionNode", data={
                "rules": [{"id": "low", "operator": "<", "value": "3"}],
            }),
            FlowNode(id="n3", type="outputNode"),
            FlowNode(id="n4", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3", sourceHandle="wrong"),
            FlowEdge(id="e3", source="n2", target="n4", sourceHandle="else"),
        ],
    )


def test_repair_plan_changes_only_requested_edge():
    graph = _condition_graph()
    plan = FlowRepairPlan(
        reason="condition handle 수정",
        remove_edge_ids=["e2"],
        add_edges=[FlowEdge(id="e4", source="n2", target="n3", sourceHandle="low")],
    )

    repaired, notes = apply_flow_repair_plan(graph, plan)

    assert validate_flow(repaired) == (True, [])
    assert {edge.id for edge in repaired.edges} == {"e1", "e3", "e4"}
    assert graph.edges[1].sourceHandle == "wrong"
    assert notes == ["엣지 제거: e2", "엣지 추가: e4"]


def test_repair_plan_operation_limit(monkeypatch):
    monkeypatch.setenv("LLM_REPAIR_MAX_OPERATIONS", "1")
    plan = FlowRepairPlan(remove_edge_ids=["e2", "e3"])

    with pytest.raises(ValueError, match="제한"):
        apply_flow_repair_plan(_condition_graph(), plan)


def test_validator_allows_bounded_loop_back_edge():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="loopNode", data={"maxIterations": 3}),
            FlowNode(id="n3", type="promptNode", data={"userPrompt": "문장을 다듬어줘"}),
            FlowNode(id="n4", type="llmNode", data={"model": "gpt-4o-mini", "systemPrompt": "편집자"}),
            FlowNode(id="n5", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3", sourceHandle="loop_start"),
            FlowEdge(id="e3", source="n3", target="n4"),
            FlowEdge(id="e4", source="n4", target="n2"),
            FlowEdge(id="e5", source="n2", target="n5", sourceHandle="done"),
        ],
    )

    assert validate_flow(graph) == (True, [])


def test_deterministic_repair_removes_exact_duplicate_connections():
    graph = FlowGraph(
        nodes=[FlowNode(id="n1", type="startNode"), FlowNode(id="n2", type="outputNode")],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n1", target="n2"),
        ],
    )

    repaired, notes = repair_disconnected_flow(graph)

    assert [edge.id for edge in repaired.edges] == ["e1"]
    assert notes == ["중복 연결 엣지 e2 제거"]
    assert validate_flow(repaired) == (True, [])


def test_deterministic_repair_moves_distributor_output_to_done_path():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="distributorNode"),
            FlowNode(id="n3", type="llmNode", data={"model": "gpt-4o-mini", "systemPrompt": "설명 생성"}),
            FlowNode(id="n4", type="mergeNode"),
            FlowNode(id="n5", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3"),
            FlowEdge(id="e3", source="n3", target="n4"),
            FlowEdge(id="e4", source="n4", target="n5"),
        ],
    )

    repaired, notes = repair_disconnected_flow(graph)

    assert any(
        edge.source == "n2" and edge.target == "n5" and edge.sourceHandle == "done"
        for edge in repaired.edges
    )
    assert not any(edge.source == "n4" and edge.target == "n5" for edge in repaired.edges)
    assert any("반복 출력을 done 경로" in note for note in notes)
    assert validate_flow(repaired) == (True, [])


def test_deterministic_repair_adds_missing_start_and_terminal():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="dynamicInputNode", data={"inputLabel": "문서"}),
            FlowNode(id="n2", type="llmNode", data={"model": "gpt-4o-mini", "systemPrompt": "작성"}),
        ],
        edges=[FlowEdge(id="e1", source="n1", target="n2")],
    )

    repaired, notes = repair_disconnected_flow(graph)

    assert {node.type for node in repaired.nodes} >= {"startNode", "outputNode"}
    assert any("시작 노드" in note for note in notes)
    assert any("종료 노드" in note for note in notes)
    assert validate_flow(repaired) == (True, [])


def test_deterministic_repair_merges_multiple_missing_start_roots():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="dynamicInputNode", data={"inputLabel": "지원자 정보"}),
            FlowNode(id="n2", type="dynamicInputNode", data={"inputLabel": "Word 서식"}),
            FlowNode(id="n3", type="llmNode", data={"model": "gpt-4o-mini", "systemPrompt": "문서 작성"}),
            FlowNode(id="n4", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n3"),
            FlowEdge(id="e2", source="n2", target="n3"),
            FlowEdge(id="e3", source="n3", target="n4"),
        ],
    )

    repaired, notes = repair_disconnected_flow(graph)

    merge = next(node for node in repaired.nodes if node.type == "mergeNode")
    assert {edge.source for edge in repaired.edges if edge.target == merge.id} == {"n1", "n2"}
    assert any(edge.source == merge.id and edge.target == "n3" for edge in repaired.edges)
    assert any("다중 입력 합류 노드" in note for note in notes)
    assert validate_flow(repaired) == (True, [])


def test_partial_repair_uses_structured_mock_provider(monkeypatch):
    graph = _condition_graph()
    ok, issues = validate_flow_detailed(graph)
    assert ok is False
    response = {
        "reason": "handle 수정",
        "remove_edge_ids": ["e2"],
        "add_edges": [{"id": "e4", "source": "n2", "target": "n3", "sourceHandle": "low"}],
    }
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", json.dumps(response))

    repaired, plan, notes = repair_flow_partially(graph, "점수에 따라 분기해줘", issues)

    assert plan.reason == "handle 수정"
    assert notes
    assert validate_flow(repaired) == (True, [])


@pytest.mark.asyncio
async def test_final_agent_repair_adds_missing_start_path(monkeypatch):
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="dynamicInputNode", data={"inputLabel": "상품 목록"}),
            FlowNode(id="n2", type="outputNode"),
        ],
        edges=[FlowEdge(id="e1", source="n1", target="n2")],
    )
    response = {
        "reason": "시작점 연결",
        "add_nodes": [{"id": "n0", "type": "startNode", "data": {}}],
        "add_edges": [{"id": "e0", "source": "n0", "target": "n1"}],
    }
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", json.dumps(response))

    repaired, notes, issues = await repair_flow_after_agent(graph, "상품을 처리해줘")

    assert issues == []
    assert validate_flow(repaired) == (True, [])
    assert any("누락된 시작 노드" in note for note in notes)


@pytest.mark.asyncio
async def test_final_agent_repair_restores_missing_task_integration(monkeypatch):
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="dynamicInputNode", data={"inputLabel": "회의 내용"}),
            FlowNode(id="n3", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3"),
        ],
    )
    spec = TaskSpec(
        request_kind="create", goal="회의 내용을 이메일로 전송",
        inputs=["회의 내용"], integrations=["Email"], actions=["이메일 전송"],
    )
    response = {
        "reason": "이메일 연동 추가",
        "add_nodes": [{
            "id": "n4", "type": "emailNode", "data": {
                "toEmail": "REPLACE_WITH_RECIPIENT_EMAIL", "subject": "회의 요약",
            },
        }],
        "remove_edge_ids": ["e2"],
        "add_edges": [
            {"id": "e3", "source": "n2", "target": "n4"},
            {"id": "e4", "source": "n4", "target": "n3"},
        ],
    }
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", json.dumps(response))

    repaired, _, issues = await repair_flow_after_agent(
        graph, "회의 내용을 이메일로 보내줘", task_spec=spec,
    )

    assert issues == []
    assert validate_flow(repaired) == (True, [])
    assert "emailNode" in {node.type for node in repaired.nodes}


def test_deterministic_task_repair_replaces_start_with_webhook():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="outputNode"),
        ],
        edges=[FlowEdge(id="e1", source="n1", target="n2")],
    )
    spec = TaskSpec(
        request_kind="create",
        goal="주문 webhook을 받는다",
        trigger="주문 webhook 수신",
    )
    issues = task_coverage_issues(spec, graph.model_dump())

    repaired, notes = repair_task_coverage_deterministically(graph, spec, issues)

    assert repaired.nodes[0].type == "webhookNode"
    assert repaired.nodes[0].data == {"method": "POST", "path": "/webhook"}
    assert any("webhook 트리거" in note for note in notes)
    assert task_coverage_issues(spec, repaired.model_dump()) == []


def test_deterministic_task_repair_inserts_json_parser_before_output():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="llmNode", data={"model": "gpt-4o-mini", "systemPrompt": "JSON 생성"}),
            FlowNode(id="n3", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3"),
        ],
    )
    spec = TaskSpec(
        request_kind="create",
        goal="소개를 JSON으로 변환",
        actions=["JSON으로 변환", "출력"],
    )
    issues = task_coverage_issues(spec, graph.model_dump())

    repaired, _ = repair_task_coverage_deterministically(graph, spec, issues)

    parser = next(node for node in repaired.nodes if node.type == "jsonParserNode")
    assert parser.data == {"mode": "parse"}
    assert any(edge.source == "n2" and edge.target == parser.id for edge in repaired.edges)
    assert any(edge.source == parser.id and edge.target == "n3" for edge in repaired.edges)
    assert validate_flow(repaired) == (True, [])


def test_deterministic_task_repair_builds_document_pipeline():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="dynamicInputNode", data={"inputLabel": "지원자 정보와 Word 서식"}),
            FlowNode(id="n3", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3"),
        ],
    )
    spec = TaskSpec(
        request_kind="create",
        goal="지원자 정보를 Word 서식에 채워 새 파일로 저장",
        inputs=["지원자 정보", "Word 서식"],
        actions=["서식 분석", "파일 저장"],
    )
    issues = task_coverage_issues(spec, graph.model_dump())

    repaired, notes = repair_task_coverage_deterministically(graph, spec, issues)

    types = {node.type for node in repaired.nodes}
    assert {"templateAnalyzerNode", "promptNode", "llmNode", "fileModifierNode"} <= types
    assert any("문서 파이프라인" in note for note in notes)
    assert task_coverage_issues(spec, repaired.model_dump()) == []
    assert validate_flow(repaired) == (True, [])


def test_deterministic_task_repair_merges_condition_results_before_output():
    graph = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode"),
            FlowNode(id="n2", type="conditionNode", data={
                "rules": [{"id": "empty", "operator": "==", "value": ""}],
            }),
            FlowNode(id="n3", type="valueNode", data={"value": "입력이 필요합니다"}),
            FlowNode(id="n4", type="outputNode"),
        ],
        edges=[
            FlowEdge(id="e1", source="n1", target="n2"),
            FlowEdge(id="e2", source="n2", target="n3", sourceHandle="empty"),
            FlowEdge(id="e3", source="n2", target="n4", sourceHandle="else"),
            FlowEdge(id="e4", source="n3", target="n4"),
        ],
    )
    spec = TaskSpec(
        request_kind="create",
        goal="입력이 비어 있으면 안내하고 있으면 결과를 출력",
        actions=["결과 출력"],
        conditions=["비어 있으면 안내, 아니면 출력"],
    )
    issues = task_coverage_issues(spec, graph.model_dump())

    repaired, _ = repair_task_coverage_deterministically(graph, spec, issues)

    merge = next(node for node in repaired.nodes if node.type == "mergeNode")
    assert {edge.source for edge in repaired.edges if edge.target == merge.id} == {"n2", "n3"}
    assert any(edge.source == merge.id and edge.target == "n4" for edge in repaired.edges)
    assert validate_flow(repaired) == (True, [])
