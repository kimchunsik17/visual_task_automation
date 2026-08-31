"""workspaces.py — workspace·멤버·초대·감사 (ADR-0024, 우선 백로그 11 TEAM-1).

권한 판정은 `project_access` 가 한다. 이 파일은 **누가 멤버인가**를 관리하고 그 변경을 감사에 남긴다.

두 가지 규칙이 전체를 관통한다.

  - **초대는 핸들로 한다.** 이메일로 초대하면 이메일만 알아도 계정 존재 여부가 확인된다.
  - **마지막 owner 는 나갈 수 없다.** 주인 없는 workspace 가 생기면 아무도 멤버를 관리할 수 없고,
    그 안의 프로젝트는 자격증명 주체를 잃는다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

import project_access

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,30})[a-z0-9]$")
RESERVED_SLUGS = {"admin", "api", "app", "official", "workflow", "workflow-ai", "system", "new", "me"}


class WorkspaceError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 규칙 위반."""


def normalize_slug(raw: str) -> str:
    slug = str(raw or "").strip().lower()
    if not SLUG_RE.match(slug) or "--" in slug:
        raise WorkspaceError("주소는 소문자·숫자·하이픈 3~32자여야 하고, 하이픈으로 시작·끝나거나 연달아 쓸 수 없습니다.")
    if slug in RESERVED_SLUGS:
        raise WorkspaceError("이미 예약된 주소입니다.")
    return slug


def audit(db, *, workspace_id: Optional[int], actor_id: Optional[int], action: str,
          resource_type: str = "", resource_id: str = "", metadata: Optional[Dict] = None,
          commit: bool = True):
    """권한·소유·자격증명 변경만 남긴다 — 실행 이력을 섞으면 정작 봐야 할 것이 파묻힌다."""
    import models

    row = models.AuditEvent(
        workspace_id=workspace_id, actor_id=actor_id, action=action,
        resource_type=resource_type or None, resource_id=str(resource_id) or None,
        event_metadata=metadata or {}, created_at=datetime.datetime.utcnow(),
    )
    db.add(row)
    if commit:
        db.commit()
    return row


# ── 생성·멤버 ───────────────────────────────────────────────────────────
def create_workspace(db, owner, *, slug: str, name: str):
    import models

    normalized = normalize_slug(slug)
    if db.query(models.Workspace).filter(models.Workspace.slug == normalized).first():
        raise WorkspaceError("이미 사용 중인 주소입니다.")

    workspace = models.Workspace(slug=normalized, name=(name or normalized)[:80],
                                 owner_id=owner.id, created_at=datetime.datetime.utcnow())
    db.add(workspace)
    db.flush()
    db.add(models.WorkspaceMember(workspace_id=workspace.id, user_id=owner.id,
                                  role=project_access.ROLE_OWNER, status="active",
                                  joined_at=datetime.datetime.utcnow()))
    audit(db, workspace_id=workspace.id, actor_id=owner.id, action="workspace.create",
          resource_type="workspace", resource_id=str(workspace.id), commit=False)
    db.commit()
    return workspace


def members(db, workspace_id: int) -> List[Dict[str, Any]]:
    import community_identity
    import models

    rows = db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.workspace_id == workspace_id,
        models.WorkspaceMember.status == "active",
    ).all()
    return [{
        "userId": row.user_id, "role": row.role,
        "profile": community_identity.public_profile(community_identity.get_profile(db, row.user_id)),
        "joinedAt": row.joined_at.isoformat() if row.joined_at else None,
    } for row in rows]


def owner_count(db, workspace_id: int) -> int:
    import models

    return db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.workspace_id == workspace_id,
        models.WorkspaceMember.role == project_access.ROLE_OWNER,
        models.WorkspaceMember.status == "active",
    ).count()


