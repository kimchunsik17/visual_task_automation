"""web_extract 회귀 테스트 (한국형 노드 계획 §6.5).

이 파일이 지키는 문장:

  1. **제목과 본문이 구분된다.** 예전 `get_text(separator=' ')` 는 이걸 못 했다.
  2. **네비게이션·푸터·스크립트가 본문에 섞이지 않는다.** 5,000자 예산을 메뉴가 먹지 않는다.
  3. **없는 것은 지어내지 않는다.** 발행일을 잘못 채우면 없는 것보다 나쁘다.
  4. **네트워크에 나가지 않는다.** 그래서 마크업이 바뀌어 깨지는 것을 여기서 재현할 수 있다.
"""

from __future__ import annotations

import pytest

import web_extract

ARTICLE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <title>사이트이름 :: 기사 제목입니다</title>
  <meta property="og:title" content="기사 제목입니다">
  <meta name="description" content="기사를 한 줄로 줄인 설명.">
  <meta property="article:published_time" content="2026-08-30T09:00:00+09:00">
  <meta name="author" content="김기자">
  <link rel="canonical" href="/news/12345">
  <script>var tracking = {id: 'GA-1'};</script>
  <style>.ad { display: none }</style>
</head>
<body>
  <header><nav><a href="/login">로그인</a><a href="/join">회원가입</a><a href="/">홈</a></nav></header>
  <article>
    <h1>기사 제목입니다</h1>
    <p>첫 번째 문단입니다.</p>
    <p>두 번째 문단입니다. <a href="https://example.org/ref">참고 링크</a></p>
  </article>
  <aside class="ad">광고 영역 텍스트</aside>
  <footer>이용약관 개인정보처리방침 © 2026 사이트이름</footer>
