"""node_error_codes — 노드 실행 로그에 NodeError v1 telemetry 컬럼 추가 (ADR-0016)

운영 지표는 node type, code, category, effectState 와 legacy 여부만 모은다 — 사용자 입력·provider
원문·경로는 저장하지 않는다. `error_request_id` 는 공개 오류와 내부 진단 기록을 잇는 열쇠다.

Revision ID: 0008_node_error_codes
Revises: 0007_image_artifacts
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_node_error_codes"
down_revision: Union[str, Sequence[str], None] = "0007_image_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("node_execution_logs") as batch:
        batch.add_column(sa.Column("error_code", sa.String(), nullable=True))
        batch.add_column(sa.Column("error_category", sa.String(), nullable=True))
        batch.add_column(sa.Column("effect_state", sa.String(), nullable=True))
        batch.add_column(sa.Column("error_legacy", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("error_request_id", sa.String(), nullable=True))
        batch.create_index(op.f("ix_node_execution_logs_error_code"), ["error_code"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("node_execution_logs") as batch:
        batch.drop_index(op.f("ix_node_execution_logs_error_code"))
        batch.drop_column("error_request_id")
        batch.drop_column("error_legacy")
        batch.drop_column("effect_state")
        batch.drop_column("error_category")
        batch.drop_column("error_code")
