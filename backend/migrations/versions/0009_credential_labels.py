"""credential_labels — 명명된 Database 자격증명 (ADR-0017)

`user_api_keys.label` 을 추가한다. provider=database 는 사용자당 여러 행(개발/운영 DB 등)을 가질 수
있고, 노드는 `{{API_CENTER:database#<id>}}` reference 로 하나를 가리킨다. 기존 행은 label NULL 로
남아 "기본 자격증명" 으로 동작한다 — 백필이 필요 없다.

Revision ID: 0009_credential_labels
Revises: 0008_node_error_codes
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_credential_labels"
down_revision: Union[str, Sequence[str], None] = "0008_node_error_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_api_keys") as batch:
        batch.add_column(sa.Column("label", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_api_keys") as batch:
        batch.drop_column("label")
