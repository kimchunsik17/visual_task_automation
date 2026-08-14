from types import SimpleNamespace

from llm.operations import summarize_generation_operations


def test_generation_operations_summary_aggregates_quality_signals():
    traces = [
        SimpleNamespace(
            outcome="graph", provider="local", status="completed", latency_ms=100,
            graph_summary={"acceptance_status": "accepted", "dry_run": {"success": True}},
            validation_issues=[], token_usage={"total_tokens": 12},
        ),
        SimpleNamespace(
            outcome="graph", provider="local", status="failed", latency_ms=300,
            graph_summary={"acceptance_status": "discarded", "dry_run": {"success": False}},
            validation_issues=[{"code": "NO_GRAPH"}], token_usage={"total_tokens": 8},
        ),
    ]

    summary = summarize_generation_operations(traces, training_example_count=1)

    assert summary["success_rate"] == 50
    assert summary["acceptance_rate"] == 50
    assert summary["dry_run_pass_rate"] == 50
    assert summary["total_tokens"] == 20
    assert summary["validation_issue_codes"] == {"NO_GRAPH": 1}
