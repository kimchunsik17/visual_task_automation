from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dry_run import dry_run_workflow
from evaluation import TEST_CASES
from flow_validation import validation_issues
from llm.task_spec import TASK_SPEC_SYSTEM_PROMPT, TaskSpec, task_coverage_issues
from meta_agent import PLACEHOLDER_URL, FlowGraph, validate_flow
from training.export_dataset import GENERATION_SYSTEM_PROMPT, REPAIR_SYSTEM_PROMPT


DATASET_VERSION = "synthetic-v1"
SPLITS = ("train", "validation", "test")
KINDS = ("generation", "repair", "clarification")
CLARIFICATION_SYSTEM_PROMPT = TASK_SPEC_SYSTEM_PROMPT + (
    "\n반드시 TaskSpec JSON 객체만 반환하고 설명이나 마크다운을 덧붙이지 않는다."
)

DOMAINS = [
    ("고객지원", "고객 문의"),
    ("채용", "지원자 정보"),
    ("교육", "학습 피드백"),
    ("쇼핑몰", "상품과 주문"),
    ("콘텐츠", "콘텐츠 초안"),
    ("마케팅", "캠페인 반응"),
    ("재무", "비용 요청"),
    ("법무", "계약 검토 요청"),
    ("의료행정", "예약 문의"),
    ("제조", "설비 점검 기록"),
    ("물류", "배송 상태"),
    ("부동산", "매물 문의"),
    ("여행", "여행 요청"),
    ("행사", "참가 신청"),
    ("연구", "연구 메모"),
    ("공공서비스", "민원 내용"),
    ("비영리", "후원 문의"),
    ("보안운영", "보안 이벤트"),
    ("게임운영", "플레이어 신고"),
    ("에너지", "사용량 기록"),
]


def split_for_domain(domain_index: int) -> str:
    if domain_index < 16:
        return "train"
    if domain_index < 18:
        return "validation"
    return "test"


def _josa(word: str, consonant_form: str, vowel_form: str) -> str:
    last = ord(word[-1]) if word else 0
    has_final_consonant = 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 != 0
    return word + (consonant_form if has_final_consonant else vowel_form)


class FlowBuilder:
    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []

    def add(self, node_type: str, data: dict[str, Any] | None = None) -> str:
        node_id = f"n{len(self.nodes) + 1}"
        self.nodes.append({"id": node_id, "type": node_type, "data": data or {}})
        return node_id

    def connect(
        self,
        source: str,
        target: str,
        *,
        source_handle: str | None = None,
        target_handle: str | None = None,
    ) -> None:
        edge: dict[str, Any] = {
            "id": f"e{len(self.edges) + 1}",
            "source": source,
            "target": target,
        }
        if source_handle is not None:
            edge["sourceHandle"] = source_handle
        if target_handle is not None:
            edge["targetHandle"] = target_handle
        self.edges.append(edge)

    def build(self, title: str, description: str) -> dict[str, Any]:
        return {
            "title": title,
            "description": description,
            "nodes": self.nodes,
            "edges": self.edges,
        }


def _llm(system_prompt: str, *, structured: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "model": "gpt-4o-mini",
        "systemPrompt": system_prompt,
    }
    if structured:
        schema = {
            "title": "WorkflowResult",
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "priority": {"type": "string"},
            },
            "required": ["title", "summary", "priority"],
            "additionalProperties": False,
        }
        data.update({
            "useStructuredOutput": True,
            "jsonSchema": json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
        })
    return data


