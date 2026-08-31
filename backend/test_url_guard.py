"""url_guard 와 webCrawlerNode 의 URL 안전 게이트 테스트.

한국형 서비스 노드 계획 §6.5 선택지 A / "Phase 0 이전" 5번.

이 노드는 `data.url` 이 비면 **직전 노드 출력을 그대로 URL 로 쓴다.** 즉 LLM 이 만든 문자열이
곧 요청 대상이 되므로, 사설·링크로컬 주소 차단은 있으면 좋은 게 아니라 없으면 SSRF 다.
"""

import pytest

import url_guard
from graph import run_workflow


def _node(node_id, node_type, data=None):
    return {"id": node_id, "type": node_type, "data": data or {}, "position": {"x": 0, "y": 0}}


def _edge(edge_id, source, target):
    return {"id": edge_id, "source": source, "target": target}


# ── check_url: 무엇을 막고 무엇을 통과시키는가 ──────────────────────────

@pytest.mark.parametrize("url, reason", [
    ("http://169.254.169.254/latest/meta-data/", "PRIVATE_ADDRESS"),   # 클라우드 메타데이터
    ("http://127.0.0.1:8000/admin", "PRIVATE_ADDRESS"),
    ("http://localhost/", "PRIVATE_ADDRESS"),
    ("http://10.0.0.5/internal", "PRIVATE_ADDRESS"),
    ("http://192.168.1.1/", "PRIVATE_ADDRESS"),
    ("http://172.16.0.1/", "PRIVATE_ADDRESS"),
    ("http://[::1]/", "PRIVATE_ADDRESS"),
    ("http://0.0.0.0/", "PRIVATE_ADDRESS"),
    ("file:///etc/passwd", "BAD_SCHEME"),
    ("gopher://example.com/", "BAD_SCHEME"),
    ("", "EMPTY"),
])
def test_내부_주소와_비HTTP_scheme은_거부한다(url, reason):
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.check_url(url)
    assert exc.value.reason == reason


@pytest.mark.parametrize("url", [
    "https://gall.dcinside.com/board/lists",   # 서브도메인도 같이 걸려야 한다
    "https://www.dcinside.com/",
    "https://www.fmkorea.com/best",
])
def test_제휴_전_커뮤니티는_범용_크롤러로도_막는다(url):
    """전용 Trigger 를 카탈로그에서 감추는 것만으로는 §11 비목표가 성립하지 않는다."""
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.check_url(url)
    assert exc.value.reason == "COMMUNITY_PARTNERSHIP_REQUIRED"


@pytest.mark.parametrize("url", [
    "https://example.com/page",
    "https://bbs.ruliweb.com/community/board/300143/rss",   # 공식 RSS 는 통과한다
])
def test_공개_주소는_통과한다(url):
    normalized, host = url_guard.check_url(url)
    assert normalized == url and host


def test_차단_사유가_사용자에게_보여줄_수_있는_문구다():
    with pytest.raises(url_guard.UrlBlocked) as exc:
        url_guard.check_url("http://169.254.169.254/")
    message = str(exc.value)
    assert "내부 주소" in message
    # 스택이나 내부 경로가 새지 않는다
    assert "Traceback" not in message and "/home/" not in message


# ── webCrawlerNode: 실제 실행 경로에서도 막히는가 ───────────────────────

def _crawl(url_value, *, from_previous=False):
    if from_previous:
        nodes = [_node("v1", "valueNode", {"value": url_value}),
                 _node("c1", "webCrawlerNode", {"url": ""}),
                 _node("c2", "outputNode")]
        edges = [_edge("e0", "v1", "c1"), _edge("e1", "c1", "c2")]
    else:
        nodes = [_node("c1", "webCrawlerNode", {"url": url_value}), _node("c2", "outputNode")]
        edges = [_edge("e1", "c1", "c2")]
    result, _usage, _logs = run_workflow(nodes, edges)
    return str(result)


# 거부 문구의 접두어가 아니라 **사유**를 본다. 접두어는 예의 계층(robots·일일 상한)이 생기면서
# "차단된 주소입니다" 로 뭉뚱그릴 수 없게 됐고, 어차피 확인해야 하는 것은 "왜" 다.

def test_노드가_내부_주소를_네트워크_이전에_거부한다():
    out = _crawl("http://169.254.169.254/latest/meta-data/")
    assert "내부 주소로는 요청할 수 없습니다" in out
    assert "meta-data" not in out.split("169.254.169.254 →")[-1], "응답 내용이 새어 나왔다"


def test_직전_노드가_만든_내부_주소도_거부한다():
    """가장 위험한 경로 — 여기가 뚫리면 LLM 출력이 곧 요청 대상이 된다."""
    assert "내부 주소로는 요청할 수 없습니다" in _crawl("http://127.0.0.1:22/", from_previous=True)


def test_노드가_제휴_전_커뮤니티를_거부한다():
    out = _crawl("https://gall.dcinside.com/board/lists")
    assert "자동 수집하지 않습니다" in out and "제휴" in out
