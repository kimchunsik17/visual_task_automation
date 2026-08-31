"""generation_traces.generation_plan — GenerationPlan 계측 (우선 백로그 10번, §4.4)

adaptive candidate 실험의 전환 판단 데이터: 요청별 계획(후보 수·평가 정책)과 후보별
결정론 점수·선택 결과를 남긴다. 과거 trace 는 계획이 없으므로 NULL 그대로 둔다.

Revision ID: 0006_trace_generation_plan
Revises: 0005_approval_requests
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_trace_generation_plan'
down_revision: Union[str, Sequence[str], None] = '0005_approval_requests'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generation_traces', sa.Column('generation_plan', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generation_traces', 'generation_plan')
