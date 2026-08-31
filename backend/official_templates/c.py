# -*- coding: utf-8 -*-
"""C묶음 — 미디어·콘텐츠(YouTube·RSS·이미지·포스터)."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def t_yt_new_video_digest():
    tr = N("youtubeTriggerNode", channelId="", maxResults=5)
    a = llm("입력은 채널의 새 영상이다. 제목과 설명으로 무엇을 다루는지 두 줄 요약을 쓴다. "
            "설명이 비어 있으면 '설명 없음'이라고 적고 추측하지 않는다.")
    n, e = chain(tr, a, out())
    add("채널 새 영상 요약 알림", "구독 채널에 새 영상이 올라오면 무엇을 다루는지 요약해 줍니다.",
        "content", ["youtube", "요약", "모니터링"], n, e)


def t_yt_to_blog_draft():
    s, i = start(), ask("영상 주소", "https://youtube.com/watch?v=xxxx")
    a = llm("입력은 영상 정보다. 블로그 글 초안을 쓴다 — 제목 한 줄, 소제목 3개, 각 소제목 아래 "
            "두 문단. 영상에 없는 내용은 쓰지 않는다.")
    n, e = chain(s, i, a, out())
    add("영상 → 블로그 글 초안", "영상 정보를 블로그 글 초안으로 바꿔 줍니다.",
        "content", ["youtube", "블로그", "초안"], n, e)


def t_rss_daily_digest():
    tr = N("rssTriggerNode", feedUrl="https://example.com/feed.xml", maxItems=20)
    a = llm("입력은 새 피드 항목이다. 주제별로 묶어 각 묶음에 한 줄 설명을 붙인다. "
            "항목이 없으면 '새 글 없음'만 출력한다.")
    n, e = chain(tr, a, out())
    add("RSS 새 글 주제별 정리", "구독 피드의 새 글을 주제별로 묶어 정리해 줍니다.",
        "content", ["rss", "요약", "피드"], n, e)


def t_rss_to_slack():
    tr = N("rssTriggerNode", feedUrl="https://example.com/feed.xml", maxItems=10)
    a = llm("입력은 새 글이다. 팀에 공유할 만한 것만 골라 제목과 왜 볼 만한지 한 줄로 쓴다. "
            "공유할 것이 없으면 '공유할 글 없음'만 출력한다.")
    sl = N("slackNode", channel="#general", text="")
    n, e = chain(tr, a, sl, out())
    add("RSS 새 글 → 슬랙 공유", "피드에서 팀에 쓸모 있는 글만 골라 슬랙에 올립니다.",
        "notification", ["rss", "슬랙", "공유"], n, e)


def t_rss_to_hwpx_weekly():
    tr = N("rssTriggerNode", feedUrl="https://example.com/feed.xml", maxItems=30)
    a = llm("입력은 이번 주 피드 항목이다. 아래 JSON 하나만 출력한다 — 설명을 붙이지 않는다.\n"
            '{"title":"주간 리뷰","blocks":[{"type":"heading","text":"주제"},{"type":"paragraph","text":"내용"}]}')
    h = N("hwpxDocumentNode", mode="create", output_path="주간리뷰.hwpx")
    n, e = chain(tr, a, h, out())
    add("RSS 주간 리뷰 → 한글 문서", "한 주 동안 모인 피드 글을 한글 리뷰 문서로 만듭니다.",
        "document", ["rss", "한글", "주간"], n, e)


def t_image_from_text():
    s, i = start(), ask("그림 설명", "가을 저녁 부산 광안대교")
    a = llm("입력을 이미지 생성 프롬프트로 다듬는다. 영어 한 문장으로만 출력하고 "
            "사람 얼굴·상표·글자는 넣지 않는다.")
    g = N("imageGenerationNode", action="generate", prompt="", size="1024x1024",
          model="gpt-5.6", quality="high", background="auto", outputFormat="png")
    n, e = chain(s, i, a, g, out())
    add("설명 한 줄 → 이미지 생성", "짧은 설명을 이미지 생성용 문장으로 다듬어 그림을 만듭니다.",
        "content", ["이미지", "생성"], n, e)


def t_poster_from_notice():
    s, i = start(), ask("공지 내용", "10월 5일 신입 환영회, 3층 대회의실 오후 6시")
    a = llm("입력을 포스터 문구로 다듬는다. 큰 제목 한 줄, 날짜·장소 한 줄, 안내 두 줄. "
            "없는 정보는 지어내지 않는다.")
    p = N("posterGeneratorNode", outputFormat="png", backgroundPreset="poster-05-layered-paper",
          width=1080, height=1350)
    n, e = chain(s, i, a, p, out())
    add("공지 → 안내 포스터", "공지 문장을 포스터 문구로 다듬어 이미지를 만듭니다.",
        "content", ["포스터", "이미지", "공지"], n, e)


def t_yt_new_to_notion():
    """`youtubeNode` 는 playlistId 가 필수라 템플릿에 담을 수 없다(사용자마다 다른 값이다).
    그래서 읽기는 트리거로 하고, 결과는 사용자 값이 필요 없는 곳으로 보낸다."""
    tr = N("youtubeTriggerNode", channelId="", maxResults=10)
    a = llm("입력은 채널의 새 영상이다. 제목·게시일·한 줄 요약을 표로 정리한다. "
            "설명이 비어 있으면 '설명 없음'이라고 적고 추측하지 않는다.")
    nt = N("notionNode", token="{{API_CENTER:notion}}", mode="create", databaseId="", title="")
    n, e = chain(tr, a, nt, out())
    add("새 영상 기록을 노션에 쌓기", "채널에 새 영상이 올라오면 요약해 노션 데이터베이스에 남깁니다.",
        "content", ["youtube", "노션", "기록"], n, e)


def t_content_calendar():
    s = sched("0 10 * * 1")
    q = N("naverSearchNode", mode="blog", query="{{분야}}", display=30, sort="date")
    a = llm("입력은 우리 분야의 최근 글이다. 아직 덜 다뤄진 주제 5개를 제안하고 "
            "각각 왜 비어 있다고 보는지 근거를 한 줄로 쓴다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="주제!A:B")
    n, e = chain(s, q, a, sh, out())
    add("주간 콘텐츠 주제 제안", "분야의 최근 글을 훑어 아직 덜 다뤄진 주제를 제안합니다.",
        "content", ["네이버", "기획", "주간"], n, e)


def t_crawl_to_image_prompt():
    s, i = start(), ask("기사 주소", "https://example.com/news/1")
    c = N("webCrawlerNode", url="", output="text", maxChars=4000, respectRobots=True)
    a = llm("입력은 기사다. 기사 분위기를 담은 삽화용 영어 프롬프트 한 문장만 출력한다. "
            "사람 얼굴·상표·글자는 넣지 않는다.")
    g = N("imageGenerationNode", action="generate", prompt="", size="1024x1024",
          model="gpt-5.6", quality="high", background="auto", outputFormat="png")
    n, e = chain(s, i, c, a, g, out())
    add("기사 → 삽화 자동 생성", "기사 본문을 읽어 어울리는 삽화를 만들어 줍니다.",
        "content", ["크롤링", "이미지", "삽화"], n, e)


def t_video_desc_writer():
    s, i = start(), ask("영상 주제", "리액트 훅 입문")
    a = llm("입력 주제로 유튜브 설명란을 쓴다 — 두 문단 소개, 타임스탬프 자리표시자 5줄, 해시태그 5개.")
    n, e = chain(s, i, a, out())
    add("영상 설명란 초안 작성", "주제 한 줄로 유튜브 설명란 초안을 만들어 줍니다.",
        "content", ["youtube", "초안"], n, e)


def t_multilang_post():
    s, i = start(), ask("원문", "신제품을 출시했습니다.")
    ko = llm("입력을 자연스러운 한국어 홍보 문구로 다듬는다. 과장하지 않는다.")
    en = llm("Rewrite the input as a concise English announcement. Do not exaggerate.")
    m = N("mergeNode")
    o = out()
    nodes = [s, i, ko, en, m, o]
    edges = [{"id": "e1", "source": s["id"], "target": i["id"], "sourceHandle": None, "targetHandle": None},
             {"id": "e2", "source": i["id"], "target": ko["id"], "sourceHandle": None, "targetHandle": None},
             {"id": "e3", "source": i["id"], "target": en["id"], "sourceHandle": None, "targetHandle": None},
             {"id": "e4", "source": ko["id"], "target": m["id"], "sourceHandle": None, "targetHandle": None},
             {"id": "e5", "source": en["id"], "target": m["id"], "sourceHandle": None, "targetHandle": None},
             {"id": "e6", "source": m["id"], "target": o["id"], "sourceHandle": None, "targetHandle": None}]
    add("공지 한국어·영어 동시 작성", "원문 하나로 한국어와 영어 안내문을 같이 만듭니다.",
        "content", ["번역", "공지"], nodes, edges)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
