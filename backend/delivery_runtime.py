"""delivery_runtime.py — Discord·SMTP·Gmail 의 공통 발송 adapter (ADR-0018, 우선 백로그 20).

발송 노드의 실행 로직을 생성 코드 문자열에서 이 모듈로 꺼냈다(databaseNode 가 db_query_runtime 으로
간 것과 같은 이유). 문자열로 조립된 코드 안에서는 첨부 검증·stream 정리·부분 실패 보고를 넣을
자리가 없었고, 채널마다 같은 로직이 조금씩 다르게 복제됐다.

  build_mime_message   SMTP 와 Gmail 이 **같은** MIME 을 만든다. 헤더 주입을 여기서 막는다.
  send_discord         webhook 과 Bot API 를 한 adapter 로 통합한다. 본문과 다중 첨부를 함께 보낸다.
  send_smtp            표준 EmailMessage 로 본문 + 첨부.

전부 `NodeResult` 를 돌려준다(ADR-0016). 성공 data 는 §4.10 의 `DeliveryResult` 다:

    {provider, messageId, threadId, attachments: [{artifactId, filename, sizeBytes, status}]}

첨부 검증은 **외부 호출 전에** 끝난다. 하나라도 실패하면 아무것도 보내지 않는다.
"""

from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any, Dict, List, Optional, Sequence

from artifacts import ArtifactError, safe_filename
from delivery_attachments import (
    attachment_report,
    collect_artifact_ids,
    connector_enabled,
    open_attachments,
    policy_for,
    validate_attachments,
)
from node_errors import NodeResult, make_error
from node_errors import delivery as delivery_errors

DISCORD_API_BASE = "https://discord.com/api/v10"

# 헤더에 그대로 들어가는 값(수신자·제목)에서 개행을 없앤다. 하나만 새어도 임의의 헤더를
# 덧붙일 수 있다 — Bcc 를 추가해 메일을 제3자에게 복사하는 것이 대표적이다.
_HEADER_STRIP = str.maketrans({"\r": " ", "\n": " ", "\x00": ""})


def sanitize_header(value: Any, *, max_length: int = 500) -> str:
    return str(value or "").translate(_HEADER_STRIP).strip()[:max_length]


def split_recipients(raw: Any) -> List[str]:
    """`a@b.com, c@d.com` → 목록. 헤더 주입 문자는 위에서 이미 제거된다."""
    text = sanitize_header(raw, max_length=2000)
    parts = [item.strip() for item in text.replace(";", ",").split(",")]
    return [item for item in parts if item]


# ── MIME ────────────────────────────────────────────────────────────────
def build_mime_message(
    *,
    to: Sequence[str] | str,
    subject: str,
    body: str,
    sender: Optional[str] = None,
    opened_attachments: Sequence[tuple] = (),
    extra_headers: Optional[Dict[str, str]] = None,
    message_id: Optional[str] = None,
) -> EmailMessage:
    """SMTP 와 Gmail 이 공유하는 MIME 조립기.

    본문은 첨부가 있든 없든 항상 들어간다 — 예전 Discord 경로는 첨부가 생기면 본문을 빈 값으로
    보냈고, 사용자가 쓴 캡션이 사라졌다(§4.10 "현재 간극"). 같은 실수를 메일에서 반복하지 않는다.
    """
    message = EmailMessage()
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [sanitize_header(item, max_length=320) for item in recipients if str(item or "").strip()]
    message["To"] = ", ".join(recipients)
    message["Subject"] = sanitize_header(subject)
    if sender:
        message["From"] = sanitize_header(sender, max_length=320)
    if message_id:
        message["Message-ID"] = sanitize_header(message_id, max_length=320)
    for name, value in (extra_headers or {}).items():
        cleaned = sanitize_header(value)
        if cleaned:
            message[sanitize_header(name, max_length=64)] = cleaned

    message.set_content(str(body or ""), subtype="plain", charset="utf-8")

    for filename, handle, mime_type in opened_attachments:
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        message.add_attachment(
            handle.read(),
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=safe_filename(filename),
        )
    return message


def _delivery_result(provider: str, *, message_id=None, thread_id=None, report=None) -> Dict[str, Any]:
    return {
        "provider": provider,
        "messageId": str(message_id) if message_id else None,
        "threadId": str(thread_id) if thread_id else None,
        "attachments": list(report or []),
    }


def _attachment_note(report: Sequence[Dict[str, Any]]) -> str:
    if not report:
        return ""
    names = ", ".join(str(item.get("filename") or "") for item in report)
    return f"\n\n[📎 첨부 {len(report)}개: {names}]"


