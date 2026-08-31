"""사용자 문서 포맷 라이브러리 (포맷 스튜디오 계획 Phase 1)

Revision ID: 0021_document_formats
Revises: 0020_template_intro_pages

프리셋 포맷은 저장소 정본(document_formats/*.json)이고, 이 표는 사용자가 포맷 스튜디오에서
만들어 저장하는 포맷이다. id 는 uuid 문자열 — formatNode.data.formatId 가 프리셋 id 와 같은
자리에서 참조한다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_document_formats"
down_revision = "0020_template_intro_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_formats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("layout", sa.String(), nullable=False, server_default="document"),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("document_formats")
