"""project_access.py — 프로젝트 권한 판정 (ADR-0024, 우선 백로그 11 TEAM-0).

**데이터 모델보다 이것이 먼저다.** 착수 시점에 `project.user_id != user.id` 형태의 검사가 42곳에
흩어져 있었다. workspace 를 도입하면서 그것들을 하나씩 고치면 반드시 한 곳을 빠뜨리고, **빠뜨린
곳이 곧 tenant isolation 구멍**이다. 그래서 판정을 먼저 한 함수로 모으고 그 안에서만 넓힌다.

■ 점진 이전이 안전한 이유
  아직 옮기지 않은 엔드포인트는 `user_id == user.id` 를 본다. 그건 workspace 멤버십보다 **더
  엄격하다** — 만든 사람만 통과한다. 그래서 이전이 덜 끝난 상태의 실패 방식은 "팀원이 아직 못
  한다"이지 "남이 볼 수 있다"가 아니다. 방향이 안전한 쪽이다.

■ 권한 표는 §4.17 이 정본이다
  owner > admin > editor > runner > viewer. 이 파일의 `ROLE_ACTIONS` 가 그 표를 그대로 옮긴 것이고,
  코드는 여기서 파생된다. 표와 코드가 어긋나면 테스트가 깨진다.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

VIEW, EDIT, RUN, DEPLOY, DELETE, SHARE = "view", "edit", "run", "deploy", "delete", "share"
ACTIONS = (VIEW, EDIT, RUN, DEPLOY, DELETE, SHARE)

ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_RUNNER, ROLE_VIEWER = (
    "owner", "admin", "editor", "runner", "viewer")
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_RUNNER, ROLE_VIEWER)

# §4.17 권한 표. 멤버 초대·workspace 삭제는 프로젝트 행위가 아니라 workspace 행위라
# `can_manage_members` / `can_transfer` 로 따로 둔다.
ROLE_ACTIONS = {
    ROLE_OWNER: {VIEW, EDIT, RUN, DEPLOY, DELETE, SHARE},
    ROLE_ADMIN: {VIEW, EDIT, RUN, DEPLOY, DELETE, SHARE},
    ROLE_EDITOR: {VIEW, EDIT, RUN, SHARE},
    ROLE_RUNNER: {VIEW, RUN},
    ROLE_VIEWER: {VIEW},
}


def workspaces_enabled() -> bool:
    """`WORKSPACE_V1`(기본 켜짐). 끄면 workspace 판정을 건너뛰고 개인 프로젝트 경로만 남는다 —
    이 모듈의 판정 함수는 그 경우에도 그대로 동작한다."""
    return os.getenv("WORKSPACE_V1", "1").strip().lower() not in {"0", "false", "off", "no"}


def role_of(db, workspace_id: Optional[int], user_id: Optional[int]) -> Optional[str]:
    """이 사용자의 workspace 역할. 멤버가 아니면 None."""
    import models

    if not workspace_id or not user_id or not workspaces_enabled():
        return None
    member = db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.workspace_id == workspace_id,
        models.WorkspaceMember.user_id == user_id,
        models.WorkspaceMember.status == "active",
    ).first()
    return member.role if member else None


def _friends_of(db, user_id: Optional[int]) -> set:
    import models

    if not user_id:
        return set()
    return {row.user_id for row in
            db.query(models.Friendship).filter(models.Friendship.friend_id == user_id).all()}


def can(db, user, project, action: str) -> bool:
    """이 사용자가 이 프로젝트에 이 행위를 할 수 있는가.

    판정 순서: 만든 사람 → workspace 역할 → 공개 범위(조회만).
    **개인 프로젝트의 동작은 도입 전과 같다** — `workspace_id` 가 비어 있으면 첫 줄과 마지막 줄만 탄다.
    """
    if project is None or action not in ACTIONS:
        return False
    user_id = getattr(user, "id", None)

    # 1) 만든 사람은 언제나 전부 할 수 있다(개인 프로젝트의 기존 동작).
    if user_id and project.user_id == user_id:
        return True

    # 2) workspace 멤버십
    role = role_of(db, getattr(project, "workspace_id", None), user_id)
    if role:
        return action in ROLE_ACTIONS.get(role, set())

    # 3) 공개 범위는 **조회만** 준다. 편집·실행·배포·삭제를 주지 않는다.
    if action != VIEW:
        return False
    visibility = getattr(project, "visibility", "private")
    if visibility == "public":
        return True
    if visibility == "friends":
        return bool(user_id) and project.user_id in _friends_of(db, user_id)
    return False


def require(db, user, project, action: str):
    """권한이 없으면 예외. 조회 권한조차 없으면 **존재를 알리지 않는다**(404 로 다뤄야 한다)."""
    if not can(db, user, project, action):
        raise PermissionError(action)
    return project


class PermissionError(Exception):
    """권한 없음. 호출부가 403(또는 조회 불가면 404)으로 바꾼다."""

    def __init__(self, action: str):
        super().__init__(f"이 프로젝트에 대한 '{action}' 권한이 없습니다.")
        self.action = action


def visible_projects_query(db, user):
    """목록 조회의 정본. 내가 만든 것 + 내가 속한 workspace 의 것."""
    import models

    user_id = getattr(user, "id", None)
    query = db.query(models.Project)
    if not user_id:
        return query.filter(models.Project.visibility == "public")

    workspace_ids = [row.workspace_id for row in db.query(models.WorkspaceMember).filter(
        models.WorkspaceMember.user_id == user_id,
        models.WorkspaceMember.status == "active",
    ).all()] if workspaces_enabled() else []

    condition = models.Project.user_id == user_id
    if workspace_ids:
        condition = condition | models.Project.workspace_id.in_(workspace_ids)
    return query.filter(condition)


def credential_owner_for(db, project) -> Optional[int]:
    """실행 시점에 **누구의 자격증명을 쓸 것인가.**

    개인 프로젝트는 지금과 같이 만든 사람이다. workspace 프로젝트는 **workspace owner** 를 쓴다 —
    그래야 만든 사람이 팀을 떠나도 자동화가 멈추지 않는다(§4.1 이 든 사용자 가치 그대로).
    workspace 전용 자격증명 저장소는 TEAM-2 의 범위이고, 그때 이 함수만 바꾸면 된다.
    """
    import models

    if project is None:
        return None
    workspace_id = getattr(project, "workspace_id", None)
    if workspace_id and workspaces_enabled():
        workspace = db.query(models.Workspace).filter(models.Workspace.id == workspace_id).first()
        if workspace and workspace.owner_id:
            return workspace.owner_id
    return project.user_id


# ── workspace 자체에 대한 권한 ──────────────────────────────────────────
def can_manage_members(role: Optional[str]) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def can_transfer(role: Optional[str]) -> bool:
    """workspace 삭제·소유권 이전은 owner 만."""
    return role == ROLE_OWNER