def set_role(db, actor, workspace, target_user_id: int, role: str):
    import models

    if role not in project_access.ROLES:
        raise WorkspaceError(f"허용되지 않는 역할입니다: {role}")
    actor_role = project_access.role_of(db, workspace.id, actor.id)
    if not project_access.can_manage_members(actor_role):
        raise WorkspaceError("멤버 역할을 바꿀 권한이 없습니다.")
    # owner 를 만들거나 내리는 것은 owner 만 한다 — admin 이 스스로 owner 가 될 수 없어야 한다.
    member = db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.workspace_id == workspace.id,
        models.WorkspaceMember.user_id == target_user_id,
        models.WorkspaceMember.status == "active",
    ).first()
    if member is None:
        raise WorkspaceError("멤버를 찾을 수 없습니다.")
    if (role == project_access.ROLE_OWNER or member.role == project_access.ROLE_OWNER) \
            and not project_access.can_transfer(actor_role):
        raise WorkspaceError("소유자 역할은 소유자만 바꿀 수 있습니다.")
    if member.role == project_access.ROLE_OWNER and role != project_access.ROLE_OWNER \
            and owner_count(db, workspace.id) <= 1:
        raise WorkspaceError("마지막 소유자의 역할은 바꿀 수 없습니다. 먼저 다른 소유자를 지정해주세요.")

    previous, member.role = member.role, role
    audit(db, workspace_id=workspace.id, actor_id=actor.id, action="member.role_change",
          resource_type="user", resource_id=str(target_user_id),
          metadata={"from": previous, "to": role}, commit=False)
    db.commit()
    return member


def remove_member(db, actor, workspace, target_user_id: int):
    import models

    actor_role = project_access.role_of(db, workspace.id, actor.id)
    leaving_self = actor.id == target_user_id
    if not leaving_self and not project_access.can_manage_members(actor_role):
        raise WorkspaceError("멤버를 내보낼 권한이 없습니다.")

    member = db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.workspace_id == workspace.id,
        models.WorkspaceMember.user_id == target_user_id,
        models.WorkspaceMember.status == "active",
    ).first()
    if member is None:
        raise WorkspaceError("멤버를 찾을 수 없습니다.")
    # **마지막 owner 는 나갈 수 없다** — 주인 없는 workspace 는 아무도 관리할 수 없고,
    # 그 안의 프로젝트는 자격증명 주체를 잃는다.
    if member.role == project_access.ROLE_OWNER and owner_count(db, workspace.id) <= 1:
        raise WorkspaceError("마지막 소유자는 나갈 수 없습니다. 먼저 소유권을 넘겨주세요.")

    member.status = "removed"
    audit(db, workspace_id=workspace.id, actor_id=actor.id,
          action="member.leave" if leaving_self else "member.remove",
          resource_type="user", resource_id=str(target_user_id), commit=False)
    db.commit()


# ── 초대 ────────────────────────────────────────────────────────────────
def invite(db, actor, workspace, *, handle: str, role: str = project_access.ROLE_VIEWER):
    import community_identity
    import models
    import notifications

    if role not in project_access.ROLES:
        raise WorkspaceError(f"허용되지 않는 역할입니다: {role}")
    if role == project_access.ROLE_OWNER:
        raise WorkspaceError("소유자로는 초대할 수 없습니다. 초대 후 소유권을 넘겨주세요.")
    if not project_access.can_manage_members(project_access.role_of(db, workspace.id, actor.id)):
        raise WorkspaceError("초대할 권한이 없습니다.")

    profile = community_identity.find_by_handle(db, handle)
    if profile is None:
        raise WorkspaceError("해당 핸들의 사용자를 찾을 수 없습니다. 상대가 커뮤니티 핸들을 먼저 만들어야 합니다.")
    if project_access.role_of(db, workspace.id, profile.user_id):
        raise WorkspaceError("이미 이 workspace 의 멤버입니다.")

    existing = db.query(models.WorkspaceInvite).filter(
        models.WorkspaceInvite.workspace_id == workspace.id,
        models.WorkspaceInvite.handle == profile.handle,
        models.WorkspaceInvite.status == "pending",
    ).first()
    if existing:
        return existing

    row = models.WorkspaceInvite(workspace_id=workspace.id, handle=profile.handle, role=role,
                                 invited_by=actor.id, status="pending",
                                 created_at=datetime.datetime.utcnow())
    db.add(row)
    notifications.notify(db, user_id=profile.user_id, kind="workspace_invite", actor_id=actor.id,
                         target_type="workspace", target_id=str(workspace.id), commit=False,
                         body=f"'{workspace.name}' 워크스페이스에 {role} 로 초대받았습니다.")
    audit(db, workspace_id=workspace.id, actor_id=actor.id, action="member.invite",
          resource_type="handle", resource_id=profile.handle, metadata={"role": role}, commit=False)
    db.commit()
    return row


