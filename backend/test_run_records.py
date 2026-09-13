"""run_records — 실행 상태 기록 workflow_runs · run_steps (백로그 32 ENGINE-1 1단계, ADR-0028) 테스트.

계약: (1) execution.start 는 db 가 있으면 실행마다 run 하나, log_step 마다 step 하나를 **호출자 세션에** 남긴다 ·
(2) 상태는 succeeded/failed/paused 로 판정되고 실패에는 요약이 붙는다 · (3) 엔진이 예외를 던져도 기록은 failed 로
닫히고 예외는 그대로 올라간다 · (4) record_usage 가 직전 run 과 FlowExecutionLog 를 **한 번만** 잇는다 ·
(5) db 가 없거나 RUN_RECORDS=0 이면 아무것도 남기지 않고 실행 결과는 같다 · (6) 마이그레이션만으로 만든 스키마에
두 표와 run_id 컬럼이 있다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import models
import run_records
from database import Base
from usage_tracking import record_usage


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    return e


LINEAR = ([N("s", "startNode"), N("v", "valueNode", value="값"), N("o", "outputNode")], [E("s", "v"), E("v", "o")])


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000),
        models.Project(id=10, user_id=1, title="기록 테스트", graph_data={}),
    ])
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _start(db, nodes, edges, **kw):
    kw.setdefault("trigger_source", "manual")
    kw.setdefault("db", db)
    kw.setdefault("project_id", 10)
    kw.setdefault("executor_user_id", 1)
    kw.setdefault("session_id", "editor")
    return execution.start(nodes, edges, **kw)


# ── 1·2. run 과 step ────────────────────────────────────────────────────────

def test_실행마다_run_하나와_log_step_마다_step_하나가_남는다(db, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    result, _tokens, logs = _start(db, *LINEAR, default_input="")
    assert result == "값"

    run = db.query(models.WorkflowRun).one()
    assert (run.status, run.trigger_source, run.engine, run.project_id) == ("succeeded", "manual", "legacy", 10)
    assert (run.executor_user_id, run.owner_user_id, run.session_id) == (1, 1, "editor")
    assert run.started_at is not None and run.finished_at is not None and run.error_summary is None
    assert run.step_count == len(logs) == 3

    steps = db.query(models.RunStep).filter(models.RunStep.run_id == run.id).order_by(models.RunStep.sequence).all()
    assert [(s.sequence, s.node_id, s.node_type, s.status, s.attempt) for s in steps] == [
        (1, "s", "startNode", "succeeded", 1), (2, "v", "valueNode", "succeeded", 1), (3, "o", "outputNode", "succeeded", 1)]
    assert steps[1].output_preview == "값" and steps[1].started_at is not None and steps[1].error is None


def test_실패한_실행은_failed_와_요약을_남기고_실패_step_에_오류가_실린다(db):
    nodes = [N("s", "startNode"), N("l", "loopNode", maxIterations="abc"), N("o", "outputNode")]
    _start(db, nodes, [E("s", "l"), E("l", "o", "done")], default_input="")
    run = db.query(models.WorkflowRun).one()
    assert run.status == "failed" and run.finished_at is not None
    assert "abc" in run.error_summary
    failed = [s for s in run.steps if s.status == "failed"]
    assert failed and failed[0].node_type == "workflow" and failed[0].error["code"]


def test_승인_대기는_paused_이고_끝난_시각이_비어_있다(db):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="초안"), N("h", "humanApprovalNode"), N("o", "outputNode")]
    result, _t, _l = _start(db, nodes, [E("s", "v"), E("v", "h"), E("h", "o")])
    assert "승인 대기" in result
    run = db.query(models.WorkflowRun).one()
    assert run.status == "paused" and run.finished_at is None and run.error_summary is None
    assert [s.status for s in run.steps][-1] == "waiting"


def test_고정_출력은_pinned_step_으로_구분된다(db):
    _start(db, *LINEAR, pinned_outputs={"v": "고정"}, default_input="")
    run = db.query(models.WorkflowRun).one()
    assert {s.node_id: s.status for s in run.steps}["v"] == "pinned"
    assert run.status == "succeeded"


def test_인터프리터_엔진도_같은_step_을_남기고_엔진_이름이_기록된다(db, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    _start(db, *LINEAR, default_input="")
    monkeypatch.setenv("EXECUTION_ENGINE", "interpreter")
    _start(db, *LINEAR, default_input="")
    runs = db.query(models.WorkflowRun).order_by(models.WorkflowRun.id).all()
    assert [r.engine for r in runs] == ["legacy", "interpreter"]
    shape = lambda r: [(s.sequence, s.node_id, s.status, s.output_preview) for s in r.steps]
    assert shape(runs[0]) == shape(runs[1])


# ── 3. 엔진 예외 ─────────────────────────────────────────────────────────────

def test_엔진_예외는_기록을_failed_로_닫고_예외는_그대로_올라간다(db, monkeypatch):
    import graph

    def boom(*a, **k):
        raise RuntimeError("엔진 폭발")

    monkeypatch.setattr(graph, "run_workflow", boom)
    with pytest.raises(RuntimeError, match="엔진 폭발"):
        _start(db, *LINEAR)
    run = db.query(models.WorkflowRun).one()
    assert run.status == "failed" and run.error_summary == "RuntimeError: 엔진 폭발" and run.finished_at is not None


def test_기록_자체의_실패는_실행을_막지_않는다(db, monkeypatch):
    def broken_begin(*a, **k):
        raise RuntimeError("기록 표가 없다")

    monkeypatch.setattr(run_records, "begin", broken_begin)
    result, _t, _l = _start(db, *LINEAR, default_input="")
    assert result == "값"
    assert db.query(models.WorkflowRun).count() == 0


# ── 4. FlowExecutionLog 와의 연결 ────────────────────────────────────────────

def test_record_usage_는_직전_run_을_한_번만_잇는다(db):
    _start(db, *LINEAR, default_input="")
    run = db.query(models.WorkflowRun).one()

    first = record_usage(db, billable_user_id=1, actor_user_id=1, project_id=10, token_usage={}, result="값")
    second = record_usage(db, billable_user_id=1, actor_user_id=1, project_id=10, token_usage={}, result="값")
    assert first.run_id == run.id
    assert second.run_id is None, "같은 run 이 두 사건에 붙으면 안 된다"


def test_프로젝트가_다른_사건에는_붙지_않는다(db):
    _start(db, *LINEAR, default_input="")
    other = record_usage(db, billable_user_id=1, actor_user_id=1, project_id=11, token_usage={}, result="값")
    assert other.run_id is None
    assert execution.take_last_run_id(10) is None, "다른 프로젝트 사건이 꺼내 갔더라도 값은 소비된다"


def test_실행_사건이_아닌_record_usage_는_run_을_소비하지_않는다(db):
    _start(db, *LINEAR, default_input="")
    run = db.query(models.WorkflowRun).one()
    misc = record_usage(db, billable_user_id=1, project_id=10, token_usage={}, result="", event_type="credential_use",
                        deduct_balance=False)
    assert misc.run_id is None
    linked = record_usage(db, billable_user_id=1, project_id=10, token_usage={}, result="값")
    assert linked.run_id == run.id


# ── 5. 꺼짐·db 없음 ─────────────────────────────────────────────────────────

def test_db_가_없으면_기록_없이_실행만_한다():
    result, _t, logs = execution.start(*LINEAR, trigger_source="manual", default_input="")
    assert result == "값" and len(logs) == 3
    assert execution.take_last_run_id() is None


def test_RUN_RECORDS_0_이면_기록하지_않는다(db, monkeypatch):
    monkeypatch.setenv(run_records.RUN_RECORDS_ENV, "0")
    result, _t, _l = _start(db, *LINEAR, default_input="")
    assert result == "값"
    assert db.query(models.WorkflowRun).count() == 0


def test_세션이_아닌_db_자리표시자는_무시한다():
    result, _t, _l = execution.start(*LINEAR, trigger_source="manual", db="DB", default_input="")
    assert result == "값"


# ── 6. 마이그레이션 ─────────────────────────────────────────────────────────

def test_마이그레이션만으로_만든_스키마에_두_표와_run_id_가_있다(tmp_path):
    import db_migrate

    url = f"sqlite:///{tmp_path / 'runs.db'}"
    engine = create_engine(url)
    db_migrate.ensure_schema(engine, url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"workflow_runs", "run_steps"} <= tables
    assert "run_id" in {c["name"] for c in inspector.get_columns("flow_execution_logs")}
    run_columns = {c["name"] for c in inspector.get_columns("workflow_runs")}
    assert {"trigger_source", "engine", "status", "idempotency_key", "heartbeat_at", "error_summary"} <= run_columns
    step_columns = {c["name"] for c in inspector.get_columns("run_steps")}
    assert {"run_id", "sequence", "node_id", "attempt", "status", "output_preview", "tokens", "error"} <= step_columns
    engine.dispose()
