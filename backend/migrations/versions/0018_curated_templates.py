"""공식(큐레이션) 템플릿 표시 — templates.is_curated

Revision ID: 0018_curated_templates
Revises: 0017_connector_cursors

일반 게시는 "본인 계정 실행 성공" 을 요구한다. 운영자가 직접 만든 공식 템플릿은 그 요건을
사람의 검수로 대체하는데, **대체했다는 사실이 행에 남아야** 나중에 "이건 왜 실행 이력이
없지" 를 설명할 수 있다. 숨은 예외로 두지 않으려고 컬럼을 만든다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_curated_templates"
down_revision = "0017_connector_cursors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "templates" not in inspector.get_table_names():
        # create_all 로 만들어진 DB 를 기준선으로 인계받는 경로가 있다(0017 과 같은 이유).
        return
    columns = {c["name"] for c in inspector.get_columns("templates")}
    if "is_curated" in columns:
        return
    op.add_column("templates",
                  sa.Column("is_curated", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.create_index("ix_templates_is_curated", "templates", ["is_curated"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "templates" not in inspector.get_table_names():
        return
    if "is_curated" not in {c["name"] for c in inspector.get_columns("templates")}:
        return
    op.drop_index("ix_templates_is_curated", table_name="templates")
    op.drop_column("templates", "is_curated")
