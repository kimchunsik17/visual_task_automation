"""connectors/services/team_chat.py — 국내 협업 메신저 발송: Dooray · 잔디(JANDI) · 카카오워크 (백로그 34 DEV-3, ADR-0035).

세 서비스를 한 모듈에 둔 이유: 전부 "텍스트 한 덩어리 + 제목/링크/색" 을 보내는 같은 모양의 발송이고, 노드 계약(Slack 발송과 같음 —
message 를 비우면 직전 출력, 채우면 직전 출력을 덧붙임)도 같다. 서비스별로 다른 것은 **주소·헤더·payload 모양·응답 판정**뿐이다.

■ 비밀은 URL 이거나 앱 키다
  Dooray·잔디의 Incoming Webhook 은 **URL 자체가 비밀**이다(누구든 알면 보낼 수 있다). API 센터 provider(`dooray_webhook`·`jandi_webhook`)에
  URL 을 저장하고 노드에는 참조만 남는다. 카카오워크는 봇 App Key(`kakaowork`)를 Bearer 로 싣는다.

■ 웹훅 URL 은 허용 호스트만
  사용자가 저장한 "웹훅 URL" 로 서버가 POST 를 보내므로, 그 URL 이 내부 주소면 SSRF 다. 서비스 공식 호스트(hook.dooray.com / *.dooray.com,
  wh.jandi.com)만 받고, 그 위에 url_guard.check_url(DNS 해석 결과 검사)을 한 번 더 건다. 목업(네트워크 없음)에서는 건너뛴다.

■ 발송은 되돌릴 수 없다
  POST 는 timeout 에 재시도하지 않는다(ConnectorSession 기본 — 429 만). 본문은 서비스 상한 근처(4,000자)에서 잘라 `…(잘림)` 을 붙인다 —
  잘린 것을 모르는 것보다 낫다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..errors import AUTH_INVALID, INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE_DOORAY = "Dooray"
SERVICE_JANDI = "잔디"
SERVICE_KAKAOWORK = "카카오워크"

DOORAY_HOST_SUFFIXES = ("hook.dooray.com", ".dooray.com")
JANDI_HOSTS = ("wh.jandi.com",)
KAKAOWORK_BASE_URL = "https://api.kakaowork.com"
KAKAOWORK_MODES = ("send", "send_by_email")

MAX_TEXT_CHARS = 4000
TRUNCATED_SUFFIX = "\n…(잘림)"
PLACEHOLDER = "{{last_result}}"

# 노드 공통 색 이름 → 서비스가 받는 값. 잔디 connectColor 는 hex, Dooray attachments.color 도 hex 를 받는다.
COLOR_HEX = {"green": "#2ECC71", "blue": "#3498DB", "yellow": "#FAC11B", "red": "#E74C3C", "gray": "#95A5A6", "purple": "#9B59B6"}


# ── 공통 ─────────────────────────────────────────────────────────────────

def compose_message(message: Any, upstream: Any) -> str:
    """Slack 발송과 같은 규약: 비우면 직전 출력, `{{last_result}}` 가 있으면 그 자리에, 아니면 메시지 뒤에 직전 출력을 덧붙인다."""
    text = "" if message is None else str(message)
    prev = "" if upstream is None else str(upstream)
    if PLACEHOLDER in text:
        return text.replace(PLACEHOLDER, prev)
    if not text.strip():
        return prev
    if prev.strip():
        return f"{text}\n\n{prev}"
    return text


def truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(TRUNCATED_SUFFIX))] + TRUNCATED_SUFFIX


def _color(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in COLOR_HEX:
        return COLOR_HEX[text.lower()]
    if text.startswith("#") and len(text) in (4, 7):
        return text.upper()
    raise ConnectorError(code=INVALID_REQUEST, service="메신저 발송",
                         detail=f"색은 {', '.join(COLOR_HEX)} 또는 #RRGGBB 여야 한다: {text!r}")


def hook_url(raw: Any, *, service: str, allowed_hosts: tuple) -> str:
    """저장된 Incoming Webhook URL 을 검사한다 — https, 허용 호스트, (목업이 아니면) url_guard."""
    url = str(raw or "").strip()
    from .. import mock_runtime

    mocking = mock_runtime.current() is not None
    if mocking and (not url or url == mock_runtime.MOCK_TOKEN):
        # 목업은 실제 자격증명을 읽지 않는다(require_token 이 MOCK_TOKEN 을 준다) — 네트워크를 타지 않으니 형식만 맞는 주소로 대신한다.
        return f"https://{allowed_hosts[0].lstrip('.')}/mock"
    if not url:
        raise ConnectorError(code=INVALID_REQUEST, service=service, detail="Incoming Webhook URL 이 비어 있다 — API 센터에 등록한다")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ConnectorError(code=INVALID_REQUEST, service=service, detail="Incoming Webhook URL 은 https 주소여야 한다")
    if not any(host == h or (h.startswith(".") and host.endswith(h)) for h in allowed_hosts):
        raise ConnectorError(code=INVALID_REQUEST, service=service,
                             detail=f"{service} 웹훅 주소가 아니다: {host} (허용: {', '.join(allowed_hosts)})")
    if not mocking:
        import url_guard

        try:
            url_guard.check_url(url)
        except url_guard.UrlBlocked as exc:
            raise ConnectorError(code=INVALID_REQUEST, service=service, detail=str(exc)) from exc
    return url


def _require_text(text: str, service: str) -> str:
    if not str(text or "").strip():
        raise ConnectorError(code=INVALID_REQUEST, service=service, detail="보낼 메시지가 비어 있다 — message 를 채우거나 앞 노드 출력을 연결한다")
    return truncate(text)


# ── Dooray ───────────────────────────────────────────────────────────────

def send_dooray(definition, webhook: str, *, text: str, title: str = "", link: str = "", color: str = "", bot_name: str = "",
                session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """Dooray 메신저 Incoming Webhook. `{"botName", "text", "attachments": [{"title", "titleLink", "text", "color"}]}`."""
    url = hook_url(webhook, service=SERVICE_DOORAY, allowed_hosts=DOORAY_HOST_SUFFIXES)
    body = _require_text(text, SERVICE_DOORAY)
    payload: Dict[str, Any] = {"text": body}
    if str(bot_name or "").strip():
        payload["botName"] = str(bot_name).strip()[:100]
    hex_color = _color(color)
    if str(title or "").strip() or str(link or "").strip():
        attachment: Dict[str, Any] = {"title": str(title or link).strip()[:200]}
        if str(link or "").strip():
            attachment["titleLink"] = str(link).strip()
        if hex_color:
            attachment["color"] = hex_color
        payload["attachments"] = [attachment]
    session = session or definition.new_session()
    response = session.post(url, headers={"Content-Type": "application/json"}, json=payload)
    header = response.body.get("header") if isinstance(response.body, dict) else None
    if isinstance(header, dict) and header.get("isSuccessful") is False:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE_DOORAY, status=response.status,
                             detail=str(header.get("resultMessage") or header.get("resultCode") or "webhook rejected")[:200])
    return {"service": "dooray", "sent": True, "text": body, "chars": len(body), "title": payload.get("attachments", [{}])[0].get("title", ""),
            "botName": payload.get("botName", ""), "telemetry": session.telemetry()}


# ── 잔디 ─────────────────────────────────────────────────────────────────

def send_jandi(definition, webhook: str, *, text: str, title: str = "", description: str = "", link: str = "", color: str = "",
               image_url: str = "", session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """잔디 Incoming Webhook(커넥트). `{"body", "connectColor", "connectInfo": [{"title", "description", "imageUrl"}]}`,
    `Accept: application/vnd.tosslab.jandi-v2+json`."""
    url = hook_url(webhook, service=SERVICE_JANDI, allowed_hosts=JANDI_HOSTS)
    body = _require_text(text, SERVICE_JANDI)
    payload: Dict[str, Any] = {"body": body}
    hex_color = _color(color)
    if hex_color:
        payload["connectColor"] = hex_color
    if any(str(v or "").strip() for v in (title, description, link, image_url)):
        info: Dict[str, Any] = {"title": str(title or "알림").strip()[:200]}
        desc = str(description or "").strip() or str(link or "").strip()
        if desc:
            info["description"] = desc[:1000]
        if str(image_url or "").strip():
            info["imageUrl"] = str(image_url).strip()
        payload["connectInfo"] = [info]
    session = session or definition.new_session()
    session.post(url, headers={"Accept": "application/vnd.tosslab.jandi-v2+json", "Content-Type": "application/json"}, json=payload)
    return {"service": "jandi", "sent": True, "text": body, "chars": len(body), "title": (payload.get("connectInfo") or [{}])[0].get("title", ""),
            "telemetry": session.telemetry()}


# ── 카카오워크 ───────────────────────────────────────────────────────────

def _kakaowork_check(response, service: str) -> Dict[str, Any]:
    body = response.body if isinstance(response.body, dict) else {}
    if body.get("success") is False or (body.get("error") and not body.get("success")):
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        code = str(error.get("code") or "").lower()
        message = str(error.get("message") or code or "request rejected")[:200]
        if code in ("unauthorized", "invalid_authentication", "invalid_app_key", "forbidden"):
            raise ConnectorError(code=AUTH_INVALID, service=service, status=response.status, detail=message)
        raise ConnectorError(code=INVALID_REQUEST, service=service, status=response.status, detail=message)
    return body


def send_kakaowork(definition, app_key: str, *, text: str, mode: str = "send", conversation_id: str = "", email: str = "",
                   session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """카카오워크 봇 API. `messages.send`(대화방 id) 또는 `messages.send_by_email`(수신자 이메일). Bearer App Key."""
    mode = str(mode or "send").strip().lower()
    if mode not in KAKAOWORK_MODES:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE_KAKAOWORK, detail=f"모드는 {', '.join(KAKAOWORK_MODES)} 중 하나여야 한다: {mode!r}")
    if not str(app_key or "").strip():
        raise ConnectorError(code=AUTH_INVALID, service=SERVICE_KAKAOWORK, detail="App Key 가 비어 있다")
    body = _require_text(text, SERVICE_KAKAOWORK)
    payload: Dict[str, Any] = {"text": body}
    if mode == "send":
        cid = str(conversation_id or "").strip()
        if not cid:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE_KAKAOWORK, detail="대화방 id(conversationId)가 비어 있다")
        payload["conversation_id"] = cid
        path = "/v1/messages.send"
    else:
        addr = str(email or "").strip()
        if "@" not in addr:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE_KAKAOWORK, detail="수신자 이메일(email)이 비어 있거나 형식이 아니다")
        payload["email"] = addr
        path = "/v1/messages.send_by_email"
    session = session or definition.new_session()
    response = session.post(f"{KAKAOWORK_BASE_URL}{path}",
                            headers={"Authorization": f"Bearer {str(app_key).strip()}", "Content-Type": "application/json"}, json=payload)
    result = _kakaowork_check(response, SERVICE_KAKAOWORK)
    message = result.get("message") if isinstance(result.get("message"), dict) else {}
    return {"service": "kakaowork", "sent": True, "mode": mode, "text": body, "chars": len(body),
            "messageId": str(message.get("id") or ""), "conversationId": str(message.get("conversation_id") or payload.get("conversation_id") or ""),
            "telemetry": session.telemetry()}
