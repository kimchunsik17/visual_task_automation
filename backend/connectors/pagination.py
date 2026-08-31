"""connectors/pagination.py — 목록 API 페이지 넘기기 (ADR-0007).

서비스마다 페이지를 넘기는 방식이 다르지만 실제로 쓰이는 형태는 몇 가지뿐이라, 노드마다
while 문을 새로 짜는 대신 정의 파일에 방식만 선언하게 한다.

    cursor : 응답 어딘가에 다음 커서가 들어 있다 (YouTube pageToken, Notion next_cursor)
    page   : 1,2,3... 페이지 번호를 올린다
    offset : offset/limit 을 더해 나간다

`maxPages` 를 반드시 둔다 — 상대 서비스가 커서를 잘못 돌려주면 무한 루프에 빠지고, 그건
워크플로우 하나가 실행 워커를 영구히 점유하는 형태로 나타난다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional

CURSOR = "cursor"
PAGE = "page"
OFFSET = "offset"


def value_at(payload: Any, path: Optional[str]) -> Any:
    """'a.b.c' 형태의 점 경로로 중첩 값을 꺼낸다. 경로가 없으면 payload 자체."""
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


@dataclass(frozen=True)
class PaginationConfig:
    style: str = CURSOR
    # 다음 페이지를 요청할 때 쓸 파라미터 이름
    cursor_param: str = "pageToken"
    # 응답에서 다음 커서를 찾을 경로
    cursor_path: str = "nextPageToken"
    # 응답에서 실제 항목 목록을 찾을 경로
    items_path: str = "items"
    page_param: str = "page"
    offset_param: str = "offset"
    limit_param: str = "limit"
    page_size: int = 50
    # 안전장치. 넘으면 조용히 자르지 않고 truncated 를 알린다.
    max_pages: int = 20
    max_items: Optional[int] = None

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "PaginationConfig":
        raw = raw or {}
        return cls(
            style=raw.get("style", CURSOR),
            cursor_param=raw.get("cursorParam", "pageToken"),
            cursor_path=raw.get("cursorPath", "nextPageToken"),
            items_path=raw.get("itemsPath", "items"),
            page_param=raw.get("pageParam", "page"),
            offset_param=raw.get("offsetParam", "offset"),
            limit_param=raw.get("limitParam", "limit"),
            page_size=raw.get("pageSize", 50),
            max_pages=raw.get("maxPages", 20),
            max_items=raw.get("maxItems"),
        )


@dataclass
class PaginationResult:
    items: List[Any]
    pages_fetched: int
    # 더 가져올 게 남았는데 한도 때문에 멈췄는지. 호출부가 사용자에게 알려야 한다 —
    # 잘린 목록을 전부인 것처럼 다루면 워크플로우가 조용히 일부만 처리한다.
    truncated: bool = False


def collect_pages(
    fetch: Callable[[Dict[str, Any]], Any],
    config: PaginationConfig = PaginationConfig(),
) -> PaginationResult:
    """`fetch(params)` 를 페이지마다 호출해 항목을 모은다.

    fetch 는 파싱된 응답(dict)을 돌려줘야 한다. HTTP 호출과 오류 정규화는 호출부(session)의
    몫이고, 여기서는 페이지를 넘기는 규칙만 다룬다.
    """
    items: List[Any] = []
    cursor: Optional[str] = None
    pages = 0
    truncated = False

    while pages < config.max_pages:
        params: Dict[str, Any] = {config.limit_param: config.page_size}
        if config.style == CURSOR:
            if cursor:
                params[config.cursor_param] = cursor
        elif config.style == PAGE:
            params = {config.page_param: pages + 1, config.limit_param: config.page_size}
        elif config.style == OFFSET:
            params = {config.offset_param: len(items), config.limit_param: config.page_size}

        payload = fetch(params)
        pages += 1

        page_items = value_at(payload, config.items_path)
        if not isinstance(page_items, list):
            page_items = []
        items.extend(page_items)

        if config.max_items is not None and len(items) >= config.max_items:
            truncated = len(items) > config.max_items or bool(value_at(payload, config.cursor_path))
            items = items[: config.max_items]
            break

        if config.style == CURSOR:
            cursor = value_at(payload, config.cursor_path)
            if not cursor:
                break
        else:
            # 번호/오프셋 방식은 "받은 항목이 요청한 크기보다 적으면 마지막 페이지"로 본다.
            if len(page_items) < config.page_size:
                break
    else:
        # while 을 max_pages 로 빠져나온 경우 — 아직 남아 있을 수 있다.
        truncated = True

    return PaginationResult(items=items, pages_fetched=pages, truncated=truncated)
