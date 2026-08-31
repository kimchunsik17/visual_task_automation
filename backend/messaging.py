"""messaging.py — 친구 간 1:1 쪽지 (ADR-0022, 우선 백로그 24 MSG-0·1·3).

**수신 범위 판정이 한 곳에 있다**(`can_message`). 전송 API 와 SSE 구독이 **같은 함수**를 쓴다 —
전송만 막고 구독을 열어 두면 차단한 상대의 메시지가 스트림으로 흘러 들어온다.

판정 순서는 차단 → 친구 → 거부다(친구 한정, 2026-08-29 결정). 친구가 아닌 상대에게는 아예 보낼 수
없고, 대화하려면 친구 요청을 거친다 — 이미 있는 친구 기능이 그대로 "이 사람과 이야기해도 될까요"를
묻는 관문이 된다. 그래서 `MessageRequest` 와 수락 흐름이 없다.

몇 가지 규칙이 이 파일 전체를 관통한다.

  - **친구가 끊기면 읽기만 남고 전송이 막힌다.** 대화를 지우지는 않는다 — 신고 조사 근거가 사라진다.
  - **삭제는 내 화면에서만이다.** 양쪽에서 사라지면 신고가 들어왔을 때 확인할 방법이 없다.
  - **본문은 로그·telemetry·오류 payload 에 남기지 않는다.** 오류 문구에 본문을 넣지 않는다.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

MAX_BODY = 4000
MAX_ATTACHMENTS = 5
DEFAULT_PAGE = 50
MAX_PAGE = 200


class MessagingError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 규칙 위반. **본문을 담지 않는다.**"""


class MessagingForbidden(MessagingError):
    """수신 범위 밖. 차단인지 비친구인지 구분해 알려주지 않는다 — 차단 사실이 새면 안 된다."""


# ── 수신 범위 ───────────────────────────────────────────────────────────
def are_friends(db, a_id: int, b_id: int) -> bool:
    import models

    return db.query(models.Friendship).filter(
        models.Friendship.user_id == a_id, models.Friendship.friend_id == b_id
    ).first() is not None


def can_message(db, sender_id: int, recipient_id: int) -> bool:
    """**전송과 구독이 함께 쓰는 판정.** 차단 → 친구 → 거부."""
    import community_safety

    if sender_id == recipient_id:
        return False
    if community_safety.is_blocked_between(db, sender_id, recipient_id):
        return False
    return are_friends(db, sender_id, recipient_id)


def require_can_message(db, sender_id: int, recipient_id: int) -> None:
    if not can_message(db, sender_id, recipient_id):
        # 차단인지 비친구인지 구분해 알려주지 않는다.
        raise MessagingForbidden("이 사용자에게는 쪽지를 보낼 수 없습니다. 먼저 친구가 되어야 합니다.")


# ── 대화 ────────────────────────────────────────────────────────────────
def _pair(a_id: int, b_id: int) -> Tuple[int, int]:
    """작은 id 가 항상 a 다 — 정렬하지 않으면 같은 상대와 대화가 두 개 생긴다."""
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def find_conversation(db, a_id: int, b_id: int):
    import models

    low, high = _pair(a_id, b_id)
    return db.query(models.Conversation).filter(
        models.Conversation.user_a_id == low, models.Conversation.user_b_id == high
    ).first()


def open_conversation(db, user, other_user):
    """대화를 열거나 이미 있는 것을 돌려준다. 여는 것 자체가 수신 범위 검사를 지난다."""
    import models

    require_can_message(db, user.id, other_user.id)
    existing = find_conversation(db, user.id, other_user.id)
    if existing:
        return existing

    low, high = _pair(user.id, other_user.id)
    conversation = models.Conversation(user_a_id=low, user_b_id=high,
                                       created_at=datetime.datetime.utcnow())
    db.add(conversation)
    db.flush()
    for member_id in (low, high):
        db.add(models.ConversationMember(conversation_id=conversation.id, user_id=member_id,
                                         last_read_message_id=0))
    db.commit()
    return conversation


def participants(conversation) -> Tuple[int, int]:
    return conversation.user_a_id, conversation.user_b_id


