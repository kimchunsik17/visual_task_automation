"""community_safety.py — 차단·신고·관리자 조치 (ADR-0020, 우선 백로그 22 SAFE-0·SAFE-2).

**차단은 한 곳에서 정하고 모두가 본다.** 글·답변·댓글·쪽지가 각자 차단 목록을 두면 "커뮤니티에서
차단했는데 쪽지는 오는" 상태가 반드시 생긴다. 그래서 `visible_author_ids` / `hidden_user_ids` 를
목록 쿼리가 직접 쓰게 하고, 화면에서 숨기는 방식은 쓰지 않는다 — 화면만 숨기면 API 로 그대로 보인다.

차단하면 세 가지가 함께 일어난다(제품 결정, 2026-08-29):
  1. 양쪽의 친구 관계가 해제된다
  2. 차단당한 쪽에도 알림이 간다 — 단 **이유는 싣지 않고** 조용한 등급으로
  3. 서로의 콘텐츠가 API 응답에서 빠진다

대부분의 플랫폼이 차단을 숨기는 이유는 보복 접촉과 우회 계정 때문이다. 알리기로 한 이상 그 위험은
신고율로 관측하고, 역효과가 보이면 §8 기준에 따라 되돌린다.
"""

from __future__ import annotations

import datetime
from typing import Iterable, List, Optional, Set

REPORT_REASONS = ("spam", "harassment", "inappropriate", "copyright", "other")
REPORT_TARGETS = ("post", "answer", "comment", "message", "profile", "template")
MODERATION_ACTIONS = ("hide", "remove", "suspend", "restore")

ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN = "user", "moderator", "admin"
STAFF_ROLES = (ROLE_MODERATOR, ROLE_ADMIN)


