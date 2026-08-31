# -*- coding: utf-8 -*-
"""D묶음 — 대화형 봇(텔레그램·디스코드·카카오)과 알림. 142개가 안 쓴 트리거들이다."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []
API = "{{API_CENTER:%s}}"


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def bot(kind):
    return N(f"{kind}TriggerNode", botToken=API % kind)


def t_tg_qna():
    a = llm("너는 친절한 안내 봇이다. 모르는 것은 모른다고 답하고 지어내지 않는다. 답은 5줄 이내.")
    n, e = chain(bot("telegram"), a, out())
    add("텔레그램 질문 답변 봇", "텔레그램으로 말을 걸면 답해 주는 기본 봇입니다.",
        "automation", ["텔레그램", "봇", "챗봇"], n, e)


def t_tg_translate():
    a = llm("입력을 영어로 번역한다. 번역문만 출력하고 설명을 붙이지 않는다.")
    n, e = chain(bot("telegram"), a, out())
    add("텔레그램 즉시 번역 봇", "메시지를 보내면 영어로 번역해 돌려줍니다.",
        "automation", ["텔레그램", "번역", "봇"], n, e)


def t_dc_qna():
    a = llm("너는 팀 도우미 봇이다. 사내 규정을 모르면 '확인이 필요합니다'라고 답하고 추측하지 않는다.")
    n, e = chain(bot("discord"), a, out())
    add("디스코드 팀 도우미 봇", "디스코드에서 멘션하면 답해 주는 봇입니다.",
        "automation", ["디스코드", "봇", "챗봇"], n, e)


def t_dc_summarize_link():
    c = N("webCrawlerNode", url="", output="text", maxChars=6000, respectRobots=True)
    a = llm("입력은 웹페이지 본문이다. 세 문장으로 요약한다. 본문에 없는 내용은 쓰지 않는다.")
    n, e = chain(bot("discord"), c, a, out())
    add("디스코드에 링크 던지면 요약", "링크를 보내면 그 페이지를 읽어 세 문장으로 요약합니다.",
        "automation", ["디스코드", "크롤링", "요약"], n, e)


def t_tg_address():
    j = N("jusoNode", keyword="", count=3)
    a = llm("입력은 도로명주소 검색 결과다. 가장 그럴듯한 주소와 우편번호만 한 줄로 답한다. "
            "없으면 '찾지 못했습니다'라고 답한다.")
    n, e = chain(bot("telegram"), j, a, out())
    add("텔레그램 주소 검색 봇", "주소를 보내면 정확한 도로명주소와 우편번호를 알려 줍니다.",
        "automation", ["텔레그램", "주소", "봇"], n, e)


def t_kakao_daily_news():
    s = sched("0 7 * * *")
    q = N("naverSearchNode", mode="blog", query="{{관심 주제}}", display=15, sort="date")
    a = llm("입력은 오늘의 글이다. 3개만 골라 제목과 한 줄 요약으로 정리한다. "
            "광고성 글은 제외한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(s, q, a, k, out())
    add("아침 관심 주제 카카오 브리핑", "매일 아침 관심 주제의 새 글 3개를 카카오톡으로 보냅니다.",
        "notification", ["카카오", "네이버", "브리핑"], n, e)


def t_slack_standup():
    s = sched("0 10 * * 1-5")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="스탠드업!A:D")
    a = llm("입력은 팀원들이 적은 오늘 할 일이다. 사람별로 묶어 정리하고 "
            "막힌 항목이 있으면 맨 위에 모아 준다.")
    sl = N("slackNode", channel="#standup", text="")
    n, e = chain(s, sh, a, sl, out())
    add("아침 스탠드업 정리 → 슬랙", "팀원이 적은 할 일을 정리해 매일 아침 슬랙에 올립니다.",
        "notification", ["슬랙", "시트", "스탠드업"], n, e)


def t_slack_error_digest():
    s = sched("0 */4 * * *")
    d = N("databaseNode", query="SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 50")
    a = llm("입력은 최근 오류 로그다. 같은 원인끼리 묶고 건수가 많은 순으로 정리한다. "
            "새로 나타난 오류는 맨 위에 표시한다.")
    sl = N("slackNode", channel="#alerts", text="")
    n, e = chain(s, d, a, sl, out())
    add("오류 로그 4시간 요약 → 슬랙", "오류 로그를 원인별로 묶어 주기적으로 슬랙에 알립니다.",
        "notification", ["슬랙", "데이터베이스", "모니터링"], n, e)


def t_email_to_kakao():
    tr = N("gmailTriggerNode", query="is:important is:unread", maxResults=10)
    a = llm("입력은 중요 메일이다. 보낸사람과 요점만 두 줄로 정리한다. 없으면 '새 메일 없음'만 출력한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(tr, a, k, out())
    add("중요 메일 카카오 알림", "중요 표시된 새 메일이 오면 요점만 카카오톡으로 보냅니다.",
        "notification", ["gmail", "카카오", "알림"], n, e)


def t_approval_notice():
    s, i = start(), ask("공지 초안", "다음 주 월요일 시스템 점검이 있습니다.")
    a = llm("입력을 사내 공지 문장으로 다듬는다. 날짜·시간·영향 범위가 빠져 있으면 "
            "'[확인 필요]' 로 표시하고 지어내지 않는다.")
    h = N("humanApprovalNode")
    sl = N("slackNode", channel="#general", text="")
    n, e = chain(s, i, a, h, sl, out())
    add("사내 공지 승인 후 발송", "공지 초안을 다듬고 사람이 확인한 뒤에만 슬랙에 올립니다.",
        "notification", ["슬랙", "승인", "공지"], n, e)


def t_webhook_to_slack():
    w = N("webhookNode")
    a = llm("입력은 외부에서 온 알림 데이터다. 사람이 읽을 한 문단으로 바꾼다. "
            "필드가 비어 있으면 '값 없음'으로 표시한다.")
    sl = N("slackNode", channel="#general", text="")
    n, e = chain(w, a, sl, out())
    add("웹훅 알림 사람 말로 바꿔 슬랙에", "외부 시스템 웹훅을 읽기 쉬운 문장으로 바꿔 알립니다.",
        "notification", ["웹훅", "슬랙"], n, e)


def t_rss_keyword_alert():
    tr = N("rssTriggerNode", feedUrl="https://example.com/feed.xml", maxItems=20)
    cond = N("conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": "{{키워드}}"}])
    a = llm("입력은 키워드가 걸린 글이다. 제목과 왜 걸렸는지 한 줄로 알린다.")
    k = N("kakaoNode", template="text")
    o = out()
    nodes = [tr, cond, a, k, o]
    edges = [link(tr, cond), link(cond, a, source_handle="r1"), link(cond, o, source_handle="else"),
             link(a, k), link(k, o)]
    add("피드에 키워드 뜨면 알림", "구독 피드에 정한 단어가 나오면 카카오톡으로 알려 줍니다.",
        "notification", ["rss", "키워드", "카카오"], nodes, edges)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
