"""템플릿 소개 페이지 · 좋아요 · 댓글 집계

Revision ID: 0020_template_intro_pages
Revises: 0019_site_feedback_submitters

목록에서 곧바로 '가져오기' 를 누르게 하던 것을 바꾼다. 먼저 **제작자가 쓴 소개를 읽고**
댓글·좋아요·신고를 할 수 있어야 한다.

`description`(목록 한 줄 요약)과 `intro_body`(읽고 판단하는 글)를 나눈 이유는 쓰임이 달라서다.
소개는 **버전 스냅샷과 달리 고쳐도 된다** — 가져간 사람의 사본이 바뀌지 않기 때문이다.

댓글·좋아요·신고는 새 표를 만들지 않고 comments/reactions/reports 의 `target_type` 에
'template' 을 더해 쓴다. 표를 새로 파면 신고 화면이 둘로 갈린다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_template_intro_pages"
down_revision = "0019_site_feedback_submitters"
branch_labels = None
depends_on = None

COLUMNS = (
    ("intro_body", lambda: sa.Column("intro_body", sa.String(), nullable=False, server_default="")),
    ("intro_image_ids", lambda: sa.Column("intro_image_ids", sa.JSON(), nullable=True)),
    ("thumbnail_artifact_id", lambda: sa.Column("thumbnail_artifact_id", sa.String(), nullable=True)),
    ("like_count", lambda: sa.Column("like_count", sa.Integer(), nullable=False, server_default="0")),
    ("comment_count", lambda: sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0")),
    ("updated_at", lambda: sa.Column("updated_at", sa.DateTime(), nullable=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "templates" not in inspector.get_table_names():
        # create_all 로 만들어진 DB 를 기준선으로 인계받는 경로가 있다(0017~0019 와 같은 이유).
        return
    existing = {c["name"] for c in inspector.get_columns("templates")}
    for name, build in COLUMNS:
        if name not in existing:
            op.add_column("templates", build())
    # 이미 있던 행의 updated_at 은 만들어진 시각으로 채운다 — NULL 이면 목록 정렬이 흔들린다.
    op.execute("UPDATE templates SET updated_at = COALESCE(published_at, created_at) "
               "WHERE updated_at IS NULL")


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("templates", name)
