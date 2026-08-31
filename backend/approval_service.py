"""approval_service.py — 사용자 승인 노드의 durable 대기·알림·재개 (ADR-0015).

워크플로우가 승인 노드에 도달하면 graph.run_workflow 가 실행을 중단하고 이 모듈로
ApprovalRequest 를 만든다. 요청은 DB에 남으므로 브라우저를 닫거나 서버가 재시작돼도
대기 상태가 유지되고, 소유자가 승인/거절하면 저장된 그래프 스냅샷과 payload 로 그 노드부터
실행을 재개한다.

계약의 핵심:
  - **승인한 것이 곧 이어지는 것이다.** 재개는 요청에 저장된 payload(승인자가 본 견본)를
    그대로 다음 노드로 흘려보낸다 — 상류 노드(LLM 초안 작성 등)를 재실행하지 않으므로
    "본 것과 다른 내용이 발송되는" 일이 구조적으로 없다.
  - **결정은 한 번만.** pending → approved/rejected 전이는 원자적 UPDATE 로 보호한다.
    중복 클릭·중복 요청은 두 번째부터 거부된다.
  - **거절도 액션이다.** rejected/else 핸들이 연결돼 있으면 그 갈래(작성자에게 거절 알림 등)가
    실행되고, 없으면 깔끔히 중단으로 기록한다.
  - **알림은 best effort.** 사이트 알림(이 행 자체)은 항상 남고, 이메일/카카오/디스코드는
    실패해도 대기 상태에 영향이 없다 — 채널별 결과를 notify_results 에 기록만 한다.

한계(문서화된 범위): 승인 노드가 loop/distributor 안에 있으면 반복 문맥 없이 그 노드부터
한 번만 재개된다. 승인 노드는 최상위 경로에 두는 것을 권장한다(팔레트/카탈로그에 안내).
"""

from __future__ import annotations

import datetime
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _node_error_runtime():
    from node_errors import runtime
    return runtime

import models

