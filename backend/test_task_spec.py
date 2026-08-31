import json

import pytest

from llm.task_spec import (
    ClarificationRequest,
    MissingInformation,
    TaskSpec,
    apply_clarification_policy,
    build_task_spec_context,
    normalize_task_spec,
    should_normalize_task_spec,
    task_coverage_issues,
)


def _spec(**overrides):
    data = {
        "request_kind": "create",
        "goal": "날씨를 슬랙으로 알린다",
        "integrations": ["Slack"],
    }
    data.update(overrides)
    return TaskSpec(**data)


def test_fillable_configuration_never_blocks_generation():
    spec = _spec(
        missing_information=[MissingInformation(
            key="slack_channel", description="슬랙 채널이 없습니다.",
            category="configuration", blocks_generation=True,
        )],
        clarification_required=True,
        clarification=ClarificationRequest(question="채널은?", options=["#general", "#alerts"]),
    )

    normalized = apply_clarification_policy(spec)

    assert normalized.clarification_required is False
    assert normalized.clarification is None
    assert normalized.missing_information[0].blocks_generation is False


def test_routing_choice_remains_a_blocker():
    spec = _spec(
        integrations=[],
        missing_information=[MissingInformation(
            key="notification_channel", description="알림 수단이 정해지지 않았습니다.",
            category="routing_choice", blocks_generation=True,
        )],
    )

    normalized = apply_clarification_policy(spec)

    assert normalized.clarification_required is True
    assert normalized.clarification is not None
    assert "질문 필요" in build_task_spec_context(normalized)


def test_selected_integration_channel_is_configuration_not_routing():
    spec = _spec(
        integrations=["KakaoTalk", "Discord"],
        missing_information=[MissingInformation(
            key="discord_channel", description="디스코드 채널을 선택해야 합니다.",
            category="routing_choice", blocks_generation=True,
        )],
    )

    assert apply_clarification_policy(spec).clarification_required is False


def test_explicit_approval_rule_is_not_asked_again():
    spec = _spec(
        goal="10만원 이상 환불은 사람 승인을 거친다",
        conditions=["금액이 10만원 이상이면 승인 요청"],
        missing_information=[MissingInformation(
            key="approval_decision", description="승인 여부가 필요합니다.",
            category="risk_decision", blocks_generation=True,
        )],
    )

    assert apply_clarification_policy(spec).clarification_required is False


def test_only_new_generation_requests_are_normalized():
    assert should_normalize_task_spec("매일 날씨를 조회해서 슬랙으로 보내줘", False) is True
    assert should_normalize_task_spec("안녕하세요", False) is False
    assert should_normalize_task_spec("디스코드", False) is False
    assert should_normalize_task_spec("새 자동화를 만들어줘", True) is False


@pytest.mark.asyncio
async def test_normalizer_uses_provider_structured_output(monkeypatch):
    response = {
        "request_kind": "create",
        "goal": "날씨 알림",
        "trigger": "매일 9시",
        "actions": ["날씨 조회", "슬랙 전송"],
        "integrations": ["Slack"],
        "missing_information": [{
            "key": "slack_channel", "description": "슬랙 채널",
            "category": "configuration", "blocks_generation": True,
        }],
        "clarification_required": True,
        "clarification": {"question": "채널은?", "options": ["#general", "#alerts"]},
    }
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", json.dumps(response, ensure_ascii=False))

    result = await normalize_task_spec("매일 9시 날씨를 슬랙으로 보내줘")

    assert result.error is None
    assert result.spec.goal == "날씨 알림"
    assert result.spec.clarification_required is False
    assert "즉시 생성" in build_task_spec_context(result.spec)


def test_task_coverage_detects_missing_integration_and_runtime_input():
    spec = _spec(inputs=["회의 내용"], integrations=["Email"])
    graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "outputNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }

    issues = task_coverage_issues(spec, graph)

    assert {issue.code for issue in issues} == {
        "INTENT_INTEGRATION_MISSING", "INTENT_RUNTIME_INPUT_MISSING",
    }


def test_task_coverage_passes_when_explicit_intent_is_present():
    spec = _spec(inputs=["회의 내용"], integrations=["Email"])
    graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "dynamicInputNode", "data": {"inputLabel": "회의 내용"}},
            {"id": "n3", "type": "emailNode", "data": {"toEmail": "", "subject": "요약"}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    }

    assert task_coverage_issues(spec, graph) == []