def _failure(error, *, passthrough: str, prefix: str = "") -> NodeResult:
    """실패해도 만들려던 본문은 버리지 않는다.

    표시 문자열은 기존 `[⚠️ 채널 발송 실패: ...]` 관례를 그대로 쓴다 — 사용자가 보는 문구이고,
    디스코드 봇의 legacy fallback 과 평가 기능이 이 모양을 읽는다. 판정 자체는 문자열이 아니라
    실행 로그의 NodeError 로 한다(ADR-0016).
    """
    note = f"[⚠️ {prefix}{error.user_message}]" if prefix else error.legacy_note()
    return NodeResult.failure(error, passthrough=passthrough,
                              display=f"{passthrough}\n\n{note}" if passthrough else note)


# ── 첨부 준비 (채널 공통) ────────────────────────────────────────────────
def prepare_attachments(
    db,
    *,
    provider: str,
    config: Any,
    upstream_artifact_ids: Sequence[str],
    upstream_text: str,
    owner_user_id: int,
    project_id: Optional[int],
    node_type: str,
    node_id: Optional[str],
) -> List:
    """설정 → artifact id → 검증된 목록. flag 가 꺼져 있으면 빈 목록(본문만 발송)."""
    if not connector_enabled(provider):
        return []
    artifact_ids = collect_artifact_ids(
        config,
        upstream_artifact_ids=upstream_artifact_ids,
        upstream_text=upstream_text,
        db=db,
        owner_user_id=owner_user_id,
    )
    if not artifact_ids:
        return []
    return validate_attachments(
        db, artifact_ids, owner_user_id=owner_user_id, project_id=project_id,
        policy=policy_for(provider), node_type=node_type, node_id=node_id,
    )


# ── Discord ─────────────────────────────────────────────────────────────
def send_discord(
    *,
    token: str,
    channel_id: str,
    body: str,
    db=None,
    owner_user_id: int = 0,
    project_id: Optional[int] = None,
    attachments_config: Any = None,
    upstream_artifact_ids: Sequence[str] = (),
    upstream_text: str = "",
    node_id: Optional[str] = None,
    session=None,
) -> NodeResult:
    """webhook 과 Bot API 를 한 경로로 보낸다(FILE-SEND-2 ①).

    `token` 이 `http` 로 시작하면 webhook URL, 아니면 봇 토큰이다(기존 판별을 그대로 유지한다).
    두 경우 모두 첨부가 있으면 multipart 로, `payload_json.content` 에 **본문을 담아** 보낸다.
    """
    import requests

    node_type = "discordNode"
    message = str(body or "")
    token = str(token or "").strip()
    channel_id = str(channel_id or "").strip()

    if not token:
        return _failure(delivery_errors.credential_missing(
            "discord", node_type=node_type, node_id=node_id,
            user_message="Discord 봇 토큰/웹훅이 설정되지 않아 실제 발송은 되지 않았습니다",
        ), passthrough=message)

    policy = policy_for("discord")
    try:
        resolved = prepare_attachments(
            db, provider="discord", config=attachments_config,
            upstream_artifact_ids=upstream_artifact_ids, upstream_text=upstream_text,
            owner_user_id=owner_user_id, project_id=project_id,
            node_type=node_type, node_id=node_id,
        )
    except ArtifactError as exc:
        # 첨부 검증 실패 — 외부 호출을 하지 않았다. 본문은 그대로 남긴다.
        return _failure(exc.error, passthrough=message, prefix="Discord 첨부 실패: ")

    poster = session.post if session is not None else requests.post
    try:
        if not token.startswith("http") and not channel_id:
            raise ValueError("Channel ID is required for Bot Token mode")

        url = token if token.startswith("http") else f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
        headers = {} if token.startswith("http") else {"Authorization": f"Bot {token}"}

        with open_attachments(resolved) as opened:
            if opened:
                files = {
                    f"files[{index}]": (filename, handle, mime_type)
                    for index, (filename, handle, mime_type) in enumerate(opened)
                }
                # multipart 에서는 Content-Type 을 직접 넣지 않는다 — requests 가 boundary 를 포함해
                # 만든다. 그리고 본문(content)은 첨부가 있어도 반드시 함께 보낸다.
                response = poster(
                    url, headers=headers,
                    data={"payload_json": json.dumps({"content": message}, ensure_ascii=False)},
                    files=files, timeout=policy.timeout_seconds,
                )
            else:
                response = poster(
                    url, headers={**headers, "Content-Type": "application/json"},
                    json={"content": message}, timeout=policy.timeout_seconds,
                )
    except ArtifactError as exc:
        return _failure(exc.error, passthrough=message, prefix="Discord 첨부 실패: ")
    except Exception as exc:
        return _failure(delivery_errors.error_from_exception(
            exc, provider="discord", node_type=node_type, node_id=node_id,
            timeout_seconds=policy.timeout_seconds,
        ), passthrough=message, prefix="Discord 발송 오류: ")

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code not in (200, 201, 204):
        return _failure(delivery_errors.error_from_status(
            status_code, provider="discord", headers=getattr(response, "headers", None),
            body=getattr(response, "text", None), node_type=node_type, node_id=node_id,
        ), passthrough=message, prefix="Discord 발송 실패: ")

    payload: Dict[str, Any] = {}
    try:
        payload = response.json() or {}
    except Exception:
        # 웹훅은 기본적으로 204 + 빈 본문이다. message ID 가 없는 것은 실패가 아니다.
        payload = {}

    report = attachment_report(resolved)
    return NodeResult.success(
        # Discord 에는 thread 개념이 채널이다 — 응답의 channel_id 를 threadId 자리에 싣는다.
        _delivery_result("discord", message_id=payload.get("id"),
                         thread_id=payload.get("channel_id") or channel_id or None, report=report),
        display=message + _attachment_note(report),
        artifacts=[item.ref.to_public_dict() for item in resolved],
    )