class SafetyError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 안전 규칙 위반."""


# ── 권한 ────────────────────────────────────────────────────────────────
def is_staff(user) -> bool:
    return getattr(user, "role", ROLE_USER) in STAFF_ROLES


def is_admin(user) -> bool:
    return getattr(user, "role", ROLE_USER) == ROLE_ADMIN


def bootstrap_admin_emails() -> tuple:
    """`ADMIN_EMAILS` 목록. **이 파일 하나에서만 읽는다.**

    예전에는 main 과 여기가 따로 읽어서, 판정하는 곳마다 결과가 달랐다 — 환경변수로만 어드민인
    계정이 관리자 화면은 열리는데 템플릿 수정은 막히는 식이다(실제로 겪었다).
    """
    import os

    return tuple(e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip())


def is_bootstrap_admin(user) -> bool:
    """DB 의 role 이 아직 user 라도 `ADMIN_EMAILS` 에 있으면 어드민으로 본다.

    `bootstrap_admins()` 가 아직 돌지 않은 환경에서도 첫 관리자가 갇히지 않게 하는 폴백이다.
    """
    email = (getattr(user, "email", "") or "").lower()
    return bool(email) and email in bootstrap_admin_emails()


def has_staff_access(user) -> bool:
    """운영 권한 판정의 **정본**. moderator·admin·부트스트랩 어드민을 모두 포함한다."""
    return bool(user) and (is_staff(user) or is_admin(user) or is_bootstrap_admin(user))


def bootstrap_admins(db) -> int:
    """`ADMIN_EMAILS` 의 계정을 admin 으로 승격한다. **첫 관리자를 만드는 용도로만** 남긴다.

    이후 권한 부여는 DB 에서 한다 — 예전처럼 환경변수만 보면 조치 이력에 "누가"를 사용자 id 로
    남길 수 없고, 권한을 바꾸려면 재배포해야 한다.
    """
    import models

    emails = bootstrap_admin_emails()
    if not emails:
        return 0
    promoted = 0
    for user in db.query(models.User).all():
        if (user.email or "").lower() in emails and user.role != ROLE_ADMIN:
            user.role = ROLE_ADMIN
            promoted += 1
    if promoted:
        db.commit()
    return promoted


# ── 차단 ────────────────────────────────────────────────────────────────
def hidden_user_ids(db, viewer_id: Optional[int]) -> Set[int]:
    """이 사용자에게 보이지 않아야 하는 상대들 — **내가 차단한 쪽과 나를 차단한 쪽 모두**.

    한쪽만 보면 차단당한 사람이 상대의 글을 계속 보게 된다.
    """
    import models

    if not viewer_id:
        return set()
    rows = db.query(models.Block).filter(
        (models.Block.blocker_id == viewer_id) | (models.Block.blocked_id == viewer_id)
    ).all()
    return {row.blocked_id if row.blocker_id == viewer_id else row.blocker_id for row in rows}


def is_blocked_between(db, a_id: int, b_id: int) -> bool:
    import models

    return db.query(models.Block).filter(
        ((models.Block.blocker_id == a_id) & (models.Block.blocked_id == b_id))
        | ((models.Block.blocker_id == b_id) & (models.Block.blocked_id == a_id))
    ).first() is not None


def block(db, blocker, blocked_user) -> "models.Block":
    """차단 + 친구 해제 + 조용한 통지. 세 가지가 한 트랜잭션에서 일어난다."""
    import models

    from notifications import notify

    if blocker.id == blocked_user.id:
        raise SafetyError("자기 자신은 차단할 수 없습니다.")

    existing = db.query(models.Block).filter(
        models.Block.blocker_id == blocker.id, models.Block.blocked_id == blocked_user.id
    ).first()
    if existing:
        return existing

    row = models.Block(blocker_id=blocker.id, blocked_id=blocked_user.id,
                       created_at=datetime.datetime.utcnow())
    db.add(row)

    # 친구 해제 — 양방향 행과 대기 중인 요청을 함께 정리한다.
    db.query(models.Friendship).filter(
        ((models.Friendship.user_id == blocker.id) & (models.Friendship.friend_id == blocked_user.id))
        | ((models.Friendship.user_id == blocked_user.id) & (models.Friendship.friend_id == blocker.id))
    ).delete(synchronize_session=False)
    db.query(models.FriendRequest).filter(
        models.FriendRequest.status == "pending",
        ((models.FriendRequest.from_user_id == blocker.id) & (models.FriendRequest.to_user_id == blocked_user.id))
        | ((models.FriendRequest.from_user_id == blocked_user.id) & (models.FriendRequest.to_user_id == blocker.id)),
    ).delete(synchronize_session=False)

    # 차단당한 쪽에도 알린다. **이유는 싣지 않는다** — 사유를 알리면 곧바로 해명·보복 접촉이 된다.
    notify(db, user_id=blocked_user.id, kind="blocked", quiet=True, commit=False,
           body="한 사용자가 회원님을 차단했습니다. 서로의 글과 쪽지가 더 이상 보이지 않습니다.")
    db.commit()
    return row


def unblock(db, blocker, blocked_user) -> bool:
    """차단만 해제한다. **친구 관계는 자동으로 복구하지 않는다** — 끊은 것을 되돌릴 결정은 사용자 몫이다."""
    import models

    deleted = db.query(models.Block).filter(
        models.Block.blocker_id == blocker.id, models.Block.blocked_id == blocked_user.id
    ).delete(synchronize_session=False)
    db.commit()
    return bool(deleted)


# ── 신고 ────────────────────────────────────────────────────────────────
def report(db, reporter, *, target_type: str, target_id: str, reason: str, detail: str = ""):
    import models

    if target_type not in REPORT_TARGETS:
        raise SafetyError(f"신고할 수 없는 대상입니다: {target_type}")
    if reason not in REPORT_REASONS:
        raise SafetyError(f"신고 사유가 올바르지 않습니다: {reason}")

    duplicate = db.query(models.Report).filter(
        models.Report.reporter_id == reporter.id,
        models.Report.target_type == target_type,
        models.Report.target_id == str(target_id),
        models.Report.status.in_(("open", "reviewing")),
    ).first()
    if duplicate:
        # 같은 대상을 반복 신고해도 큐를 부풀리지 않는다.
        return duplicate

    row = models.Report(
        target_type=target_type, target_id=str(target_id), reporter_id=reporter.id,
        reason=reason, detail=(detail or "")[:1000], status="open",
        created_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def resolve_report(db, staff, report_id: int, *, status: str) -> "models.Report":
    import models

    if status not in ("resolved", "rejected", "reviewing"):
        raise SafetyError("처리 상태가 올바르지 않습니다.")
    row = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not row:
        raise SafetyError("신고를 찾을 수 없습니다.")
    row.status = status
    # 보존 기간(30일)은 **신고 처리가 끝난 시점부터** 센다 — 조사 중에 근거가 사라지면 안 된다.
    row.resolved_at = datetime.datetime.utcnow() if status in ("resolved", "rejected") else None
    db.commit()
    return row


# ── 관리자 조치 ─────────────────────────────────────────────────────────
def record_action(db, staff, *, target_type: str, target_id: str, action: str, reason: str = "",
                  commit: bool = True):
    """조치 이력. **되돌리기(restore)도 하나의 조치로 남는다** — 무엇을 되돌렸는지도 기록이다."""
    import models

    if action not in MODERATION_ACTIONS:
        raise SafetyError(f"허용되지 않는 조치입니다: {action}")
    row = models.ModerationAction(
        target_type=target_type, target_id=str(target_id), admin_id=getattr(staff, "id", None),
        action=action, reason=(reason or "")[:500], created_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    if commit:
        db.commit()
    return row


# ── 신고 대상 미리보기 ──────────────────────────────────────────────────
def target_preview(db, target_type: str, target_id: str) -> Dict[str, Any]:
    """신고된 것이 **무엇인지** 보여준다. 이것 없이는 관리자가 판단할 근거가 없다.

    본문은 잘라서 준다 — 검수 화면은 판단하는 자리이지 읽는 자리가 아니다. 쪽지는 사적인 대화라
    **신고된 그 메시지만** 열린다(대화 전체를 열지 않는다).
    """
    import community_identity
    import models

    if target_type == "profile":
        profile = db.query(models.CommunityProfile).filter(
            models.CommunityProfile.user_id == int(target_id or 0)).first()
        if profile is None:
            return {"found": False}
        return {"found": True, "kind": "profile",
                "author": community_identity.public_profile(profile),
                "excerpt": profile.bio or "",
                "status": "suspended" if profile.suspended_until else "active"}

    model = {"post": models.Post, "answer": models.Answer,
             "comment": models.Comment, "message": models.Message}.get(target_type)
    if model is None:
        return {"found": False}
    try:
        row = db.query(model).filter(model.id == int(target_id)).first()
    except (TypeError, ValueError):
        return {"found": False}
    if row is None:
        return {"found": False}

    author_id = getattr(row, "author_id", None) or getattr(row, "sender_id", None)
    return {
        "found": True, "kind": target_type,
        "title": getattr(row, "title", None),
        "excerpt": (getattr(row, "body", "") or "")[:400],
        "author": community_identity.public_profile(community_identity.get_profile(db, author_id))
        if author_id else None,
        "status": getattr(row, "status", "sent"),
        "hidden": getattr(row, "deleted_at", None) is not None,
        "createdAt": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "postId": getattr(row, "post_id", None) if target_type == "answer" else (
            row.id if target_type == "post" else None),
    }


# ── 콘텐츠 조치 ─────────────────────────────────────────────────────────
def moderate_content(db, staff, *, target_type: str, target_id: str, action: str, reason: str = ""):
    """글·답변·댓글·쪽지를 숨기거나 되돌린다. **되돌리기도 하나의 조치로 남는다.**"""
    import datetime as _dt

    import models

    if action not in ("hide", "remove", "restore"):
        raise SafetyError(f"허용되지 않는 조치입니다: {action}")
    model = {"post": models.Post, "answer": models.Answer,
             "comment": models.Comment, "message": models.Message}.get(target_type)
    if model is None:
        raise SafetyError(f"조치할 수 없는 대상입니다: {target_type}")

    row = db.query(model).filter(model.id == int(target_id)).first()
    if row is None:
        raise SafetyError("대상을 찾을 수 없습니다.")

    if target_type == "message":
        # 쪽지는 본문을 지우되 자리는 남긴다(ADR-0022) — 대화 흐름이 끊기지 않게.
        if action == "restore":
            raise SafetyError("삭제한 쪽지는 되돌릴 수 없습니다. 본문이 남아 있지 않습니다.")
        row.status = "removed_by_admin"
        row.body = ""
    elif action == "restore":
        row.status = "published"
        row.deleted_at = None
    else:
        row.status = "removed" if action == "remove" else "hidden"
        # soft delete — 신고 조사 중에 근거가 사라지면 안 된다. 30일 뒤 정리된다.
        row.deleted_at = _dt.datetime.utcnow()

    record_action(db, staff, target_type=target_type, target_id=str(target_id),
                  action=action, reason=reason, commit=False)
    db.commit()
    return row


def recent_actions(db, *, limit: int = 50) -> List[Dict[str, Any]]:
    import community_identity
    import models

    rows = db.query(models.ModerationAction).order_by(
        models.ModerationAction.id.desc()).limit(max(1, min(limit, 200))).all()
    return [{
        "id": r.id, "targetType": r.target_type, "targetId": r.target_id,
        "action": r.action, "reason": r.reason,
        "admin": community_identity.public_profile(community_identity.get_profile(db, r.admin_id))
        if r.admin_id else None,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


# ── 긴급 스위치 ─────────────────────────────────────────────────────────
# 커뮤니티 쓰기 전체 중지. 환경변수가 아니라 **조치 이력**으로 상태를 표현한다 — 긴급 스위치가
# 재배포를 요구하면 정작 긴급할 때 쓸 수 없고, 조치 이력에 두면 누가 언제 껐는지가 공짜로 남는다.
# 읽기는 어느 경우에도 유지된다.
WRITES_TARGET_TYPE = "community"
WRITES_TARGET_ID = "writes"


def community_writes_enabled(db) -> bool:
    import models

    last = db.query(models.ModerationAction).filter(
        models.ModerationAction.target_type == WRITES_TARGET_TYPE,
        models.ModerationAction.target_id == WRITES_TARGET_ID,
    ).order_by(models.ModerationAction.id.desc()).first()
    return last is None or last.action == "restore"


def set_community_writes(db, staff, *, enabled: bool, reason: str = "") -> bool:
    record_action(db, staff, target_type=WRITES_TARGET_TYPE, target_id=WRITES_TARGET_ID,
                  action="restore" if enabled else "suspend", reason=reason)
    return enabled


def suspend_user(db, staff, target_user, *, days: int, reason: str = ""):
    """쓰기만 막고 읽기는 남긴다. 프로필이 없으면 만들지 않는다 — 커뮤니티에 들어온 적 없는 사용자다."""
    import community_identity

    from notifications import notify

    profile = community_identity.get_profile(db, target_user.id)
    if profile is None:
        raise SafetyError("이 사용자는 아직 커뮤니티 프로필이 없습니다.")
    profile.suspended_until = datetime.datetime.utcnow() + datetime.timedelta(days=max(1, int(days)))
    record_action(db, staff, target_type="profile", target_id=str(target_user.id),
                  action="suspend", reason=reason, commit=False)
    notify(db, user_id=target_user.id, kind="moderation", commit=False,
           body=f"커뮤니티 활동이 {days}일간 제한됩니다. 읽기는 계속 가능합니다.")
    db.commit()
    return profile


def restore_user(db, staff, target_user, *, reason: str = ""):
    import community_identity

    profile = community_identity.get_profile(db, target_user.id)
    if profile is None:
        raise SafetyError("이 사용자는 아직 커뮤니티 프로필이 없습니다.")
    profile.suspended_until = None
    record_action(db, staff, target_type="profile", target_id=str(target_user.id),
                  action="restore", reason=reason, commit=False)
    db.commit()
    return profile
