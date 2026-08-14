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
