"""Workspace/RBAC Team MVP (ADR-0024, 우선 백로그 11) 계약 테스트.

§4.17 검증 매트릭스의 층을 따른다 — 회귀·권한 표·격리·초대·자격증명·감사·소유권.

이 파일이 지키는 두 문장:
  1. **개인 프로젝트의 동작은 도입 전과 같다.** 회귀가 0이어야 한다.
  2. **권한 표(§4.17)와 코드가 어긋나면 실패한다.**
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import community_identity as identity
import models
import project_access as access
import workspaces as ws
from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([models.User(id=i, name=f"u{i}", email=f"u{i}@t.com", role="user")
                     for i in range(1, 7)])
    session.commit()
    for uid in range(1, 7):
        identity.create_profile(session, session.query(models.User).get(uid), handle=f"user-{uid}")
    yield session
    session.close()


def _u(db, uid):
    return db.query(models.User).get(uid)


def _project(db, user_id=1, visibility="private", workspace_id=None):
    project = models.Project(user_id=user_id, title="p", graph_data={"nodes": [], "edges": []},
                             visibility=visibility, workspace_id=workspace_id)
    db.add(project)
    db.commit()
    return project


def _workspace(db, owner_id=1, slug="team-one"):
    return ws.create_workspace(db, _u(db, owner_id), slug=slug, name="팀")


def _join(db, workspace, user_id, role):
    db.add(models.WorkspaceMember(workspace_id=workspace.id, user_id=user_id,
                                  role=role, status="active"))
    db.commit()


# ── 1. 회귀 — 개인 프로젝트 동작은 그대로다 ────────────────────────────
def test_owner_can_do_everything_to_their_own_project(db):
    project = _project(db)
    for action in access.ACTIONS:
        assert access.can(db, _u(db, 1), project, action) is True


@pytest.mark.parametrize("visibility, viewer_is_friend, expected_view", [
    ("private", False, False),
    ("friends", False, False),
    ("friends", True, True),
    ("public", False, True),
])
def test_visibility_grants_view_only(db, visibility, viewer_is_friend, expected_view):
    """공개 범위는 **조회만** 준다 — 편집·실행·배포·삭제를 주지 않는다."""
    project = _project(db, visibility=visibility)
    if viewer_is_friend:
        db.add(models.Friendship(user_id=1, friend_id=2))
        db.commit()
    assert access.can(db, _u(db, 2), project, access.VIEW) is expected_view
    for action in (access.EDIT, access.RUN, access.DEPLOY, access.DELETE):
        assert access.can(db, _u(db, 2), project, action) is False


def test_anonymous_sees_only_public(db):
    assert access.can(db, None, _project(db, visibility="public"), access.VIEW) is True
    assert access.can(db, None, _project(db, visibility="friends"), access.VIEW) is False
    assert access.can(db, None, _project(db, visibility="private"), access.VIEW) is False


def test_personal_projects_use_their_creators_credentials(db):
    project = _project(db)
    assert access.credential_owner_for(db, project) == 1


# ── 2. 권한 표 (§4.17 이 정본) ──────────────────────────────────────────
PERMISSION_TABLE = {
    "owner":  {"view": True, "edit": True,  "run": True,  "deploy": True,  "delete": True,  "share": True},
    "admin":  {"view": True, "edit": True,  "run": True,  "deploy": True,  "delete": True,  "share": True},
    "editor": {"view": True, "edit": True,  "run": True,  "deploy": False, "delete": False, "share": True},
    "runner": {"view": True, "edit": False, "run": True,  "deploy": False, "delete": False, "share": False},
    "viewer": {"view": True, "edit": False, "run": False, "deploy": False, "delete": False, "share": False},
}


@pytest.mark.parametrize("role", list(PERMISSION_TABLE))
@pytest.mark.parametrize("action", list(access.ACTIONS))
def test_every_role_action_combination_matches_the_table(db, role, action):
    """표와 코드가 어긋나면 여기서 깨진다 — 표가 정본이다."""
    workspace = _workspace(db)
    project = _project(db, user_id=1, workspace_id=workspace.id)
    _join(db, workspace, 2, role)
    assert access.can(db, _u(db, 2), project, action) is PERMISSION_TABLE[role][action]


def test_a_removed_member_loses_access_immediately(db):
    workspace = _workspace(db)
    project = _project(db, workspace_id=workspace.id)
    _join(db, workspace, 2, "editor")
    assert access.can(db, _u(db, 2), project, access.EDIT) is True

    ws.remove_member(db, _u(db, 1), workspace, 2)
    assert access.can(db, _u(db, 2), project, access.EDIT) is False
    assert access.can(db, _u(db, 2), project, access.VIEW) is False


# ── 3. 격리 ─────────────────────────────────────────────────────────────
def test_other_workspaces_projects_are_invisible(db):
    mine = _workspace(db, owner_id=1, slug="team-mine")
    theirs = _workspace(db, owner_id=3, slug="team-theirs")
    my_project = _project(db, user_id=1, workspace_id=mine.id)
    their_project = _project(db, user_id=3, workspace_id=theirs.id)
    _join(db, mine, 2, "editor")

    for action in access.ACTIONS:
        assert access.can(db, _u(db, 2), their_project, action) is False, action

    visible = [p.id for p in access.visible_projects_query(db, _u(db, 2)).all()]
    assert visible == [my_project.id], "목록에도 섞이지 않는다"


def test_non_members_cannot_see_a_workspace_at_all(db):
    workspace = _workspace(db)
    assert access.role_of(db, workspace.id, 2) is None


def test_visible_projects_include_my_own_and_my_workspaces(db):
    workspace = _workspace(db)
    _join(db, workspace, 2, "viewer")
    own = _project(db, user_id=2)
    team = _project(db, user_id=1, workspace_id=workspace.id)
    _project(db, user_id=3)   # 남의 개인 프로젝트

    visible = {p.id for p in access.visible_projects_query(db, _u(db, 2)).all()}
    assert visible == {own.id, team.id}


def test_turning_workspaces_off_leaves_only_personal_projects(db, monkeypatch):
    workspace = _workspace(db)
    project = _project(db, user_id=1, workspace_id=workspace.id)
    _join(db, workspace, 2, "admin")
    assert access.can(db, _u(db, 2), project, access.EDIT) is True

    monkeypatch.setenv("WORKSPACE_V1", "0")
    assert access.can(db, _u(db, 2), project, access.EDIT) is False
    assert access.can(db, _u(db, 1), project, access.EDIT) is True, "만든 사람은 그대로다"


# ── 4. 초대 ─────────────────────────────────────────────────────────────
def test_invite_flow_by_handle(db):
    workspace = _workspace(db)
    invite = ws.invite(db, _u(db, 1), workspace, handle="user-2", role="editor")
    assert invite.status == "pending"
    # 초대 알림이 §4.16 의 알림함으로 간다.
    assert db.query(models.Notification).filter(
        models.Notification.user_id == 2, models.Notification.kind == "workspace_invite").count() == 1

    ws.respond_to_invite(db, _u(db, 2), invite.id, accept=True)
    assert access.role_of(db, workspace.id, 2) == "editor"


def test_you_cannot_accept_someone_elses_invite(db):
    workspace = _workspace(db)
    invite = ws.invite(db, _u(db, 1), workspace, handle="user-2")
    with pytest.raises(ws.WorkspaceError):
        ws.respond_to_invite(db, _u(db, 3), invite.id, accept=True)
    assert access.role_of(db, workspace.id, 3) is None


def test_declining_leaves_no_membership(db):
    workspace = _workspace(db)
    invite = ws.invite(db, _u(db, 1), workspace, handle="user-2")
    ws.respond_to_invite(db, _u(db, 2), invite.id, accept=False)
    assert access.role_of(db, workspace.id, 2) is None


def test_users_without_a_handle_cannot_be_invited(db):
    """핸들이 없는 사용자는 공개 표면에 존재하지 않는다(ADR-0020) — 초대도 마찬가지다."""
    db.add(models.User(id=99, name="무핸들", email="n@t.com"))
    db.commit()
    workspace = _workspace(db)
    with pytest.raises(ws.WorkspaceError):
        ws.invite(db, _u(db, 1), workspace, handle="nobody-here")


def test_duplicate_invites_do_not_pile_up(db):
    workspace = _workspace(db)
    first = ws.invite(db, _u(db, 1), workspace, handle="user-2")
    assert ws.invite(db, _u(db, 1), workspace, handle="user-2").id == first.id


def test_only_managers_invite_and_never_as_owner(db):
    workspace = _workspace(db)
    _join(db, workspace, 2, "editor")
    with pytest.raises(ws.WorkspaceError):
        ws.invite(db, _u(db, 2), workspace, handle="user-3")
    with pytest.raises(ws.WorkspaceError):
        ws.invite(db, _u(db, 1), workspace, handle="user-3", role="owner")


# ── 5. 소유권 ───────────────────────────────────────────────────────────
def test_the_last_owner_cannot_leave(db):
    """주인 없는 workspace 는 아무도 관리할 수 없고, 그 안의 프로젝트는 자격증명 주체를 잃는다."""
    workspace = _workspace(db)
    with pytest.raises(ws.WorkspaceError) as exc:
        ws.remove_member(db, _u(db, 1), workspace, 1)
    assert "마지막 소유자" in str(exc.value)


def test_the_last_owner_cannot_be_demoted(db):
    workspace = _workspace(db)
    with pytest.raises(ws.WorkspaceError):
        ws.set_role(db, _u(db, 1), workspace, 1, "admin")


def test_admins_cannot_promote_themselves_to_owner(db):
    workspace = _workspace(db)
    _join(db, workspace, 2, "admin")
    with pytest.raises(ws.WorkspaceError):
        ws.set_role(db, _u(db, 2), workspace, 2, "owner")


def test_ownership_can_be_transferred_then_the_old_owner_may_leave(db):
    workspace = _workspace(db)
    _join(db, workspace, 2, "admin")
    ws.set_role(db, _u(db, 1), workspace, 2, "owner")
    ws.remove_member(db, _u(db, 1), workspace, 1)
    assert access.role_of(db, workspace.id, 1) is None
    assert access.role_of(db, workspace.id, 2) == "owner"


# ── 6. 자격증명 주체 ────────────────────────────────────────────────────
def test_workspace_projects_use_the_workspace_owners_credentials(db):
    """만든 사람이 팀을 떠나도 자동화가 멈추지 않아야 한다(§4.1 이 든 사용자 가치)."""
    workspace = _workspace(db, owner_id=1)
    _join(db, workspace, 2, "editor")
    project = _project(db, user_id=2, workspace_id=workspace.id)
    assert access.credential_owner_for(db, project) == 1

    ws.set_role(db, _u(db, 1), workspace, 2, "owner")
    workspace.owner_id = 2
    db.commit()
    assert access.credential_owner_for(db, project) == 2


# ── 7. 프로젝트 이동 ────────────────────────────────────────────────────
def test_moving_a_project_into_a_workspace_requires_managing_it(db):
    workspace = _workspace(db, owner_id=3, slug="team-other")
    project = _project(db, user_id=1)
    with pytest.raises(ws.WorkspaceError):
        ws.move_project(db, _u(db, 1), project, workspace_id=workspace.id)

    _join(db, workspace, 1, "admin")
    ws.move_project(db, _u(db, 1), project, workspace_id=workspace.id)
    assert project.workspace_id == workspace.id


def test_moving_a_project_back_to_personal(db):
    workspace = _workspace(db)
    project = _project(db, user_id=1, workspace_id=workspace.id)
    ws.move_project(db, _u(db, 1), project, workspace_id=None)
    assert project.workspace_id is None
    assert access.credential_owner_for(db, project) == 1


# ── 8. 감사 ─────────────────────────────────────────────────────────────
def test_permission_and_ownership_changes_are_audited(db):
    workspace = _workspace(db)
    _join(db, workspace, 2, "viewer")
    ws.set_role(db, _u(db, 1), workspace, 2, "editor")
    ws.remove_member(db, _u(db, 1), workspace, 2)

    actions = [e["action"] for e in ws.recent_events(db, workspace.id)]
    assert "member.role_change" in actions and "member.remove" in actions
    assert "workspace.create" in actions
    change = [e for e in ws.recent_events(db, workspace.id) if e["action"] == "member.role_change"][0]
    assert change["metadata"] == {"from": "viewer", "to": "editor"}
    assert change["actor"]["handle"] == "user-1"


def test_audit_payload_carries_handles_not_emails(db):
    workspace = _workspace(db)
    payload = json.dumps(ws.recent_events(db, workspace.id), ensure_ascii=False)
    assert "u1@t.com" not in payload


# ── 9. 이름 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("slug, ok", [
    ("team-one", True), ("abc", True),
    ("ab", False), ("-x", False), ("x-", False), ("a--b", False), ("official", False),
])
def test_workspace_slug_rules(slug, ok):
    if ok:
        assert ws.normalize_slug(slug) == slug
    else:
        with pytest.raises(ws.WorkspaceError):
            ws.normalize_slug(slug)


def test_duplicate_slugs_are_refused(db):
    _workspace(db, slug="dup-team")
    with pytest.raises(ws.WorkspaceError):
        _workspace(db, owner_id=2, slug="dup-team")
