# -*- coding: utf-8 -*-
"""F묶음 — 영업·고객·인사 업무."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []
NOTION = "{{API_CENTER:notion}}"


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def approve_send(trigger, prompt, sender, title, desc, cat, tags):
    a = llm(prompt)
    h = N("humanApprovalNode")
    n, e = chain(trigger, a, h, sender, out())
    add(title, desc, cat, tags, n, e)


def t_lead_triage():
    tr = N("gmailTriggerNode", query="subject:문의", maxResults=20)
    a = llm("입력은 고객 문의 메일이다. '견적 요청 / 기술 문의 / 단순 안내 / 스팸' 중 하나로 분류하고 "
            "회신 우선순위를 상·중·하로 매긴다. 근거를 한 줄로 적는다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="문의!A:D")
    n, e = chain(tr, a, sh, out())
    add("고객 문의 자동 분류·기록", "문의 메일을 종류와 우선순위로 나눠 시트에 기록합니다.",
        "automation", ["gmail", "고객", "분류"], n, e)


def t_quote_draft():
    s, i = start(), ask("견적 요청 내용", "제품 A 100개, 납기 2주")
    a = llm("입력을 견적서 초안으로 정리한다. 품목·수량·납기·비고를 표로 쓰고, "
            "금액은 '[담당자 입력]' 으로 남긴다 — 지어내지 않는다.")
    h = N("hwpxDocumentNode", mode="create", output_path="견적서.hwpx")
    n, e = chain(s, i, a, h, out())
    add("견적 요청 → 한글 견적서 초안", "요청 내용을 견적서 초안으로 만들어 줍니다. 금액은 비워 둡니다.",
        "document", ["견적", "한글", "영업"], n, e)


def t_customer_followup():
    s = sched("0 10 * * 2")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="고객!A:F")
    a = llm("입력은 고객 목록이다. 마지막 연락이 30일 넘은 고객만 골라 "
            "이름과 마지막 연락일, 제안할 다음 행동을 표로 정리한다.")
    n, e = chain(s, sh, a, out())
    add("연락 끊긴 고객 찾기", "한동안 연락이 없던 고객을 추려 다음 행동을 제안합니다.",
        "data", ["고객", "시트", "영업"], n, e)


def t_contract_review():
    s = start()
    t = N("templateAnalyzerNode", template_path="uploads/계약서.hwpx")
    a = llm("입력은 계약 서식 분석 결과다. 채워야 할 항목을 표로 정리하고, "
            "빠지면 법적으로 문제가 될 만한 항목에는 '중요' 표시를 붙인다.")
    n, e = chain(s, t, a, out())
    add("계약서 필수 항목 점검", "계약 서식에서 반드시 채워야 할 항목을 짚어 줍니다.",
        "document", ["계약", "서식", "점검"], n, e)


def t_resume_screen():
    tr = N("gmailTriggerNode", query="subject:지원 has:attachment", maxResults=20)
    a = llm("입력은 지원 메일이다. 이름·경력연수·주요 기술을 표로 정리한다. "
            "메일에서 확인되지 않는 항목은 '확인 불가'로 적고 추측하지 않는다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="지원자!A:D")
    n, e = chain(tr, a, sh, out())
    add("지원 메일 → 지원자 대장", "지원 메일에서 기본 정보를 뽑아 대장에 기록합니다.",
        "data", ["채용", "gmail", "시트"], n, e)


def t_interview_schedule():
    s, i = start(), ask("면접 안내 요청", "김철수 지원자, 다음 주 수요일 오후 2시")
    a = llm("입력으로 면접 안내 메일 본문을 쓴다. 일시·장소·준비물을 항목으로 나누고, "
            "빠진 정보는 '[확인 필요]' 로 표시한다.")
    h = N("humanApprovalNode")
    g = N("gmailNode", mode="send_email", to="", subject="면접 안내", body="")
    n, e = chain(s, i, a, h, g, out())
    add("면접 안내 메일 (승인 후 발송)", "면접 안내 메일을 쓰고 사람이 확인한 뒤 보냅니다.",
        "automation", ["채용", "gmail", "승인"], n, e)


def t_onboarding_checklist():
    s, i = start(), ask("입사자 정보", "김철수, 개발팀, 9월 1일 입사")
    a = llm("입력으로 온보딩 체크리스트를 만든다. 입사 전·첫날·첫 주로 나누고 "
            "각 항목에 담당 부서를 적는다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, i, a, nt, out())
    add("입사자 온보딩 체크리스트", "입사자 정보로 온보딩 할 일 목록을 만들어 노션에 올립니다.",
        "document", ["인사", "노션", "온보딩"], n, e)


def t_expense_check():
    s = start()
    d = N("databaseNode", query="SELECT * FROM expenses WHERE status = 'pending'")
    a = llm("입력은 결재 대기 지출이다. 금액이 평소보다 크거나 항목이 모호한 건을 골라 "
            "확인이 필요한 이유와 함께 정리한다. 특이사항이 없으면 '이상 없음'만 출력한다.")
    sl = N("slackNode", channel="#finance", text="")
    n, e = chain(s, d, a, sl, out())
    add("지출 결재 이상 건 점검", "결재 대기 중인 지출에서 확인이 필요한 건을 골라 줍니다.",
        "notification", ["재무", "데이터베이스", "점검"], n, e)


def t_survey_summary():
    s = sched("0 9 * * 1")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="설문!A:Z")
    a = llm("입력은 설문 응답이다. 반복되는 의견 5가지를 뽑고 각각 몇 명이 비슷한 말을 했는지 적는다. "
            "숫자를 확신할 수 없으면 '다수' 로 적는다.")
    h = N("hwpxDocumentNode", mode="create", output_path="설문결과.hwpx")
    n, e = chain(s, sh, a, h, out())
    add("설문 응답 → 한글 결과 보고서", "설문 응답을 정리해 한글 보고서로 만듭니다.",
        "document", ["설문", "한글", "보고서"], n, e)


def t_vendor_address_check():
    s = start()
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="거래처!A:D")
    d = N("distributorNode")
    j = N("jusoNode", keyword="", count=1)
    a = llm("입력은 주소 검색 결과다. 도로명주소와 우편번호만 한 줄로 출력한다. "
            "찾지 못했으면 '확인 필요'만 출력한다.")
    m = N("mergeNode")
    o = out()
    nodes = [s, sh, d, j, a, m, o]
    edges = [link(s, sh), link(sh, d), link(d, j), link(j, a), link(a, m),
             link(d, o, source_handle="done")]
    add("거래처 주소 일괄 검증", "거래처 시트의 주소를 정본 주소와 대조해 정리합니다.",
        "data", ["주소", "거래처", "일괄처리"], nodes, edges)


def t_complaint_route():
    w = N("webhookNode")
    a = llm("입력은 고객 불만 접수다. '환불 / 배송 / 품질 / 기타' 로 분류하고 긴급도를 상·중·하로 매긴다. "
            "긴급도가 '상' 이면 이유를 반드시 적는다.")
    cond = N("conditionNode", rules=[{"id": "urgent", "operator": "Contains", "value": "긴급도: 상"}])
    sl = N("slackNode", channel="#urgent", text="")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="접수!A:C")
    o = out()
    nodes = [w, a, cond, sl, sh, o]
    edges = [link(w, a), link(a, cond), link(cond, sl, source_handle="urgent"),
             link(cond, sh, source_handle="else"), link(sl, o), link(sh, o)]
    add("고객 불만 분류·긴급 건 즉시 알림", "접수된 불만을 분류하고 긴급한 것만 바로 슬랙에 알립니다.",
        "automation", ["고객", "분류", "슬랙"], nodes, edges)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
