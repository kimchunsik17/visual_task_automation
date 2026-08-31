# -*- coding: utf-8 -*-
"""새 템플릿 A묶음 — 한국형 노드(네이버·HWPX·도로명주소·웹수집).

142개를 만들 때는 없던 노드들이다. 그래서 이 묶음은 기존 템플릿과 겹치지 않는다.
"""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


# ── 네이버 검색 ─────────────────────────────────────────────────────────
def t_naver_blog_digest():
    s, q = sched("0 9 * * *"), N("naverSearchNode", mode="blog", query="{{키워드}}", display=20, sort="date")
    a = llm("입력은 네이버 블로그 검색 결과다. 오늘 주목할 글 5개를 골라 제목과 한 줄 요약으로 정리한다. "
            "광고성 글은 제외하고, 판단 근거가 부족하면 '판단 보류'라고 적는다.")
    n, e = chain(s, q, a, out())
    add("네이버 블로그 아침 브리핑", "정한 키워드로 매일 아침 블로그 새 글을 모아 5개로 추려 줍니다.",
        "content", ["네이버", "브리핑", "스케줄"], n, e)


def t_naver_cafe_watch():
    tr = N("naverSearchTriggerNode", mode="cafe_article", query="{{키워드}}", pollInterval=600, maxResults=10)
    a = llm("입력은 새로 올라온 네이버 카페 글이다. 우리가 대응해야 할 글만 남기고 "
            "각각에 왜 대응이 필요한지 한 줄로 적는다. 없으면 '대응 필요 없음'만 출력한다.")
    n, e = chain(tr, a, out())
    add("카페 새 글 감시 → 대응 필요 판별", "키워드로 카페 새 글을 감시해 대응이 필요한 것만 걸러 줍니다.",
        "notification", ["네이버", "모니터링", "카페"], n, e)


def t_naver_to_hwpx():
    s, q = start(), N("naverSearchNode", mode="blog", query="{{조사 주제}}", display=30, sort="sim")
    a = llm("입력은 검색 결과다. 아래 JSON 하나만 출력한다 — 설명이나 코드펜스를 붙이지 않는다.\n"
            '{"title":"보고서 제목","blocks":[{"type":"heading","text":"소제목"},'
            '{"type":"paragraph","text":"내용"}]}\n검색 결과에 없는 사실은 쓰지 않는다.')
    h = N("hwpxDocumentNode", mode="create", output_path="시장조사.hwpx")
    n, e = chain(s, q, a, h, out())
    add("네이버 검색 → 한글 시장조사 보고서", "주제 하나로 블로그를 훑어 한글(.hwpx) 보고서 초안을 만듭니다.",
        "document", ["네이버", "한글", "hwpx", "보고서"], n, e)


def t_juso_cleanup():
    s, i = start(), ask("정리할 주소", "부산대학로63번길 2")
    j = N("jusoNode", keyword="", count=5)
    a = llm("입력은 도로명주소 검색 결과 JSON 이다. 가장 그럴듯한 한 건을 골라 "
            "도로명주소·지번주소·우편번호·영문주소를 표로 정리한다. 결과가 없으면 '찾지 못함'만 출력한다.")
    n, e = chain(s, i, j, a, out())
    add("주소 정규화 (도로명·지번·우편번호·영문)", "사람이 대충 적은 주소를 행정안전부 정본 주소로 바꿉니다.",
        "data", ["주소", "우편번호", "공공데이터"], n, e)


def t_juso_batch():
    # 여기서는 반복이 **진짜로 필요하다** — jusoNode 가 주소 한 건씩만 조회한다.
    # 그래서 입력을 JSON 배열로 받아 jsonParserNode 로 실제 목록을 만들어 분배기에 넣는다.
    # 줄바꿈 텍스트를 그대로 주면 분배기가 한 번만 돌고 jusoNode 가 통짜 문자열을 받는다
    # (2026-08-31 실제로 그렇게 나가 있었다). 텍스트를 줄 단위로 쪼개는 노드가 생기면
    # 그때 입력 형식을 다시 사람 친화적으로 되돌릴 것.
    s = start()
    i = ask("정리할 주소 목록 (JSON 배열)",
            '["부산광역시 금정구 부산대학로63번길 2", "서울특별시 중구 세종대로 110"]')
    parse = N("jsonParserNode", mode="parse")
    d = N("distributorNode")
    j = N("jusoNode", keyword="", count=1)
    a = llm("입력은 도로명주소 검색 결과다. 도로명주소와 우편번호만 한 줄로 출력한다.")
    o = out()
    nodes = [s, i, parse, d, j, a, o]
    # 반복 안에서 outputNode 에 닿으면 첫 항목만 처리하고 끝난다 — 'done' 으로 빠져나간다.
    edges = [link(s, i), link(i, parse), link(parse, d), link(d, j), link(j, a),
             link(d, o, source_handle="done")]
    add("주소 목록 일괄 정리", "주소 목록(JSON 배열)을 한 건씩 도로명주소로 조회해 정리해 줍니다.",
        "data", ["주소", "일괄처리", "공공데이터"], nodes, edges)