def other_participant(conversation, user_id: int) -> int:
    return conversation.user_b_id if conversation.user_a_id == user_id else conversation.user_a_id


def is_participant(conversation, user_id: int) -> bool:
    return user_id in participants(conversation)


def member_of(db, conversation_id: int, user_id: int):
    import models

    return db.query(models.ConversationMember).filter(
        models.ConversationMember.conversation_id == conversation_id,
        models.ConversationMember.user_id == user_id,
    ).first()


def require_participant(db, conversation, user_id: int):
    """참가자가 아니면 **404 로 취급한다** — 대화 id 를 찍어보며 존재를 확인할 수 없어야 한다."""
    if conversation is None or not is_participant(conversation, user_id):
        raise MessagingError("대화를 찾을 수 없습니다.")
    return conversation


# ── 전송 ────────────────────────────────────────────────────────────────
def send_message(db, sender, conversation, *, body: str, artifact_ids: Optional[List[str]] = None):
    """쪽지 한 통. 첨부는 ADR-0018 과 **같은 검증 경로**를 쓴다 — 새 저장 규칙을 만들지 않는다."""
    import models

    require_participant(db, conversation, sender.id)
    recipient_id = other_participant(conversation, sender.id)
    # 친구가 끊겼거나 차단되면 여기서 막힌다. 기존 대화는 읽기로만 남는다.
    require_can_message(db, sender.id, recipient_id)

    clean = str(body or "").strip()[:MAX_BODY]
    artifact_ids = [str(a) for a in (artifact_ids or []) if str(a).strip()][:MAX_ATTACHMENTS]
    if not clean and not artifact_ids:
        raise MessagingError("내용을 입력해주세요.")

    if artifact_ids:
        import delivery_attachments
        from artifacts import ArtifactError

        try:
            delivery_attachments.validate_attachments(
                db, artifact_ids, owner_user_id=sender.id, project_id=None,
                policy=delivery_attachments.policy_for("discord"), node_type="message",
            )
        except ArtifactError as exc:
            # 사용자 문구만 옮긴다. 파일 경로·저장 이름은 여기까지 오지 않는다(ADR-0018).
            raise MessagingError(exc.error.user_message) from None

    message = models.Message(
        conversation_id=conversation.id, sender_id=sender.id, body=clean,
        attachment_artifact_ids=artifact_ids, status="sent", deleted_for_user_ids=[],
        created_at=datetime.datetime.utcnow(),
    )
    db.add(message)
    conversation.last_message_at = message.created_at
    # 보낸 사람에게는 이미 읽은 것이다.
    sender_member = member_of(db, conversation.id, sender.id)
    db.commit()
    if sender_member:
        sender_member.last_read_message_id = message.id
        db.commit()
    return message


# ── 조회 ────────────────────────────────────────────────────────────────
def public_message(message, viewer_id: int) -> Dict[str, Any]:
    return {
        "id": message.id,
        "conversationId": message.conversation_id,
        "senderId": message.sender_id,
        "mine": message.sender_id == viewer_id,
        "body": "(관리자가 삭제한 메시지입니다)" if message.status == "removed_by_admin" else message.body,
        "attachments": list(message.attachment_artifact_ids or []),
        "removed": message.status == "removed_by_admin",
        "createdAt": message.created_at.isoformat() if message.created_at else None,
    }


def list_messages(db, conversation, viewer_id: int, *, before_id: Optional[int] = None,
                  after_id: Optional[int] = None, limit: int = DEFAULT_PAGE) -> List:
    import models

    require_participant(db, conversation, viewer_id)
    query = db.query(models.Message).filter(models.Message.conversation_id == conversation.id)
    if before_id:
        query = query.filter(models.Message.id < before_id)
    if after_id:
        query = query.filter(models.Message.id > after_id)
    rows = query.order_by(
        models.Message.id.asc() if after_id else models.Message.id.desc()
    ).limit(max(1, min(limit, MAX_PAGE))).all()
    if not after_id:
        rows = list(reversed(rows))
    # 내가 지운 것만 내 화면에서 빠진다. 상대의 화면은 그대로다.
    return [m for m in rows if viewer_id not in (m.deleted_for_user_ids or [])]


