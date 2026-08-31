"""oauth_states — 인가 코드 흐름의 왕복 상태 (한국형 노드 계획 Phase 0)

지금까지 OAuth 토큰은 사용자가 provider 콘솔에서 직접 받아 붙여넣었다(`google_oauth`·
`kakao_token` 의 guide 가 그 절차다). 네이버·X·Instagram 을 붙이려면 동의 화면으로 보냈다가
받아오는 경로가 필요하고, 그러려면 "이 응답이 우리가 보낸 요청에 대한 것인가"를 서버가 판단할
근거가 있어야 한다. state 를 클라이언트에 맡기면 CSRF 로 남의 계정에 공격자의 토큰을 붙일 수
있어서 서버가 들고 있는다.

기존 동작은 그대로다 — 이 표는 새 경로에서만 쓰이고, 토큰 자체는 여전히 `user_api_keys` 에
저장되므로 `ensure_fresh_token` 이 손대지 않고도 계속 동작한다.

Revision ID: 0016_oauth_states
Revises: 0015_workspaces
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_oauth_states"
down_revision: Union[str, Sequence[str], None] = "0015_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, unique=True),
        sa.Column("code_verifier", sa.String(), nullable=True),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("return_to", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])
    op.create_index("ix_oauth_states_provider", "oauth_states", ["provider"])
    op.create_index("ix_oauth_states_state", "oauth_states", ["state"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_oauth_states_state", table_name="oauth_states")
    op.drop_index("ix_oauth_states_provider", table_name="oauth_states")
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