def t_crawl_to_hwpx():
    s, i = start(), ask("기사 주소", "https://example.com/news/1")
    c = N("webCrawlerNode", url="", output="text", maxChars=8000, respectRobots=True)
    a = llm("입력은 기사 본문이다. 아래 JSON 하나만 출력한다 — 설명을 붙이지 않는다.\n"
            '{"title":"보고서 제목","blocks":[{"type":"heading","text":"소제목"},'
            '{"type":"paragraph","text":"내용"}]}\n기사에 없는 사실은 쓰지 않는다.')
    h = N("hwpxDocumentNode", mode="create", output_path="기사요약.hwpx")
    n, e = chain(s, i, c, a, h, out())
    add("기사 URL → 한글 요약 보고서", "기사 주소 하나로 본문만 골라 읽어 한글 문서를 만듭니다.",
        "document", ["크롤링", "한글", "요약"], n, e)


def t_crawl_links():
    s, i = start(), ask("목록 페이지 주소", "https://example.com/notice")
    c = N("webCrawlerNode", url="", output="links", maxChars=5000, respectRobots=True)
    a = llm("입력은 페이지의 링크 목록 JSON 이다. 공지·게시글로 보이는 링크만 골라 "
            "제목과 주소를 표로 정리한다. 메뉴·로그인·푸터 링크는 제외한다.")
    n, e = chain(s, i, c, a, out())
    add("목록 페이지에서 게시글 링크만 추리기", "목록 페이지의 링크를 모아 실제 게시글만 골라 줍니다.",
        "data", ["크롤링", "링크", "수집"], n, e)


def t_crawl_watch_notify():
    s = sched("0 * * * *")
    c = N("webCrawlerNode", url="https://example.com/notice", output="structured",
          maxChars=4000, respectRobots=True)
    a = llm("입력은 페이지 구조화 결과다. 제목과 발행일만 뽑아 한 줄로 출력한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(s, c, a, k, out())
    add("공지 페이지 변경 감시 → 카카오 알림", "정한 페이지를 한 시간마다 읽어 제목과 발행일을 알려 줍니다.",
        "notification", ["크롤링", "감시", "카카오"], n, e)


def t_hwpx_inspect():
    s = start()
    h = N("hwpxDocumentNode", mode="inspect")
    a = llm("입력은 한글 문서 검사 결과다. 어떤 자리표시자가 있고 몇 개를 채워야 하는지 "
            "사람이 읽기 좋게 정리한다.")
    n, e = chain(s, h, a, out())
    add("한글 서식 자리표시자 점검", "한글 문서에 어떤 빈칸이 있는지 훑어 알려 줍니다.",
        "document", ["한글", "hwpx", "서식"], n, e)


def t_naver_competitor():
    s = sched("0 8 * * 1")
    q1 = N("naverSearchNode", mode="blog", query="{{our_brand}}", display=20, sort="date")
    q2 = N("naverSearchNode", mode="cafe_article", query="{{competitor}}", display=20, sort="date")
    m = N("mergeNode")
    a = llm("입력은 우리 브랜드와 경쟁사에 대한 글 모음이다. 각각에서 반복되는 이야기를 "
            "3가지씩 뽑고 차이를 한 문단으로 정리한다. 근거가 된 글 제목을 붙인다.")
    nodes = [s, q1, q2, m, a, out()]
    edges = [link(s, q1), link(s, q2), link(q1, m), link(q2, m), link(a, nodes[-1]), link(m, a)]
    add("주간 브랜드·경쟁사 여론 비교", "매주 월요일 우리 브랜드와 경쟁사 언급을 모아 차이를 정리합니다.",
        "content", ["네이버", "브랜드", "주간"], nodes, edges)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
