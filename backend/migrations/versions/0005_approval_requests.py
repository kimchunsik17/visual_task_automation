"""approval_requests — 사용자 승인 노드의 durable 대기 상태 (ADR-0015)

승인 노드에 도달한 실행의 중단 지점(그래프 스냅샷·payload·런타임 입력)을 저장해,
서버 재시작 후에도 승인/거절 결정으로 정확한 지점부터 재개할 수 있게 한다.

Revision ID: 0005_approval_requests
Revises: 0004_trace_node_selection
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_approval_requests'
down_revision: Union[str, Sequence[str], None] = '0004_trace_node_selection'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('project_title', sa.String(), nullable=True),
        sa.Column('node_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('origin', sa.String(), nullable=True),
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('payload', sa.String(), nullable=True),
        sa.Column('graph_snapshot', sa.JSON(), nullable=True),
        sa.Column('runtime_inputs', sa.JSON(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('notify_channels', sa.JSON(), nullable=True),
        sa.Column('notify_results', sa.JSON(), nullable=True),
        sa.Column('comment', sa.String(), nullable=True),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resume_outcome', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('approval_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_approval_requests_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approval_requests_request_id'), ['request_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_approval_requests_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approval_requests_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approval_requests_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_approval_requests_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('approval_requests')