MAX_PAYLOAD_CHARS = 200_000
PREVIEW_CHARS = 1_200
VALID_CHANNELS = ("email", "kakao", "discord")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _frontend_base_url() -> str:
    return (os.getenv("FRONTEND_BASE_URL") or "https://wa-pnu.duckdns.org").rstrip("/")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def serializable_runtime_inputs(runtime_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """재개 시 그대로 kwargs 로 돌려줄 수 있는 값만 남긴다. db 세션·콜백 같은 객체와
    승인 관련 키(재개 시 새로 채워진다)는 제외한다."""
    excluded = {"approval_decisions", "approval_decision", "__approval_payload__"}
    safe: Dict[str, Any] = {}
    for key, value in (runtime_inputs or {}).items():
        if key in excluded:
            continue
        if isinstance(value, (str, int, float, bool, type(None))):
            safe[key] = value
        elif isinstance(value, (list, dict)):
            safe[key] = _json_safe(value)
    return safe


def create_request(
    db,
    *,
    owner_user_id: int,
    project_id: Optional[int],
    node: Dict[str, Any],
    payload: Any,
    graph_snapshot: Dict[str, Any],
    runtime_inputs: Dict[str, Any],
    session_id: Optional[str],
    origin: str,
) -> models.ApprovalRequest:
    """승인 대기 행을 만들고 알림을 발송한다(알림 실패는 대기 상태에 영향 없음)."""
    data = node.get("data") or {}
    channels = [c for c in VALID_CHANNELS if data.get(
        {"email": "notifyEmail", "kakao": "notifyKakao", "discord": "notifyDiscord"}[c]
    )]
    project_title = None
    if project_id:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        project_title = project.title if project else None

    request = models.ApprovalRequest(
        request_id=uuid.uuid4().hex,
        user_id=owner_user_id,
        project_id=project_id,
        project_title=project_title,
        node_id=str(node.get("id")),
        status="pending",
        origin=origin,
        message=str(data.get("message") or "다음 단계로 진행하시겠습니까?"),
        payload=str(payload if payload is not None else "")[:MAX_PAYLOAD_CHARS],
        graph_snapshot=graph_snapshot,
        runtime_inputs=serializable_runtime_inputs(runtime_inputs),
        session_id=session_id,
        notify_channels=channels,
        created_at=_now(),
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    request.notify_results = send_notifications(db, request, discord_channel_id=str(data.get("discordChannelId") or ""))
    db.commit()
    return request


# ── 알림 ────────────────────────────────────────────────────────────────
def _notification_text(request: models.ApprovalRequest) -> str:
    preview = (request.payload or "").strip()
    if len(preview) > PREVIEW_CHARS:
        preview = preview[:PREVIEW_CHARS] + "\n...(이하 생략 — 사이트에서 전체 확인)"
    lines = [
        f"[승인 요청] {request.project_title or '워크플로우'}",
        request.message or "",
        "",
        "── 승인 대상 미리보기 ──",
        preview or "(내용 없음)",
        "",
        f"승인/거절: {_frontend_base_url()}/approvals",
    ]
    return "\n".join(lines)


def _send_email(db, request: models.ApprovalRequest, text: str) -> str:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    user = db.query(models.User).filter(models.User.id == request.user_id).first()
    if not user or not user.email:
        return "skipped: 사용자 이메일 없음"
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    # emailNode 와 같은 우선순위: API 센터 google_smtp("이메일:앱비밀번호") 가 있으면 사용자 계정으로.
    key = db.query(models.UserApiKey).filter(
        models.UserApiKey.user_id == request.user_id,
        models.UserApiKey.provider == "google_smtp",
    ).first()
    if key:
        from credential_crypto import decrypt_secret
        secret = decrypt_secret(key.api_key)
        if secret and ":" in secret:
            smtp_user, smtp_password = secret.split(":", 1)
    if not smtp_user or not smtp_password:
        return "skipped: SMTP 자격증명 없음"
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = user.email
    msg["Subject"] = f"[WorkFlow Ai] 승인 요청: {request.project_title or '워크플로우'}"
    msg.attach(MIMEText(text, "plain", "utf-8"))
    server = smtplib.SMTP(os.getenv("SMTP_SERVER", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=10)
    try:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    finally:
        server.quit()
    return "sent"


def _send_kakao(db, request: models.ApprovalRequest, text: str) -> str:
    import requests

    from kakao_utils import ensure_kakao_token_fresh

    token = ensure_kakao_token_fresh(request.user_id, db)
    if not token:
        key = db.query(models.UserApiKey).filter(
            models.UserApiKey.user_id == request.user_id,
            models.UserApiKey.provider == "kakao_token",
        ).first()
        if key:
            from credential_crypto import decrypt_secret
            token = decrypt_secret(key.api_key)
    if not token:
        return "skipped: 카카오 토큰 없음"
    template_object = {
        "object_type": "text",
        "text": text[:1900],  # 카카오 텍스트 템플릿 제한(2000자) 여유분
        "link": {"web_url": f"{_frontend_base_url()}/approvals", "mobile_web_url": f"{_frontend_base_url()}/approvals"},
        "button_title": "승인하러 가기",
    }
    resp = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps(template_object, ensure_ascii=False)},
        timeout=10,
    )
    return "sent" if resp.status_code == 200 else f"failed: HTTP {resp.status_code}"


def _send_discord(db, request: models.ApprovalRequest, text: str, channel_id: str) -> str:
    import requests

    if not channel_id:
        return "skipped: 채널 ID 없음(노드 설정에서 입력)"
    key = db.query(models.UserApiKey).filter(
        models.UserApiKey.user_id == request.user_id,
        models.UserApiKey.provider == "discord",
    ).first()
    if not key:
        return "skipped: 디스코드 봇 토큰 없음"
    from credential_crypto import decrypt_secret
    token = decrypt_secret(key.api_key)
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id.strip()}/messages",
        headers={"Authorization": f"Bot {token}"},
        json={"content": text[:1900]},
        timeout=10,
    )
    return "sent" if resp.status_code in (200, 201) else f"failed: HTTP {resp.status_code}"


