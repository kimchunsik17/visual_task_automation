"""messaging — 친구 간 1:1 쪽지 (ADR-0022, 우선 백로그 24)

**친구 한정**으로 정했으므로(2026-08-29) `MessageRequest` 와 수락 흐름이 없다. 수락은 이미 있는
친구 요청이 담당한다.

`conversations` 의 참가자 쌍은 **작은 id 를 user_a 에** 두는 규칙으로 유일성을 보장한다. 정렬하지
않으면 (1,2)와 (2,1)이 서로 다른 행이 되어 같은 상대와 대화가 두 개 생긴다.

Revision ID: 0013_messaging
Revises: 0012_community_qna
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_messaging"
down_revision: Union[str, Sequence[str], None] = "0012_community_qna"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("user_a_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_b_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_message_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint('user_a_id', 'user_b_id', name="uq_conversation_pair"),
    )
    op.create_index("ix_conversations_user_a_id", "conversations", ["user_a_id"])
    op.create_index("ix_conversations_user_b_id", "conversations", ["user_b_id"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    op.create_table(
        "conversation_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_read_message_id", sa.Integer(), nullable=False),
        sa.Column("muted_until", sa.DateTime()),
        sa.Column("hidden_at", sa.DateTime()),
        sa.UniqueConstraint('conversation_id', 'user_id', name="uq_conversation_member"),
    )
    op.create_index("ix_conversation_members_conversation_id", "conversation_members", ["conversation_id"])
    op.create_index("ix_conversation_members_user_id", "conversation_members", ["user_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("attachment_artifact_ids", sa.JSON()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("deleted_for_user_ids", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("edited_at", sa.DateTime()),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

def downgrade() -> None:
    for name in ("messages", "conversation_members", "conversations"):
        op.drop_table(name)
