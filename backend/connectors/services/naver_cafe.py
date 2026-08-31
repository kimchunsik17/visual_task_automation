"""connectors/services/naver_cafe.py — 네이버 카페 가입·글쓰기 (한국형 노드 계획 §4.2).

■ HUB 가 아니라 개발자센터다

검색 API 는 2026-06-25 에 NAVER API HUB 로 옮겨갔지만 **카페는 이관 대상이 아니었다**(§4.0).
그래서 호스트도 인증도 검색과 다르다.

    검색   naverapihub.apigw.ntruss.com  + X-NCP-APIGW-API-KEY-*
    카페   openapi.naver.com             + Authorization: Bearer <사용자 토큰>

■ 한글이 깨지는 자리 — 공식 예제가 두 번 인코딩한다

    // 해당 string은 UTF-8로 encode 후 MS949로 재 encode를 수행한 값
    String subject = URLEncoder.encode(URLEncoder.encode("카페 가입 인사", "UTF-8"), "MS949");

1차 인코딩 결과가 이미 ASCII(`%EC%B9%B4...`)라 2차의 charset 은 사실상 무의미하고, `%` 가
`%25` 로 한 번 더 감싸질 뿐이다. 그래서 우리도 **URL 인코딩을 두 번** 한다.

이 때문에 본문을 `data={"subject": ...}` 같은 dict 로 넘기면 안 된다 — HTTP 라이브러리가
**세 번째** 인코딩을 하기 때문이다. 이미 인코딩된 문자열을 그대로 body 로 보낸다.

■ 실수로 게시되지 않게 한다

글쓰기는 되돌릴 수 없다. 그래서 기본값은 **미리보기**이고, 실제 게시는 노드에서 명시적으로
켜야 한다(`confirm`). 켜지 않으면 어떤 요청도 나가지 않는다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "네이버 카페"
BASE_URL = "https://openapi.naver.com/v1/cafe"

MODES = ("join", "write_article")

MAX_SUBJECT = 200
MAX_CONTENT = 50_000


def encode_field(value: Any) -> str:
    """공식 예제와 같은 이중 URL 인코딩. 한 번만 하면 한글이 깨진다."""
    return quote_plus(quote_plus("" if value is None else str(value), encoding="utf-8"))


def form_body(fields: Dict[str, Any]) -> str:
    """이미 인코딩된 값들로 body 를 직접 만든다 — 라이브러리에 맡기면 한 번 더 인코딩된다."""
    return "&".join(f"{name}={encode_field(value)}" for name, value in fields.items())


def _auth(access_token: str) -> Dict[str, str]:
    token = (access_token or "").strip()
    if not token:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="네이버 사용자 토큰이 없다 — API 센터에서 카페 권한으로 연결해야 한다",
        )
    # 공식 예제 주석: "Bearer 다음에 공백 추가"
    return {"Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded"}


def _club_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text.isdigit():
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="카페 ID 는 숫자다. 카페 관리 화면이나 카페 주소에서 확인할 수 있다",
        )
    return text


def preview(mode: str, *, club_id: Any = "", menu_id: Any = "",
            subject: str = "", content: str = "", nickname: str = "") -> Dict[str, Any]:
    """무엇이 어디에 올라가는지. **아무것도 보내지 않는다.**

    사용자가 실행 전에 볼 수 있어야 하는 것: 어느 카페의 어느 게시판에, 어떤 제목으로.
    """
    if mode == "join":
        return {"mode": "join", "clubId": str(club_id or ""), "nickname": nickname,
                "willSend": False,
                "summary": f"카페 {club_id} 에 '{nickname}' 이름으로 가입합니다."}
    body = str(content or "")
    return {
        "mode": "write_article",
        "clubId": str(club_id or ""),
        "menuId": str(menu_id or ""),
        "subject": subject,
        "contentPreview": body[:200] + ("…" if len(body) > 200 else ""),
        "contentLength": len(body),
        "willSend": False,
        "summary": f"카페 {club_id} 의 게시판 {menu_id} 에 '{subject}' 글을 올립니다.",
    }


def join(definition, access_token: str, *, club_id: Any, nickname: str,
         session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """카페에 가입한다. 되돌릴 수 없으므로 호출부가 확인을 받은 뒤에만 부른다."""
    club = _club_id(club_id)
    if not str(nickname or "").strip():
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="카페에서 쓸 별명이 비어 있다")

    session = session or definition.new_session()
    response = session.request(
        "POST", f"{BASE_URL}/{club}/members",
        headers=_auth(access_token),
        data=form_body({"nickname": nickname}),
        idempotent=False,
    )
    body = response.body if isinstance(response.body, dict) else {}
    return {"mode": "join", "clubId": club, "sent": True, "raw": body}


def write_article(definition, access_token: str, *, club_id: Any, menu_id: Any,
                  subject: str, content: str,
                  session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """카페 게시판에 글을 쓴다.

    **재시도하지 않는다**(`idempotent=False`). timeout 뒤 재시도는 같은 글을 두 번 올린다 —
    한 번 실패하는 것보다 나쁘다(ADR-0007 의 원칙).
    """
    club = _club_id(club_id)
    menu = str(menu_id or "").strip()
    if not menu.isdigit():
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="게시판 ID 는 숫자다. 카페 게시판 주소의 menuid 에서 확인할 수 있다(상품게시판은 쓸 수 없다)",
        )
    if not str(subject or "").strip():
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="제목이 비어 있다")
    if len(str(subject)) > MAX_SUBJECT:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"제목이 너무 길다({len(str(subject))}자, 상한 {MAX_SUBJECT}자)")
    if len(str(content or "")) > MAX_CONTENT:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"본문이 너무 길다(상한 {MAX_CONTENT}자)")

    session = session or definition.new_session()
    response = session.request(
        "POST", f"{BASE_URL}/{club}/menu/{menu}/articles",
        headers=_auth(access_token),
        data=form_body({"subject": subject, "content": content}),
        idempotent=False,
    )
    body = response.body if isinstance(response.body, dict) else {}
    message = body.get("message") if isinstance(body, dict) else None
    return {
        "mode": "write_article", "clubId": club, "menuId": menu,
        "subject": subject, "sent": True,
        # 응답에 글 번호가 오면 감사 기록에 남긴다 — 중복 게시 여부를 사람이 확인할 근거다.
        "articleId": (message or {}).get("result", {}).get("articleId") if isinstance(message, dict) else None,
        "raw": body,
    }
