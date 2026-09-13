"""workflow_runs 에 재개 상태 컬럼 추가 (백로그 32 ENGINE-1 2단계, ADR-0028)

Revision ID: 0025_workflow_runs_resume
Revises: 0024_workflow_runs

승인 대기 전용이던 스냅샷 재개(ADR-0015, approval_requests.graph_snapshot·runtime_inputs)를 실행 기록으로 일반화한다.
paused 상태의 run 이 스스로 재개에 필요한 것(그래프 스냅샷·런타임 입력·재개 노드·직전 값)을 갖고, 승인 결정·대기(wait)·
워커 재시작(ENGINE-2)이 같은 재개 함수(execution.resume)를 쓴다. approval_requests 는 그대로 두고 run 이 그 id 를 가리킨다 —
알림·결정 UI 는 그 표가 정본이고, 실행 상태는 이 표가 정본이다.

⚠️ 존재 확인은 inspector 로 한다(0023·0024 의 교훈).
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_workflow_runs_resume"
down_revision = "0024_workflow_runs"
branch_labels = None
depends_on = None

_TABLE = "workflow_runs"
_COLUMNS = (
    sa.Column("paused_reason", sa.String, nullable=True),          # approval | (ENGINE-2) wait · worker_restart
    sa.Column("resume_node_id", sa.String, nullable=True),         # 재개 지점 — entry_node_id 로 들어간다
    sa.Column("resume_payload", sa.String, nullable=True),         # 재개 지점의 직전 노드 출력 자리 값(승인자가 본 견본)
    sa.Column("graph_snapshot", sa.JSON, nullable=True),           # {nodes, edges} — 자격증명은 reference 상태
    sa.Column("runtime_inputs", sa.JSON, nullable=True),           # 직렬화 가능한 런타임 입력(approval_service.serializable_runtime_inputs)
    sa.Column("approval_request_id", sa.String, nullable=True),    # 승인 대기면 approval_requests.request_id
    sa.Column("resume_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("resumed_at", sa.DateTime, nullable=True),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return  # 0024 가 만들지 않은(create_all 인계) DB — 표는 모델이 재개 컬럼까지 포함해 만든다
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    missing = [c for c in _COLUMNS if c.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(_TABLE) as batch:
        for column in missing:
            batch.add_column(column)
        if "approval_request_id" in {c.name for c in missing}:
            batch.create_index("ix_workflow_runs_approval_request_id", ["approval_request_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        if "ix_workflow_runs_approval_request_id" in indexes:
            batch.drop_index("ix_workflow_runs_approval_request_id")
        for column in _COLUMNS:
            if column.name in existing:
                batch.drop_column(column.name)
