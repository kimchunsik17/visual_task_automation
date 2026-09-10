"""재개 일반화 — paused run 이 재개 상태를 갖고 execution.resume 이 같은 run 으로 이어서 실행한다 (ENGINE-1 2단계, ADR-0028).

계약: (1) 승인 대기로 멈춘 실행의 run 은 paused 이고 재개에 필요한 것(스냅샷·입력·재개 노드·직전 값·요청 id)을 갖는다 ·
(2) 승인 결정은 **같은 run** 을 이어서 실행한다 — 새 run 이 생기지 않고 step 이 이어 붙고 토큰이 누적된다 ·
(3) execution.resume 은 승인과 무관한 일반 재개 함수다 — paused 가 아니면 거부한다 · (4) 기록이 없는 옛 승인 요청은
예전 방식(새 실행)으로 그대로 재개된다 · (5) 마이그레이션만으로 만든 스키마에 재개 컬럼이 있다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import approval_service
import execution
import models
import run_records
from database import Base

DRAFT = "자기소개서 초안 v1 — 저는 성실한 지원자입니다."


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    return e


def approval_graph(with_reject_branch=False):
    nodes = [N("n1", "startNode"), N("v1", "valueNode", value=DRAFT),
             N("n2", "humanApprovalNode", message="이 초안을 발송할까요?"), N("n3", "outputNode")]
    edges = [E("n1", "v1"), E("v1", "n2")]
    if with_reject_branch:
        nodes += [N("v2", "valueNode", value="거절되어 반려 알림을 보냈습니다."), N("n4", "outputNode")]
        edges += [E("n2", "n3", "approved"), E("n2", "v2", "rejected"), E("v2", "n4")]
    else:
        edges += [E("n2", "n3")]
    return nodes, edges


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000),
                     models.Project(id=10, user_id=1, title="자소서 자동화", graph_data={})])
    session.commit()
    yield session
    session.close()
    engine.dispose()


def pause(db, **graph_kwargs):
    nodes, edges = approval_graph(**graph_kwargs)
    result, _t, logs = execution.start(nodes, edges, trigger_source="manual", db=db, session_id="editor", project_id=10,
                                       executor_user_id=1, extra_flag="유지")
    db.commit()
    assert "승인 대기" in result
    return db.query(models.ApprovalRequest).one(), db.query(models.WorkflowRun).one()


# ── 1. 대기로 멈춘 run 의 재개 상태 ────────────────────────────────────────

def test_승인_대기로_멈춘_run_은_paused_이고_재개_상태를_갖는다(db):
    request, run = pause(db)
    assert run.status == "paused" and run.paused_reason == "approval" and run.finished_at is None
    assert run.resume_node_id == "n2" and run.resume_payload == DRAFT
    assert run.approval_request_id == request.request_id
    assert [n["id"] for n in run.graph_snapshot["nodes"]] == ["n1", "v1", "n2", "n3"] and len(run.graph_snapshot["edges"]) == 3
    assert run.runtime_inputs["extra_flag"] == "유지" and run.runtime_inputs["session_id"] == "editor"
    assert [s.status for s in run.steps] == ["succeeded", "succeeded", "waiting"] and run.step_count == 3


def test_resume_arguments_는_예약_키를_빼고_명시_인자로_돌려준다(db):
    _request, run = pause(db)
    args = run_records.resume_arguments(run)
    assert args["entry_node_id"] == "n2" and args["approval_payload"] == DRAFT
    assert args["session_id"] == "editor" and args["project_id"] == 10 and args["executor_user_id"] == 1
    assert args["runtime_inputs"] == {"extra_flag": "유지"}, "session/project/승인 payload·결정은 명시 인자로 간다"


# ── 2. 승인 결정은 같은 run 을 이어서 실행한다 ─────────────────────────────

def test_승인하면_같은_run_이_이어지고_step_이_붙는다(db):
    request, run = pause(db)
    decided, result, _tokens, logs = approval_service.decide_and_resume(
        db, request_id=request.request_id, actor_user_id=1, decision="approve", comment="좋음")
    assert decided.status == "approved" and decided.resume_outcome == "success" and DRAFT in result

    runs = db.query(models.WorkflowRun).all()
    assert len(runs) == 1, "재개는 새 run 을 만들지 않는다"
    db.refresh(run)
    assert run.status == "succeeded" and run.finished_at is not None and run.paused_reason is None
    assert run.resume_count == 1 and run.resumed_at is not None
    # 앞 구간 3 step(대기 포함) + 재개 구간(n2 승인 통과·n3 출력) 이 sequence 를 이어 간다
    assert [(s.sequence, s.node_id, s.status) for s in run.steps] == [
        (1, "n1", "succeeded"), (2, "v1", "succeeded"), (3, "n2", "waiting"), (4, "n2", "succeeded"), (5, "n3", "succeeded")]
    assert run.step_count == 5
    assert run.steps[-1].output_preview == DRAFT, "승인자가 본 견본이 그대로 이어진다"


def test_거절_갈래가_있으면_거절_경로가_같은_run_에_이어진다(db):
    request, run = pause(db, with_reject_branch=True)
    decided, result, _t, _l = approval_service.decide_and_resume(
        db, request_id=request.request_id, actor_user_id=1, decision="reject")
    assert decided.status == "rejected" and decided.resume_outcome == "success" and "반려" in result
    db.refresh(run)
    assert run.status == "succeeded" and [s.node_id for s in run.steps][-2:] == ["v2", "n4"]


def test_거절_갈래가_없으면_같은_run_이_failed_로_닫힌다(db):
    request, run = pause(db)
    decided, result, _t, _l = approval_service.decide_and_resume(
        db, request_id=request.request_id, actor_user_id=1, decision="reject")
    assert decided.resume_outcome == "halted" and "중단" in result
    db.refresh(run)
    assert run.status == "failed" and run.error_summary and run.resume_count == 1


def test_재개_실행의_진행_이벤트는_같은_run_id_를_싣는다(db):
    import run_events

    request, run = pause(db)
    sub = run_events.subscribe(1)
    try:
        approval_service.decide_and_resume(db, request_id=request.request_id, actor_user_id=1, decision="approve")
        events = []
        while not sub.queue.empty():
            events.append(sub.queue.get_nowait())
    finally:
        run_events.unsubscribe(sub)
    assert events and all(e["runId"] == run.id for e in events)
    assert events[-1]["type"] == "run_finished" and events[-1]["status"] == "succeeded"
    assert events[-1]["triggerSource"] == "approval"


# ── 3. execution.resume 은 일반 재개 함수다 ────────────────────────────────

def test_execution_resume_는_승인_없이도_paused_run_을_이어_실행한다(db):
    _request, run = pause(db)
    result, _t, _l = execution.resume(run.id, db=db, trigger_source="approval",
                                      extra_inputs={"approval_decisions": {"n2": "Y"}})
    assert DRAFT in result
    db.refresh(run)
    assert run.status == "succeeded" and run.resume_count == 1


def test_paused_가_아닌_run_은_재개를_거부한다(db):
    _request, run = pause(db)
    execution.resume(run.id, db=db, trigger_source="approval", extra_inputs={"approval_decisions": {"n2": "Y"}})
    with pytest.raises(ValueError, match="paused 상태만"):
        execution.resume(run.id, db=db, trigger_source="approval")
    with pytest.raises(LookupError):
        execution.resume(999999, db=db, trigger_source="approval")


def test_resume_run_id_는_db_없이_쓸_수_없다():
    nodes, edges = approval_graph()
    with pytest.raises(ValueError, match="db"):
        execution.start(nodes, edges, trigger_source="approval", resume_run_id=1)


# ── 4. 기록이 없는 옛 승인 요청 ─────────────────────────────────────────────

def test_기록이_없는_승인_요청은_예전_방식으로_새_실행을_만든다(db):
    request, run = pause(db)
    # 마이그레이션 전 요청을 흉내 낸다 — run 이 요청을 가리키지 않는다.
    run.approval_request_id = None
    db.commit()
    decided, result, _t, _l = approval_service.decide_and_resume(
        db, request_id=request.request_id, actor_user_id=1, decision="approve")
    assert decided.resume_outcome == "success" and DRAFT in result
    runs = db.query(models.WorkflowRun).order_by(models.WorkflowRun.id).all()
    assert [r.status for r in runs] == ["paused", "succeeded"], "옛 요청은 새 run 으로 재개되고 원 run 은 paused 로 남는다"
    assert runs[1].trigger_source == "approval" and runs[1].resume_count == 0


def test_RUN_RECORDS_0_이면_승인_대기·재개가_예전처럼_동작한다(db, monkeypatch):
    monkeypatch.setenv(run_records.RUN_RECORDS_ENV, "0")
    nodes, edges = approval_graph()
    result, _t, _l = execution.start(nodes, edges, trigger_source="manual", db=db, session_id="editor", project_id=10)
    db.commit()
    assert "승인 대기" in result and db.query(models.WorkflowRun).count() == 0
    request = db.query(models.ApprovalRequest).one()
    decided, result, _t, _l = approval_service.decide_and_resume(
        db, request_id=request.request_id, actor_user_id=1, decision="approve")
    assert decided.resume_outcome == "success" and DRAFT in result


# ── 5. 마이그레이션 ─────────────────────────────────────────────────────────

def test_마이그레이션만으로_만든_스키마에_재개_컬럼이_있다(tmp_path):
    import db_migrate

    url = f"sqlite:///{tmp_path / 'resume.db'}"
    engine = create_engine(url)
    db_migrate.ensure_schema(engine, url)
    columns = {c["name"] for c in inspect(engine).get_columns("workflow_runs")}
    assert {"paused_reason", "resume_node_id", "resume_payload", "graph_snapshot", "runtime_inputs",
            "approval_request_id", "resume_count", "resumed_at"} <= columns
    engine.dispose()
