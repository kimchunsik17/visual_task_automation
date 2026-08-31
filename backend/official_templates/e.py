# -*- coding: utf-8 -*-
"""E묶음 — 문서·데이터 처리(노션·데이터베이스·반복·한글)."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []
NOTION = "{{API_CENTER:notion}}"


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def t_notion_meeting_notes():
    s, i = start(), ask("회의 기록", "오늘 회의에서 A안으로 결정, 담당 김철수, 마감 다음 주 금요일")
    a = llm("입력은 회의 기록이다. 결정사항·담당자·마감일을 표로 정리하고, "
            "빠진 항목은 '미정'으로 표시한다. 지어내지 않는다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, i, a, nt, out())
    add("회의 기록 → 노션 정리", "회의 메모에서 결정사항과 담당자를 뽑아 노션에 정리합니다.",
        "document", ["노션", "회의", "정리"], n, e)


def t_notion_query_digest():
    s = sched("0 9 * * 1")
    nt = N("notionNode", token=NOTION, mode="query", databaseId="")
    a = llm("입력은 노션 데이터베이스 항목이다. 이번 주 마감인 것만 골라 담당자별로 묶어 정리한다. "
            "없으면 '이번 주 마감 없음'만 출력한다.")
    sl = N("slackNode", channel="#general", text="")
    n, e = chain(s, nt, a, sl, out())
    add("이번 주 마감 항목 알림", "노션에서 이번 주 마감인 일만 골라 담당자별로 알려 줍니다.",
        "notification", ["노션", "슬랙", "마감"], n, e)


def t_db_weekly_metrics():
    s = sched("0 9 * * 1")
    d = N("databaseNode", query="SELECT date, signups, revenue FROM daily_metrics ORDER BY date DESC LIMIT 14")
    a = llm("입력은 최근 14일 지표다. 지난주와 이번 주를 비교해 늘고 준 항목을 정리한다. "
            "데이터에 없는 수치는 만들지 않는다.")
    h = N("hwpxDocumentNode", mode="create", output_path="주간지표.hwpx")
    n, e = chain(s, d, a, h, out())
    add("주간 지표 → 한글 보고서", "데이터베이스 지표를 읽어 한글 주간 보고서를 만듭니다.",
        "document", ["데이터베이스", "한글", "주간"], n, e)


def t_db_anomaly():
    s = sched("0 */6 * * *")
    d = N("databaseNode", query="SELECT * FROM orders WHERE created_at > NOW() - INTERVAL '6 hours'")
    a = llm("입력은 최근 6시간 주문이다. 평소와 다른 점(급증·급감·같은 계정 반복)이 보이면 알린다. "
            "특이사항이 없으면 '이상 없음'만 출력한다.")
    sl = N("slackNode", channel="#alerts", text="")
    n, e = chain(s, d, a, sl, out())
    add("주문 이상 징후 감시", "여섯 시간마다 주문을 훑어 평소와 다른 점을 알려 줍니다.",
        "notification", ["데이터베이스", "감시", "슬랙"], n, e)


def t_csv_to_summary():
    s, i = start(), ask("표 데이터(CSV)", "이름,부서,금액\n김철수,영업,120000")
    p = N("pythonNode", code=(
        "lines = [l for l in str(input_data).split(chr(10)) if l.strip()]\n"
        "header = lines[0].split(',') if lines else []\n"
        "output_data = f'{len(lines)-1}행, 열: {header}'"))
    a = llm("입력은 표 요약이다. 사람이 읽을 한 문단으로 정리한다.")
    n, e = chain(s, i, p, a, out())
    add("붙여넣은 표 요약", "CSV를 붙여넣으면 무엇이 들어 있는지 정리해 줍니다.",
        "data", ["csv", "요약", "코드"], n, e)


def t_hwpx_fill_form():
    s, i = start(), ask("채울 내용", "이름: 김철수, 부서: 개발팀, 날짜: 2026-09-01")
    a = llm("입력에서 항목을 뽑아 {\"이름\":\"값\"} 형태의 JSON 하나만 출력한다. "
            "설명을 붙이지 않고, 없는 항목은 넣지 않는다.")
    f = N("fileModifierNode", template_path="uploads/서식.hwpx", output_path="작성완료.hwpx")
    n, e = chain(s, i, a, f, out())
    add("한글 서식 빈칸 자동 채우기", "문장으로 적은 내용을 한글 서식의 빈칸에 채워 넣습니다.",
        "document", ["한글", "서식", "자동완성"], n, e)


def t_template_check():
    s = start()
    t = N("templateAnalyzerNode", template_path="uploads/서식.hwpx")
    a = llm("입력은 서식 분석 결과다. 어떤 빈칸이 있고 각각 무엇을 넣어야 할지 표로 정리한다.")
    n, e = chain(s, t, a, out())
    add("서식 빈칸 목록 뽑기", "서식 파일에 어떤 빈칸이 있는지 목록으로 정리해 줍니다.",
        "document", ["서식", "분석"], n, e)


def t_loop_batch_summary():
    s, i = start(), ask("요약할 문단들(줄바꿈 구분)", "첫 문단\n두 번째 문단")
    d = N("distributorNode")
    a = llm("입력 문단을 한 문장으로 줄인다. 문장 하나만 출력한다.")
    # 분배기를 쓰지 않는다 — 입력이 텍스트 한 칸이라 목록이 아니어서 한 번만 돈다(h.py 참고).
    n, e = chain(s, i, a, out())
    add("여러 문단 한 번에 요약", "줄바꿈으로 나눈 문단을 각각 한 문장으로 줄여 줍니다.",
        "content", ["일괄처리", "요약"], n, e)


def t_json_normalize():
    s, i = start(), ask("JSON 데이터", '{"name":"홍길동","addr":"부산 금정구"}')
    j = N("jsonParserNode", mode="parse")
    a = llm("입력은 파싱된 데이터다. 사람이 읽을 표로 정리한다. 빈 값은 '없음'으로 적는다.")
    n, e = chain(s, i, j, a, out())
    add("JSON 사람 말로 바꾸기", "JSON 데이터를 읽기 쉬운 표로 정리해 줍니다.",
        "data", ["json", "정리"], n, e)


def t_doc_translate_hwpx():
    s, i = start(), ask("번역할 원문", "This is a quarterly report.")
    a = llm("입력을 자연스러운 한국어로 번역한 뒤, 아래 JSON 하나만 출력한다 — 설명을 붙이지 않는다.\n"
            '{"title":"제목","blocks":[{"type":"paragraph","text":"번역문"}]}')
    h = N("hwpxDocumentNode", mode="create", output_path="번역본.hwpx")
    n, e = chain(s, i, a, h, out())
    add("영문 원문 → 한글 번역 문서", "영어 원문을 번역해 한글 문서로 만들어 줍니다.",
        "document", ["번역", "한글", "hwpx"], n, e)


def t_hwpx_validate_batch():
    s = start()
    h = N("hwpxDocumentNode", mode="validate")
    a = llm("입력은 문서 검사 결과다. 열리는지 여부와 문제가 있으면 무엇인지 한 문단으로 정리한다.")
    n, e = chain(s, h, a, out())
    add("한글 문서 열림 검사", "한글 파일이 정상적으로 열리는 상태인지 확인해 줍니다.",
        "document", ["한글", "검사"], n, e)


def t_db_to_sheet():
    s = sched("0 2 * * *")
    d = N("databaseNode", query="SELECT * FROM daily_summary WHERE date = CURRENT_DATE - 1")
    a = llm("입력은 어제 집계다. 쉼표로 구분한 한 줄로만 출력한다. 값이 없으면 빈칸으로 둔다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="집계!A:E")
    n, e = chain(s, d, a, sh, out())
    add("어제 집계 → 시트 적재", "매일 새벽에 어제 집계를 시트에 한 줄씩 쌓습니다.",
        "data", ["데이터베이스", "시트", "집계"], n, e)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
