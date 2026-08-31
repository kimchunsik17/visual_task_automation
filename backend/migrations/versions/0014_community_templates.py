"""community_templates — 검증된 공유의 승격 (ADR-0023, 우선 백로그 12)

템플릿 버전은 스냅샷을 **다시 만들지 않고** §4.12 의 `workflow_shares` 를 가리킨다. 정화 로직을
두 벌 만들면 한쪽만 고쳐지는 날이 온다.

게시된 버전은 **불변**이다 — `status` 외의 어떤 컬럼도 갱신하지 않는다. 누군가 v1.0 을 설치했는데
v1.0 의 내용이 바뀌면 "v1.0 을 설치했다"는 기록이 거짓말이 된다.

정지는 별도 테이블을 만들지 않고 ADR-0020 의 `moderation_actions` 를 쓴다 — 검수 화면이 하나여야
관리자가 한 자리에서 판단할 수 있다.

Revision ID: 0014_community_templates
Revises: 0013_messaging
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_community_templates"
down_revision: Union[str, Sequence[str], None] = "0013_messaging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("tags", sa.JSON()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("latest_version_id", sa.Integer()),
        sa.Column("install_count", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_templates_owner_id", "templates", ["owner_id"])
    op.create_index("ix_templates_slug", "templates", ["slug"])
    op.create_index("ix_templates_category", "templates", ["category"])
    op.create_index("ix_templates_status", "templates", ["status"])
    op.create_index("ix_templates_published_at", "templates", ["published_at"])
    op.create_table(
        "template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("workflow_share_id", sa.Integer(), nullable=False),
        sa.Column("changelog", sa.String()),
        sa.Column("compatibility", sa.JSON()),
        sa.Column("publish_gate", sa.JSON()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint('template_id', 'version', name="uq_template_version"),
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])
    op.create_index("ix_template_versions_status", "template_versions", ["status"])
    op.create_index("ix_template_versions_published_at", "template_versions", ["published_at"])
    op.create_table(
        "template_installs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_version_id", sa.Integer(), sa.ForeignKey("template_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installed_project_id", sa.Integer()),
        sa.Column("installed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("installed_at", sa.DateTime()),
        sa.Column("first_run_outcome", sa.String()),
        sa.Column("retained_at_7d", sa.Boolean()),
    )
    op.create_index("ix_template_installs_template_version_id", "template_installs", ["template_version_id"])
    op.create_index("ix_template_installs_installed_project_id", "template_installs", ["installed_project_id"])
    op.create_index("ix_template_installs_installed_by", "template_installs", ["installed_by"])
    op.create_index("ix_template_installs_installed_at", "template_installs", ["installed_at"])
    op.create_index("ix_template_installs_first_run_outcome", "template_installs", ["first_run_outcome"])

def downgrade() -> None:
    for name in ("template_installs", "template_versions", "templates"):
        op.drop_table(name)
