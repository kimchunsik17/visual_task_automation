from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from flow_validation import ValidationIssue
from llm.providers import create_chat_model


TASK_SPEC_PROMPT_VERSION = "task-spec-v1"


class MissingInformation(BaseModel):
    key: str = Field(description="Stable snake_case name for the missing information")
    description: str = Field(description="What is missing, written in Korean")
    category: Literal[
        "routing_choice", "configuration", "credential", "runtime_input", "optional_detail", "risk_decision"
    ]
    blocks_generation: bool = Field(
        description="True only when choosing a value changes the workflow topology or a risky action cannot be assumed"
    )


class ClarificationRequest(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list, min_length=2, max_length=4)


class TaskSpec(BaseModel):
    request_kind: Literal["create", "edit", "chat"]
    goal: str
    trigger: Optional[str] = None
    inputs: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    clarification_required: bool = False
    clarification: Optional[ClarificationRequest] = None


@dataclass
class TaskSpecNormalization:
    spec: Optional[TaskSpec]
    token_usage: dict = field(default_factory=lambda: {
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
    })
    latency_ms: int = 0
    prompt_version: str = TASK_SPEC_PROMPT_VERSION
    error: Optional[str] = None


TASK_SPEC_SYSTEM_PROMPT = """\
너는 노코드 워크플로우 생성 요청을 실행 전에 구조화하는 분석기다.
사용자의 말을 TaskSpec으로만 변환하고 워크플로우 자체는 만들지 않는다.

[판정 원칙]
1. request_kind는 새 워크플로우 생성이면 create, 기존 그래프 수정이면 edit, 단순 대화면 chat이다.
2. URL, API key, token, channel ID, database ID, recipient email, 파일 경로처럼 나중에 에디터에서
   채울 수 있는 구체 설정값이 없다는 이유만으로 생성을 막지 않는다. category는 configuration 또는
   credential로 두고 blocks_generation=false로 한다.
3. 실행할 때 사용자가 넣을 문서, CSV, 메시지, 회의록, 상품 목록 등이 아직 없으면 dynamic input으로
   받을 수 있으므로 category=runtime_input, blocks_generation=false다.
4. 사용자가 Slack, 이메일, Discord처럼 연동 종류를 이미 골랐다면 세부 대상이 없어도 질문하지 않는다.
5. 어디로 알릴지처럼 선택에 따라 노드 종류와 그래프 구조 자체가 달라지고 사용자가 아무 선택도 하지
   않았다면 routing_choice, blocks_generation=true로 둘 수 있다.
6. 결제, 삭제, 외부 게시처럼 위험한 작업의 승인 여부가 요청에서 빠졌고 임의 가정이 위험하면
   risk_decision, blocks_generation=true로 둔다.
7. 부수적인 문구, 색상, 예시값은 optional_detail이며 생성을 막지 않는다.
8. clarification_required는 blocks_generation=true인 missing_information이 하나라도 있을 때만 true다.
9. clarification이 필요하면 한 질문과 2~4개의 서로 배타적인 선택지를 한국어로 만든다.
10. 사용자가 합리적으로 요청한 동작을 축소하거나 새로운 기능을 임의로 추가하지 않는다.
"""


def should_normalize_task_spec(user_request: str, has_existing_graph: bool) -> bool:
    if has_existing_graph:
        return False
    text = user_request.strip()
    if len(text) < 6:
        return False
    generation_signal = re.compile(
        r"(만들|생성|자동화|워크플로|플로우|봇|처리해|보내줘|알려줘|출력해|저장해|"
        r"요약해|변환해|조회해|등록해|추가해|workflow|flow|build|create|generate)",
        re.IGNORECASE,
    )
    return bool(generation_signal.search(text))


def apply_clarification_policy(spec: TaskSpec) -> TaskSpec:
    """Do not let provider-specific judgments turn fillable values into blockers."""
    non_blocking = {"configuration", "credential", "runtime_input", "optional_detail"}
    normalized_missing = []
    for item in spec.missing_information:
        selected_integrations = " ".join(spec.integrations).lower()
        explicit_approval = " ".join([
            spec.goal, *spec.actions, *spec.conditions, *spec.constraints,
        ]).lower()
        integration_detail = (
            item.category == "routing_choice"
            and bool(selected_integrations)
            and any(word in f"{item.key} {item.description}".lower() for word in (
                "channel", "채널", "recipient", "수신", "database", "데이터베이스", "workspace", "워크스페이스",
            ))
        )
        approval_already_specified = (
            item.category == "risk_decision"
            and any(word in explicit_approval for word in ("승인", "approval", "거절", "rejected"))
        )
        # 요청에 없는 승인·검토 단계는 **묻지도 말고 넣지도 않는다**(생성 원칙 1 — 요청에 없는
        # 보조 노드는 사용자가 결과를 보고 에디터에서 붙이는 몫이다). 판정이 반대로 걸려 있어서,
        # 승인을 언급하지 않은 요청일 때 오히려 "검토 단계를 넣을까요?"를 되묻고 생성을 멈췄다
        # (2026-08-31 평가 case32: "팜플렛 만들어서 디스코드에 올려줘" 가 3회 중 2회 질문으로 끝났다).
        # 값 자체가 위험한 결정(금액·삭제 대상 등)은 이 예외에 걸리지 않으므로 그대로 차단된다.
        unrequested_review_step = (
            item.category == "risk_decision"
            and not any(word in explicit_approval for word in
                        ("승인", "approval", "검토", "review", "거절", "rejected", "미리보기"))
            and any(word in f"{item.key} {item.description}".lower() for word in
                    ("승인", "approval", "검토", "review", "미리보기", "preview", "확인 단계", "게시 방식"))
        )
        if (item.category in non_blocking or integration_detail
                or approval_already_specified or unrequested_review_step):
            item = item.model_copy(update={"blocks_generation": False})
        normalized_missing.append(item)

    blockers = [item for item in normalized_missing if item.blocks_generation]
    clarification = spec.clarification if blockers else None
    if blockers and clarification is None:
        first = blockers[0]
        clarification = ClarificationRequest(
            question=f"{first.description} 어떤 방식으로 진행할까요?",
            options=["합리적인 기본값 사용", "직접 설정 후 진행"],
        )
    return spec.model_copy(update={
        "missing_information": normalized_missing,
        "clarification_required": bool(blockers),
        "clarification": clarification,
    })