def respond_to_invite(db, user, invite_id: int, *, accept: bool):
    import community_identity
    import models

    row = db.query(models.WorkspaceInvite).filter(models.WorkspaceInvite.id == invite_id).first()
    if row is None or row.status != "pending":
        raise WorkspaceError("초대를 찾을 수 없습니다.")
    profile = community_identity.get_profile(db, user.id)
    # 초대받지 않은 사람이 남의 초대를 수락할 수 없다.
    if profile is None or profile.handle != row.handle:
        raise WorkspaceError("초대를 찾을 수 없습니다.")

    row.status = "accepted" if accept else "declined"
    if accept:
        db.add(models.WorkspaceMember(workspace_id=row.workspace_id, user_id=user.id,
                                      role=row.role, status="active", invited_by=row.invited_by,
                                      joined_at=datetime.datetime.utcnow()))
        audit(db, workspace_id=row.workspace_id, actor_id=user.id, action="member.join",
              resource_type="user", resource_id=str(user.id), metadata={"role": row.role},
              commit=False)
    db.commit()
    return row


def pending_invites(db, user) -> List[Dict[str, Any]]:
    import community_identity
    import models

    profile = community_identity.get_profile(db, user.id)
    if profile is None:
        return []
    rows = db.query(models.WorkspaceInvite).filter(
        models.WorkspaceInvite.handle == profile.handle,
        models.WorkspaceInvite.status == "pending",
    ).all()
    result = []
    for row in rows:
        workspace = db.query(models.Workspace).filter(
            models.Workspace.id == row.workspace_id).first()
        if workspace:
            result.append({"id": row.id, "role": row.role, "workspace": {
                "id": workspace.id, "slug": workspace.slug, "name": workspace.name}})
    return result


def my_workspaces(db, user) -> List[Dict[str, Any]]:
    import models

    rows = db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.user_id == user.id,
        models.WorkspaceMember.status == "active",
    ).all()
    result = []
    for row in rows:
        workspace = db.query(models.Workspace).filter(
            models.Workspace.id == row.workspace_id).first()
        if workspace:
            result.append({"id": workspace.id, "slug": workspace.slug, "name": workspace.name,
                           "role": row.role, "memberCount": len(members(db, workspace.id))})
    return result


# ── 프로젝트 이동 ───────────────────────────────────────────────────────
def move_project(db, actor, project, *, workspace_id: Optional[int]):
    """개인 ↔ workspace 이동. 옮기는 것은 **소유자 또는 대상 workspace 의 owner/admin** 만."""
    import models

    if project.user_id != actor.id:
        # 만든 사람이 아니면 현재 workspace 의 관리자여야 한다.
        if not project_access.can_manage_members(
                project_access.role_of(db, project.workspace_id, actor.id)):
            raise WorkspaceError("이 프로젝트를 옮길 권한이 없습니다.")
    if workspace_id is not None:
        if not project_access.can_manage_members(project_access.role_of(db, workspace_id, actor.id)):
            raise WorkspaceError("대상 workspace 의 관리자만 프로젝트를 들여올 수 있습니다.")

    previous, project.workspace_id = project.workspace_id, workspace_id
    audit(db, workspace_id=workspace_id or previous, actor_id=actor.id, action="project.move",
          resource_type="project", resource_id=str(project.id),
          metadata={"from": previous, "to": workspace_id}, commit=False)
    db.commit()
    return project


def recent_events(db, workspace_id: int, *, limit: int = 50) -> List[Dict[str, Any]]:
    import community_identity
    import models

    rows = db.query(models.AuditEvent).filter(
        models.AuditEvent.workspace_id == workspace_id
    ).order_by(models.AuditEvent.id.desc()).limit(max(1, min(limit, 200))).all()
    return [{
        "id": r.id, "action": r.action, "resourceType": r.resource_type,
        "resourceId": r.resource_id, "metadata": r.event_metadata or {},
        "actor": community_identity.public_profile(community_identity.get_profile(db, r.actor_id))
        if r.actor_id else None,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
