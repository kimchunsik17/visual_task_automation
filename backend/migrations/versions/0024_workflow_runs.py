"""workflow_runs · run_steps 신설, flow_execution_logs.run_id 추가 (백로그 32 ENGINE-1 1단계, ADR-0028)

Revision ID: 0024_workflow_runs
Revises: 0023_uploads_per_user

실행 상태를 실행 단위(workflow_runs)와 노드 단위(run_steps)로 남긴다. 지금까지는 FlowExecutionLog(과금·사용량
관점의 사건)와 NodeExecutionLog(그 사건에 매달린 노드 기록)만 있었고, 어느 경로로 시작했는지(trigger_source)·
어느 엔진이 돌았는지·대기(paused)인지·재개 지점이 어디인지 같은 **실행 상태**는 표에 없었다. 큐/워커(ENGINE-2)와
재시도·멱등성(ENGINE-3)이 이 표 위에 얹힌다 — idempotency_key·heartbeat_at 은 그때 쓰는 자리를 미리 잡아 둔 것.

FlowExecutionLog 는 그대로 두고 run_id 만 붙인다 — 통계(build_statistics)·과금은 건드리지 않는다(로드맵 §3.1 ENGINE-1 4).

⚠️ 존재 확인은 inspector 로 한다(0023 의 교훈): SQLite 는 batch 작업이 with 종료 시점에 실행돼 try/except 가 소용없고,
PostgreSQL 은 실패한 문장이 트랜잭션을 오염시킨다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_workflow_runs"
down_revision = "0023_uploads_per_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "workflow_runs" not in tables:
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("project_id", sa.Integer, nullable=True),
            sa.Column("trigger_source", sa.String, nullable=False),
            sa.Column("engine", sa.String, nullable=False, server_default="legacy"),
            sa.Column("status", sa.String, nullable=False),
            sa.Column("idempotency_key", sa.String, nullable=True),
            sa.Column("executor_user_id", sa.Integer, nullable=True),
            sa.Column("owner_user_id", sa.Integer, nullable=True),
            sa.Column("session_id", sa.String, nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=False),
            sa.Column("finished_at", sa.DateTime, nullable=True),
            sa.Column("heartbeat_at", sa.DateTime, nullable=True),
            sa.Column("error_summary", sa.String, nullable=True),
            sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
            sa.Column("step_count", sa.Integer, nullable=False, server_default="0"),
        )
        op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])
        op.create_index("ix_workflow_runs_trigger_source", "workflow_runs", ["trigger_source"])
        op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
        op.create_index("ix_workflow_runs_executor_user_id", "workflow_runs", ["executor_user_id"])
        op.create_index("ix_workflow_runs_owner_user_id", "workflow_runs", ["owner_user_id"])
        op.create_index("ix_workflow_runs_started_at", "workflow_runs", ["started_at"])
        op.create_index("ix_workflow_runs_idempotency_key", "workflow_runs", ["idempotency_key"], unique=True)

    if "run_steps" not in tables:
        op.create_table(
            "run_steps",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("run_id", sa.Integer, sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer, nullable=False),
            sa.Column("node_id", sa.String, nullable=False),
            sa.Column("node_type", sa.String, nullable=True),
            sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.String, nullable=False),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("finished_at", sa.DateTime, nullable=True),
            sa.Column("output_preview", sa.String, nullable=True),
            sa.Column("tokens", sa.JSON, nullable=True),
            sa.Column("error", sa.JSON, nullable=True),
        )
        op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
        op.create_index("ix_run_steps_status", "run_steps", ["status"])

    # create_all 시절 DB 를 기준선으로 stamp 해 인계받는 경우(db_migrate.ensure_schema) 표가 없을 수 있다 —
    # 없으면 건드리지 않는다. 표는 모델(create_all)이나 이후 마이그레이션이 run_id 를 포함해 만든다.
    if "flow_execution_logs" in tables:
        flow_columns = {c["name"] for c in inspector.get_columns("flow_execution_logs")}
        if "run_id" not in flow_columns:
            with op.batch_alter_table("flow_execution_logs") as batch:
                batch.add_column(sa.Column("run_id", sa.Integer, nullable=True))
                batch.create_index("ix_flow_execution_logs_run_id", ["run_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "flow_execution_logs" in tables:
        flow_columns = {c["name"] for c in inspector.get_columns("flow_execution_logs")}
        if "run_id" in flow_columns:
            with op.batch_alter_table("flow_execution_logs") as batch:
                batch.drop_index("ix_flow_execution_logs_run_id")
                batch.drop_column("run_id")
    if "run_steps" in tables:
        op.drop_table("run_steps")
    if "workflow_runs" in tables:
        op.drop_table("workflow_runs")
