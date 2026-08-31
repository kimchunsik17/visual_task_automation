from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace

import pytest

from database import Base
from generation_trace import (
    build_generation_trace,
    compare_graph_signatures,
    graph_fingerprint,
    graph_signature,
    persist_generation_trace,
    record_trace_adoption,
    redact_trace_text,
    summarize_graph,
    trace_to_dict,
)
import models
import meta_agent


def test_trace_redaction_removes_common_secrets_and_email():
    api_key = "sk-" + "abcdefghijklmnop"
    bearer_token = "abcdefghijklmnop"
    value = (
        f"api_key={api_key} bearer {bearer_token} token:super-secret user@example.com"
    )

    redacted = redact_trace_text(value)

    assert api_key not in redacted
    assert bearer_token not in redacted
    assert "super-secret" not in redacted
    assert "user@example.com" not in redacted
    assert "REDACTED" in redacted


def test_trace_omits_request_content_by_default(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    trace = build_generation_trace(
        trace_id="trace-1",
        thread_id="project-1",
        message="지원자 이메일 user@example.com을 요약해줘",
        complexity_level="low",
        graph_data={"nodes": [{"id": "n1", "type": "llmNode", "data": {"secret": "x"}}], "edges": []},
        task_spec={"request_kind": "create", "goal": "지원자 요약"},
        outcome="graph",
        status="completed",
        latency_ms=123,
    )

    assert trace["request_preview"] is None
    assert trace["task_spec"] is None
    assert trace["request_hash"]
    assert trace["request_length"] > 0
    summary = trace["graph_summary"]
    assert summary["node_count"] == 1
    assert summary["edge_count"] == 0
    assert summary["node_types"] == {"llmNode": 1}
    assert summary["fingerprint"]
    assert summary["_signature"]
    assert "secret" not in str(summary)


def test_trace_content_storage_is_opt_in_and_redacted(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "true")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    trace = build_generation_trace(
        trace_id="trace-2",
        thread_id="project-1",
        message="user@example.com에게 보내줘",
        complexity_level="low",
        graph_data={},
        task_spec={"request_kind": "create", "inputs": ["token=top-secret"]},
        outcome="clarification",
        status="completed",
        latency_ms=10,
    )

    assert trace["request_preview"] == "[REDACTED_EMAIL]에게 보내줘"
    assert "top-secret" not in str(trace["task_spec"])


def test_graph_summary_counts_types_without_node_data():
    summary = summarize_graph({
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {"value": "private"}},
            {"id": "n2", "type": "llmNode", "data": {"systemPrompt": "private"}},
            {"id": "n3", "type": "llmNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })

    assert summary == {
        "node_count": 3,
        "edge_count": 1,
        "node_types": {"startNode": 1, "llmNode": 2},
    }


def test_graph_fingerprint_ignores_layout_and_ui_state(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_HASH_SALT", "test-salt")
    first = {
        "nodes": [{
            "id": "n1", "type": "llmNode", "position": {"x": 0, "y": 0},
            "data": {"model": "mock", "isAIModified": True, "aiChanges": ["model"]},
        }],
        "edges": [],
    }
    second = {
        "nodes": [{
            "id": "n1", "type": "llmNode", "position": {"x": 900, "y": 400},
            "data": {"model": "mock", "isAIModified": False},
        }],
        "edges": [],
    }

    assert graph_fingerprint(first) == graph_fingerprint(second)
    assert "mock" not in str(graph_signature(first))


def test_graph_comparison_classifies_acceptance_and_modification(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_HASH_SALT", "test-salt")
    generated_graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "outputNode", "data": {}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    generated = graph_signature(generated_graph)

    accepted = compare_graph_signatures(generated, graph_signature(generated_graph))
    modified_graph = {
        **generated_graph,
        "nodes": [*generated_graph["nodes"], {"id": "n3", "type": "delayNode", "data": {"seconds": 5}}],
    }
    modified = compare_graph_signatures(generated, graph_signature(modified_graph))
    discarded = compare_graph_signatures(generated, graph_signature({"nodes": [], "edges": []}))

    assert accepted["acceptance_status"] == "accepted"
    assert accepted["changed_elements"] == 0
    assert modified["acceptance_status"] == "partially_modified"
    assert modified["added_node_count"] == 1
    assert discarded["acceptance_status"] == "discarded"


def test_generation_trace_persists_and_serializes(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    trace = build_generation_trace(
        trace_id="trace-db",
        thread_id="project-7",
        message="요약해줘",
        complexity_level="low",
        graph_data={"nodes": [], "edges": []},
        outcome="no_graph",
        status="failed",
        latency_ms=20,
        validation_issues=[{"code": "NO_GRAPH", "message": "그래프 없음"}],
    )

    row = persist_generation_trace(session, trace, user_id=None, project_id=7)
    serialized = trace_to_dict(row)

    assert session.query(models.GenerationTrace).count() == 1
    assert serialized["trace_id"] == "trace-db"
    assert serialized["status"] == "failed"
    assert serialized["validation_issues"][0]["code"] == "NO_GRAPH"
    session.close()


def test_trace_adoption_updates_project_and_hides_internal_signature(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setenv("GENERATION_TRACE_HASH_SALT", "test-salt")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "outputNode", "data": {}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    trace = build_generation_trace(
        trace_id="trace-adoption",
        thread_id="project-draft",
        message="출력해줘",
        complexity_level="low",
        graph_data=graph,
        outcome="graph",
        status="completed",
        latency_ms=10,
    )
    row = persist_generation_trace(session, trace, user_id=3, project_id=None)

    metrics = record_trace_adoption(
        session,
        trace_id="trace-adoption",
        user_id=3,
        project_id=9,
        saved_graph_data=graph,
    )
    session.refresh(row)
    serialized = trace_to_dict(row)

    assert metrics["acceptance_status"] == "accepted"
    assert row.project_id == 9
    assert serialized["acceptance_status"] == "accepted"
    assert serialized["edit_metrics"]["changed_elements"] == 0
    assert "_signature" not in serialized["graph_summary"]
    session.close()


def test_trace_adoption_rejects_non_graph_trace(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    trace = build_generation_trace(
        trace_id="trace-chat",
        thread_id="project-3",
        message="안녕",
        complexity_level="low",
        graph_data={"nodes": [], "edges": []},
        outcome="chat",
        status="completed",
        latency_ms=5,
    )
    row = persist_generation_trace(session, trace, user_id=3, project_id=None)

    metrics = record_trace_adoption(
        session,
        trace_id="trace-chat",
        user_id=3,
        project_id=9,
        saved_graph_data={"nodes": [], "edges": []},
    )

    session.refresh(row)
    assert metrics is None
    assert row.project_id is None
    session.close()


def test_training_candidate_requires_opt_in_and_is_sanitized(monkeypatch):
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setenv("LLM_TRAINING_DATA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    api_key = "sk-" + "private-value"
    graph = {
        "nodes": [{
            "id": "n1", "type": "llmNode",
            "data": {"apiKey": api_key, "systemPrompt": "요약해"},
        }],
        "edges": [],
    }
    trace = build_generation_trace(
        trace_id="trace-training",
        thread_id="draft-training",
        message="user@example.com의 내용을 요약해줘",
        complexity_level="low",
        graph_data=graph,
        outcome="graph",
        status="completed",
        latency_ms=5,
        training_consent=True,
    )
    persist_generation_trace(session, trace, user_id=3, project_id=None)

    candidate = session.query(models.TrainingExample).one()
    serialized = str(candidate.generated_graph)
    assert api_key not in serialized
    assert candidate.request_text.startswith("[REDACTED_EMAIL]")

    record_trace_adoption(
        session,
        trace_id="trace-training",
        user_id=3,
        project_id=11,
        saved_graph_data=graph,
    )
    session.refresh(candidate)
    assert candidate.acceptance_status == "accepted"
    assert candidate.project_id == 11
    session.close()


@pytest.mark.asyncio
async def test_agent_turn_attaches_private_trace_payload_without_api_call(monkeypatch):
    class FakeAgent:
        async def ainvoke(self, *_args, **_kwargs):
            return {"messages": [SimpleNamespace(
                content="안녕하세요",
                usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            )]}

    graph = meta_agent.FlowGraph(nodes=[], edges=[])
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("GENERATION_TRACE_STORE_CONTENT", "false")
    monkeypatch.setattr(
        meta_agent,
        "build_agent",
        lambda *args, **kwargs: (FakeAgent(), lambda: graph, lambda: None, lambda: None),
    )

    reply, graph_data, usage, clarification = await meta_agent.run_agent_turn(
        {"nodes": [], "edges": []},
        "안녕",
        thread_id="trace-test",
        trace_id="trace-agent",
    )

    assert reply == "안녕하세요"
    assert graph_data == {"nodes": [], "edges": []}
    assert clarification is None
    assert usage["trace_id"] == "trace-agent"
    assert usage["_generation_trace"]["outcome"] == "chat"
    assert usage["_generation_trace"]["request_preview"] is None
