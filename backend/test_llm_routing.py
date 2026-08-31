import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from llm.routing import HybridRunnable, is_high_risk_input, routing_metrics
from llm.routing import HybridChatModel
from llm.providers.adapters import MockChatModel


def test_hybrid_router_falls_back_after_local_error(monkeypatch):
    monkeypatch.setenv("LLM_HIGH_RISK_FORCE_HOSTED", "false")
    routing_metrics.reset()

    def fail(_value):
        raise RuntimeError("local unavailable")

    router = HybridRunnable(
        RunnableLambda(fail),
        RunnableLambda(lambda _value: "hosted"),
        local_percentage=100,
    )

    assert router.invoke("normal request") == "hosted"
    metrics = routing_metrics.snapshot()
    assert metrics["local_attempts"] == 1
    assert metrics["fallback_successes"] == 1


@pytest.mark.asyncio
async def test_hybrid_router_forces_high_risk_request_to_hosted(monkeypatch):
    monkeypatch.setenv("LLM_HIGH_RISK_FORCE_HOSTED", "true")
    routing_metrics.reset()
    router = HybridRunnable(
        RunnableLambda(lambda _value: "local"),
        RunnableLambda(lambda _value: "hosted"),
        local_percentage=100,
    )

    result = await router.ainvoke([HumanMessage(content="결제 워크플로우를 만들어줘")])

    assert result == "hosted"
    assert routing_metrics.snapshot()["forced_hosted"] == 1


def test_high_risk_detection_uses_last_user_message_only(monkeypatch):
    monkeypatch.setenv("LLM_HIGH_RISK_FORCE_HOSTED", "true")
    messages = [
        AIMessage(content="결제와 삭제를 지원할 수 있습니다"),
        HumanMessage(content="회의록을 요약해줘"),
    ]

    assert is_high_risk_input(messages) is False


def test_hybrid_chat_model_keeps_structured_output_contract(monkeypatch):
    monkeypatch.setenv("LLM_HIGH_RISK_FORCE_HOSTED", "false")
    model = HybridChatModel(
        primary=MockChatModel(response='{"value":"local"}'),
        fallback=MockChatModel(response='{"value":"hosted"}'),
        local_percentage=100,
    )

    result = model.with_structured_output(dict).invoke("normal request")

    assert result == {"value": "local"}
