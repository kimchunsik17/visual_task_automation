"""workspaces — 조직 단위와 역할 (ADR-0024, 우선 백로그 11)

`projects.workspace_id` 는 **nullable 이고 백필하지 않는다.** 비어 있으면 개인 소유이고 동작이
도입 전과 같다. 전면 백필은 모든 조회 경로를 바꾸는데, 얻는 것("코드 경로가 하나")은
`project_access.can()` 이 이미 준다(§4.17 판단).

Revision ID: 0015_workspaces
Revises: 0014_community_templates
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_workspaces"
down_revision: Union[str, Sequence[str], None] = "0014_community_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"])
    op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"])
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("invited_by", sa.Integer()),
        sa.Column("joined_at", sa.DateTime()),
        sa.UniqueConstraint('workspace_id', 'user_id', name="uq_workspace_member"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_index("ix_workspace_members_status", "workspace_members", ["status"])
    op.create_table(
        "workspace_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handle", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("invited_by", sa.Integer()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_workspace_invites_workspace_id", "workspace_invites", ["workspace_id"])
    op.create_index("ix_workspace_invites_handle", "workspace_invites", ["handle"])
    op.create_index("ix_workspace_invites_status", "workspace_invites", ["status"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String()),
        sa.Column("resource_id", sa.String()),
        sa.Column("event_metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_audit_events_workspace_id", "audit_events", ["workspace_id"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    # 컬럼과 외래키를 나눠서 건다. SQLite 는 제약 ALTER 를 지원하지 않고, batch 모드는 테이블을
    # 통째로 재생성하다 `projects` 의 이름 없는 제약에서 실패한다. 운영은 PostgreSQL 이므로
    # **참조 무결성은 거기서 걸고**, 테스트용 SQLite 는 컬럼만 갖는다(모델의 ForeignKey 선언은
    # 양쪽 모두에서 ORM 관계로 동작한다).
    op.add_column("projects", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    if op.get_bind().dialect.name == "postgresql":
        # workspace 를 지우면 프로젝트는 **개인 소유로 돌아간다**(삭제되지 않는다).
        op.create_foreign_key("fk_projects_workspace_id", "projects", "workspaces",
                              ["workspace_id"], ["id"], ondelete="SET NULL")

def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_projects_workspace_id", "projects", type_="foreignkey")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_column("projects", "workspace_id")
    for name in ("audit_events", "workspace_invites", "workspace_members", "workspaces"):
        op.drop_table(name)
