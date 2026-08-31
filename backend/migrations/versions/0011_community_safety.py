"""community_safety — 커뮤니티 안전·정체성 공통 기반 (ADR-0020, 우선 백로그 22)

§4.12(글·답변)와 §4.13(쪽지)이 **함께 쓰는 바닥**이다. 기능마다 신고·차단을 따로 두면 관리자가
두 화면을 보며 같은 사용자를 판단하게 되고, "커뮤니티에서 차단했는데 쪽지는 오는" 상태가 생긴다.

`community_profiles` 는 **백필하지 않는다.** 핸들은 커뮤니티에 처음 들어올 때 만든다 — 커뮤니티를
쓸 생각이 없는 사용자에게 공개 이름을 강제할 이유가 없고, 행이 없는 사용자는 공개 표면에 나타나지
않는 것이 올바른 기본값이다.

`users.role` 은 기존 행을 'user' 로 채운다. 첫 관리자는 서버 시작 시 `ADMIN_EMAILS` 부트스트랩이 만든다.

Revision ID: 0011_community_safety
Revises: 0010_artifact_refs
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_community_safety"
down_revision: Union[str, Sequence[str], None] = "0010_artifact_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(), nullable=False, server_default="user"))
    with op.batch_alter_table("friend_requests") as batch:
        batch.add_column(sa.Column("greeting", sa.String(), nullable=True))

    op.create_table(
        "community_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("handle", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("bio", sa.String(), nullable=True),
        sa.Column("avatar_artifact_id", sa.String(), nullable=True),
        sa.Column("suspended_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_community_profiles_user_id", "community_profiles", ["user_id"])
    op.create_index("ix_community_profiles_handle", "community_profiles", ["handle"])

    op.create_table(
        "blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blocker_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blocked_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),
    )
    op.create_index("ix_blocks_blocker_id", "blocks", ["blocker_id"])
    op.create_index("ix_blocks_blocked_id", "blocks", ["blocked_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    for column in ("target_type", "target_id", "reporter_id", "status", "created_at", "resolved_at"):
        op.create_index(f"ix_reports_{column}", "reports", [column])

    op.create_table(
        "moderation_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for column in ("target_type", "target_id", "admin_id", "created_at"):
        op.create_index(f"ix_moderation_actions_{column}", "moderation_actions", [column])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.String(), nullable=True),
        sa.Column("quiet", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_rate_limit_counters_expires_at", "rate_limit_counters", ["expires_at"])


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
    op.drop_table("notifications")
    op.drop_table("moderation_actions")
    op.drop_table("reports")
    op.drop_table("blocks")
    op.drop_table("community_profiles")
    with op.batch_alter_table("friend_requests") as batch:
        batch.drop_column("greeting")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")
