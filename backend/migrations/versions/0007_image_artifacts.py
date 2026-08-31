"""image_artifacts — AI 이미지 생성·수정 버전 계보

Revision ID: 0007_image_artifacts
Revises: 0006_trace_generation_plan
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_image_artifacts"
down_revision: Union[str, Sequence[str], None] = "0006_trace_generation_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("stored_name", sa.String(), nullable=False),
        sa.Column("parent_artifact_id", sa.String(), nullable=True),
        sa.Column("response_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("revision_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action", sa.String(), nullable=False, server_default="auto"),
        sa.Column("provider", sa.String(), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt", sa.String(), nullable=True),
        sa.Column("revised_prompt", sa.String(), nullable=True),
        sa.Column("output_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(op.f("ix_image_artifacts_id"), "image_artifacts", ["id"], unique=False)
    op.create_index(op.f("ix_image_artifacts_artifact_id"), "image_artifacts", ["artifact_id"], unique=True)
    op.create_index(op.f("ix_image_artifacts_owner_user_id"), "image_artifacts", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_image_artifacts_project_id"), "image_artifacts", ["project_id"], unique=False)
    op.create_index(op.f("ix_image_artifacts_response_id"), "image_artifacts", ["response_id"], unique=False)
    op.create_index(op.f("ix_image_artifacts_created_at"), "image_artifacts", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_image_artifacts_created_at"), table_name="image_artifacts")
    op.drop_index(op.f("ix_image_artifacts_response_id"), table_name="image_artifacts")
    op.drop_index(op.f("ix_image_artifacts_project_id"), table_name="image_artifacts")
    op.drop_index(op.f("ix_image_artifacts_owner_user_id"), table_name="image_artifacts")
    op.drop_index(op.f("ix_image_artifacts_artifact_id"), table_name="image_artifacts")
    op.drop_index(op.f("ix_image_artifacts_id"), table_name="image_artifacts")
    op.drop_table("image_artifacts")
