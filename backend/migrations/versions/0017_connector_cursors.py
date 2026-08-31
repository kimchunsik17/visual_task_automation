"""connector_cursors — Trigger cursor 전용 저장소와 기존 값 이관 (한국형 노드 계획 Phase 0, §7)

예전에는 `NodeMemory` 를 `session_id='__cursor__'` 로 빌려 썼다. 대화 기억용 표에 세션이 아닌
상태를 끼워 넣은 것이라 workspace 격리·provider 구분·형식 버전·lease 를 둘 자리가 없었다.

**이 마이그레이션의 핵심은 표를 만드는 게 아니라 값을 옮기는 것이다.** YouTube·RSS·Gmail
Trigger 가 이미 옛 형식을 쓰고 있고, 그 값이 넘어오지 않으면 세 노드가 "첫 실행"으로 판단해
**과거 항목을 한 번씩 다시 통지한다**(connectors/services/rss.py 의 `first_run = not cursor`).
그래서 표 생성과 같은 마이그레이션 안에서 복사한다.

옛 행은 지우지 않는다 — 되돌릴 때 필요하고, 크기도 작다. `connectors/cursor.py` 가 새 표에
행이 없을 때만 옛 자리를 한 번 더 보는 이행기 읽기를 갖고 있어서, 이 마이그레이션 전에 만들어진
행이 남아 있어도 재통지가 나지 않는다.

Revision ID: 0017_connector_cursors
Revises: 0016_oauth_states
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_connector_cursors"
down_revision: Union[str, Sequence[str], None] = "0016_oauth_states"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_cursors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("cursor_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cursor_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("lease_owner", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("project_id", "node_id", name="uq_connector_cursor"),
    )
    op.create_index("ix_connector_cursors_workspace_id", "connector_cursors", ["workspace_id"])
    op.create_index("ix_connector_cursors_project_id", "connector_cursors", ["project_id"])
    op.create_index("ix_connector_cursors_node_id", "connector_cursors", ["node_id"])
    op.create_index("ix_connector_cursors_provider", "connector_cursors", ["provider"])

    # ── 기존 cursor 이관 ────────────────────────────────────────────────
    # workspace_id 는 프로젝트에서 따라온다. 프로젝트가 이미 지워졌으면 그 cursor 는 옮길
    # 이유가 없으므로(다시 실행될 일이 없다) 조인으로 자연스럽게 빠진다.
    #
    # `node_memory` 가 없는 DB 도 있다 — create_all 로 만들어져 마이그레이션 이력이 없는 기존
    # DB 를 `db_migrate.ensure_schema()` 가 기준선으로 stamp 한 뒤 인계받는 경로다(ADR-0006).
    # 그런 DB 에는 옮길 cursor 자체가 없으므로 표가 없으면 조용히 건너뛴다.
    inspector = sa.inspect(op.get_bind())
    if "node_memory" in inspector.get_table_names():
        op.execute(sa.text("""
            INSERT INTO connector_cursors
                (workspace_id, project_id, node_id, provider, cursor_version, cursor_json, updated_at)
            SELECT p.workspace_id, m.project_id, m.node_id, NULL, 1,
                   COALESCE(NULLIF(m.history, ''), '{}'), m.updated_at
            FROM node_memory AS m
            JOIN projects AS p ON p.id = m.project_id
            WHERE m.session_id = '__cursor__'
        """))


def downgrade() -> None:
    op.drop_index("ix_connector_cursors_provider", table_name="connector_cursors")
    op.drop_index("ix_connector_cursors_node_id", table_name="connector_cursors")
    op.drop_index("ix_connector_cursors_project_id", table_name="connector_cursors")
    op.drop_index("ix_connector_cursors_workspace_id", table_name="connector_cursors")
    op.drop_table("connector_cursors")
