# -*- coding: utf-8 -*-
"""새 템플릿 I묶음 — **필드 데이터 바인딩**(ADR-0026)을 쓰는 흐름.

a~h 묶음이 만들어질 때는 값 하나를 다음 노드의 필드에 넣으려면 promptNode + llmNode 나
jsonParserNode 사슬이 필요했다. 이 묶음은 그 자리를 `data.bindings` 로 대체한다 — 값이
바뀌어 나오지 않고(환각 없음), 실행마다 토큰이 들지 않는다.

그래서 이 묶음의 템플릿 대부분은 **LLM 을 아예 부르지 않거나**, 판단·요약처럼 실제로 생각이
필요한 자리에만 llmNode 를 둔다. 각 템플릿의 설명에 "LLM 0회" 를 적어 사용자가 그 차이를
알 수 있게 했다.

경로(path)를 쓰는 기준은 카탈로그 규칙과 같다 — 출력 형식이 문서화된 소스(naverSearchNode,
rssTriggerNode, databaseNode …)이거나, 웹훅처럼 **템플릿이 요청 본문 계약을 설명에 명시**한
경우에만 경로를 쓴다. 그 외에는 경로를 비워 출력 전체를 넘긴다.
"""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []


def add(title, desc, category, tags, nodes, edges, source="", slug=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source,
                      # 제목이 한글이면 slugify 가 ASCII 만 남겨 "llm-0" 같은 주소를 만든다 —
                      # 여러 템플릿이 같은 접두사를 나눠 갖게 되므로 읽을 수 있는 주소를 직접 준다.
                      "slug": slug})


def bind(node, field, source_node, path=""):
    """필드 하나를 앞 노드의 값에 연결한다(계획 §3 BindingSpec)."""
    node["data"].setdefault("bindings", {})[field] = {"source": source_node["id"], "path": path}
    return node


def var(name, value=""):
    """변수 허브 — 이름을 붙인 valueNode 는 앞 결과를 이어 붙이지 않고 값 그대로 내보낸다."""
    return N("valueNode", varName=name, value=value)