def list_conversations(db, user_id: int, *, limit: int = 50) -> List[Dict[str, Any]]:
    """내 대화 목록. 차단한 상대의 대화는 빠지고, 숨긴 대화도 빠진다."""
    import community_identity
    import community_safety
    import models

    hidden_users = community_safety.hidden_user_ids(db, user_id)
    rows = db.query(models.Conversation).filter(
        (models.Conversation.user_a_id == user_id) | (models.Conversation.user_b_id == user_id)
    ).order_by(models.Conversation.last_message_at.desc().nullslast()).limit(limit).all()

    result = []
    for conversation in rows:
        other_id = other_participant(conversation, user_id)
        if other_id in hidden_users:
            continue
        member = member_of(db, conversation.id, user_id)
        if member and member.hidden_at and conversation.last_message_at \
                and conversation.last_message_at <= member.hidden_at:
            continue   # 숨긴 뒤 새 메시지가 없으면 목록에 다시 올리지 않는다

        last = db.query(models.Message).filter(
            models.Message.conversation_id == conversation.id
        ).order_by(models.Message.id.desc()).first()
        unread = db.query(models.Message).filter(
            models.Message.conversation_id == conversation.id,
            models.Message.id > (member.last_read_message_id if member else 0),
            models.Message.sender_id != user_id,
        ).count()
        result.append({
            "id": conversation.id,
            "other": community_identity.public_profile(community_identity.get_profile(db, other_id)),
            "otherId": other_id,
            "lastMessage": (last.body[:80] if last and last.status == "sent" else "") if last else "",
            "lastMessageAt": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
            "unread": unread,
            # 친구가 끊기거나 차단되면 읽기만 남는다.
            "canSend": can_message(db, user_id, other_id),
        })
    return result


def unread_total(db, user_id: int) -> int:
    import models

    total = 0
    for member in db.query(models.ConversationMember).filter(
            models.ConversationMember.user_id == user_id).all():
        total += db.query(models.Message).filter(
            models.Message.conversation_id == member.conversation_id,
            models.Message.id > (member.last_read_message_id or 0),
            models.Message.sender_id != user_id,
        ).count()
    return total


# ── 읽음·숨김·삭제 ──────────────────────────────────────────────────────
def mark_read(db, conversation, user_id: int, *, up_to_id: Optional[int] = None) -> int:
    import models

    require_participant(db, conversation, user_id)
    member = member_of(db, conversation.id, user_id)
    if member is None:
        return 0
    if up_to_id is None:
        last = db.query(models.Message).filter(
            models.Message.conversation_id == conversation.id
        ).order_by(models.Message.id.desc()).first()
        up_to_id = last.id if last else 0
    member.last_read_message_id = max(member.last_read_message_id or 0, int(up_to_id))
    db.commit()
    return member.last_read_message_id


def hide_conversation(db, conversation, user_id: int) -> None:
    """**내 목록에서만** 숨긴다. 상대의 대화와 메시지는 그대로다."""
    require_participant(db, conversation, user_id)
    member = member_of(db, conversation.id, user_id)
    if member:
        member.hidden_at = datetime.datetime.utcnow()
        db.commit()


def delete_for_me(db, message, user_id: int) -> None:
    """내 화면에서만 지운다. 양쪽에서 지우면 신고 조사가 불가능해진다."""
    from sqlalchemy.orm.attributes import flag_modified

    ids = list(message.deleted_for_user_ids or [])
    if user_id not in ids:
        ids.append(user_id)
        message.deleted_for_user_ids = ids
        flag_modified(message, "deleted_for_user_ids")
        db.commit()


def remove_by_admin(db, staff, message, *, reason: str = "") -> None:
    """관리자 삭제는 별도 상태로 남는다 — 본문은 지우되 흔적은 남긴다."""
    import community_safety

    message.status = "removed_by_admin"
    message.body = ""
    community_safety.record_action(db, staff, target_type="message", target_id=str(message.id),
                                   action="remove", reason=reason, commit=False)
    db.commit()
