"""connectors/services/rss.py — RSS/Atom 새 항목 트리거의 실행부 (Wave 1, 우선 백로그 8번).

자격증명이 전혀 필요 없는 첫 트리거다 — Trigger·cursor·중복 제거 계약(ADR-0007/0008)을
가장 값싸게 검증하는 자리이기도 하다(로드맵 §4.7 Wave 1 선정 이유 그대로).

■ 중복 실행
  피드는 항상 "최근 N개"의 슬라이딩 윈도우를 통째로 돌려주므로, YouTube 처럼 게시 시각
  cursor 를 쓸 필요 없이 항목 id(guid/atom id/링크) 집합만 들고 다니면 된다. 첫 실행은
  기준점만 잡고 아무것도 통지하지 않는다(켜는 순간 과거 글 전부가 쏟아지는 것 방지).

■ 파싱
  RSS 2.0 과 Atom 을 xml.etree 로 직접 읽는다 — feedparser 같은 의존성을 더하지 않기
  위해서다. 필드는 노드가 실제로 쓰는 것(제목/링크/요약/게시 시각)만 뽑는다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "RSS"
TRIGGER_NODE_TYPE = "rssTriggerNode"

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


# 피드 서버가 봇으로 보고 막지 않게 브라우저형 UA 를 쓴다. 식별자는 뒤에 남겨 운영자가 우리 요청을 알아볼 수 있게 한다.
RSS_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WorkflowAI-RSS/1.0"


def _session(definition, **kwargs: Any) -> ConnectorSession:
    return definition.new_session(**kwargs)


def _text(element: Optional[ET.Element]) -> str:
    return (element.text or "").strip() if element is not None else ""


def parse_feed(xml_text: str) -> List[Dict[str, str]]:
    """RSS 2.0 또는 Atom 문서에서 항목 목록을 뽑는다. 항목 id 가 없으면 링크, 그것도 없으면
    제목을 식별자로 쓴다 — 셋 다 없는 항목은 중복 제거가 불가능하므로 버린다."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"피드를 XML로 해석하지 못했다: {exc}",
        ) from None

    items: List[Dict[str, str]] = []
    if root.tag == f"{_ATOM_NS}feed":
        for entry in root.findall(f"{_ATOM_NS}entry"):
            link = ""
            for candidate in entry.findall(f"{_ATOM_NS}link"):
                if candidate.get("rel") in (None, "alternate"):
                    link = candidate.get("href") or ""
                    break
            items.append({
                "id": _text(entry.find(f"{_ATOM_NS}id")) or link or _text(entry.find(f"{_ATOM_NS}title")),
                "title": _text(entry.find(f"{_ATOM_NS}title")),
                "link": link,
                "summary": _text(entry.find(f"{_ATOM_NS}summary")) or _text(entry.find(f"{_ATOM_NS}content")),
                "published_at": _text(entry.find(f"{_ATOM_NS}published")) or _text(entry.find(f"{_ATOM_NS}updated")),
            })
    else:
        channel = root.find("channel")
        if channel is None:
            raise ConnectorError(
                code=INVALID_REQUEST, service=SERVICE,
                detail="RSS(channel) 또는 Atom(feed) 형식이 아니다",
            )
        for item in channel.findall("item"):
            link = _text(item.find("link"))
            items.append({
                "id": _text(item.find("guid")) or link or _text(item.find("title")),
                "title": _text(item.find("title")),
                "link": link,
                "summary": _text(item.find("description")),
                "published_at": _text(item.find("pubDate")),
            })
    return [item for item in items if item["id"]]


CURSOR_VERSION = 1
#: 겹침 창. 피드는 항목이 밀려났다 돌아오기도 하고, 서버가 잠깐 적게 주기도 한다 —
#: 마지막 응답만 기억하면 그때마다 "새 글" 로 다시 알린다(계획 §2 불일치 12).
#: `naverSearchTriggerNode` 와 같은 방식이다.
SEEN_WINDOW = 300


def poll_new_items(
    definition,
    *,
    feed_url: str,
    cursor: Optional[Dict[str, Any]] = None,
    max_items: int = 10,
    start_mode: str = "baseline",
    since: Any = None,
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    """마지막 실행 이후 새로 등장한 항목만 돌려주고, 다음 실행에 쓸 cursor 를 함께 준다."""
    feed_url = (feed_url or "").strip()
    if not feed_url.startswith(("http://", "https://")):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="피드 주소는 http(s) URL이어야 한다",
        )
    session = session or _session(definition)
    cursor = cursor or {}

    # 브라우저형 User-Agent 를 명시한다 — 뽐뿌 등 국내 커뮤니티 피드는 python-requests 기본 UA 를
    # 403 으로 막는다(2026-09-05 실측: 기본 UA 403, Mozilla 계열 UA 200). Accept 도 피드 MIME 을 앞세운다.
    body = session.get(feed_url, headers={
        "User-Agent": RSS_USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    }).json()
    if not isinstance(body, str):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="피드 응답이 XML 문서가 아니다 (JSON 등 다른 형식)",
        )
    items = parse_feed(body)

    from .. import cursor as cursor_store

    # 정책은 `connectors/cursor.py` 한 곳에 있다 — 예전에는 이 함수와
    # `naver_search.poll_new_results` 가 같은 일을 각자 구현했고, 그래서 한쪽에서 고친 결함이
    # 다른 쪽에 오래 남아 있었다.
    try:
        picked = cursor_store.select_new(
            cursor, items, key="id", seen_field="seen_ids",
            window=SEEN_WINDOW, start_mode=start_mode, since=since,
            time_key="published_at", limit=max_items, version=CURSOR_VERSION)
    except cursor_store.CursorUnreadable as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from None

    return {
        "items": picked["items"],
        "cursor": picked["cursor"],
        "first_run": picked["first_run"],
        "feed_size": len(items),
        "pending": picked["pending"],
    }