def test_runtime_input_in_missing_information_also_requires_input_node():
    spec = _spec(
        inputs=[],
        missing_information=[MissingInformation(
            key="event_details", description="일정 세부 내용",
            category="runtime_input", blocks_generation=False,
        )],
    )

    issues = task_coverage_issues(spec, {"nodes": [], "edges": []})

    assert "INTENT_RUNTIME_INPUT_MISSING" in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("goal", "actions", "expected_code"),
    [
        ("승인 후 결제 API 호출", ["결제 API 호출"], "INTENT_HTTP_REQUEST_MISSING"),
        ("소개를 JSON으로 변환", ["JSON으로 변환"], "INTENT_JSON_PARSER_MISSING"),
        ("Word 서식에 지원자 정보를 채운다", ["Word 서식 분석"], "INTENT_TEMPLATE_ANALYZER_MISSING"),
    ],
)
def test_task_coverage_detects_specialized_action_nodes(goal, actions, expected_code):
    spec = _spec(goal=goal, actions=actions, integrations=[])

    issues = task_coverage_issues(spec, {
        "nodes": [{"id": "n1", "type": "startNode", "data": {}}],
        "edges": [],
    })

    assert expected_code in {issue.code for issue in issues}


def test_condition_based_classification_does_not_force_llm_node():
    spec = _spec(
        goal="환불 요청을 금액으로 분류한다",
        actions=["환불 요청 분류"],
        conditions=["10만원 이상이면 승인"],
        integrations=[],
    )
    graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "conditionNode", "data": {"rules": []}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }

    codes = {issue.code for issue in task_coverage_issues(spec, graph)}

    assert "INTENT_ACTION_MISSING" not in codes


def test_conditional_screen_output_requires_merge_node():
    spec = _spec(
        goal="입력이 비어 있으면 안내하고 있으면 요약해서 출력",
        actions=["결과 출력"],
        conditions=["입력이 비어 있으면 안내, 아니면 요약"],
        integrations=[],
    )

    codes = {issue.code for issue in task_coverage_issues(spec, {
        "nodes": [
            {"id": "n1", "type": "conditionNode", "data": {}},
            {"id": "n2", "type": "outputNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    })}

    assert "INTENT_MERGE_MISSING" in codes


def test_conditional_goal_requires_merge_when_conditions_field_is_empty():
    spec = _spec(
        goal="입력이 비어 있으면 안내하고 있으면 요약해서 출력",
        actions=["요약 결과 출력"],
        conditions=[],
        integrations=[],
    )

    codes = {issue.code for issue in task_coverage_issues(spec, {
        "nodes": [
            {"id": "n1", "type": "conditionNode", "data": {}},
            {"id": "n2", "type": "llmNode", "data": {}},
            {"id": "n3", "type": "outputNode", "data": {}},
        ],
        "edges": [],
    })}

    assert "INTENT_MERGE_MISSING" in codes


def test_unrequested_review_step_is_not_asked_about():
    """요청에 없는 승인·검토 단계는 묻지도 말고 넣지도 않는다(생성 원칙 1).
    2026-08-31 평가 case32: "팜플렛 만들어서 디스코드에 올려줘" 가 3회 중 2회
    "게시 전 검토 단계를 넣을까요?" 질문으로 끝나 그래프가 아예 안 나왔다."""
    spec = _spec(
        goal="3단 팜플렛 양식으로 신규 서비스 소개 인쇄물을 만들어서 디스코드에 올린다",
        missing_information=[MissingInformation(
            key="posting_review", description="게시 전 검토 단계를 넣을지 선택이 필요합니다.",
            category="risk_decision", blocks_generation=True,
        )],
    )
    assert apply_clarification_policy(spec).clarification_required is False


def test_risky_value_decisions_still_block():
    """값 자체가 위험한 결정은 그대로 되물어야 한다 — 위 예외가 너무 넓어지면 안 된다."""
    spec = _spec(
        goal="조건에 맞는 주문을 자동으로 취소한다",
        missing_information=[MissingInformation(
            key="cancel_threshold", description="어떤 주문을 취소 대상으로 볼지 기준이 없습니다.",
            category="risk_decision", blocks_generation=True,
        )],
    )
    assert apply_clarification_policy(spec).clarification_required is True