def _usage_from_message(message) -> dict:
    usage = getattr(message, "usage_metadata", None) or {}
    return {
        "input_tokens": int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        "output_tokens": int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }


async def normalize_task_spec(user_request: str, timeout_seconds: Optional[float] = None) -> TaskSpecNormalization:
    started = time.perf_counter()
    timeout = timeout_seconds or float(os.getenv("LLM_TASK_SPEC_TIMEOUT_SECONDS", "20"))
    try:
        llm = create_chat_model(
            profile="fast", temperature=0, required_capabilities={"structured_output"},
        ).with_structured_output(TaskSpec, include_raw=True)
        result = await asyncio.wait_for(
            llm.ainvoke([
                ("system", TASK_SPEC_SYSTEM_PROMPT),
                ("user", f"사용자 요청:\n{user_request}"),
            ]),
            timeout=timeout,
        )
        if isinstance(result, dict) and "parsed" in result:
            parsed = result.get("parsed")
            raw = result.get("raw")
            parsing_error = result.get("parsing_error")
            if parsing_error or parsed is None:
                raise ValueError(f"TaskSpec parsing failed: {parsing_error}")
            usage = _usage_from_message(raw)
        else:
            parsed = result
            usage = _usage_from_message(result)
        if not isinstance(parsed, TaskSpec):
            parsed = TaskSpec.model_validate(parsed)
        spec = apply_clarification_policy(parsed)
        return TaskSpecNormalization(
            spec=spec,
            token_usage=usage,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return TaskSpecNormalization(
            spec=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=str(exc),
        )


def build_task_spec_context(spec: TaskSpec) -> str:
    decision = (
        "질문 필요: ask_clarification을 한 번 호출하고 이번 턴에는 생성하지 않는다."
        if spec.clarification_required
        else "즉시 생성: ask_clarification을 호출하지 말고 누락된 설정은 placeholder/default로 채운다."
    )
    return (
        f"[정규화된 TaskSpec / {TASK_SPEC_PROMPT_VERSION}]\n"
        f"{spec.model_dump_json(exclude_none=True)}\n"
        f"[결정론적 실행 정책] {decision}"
    )


def task_coverage_issues(spec: TaskSpec, graph_data: dict) -> list[ValidationIssue]:
    if spec.request_kind != "create" or spec.clarification_required:
        return []
    node_types = {node.get("type") for node in graph_data.get("nodes", [])}
    issues: list[ValidationIssue] = []

    def require(code: str, description: str, expected: set[str]) -> None:
        if node_types.isdisjoint(expected):
            issues.append(ValidationIssue(
                code=code,
                message=description,
                repairable=True,
                details={"expected_node_types": sorted(expected)},
            ))

    integration_text = " ".join(spec.integrations).lower()
    semantic_text = " ".join(filter(None, [
        spec.goal,
        spec.trigger or "",
        *spec.inputs,
        *spec.actions,
        *spec.integrations,
        *spec.conditions,
        *spec.constraints,
    ])).lower()
    integration_rules = [
        (("slack", "슬랙"), {"slackNode"}),
        (("discord", "디스코드"), {"discordNode"}),
        (("kakao", "카카오"), {"kakaoNode"}),
        (("telegram", "텔레그램"), {"telegramNode"}),
        (("email", "이메일", "메일"), {"emailNode"}),
        (("calendar", "캘린더"), {"googleCalendarNode"}),
        (("sheet", "시트"), {"googleSheetsNode"}),
        (("notion", "노션"), {"notionNode"}),
    ]
    for keywords, expected in integration_rules:
        if any(keyword in integration_text for keyword in keywords):
            require(
                "INTENT_INTEGRATION_MISSING",
                f"TaskSpec에 명시된 연동({', '.join(spec.integrations)})을 실행할 노드가 없다.",
                expected,
            )

    trigger = f"{spec.trigger or ''} {semantic_text}".lower()
    if any(word in trigger for word in ("매일", "매주", "매월", "분마다", "시간마다", "cron", "정기")):
        require("INTENT_TRIGGER_MISSING", f"TaskSpec의 정기 실행 트리거({spec.trigger})가 그래프에 없다.", {"scheduleNode"})
    if "webhook" in trigger or "웹훅" in trigger:
        require("INTENT_TRIGGER_MISSING", f"TaskSpec의 webhook 트리거({spec.trigger})가 그래프에 없다.", {"webhookNode"})

    action_text = f"{' '.join(spec.actions)} {spec.goal}".lower()
    llm_action = any(word in action_text for word in (
        "요약", "분석", "번역", "설명 생성", "콘텐츠 생성", "문서 생성", "summar",
    )) or ("분류" in action_text and not spec.conditions)
    if llm_action:
        require("INTENT_ACTION_MISSING", "TaskSpec의 LLM 처리 액션을 수행할 llmNode가 없다.", {"llmNode"})
    if any(word in action_text for word in ("출력", "보여", "display")):
        require("INTENT_OUTPUT_MISSING", "TaskSpec의 화면 출력 액션을 수행할 outputNode가 없다.", {"outputNode"})
    if any(word in semantic_text for word in ("api 호출", "api 요청", "http 요청", "web api")):
        require(
            "INTENT_HTTP_REQUEST_MISSING",
            "TaskSpec의 외부 API 호출을 수행할 httpRequestNode가 없다.",
            {"httpRequestNode"},
        )
    if any(word in semantic_text for word in ("json으로 변환", "json 변환", "json 형식", "json 파싱")):
        require(
            "INTENT_JSON_PARSER_MISSING",
            "TaskSpec의 JSON 변환 결과를 검증할 jsonParserNode가 없다.",
            {"jsonParserNode"},
        )
    template_request = any(word in semantic_text for word in ("서식", "템플릿")) and any(
        word in semantic_text for word in ("word", "docx", "excel", "xlsx", "pptx", "hwpx", "파일")
    )
    if template_request:
        require(
            "INTENT_ACTION_MISSING",
            "TaskSpec의 문서 서식 값을 생성할 llmNode가 없다.",
            {"llmNode"},
        )
        require(
            "INTENT_TEMPLATE_ANALYZER_MISSING",
            "TaskSpec의 문서 서식을 분석할 templateAnalyzerNode가 없다.",
            {"templateAnalyzerNode"},
        )
        require(
            "INTENT_FILE_MODIFIER_MISSING",
            "TaskSpec의 문서 서식에 값을 저장할 fileModifierNode가 없다.",
            {"fileModifierNode"},
        )
    if "반복" in semantic_text and re.search(r"(?:최대\s*)?\d+\s*번", semantic_text):
        require("INTENT_LOOP_MISSING", "TaskSpec의 제한 반복을 수행할 loopNode가 없다.", {"loopNode"})
    if any(word in semantic_text for word in ("목록 각각", "각각의")):
        require(
            "INTENT_DISTRIBUTOR_MISSING",
            "TaskSpec의 목록 항목별 처리를 수행할 distributorNode가 없다.",
            {"distributorNode"},
        )
    condition_text = " ".join(spec.conditions).lower()
    has_conditional_intent = bool(spec.conditions) or any(
        word in spec.goal.lower() for word in ("이면", "있으면", "비어 있으면", "아니면", "경우")
    )
    conditional_output = (
        has_conditional_intent
        and any(word in action_text for word in ("출력", "보여", "display"))
        and any(word in f"{spec.goal} {condition_text}".lower() for word in ("아니면", "else", "있으면", "경우"))
    )
    if conditional_output or any(word in semantic_text for word in ("결과를 합쳐", "결과 합쳐", "병합")):
        require("INTENT_MERGE_MISSING", "TaskSpec의 결과 병합을 수행할 mergeNode가 없다.", {"mergeNode"})

    if spec.conditions and any(word in condition_text for word in ("조건", "이면", "경우", "미만", "이상", "else")):
        require("INTENT_CONDITION_MISSING", "TaskSpec에 명시된 조건 분기를 수행할 conditionNode가 없다.", {"conditionNode"})
    if any(word in f"{spec.goal} {condition_text}".lower() for word in ("사람 승인", "승인하면", "승인을 거")):
        require("INTENT_APPROVAL_MISSING", "TaskSpec에 명시된 사용자 승인을 수행할 humanApprovalNode가 없다.", {"humanApprovalNode"})

    has_runtime_input = bool(spec.inputs) or any(
        item.category == "runtime_input" for item in spec.missing_information
    )
    runtime_input_labels = spec.inputs or [
        item.description for item in spec.missing_information if item.category == "runtime_input"
    ]
    if has_runtime_input and not spec.trigger:
        require(
            "INTENT_RUNTIME_INPUT_MISSING",
            f"TaskSpec의 실행 시 입력({', '.join(runtime_input_labels)})을 받을 입력 노드가 없다.",
            {"dynamicInputNode", "webhookNode", "telegramTriggerNode", "discordTriggerNode"},
        )
    return issues