</body>
</html>"""


@pytest.fixture
def page():
    return web_extract.extract(ARTICLE, url="https://news.example.com/news/12345")


# ── 1. 무엇이 제목인지 안다 ─────────────────────────────────────────────

def test_og_title을_title_태그보다_먼저_쓴다(page):
    """`<title>` 에는 사이트 이름이 붙는다 — og:title 이 더 깨끗하다."""
    assert page["title"] == "기사 제목입니다"
    assert "사이트이름" not in page["title"]


def test_og_title이_없으면_title_태그를_쓴다():
    html = "<html><head><title>제목만 있다</title></head><body><p>본문</p></body></html>"
    assert web_extract.extract(html, url="https://e.com")["title"] == "제목만 있다"


def test_둘_다_없으면_h1을_쓴다():
    html = "<html><body><h1>큰 제목</h1><p>본문</p></body></html>"
    assert web_extract.extract(html, url="https://e.com")["title"] == "큰 제목"


def test_아무것도_없으면_None이다():
    """지어내지 않는다."""
    assert web_extract.extract("<html><body><p>본문</p></body></html>")["title"] is None


# ── 2. 본문에 껍데기가 섞이지 않는다 ────────────────────────────────────

def test_본문에_문단이_들어간다(page):
    assert "첫 번째 문단입니다." in page["text"]
    assert "두 번째 문단입니다." in page["text"]


@pytest.mark.parametrize("junk", ["로그인", "회원가입", "이용약관", "개인정보처리방침",
                                  "광고 영역 텍스트", "tracking", "GA-1", "display: none"])
def test_껍데기가_본문에_없다(page, junk):
    """예전 구현은 이걸 전부 본문으로 넘겼다."""
    assert junk not in page["text"]


def test_문단이_한_줄에_붙지_않는다(page):
    """`separator=' '` 로 합치면 제목과 첫 문장이 한 줄이 된다 — LLM 이 경계를 못 본다."""
    assert "기사 제목입니다\n첫 번째 문단입니다." in page["text"]


def test_article이_없어도_가장_긴_덩어리를_고른다():
    html = """<html><body>
      <nav>메뉴 하나 둘 셋</nav>
      <div class="wrap"><div class="post">%s</div></div>
      <footer>푸터</footer></body></html>""" % ("본문 문장이 길게 이어집니다. " * 40)
    result = web_extract.extract(html, url="https://e.com")
    assert "본문 문장이 길게 이어집니다." in result["text"]


# ── 3. 메타데이터 ───────────────────────────────────────────────────────

def test_발행일과_작성자를_찾는다(page):
    assert page["publishedAt"] == "2026-08-30T09:00:00+09:00"
    assert page["byline"] == "김기자"


def test_canonical을_절대주소로_바꾼다(page):
    """`/news/12345` 는 그대로 두면 어디를 가리키는지 알 수 없다."""
    assert page["canonicalUrl"] == "https://news.example.com/news/12345"


def test_time_태그도_본다():
    html = '<html><body><time datetime="2026-01-02T03:04:05Z">언제</time><p>본문</p></body></html>'
    assert web_extract.extract(html)["publishedAt"] == "2026-01-02T03:04:05Z"


def test_날짜꼴이_아닌_time은_받지_않는다():
    """`<time datetime="PT5M">` 같은 것은 발행일이 아니다."""
    html = '<html><body><time datetime="PT5M">5분</time><p>본문</p></body></html>'
    assert web_extract.extract(html)["publishedAt"] is None


def test_발행일이_없으면_None이다():
    assert web_extract.extract("<html><body><p>본문</p></body></html>")["publishedAt"] is None


def test_언어를_읽는다(page):
    assert page["lang"] == "ko"


# ── 4. 링크 ─────────────────────────────────────────────────────────────

def test_상대주소를_절대주소로_바꾼다(page):
    urls = [link["url"] for link in page["links"]]
    assert "https://news.example.com/login" in urls
    assert "https://example.org/ref" in urls


def test_링크_텍스트가_함께_온다(page):
    ref = next(l for l in page["links"] if l["url"] == "https://example.org/ref")
    assert ref["text"] == "참고 링크"


@pytest.mark.parametrize("href", ["#top", "javascript:void(0)", "mailto:a@b.c",
                                  "tel:010-0000-0000", "data:text/html,x"])
def test_따라갈_수_없는_링크는_빼다(href):
    html = f'<html><body><a href="{href}">x</a></body></html>'
    assert web_extract.extract(html, url="https://e.com")["links"] == []


def test_같은_주소는_한_번만_담는다():
    html = '<html><body><a href="/a">1</a><a href="/a">2</a><a href="/a#b">3</a></body></html>'
    assert len(web_extract.extract(html, url="https://e.com")["links"]) == 1


def test_링크_수에_상한이_있다():
    html = "<html><body>" + "".join(f'<a href="/p{i}">{i}</a>' for i in range(500)) + "</body></html>"
    assert len(web_extract.extract(html, url="https://e.com", max_links=10)["links"]) == 10


def test_네비게이션_링크도_남는다(page):
    """링크는 본문 후보를 고르기 **전에** 모은다 — 목록 페이지에서 상세로 넘어가려면 필요하다."""
    assert any(l["url"].endswith("/login") for l in page["links"])


# ── 5. 자르기 ───────────────────────────────────────────────────────────

def test_상한을_넘으면_자르고_알린다():
    html = "<html><body><article><p>" + ("가" * 9000) + "</p></article></body></html>"
    result = web_extract.extract(html, url="https://e.com", max_chars=1000)
    assert len(result["text"]) == 1000
    assert result["truncated"] is True
    assert result["textLength"] > 1000


def test_상한_안이면_자르지_않는다(page):
    assert page["truncated"] is False
    assert len(page["text"]) == page["textLength"]


def test_as_text가_머리말을_붙인다(page):
    text = web_extract.as_text(page)
    assert text.startswith("제목: 기사 제목입니다")
    assert "발행: 2026-08-30" in text and "작성: 김기자" in text
    assert "첫 번째 문단입니다." in text


def test_as_text는_잘렸다는_사실을_알린다():
    html = "<html><body><article><p>" + ("나" * 5000) + "</p></article></body></html>"
    result = web_extract.extract(html, url="https://e.com", max_chars=300)
    assert "300자만 표시" in web_extract.as_text(result)


# ── 6. 망가진 입력 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("html", ["", "   ", "<html>", "not html at all",
                                  "<html><body>", "<<<>>>"])
def test_망가진_HTML에도_터지지_않는다(html):
    result = web_extract.extract(html, url="https://e.com")
    assert isinstance(result["text"], str)
    assert isinstance(result["links"], list)


def test_url이_없어도_동작한다():
    """`extract` 는 순수 함수다 — URL 없이도 텍스트는 나와야 한다."""
    result = web_extract.extract(ARTICLE)
    assert "첫 번째 문단입니다." in result["text"]
    assert result["url"] is None
