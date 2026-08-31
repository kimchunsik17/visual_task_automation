"""url_guard 의 '예의' 계층 — robots.txt, 최소 간격, 일일 상한 (계획 §6.5).

`test_url_guard.py` 가 **안전**(SSRF·크기·리다이렉트)을 지킨다면 이 파일은 **부하**를 지킨다.
아카라이브 규정 8번이 금지하는 것은 크롤링 자체가 아니라 "서버에 부하를 주는" 크롤링이라,
부하를 주지 않는다는 것이 코드로 증명돼야 한다.

네트워크에 나가지 않는다. `requests.get` 과 시계를 갈아 끼운다.
"""

from __future__ import annotations

import types

import pytest

import url_guard

URL = "https://site.example/page"


class _FakeResponse:
    def __init__(self, status=200, text="", body=b"<html><body><p>ok</p></body></html>",
                 headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self._body = body

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers

    is_permanent_redirect = False

    def iter_content(self, size):
        yield self._body

    def close(self):
        pass


class _FakeClock:
    """진짜로 자지 않는다. 잠든 만큼 시계를 앞으로 민다."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def net(monkeypatch):
    """robots.txt 와 본문 응답을 지정할 수 있는 가짜 네트워크."""
    import requests

    state = types.SimpleNamespace(
        robots=_FakeResponse(404),      # 기본은 robots 없음 = 전부 허용
        page=_FakeResponse(200),
        calls=[],
    )

    def fake_get(url, **kwargs):
        state.calls.append(url)
        return state.robots if url.endswith("/robots.txt") else state.page

    monkeypatch.setattr(requests, "get", fake_get)
    # DNS 를 타지 않는다. 안전 검사는 다른 파일에서 본다.
    monkeypatch.setattr(url_guard, "_resolve", lambda host: ["93.184.216.34"])
    clock = _FakeClock()
    monkeypatch.setattr(url_guard, "time", clock)
    state.clock = clock
    url_guard.reset_politeness_state()
    yield state
    url_guard.reset_politeness_state()


def _robots(body: str, status: int = 200) -> _FakeResponse:
    return _FakeResponse(status, text=body)


# ── 1. robots.txt 를 지킨다 ─────────────────────────────────────────────

def test_disallow된_경로는_요청하지_않는다(net):
    net.robots = _robots("User-agent: *\nDisallow: /page")
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "ROBOTS_DISALLOWED"
    # robots.txt 만 받고 본문은 **가지 않았다**.
    assert net.calls == ["https://site.example/robots.txt"]


def test_allow된_경로는_통과한다(net):
    net.robots = _robots("User-agent: *\nDisallow: /admin")
    assert "ok" in url_guard.fetch_text(URL)
    assert net.calls[-1] == URL


def test_전체_disallow도_막는다(net):
    net.robots = _robots("User-agent: *\nDisallow: /")
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "ROBOTS_DISALLOWED"


def test_robots가_없으면_허용이다(net):
    """RFC 9309: 4xx 는 '규칙이 없다' 이므로 전부 허용."""
    net.robots = _FakeResponse(404)
    assert "ok" in url_guard.fetch_text(URL)


def test_robots를_못_읽으면_거부한다(net):
    """5xx 는 '알 수 없다' 다. 허용으로 두면 사이트가 불안정할 때 우리가 가장 세게 때린다."""
    net.robots = _FakeResponse(500)
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "ROBOTS_DISALLOWED"


def test_robots_요청이_실패해도_거부한다(net, monkeypatch):
    import requests

    def boom(url, **kwargs):
        if url.endswith("/robots.txt"):
            raise OSError("네트워크 오류")
        return net.page

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "ROBOTS_DISALLOWED"


def test_robots를_매번_받지_않는다(net):
    net.robots = _robots("User-agent: *\nDisallow: /admin")
    url_guard.fetch_text(URL)
    url_guard.fetch_text("https://site.example/other")
    assert net.calls.count("https://site.example/robots.txt") == 1


def test_respect_robots를_끄면_받지도_않는다(net):
    net.robots = _robots("User-agent: *\nDisallow: /")
    assert "ok" in url_guard.fetch_text(URL, respect_robots=False)
    assert "https://site.example/robots.txt" not in net.calls


# ── 2. 같은 호스트에 연달아 때리지 않는다 ───────────────────────────────

def test_연속_요청_사이에_최소_간격을_둔다(net):
    url_guard.fetch_text(URL)
    url_guard.fetch_text(URL)
    assert net.clock.slept, "두 번째 요청이 곧바로 나갔다"
    assert sum(net.clock.slept) >= url_guard.MIN_HOST_INTERVAL - 1e-9


def test_충분히_지났으면_기다리지_않는다(net):
    url_guard.fetch_text(URL)
    net.clock.now += url_guard.MIN_HOST_INTERVAL * 3
    url_guard.fetch_text(URL)
    assert net.clock.slept == []


def test_다른_호스트는_서로_기다리지_않는다(net):
    url_guard.fetch_text(URL)
    url_guard.fetch_text("https://other.example/page")
    assert net.clock.slept == []


def test_crawl_delay가_더_크면_그것을_따른다(net):
    net.robots = _robots("User-agent: *\nCrawl-delay: 5")
    url_guard.fetch_text(URL)
    url_guard.fetch_text(URL)
    assert sum(net.clock.slept) >= 5


def test_crawl_delay가_터무니없으면_기다리지_말고_거부한다(net):
    """1분을 자며 워커를 붙잡느니 '이 사이트는 대상이 아니다' 라고 말하는 편이 낫다."""
    net.robots = _robots(f"User-agent: *\nCrawl-delay: {url_guard.MAX_HOST_INTERVAL + 10:.0f}")
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "CRAWL_DELAY_TOO_LONG"
    assert net.clock.slept == []


# ── 3. 하루 상한 ────────────────────────────────────────────────────────

class _FakeDb:
    pass


def test_db를_주면_예산을_쓴다(net, monkeypatch):
    import rate_limit

    seen = []
    monkeypatch.setattr(rate_limit, "enforce",
                        lambda db, subject, action, **kw: seen.append((subject, action)))
    url_guard.fetch_text(URL, db=_FakeDb())
    assert seen == [("host:site.example", "crawl.fetch")]


def test_예산_주체는_사용자가_아니라_호스트다(net, monkeypatch):
    """사용자별로 세면 사용자가 늘수록 상대 서버가 받는 총량이 늘어난다."""
    import rate_limit

    seen = []
    monkeypatch.setattr(rate_limit, "enforce",
                        lambda db, subject, action, **kw: seen.append(subject))
    url_guard.fetch_text(URL, db=_FakeDb())
    assert seen[0].startswith("host:")


def test_상한을_넘으면_요청하지_않는다(net, monkeypatch):
    import rate_limit

    def over(db, subject, action, **kw):
        raise rate_limit.RateLimited(action, 500, 86400, 3600)

    monkeypatch.setattr(rate_limit, "enforce", over)
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL, db=_FakeDb())
    assert exc.value.reason == "HOST_DAILY_LIMIT"
    assert URL not in net.calls, "상한을 넘었는데 요청이 나갔다"


def test_상한에_걸릴_요청_때문에_잠들지_않는다(net, monkeypatch):
    """예산을 먼저 쓰고 나서 기다린다 — 순서가 반대면 거부할 요청을 위해 잔다."""
    import rate_limit

    url_guard.fetch_text(URL)          # 직전 요청 시각을 남긴다
    monkeypatch.setattr(rate_limit, "enforce", lambda *a, **k: (_ for _ in ()).throw(
        rate_limit.RateLimited("crawl.fetch", 500, 86400, 3600)))
    net.clock.slept.clear()
    with pytest.raises(url_guard.UrlBlocked):
        url_guard.fetch_text(URL, db=_FakeDb())
    assert net.clock.slept == []


def test_crawl_fetch_한도가_등록돼_있다():
    import rate_limit

    assert "crawl.fetch" in rate_limit.DEFAULT_RULES
    limit, window = rate_limit.DEFAULT_RULES["crawl.fetch"]
    assert window == 86400 and 0 < limit <= 2000


# ── 4. 사이트가 그만하라면 그만한다 ─────────────────────────────────────

@pytest.mark.parametrize("status", [429, 503])
def test_throttle_응답에_재시도하지_않는다(net, status):
    """부하를 줄이자는 장치가 재시도로 부하를 늘리면 앞뒤가 안 맞는다."""
    net.page = _FakeResponse(status)
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text(URL)
    assert exc.value.reason == "SITE_THROTTLED"
    assert net.calls.count(URL) == 1


# ── 5. 우리를 숨기지 않는다 ─────────────────────────────────────────────

def test_브라우저인_척하지_않는다():
    """상대가 우리를 식별하고 차단할 수 있어야 한다. 그게 robots 를 지키는 것의 짝이다."""
    ua = url_guard.USER_AGENT
    assert "WorkflowAI" in ua and "http" in ua
    for browser in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert browser not in ua


def test_안전_검사가_예의보다_먼저다(net):
    """robots 가 허용해도 내부 주소는 못 간다 — 순서가 바뀌면 SSRF 검사 전에 요청이 나간다."""
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.fetch_text("http://169.254.169.254/latest/meta-data/")
    assert exc.value.reason == "PRIVATE_ADDRESS"
    assert net.calls == []


# ── 6. 노드가 실제로 예산을 넘겨주는가 ──────────────────────────────────
#
# `fetch_text(db=None)` 이면 일일 상한이 **조용히** 없어진다. 소리 없이 없어지는 안전장치가
# 가장 나쁘므로, 생성 코드가 db 를 넘긴다는 사실을 여기서 붙들어 둔다.

def _source(data):
    from graph import compile_workflow

    return compile_workflow(
        [{"id": "c1", "type": "webCrawlerNode", "data": data, "position": {"x": 0, "y": 0}}], [])


def test_생성_코드가_db를_넘긴다():
    assert "db=db" in _source({"url": "https://example.com"})


def test_생성_코드가_robots를_기본으로_지킨다():
    assert "respect_robots=True" in _source({"url": "https://example.com"})


def test_robots를_끄는_것은_명시적인_선택이다():
    assert "respect_robots=False" in _source({"url": "https://example.com", "respectRobots": False})


@pytest.mark.parametrize("output,expected", [
    ("text", "web_extract.as_text("),
    ("structured", "_json.dumps(_page_c1"),
    ("links", "_page_c1['links']"),
])
def test_출력_형식이_생성_코드에_반영된다(output, expected):
    assert expected in _source({"url": "https://example.com", "output": output})


def test_알_수_없는_출력_형식은_text로_떨어진다():
    assert "web_extract.as_text(" in _source({"url": "https://example.com", "output": "무엇"})


@pytest.mark.parametrize("given,expected", [
    (3000, 3000), (0, 5000), (None, 5000), ("", 5000),
    (10, 200), (999999, 50000), ("abc", 5000),
])
def test_maxChars가_범위_안으로_정리된다(given, expected):
    assert f"max_chars={expected})" in _source({"url": "https://example.com", "maxChars": given})


# ── 7. 노드 하나를 끝까지 돌려본다 ──────────────────────────────────────
#
# 생성기·url_guard·web_extract 가 각각 맞아도 이어 붙였을 때 틀릴 수 있다. 여기서는 실제
# 워크플로우를 컴파일해 실행하고, 사용자가 결과로 보는 문자열까지 확인한다.
#
# 로컬 HTTP 서버로는 이 시험을 할 수 없다 — `url_guard` 가 127.0.0.1 을 막기 때문이다.
# 막는 것이 맞으므로 서버 대신 `requests.get` 을 갈아 끼운다.

_PAGE = """<html lang="ko"><head>
  <meta property="og:title" content="오늘의 뉴스">
  <meta property="article:published_time" content="2026-08-30T09:00:00+09:00">
</head><body>
  <nav><a href="/login">로그인</a></nav>
  <article><h1>오늘의 뉴스</h1><p>본문 문장입니다.</p>
    <a href="/detail/1">자세히</a></article>
  <footer>이용약관</footer>
</body></html>"""


@pytest.fixture
def live(net):
    net.page = _FakeResponse(200, body=_PAGE.encode("utf-8"))
    return net


def _run(data):
    from graph import run_workflow

    nodes = [{"id": "c1", "type": "webCrawlerNode", "data": data, "position": {"x": 0, "y": 0}},
             {"id": "o1", "type": "outputNode", "data": {}, "position": {"x": 200, "y": 0}}]
    edges = [{"id": "e1", "source": "c1", "target": "o1"}]
    result, _usage, _logs = run_workflow(nodes, edges)
    return str(result)


def test_기본_출력에_제목과_본문이_들어간다(live):
    out = _run({"url": URL})
    assert "제목: 오늘의 뉴스" in out
    assert "본문 문장입니다." in out


def test_기본_출력에_메뉴와_푸터가_없다(live):
    """예전 구현이 그대로 넘기던 것들이다."""
    out = _run({"url": URL})
    assert "로그인" not in out and "이용약관" not in out


def test_structured는_JSON이다(live):
    import json

    parsed = json.loads(_run({"url": URL, "output": "structured"}))
    assert parsed["title"] == "오늘의 뉴스"
    assert parsed["publishedAt"] == "2026-08-30T09:00:00+09:00"


def test_links는_절대주소_목록이다(live):
    import json

    links = json.loads(_run({"url": URL, "output": "links"}))
    assert "https://site.example/detail/1" in [l["url"] for l in links]


def test_robots가_막으면_사용자에게_이유가_보인다(live):
    live.robots = _robots("User-agent: *\nDisallow: /")
    out = _run({"url": URL})
    assert "robots.txt" in out
    assert "본문 문장입니다." not in out, "막았는데 내용이 나왔다"


def test_실패해도_워크플로우가_멈추지_않는다(live, monkeypatch):
    """이 노드의 오랜 계약이다 — 실패는 문자열로 하류에 전달된다."""
    import requests

    monkeypatch.setattr(requests, "get", lambda url, **kw: (_ for _ in ()).throw(OSError("끊김")))
    out = _run({"url": URL})
    assert out and "Traceback" not in out
