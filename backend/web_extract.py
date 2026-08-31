"""web_extract.py — HTML 한 장에서 쓸 만한 것만 뽑아낸다 (한국형 노드 계획 §6.5).

예전 `webCrawlerNode` 는 `soup.get_text(separator=' ')[:5000]` 한 줄이었다. 그 결과물은
**메뉴·광고·푸터가 본문과 한 덩어리로 붙은 5,000자**다. 하류 LLM 이 받는 것이

    로그인 회원가입 전체메뉴 뉴스 스포츠 ... 오늘의 주요 뉴스 제목입니다 기사 본문이 여기서...
    ... 관련기사 더보기 댓글 0 이용약관 개인정보처리방침 © 2026

이라면 "제목이 뭐냐" 는 질문에 답할 근거가 없다. 게다가 5,000자 예산의 절반을 네비게이션이
먹는다. 그래서 **구조를 먼저 복원하고** 자른다.

■ 순수 함수다

이 모듈은 네트워크에 나가지 않는다. 입력은 HTML 문자열, 출력은 dict 다. 그래서 실제 페이지를
받아 저장해 두고 회귀 테스트를 돌릴 수 있다 — 사이트가 마크업을 바꿔서 깨지는 것이 이런 코드의
가장 흔한 실패인데, 네트워크가 섞여 있으면 그 실패를 재현할 수가 없다.

■ 뽑는 것

    title         og:title → <title> → 첫 <h1>
    excerpt       og:description → meta[name=description]
    publishedAt   article:published_time → 여러 흔한 meta → <time datetime>
    byline        article:author → meta[name=author]
    canonicalUrl  link[rel=canonical] → og:url → 요청한 URL
    text          본문 후보 안의 블록 텍스트(줄바꿈 보존)
    links         절대 URL + 앵커 텍스트

없는 것은 `None` 이나 빈 값으로 둔다. **추측하지 않는다** — 발행일을 잘못 채우면 없는 것보다 나쁘다.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

DEFAULT_MAX_CHARS = 5000
DEFAULT_MAX_LINKS = 100

# 본문일 리 없는 것들. 지우고 시작한다.
_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "canvas",
              "iframe", "form", "nav", "header", "footer", "aside")

# 본문이 들어 있을 만한 곳. 앞에서부터 찾아 처음 걸리는 것을 쓴다.
_MAIN_SELECTORS = ("article", "main", "[role=main]", "#content", "#main",
                   ".article-body", ".post-content", ".entry-content")

# 줄을 바꿔야 읽히는 태그들. 이걸 안 하면 제목과 본문 첫 문장이 한 줄에 붙는다.
_BLOCK_TAGS = ("p", "div", "section", "li", "tr", "br", "h1", "h2", "h3", "h4",
               "h5", "h6", "blockquote", "pre", "figcaption", "td", "th")

_PUBLISHED_META = (
    ("property", "article:published_time"),
    ("property", "og:published_time"),
    ("property", "article:modified_time"),
    ("name", "article:published_time"),
    ("itemprop", "datePublished"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("name", "date"),
    ("name", "DC.date.issued"),
)

_AUTHOR_META = (
    ("property", "article:author"),
    ("name", "author"),
    ("itemprop", "author"),
    ("name", "twitter:creator"),
)


def _soup(html: str):
    from bs4 import BeautifulSoup

    # lxml 이 있으면 더 관대하게 고쳐 읽는다. 없으면 표준 파서로 떨어진다.
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _meta(soup, pairs) -> Optional[str]:
    """`(속성이름, 값)` 후보를 순서대로 보고 처음 찾은 content 를 돌려준다."""
    for attr, value in pairs:
        tag = soup.find("meta", attrs={attr: value})
        if tag:
            content = (tag.get("content") or "").strip()
            if content:
                return content
    return None


def _clean(text: str) -> str:
    """줄 안의 공백만 합치고 줄바꿈은 남긴다 — 문단 구분이 본문 이해에 쓸모가 있다."""
    lines = [re.sub(r"[ \t ​]+", " ", line).strip() for line in text.split("\n")]
    kept = [line for line in lines if line]
    # 같은 문구가 연달아 반복되면(메뉴 잔여물) 하나만 남긴다.
    out: List[str] = []
    for line in kept:
        if not out or out[-1] != line:
            out.append(line)
    return "\n".join(out)


def _block_text(node) -> str:
    """블록 태그 경계마다 줄바꿈을 넣어 텍스트를 만든다."""
    for tag in node.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return _clean(node.get_text())


def _pick_main(soup):
    """본문 후보를 고른다. 셀렉터로 못 찾으면 **글자가 가장 많은 컨테이너**로 떨어진다."""
    for selector in _MAIN_SELECTORS:
        try:
            found = soup.select_one(selector)
        except Exception:
            continue
        if found and len(found.get_text(strip=True)) >= 200:
            return found

    body = soup.body or soup
    best, best_len = body, 0
    for candidate in body.find_all(("div", "section", "td")):
        # 자식 div 가 많으면 본문이 아니라 레이아웃 컨테이너다.
        length = len(candidate.get_text(strip=True))
        if length > best_len and len(candidate.find_all("div", recursive=False)) <= 3:
            best, best_len = candidate, length
    # 후보가 body 전체의 4분의 1도 안 되면 신뢰하지 않고 body 를 쓴다.
    return best if best_len >= len(body.get_text(strip=True)) * 0.25 else body


def _links(soup, base_url: str, limit: int) -> List[Dict[str, str]]:
    """절대 URL 로 바꾼 링크. 같은 주소는 한 번만, http(s) 만."""
    seen, out = set(), []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).scheme not in ("http", "https"):
            continue
        absolute = absolute.split("#")[0]
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append({"url": absolute, "text": _clean(anchor.get_text())[:120]})
        if len(out) >= limit:
            break
    return out


def _published(soup) -> Optional[str]:
    found = _meta(soup, _PUBLISHED_META)
    if found:
        return found
    # <time datetime="..."> 는 meta 다음으로 흔하다. 값이 날짜꼴일 때만 받는다.
    for tag in soup.find_all("time"):
        value = (tag.get("datetime") or "").strip()
        if value and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value
    return None


def extract(html: str, *, url: str = "", max_chars: int = DEFAULT_MAX_CHARS,
            max_links: int = DEFAULT_MAX_LINKS) -> Dict[str, Any]:
    """HTML → 구조화된 dict. **네트워크에 나가지 않는다.**"""
    soup = _soup(html or "")

    # 링크는 본문 후보를 고르기 **전에** 모은다 — 네비게이션을 지우고 나면 사라지는 것이 많고,
    # "이 페이지에서 갈 수 있는 곳" 은 그 자체로 쓸모가 있다(목록 → 상세 순회).
    links = _links(soup, url, max_links) if url else _links(soup, "", max_links)

    title = _meta(soup, (("property", "og:title"), ("name", "twitter:title")))
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        title = _clean(h1.get_text()) if h1 else None

    excerpt = _meta(soup, (("property", "og:description"), ("name", "description"),
                           ("name", "twitter:description")))
    published_at = _published(soup)
    byline = _meta(soup, _AUTHOR_META)

    canonical = None
    link_tag = soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, list) else [v]))
    if link_tag and link_tag.get("href"):
        canonical = urljoin(url, link_tag["href"].strip()) if url else link_tag["href"].strip()
    if not canonical:
        canonical = _meta(soup, (("property", "og:url"),)) or (url or None)

    lang = None
    if soup.html and soup.html.get("lang"):
        lang = soup.html["lang"].strip() or None

    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    text = _block_text(_pick_main(soup))
    truncated = len(text) > max_chars

    return {
        "url": url or None,
        "canonicalUrl": canonical,
        "title": (title or "").strip() or None,
        "excerpt": (excerpt or "").strip() or None,
        "publishedAt": published_at,
        "byline": (byline or "").strip() or None,
        "lang": lang,
        "text": text[:max_chars],
        "textLength": len(text),
        "truncated": truncated,
        "links": links,
    }


def as_text(result: Dict[str, Any]) -> str:
    """구조화 결과를 사람·LLM 이 읽는 한 덩어리로. 머리말이 있어야 무엇이 제목인지 안다."""
    head = []
    if result.get("title"):
        head.append(f"제목: {result['title']}")
    if result.get("publishedAt"):
        head.append(f"발행: {result['publishedAt']}")
    if result.get("byline"):
        head.append(f"작성: {result['byline']}")
    if result.get("canonicalUrl"):
        head.append(f"출처: {result['canonicalUrl']}")
    body = result.get("text") or ""
    if result.get("truncated"):
        body += f"\n\n[본문 {result['textLength']}자 중 {len(body)}자만 표시]"
    return ("\n".join(head) + "\n\n" + body).strip() if head else body
