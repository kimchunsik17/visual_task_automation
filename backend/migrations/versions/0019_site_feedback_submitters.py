"""사이트 평가 중복 제출 차단 — site_feedback_submitters

Revision ID: 0019_site_feedback_submitters
Revises: 0018_curated_templates

평가 내용은 익명으로 저장한다(`site_feedback.user_id` 는 늘 NULL). 그래서 "계정당 한 번" 을
확인할 방법이 없었고, 같은 사람이 몇 번이든 제출할 수 있었다.

내용에 user_id 를 되돌리면 익명 결정이 무너진다. 대신 **낸 사람의 목록만** 따로 둔다.
두 표는 서로를 가리키지 않는다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_site_feedback_submitters"
down_revision = "0018_curated_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "site_feedback_submitters" in inspector.get_table_names():
        # create_all 로 만들어진 DB 를 기준선으로 인계받는 경로가 있다(0017·0018 과 같은 이유).
        return
    op.create_table(
        "site_feedback_submitters",
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("submitted_on", sa.Date(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("site_feedback_submitters")
