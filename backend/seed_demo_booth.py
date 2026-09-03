# -*- coding: utf-8 -*-
"""seed_demo_booth.py — 부스 시연 콘텐츠 시딩 (시연 종합보고서 §4).

시연 계정에 "한국 서비스 강한 연동"을 보여주는 워크플로우 5개 + 앱 빌더 앱 2개 +
전용 문서 포맷 1개를 심는다. 코드가 아니라 **데이터**라서 시연 브랜치를 따지 않는다 —
이 스크립트는 멱등(제목 기준 upsert)이라 몇 번을 돌려도 안전하고, 시연 후에도 무해하다.

사용:
    venv\\Scripts\\python seed_demo_booth.py --email booth@example.com
    venv\\Scripts\\python seed_demo_booth.py --user-id 3

시딩 전 모든 워크플로우를 dry_run 으로 검증한다 — 하나라도 실패하면 아무것도 쓰지 않는다.

콘텐츠 목록:
  포맷   demo-news-briefing        뉴스 브리핑 (formatNode 가 참조하는 사용자 포맷)
  WF1    키워드 → 네이버 뉴스 → 한글(HWPX) 브리핑     naverSearchNode + formatNode
  WF2    주소 정제 · 우편번호 찾기                    jusoNode (행정안전부)
  WF3    아침 IT 정책 브리핑 → 카카오톡               dataGoKrNode(과기정통부) + kakaoNode
  WF4    브랜드 모니터링 → 이메일 경보                naverSearchTriggerNode
  WF5    휴가 신청 전자결재 → HWPX 발급 → 메일        formatNode(leave-request) + humanApproval
  APP1   주소 접수 데스크        (WF2 연결 — 층 1 QR 체험용)
  APP2   뉴스 브리핑 생성기      (WF1 연결 — 층 1 QR 체험용)

주의: WF3 의 카카오톡 발송은 시연 계정에 카카오 연동(API 센터)이 있어야 실제로 나간다.
공공데이터·도로명주소 승인키도 시연 계정 API 센터(또는 DEMO_SHARED_CREDENTIALS_*)에 필요하다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

DEMO_FORMAT_ID = "demo-news-briefing"
TITLE_PREFIX = "[시연] "


# ── 그래프 조립 헬퍼 (official_templates/_lib 과 같은 문법, id 는 안정적으로 지정) ──

def N(node_id: str, node_type: str, **data):
    return {"id": node_id, "type": node_type, "data": data, "position": None}


def chain(*nodes):
    edges = [{"id": f"e-{a['id']}-{b['id']}", "source": a["id"], "target": b["id"],
              "sourceHandle": None, "targetHandle": None}
             for a, b in zip(nodes, nodes[1:])]
    return list(nodes), edges


def link(a, b, source_handle=None):
    return {"id": f"e-{a['id']}-{b['id']}-{source_handle or ''}", "source": a["id"],
            "target": b["id"], "sourceHandle": source_handle, "targetHandle": None}


# ── 전용 문서 포맷: 뉴스 브리핑 ──────────────────────────────────────────

NEWS_BRIEFING_SPEC = {
    "version": 1,
    "name": "뉴스 브리핑",
    "description": "네이버 뉴스 검색 결과를 정리한 한 장짜리 브리핑 문서",
    "layout": "document",
    "output": {"default": "hwpx", "allowed": ["hwpx", "docx", "pdf"]},
    "fields": [
        {"name": "reportTitle", "label": "브리핑 제목", "kind": "text", "required": True,
         "example": "생성형 AI 뉴스 브리핑"},
        {"name": "reportDate", "label": "작성일", "kind": "text", "required": True,
         "example": "2026년 9월 10일"},
        {"name": "keyword", "label": "검색 키워드", "kind": "text", "required": True,
         "example": "생성형 AI"},
        {"name": "summary", "label": "오늘의 흐름", "kind": "multiline", "required": True,
         "example": "관련 보도가 이어지며 업계의 관심이 집중되고 있습니다."},
        {"name": "articles", "label": "주요 기사", "kind": "rows",
         "columns": ["제목", "매체", "한 줄 요약"], "required": True},
        {"name": "insight", "label": "시사점", "kind": "multiline", "required": True,
         "example": "후속 동향을 주간 단위로 확인할 필요가 있습니다."},
    ],
    "blocks": [
        {"type": "heading", "level": 1, "text": "{{reportTitle}}"},
        {"type": "table", "columns": ["항목", "내용"],
         "rows": [["검색 키워드", "{{keyword}}"], ["작성일", "{{reportDate}}"]]},
        {"type": "heading", "level": 2, "text": "1. 오늘의 흐름"},
        {"type": "paragraph", "text": "{{summary}}"},
        {"type": "heading", "level": 2, "text": "2. 주요 기사"},
        {"type": "table", "fromField": "articles"},
        {"type": "heading", "level": 2, "text": "3. 시사점"},
        {"type": "paragraph", "text": "{{insight}}"},
        {"type": "paragraph", "text": "본 브리핑은 네이버 뉴스 검색 결과를 바탕으로 자동 생성되었습니다."},
    ],
}

NEWS_BRIEFING_SCHEMA = json.dumps({
    "title": "NewsBriefing",
    "type": "object",
    "properties": {
        "reportTitle": {"type": "string", "description": "브리핑 제목 (예: 생성형 AI 뉴스 브리핑)"},
        "reportDate": {"type": "string", "description": "오늘 날짜 (예: 2026년 9월 10일)"},
        "keyword": {"type": "string", "description": "검색 키워드 원문"},
        "summary": {"type": "string", "description": "오늘 흐름 요약 3~4문장"},
        "articles": {"type": "array", "description": "주요 기사 3~5건, 각 행은 [제목, 매체, 한 줄 요약]",
                     "items": {"type": "array", "items": {"type": "string"}}},
        "insight": {"type": "string", "description": "실무 시사점 2~3문장"},
    },
    "required": ["reportTitle", "reportDate", "keyword", "summary", "articles", "insight"],
}, ensure_ascii=False)

LEAVE_REQUEST_SCHEMA = json.dumps({
    "title": "LeaveRequest",
    "type": "object",
    "properties": {
        "department": {"type": "string", "description": "부서"},
        "position": {"type": "string", "description": "직위"},
        "applicantName": {"type": "string", "description": "신청자 성명"},
        "leaveType": {"type": "string", "description": "휴가 구분 (연차/반차/병가/경조 등)"},
        "startDate": {"type": "string", "description": "시작일 (YYYY-MM-DD)"},
        "endDate": {"type": "string", "description": "종료일 (YYYY-MM-DD)"},
        "days": {"type": "string", "description": "일수 (숫자만)"},
        "emergencyContact": {"type": "string", "description": "비상 연락처, 없으면 빈 문자열"},
        "handoverTo": {"type": "string", "description": "업무 인수자, 없으면 빈 문자열"},
        "reason": {"type": "string", "description": "휴가 사유 한두 문장"},
        "appliedAt": {"type": "string", "description": "오늘 날짜 (예: 2026년 9월 3일)"},
    },
    "required": ["department", "position", "applicantName", "leaveType",
                 "startDate", "endDate", "days", "reason", "appliedAt"],
}, ensure_ascii=False)


# ── 워크플로우 5종 ───────────────────────────────────────────────────────

def build_workflows(owner_email: str):
    """제목 → (설명, nodes, edges). 노드 id 는 앱 payload 키로도 쓰이므로 바꾸지 말 것."""
    flows = {}

    # WF1 — 키워드 정제 → 네이버 검색 → (결과 유무 분기) → 구조화 → 한글(HWPX) 브리핑
    n_start = N("start1", "startNode")
    n_in = N("in_keyword", "dynamicInputNode", inputLabel="검색 키워드", testValue="생성형 AI")
    n_refine = N("refine_llm", "llmNode", model="gpt-4o-mini",
                 systemPrompt=("입력은 사용자가 적은 검색 요청이다. 조사·군더더기를 걷어내고 "
                               "네이버 검색에 넣을 핵심 검색어 하나로 정제한다. 검색어만 한 줄로 출력한다."))
    n_news = N("news_search", "naverSearchNode", mode="blog", query="", display=10, sort="date")
    n_cond = N("cond_hits", "conditionNode",
               rules=[{"id": "empty", "operator": "Contains", "value": '"items": []'}])
    n_empty = N("no_hits_msg", "valueNode",
                value="검색 결과가 없습니다 — 키워드를 조금 더 일반적인 표현으로 바꿔 다시 시도해 주세요.")
    n_brief = N("brief_llm", "llmNode", model="gpt-4o-mini",
                systemPrompt=("입력은 네이버 검색 결과다. 이것만 근거로 오늘의 브리핑을 만든다. "
                              "articles 는 실제 글에서 3~5건을 골라 [제목, 매체, 한 줄 요약] 로 적는다. "
                              "글에 없는 내용을 지어내지 않는다. reportTitle 은 '<키워드> 브리핑' 형태로, "
                              "reportDate 는 오늘 날짜를 한국어로 적는다."),
                useStructuredOutput=True, jsonSchema=NEWS_BRIEFING_SCHEMA)
    n_doc = N("brief_doc", "formatNode", formatId=DEMO_FORMAT_ID, output="hwpx")
    n_merge = N("merge1", "mergeNode")
    n_out = N("out1", "outputNode")
    nodes = [n_start, n_in, n_refine, n_news, n_cond, n_empty, n_brief, n_doc, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_refine), link(n_refine, n_news), link(n_news, n_cond),
             link(n_cond, n_empty, source_handle="empty"),
             link(n_cond, n_brief, source_handle="else"),
             link(n_brief, n_doc), link(n_doc, n_merge), link(n_empty, n_merge), link(n_merge, n_out)]
    flows["키워드 → 네이버 브리핑 문서"] = (
        "키워드를 AI가 검색어로 정제해 네이버 최신 글을 모으고, 결과가 있으면 요약해 한/글(HWPX) 브리핑 "
        "문서를 만듭니다. 결과가 없으면 분기해서 안내 문구를 돌려줍니다 — 검색 → 분기 → 문서화의 완결 흐름.",
        nodes, edges)

    # WF2 — 주소 정제 · 우편번호 (검색 → 결과 유무 분기 → 정본 카드 / 재시도 안내)
    n_start = N("start2", "startNode")
    n_in = N("in_addr", "dynamicInputNode", inputLabel="정리할 주소",
             testValue="부산 금정구 부산대학로63번길 2")
    n_juso = N("juso_search", "jusoNode", keyword="", count=3)
    n_cond = N("cond_found", "conditionNode",
               rules=[{"id": "none", "operator": "Contains", "value": '"total": 0'}])
    n_none = N("not_found_msg", "valueNode",
               value="주소를 찾지 못했습니다 — 동 이름이나 건물번호까지 포함해 다시 적어 주세요. (예: 부산대학로63번길 2)")
    n_pick = N("pick_llm", "llmNode", model="gpt-4o-mini",
               systemPrompt=("입력은 행정안전부 도로명주소 검색 결과다. 가장 그럴듯한 것 하나를 고른다. "
                             "1줄: '도로명주소 (우편번호)', 2줄: '지번: <지번주소>', 3줄: 후보가 더 있으면 "
                             "'다른 후보 N건이 있습니다'. 검색 결과에 없는 내용은 쓰지 않는다."))
    n_merge = N("merge2", "mergeNode")
    n_out = N("out2", "outputNode")
    nodes = [n_start, n_in, n_juso, n_cond, n_none, n_pick, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_juso), link(n_juso, n_cond),
             link(n_cond, n_none, source_handle="none"),
             link(n_cond, n_pick, source_handle="else"),
             link(n_pick, n_merge), link(n_none, n_merge), link(n_merge, n_out)]
    flows["주소 정제 · 우편번호 찾기"] = (
        "대충 적은 주소를 행정안전부 정본 도로명주소·우편번호·지번까지 3초 만에 정리합니다. "
        "못 찾으면 분기해서 어떻게 다시 적을지 안내합니다.", nodes, edges)

    # WF3 — 아침 IT 정책 브리핑 (공공데이터 → 새 자료 유무 분기 → 카카오톡 + 이메일 보관)
    n_sched = N("sched_am8", "scheduleNode", cronExpression="0 8 * * 1-5")
    n_gov = N("gov_press", "dataGoKrNode", dataset="msit_press_release", operation="list", rows=8)
    n_cond = N("cond_press", "conditionNode",
               rules=[{"id": "quiet", "operator": "Contains", "value": '"items": []'}])
    n_quiet = N("quiet_msg", "valueNode", value="오늘은 새 보도자료가 없습니다 — 알림을 보내지 않습니다.")
    n_sum = N("sum_llm", "llmNode", model="gpt-4o-mini",
              systemPrompt=("입력은 과학기술정보통신부 보도자료 목록이다. 오늘 알아야 할 3건을 골라 "
                            "'· 제목 — 요점 한 줄' 형식으로 정리한다. 첫 줄은 '📋 오늘의 IT 정책 브리핑' 으로 "
                            "시작하고, 마지막 줄에 '(공공데이터포털 · 과기정통부)' 출처를 적는다. "
                            "목록에 없는 내용은 쓰지 않는다."))
    n_kakao = N("kakao_send", "kakaoNode", template="text")
    n_archive = N("archive_mail", "emailNode", toEmail=owner_email, subject="[보관] 오늘의 IT 정책 브리핑")
    n_merge = N("merge3", "mergeNode")
    n_out = N("out3", "outputNode")
    nodes = [n_sched, n_gov, n_cond, n_quiet, n_sum, n_kakao, n_archive, n_merge, n_out]
    edges = [link(n_sched, n_gov), link(n_gov, n_cond),
             link(n_cond, n_quiet, source_handle="quiet"),
             link(n_cond, n_sum, source_handle="else"),
             link(n_sum, n_kakao), link(n_kakao, n_archive),
             link(n_archive, n_merge), link(n_quiet, n_merge), link(n_merge, n_out)]
    flows["아침 IT 정책 브리핑 → 카카오톡"] = (
        "평일 아침 8시, 공공데이터포털의 과기정통부 보도자료를 확인해 새 자료가 있을 때만 핵심 3건을 "
        "카카오톡으로 보내고 이메일로도 보관합니다. 새 자료가 없는 날은 조용히 넘어갑니다.", nodes, edges)

    # WF4 — 브랜드 모니터링 (새 글 트리거 → 논조 분석 → 부정이면 경보, 평시엔 일지)
    n_watch = N("watch_naver", "naverSearchTriggerNode", mode="blog", query="업무 자동화", maxResults=5)
    n_judge = N("judge_llm", "llmNode", model="gpt-4o-mini",
                systemPrompt=("입력은 우리 키워드가 언급된 네이버 새 글 목록이다. 글마다 '제목 — 논조(긍정/중립/부정) "
                              "— 한 줄 요약' 으로 정리하고, 부정 논조가 하나라도 있으면 맨 첫 줄에 정확히 "
                              "'⚠️ 부정 언급 감지' 라고 쓴다. 글에 없는 내용을 추측하지 않는다."))
    n_cond = N("cond_tone", "conditionNode",
               rules=[{"id": "negative", "operator": "Contains", "value": "부정 언급 감지"}])
    n_alert = N("alert_mail", "emailNode", toEmail=owner_email, subject="[경보] 부정 언급 감지 — 즉시 확인")
    n_log = N("digest_msg", "valueNode",
              value="새 글이 있었지만 부정 언급은 없습니다 — 실행 기록으로만 남깁니다.")
    n_merge = N("merge4", "mergeNode")
    n_out = N("out4", "outputNode")
    nodes = [n_watch, n_judge, n_cond, n_alert, n_log, n_merge, n_out]
    edges = [link(n_watch, n_judge), link(n_judge, n_cond),
             link(n_cond, n_alert, source_handle="negative"),
             link(n_cond, n_log, source_handle="else"),
             link(n_alert, n_merge), link(n_log, n_merge), link(n_merge, n_out)]
    flows["브랜드 모니터링 → 이메일 경보"] = (
        "네이버에 우리 키워드가 담긴 새 글이 올라오면 논조를 분석하고, 부정 언급이 있을 때만 경보 메일을 "
        "보냅니다. 평시에는 실행 기록만 남습니다 — 감시 → 판정 → 분기 알림의 정석 구조.", nodes, edges)

    # WF5 — 휴가 신청 전자결재 (접수 검토 → 반려 분기 → 정형화 → HWPX → 승인 → 발급 메일)
    n_start = N("start5", "startNode")
    n_in = N("in_leave", "dynamicInputNode", inputLabel="휴가 신청 내용",
             testValue=("9월 10일부터 11일까지 연차 2일 신청합니다. 사유는 개인 사정입니다. "
                        "신청자 김워크, 운영1팀 대리, 비상연락처 010-0000-0000, 업무 인수자는 이플로입니다."))
    n_review = N("review_llm", "llmNode", model="gpt-4o-mini",
                 systemPrompt=("입력은 자연어 휴가 신청이다. 신청자 이름·휴가 기간·사유 세 가지가 모두 있는지 "
                               "확인한다. 하나라도 없으면 첫 줄에 정확히 '보완 필요' 라고 쓰고 무엇이 빠졌는지 "
                               "한 줄로 적는다. 모두 있으면 첫 줄에 '접수' 라고 쓰고, 다음 줄부터 신청 원문을 "
                               "그대로 다시 적는다(뒷단계가 원문을 쓴다)."))
    n_cond = N("cond_intake", "conditionNode",
               rules=[{"id": "needfix", "operator": "Contains", "value": "보완 필요"}])
    n_reject = N("reject_msg", "valueNode",
                 value=("신청 내용에 누락이 있어 접수되지 않았습니다 — 신청자 이름, 휴가 기간(시작~종료), "
                        "사유를 포함해 다시 신청해 주세요."))
    n_fill = N("fill_llm", "llmNode", model="gpt-4o-mini",
               systemPrompt=("입력은 검토를 통과한 휴가 신청이다. 휴가신청서의 빈칸을 채운다. 날짜는 YYYY-MM-DD 로, "
                             "days 는 숫자만 적는다. appliedAt 은 오늘 날짜를 한국어(예: 2026년 9월 3일)로 적는다. "
                             "입력에 없는 값은 지어내지 말고 빈 문자열로 둔다(필수가 아닌 칸)."),
               useStructuredOutput=True, jsonSchema=LEAVE_REQUEST_SCHEMA)
    n_doc = N("leave_doc", "formatNode", formatId="leave-request", output="hwpx")
    n_approve = N("approve", "humanApprovalNode",
                  message="휴가 신청 결재 요청입니다 — 생성된 신청서(HWPX)를 확인하고 승인해 주세요.",
                  notifyEmail=True)
    n_mail = N("issue_mail", "emailNode", toEmail=owner_email, subject="휴가 신청서 발급 완료")
    n_merge = N("merge5", "mergeNode")
    n_out = N("out5", "outputNode")
    nodes = [n_start, n_in, n_review, n_cond, n_reject, n_fill, n_doc, n_approve, n_mail, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_review), link(n_review, n_cond),
             link(n_cond, n_reject, source_handle="needfix"),
             link(n_cond, n_fill, source_handle="else"),
             link(n_fill, n_doc), link(n_doc, n_approve), link(n_approve, n_mail),
             link(n_mail, n_merge), link(n_reject, n_merge), link(n_merge, n_out)]
    flows["휴가 신청 전자결재 → 신청서 발급"] = (
        "말로 적은 휴가 신청을 AI가 접수 검토(누락 시 반려)하고, 통과하면 정식 휴가신청서(HWPX)를 만들어 "
        "결재(승인 대기함)에 올립니다. 승인되면 신청서가 이메일로 발급됩니다 — 접수 → 검토 → 분기 → "
        "문서화 → 전자결재 → 발급의 완결 흐름.", nodes, edges)

    return flows


# ── 앱 2종 (앱 빌더) ─────────────────────────────────────────────────────

def _text(cid, text, x, y, w, h=36, **style):
    return {"id": cid, "type": "text",
            "props": {"text": text, "position": {"x": x, "y": y},
                      "style": {"width": f"{w}px", "height": f"{h}px", **style}}}


def _input(cid, label, placeholder, input_key, x, y, w=420):
    return {"id": cid, "type": "input",
            "props": {"label": label, "placeholder": placeholder, "inputKey": input_key,
                      "position": {"x": x, "y": y}, "style": {"width": f"{w}px", "height": "68px"}}}


def _button(cid, text, x, y, w=180):
    return {"id": cid, "type": "button",
            "props": {"text": text, "position": {"x": x, "y": y},
                      "style": {"width": f"{w}px", "height": "48px"}}}


def _result(cid, kind, placeholder, x, y, w=560, h=200):
    return {"id": cid, "type": kind,
            "props": {"label": "결과", "placeholder": placeholder, "readOnly": True,
                      "position": {"x": x, "y": y}, "style": {"width": f"{w}px", "height": f"{h}px"}}}


def _blueprint(button_id, project_id, fields, result_id):
    """버튼 클릭 → 워크플로우 실행 → 결과 컴포넌트 표시 — UIEngine 의 표준 3노드 체인."""
    nodes = [
        {"id": "t1", "type": "triggerNode", "data": {"componentId": button_id, "eventType": "onClick"},
         "position": {"x": 40, "y": 80}},
        {"id": "s1", "type": "submitNode",
         "data": {"projectId": str(project_id),
                  "fields": [{"name": name, "componentId": cid} for name, cid in fields]},
         "position": {"x": 300, "y": 80}},
        {"id": "o1", "type": "outputNode", "data": {"componentId": result_id, "format": "text"},
         "position": {"x": 560, "y": 80}},
    ]
    edges = [
        {"id": "be1", "source": "t1", "target": "s1", "sourceHandle": "triggerOut", "targetHandle": "triggerIn"},
        {"id": "be2", "source": "s1", "target": "o1", "sourceHandle": "triggerOut", "targetHandle": "triggerIn"},
    ]
    return {"nodes": nodes, "edges": edges}


def build_apps(project_ids: dict):
    """제목 → (ui_graph_data, logic_graph, workflow_mappings)."""
    apps = {}

    # APP1 — 주소 접수 데스크 (WF2)
    juso_pid = project_ids["주소 정제 · 우편번호 찾기"]
    components = [
        _text("title", "📮 주소 접수 데스크", 60, 44, 560, 44, fontSize="30px", fontWeight="700"),
        _text("desc", "대충 적어도 됩니다 — 행정안전부 정본 주소와 우편번호로 정리해 드려요.",
              60, 96, 720, 30, fontSize="15px", color="#64748b"),
        _input("addr_input", "주소", "예: 부산 금정구 부산대학로63번길 2", "in_addr", 60, 150),
        _button("submit_btn", "정본 주소 찾기", 500, 172),
        _result("result_box", "textarea", "정리된 주소가 여기에 표시됩니다.", 60, 250),
    ]
    ui = {"components": components, "canvas": {"width": 800, "height": 520, "autoHeight": True},
          "rootStyle": {"backgroundColor": "#f8fafc"}, "globalCss": "", "globalJs": "",
          "description": "주소 한 줄을 정본 도로명주소·우편번호로 정리하는 접수 데스크"}
    logic = _blueprint("submit_btn", juso_pid, [("in_addr", "addr_input")], "result_box")
    apps["주소 접수 데스크"] = (ui, logic, {"submit_btn": {"projectId": str(juso_pid)}})

    # APP2 — 브리핑 생성기 (WF1)
    news_pid = project_ids["키워드 → 네이버 브리핑 문서"]
    components = [
        _text("title", "📰 브리핑 문서 생성기", 60, 44, 560, 44, fontSize="30px", fontWeight="700"),
        _text("desc", "키워드 하나면 네이버 최신 글을 정리한 한/글(HWPX) 브리핑 문서가 만들어집니다.",
              60, 96, 760, 30, fontSize="15px", color="#64748b"),
        _input("kw_input", "검색 키워드", "예: 생성형 AI", "in_keyword", 60, 150),
        _button("make_btn", "브리핑 만들기", 500, 172),
        _result("brief_box", "textarea", "생성된 브리핑 파일 경로가 여기에 표시됩니다. (약 20~30초)",
                60, 250, 640, 180),
        _text("hint", "생성이 끝나면 위 경로의 .hwpx 파일이 내 파일함에 저장됩니다.",
              60, 448, 640, 26, fontSize="13px", color="#94a3b8"),
    ]
    ui = {"components": components, "canvas": {"width": 800, "height": 540, "autoHeight": True},
          "rootStyle": {"backgroundColor": "#f8fafc"}, "globalCss": "", "globalJs": "",
          "description": "네이버 검색 → AI 요약 → 한/글 브리핑 문서 생성기"}
    logic = _blueprint("make_btn", news_pid, [("in_keyword", "kw_input")], "brief_box")
    apps["브리핑 문서 생성기"] = (ui, logic, {"make_btn": {"projectId": str(news_pid)}})

    return apps


# ── 시딩 본체 ────────────────────────────────────────────────────────────

def seed(db, user) -> dict:
    """검증 → upsert. 반환: {'formats': [...], 'projects': {제목: id}, 'apps': {제목: id}}."""
    import models
    from dry_run import dry_run_workflow

    flows = build_workflows(owner_email=user.email or "booth@example.com")

    # 1) 전량 사전 검증 — 하나라도 실패하면 아무것도 쓰지 않는다.
    failures = []
    for title, (_desc, nodes, edges) in flows.items():
        result = dry_run_workflow({"nodes": nodes, "edges": edges})
        if not (result.success and result.compile_passed):
            failures.append((title, [str(i) for i in (result.issues or [])]))
    if failures:
        raise SystemExit(f"dry_run 검증 실패 — 시딩 중단: {failures}")

    # 2) 전용 포맷 (formatNode 가 참조하므로 워크플로우보다 먼저)
    from documents.format_spec import validate_format_spec
    spec = validate_format_spec({**NEWS_BRIEFING_SPEC, "id": DEMO_FORMAT_ID})
    fmt = db.query(models.DocumentFormat).filter(models.DocumentFormat.id == DEMO_FORMAT_ID).first()
    if fmt is None:
        fmt = models.DocumentFormat(id=DEMO_FORMAT_ID, owner_user_id=user.id,
                                    name=spec["name"], layout=spec["layout"], spec=spec)
        db.add(fmt)
    else:
        fmt.owner_user_id, fmt.name, fmt.layout, fmt.spec = user.id, spec["name"], spec["layout"], spec

    # 3) 워크플로우 upsert (소유자+제목 기준)
    project_ids = {}
    for title, (desc, nodes, edges) in flows.items():
        full_title = TITLE_PREFIX + title
        graph = {"nodes": nodes, "edges": edges}
        row = (db.query(models.Project)
               .filter(models.Project.user_id == user.id, models.Project.title == full_title).first())
        if row is None:
            row = models.Project(user_id=user.id, title=full_title, description=desc, graph_data=graph)
            db.add(row)
            db.flush()
        else:
            row.description, row.graph_data = desc, graph
        if not row.share_token:            # 층 1 QR 체험은 share 링크가 필요하다
            row.share_token = str(uuid.uuid4())
        project_ids[title] = row.id

    # 4) 앱 upsert (소유자+제목 기준)
    app_ids = {}
    for title, (ui, logic, mappings) in build_apps(project_ids).items():
        full_title = TITLE_PREFIX + title
        combined = {"ui": ui, "logic": logic}
        row = (db.query(models.CustomApp)
               .filter(models.CustomApp.owner_id == user.id, models.CustomApp.title == full_title).first())
        if row is None:
            row = models.CustomApp(id=str(uuid.uuid4()), title=full_title,
                                   ui_graph_data=combined, workflow_mappings=mappings, owner_id=user.id)
            db.add(row)
        else:
            row.ui_graph_data, row.workflow_mappings = combined, mappings
        app_ids[title] = row.id

    db.commit()
    return {"formats": [DEMO_FORMAT_ID], "projects": project_ids, "apps": app_ids}


def main():
    parser = argparse.ArgumentParser(description="부스 시연 콘텐츠 시딩")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="시연 계정 이메일")
    group.add_argument("--user-id", type=int, help="시연 계정 user id")
    args = parser.parse_args()

    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        query = db.query(models.User)
        user = (query.filter(models.User.email == args.email).first() if args.email
                else query.filter(models.User.id == args.user_id).first())
        if user is None:
            raise SystemExit("사용자를 찾을 수 없습니다 — 먼저 그 계정으로 한 번 로그인해 주세요.")
        result = seed(db, user)
        print(f"시딩 완료 (user={user.id} {user.email})")
        print(f"  포맷: {result['formats']}")
        for title, pid in result["projects"].items():
            print(f"  워크플로우 #{pid}: {TITLE_PREFIX}{title}")
        for title, aid in result["apps"].items():
            print(f"  앱 {aid}: {TITLE_PREFIX}{title}")
        print("남은 일: 시연 계정 API 센터에 juso·data_go_kr 승인키(+카카오 연동), 앱은 앱 빌더에서 '배포'로 링크 발급.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
