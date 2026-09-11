"""workflow_runs 를 실행 큐로 — queued 상태와 워커 claim 컬럼 (백로그 32 ENGINE-2 1단계, ADR-0029)

Revision ID: 0026_workflow_runs_queue
Revises: 0025_workflow_runs_resume

status=queued 인 run 이 곧 큐 항목이다. 워커가 SELECT … FOR UPDATE SKIP LOCKED 로 하나를 잡아 running 으로 바꾸고(worker_id·
claimed_at·attempts), 실행 중 heartbeat_at 을 갱신한다. 별도 큐 표를 두지 않는 이유: run 이 이미 실행에 필요한 것(스냅샷·
런타임 입력·재개 상태)을 갖고 있고, "한 논리적 실행은 run 하나"(ADR-0028)를 큐 단계에서도 지키기 위해서다. run_options 는
stop/scope/pinned·user_inputs 같은 실행 인자.

⚠️ 존재 확인은 inspector 로 한다(0023~0025 의 교훈).
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_workflow_runs_queue"
down_revision = "0025_workflow_runs_resume"
branch_labels = None
depends_on = None

_TABLE = "workflow_runs"
_COLUMNS = (
    sa.Column("queued_at", sa.DateTime, nullable=True),
    sa.Column("claimed_at", sa.DateTime, nullable=True),
    sa.Column("worker_id", sa.String, nullable=True),
    sa.Column("run_options", sa.JSON, nullable=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return  # create_all 인계 DB — 표는 모델이 큐 컬럼까지 포함해 만든다
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    missing = [c for c in _COLUMNS if c.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(_TABLE) as batch:
        for column in missing:
            batch.add_column(column)
        if "worker_id" in {c.name for c in missing}:
            batch.create_index("ix_workflow_runs_worker_id", ["worker_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        if "ix_workflow_runs_worker_id" in indexes:
            batch.drop_index("ix_workflow_runs_worker_id")
        for column in _COLUMNS:
            if column.name in existing:
                batch.drop_column(column.name)
