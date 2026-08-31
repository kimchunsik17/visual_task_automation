# -*- coding: utf-8 -*-
"""H묶음 — 개발·운영·마케팅. 100개를 채우는 마지막 묶음."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []
NOTION = "{{API_CENTER:notion}}"


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def t_release_notes():
    s, i = start(), ask("이번 배포 변경 목록", "- 로그인 속도 개선\n- 결제 오류 수정")
    a = llm("입력을 사용자용 릴리스 노트로 다듬는다 — 새 기능 / 개선 / 버그 수정으로 나누고 "
            "기술 용어는 쉬운 말로 바꾼다. 입력에 없는 항목은 만들지 않는다.")
    sl = N("slackNode", channel="#release", text="")
    n, e = chain(s, i, a, sl, out())
    add("배포 변경 목록 → 릴리스 노트", "커밋 메모를 사용자용 릴리스 노트로 바꿔 줍니다.",
        "content", ["배포", "슬랙", "개발"], n, e)


def t_incident_report():
    s, i = start(), ask("장애 상황", "결제 API 30분 지연, 재시작으로 복구")
    a = llm("입력으로 장애 보고서를 쓴다 — 발생 시각 / 영향 / 원인 / 조치 / 재발 방지. "
            "입력에서 확인되지 않은 항목은 '조사 중' 으로 적고 추측하지 않는다.")
    h = N("hwpxDocumentNode", mode="create", output_path="장애보고서.hwpx")
    n, e = chain(s, i, a, h, out())
    add("장애 상황 → 한글 보고서", "장애 메모를 정해진 형식의 한글 보고서로 만듭니다.",
        "document", ["장애", "한글", "운영"], n, e)


def t_db_backup_check():
    s = sched("0 6 * * *")
    d = N("databaseNode", query="SELECT MAX(created_at) AS last_backup FROM backup_log")
    a = llm("입력은 마지막 백업 시각이다. 24시간이 넘었으면 경고 문구를, 아니면 '정상'만 출력한다.")
    sl = N("slackNode", channel="#ops", text="")
    n, e = chain(s, d, a, sl, out())
    add("백업 상태 아침 점검", "매일 아침 마지막 백업이 언제였는지 확인해 알립니다.",
        "notification", ["데이터베이스", "운영", "점검"], n, e)


def t_api_health():
    s = sched("*/30 * * * *")
    h = N("httpRequestNode", url="REPLACE_WITH_ACTUAL_URL", method="GET")
    a = llm("입력은 상태 점검 응답이다. 정상이면 '정상' 만, 아니면 무엇이 문제인지 한 줄로 알린다.")
    sl = N("slackNode", channel="#ops", text="")
    n, e = chain(s, h, a, sl, out())
    add("서비스 상태 30분 점검", "정한 주소를 주기적으로 찔러 보고 이상하면 알려 줍니다.",
        "notification", ["모니터링", "슬랙", "운영"], n, e)


def t_log_to_notion():
    s = sched("0 23 * * *")
    d = N("databaseNode", query="SELECT * FROM error_logs WHERE created_at::date = CURRENT_DATE")
    a = llm("입력은 오늘 오류다. 원인별로 묶고 각 묶음에 건수와 첫 발생 시각을 적는다. "
            "오류가 없으면 '오늘 오류 없음'만 출력한다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, d, a, nt, out())
    add("일일 오류 기록을 노션에", "하루 오류를 원인별로 묶어 노션에 남깁니다.",
        "data", ["데이터베이스", "노션", "운영"], n, e)


def t_seo_title():
    s, i = start(), ask("글 주제", "리액트 상태 관리 비교")
    a = llm("입력 주제로 검색에 잘 걸릴 제목 후보 5개를 만든다. 각 제목 아래 "
            "왜 그렇게 지었는지 한 줄로 설명한다. 과장하거나 낚시성 표현은 쓰지 않는다.")
    n, e = chain(s, i, a, out())
    add("검색 잘 되는 제목 후보 만들기", "주제 하나로 제목 후보 5개와 근거를 만들어 줍니다.",
        "content", ["마케팅", "제목"], n, e)


def t_ad_copy_variants():
    s, i = start(), ask("제품 설명", "가벼운 노트북 거치대")
    a = llm("입력으로 광고 문구 5개를 만든다. 각각 다른 각도(가격·편의·디자인·후기·비교)를 쓰고, "
            "제품 설명에 없는 효능은 넣지 않는다.")
    n, e = chain(s, i, a, out())
    add("광고 문구 5개 만들기", "제품 설명 하나로 서로 다른 각도의 문구를 만들어 줍니다.",
        "content", ["마케팅", "광고"], n, e)


def t_review_reply():
    s, i = start(), ask("고객 후기", "배송은 빨랐는데 포장이 아쉬웠어요")
    a = llm("입력 후기에 대한 답글을 쓴다. 지적한 점을 인정하고 개선 방향을 한 줄로 밝힌다. "
            "변명하지 않고 5줄을 넘기지 않는다.")
    h = N("humanApprovalNode")
    n, e = chain(s, i, a, h, out())
    add("고객 후기 답글 초안", "후기에 대한 답글 초안을 쓰고 사람이 확인하게 합니다.",
        "content", ["고객", "후기", "승인"], n, e)


def t_competitor_price():
    s = sched("0 10 * * *")
    c = N("webCrawlerNode", url="https://example.com/competitor", output="structured",
          maxChars=5000, respectRobots=True)
    a = llm("입력은 경쟁사 페이지 정보다. 제목과 본문에서 가격·프로모션으로 보이는 내용을 뽑아 정리한다. "
            "찾지 못하면 '변동 없음'만 출력한다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="경쟁사!A:C")
    n, e = chain(s, c, a, sh, out())
    add("경쟁사 페이지 매일 기록", "경쟁사 페이지를 매일 읽어 변화를 시트에 쌓습니다.",
        "data", ["크롤링", "시트", "마케팅"], n, e)


def t_social_calendar():
    s = sched("0 9 * * 1")
    q = N("naverSearchNode", mode="blog", query="{{업계 키워드}}", display=25, sort="date")
    a = llm("입력은 업계 최근 글이다. 이번 주 올릴 소셜 게시물 5개를 제안한다. "
            "각각 무엇을 다루고 왜 지금인지 한 줄로 적는다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, q, a, nt, out())
    add("주간 소셜 게시물 기획", "업계 흐름을 보고 이번 주 올릴 게시물을 제안합니다.",
        "content", ["네이버", "노션", "마케팅"], n, e)


def t_faq_builder():
    s = start()
    d = N("databaseNode", query="SELECT question FROM support_tickets ORDER BY created_at DESC LIMIT 200")
    a = llm("입력은 고객 문의 모음이다. 자주 나오는 질문 10개를 뽑고 각각에 답변 초안을 쓴다. "
            "답을 모르는 것은 '담당자 확인 필요' 로 남긴다.")
    h = N("hwpxDocumentNode", mode="create", output_path="FAQ.hwpx")
    n, e = chain(s, d, a, h, out())
    add("문의 기록 → FAQ 문서", "쌓인 문의에서 자주 나오는 질문을 뽑아 FAQ를 만듭니다.",
        "document", ["데이터베이스", "한글", "고객"], n, e)


def t_code_review_summary():
    s, i = start(), ask("리뷰 코멘트 모음", "- 변수명 모호\n- 테스트 누락")
    a = llm("입력은 코드 리뷰 코멘트다. 반복되는 지적을 묶어 팀이 고칠 규칙 3가지를 제안한다. "
            "코멘트에 없는 규칙은 만들지 않는다.")
    sl = N("slackNode", channel="#dev", text="")
    n, e = chain(s, i, a, sl, out())
    add("리뷰 코멘트에서 팀 규칙 뽑기", "반복되는 리뷰 지적을 모아 팀 규칙으로 제안합니다.",
        "content", ["개발", "슬랙", "리뷰"], n, e)


def t_doc_gap_check():
    s, i = start(), ask("문서 주소", "https://example.com/docs")
    c = N("webCrawlerNode", url="", output="structured", maxChars=8000, respectRobots=True)
    a = llm("입력은 문서 페이지다. 설명이 빠졌거나 예시가 없는 부분을 짚어 준다. "
            "문서에서 확인되는 것만 지적하고 추측하지 않는다.")
    n, e = chain(s, i, c, a, out())
    add("문서 빠진 부분 점검", "문서 페이지를 읽어 설명이나 예시가 빠진 곳을 짚어 줍니다.",
        "content", ["크롤링", "문서", "개발"], n, e)


def t_daily_standup_reminder():
    s = sched("50 9 * * 1-5")
    a = llm("오늘 스탠드업 알림 문구를 쓴다. 어제 한 일·오늘 할 일·막힌 것 세 가지를 "
            "적어 달라고 요청하는 짧은 문장이면 된다.")
    sl = N("slackNode", channel="#standup", text="")
    n, e = chain(s, a, sl, out())
    add("스탠드업 작성 알림", "평일 아침에 스탠드업을 적어 달라고 슬랙에 알립니다.",
        "notification", ["슬랙", "알림", "팀"], n, e)


def t_backup_report_mail():
    s = sched("0 7 * * 1")
    d = N("databaseNode", query="SELECT * FROM backup_log WHERE created_at > NOW() - INTERVAL '7 days'")
    a = llm("입력은 지난주 백업 기록이다. 성공·실패 건수와 실패한 날짜를 정리한다. "
            "기록이 없으면 '기록 없음'만 출력한다.")
    g = N("gmailNode", mode="send_email", to="", subject="주간 백업 보고", body="")
    n, e = chain(s, d, a, g, out())
    add("주간 백업 보고 메일", "지난주 백업 성공·실패를 정리해 메일로 보냅니다.",
        "notification", ["데이터베이스", "gmail", "운영"], n, e)


def t_translate_docs_batch():
    s, i = start(), ask("번역할 문단들(줄바꿈 구분)", "First paragraph.\nSecond paragraph.")
    d = N("distributorNode")
    a = llm("입력 문단을 자연스러운 한국어로 번역한다. 번역문만 출력한다.")
    # 분배기를 쓰지 않는다 — 입력이 텍스트 한 칸이라 목록이 아니어서 **한 번만 돈다**.
    # 모델이 여러 문단을 한 번에 번역할 수 있으므로 그냥 통째로 넘긴다(제목도 "한 번에" 다).
    n, e = chain(s, i, a, out())
    add("문단 일괄 번역", "여러 문단을 한 번에 한국어로 번역해 줍니다.",
        "content", ["번역", "일괄처리"], n, e)


def t_notion_to_hwpx():
    s = start()
    nt = N("notionNode", token=NOTION, mode="query", databaseId="")
    a = llm("입력은 노션 항목이다. 아래 JSON 하나만 출력한다 — 설명을 붙이지 않는다.\n"
            '{"title":"문서 제목","blocks":[{"type":"heading","text":"소제목"},{"type":"paragraph","text":"내용"}]}')
    h = N("hwpxDocumentNode", mode="create", output_path="노션정리.hwpx")
    n, e = chain(s, nt, a, h, out())
    add("노션 내용 → 한글 문서", "노션 데이터베이스 내용을 한글 문서로 내보냅니다.",
        "document", ["노션", "한글", "hwpx"], n, e)


def t_email_thread_summary():
    tr = N("gmailTriggerNode", query="is:unread", maxResults=30)
    a = llm("입력은 메일 묶음이다. 같은 주제끼리 묶고 각 묶음의 현재 상황과 "
            "내가 해야 할 일을 한 줄씩 정리한다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(tr, a, nt, out())
    add("메일 주제별 정리 → 노션", "쌓인 메일을 주제별로 묶어 할 일과 함께 노션에 정리합니다.",
        "automation", ["gmail", "노션", "정리"], n, e)


def t_webhook_to_db_log():
    w = N("webhookNode")
    j = N("jsonParserNode", mode="parse")
    a = llm("입력은 파싱된 이벤트다. 무슨 일이 일어났는지 한 문장으로 정리한다. "
            "필드가 비어 있으면 '값 없음'으로 표시한다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="이벤트!A:B")
    n, e = chain(w, j, a, sh, out())
    add("웹훅 이벤트 기록", "외부에서 온 웹훅을 사람 말로 바꿔 시트에 기록합니다.",
        "data", ["웹훅", "시트", "기록"], n, e)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