def _spec(
    *,
    goal: str,
    trigger: str,
    inputs: list[str],
    actions: list[str],
    integrations: list[str] | None = None,
    conditions: list[str] | None = None,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    return TaskSpec(
        request_kind="create",
        goal=goal,
        trigger=trigger,
        inputs=inputs,
        actions=actions,
        integrations=integrations or [],
        conditions=conditions or [],
        constraints=(constraints or []) + ["인증정보와 실행 시 값은 placeholder로 유지"],
        assumptions=["누락된 연결 설정은 에디터에서 실행 전에 입력"],
        missing_information=[],
        clarification_required=False,
        clarification=None,
    ).model_dump(mode="json")


def _linear_summary(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} 팀에서 입력한 {_josa(subject, '을', '를')} 핵심 세 문장으로 요약해 결과 화면에 보여줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    instruction = b.add("promptNode", {"userPrompt": f"{subject}의 사실을 보존해 세 문장으로 요약하세요."})
    model = b.add("llmNode", _llm(f"당신은 {domain} 문서 요약 담당자입니다. 추측하지 마세요."))
    output = b.add("outputNode")
    for source, target in ((start, value), (value, instruction), (instruction, model), (model, output)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 요약 결과 표시", trigger="사용자 실행", inputs=[subject], actions=["세 문장 요약", "화면 출력"])
    return prompt, spec, b.build(f"{domain} 요약", f"입력된 {_josa(subject, '을', '를')} 요약해 표시합니다.")


def _structured_extract(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}의 {subject}에서 제목, 요약, 우선순위를 JSON으로 추출해 화면에 출력해줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    model = b.add("llmNode", _llm(f"{domain} 입력을 지정된 구조로 정리하세요.", structured=True))
    parser = b.add("jsonParserNode", {"mode": "parse"})
    output = b.add("outputNode")
    for source, target in ((start, value), (value, model), (model, parser), (parser, output)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 구조화", trigger="사용자 실행", inputs=[subject], actions=["JSON 형식으로 정보 추출", "화면 출력"])
    return prompt, spec, b.build(f"{domain} 정보 추출", f"{_josa(subject, '을', '를')} 안전한 JSON으로 구조화합니다.")


def _conditional_notice(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}의 {subject}에 '긴급'이 포함되면 이메일로 보내고, 아니면 슬랙 기록 채널에 남겨줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    condition = b.add("conditionNode", {"rules": [{"id": "urgent", "operator": "Contains", "value": "긴급"}]})
    email = b.add("emailNode", {"toEmail": "{{recipient_email}}", "subject": f"[{domain}] 긴급 알림"})
    slack = b.add("slackNode", {"token": "{{API_CENTER:slack}}", "channel": "{{slack_channel}}"})
    b.connect(start, value)
    b.connect(value, condition)
    b.connect(condition, email, source_handle="urgent")
    b.connect(condition, slack, source_handle="else")
    spec = _spec(goal=f"{subject} 긴급도별 전달", trigger="사용자 실행", inputs=[subject], actions=["조건 분기", "알림 전송"], integrations=["이메일", "Slack"], conditions=["긴급 포함 시 이메일, 그 외 Slack"])
    return prompt, spec, b.build(f"{domain} 긴급 분기", f"{subject}의 긴급 여부에 따라 전달 경로를 나눕니다.")


def _scheduled_monitor(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}용 상태 API를 30분마다 확인하고 응답에 DOWN이 있으면 슬랙 경고, 정상이면 결과만 남겨줘."
    b = FlowBuilder()
    schedule = b.add("scheduleNode", {"cronExpression": "*/30 * * * *"})
    request = b.add("httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL})
    condition = b.add("conditionNode", {"rules": [{"id": "down", "operator": "Contains", "value": "DOWN"}]})
    slack = b.add("slackNode", {"token": "{{API_CENTER:slack}}", "channel": "{{slack_channel}}"})
    output = b.add("outputNode")
    b.connect(schedule, request)
    b.connect(request, condition)
    b.connect(condition, slack, source_handle="down")
    b.connect(condition, output, source_handle="else")
    spec = _spec(goal=f"{domain} 상태 감시", trigger="30분마다", inputs=["상태 API 응답"], actions=["API 조회", "조건 분기", "장애 알림"], integrations=["상태 API", "Slack"], conditions=["DOWN 응답일 때만 경고"])
    return prompt, spec, b.build(f"{domain} 상태 감시", f"정기적으로 {domain} 상태를 점검합니다.")


def _webhook_sheet(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} webhook으로 들어오는 {subject} JSON을 파싱해서 구글 시트에 한 행씩 추가해줘."
    b = FlowBuilder()
    webhook = b.add("webhookNode")
    parser = b.add("jsonParserNode", {"mode": "parse"})
    sheet = b.add("googleSheetsNode", {"mode": "append", "spreadsheetId": "{{spreadsheet_id}}", "range": "Records!A:Z", "values": ""})
    b.connect(webhook, parser)
    b.connect(parser, sheet)
    spec = _spec(goal=f"{subject} 시트 적재", trigger="webhook 수신", inputs=[f"{subject} JSON"], actions=["JSON 파싱", "행 추가"], integrations=["webhook", "Google Sheets"])
    return prompt, spec, b.build(f"{domain} 시트 적재", f"webhook {_josa(subject, '을', '를')} 시트에 추가합니다.")


def _email_digest(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} 담당자가 붙여 넣은 {_josa(subject, '을', '를')} 정중한 주간 보고서로 정리해 이메일로 보내줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    model = b.add("llmNode", _llm(f"{domain} 주간 보고서를 간결하고 사실 중심으로 작성하세요."))
    email = b.add("emailNode", {"toEmail": "{{recipient_email}}", "subject": f"{domain} 주간 보고"})
    for source, target in ((start, value), (value, model), (model, email)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 주간 보고 발송", trigger="사용자 실행", inputs=[subject], actions=["보고서 요약", "이메일 발송"], integrations=["이메일"])
    return prompt, spec, b.build(f"{domain} 주간 메일", f"{_josa(subject, '을', '를')} 정리해 이메일로 전송합니다.")


def _telegram_assistant(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} 텔레그램 봇에 {subject} 질문이 오면 짧고 정확하게 답장하는 흐름을 만들어줘."
    b = FlowBuilder()
    trigger = b.add("telegramTriggerNode", {"botToken": "{{API_CENTER:telegram}}"})
    model = b.add("llmNode", _llm(f"{domain} 문의에 확인된 내용만 세 문장 이내로 답하세요."))
    output = b.add("telegramNode", {"botToken": "{{API_CENTER:telegram}}", "chatId": ""})
    b.connect(trigger, model)
    b.connect(model, output)
    spec = _spec(goal=f"{domain} 텔레그램 질의 응답", trigger="Telegram 메시지", inputs=[f"{subject} 질문"], actions=["답변 생성", "원 대화에 응답"], integrations=["Telegram"])
    return prompt, spec, b.build(f"{domain} 텔레그램 도우미", f"텔레그램에서 {subject} 질문에 답합니다.")


def _database_report(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"매일 오후 6시에 {domain} 데이터베이스에서 오늘의 {subject} 건수를 읽기 전용으로 조회하고 요약해줘."
    b = FlowBuilder()
    schedule = b.add("scheduleNode", {"cronExpression": "0 18 * * *"})
    database = b.add("databaseNode", {"connectionString": "", "query": "SELECT COUNT(*) AS total FROM records WHERE created_at >= CURRENT_DATE"})
    model = b.add("llmNode", _llm(f"{domain} 일일 집계를 숫자를 바꾸지 말고 한 문단으로 설명하세요."))
    output = b.add("outputNode")
    for source, target in ((schedule, database), (database, model), (model, output)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 일일 집계", trigger="매일 오후 6시", inputs=["읽기 전용 조회 결과"], actions=["SELECT 조회", "집계 요약", "화면 출력"], integrations=["SQL database"], constraints=["SELECT 또는 WITH 쿼리만 사용"])
    return prompt, spec, b.build(f"{domain} 일일 집계", f"오늘의 {subject} 건수를 조회해 요약합니다.")


def _crawler_digest(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} 팀이 지정할 공개 웹페이지를 크롤링해서 {subject} 관련 변경점을 요약해줘."
    b = FlowBuilder()
    start = b.add("startNode")
    crawler = b.add("webCrawlerNode", {"url": PLACEHOLDER_URL})
    model = b.add("llmNode", _llm(f"{domain} 관련 변경점만 근거와 함께 요약하세요."))
    output = b.add("outputNode")
    for source, target in ((start, crawler), (crawler, model), (model, output)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 웹 변경점 요약", trigger="사용자 실행", inputs=["공개 웹페이지"], actions=["웹 크롤링", "변경점 요약", "화면 출력"], integrations=["공개 웹페이지"])
    return prompt, spec, b.build(f"{domain} 웹 동향", f"지정 웹페이지에서 {subject} 변경점을 요약합니다.")


def _document_fill(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} 담당자가 입력한 {_josa(subject, '을', '를')} Word 서식의 빈칸에 맞게 정리해 새 문서로 저장해줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    analyzer = b.add("templateAnalyzerNode", {"template_path": "uploads/template.docx"})
    model = b.add("llmNode", _llm("서식의 필드 이름을 키로 하는 유효한 JSON 객체만 반환하세요."))
    modifier = b.add("fileModifierNode", {"template_path": "uploads/template.docx", "output_path": "uploads/completed.docx"})
    for source, target in ((start, value), (value, analyzer), (analyzer, model), (model, modifier)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} Word 서식 작성", trigger="사용자 실행", inputs=[subject, "Word 서식 파일"], actions=["서식 분석", "문서 값 생성", "새 파일 저장"])
    return prompt, spec, b.build(f"{domain} 서식 작성", f"{_josa(subject, '을', '를')} Word 서식에 채워 저장합니다.")


def _poster(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}의 {_josa(subject, '을', '를')} 입력받아 900x1200 PNG 안내 포스터로 저장해줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    model = b.add("llmNode", _llm("접근성 높은 단일 HTML 포스터를 만들고 HTML 코드만 반환하세요."))
    poster = b.add("posterGeneratorNode", {"outputFormat": "png", "width": 900, "height": 1200, "outputPath": "uploads/poster.png"})
    for source, target in ((start, value), (value, model), (model, poster)):
        b.connect(source, target)
    spec = _spec(goal=f"{subject} 안내 포스터 생성", trigger="사용자 실행", inputs=[subject], actions=["HTML 디자인 생성", "PNG 포스터 저장"])
    return prompt, spec, b.build(f"{domain} 안내 포스터", f"{_josa(subject, '을', '를')} PNG 포스터로 만듭니다.")


def _delayed_email(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain} webhook으로 {_josa(subject, '이', '가')} 접수되면 10분 기다린 뒤 확인 이메일을 보내줘."
    b = FlowBuilder()
    webhook = b.add("webhookNode")
    delay = b.add("delayNode", {"seconds": 600})
    email = b.add("emailNode", {"toEmail": "{{recipient_email}}", "subject": f"{domain} 접수 확인"})
    b.connect(webhook, delay)
    b.connect(delay, email)
    spec = _spec(goal=f"{subject} 지연 확인 메일", trigger="webhook 수신", inputs=[subject], actions=["10분 대기", "확인 이메일 발송"], integrations=["webhook", "이메일"])
    return prompt, spec, b.build(f"{domain} 지연 확인", f"{subject} 접수 10분 후 확인 메일을 보냅니다.")


def _bounded_refinement(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}의 {subject} 문장을 최대 3번 반복해서 명확하게 다듬고 최종 결과를 보여줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    loop = b.add("loopNode", {"maxIterations": 3})
    model = b.add("llmNode", _llm(f"{domain} 문장을 의미를 유지하며 더 명확하게 다듬으세요."))
    output = b.add("outputNode")
    b.connect(start, value)
    b.connect(value, loop)
    b.connect(loop, model, source_handle="loop_start")
    b.connect(model, loop)
    b.connect(loop, output, source_handle="done")
    spec = _spec(goal=f"{subject} 문장 개선", trigger="사용자 실행", inputs=[subject], actions=["최대 3번 반복 개선", "최종 결과 출력"])
    return prompt, spec, b.build(f"{domain} 문장 개선", f"{subject} 문장을 제한된 횟수로 다듬습니다.")


def _list_distribution(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}에서 입력한 {subject} JSON 목록 각각의 한 줄 설명을 만들고 처리가 끝나면 결과를 보여줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": f"{subject} JSON 목록", "inputType": "textarea"})
    parser = b.add("jsonParserNode", {"mode": "parse"})
    distributor = b.add("distributorNode")
    model = b.add("llmNode", _llm(f"{domain} 목록의 현재 항목을 한 줄로 설명하세요."))
    output = b.add("outputNode")
    for source, target in ((start, value), (value, parser), (parser, distributor)):
        b.connect(source, target)
    b.connect(distributor, model)
    b.connect(distributor, output, source_handle="done")
    spec = _spec(goal=f"{subject} 목록별 설명", trigger="사용자 실행", inputs=[f"{subject} JSON 목록"], actions=["JSON 파싱", "목록 각각 설명 생성", "처리 완료 후 출력"])
    return prompt, spec, b.build(f"{domain} 목록 설명", f"{subject} 목록을 항목별로 처리합니다.")


def _approval_api(domain: str, subject: str) -> tuple[str, dict, dict]:
    prompt = f"{domain}의 {_josa(subject, '을', '를')} 담당자에게 보여주고 승인되면 외부 API로 전송하며 거절되면 안내 메일을 보내줘."
    b = FlowBuilder()
    start = b.add("startNode")
    value = b.add("dynamicInputNode", {"inputLabel": subject, "inputType": "textarea"})
    approval = b.add("humanApprovalNode", {"message": f"{subject} 외부 전송을 승인하시겠습니까?"})
    request = b.add("httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL, "headers": "{}", "body": "{{approval_payload}}"})
    output = b.add("outputNode")
    email = b.add("emailNode", {"toEmail": "{{recipient_email}}", "subject": f"{domain} 요청 거절 안내"})
    b.connect(start, value)
    b.connect(value, approval)
    b.connect(approval, request, source_handle="approved")
    b.connect(request, output)
    b.connect(approval, email, source_handle="rejected")
    spec = _spec(goal=f"{subject} 승인 후 외부 전송", trigger="사용자 실행", inputs=[subject], actions=["사람 승인", "승인 시 API 전송", "거절 시 이메일"], integrations=["외부 API", "이메일"], conditions=["승인과 거절 경로 분리"], constraints=["승인 전에는 외부 전송 금지"])
    return prompt, spec, b.build(f"{domain} 승인 전송", f"{_josa(subject, '을', '를')} 승인 후에만 외부로 전송합니다.")


SCENARIOS: list[tuple[str, str, Callable[[str, str], tuple[str, dict, dict]]]] = [
    ("linear_summary", "basic", _linear_summary),
    ("structured_extract", "intermediate", _structured_extract),
    ("conditional_notice", "intermediate", _conditional_notice),
    ("scheduled_monitor", "advanced", _scheduled_monitor),
    ("webhook_sheet", "intermediate", _webhook_sheet),
    ("email_digest", "basic", _email_digest),
    ("telegram_assistant", "intermediate", _telegram_assistant),
    ("database_report", "advanced", _database_report),
    ("crawler_digest", "intermediate", _crawler_digest),
    ("document_fill", "advanced", _document_fill),
    ("poster", "advanced", _poster),
    ("delayed_email", "intermediate", _delayed_email),
    ("bounded_refinement", "advanced", _bounded_refinement),
    ("list_distribution", "advanced", _list_distribution),
    ("approval_api", "advanced", _approval_api),
]


def _record(
    record_id: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    assistant_payload: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": record_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))},
            {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False, separators=(",", ":"))},
        ],
        "metadata": {"dataset_version": DATASET_VERSION, "synthetic": True, **metadata},
    }


def build_generation_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    number = 1
    for scenario, difficulty, builder in SCENARIOS:
        for domain_index, (domain, subject) in enumerate(DOMAINS):
            prompt, spec, graph = builder(domain, subject)
            records.append(_record(
                f"synthetic-generation-{number:04d}",
                GENERATION_SYSTEM_PROMPT,
                {"request": prompt, "task_spec": spec},
                graph,
                {
                    "kind": "generation",
                    "split": split_for_domain(domain_index),
                    "domain": domain,
                    "domain_group": f"domain-{domain_index + 1:02d}",
                    "scenario": scenario,
                    "difficulty": difficulty,
                },
            ))
            number += 1
    return records


def _corrupt_node_data(graph: dict[str, Any]) -> str:
    mutations: dict[str, tuple[str, Any]] = {
        "llmNode": ("model", "unsupported-model"),
        "httpRequestNode": ("method", "PATCH"),
        "jsonParserNode": ("mode", "invalid"),
        "delayNode": ("seconds", -1),
        "databaseNode": ("query", "DELETE FROM records"),
        "scheduleNode": ("cronExpression", ""),
    }
    for node in graph["nodes"]:
        if node["type"] in mutations:
            key, value = mutations[node["type"]]
            node["data"][key] = value
            return f"invalid_{node['type']}_{key}"
    graph["edges"].append({"id": "broken-data-fallback", "source": graph["nodes"][0]["id"], "target": "missing-node"})
    return "dangling_fallback"


def corrupt_graph(graph: dict[str, Any], mutation_index: int) -> tuple[dict[str, Any], str]:
    broken = copy.deepcopy(graph)
    mutation = mutation_index % 10
    if mutation == 0:
        broken["edges"].append({"id": "broken-dangling", "source": broken["nodes"][0]["id"], "target": "missing-node"})
        name = "dangling_edge"
    elif mutation == 1:
        broken["nodes"].append(copy.deepcopy(broken["nodes"][0]))
        name = "duplicate_node_id"
    elif mutation == 2:
        broken["edges"].append(copy.deepcopy(broken["edges"][0]))
        name = "duplicate_edge_id"
    elif mutation == 3:
        broken["nodes"].append({"id": "orphan-node", "type": "delayNode", "data": {"seconds": 1}})
        name = "orphan_node"
    elif mutation == 4:
        broken["nodes"].append({"id": "extra-start", "type": "startNode", "data": {}})
        name = "extra_start"
    elif mutation == 5:
        output = next((node for node in broken["nodes"] if node["type"] == "outputNode"), None)
        if output:
            broken["edges"].append({"id": "broken-output-edge", "source": output["id"], "target": broken["nodes"][0]["id"]})
            name = "output_has_outgoing"
        else:
            broken["edges"].append({"id": "broken-dangling", "source": broken["nodes"][0]["id"], "target": "missing-node"})
            name = "dangling_edge_fallback"
    elif mutation == 6:
        broken["edges"].pop(0)
        name = "missing_edge"
    elif mutation == 7:
        target = broken["nodes"][-1]
        target["id"] = "renamed-without-edges"
        name = "stale_edge_reference"
    elif mutation == 8:
        name = _corrupt_node_data(broken)
    else:
        condition = next((node for node in broken["nodes"] if node["type"] == "conditionNode"), None)
        if condition:
            edge = next(edge for edge in broken["edges"] if edge["source"] == condition["id"])
            edge.pop("sourceHandle", None)
            name = "condition_handle_missing"
        else:
            broken["nodes"].append({"id": "extra-start", "type": "startNode", "data": {}})
            name = "extra_start_fallback"

    try:
        candidate = FlowGraph.model_validate(broken)
        valid, _ = validate_flow(candidate)
    except Exception:
        valid = False
    if valid:
        broken["edges"].append({"id": "forced-dangling", "source": broken["nodes"][0]["id"], "target": "missing-node"})
        name += "+forced_dangling"
    return broken, name


def build_repair_records(generation_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_domain: dict[str, list[dict[str, Any]]] = {domain: [] for domain, _ in DOMAINS}
    for record in generation_records:
        by_domain[record["metadata"]["domain"]].append(record)

    selected: list[dict[str, Any]] = []
    for domain_index, (domain, _) in enumerate(DOMAINS):
        selected.extend(by_domain[domain][:8 if domain_index % 2 == 0 else 7])

    records: list[dict[str, Any]] = []
    for index, source in enumerate(selected, start=1):
        final_graph = json.loads(source["messages"][2]["content"])
        request_payload = json.loads(source["messages"][1]["content"])
        broken, mutation = corrupt_graph(final_graph, index - 1)
        try:
            graph_model = FlowGraph.model_validate(broken)
            valid, errors = validate_flow(graph_model)
        except Exception as exc:
            valid, errors = False, [f"FlowGraph schema 오류: {exc}"]
        if valid or not errors:
            raise ValueError(f"Repair source must be invalid: {source['id']} ({mutation})")
        issues = [issue.model_dump(mode="json") for issue in validation_issues(errors)]
        records.append(_record(
            f"synthetic-repair-{index:04d}",
            REPAIR_SYSTEM_PROMPT,
            {"request": request_payload["request"], "generated_graph": broken, "validation_issues": issues},
            final_graph,
            {
                "kind": "repair",
                "split": source["metadata"]["split"],
                "domain": source["metadata"]["domain"],
                "domain_group": source["metadata"]["domain_group"],
                "scenario": source["metadata"]["scenario"],
                "mutation": mutation,
                "source_generation_id": source["id"],
            },
        ))
    return records


def _clarification_spec(domain: str, subject: str, kind: str) -> tuple[str, dict[str, Any]]:
    if kind == "routing_choice":
        prompt = f"{domain}에서 긴급한 {_josa(subject, '이', '가')} 들어오면 담당 팀에 자동으로 알려줘. 알림 방법은 아직 정하지 않았어."
        spec = TaskSpec.model_validate({
            "request_kind": "create",
            "goal": f"긴급 {subject} 담당 팀 알림",
            "trigger": f"긴급 {subject} 접수",
            "inputs": [subject],
            "actions": ["긴급 여부 판단", "담당 팀 알림"],
            "integrations": [],
            "conditions": ["긴급한 경우 알림"],
            "constraints": [],
            "assumptions": [],
            "missing_information": [{
                "key": "notification_channel",
                "description": "담당 팀에 알릴 채널",
                "category": "routing_choice",
                "blocks_generation": True,
            }],
            "clarification_required": True,
            "clarification": {
                "question": f"{domain} 담당 팀에는 어떤 채널로 알릴까요?",
                "options": ["Slack", "이메일", "Telegram"],
            },
        })
    else:
        prompt = f"{domain}에서 취소 대상으로 분류된 {_josa(subject, '을', '를')} 자동 삭제하는 흐름을 만들어줘. 삭제 전 승인 여부는 정하지 않았어."
        spec = TaskSpec.model_validate({
            "request_kind": "create",
            "goal": f"취소 대상 {subject} 삭제",
            "trigger": f"{subject} 취소 대상 분류",
            "inputs": [subject],
            "actions": ["취소 대상 분류", "데이터 삭제"],
            "integrations": ["외부 저장소"],
            "conditions": ["취소 대상으로 분류된 경우"],
            "constraints": ["삭제는 되돌리기 어려움"],
            "assumptions": [],
            "missing_information": [{
                "key": "deletion_approval_policy",
                "description": "영구 삭제 전에 사람 승인을 받을지 여부",
                "category": "risk_decision",
                "blocks_generation": True,
            }],
            "clarification_required": True,
            "clarification": {
                "question": f"{domain} 데이터의 영구 삭제 전에 사람 승인을 받을까요?",
                "options": ["항상 승인받기", "조건부 승인받기", "승인 없이 삭제"],
            },
        })
    return prompt, spec.model_dump(mode="json")


def build_clarification_records() -> list[dict[str, Any]]:
    requests: list[tuple[int, str]] = []
    for domain_index in range(len(DOMAINS)):
        requests.extend(((domain_index, "routing_choice"), (domain_index, "risk_decision")))
    requests.extend((domain_index, "routing_choice" if domain_index % 2 == 0 else "risk_decision") for domain_index in range(8))
    requests.append((16, "routing_choice"))
    requests.append((18, "risk_decision"))

    records: list[dict[str, Any]] = []
    for index, (domain_index, kind) in enumerate(requests, start=1):
        domain, subject = DOMAINS[domain_index]
        prompt, spec = _clarification_spec(domain, subject, kind)
        if index > 40:
            prompt += f" 운영 정책안 {index - 40}에 맞춰 구성해줘."
        records.append(_record(
            f"synthetic-clarification-{index:04d}",
            CLARIFICATION_SYSTEM_PROMPT,
            {"request": prompt},
            spec,
            {
                "kind": "clarification",
                "split": split_for_domain(domain_index),
                "domain": domain,
                "domain_group": f"domain-{domain_index + 1:02d}",
                "clarification_kind": kind,
            },
        ))
    return records


def _assistant_payload(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(record["messages"][2]["content"])


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    graph_count = 0
    dry_run_count = 0
    repair_invalid_count = 0
    evaluation_prompts = {case["prompt"].strip() for case in TEST_CASES}
    seen_ids: set[str] = set()
    seen_prompts: set[tuple[str, str]] = set()
    all_prompts: set[str] = set()
    split_by_domain: dict[str, str] = {}

    for record in records:
        record_id = record["id"]
        metadata = record["metadata"]
        user_payload = json.loads(record["messages"][1]["content"])
        prompt = str(user_payload["request"]).strip()
        if record_id in seen_ids:
            errors.append(f"duplicate id: {record_id}")
        seen_ids.add(record_id)
        prompt_key = (metadata["kind"], prompt)
        if prompt_key in seen_prompts:
            errors.append(f"duplicate prompt within {metadata['kind']}: {prompt}")
        seen_prompts.add(prompt_key)
        all_prompts.add(prompt)
        if prompt in evaluation_prompts:
            errors.append(f"evaluation leakage: {record_id}")
        group = metadata["domain_group"]
        previous_split = split_by_domain.setdefault(group, metadata["split"])
        if previous_split != metadata["split"]:
            errors.append(f"domain split leakage: {group}")

        if metadata["kind"] == "clarification":
            spec = TaskSpec.model_validate(_assistant_payload(record))
            blockers = [item for item in spec.missing_information if item.blocks_generation]
            if not spec.clarification_required or not blockers or spec.clarification is None:
                errors.append(f"invalid clarification target: {record_id}")
            continue

        final_graph = _assistant_payload(record)
        graph = FlowGraph.model_validate(final_graph)
        valid, issues = validate_flow(graph)
        if not valid:
            errors.append(f"final graph invalid: {record_id}: {' | '.join(issues)}")
        dry_run = dry_run_workflow(final_graph)
        if not dry_run.success:
            errors.append(f"dry-run failed: {record_id}: {' | '.join(dry_run.issues)}")
        graph_count += 1
        dry_run_count += int(dry_run.success)

        if metadata["kind"] == "generation":
            spec = TaskSpec.model_validate(user_payload["task_spec"])
            coverage = task_coverage_issues(spec, final_graph)
            if coverage:
                errors.append(f"semantic coverage failed: {record_id}: {coverage[0].message}")
        else:
            broken = FlowGraph.model_validate(user_payload["generated_graph"])
            initial_valid, initial_errors = validate_flow(broken)
            if initial_valid or not initial_errors or not user_payload["validation_issues"]:
                errors.append(f"repair source is not invalid: {record_id}")
            else:
                repair_invalid_count += 1

    serialized = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    sensitive_patterns = {
        "OpenAI-style API key": r"\bsk-[A-Za-z0-9_-]{12,}\b",
        "Bearer token": r"\bBearer\s+[A-Za-z0-9._~-]{12,}",
        "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "literal email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    }
    for label, pattern in sensitive_patterns.items():
        if re.search(pattern, serialized, re.IGNORECASE):
            errors.append(f"sensitive value detected: {label}")

    counts = Counter(f"{record['metadata']['kind']}_{record['metadata']['split']}" for record in records)
    expected = {
        "generation_train": 240,
        "generation_validation": 30,
        "generation_test": 30,
        "repair_train": 120,
        "repair_validation": 15,
        "repair_test": 15,
        "clarification_train": 40,
        "clarification_validation": 5,
        "clarification_test": 5,
    }
    for key, value in expected.items():
        if counts[key] != value:
            errors.append(f"count mismatch {key}: expected {value}, got {counts[key]}")

    report = {
        "passed": not errors,
        "record_count": len(records),
        "validated_final_graphs": graph_count,
        "successful_dry_runs": dry_run_count,
        "invalid_repair_sources": repair_invalid_count,
        "unique_ids": len(seen_ids),
        "unique_prompts": len(all_prompts),
        "evaluation_prompt_overlap": len(all_prompts & evaluation_prompts),
        "counts": dict(sorted(counts.items())),
        "errors": errors,
    }
    if errors:
        raise ValueError("Synthetic dataset validation failed:\n- " + "\n- ".join(errors[:30]))
    return report


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    content = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate_dataset(output_dir: Path) -> dict[str, Any]:
    generation = build_generation_records()
    repair = build_repair_records(generation)
    clarification = build_clarification_records()
    records = generation + repair + clarification
    report = validate_records(records)

    output_dir.mkdir(parents=True, exist_ok=True)
    file_entries: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        for split in SPLITS:
            selected = [
                record for record in records
                if record["metadata"]["kind"] == kind and record["metadata"]["split"] == split
            ]
            path = output_dir / f"{kind}-{split}.jsonl"
            file_entries[path.name] = {"count": len(selected), "sha256": _write_jsonl(path, selected)}

    report_path = output_dir / "validation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "dataset_version": DATASET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": "backend/training/generate_synthetic.py",
        "generation_method": "deterministic templates; no external LLM or API calls",
        "split_policy": "domain-grouped 80/10/10 (16/2/2 domains)",
        "counts": {"total": len(records), "generation": len(generation), "repair": len(repair), "clarification": len(clarification)},
        "files": file_entries,
        "validation_report": report_path.name,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="외부 LLM 호출 없는 workflow LoRA 합성 데이터 생성")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "datasets" / DATASET_VERSION,
    )
    args = parser.parse_args()
    print(json.dumps(generate_dataset(args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