# ── 웹훅 payload → 필드 (요청 본문 계약을 설명에 명시한다) ─────────────────
def t_inquiry_ack():
    hook = N("webhookNode", method="POST", path="/inquiry")
    body = var("접수 안내문",
               "문의가 정상적으로 접수되었습니다.\n담당자가 확인한 뒤 영업일 기준 1일 안에 회신드립니다.")
    mail = N("emailNode", toEmail="", subject="문의가 접수되었습니다")
    bind(mail, "toEmail", hook, "email")
    nodes, edges = chain(hook, body, mail)
    add("문의 접수 확인 메일 (LLM 0회)",
        "웹훅으로 문의가 들어오면 문의한 사람에게 접수 확인 메일을 보냅니다. "
        "받는 사람 주소는 요청 본문의 email 값에 **연결**되어 있어 LLM 을 한 번도 부르지 않습니다. "
        "요청 본문 예: {\"email\": \"buyer@example.com\", \"name\": \"김워크\"}. "
        "메일 본문은 변수 노드의 안내문이 그대로 나갑니다 — 문구만 고쳐 쓰세요.",
        "notification", ["웹훅", "값연결", "토큰절약", "메일"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-inquiry-ack")


def t_incident_report_publish():
    hook = N("webhookNode", method="POST", path="/incident")
    fmt = N("formatNode", formatId="incident-report", output="hwpx")
    bind(fmt, "values", hook, "")          # 요청 본문(JSON) 전체를 빈칸 값으로
    mail = N("emailNode", toEmail="", subject="시말서 제출")
    bind(mail, "toEmail", hook, "managerEmail")
    nodes, edges = chain(hook, fmt, mail)
    add("사고 접수 웹훅 → 시말서 자동 발행 → 담당자 메일 (LLM 0회)",
        "사내 양식이 웹훅으로 보낸 값을 시말서 빈칸에 그대로 채워 한글(.hwpx) 파일을 만들고 "
        "담당자에게 첨부해 보냅니다. 빈칸과 수신자 모두 요청 본문에 **연결**되어 있어 "
        "LLM 을 부르지 않습니다 — 값이 바뀌어 나올 일이 없습니다. "
        "요청 본문 키: department, authorName, incidentAt, summary, cause, prevention (필수) · "
        "place, timeline (선택) · managerEmail (받는 사람).",
        "document", ["웹훅", "시말서", "값연결", "토큰절약", "한글"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-incident-report")


def t_webhook_relay():
    hook = N("webhookNode", method="POST", path="/relay")
    # headers 는 정화에서 지워진다(Authorization 이 섞이는 자리라 게시 시 비워진다) —
    # 템플릿에 적어 두면 남는 것처럼 보이므로 아예 넣지 않고 설명으로 안내한다.
    fwd = N("httpRequestNode", method="POST", url="REPLACE_WITH_ACTUAL_URL", body="")
    bind(fwd, "body", hook, "")            # 받은 본문을 그대로 전달
    nodes, edges = chain(hook, fwd, out())
    add("웹훅 릴레이 — 받은 요청을 다른 시스템으로 그대로 전달 (LLM 0회)",
        "한 곳에서 받은 웹훅을 다른 시스템의 API 로 그대로 넘깁니다. 보낼 본문이 받은 본문에 "
        "**연결**되어 있어 값을 다시 만들지 않습니다(LLM 0회). 전달할 주소만 채우세요. "
        "본문 일부만 넘기려면 연결의 경로를 원하는 키로 바꾸면 됩니다. "
        "인증 헤더가 필요한 API 라면 헤더는 설치 후 직접 채우세요 — 게시 시 비워집니다.",
        "automation", ["웹훅", "릴레이", "값연결", "토큰절약"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-webhook-relay")


def t_variable_hub_fanout():
    hook = N("webhookNode", method="POST", path="/order")
    hub = var("담당자 이메일")
    bind(hub, "value", hook, "managerEmail")   # 한 번만 꺼낸다
    to_manager = N("emailNode", toEmail="", subject="[접수] 새 주문이 등록되었습니다")
    bind(to_manager, "toEmail", hub, "")
    to_archive = N("emailNode", toEmail="", subject="[사본] 주문 접수 기록")
    bind(to_archive, "toEmail", hub, "")
    nodes = [hook, hub, to_manager, to_archive]
    edges = [link(hook, hub), link(hub, to_manager), link(hub, to_archive)]
    add("변수 허브 — 같은 주소를 여러 발송 노드가 함께 쓰기 (LLM 0회)",
        "요청 본문에서 담당자 주소를 **한 번만** 꺼내 변수 노드에 담고, 알림 메일과 사본 메일이 "
        "그 변수를 연결해 씁니다. 주소를 바꿀 일이 생기면 변수 노드 한 곳만 고치면 됩니다 — "
        "경로를 발송 노드마다 복사해 두면 한 곳을 놓치기 쉽습니다. "
        "요청 본문 키: managerEmail.",
        "notification", ["변수허브", "값연결", "토큰절약", "메일"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-variable-hub")


# ── 출력 형식이 문서화된 소스 → 경로를 써도 되는 자리 ──────────────────────
def t_naver_first_article():
    s = start()
    q = N("naverSearchNode", mode="blog", query="{{검색어}}", display=10, sort="sim")
    crawl = N("webCrawlerNode", url="", output="text", maxChars=5000)
    bind(crawl, "url", q, "items[0].link")     # 카탈로그에 문서화된 출력 형식
    a = llm("입력은 블로그 글 본문이다. 핵심을 5줄로 요약하고, 근거가 약한 주장은 "
            "'확인 필요'로 표시한다. 본문에 없는 내용은 쓰지 않는다.")
    nodes, edges = chain(s, q, crawl, a, out())
    add("네이버 검색 → 첫 글 본문 수집 → 요약",
        "검색어 하나로 블로그를 찾아 **가장 관련 있는 첫 글의 링크를 크롤러 주소에 연결**해 "
        "본문을 읽고 요약합니다. 링크를 꺼내려고 JSON 파서나 LLM 을 끼우지 않습니다 — "
        "LLM 은 요약 한 번만 씁니다.",
        "content", ["네이버", "크롤링", "값연결", "요약"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-naver-first-article")


def t_rss_to_slack():
    tr = N("rssTriggerNode", feedUrl="{{피드 주소}}", maxItems=5)
    crawl = N("webCrawlerNode", url="", output="text", maxChars=4000)
    bind(crawl, "url", tr, "[0].link")         # 새 항목 배열의 첫 글
    a = llm("입력은 새 글의 본문이다. 팀에게 알릴 만한 내용인지 판단해 "
            "'알림: <한 줄 요약>' 또는 '알림 불필요'만 출력한다.")
    slack = N("slackNode", channel="#{{채널}}", message="RSS 새 글 요약")
    nodes, edges = chain(tr, crawl, a, slack)
    add("RSS 새 글 → 본문 수집 → 슬랙 알림",
        "피드에 새 글이 올라오면 **그 글의 링크를 크롤러 주소에 연결**해 본문까지 읽고, "
        "팀에 알릴 만한지 판단해 슬랙으로 보냅니다. 링크 추출용 노드가 필요 없습니다.",
        "notification", ["rss", "크롤링", "값연결", "슬랙"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-rss-to-slack")


def t_db_owner_notify():
    s = sched("0 9 * * 1")
    db = N("databaseNode", connectionString="{{API_CENTER:database}}",
           query="SELECT owner_email, overdue_count FROM overdue_summary LIMIT 1",
           allowedSchemas="public", outputFormat="result", rows=1)
    mail = N("emailNode", toEmail="", subject="[주간] 처리 지연 건 안내")
    bind(mail, "toEmail", db, "data.rows[0][0]")   # result 형식의 문서화된 경로
    nodes, edges = chain(s, db, mail)
    add("주간 DB 조회 → 조회 결과의 담당자에게 자동 발송 (LLM 0회)",
        "매주 월요일 아침에 조회를 돌려 **결과 첫 행의 이메일 주소를 받는 사람에 연결**해 보냅니다. "
        "주소를 꺼내기 위해 LLM 을 쓰지 않습니다(LLM 0회). 조회는 읽기 전용이며 변경 쿼리는 "
        "실행 전에 차단됩니다. 접속 정보는 API 센터에 등록해 연결하세요. "
        "쿼리와 결과 형식(result)을 바꾸면 연결 경로도 함께 맞춰야 합니다.",
        "data", ["데이터베이스", "값연결", "토큰절약", "스케줄"], nodes, edges,
        source="WorkFlow Ai 자체 제작 (데이터 바인딩 예시)", slug="binding-db-owner-notify")


for _fn in (t_inquiry_ack, t_incident_report_publish, t_webhook_relay, t_variable_hub_fanout,
            t_naver_first_article, t_rss_to_slack, t_db_owner_notify):
    _fn()
