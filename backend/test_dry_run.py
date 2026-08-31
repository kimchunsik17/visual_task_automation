from dry_run import dry_run_workflow


def test_dry_run_simulates_safe_graph_without_executing_it():
    result = dry_run_workflow({
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "outputNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })

    assert result.success is True
    assert result.compile_passed is True
    assert result.reachable_node_count == 2
    assert {step.status for step in result.steps} == {"simulated"}


def test_dry_run_blocks_external_side_effects():
    result = dry_run_workflow({
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "httpRequestNode", "data": {
                "method": "POST", "url": "https://example.com",
            }},
            {"id": "n3", "type": "outputNode", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    })

    assert result.success is True
    assert result.blocked_side_effect_count == 1
    assert next(step for step in result.steps if step.node_id == "n2").status == "blocked"


def test_dry_run_reports_invalid_graph_and_never_executes_python():
    result = dry_run_workflow({
        "nodes": [{"id": "n1", "type": "pythonNode", "data": {"code": "raise RuntimeError('boom')"}}],
        "edges": [],
    })

    assert result.success is False
    assert result.structural_passed is False
    assert result.blocked_side_effect_count == 1


def test_dry_run_accepts_edges_without_ids():
    """프론트 실행 계열 직렬화가 오랫동안 엣지 id 를 빼고 보냈다(실행기는 id 를 안 읽어서
    무증상). dry_run 이 FlowGraph 재파싱을 도입하면서 'edges.N.id Field required' 로 터졌다 —
    FlowGraph 의 mode="before" 검증기가 누락 id 를 보충하므로 다시는 스키마 오류가 나면 안 된다."""
    from dry_run import dry_run_workflow
    result = dry_run_workflow({
        "nodes": [
            {"id": "node_a", "type": "startNode", "data": {}},
            {"id": "node_b", "type": "promptNode", "data": {"userPrompt": "x"}},
            {"id": "node_c", "type": "llmNode", "data": {"systemPrompt": "y", "model": "gpt-4o-mini"}},
            {"id": "node_d", "type": "outputNode", "data": {}},
        ],
        "edges": [
            {"source": "node_a", "target": "node_b", "sourceHandle": "out", "targetHandle": "in"},
            {"source": "node_b", "target": "node_c", "sourceHandle": "out", "targetHandle": "in"},
            {"source": "node_c", "target": "node_d", "sourceHandle": "out", "targetHandle": "in"},
        ],
    })
    assert not any("FlowGraph schema 오류" in issue for issue in result.issues), result.issues
    assert result.structural_passed and result.success