# ── SMTP ────────────────────────────────────────────────────────────────
def send_smtp(
    *,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    subject: str,
    body: str,
    db=None,
    owner_user_id: int = 0,
    project_id: Optional[int] = None,
    attachments_config: Any = None,
    upstream_artifact_ids: Sequence[str] = (),
    upstream_text: str = "",
    node_id: Optional[str] = None,
    client_factory=None,
) -> NodeResult:
    """SMTP 발송. 본문 + MIME 첨부(FILE-SEND-3 ①).

    `client_factory` 는 테스트가 로컬 test SMTP 로 갈아끼우는 자리다(기본은 smtplib.SMTP).
    """
    node_type = "emailNode"
    message_body = str(body or "")
    policy = policy_for("smtp")
    recipients = split_recipients(to_email)

    if not smtp_user or not smtp_password:
        return _failure(delivery_errors.credential_missing(
            "smtp", node_type=node_type, node_id=node_id, credential_provider="google_smtp",
            user_message="SMTP 계정이 설정되지 않아 실제 발송은 되지 않았습니다",
        ), passthrough=message_body, prefix="이메일 발송 실패: ")
    if not recipients:
        return _failure(make_error(
            "VALIDATION_REQUIRED", field="toEmail", effect_state="not_started",
            safe_details={"field": "toEmail"}, node_type=node_type, node_id=node_id,
        ), passthrough=message_body, prefix="이메일 발송 실패: ")

    try:
        resolved = prepare_attachments(
            db, provider="smtp", config=attachments_config,
            upstream_artifact_ids=upstream_artifact_ids, upstream_text=upstream_text,
            owner_user_id=owner_user_id, project_id=project_id,
            node_type=node_type, node_id=node_id,
        )
    except ArtifactError as exc:
        return _failure(exc.error, passthrough=message_body, prefix="이메일 첨부 실패: ")

    try:
        with open_attachments(resolved) as opened:
            # SMTP 서버는 message ID 를 돌려주지 않는다. 보내는 쪽에서 만들어 두면 결과에
            # 실을 값이 생기고, 사용자가 메일함에서 같은 메일을 찾을 수 있다.
            message = build_mime_message(
                to=recipients, subject=subject, body=message_body,
                sender=smtp_user, opened_attachments=opened, message_id=make_msgid(),
            )
        factory = client_factory or smtplib.SMTP
        client = factory(smtp_server, smtp_port, timeout=policy.timeout_seconds)
        try:
            client.starttls()
            client.login(smtp_user, smtp_password)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:
                pass
    except ArtifactError as exc:
        return _failure(exc.error, passthrough=message_body, prefix="이메일 첨부 실패: ")
    except Exception as exc:
        return _failure(delivery_errors.error_from_exception(
            exc, provider="smtp", node_type=node_type, node_id=node_id,
            timeout_seconds=policy.timeout_seconds, credential_provider="google_smtp",
        ), passthrough=message_body, prefix="이메일 발송 실패: ")

    report = attachment_report(resolved)
    return NodeResult.success(
        # SMTP 는 provider message ID 를 돌려주지 않는다. 우리가 만든 Message-ID 를 쓴다 —
        # 재시도 판단은 effectState 로 하지 이 값으로 하지 않는다.
        _delivery_result("smtp", message_id=message.get("Message-ID"), report=report),
        display=message_body + _attachment_note(report),
        artifacts=[item.ref.to_public_dict() for item in resolved],
    )
