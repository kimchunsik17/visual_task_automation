"""connectors/services/naver_search.py — 네이버 블로그·카페글 검색 (한국형 노드 계획 §4.2).

■ 개발자센터가 아니라 NAVER API HUB 다

2026-06-25 이관으로 검색 API 가 네이버 클라우드로 옮겨갔다(계획 §4.0). 옛 코드를 베끼면
안 되는 지점이 셋이다.

    호스트   openapi.naver.com          → naverapihub.apigw.ntruss.com
    헤더     X-Naver-Client-Id/Secret   → X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
    경로     /v1/search/blog.json       → /search/v1/blog

위 셋은 2026-08-30 에 실제 키로 호출해 200 을 받아 확인했다.

■ 오류 응답이 두 가지 형태로 온다

게이트웨이가 막으면(401) `{"error": {"errorCode": ..., "message": ...}}` 이고, 검색 쪽이
거절하면(400) `{"errorMessage": ..., "errorCode": "SE01"}` 이다. 한 쪽만 보고 만들면 다른
쪽에서 사용자에게 빈 메시지가 간다.

■ 원문을 그대로 두지 않는다

네이버는 검색어에 `<b>` 태그를 씌워 돌려준다. 그대로 하류로 넘기면 LLM 프롬프트와 문서에
태그가 섞여 들어가므로 걷어낸 `title` 을 주고, 필요하면 볼 수 있게 `titleRaw` 를 남긴다.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from ..errors import AUTH_INVALID, INVALID_REQUEST, RATE_LIMITED, ConnectorError
from ..session import ConnectorSession

SERVICE = "네이버 검색"
BASE_URL = "https://naverapihub.apigw.ntruss.com/search/v1"

#: 노드 mode → HUB 경로. 여기 없는 mode 는 받지 않는다.
MODE_PATHS = {"blog": "blog", "cafe_article": "cafearticle"}

#: 한 번에 가져올 수 있는 개수. HUB 가 범위 밖이면 SE02 로 거절한다.
MIN_DISPLAY, MAX_DISPLAY = 1, 100
MAX_START = 1000

_TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: Any) -> str:
    """`<b>` 강조와 HTML entity 를 걷어낸다. 값이 없으면 빈 문자열."""
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub("", str(text))).strip()


def _credentials(raw: str) -> Dict[str, str]:
    """`key_id:key` 를 HUB 인증 헤더로. 형식이 어긋나면 호출 전에 멈춘다."""
    key_id, separator, key = (raw or "").partition(":")
    if not separator or not key_id.strip() or not key.strip():
        raise ConnectorError(
            code=AUTH_INVALID, service=SERVICE,
            detail="NAVER API HUB 키는 'key_id:key' 형식이어야 한다",
        )
    return {
        "X-NCP-APIGW-API-KEY-ID": key_id.strip(),
        "X-NCP-APIGW-API-KEY": key.strip(),
    }


def normalize(item: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """블로그·카페글의 서로 다른 필드를 공통 모양으로. 원문은 `raw` 로 보존한다."""
    common = {
        "title": _strip(item.get("title")),
        "titleRaw": item.get("title") or "",
        "link": item.get("link") or "",
        "description": _strip(item.get("description")),
        "source": mode,
    }
    if mode == "blog":
        # 블로그만 작성일(postdate)과 블로거 정보를 준다.
        common.update({
            "author": item.get("bloggername") or "",
            "authorLink": item.get("bloggerlink") or "",
            "publishedAt": item.get("postdate") or "",
        })
    else:
        # 카페글에는 작성일이 없다 — 없는 것을 지어내지 않는다.
        common.update({
            "author": item.get("cafename") or "",
            "authorLink": item.get("cafeurl") or "",
            "publishedAt": "",
        })
    common["raw"] = item
    return common


def search(
    definition,
    api_key: str,
    *,
    mode: str = "blog",
    query: str = "",
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    """검색 결과를 공통 모양으로 돌려준다. 호출 전에 입력을 먼저 거른다 —
    범위 밖 값을 보내면 HUB 가 400 으로 돌려주는데, 그건 사용자가 고칠 수 있는 것이라
    한도를 축내며 배울 이유가 없다."""
    if mode not in MODE_PATHS:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"알 수 없는 검색 대상: {mode} (가능한 값: {', '.join(MODE_PATHS)})",
        )
    query = (query or "").strip()
    if not query:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="검색어가 비어 있다")
    if sort not in ("sim", "date"):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE, detail="sort 는 sim 또는 date 여야 한다")

    # `or` 로 기본값을 주면 0 이 "미지정" 으로 오인된다 — -5 는 1 로 깎으면서 0 만 10 이 되는
    # 일관성 없는 동작이 나온다. 값이 **없을 때만** 기본값을 쓰고, 있는 값은 범위로 깎는다.
    display = 10 if display is None else display
    start = 1 if start is None else start
    try:
        display = max(MIN_DISPLAY, min(int(display), MAX_DISPLAY))
        start = max(1, min(int(start), MAX_START))
    except (TypeError, ValueError):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="display 와 start 는 숫자여야 한다",
        ) from None

    session = session or definition.new_session()
    response = session.get(
        f"{BASE_URL}/{MODE_PATHS[mode]}",
        headers=_credentials(api_key),
        params={"query": query, "display": display, "start": start, "sort": sort},
    )
    body = response.body if isinstance(response.body, dict) else {}
    items = [normalize(item, mode) for item in (body.get("items") or [])]
    return {
        "mode": mode,
        "query": query,
        "total": int(body.get("total") or 0),
        "start": int(body.get("start") or start),
        "display": len(items),
        "items": items,
    }


# ── Trigger: 새 결과만 알린다 ───────────────────────────────────────────

CURSOR_VERSION = 1
#: 겹침 창. 검색 인덱스는 순서가 흔들리고 항목이 밀려났다 돌아오기도 한다 — 마지막 응답만
#: 기억하면 그때마다 "새 글" 로 다시 알린다(rssTriggerNode 가 겪은 문제, 계획 §2 불일치 12).
SEEN_WINDOW = 300


def poll_new_results(
    definition,
    api_key: str,
    *,
    mode: str = "blog",
    query: str = "",
    cursor: Optional[Dict[str, Any]] = None,
    max_results: int = 10,
    start_mode: str = "baseline",
    since: Any = None,
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    """마지막 실행 이후 새로 나타난 결과만 돌려주고, 다음 실행에 쓸 cursor 를 함께 준다.

    **첫 실행은 기준점만 잡는다.** 그러지 않으면 워크플로를 켠 순간 과거 결과 수십 건이
    한꺼번에 쏟아진다.

    정렬은 항상 `date` 다 — 정확도순으로 폴링하면 새 글이 상위에 못 올라와 영영 놓친다.
    """
    from .. import cursor as cursor_store

    result = search(definition, api_key, mode=mode, query=query,
                    display=max_results, sort="date", session=session)

    # 정책(첫 실행 기준선·겹침 창·알린 것만 기억)은 `connectors/cursor.py` 한 곳에 있다.
    # 예전에는 여기와 `rss.poll_new_items` 가 같은 일을 각자 구현했다.
    try:
        picked = cursor_store.select_new(
            cursor, result["items"], key="link", seen_field="seen_links",
            window=SEEN_WINDOW, start_mode=start_mode, since=since,
            time_key="publishedAt", version=CURSOR_VERSION)
    except cursor_store.CursorUnreadable as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from None

    return {
        "mode": mode,
        "query": query,
        "items": picked["items"],
        "first_run": picked["first_run"],
        "cursor": picked["cursor"],
    }


def quota_subject(owner_user_id: Any) -> str:
    """한도는 키 단위로 공유된다. 키는 사용자당 하나이므로 사용자로 센다."""
    return f"naver_search:{owner_user_id or 0}"


def consume_quota(db, owner_user_id: Any) -> Dict[str, Any]:
    """호출 한 번을 세고 남은 양을 돌려준다. 한도를 넘으면 ConnectorError.

    한도에 걸리는 것이 실패는 맞지만 **고쳐지는 실패**다 — 다음 날이면 풀린다. 그래서
    `quota_exceeded`(기다린다고 풀리지 않음)가 아니라 `rate_limited` 로 분류한다.
    """
    if db is None:
        return {"used": 0, "limit": 0, "remaining": 0, "ratio": 0.0}
    import rate_limit

    rule = rate_limit.rule_for("naver.search")
    used = rate_limit.hit(db, quota_subject(owner_user_id), "naver.search")
    if used > rule.limit:
        raise ConnectorError(
            code=RATE_LIMITED, service=SERVICE,
            detail=f"네이버 검색 하루 한도({rule.limit:,}건)를 다 썼다",
            retry_after=float(rule.window_seconds),
        )
    return {
        "used": used,
        "limit": rule.limit,
        "remaining": max(0, rule.limit - used),
        "ratio": used / rule.limit if rule.limit else 0.0,
    }
