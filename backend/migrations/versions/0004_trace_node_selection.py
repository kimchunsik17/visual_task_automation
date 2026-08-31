"""generation_traces.node_selection — 노드 선별 계측(ADR-0013)

RAG Phase A: 생성 턴마다 LLM 선별 결과, hybrid shadow 선별 결과, 최종 그래프에 실제로
쓰인 노드의 비교를 남긴다. 과거 trace는 선별 기록이 없으므로 NULL 그대로 둔다 — 지어낸
값을 백필하면 shadow 평가 집계가 오염된다.

Revision ID: 0004_trace_node_selection
Revises: 0003_uploaded_files
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_trace_node_selection'
down_revision: Union[str, Sequence[str], None] = '0003_uploaded_files'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generation_traces', sa.Column('node_selection', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generation_traces', 'node_selection')
