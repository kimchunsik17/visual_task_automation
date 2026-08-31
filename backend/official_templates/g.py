# -*- coding: utf-8 -*-
"""G묶음 — 개인 생산성·학습·생활."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []
NOTION = "{{API_CENTER:notion}}"


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def simple(trigger, prompt, tail, title, desc, cat, tags):
    a = llm(prompt)
    parts = [trigger, a] + list(tail) + [out()]
    n, e = chain(*parts)
    add(title, desc, cat, tags, n, e)


def t_daily_journal():
    s, i = start(), ask("오늘 있었던 일", "회의 두 건, 코드 리뷰 마무리")
    a = llm("입력으로 하루 회고를 쓴다 — 잘된 것 / 아쉬운 것 / 내일 할 것 세 항목. "
            "입력에 없는 일은 지어내지 않는다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, i, a, nt, out())
    add("하루 회고 자동 정리", "오늘 한 일을 적으면 회고 형식으로 정리해 노션에 남깁니다.",
        "document", ["회고", "노션", "개인"], n, e)


def t_reading_notes():
    s, i = start(), ask("읽은 글 주소", "https://example.com/article")
    c = N("webCrawlerNode", url="", output="text", maxChars=8000, respectRobots=True)
    a = llm("입력은 글 본문이다. 핵심 주장 3개, 근거, 내가 확인해 볼 것 2개로 정리한다. "
            "본문에 없는 내용은 쓰지 않는다.")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(s, i, c, a, nt, out())
    add("읽은 글 독서 노트", "글 주소를 넣으면 핵심과 확인할 점을 정리해 노션에 남깁니다.",
        "document", ["크롤링", "노션", "학습"], n, e)


def t_study_quiz():
    s, i = start(), ask("공부한 내용", "HTTP 상태 코드 정리")
    a = llm("입력 내용으로 복습 문제 5개를 만든다. 각 문제 아래 정답과 한 줄 해설을 붙인다. "
            "입력에 없는 내용은 묻지 않는다.")
    n, e = chain(s, i, a, out())
    add("공부한 내용 → 복습 문제", "오늘 공부한 것으로 복습 문제를 만들어 줍니다.",
        "content", ["학습", "퀴즈"], n, e)


def t_weekly_review_mail():
    s = sched("0 19 * * 5")
    nt = N("notionNode", token=NOTION, mode="query", databaseId="")
    a = llm("입력은 이번 주 기록이다. 한 주를 세 문단으로 돌아본다 — 한 일, 배운 것, 다음 주 초점. "
            "기록에 없는 것은 쓰지 않는다.")
    g = N("gmailNode", mode="send_email", to="", subject="주간 회고", body="")
    n, e = chain(s, nt, a, g, out())
    add("금요일 주간 회고 메일", "한 주 기록을 모아 회고를 써서 나에게 메일로 보냅니다.",
        "content", ["노션", "회고", "주간"], n, e)


def t_link_saver():
    a = llm("입력은 링크와 짧은 메모다. 무엇에 대한 링크인지 한 줄로 요약하고 태그 3개를 붙인다.")
    tr = N("telegramTriggerNode", botToken="{{API_CENTER:telegram}}")
    nt = N("notionNode", token=NOTION, mode="create", databaseId="", title="")
    n, e = chain(tr, a, nt, out())
    add("텔레그램으로 링크 모으기", "텔레그램에 링크를 보내면 요약과 태그를 붙여 노션에 저장합니다.",
        "automation", ["텔레그램", "노션", "북마크"], n, e)


def t_recipe_planner():
    s, i = start(), ask("냉장고에 있는 것", "달걀, 양파, 두부")
    a = llm("입력 재료로 만들 수 있는 요리 3가지를 제안한다. 각각 재료와 순서를 간단히 쓴다. "
            "없는 재료가 꼭 필요하면 '추가 필요' 로 표시한다.")
    n, e = chain(s, i, a, out())
    add("있는 재료로 요리 제안", "냉장고에 있는 재료로 만들 수 있는 요리를 알려 줍니다.",
        "content", ["생활", "추천"], n, e)


def t_expense_split():
    s, i = start(), ask("모임 지출 내역", "저녁 60000원 4명, 카페 20000원 3명")
    p = N("pythonNode", code=("lines = [l for l in str(input_data).split(chr(10)) if l.strip()]\n"
                              "output_data = chr(10).join(lines)"))
    a = llm("입력은 모임 지출이다. 각 항목의 1인당 금액과 최종 정산표를 만든다. "
            "인원이 불분명하면 '확인 필요' 로 표시한다.")
    n, e = chain(s, i, p, a, out())
    add("모임 비용 정산", "모임 지출을 적으면 1인당 금액과 정산표를 만들어 줍니다.",
        "data", ["생활", "정산"], n, e)


def t_job_watch():
    tr = N("rssTriggerNode", feedUrl="https://example.com/jobs.xml", maxItems=20)
    a = llm("입력은 새 채용 공고다. 내 조건({{조건}})에 맞는 것만 골라 회사·직무·왜 맞는지 정리한다. "
            "맞는 것이 없으면 '해당 없음'만 출력한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(tr, a, k, out())
    add("채용 공고 조건 맞춤 알림", "새 채용 공고 중 내 조건에 맞는 것만 골라 알려 줍니다.",
        "notification", ["rss", "채용", "카카오"], n, e)


def t_price_watch():
    s = sched("0 9,21 * * *")
    c = N("webCrawlerNode", url="https://example.com/product/1", output="structured",
          maxChars=3000, respectRobots=True)
    a = llm("입력은 상품 페이지 정보다. 제목과 본문에서 가격으로 보이는 숫자를 찾아 한 줄로 알린다. "
            "찾지 못하면 '가격 확인 실패'만 출력한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(s, c, a, k, out())
    add("상품 가격 하루 두 번 확인", "정한 상품 페이지를 하루 두 번 읽어 가격을 알려 줍니다.",
        "notification", ["크롤링", "가격", "카카오"], n, e)


def t_meeting_prep():
    s = sched("0 8 * * 1-5")
    c = N("googleCalendarNode", mode="list", calendarId="")
    a = llm("입력은 오늘 회의 일정이다. 각 회의마다 미리 준비하면 좋을 것을 두 가지씩 제안한다. "
            "제목만으로 알 수 없으면 '안건 확인 필요' 로 적는다.")
    n, e = chain(s, c, a, out())
    add("오늘 회의 준비 도우미", "오늘 잡힌 회의마다 미리 챙길 것을 알려 줍니다.",
        "content", ["캘린더", "회의", "준비"], n, e)


def t_habit_tracker():
    s = sched("0 21 * * *")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="습관!A:H")
    a = llm("입력은 습관 기록이다. 이번 주 달성률을 항목별로 계산하고, "
            "가장 잘 지킨 것과 가장 놓친 것을 짚어 준다.")
    k = N("kakaoNode", template="text")
    n, e = chain(s, sh, a, k, out())
    add("저녁 습관 점검 알림", "매일 밤 습관 기록을 보고 이번 주 달성률을 알려 줍니다.",
        "notification", ["시트", "습관", "카카오"], n, e)


def t_translate_bot():
    tr = N("discordTriggerNode", botToken="{{API_CENTER:discord}}")
    a = llm("입력이 한국어면 영어로, 아니면 한국어로 번역한다. 번역문만 출력한다.")
    n, e = chain(tr, a, out())
    add("디스코드 양방향 번역 봇", "디스코드에서 말을 걸면 한국어↔영어로 번역해 줍니다.",
        "automation", ["디스코드", "번역", "봇"], n, e)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