def send_notifications(db, request: models.ApprovalRequest, discord_channel_id: str = "") -> Dict[str, str]:
    """채널별 best-effort 발송. 사이트 알림은 요청 행 자체이므로 여기서 다루지 않는다."""
    text = _notification_text(request)
    senders = {
        "email": lambda: _send_email(db, request, text),
        "kakao": lambda: _send_kakao(db, request, text),
        "discord": lambda: _send_discord(db, request, text, discord_channel_id),
    }
    results: Dict[str, str] = {}
    for channel in request.notify_channels or []:
        try:
            results[channel] = senders[channel]()
        except Exception as exc:
            results[channel] = f"failed: {type(exc).__name__}: {exc}"
    return results


# ── 결정과 재개 ─────────────────────────────────────────────────────────
def decide_and_resume(
    db,
    *,
    request_id: str,
    actor_user_id: int,
    decision: str,
    comment: str = "",
) -> Tuple[models.ApprovalRequest, str, dict, list]:
    """결정을 기록하고 중단 지점부터 실행을 재개한다.

    반환: (요청 행, 재개 결과 텍스트, 토큰 사용량, 실행 로그).
    권한(소유자만)·상태(pending 만)·멱등성(원자적 전이)을 여기서 강제한다.
    """
    if decision not in ("approve", "reject"):
        raise ValueError("decision 은 approve 또는 reject 여야 합니다")

    request = db.query(models.ApprovalRequest).filter(
        models.ApprovalRequest.request_id == request_id,
    ).first()
    if request is None:
        raise LookupError("승인 요청을 찾을 수 없습니다")
    if request.user_id != actor_user_id:
        raise PermissionError("이 승인 요청을 결정할 권한이 없습니다")

    new_status = "approved" if decision == "approve" else "rejected"
    # 원자적 전이 — 두 요청이 동시에 결정해도 한쪽만 성공한다(중복 재개 방지).
    updated = db.query(models.ApprovalRequest).filter(
        models.ApprovalRequest.id == request.id,
        models.ApprovalRequest.status == "pending",
    ).update({
        "status": new_status,
        "comment": (comment or "")[:2000],
        "decided_by": actor_user_id,
        "decided_at": _now(),
    }, synchronize_session=False)
    db.commit()
    if not updated:
        db.refresh(request)
        raise RuntimeError(f"이미 처리된 요청입니다 (현재 상태: {request.status})")
    db.refresh(request)

    from graph import run_workflow

    snapshot = request.graph_snapshot or {}
    runtime_inputs = dict(request.runtime_inputs or {})
    runtime_inputs.pop("session_id", None)
    runtime_inputs.pop("project_id", None)
    result_text, tokens, logs = run_workflow(
        snapshot.get("nodes") or [],
        snapshot.get("edges") or [],
        db=db,
        session_id=request.session_id,
        project_id=request.project_id,
        entry_node_id=request.node_id,
        approval_payload=request.payload,
        approval_decisions={request.node_id: "Y" if decision == "approve" else "N"},
        **runtime_inputs,
    )

    if "Rejected" in result_text and decision == "reject":
        # 거절 갈래가 연결되지 않은 그래프 — 예외 중단이 아니라 의도된 결과로 기록한다.
        request.resume_outcome = "halted"
        result_text = "거절되어 워크플로우를 중단했습니다. (거절 시 동작을 정의하려면 승인 노드의 '거절 시' 핸들에 노드를 연결하세요)"
    elif _node_error_runtime().flow_outcome(result_text, logs) == "error":
        # 구조화 오류(NodeError v1) 우선, legacy 문구는 fallback(ADR-0016)
        request.resume_outcome = "error"
    else:
        request.resume_outcome = "success"
    db.commit()
    return request, result_text, tokens, logs


def request_to_dict(request: models.ApprovalRequest, *, include_full_payload: bool = False) -> dict:
    payload = request.payload or ""
    return {
        "request_id": request.request_id,
        "project_id": request.project_id,
        "project_title": request.project_title,
        "node_id": request.node_id,
        "status": request.status,
        "origin": request.origin,
        "message": request.message,
        "payload_preview": payload if include_full_payload else payload[:PREVIEW_CHARS],
        "payload_truncated": (not include_full_payload) and len(payload) > PREVIEW_CHARS,
        "notify_channels": request.notify_channels or [],
        "notify_results": request.notify_results or {},
        "comment": request.comment,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
        "resume_outcome": request.resume_outcome,
        "created_at": request.created_at.isoformat() if request.created_at else None,
    }
