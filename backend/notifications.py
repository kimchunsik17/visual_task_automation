"""notifications.py — 인앱 알림함 (ADR-0020, 우선 백로그 22 SAFE-3).

**인앱만이다.** 이메일·외부 채널은 만들지 않는다(제품 결정, 2026-08-29). ADR-0015 의 승인 알림은
외부 채널을 쓰지만 그건 "실행이 멈춰 사람을 기다리는" 상황이라 성격이 다르다.

**폴링을 넣지 않는다.** 댓글·좋아요·친구 요청은 초 단위 실시간이 필요 없고, 2 vCPU·1.9GB 서버에서
상시 연결이나 주기 요청을 지금 감당할 이유가 없다. 화면 전환 시 갱신으로 시작하고, 실시간 푸시는
쪽지(§4.13)가 SSE 를 들여올 때 **같은 채널에 얹는다**.

`quiet` 알림은 배지에 세지 않고 목록에만 남는다 — 차단 통지처럼 "알려야 하지만 재촉할 일은 아닌" 것.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

MAX_BODY = 500
DEFAULT_PAGE = 30
MAX_PAGE = 100


def notify(db, *, user_id: int, kind: str, body: str = "", actor_id: Optional[int] = None,
           target_type: Optional[str] = None, target_id: Optional[str] = None,
           quiet: bool = False, commit: bool = True):
    """알림 하나를 남긴다.

    `commit=False` 는 호출부가 더 큰 트랜잭션 안에 있을 때 쓴다(차단은 친구 해제·통지가 한 덩어리다).
    """
    import models

    row = models.Notification(
        user_id=user_id, kind=kind, body=(body or "")[:MAX_BODY],
        actor_id=actor_id, target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        quiet=bool(quiet), created_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    if commit:
        db.commit()
    return row


def unread_count(db, user_id: int) -> int:
    """배지 숫자. **quiet 은 세지 않는다.**"""
    import models

    return db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.read_at.is_(None),
        models.Notification.quiet.is_(False),
    ).count()


def list_for(db, user_id: int, *, before_id: Optional[int] = None, limit: int = DEFAULT_PAGE) -> List[Dict[str, Any]]:
    """커서(id 역순) 목록. 차단한 상대가 만든 알림은 제외한다 — 차단은 알림에도 적용된다."""
    import community_safety
    import models

    hidden = community_safety.hidden_user_ids(db, user_id)
    query = db.query(models.Notification).filter(models.Notification.user_id == user_id)
    if before_id:
        query = query.filter(models.Notification.id < before_id)
    if hidden:
        query = query.filter(
            (models.Notification.actor_id.is_(None)) | (~models.Notification.actor_id.in_(hidden))
        )
    rows = query.order_by(models.Notification.id.desc()).limit(max(1, min(limit, MAX_PAGE))).all()
    return [_public(db, row) for row in rows]


def _public(db, row) -> Dict[str, Any]:
    import community_identity

    actor = None
    if row.actor_id:
        profile = community_identity.get_profile(db, row.actor_id)
        # 프로필이 없으면 공개 이름이 없는 사용자다. 이메일·실명으로 대체하지 않는다.
        actor = community_identity.public_profile(profile) if profile else None
    return {
        "id": row.id,
        "kind": row.kind,
        "body": row.body or "",
        "actor": actor,
        "targetType": row.target_type,
        "targetId": row.target_id,
        "quiet": bool(row.quiet),
        "read": row.read_at is not None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


def mark_read(db, user_id: int, *, notification_ids: Optional[List[int]] = None) -> int:
    """id 를 주면 그것만, 안 주면 전부 읽음 처리한다."""
    import models

    query = db.query(models.Notification).filter(
        models.Notification.user_id == user_id, models.Notification.read_at.is_(None)
    )
    if notification_ids:
        query = query.filter(models.Notification.id.in_([int(i) for i in notification_ids]))
    updated = query.update({models.Notification.read_at: datetime.datetime.utcnow()},
                           synchronize_session=False)
    db.commit()
    return int(updated or 0)
