"""connectors/services/gmail.py — Gmail 트리거·액션의 실행부 (Wave 1, 우선 백로그 8번).

ADR-0007/0008 계약의 반복 적용이다. 타임아웃·재시도·오류 분류는 ConnectorSession 이,
토큰은 실행 시점의 API 센터 조회(connectors.oauth)가 담당한다 — 이 파일에는 Gmail 고유한
것(검색 질의, MIME 조립, 라벨 해석)만 있다.

■ 노드가 두 개인 이유
  gmailTriggerNode : 조건(query)에 맞는 새 메일을 본다(읽기 전용, cursor 로 중복 제거)
  gmailNode        : 발송/답장/임시저장/라벨 적용 (임시저장 포함 전부 계정 상태를 바꾼다)

■ 중복 실행
  Gmail 의 `after:` 검색은 초 단위라 같은 초에 도착한 메일이 중복 통지될 수 있다 —
  YouTube 트리거와 같은 이유로 시각과 메시지 id 집합을 함께 cursor 에 둔다.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Sequence

from ..errors import INVALID_REQUEST, ConnectorError
from ..pagination import PaginationConfig
from ..session import ConnectorSession

SERVICE = "Gmail"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

TRIGGER_NODE_TYPE = "gmailTriggerNode"
ACTION_NODE_TYPE = "gmailNode"


def _session(definition, **kwargs: Any) -> ConnectorSession:
    return definition.new_session(**kwargs)


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _require(params: Dict[str, Any], field: str, label: str) -> str:
    value = str(params.get(field) or "").strip()
    if not value:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}이(가) 비어 있다")
    return value


def _headers_map(message: Dict[str, Any]) -> Dict[str, str]:
    return {
        (header.get("name") or "").lower(): header.get("value") or ""
        for header in ((message.get("payload") or {}).get("headers") or [])
    }


def _message_summary(message: Dict[str, Any]) -> Dict[str, Any]:
    headers = _headers_map(message)
    return {
        "message_id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
        "internal_ms": int(message.get("internalDate") or 0),
    }


def _fetch_summary(session: ConnectorSession, token: str, message_id: str) -> Dict[str, Any]:
    payload = session.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_auth(token),
        params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"]},
    ).json() or {}
    return _message_summary(payload)


# ── 트리거 ─────────────────────────────────────────────────────────────
def poll_new_emails(
    definition,
    token: str,
    *,
    query: str = "",
    cursor: Optional[Dict[str, Any]] = None,
    max_results: int = 10,
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    """마지막 실행 이후 도착한, 조건에 맞는 메일만 돌려준다.

    첫 실행은 가장 최근 메일의 도착 시각만 기준점으로 잡고 아무것도 통지하지 않는다 —
    받은편지함 전체가 알림으로 쏟아지는 것을 막는다.
    """
    session = session or _session(definition)
    cursor = cursor or {}
    first_run = not cursor
    last_ms = int(cursor.get("last_internal_ms") or 0)

    effective_query = (query or "").strip()
    if not first_run and last_ms:
        # after: 는 초 단위(내림) — 같은 초 중복은 seen_ids 가 걸러낸다.
        effective_query = f"{effective_query} after:{last_ms // 1000}".strip()

    listing = session.get(
        f"{API_BASE}/messages",
        headers=_auth(token),
        params={"q": effective_query, "maxResults": 1 if first_run else min(max_results * 2, 50)},
    ).json() or {}
    ids = [item.get("id") for item in (listing.get("messages") or []) if item.get("id")]

    if first_run:
        baseline_ms = 0
        if ids:
            baseline_ms = _fetch_summary(session, token, ids[0])["internal_ms"]
        return {
            "emails": [],
            "cursor": {"last_internal_ms": baseline_ms, "seen_ids": ids[:1]},
            "first_run": True,
        }

    seen_ids = set(cursor.get("seen_ids") or [])
    summaries = [_fetch_summary(session, token, message_id) for message_id in ids if message_id not in seen_ids]
    summaries = [s for s in summaries if s["internal_ms"] >= last_ms]
    summaries.sort(key=lambda item: item["internal_ms"])
    fresh = summaries[:max_results]

    newest_ms = max([item["internal_ms"] for item in summaries] + [last_ms])
    next_seen = sorted(
        {item["message_id"] for item in summaries if item["internal_ms"] == newest_ms}
        | (seen_ids if newest_ms == last_ms else set())
    )
    return {
        "emails": fresh,
        "cursor": {"last_internal_ms": newest_ms, "seen_ids": next_seen},
        "first_run": False,
    }


# ── 액션 ───────────────────────────────────────────────────────────────
def _raw_message(
    *,
    to: str,
    subject: str,
    body: str,
    extra_headers: Optional[Dict[str, str]] = None,
    attachments: Sequence[tuple] = (),
) -> str:
    """Gmail API 에 넘길 URL-safe base64 raw message.

    MIME 조립은 SMTP 와 **같은 builder** 를 쓴다(ADR-0018 FILE-SEND-3 ②) — 예전에는 여기서
    `MIMEText` 하나만 만들어서 첨부를 표현할 자리가 아예 없었고, 수신자·제목의 헤더 주입도
    막지 않았다. 첨부는 `(filename, handle, mime_type)` 튜플이며 열고 닫는 책임은 호출부
    (delivery_attachments.open_attachments)에 있다.
    """
    from delivery_runtime import build_mime_message

    message = build_mime_message(
        to=to, subject=subject, body=body,
        extra_headers=extra_headers, opened_attachments=attachments,
    )
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _send_email(session, token, params) -> Dict[str, Any]:
    to = _require(params, "to", "수신자")
    raw = _raw_message(
        to=to, subject=str(params.get("subject") or ""), body=str(params.get("body") or ""),
        attachments=params.get("__attachments__") or (),
    )
    sent = session.post(f"{API_BASE}/messages/send", headers=_auth(token), json={"raw": raw}).json() or {}
    return {"message_id": sent.get("id", ""), "thread_id": sent.get("threadId", ""), "to": to}


def _reply_email(session, token, params) -> Dict[str, Any]:
    message_id = _require(params, "messageId", "답장할 메시지 ID")
    original = session.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_auth(token),
        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Message-ID"]},
    ).json() or {}
    headers = _headers_map(original)
    to = str(params.get("to") or "").strip() or headers.get("from", "")
    if not to:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="답장 수신자를 알 수 없다")
    subject = headers.get("subject", "")
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    original_message_id = headers.get("message-id", "")
    # 답장은 기존 thread 를 유지해야 한다 — threadId 와 In-Reply-To/References 를 함께 보낸다.
    # 첨부가 붙어도 이 헤더들은 그대로다(FILE-SEND-3 ③).
    raw = _raw_message(
        to=to, subject=subject, body=str(params.get("body") or ""),
        extra_headers={"In-Reply-To": original_message_id, "References": original_message_id},
        attachments=params.get("__attachments__") or (),
    )
    sent = session.post(
        f"{API_BASE}/messages/send",
        headers=_auth(token),
        json={"raw": raw, "threadId": original.get("threadId", "")},
    ).json() or {}
    return {"message_id": sent.get("id", ""), "thread_id": sent.get("threadId", ""), "to": to, "subject": subject}


def _create_draft(session, token, params) -> Dict[str, Any]:
    to = _require(params, "to", "수신자")
    raw = _raw_message(
        to=to, subject=str(params.get("subject") or ""), body=str(params.get("body") or ""),
        attachments=params.get("__attachments__") or (),
    )
    draft = session.post(f"{API_BASE}/drafts", headers=_auth(token), json={"message": {"raw": raw}}).json() or {}
    return {"draft_id": draft.get("id", ""), "to": to}


def _add_label(session, token, params) -> Dict[str, Any]:
    message_id = _require(params, "messageId", "메시지 ID")
    label_name = _require(params, "labelName", "라벨 이름")
    listing = session.get(f"{API_BASE}/labels", headers=_auth(token)).json() or {}
    label_id = next(
        (label.get("id") for label in listing.get("labels") or []
         if (label.get("name") or "").lower() == label_name.lower()),
        None,
    )
    created = False
    if not label_id:
        made = session.post(f"{API_BASE}/labels", headers=_auth(token), json={"name": label_name}).json() or {}
        label_id, created = made.get("id", ""), True
    session.post(
        f"{API_BASE}/messages/{message_id}/modify",
        headers=_auth(token),
        json={"addLabelIds": [label_id]},
    )
    return {"message_id": message_id, "label": label_name, "label_id": label_id, "label_created": created}


_ACTIONS = {
    "send_email": _send_email,
    "reply_email": _reply_email,
    "create_draft": _create_draft,
    "add_label": _add_label,
}


def run_action(
    definition,
    mode: str,
    token: str,
    params: Dict[str, Any],
    *,
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    declared = definition.connector.modes
    if mode not in declared:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"'{mode}' 는 이 노드가 지원하지 않는 동작이다. 가능: {', '.join(declared)}",
        )
    session = session or _session(definition)
    return _ACTIONS[mode](session, token, params)
