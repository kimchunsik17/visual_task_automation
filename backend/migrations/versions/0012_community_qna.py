"""community_qna — 커뮤니티 Q&A (ADR-0021, 우선 백로그 23)

질문·답변·댓글을 **세 층**으로 나눈다. "글 + 댓글" 한 겹이면 *답*과 *되묻는 말*이 같은 줄에 섞여
채택할 대상을 고를 수 없다.

`workflow_shares.graph_snapshot` 은 게시 시점의 **불변** 사본이다 — 프로젝트를 가리키는 포인터가
아니다. 포인터로 두면 작성자가 프로젝트를 고칠 때 남이 이미 읽은 글이 조용히 바뀐다.
`community_sanitize` 를 통과한 것만 들어오므로 이 컬럼에 비밀은 없다.

`execution_excerpts` 는 NodeError v1(ADR-0016)의 **공개 payload 만** 담는다. 실행 로그를 통째로
붙이면 접속 문자열·토큰·서버 경로가 그대로 샌다.

Revision ID: 0012_community_qna
Revises: 0011_community_safety
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_community_qna"
down_revision: Union[str, Sequence[str], None] = "0011_community_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("tags", sa.JSON()),
        sa.Column("image_artifact_ids", sa.JSON()),
        sa.Column("accepted_answer_id", sa.Integer()),
        sa.Column("answer_count", sa.Integer(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("edited_at", sa.DateTime()),
        sa.Column("deleted_at", sa.DateTime()),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_kind", "posts", ["kind"])
    op.create_index("ix_posts_visibility", "posts", ["visibility"])
    op.create_index("ix_posts_accepted_answer_id", "posts", ["accepted_answer_id"])
    op.create_index("ix_posts_status", "posts", ["status"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])
    op.create_index("ix_posts_deleted_at", "posts", ["deleted_at"])
    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("edited_at", sa.DateTime()),
        sa.Column("deleted_at", sa.DateTime()),
    )
    op.create_index("ix_answers_post_id", "answers", ["post_id"])
    op.create_index("ix_answers_author_id", "answers", ["author_id"])
    op.create_index("ix_answers_status", "answers", ["status"])
    op.create_index("ix_answers_created_at", "answers", ["created_at"])
    op.create_index("ix_answers_deleted_at", "answers", ["deleted_at"])
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("edited_at", sa.DateTime()),
        sa.Column("deleted_at", sa.DateTime()),
    )
    op.create_index("ix_comments_target_type", "comments", ["target_type"])
    op.create_index("ix_comments_target_id", "comments", ["target_id"])
    op.create_index("ix_comments_author_id", "comments", ["author_id"])
    op.create_index("ix_comments_status", "comments", ["status"])
    op.create_index("ix_comments_created_at", "comments", ["created_at"])
    op.create_index("ix_comments_deleted_at", "comments", ["deleted_at"])
    op.create_table(
        "reactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint('target_type', 'target_id', 'user_id', 'kind', name="uq_reaction_once"),
    )
    op.create_index("ix_reactions_target_type", "reactions", ["target_type"])
    op.create_index("ix_reactions_target_id", "reactions", ["target_id"])
    op.create_index("ix_reactions_user_id", "reactions", ["user_id"])
    op.create_table(
        "workflow_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("source_project_id", sa.Integer()),
        sa.Column("source_revision", sa.Integer()),
        sa.Column("graph_snapshot", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("node_types", sa.JSON()),
        sa.Column("required_credentials", sa.JSON()),
        sa.Column("risk_flags", sa.JSON()),
        sa.Column("import_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_workflow_shares_owner_type", "workflow_shares", ["owner_type"])
    op.create_index("ix_workflow_shares_owner_id", "workflow_shares", ["owner_id"])
    op.create_table(
        "execution_excerpts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String()),
        sa.Column("error_code", sa.String()),
        sa.Column("error_category", sa.String()),
        sa.Column("effect_state", sa.String()),
        sa.Column("user_message", sa.String()),
        sa.Column("occurred_at", sa.DateTime()),
    )
    op.create_index("ix_execution_excerpts_post_id", "execution_excerpts", ["post_id"])
    op.create_index("ix_execution_excerpts_error_code", "execution_excerpts", ["error_code"])


def downgrade() -> None:
    for name in ("execution_excerpts", "workflow_shares", "reactions", "comments", "answers", "posts"):
        op.drop_table(name)
