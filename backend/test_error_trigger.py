"""에러 트리거 — 실패한 실행 뒤 graph_data.errorWorkflowId 의 워크플로우를 부른다 (백로그 32 ENGINE-3 3단계, ADR-0030 추기).

계약: (1) 노드 오류로 failed 로 끝나면 에러 워크플로우가 default_input=실패 payload JSON 으로 돈다(인라인) · (2) 엔진 예외로 실패해도
돈다 · (3) 큐가 켜져 있으면 enqueue 만 하고 워커가 실행한다 · (4) 연쇄 금지 — 에러 워크플로우 자신의 실패는 다시 트리거하지 않는다 ·
(5) 자기 자신·없는 프로젝트·다른 소유자·설정 없음·성공·db 없음·mock 출처는 부르지 않는다 · (6) 인라인 실행이 원래 실행의 run id
슬롯을 덮지 않는다(원래 실행의 FlowExecutionLog.run_id 유지) · (7) 인라인 실행은 과금 기록(trigger_type error_trigger)을 남긴다.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import error_trigger
import execution
import graph
import models
import run_queue
import run_worker
from connectors import errors as connector_errors
from connectors.services import http_request
from database import Base
from usage_tracking import EVENT_WORKFLOW_EXECUTION, record_usage


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target):
    return {"source": source, "target": target}


FAILING = {"nodes": [N("s", "startNode"), N("h", "httpRequestNode", url="https://api.example.test/x", method="GET"), N("o", "outputNode")],
           "edges": [E("s", "h"), E("h", "o")]}
# 에러 워크플로우: 웹훅 노드가 default_input(=실패 payload)을 받아 그대로 출력한다 — 알림 노드 자리
NOTIFIER = {"nodes": [N("w", "webhookNode"), N("o", "outputNode")], "edges": [E("w", "o")]}


class AlwaysFail:
    def __init__(self):
        self.calls = 0

    def __call__(self, definition, *, method, url, headers=None, body=None, session=None):
        self.calls += 1
        raise connector_errors.ConnectorError(code=connector_errors.AUTH_INVALID, service="테스트 API", status=401)


@pytest.fixture
def factory(monkeypatch):
    monkeypatch.setattr(http_request, "call", AlwaysFail())
    monkeypatch.delenv(run_queue.QUEUE_ENV, raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    db = make()
    db.add_all([
        models.User(id=1, name="Owner", email="owner@example.com", token_balance=10_000),
        models.User(id=2, name="Other", email="other@example.com", token_balance=10_000),
        models.Project(id=1, user_id=1, title="실패하는 워크플로우", graph_data={**FAILING, "errorWorkflowId": 2}),
        models.Project(id=2, user_id=1, title="실패 알림", graph_data=dict(NOTIFIER)),
        models.Project(id=3, user_id=2, title="남의 알림", graph_data=dict(NOTIFIER)),
    ])
    db.commit()
    db.close()
    yield make
    engine.dispose()


def _run_failing(db, project_id=1, trigger_source="manual", **kw):
    project = db.get(models.Project, project_id)
    nodes, edges = project.graph_data["nodes"], project.graph_data["edges"]
    return execution.start(nodes, edges, trigger_source=trigger_source, db=db, project_id=project_id, executor_user_id=1,
                           session_id=f"t_{project_id}", **kw)


def _runs(db, project_id):
    return db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == project_id).order_by(models.WorkflowRun.id).all()


def _set_error_workflow(db, project_id, value):
    project = db.get(models.Project, project_id)
    data = dict(project.graph_data)
    if value is None:
        data.pop("errorWorkflowId", None)
    else:
        data["errorWorkflowId"] = value
    project.graph_data = data
    db.commit()


# ── 1·6·7. 인라인 ───────────────────────────────────────────────────────────

def test_노드_오류로_실패하면_에러_워크플로우가_payload_를_받아_인라인으로_돈다(factory):
    db = factory()
    result, tokens, logs = _run_failing(db)
    # 원래 실행의 호출부가 하듯 과금을 남기고 커밋 — run id 슬롯이 보존됐는지 여기서 드러난다
    log = record_usage(db, billable_user_id=1, actor_user_id=1, project_id=1, token_usage=tokens, payload="t", result=result,
                       event_type=EVENT_WORKFLOW_EXECUTION, outcome="error", trigger_type="editor")
    db.commit()

    failed = _runs(db, 1)
    assert len(failed) == 1 and failed[0].status == "failed"
    assert log.run_id == failed[0].id, "에러 워크플로우 인라인 실행이 원래 실행의 run id 슬롯을 덮으면 안 된다"

    notified = _runs(db, 2)
    assert len(notified) == 1
    run = notified[0]
    assert run.trigger_source == "error_trigger" and run.status == "succeeded" and run.session_id == "error_1"
    output = next(s for s in run.steps if s.node_id == "o")
    payload = json.loads(output.output_preview)
    assert payload["event"] == "workflow_failed" and payload["failedProjectId"] == 1 and payload["failedProjectTitle"] == "실패하는 워크플로우"
    assert payload["runId"] == failed[0].id and payload["triggerSource"] == "manual"
    assert payload["failedNodes"] == [{"nodeId": "h", "nodeType": "httpRequestNode", "code": "CREDENTIAL_INVALID",
                                       "message": payload["failedNodes"][0]["message"]}]
    assert payload["errorSummary"] and payload["at"]

    billing = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == 2).one()
    assert billing.trigger_type == "error_trigger" and billing.run_id == run.id and billing.billable_user_id == 1
    db.close()


# ── 2. 엔진 예외 ────────────────────────────────────────────────────────────

def test_엔진_예외로_실패해도_에러_워크플로우가_돈다(factory, monkeypatch):
    real = graph.run_workflow
    state = {"armed": True}

    def boom(nodes, edges, **kw):
        if state["armed"]:
            state["armed"] = False
            raise RuntimeError("엔진이 터졌다")
        return real(nodes, edges, **kw)

    monkeypatch.setattr(graph, "run_workflow", boom)
    db = factory()
    with pytest.raises(RuntimeError):
        _run_failing(db)
    db.commit()
    notified = _runs(db, 2)
    assert len(notified) == 1 and notified[0].status == "succeeded"
    payload = json.loads(next(s for s in notified[0].steps if s.node_id == "o").output_preview)
    assert payload["errorSummary"] == "RuntimeError: 엔진이 터졌다" and payload["failedNodes"] == []
    db.close()


# ── 3. 큐 ───────────────────────────────────────────────────────────────────

def test_큐가_켜져_있으면_enqueue_만_하고_워커가_실행한다(factory, monkeypatch):
    monkeypatch.setenv(run_queue.QUEUE_ENV, "1")
    db = factory()
    _run_failing(db)
    db.commit()
    queued = _runs(db, 2)
    assert len(queued) == 1 and queued[0].status == "queued" and queued[0].trigger_source == "error_trigger"
    assert '"failedProjectId": 1' in queued[0].runtime_inputs["default_input"]
    assert db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == 2).count() == 0, "과금은 워커가"

    worker = run_worker.Worker(factory, worker_id="w-test", heartbeat_seconds=60)
    assert worker.run_once() == queued[0].id
    db.expire_all()
    run = _runs(db, 2)[0]
    assert run.status == "succeeded" and run.worker_id == "w-test"
    assert db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == 2).one().trigger_type == "error_trigger"
    db.close()


# ── 4·5. 막는 것 ────────────────────────────────────────────────────────────

def test_에러_워크플로우_자신의_실패는_다시_트리거하지_않는다(factory):
    db = factory()
    _set_error_workflow(db, 2, 1)                       # 알림 → 실패 워크플로우 로 되돌아가는 설정
    project2 = db.get(models.Project, 2)
    data = dict(project2.graph_data)
    data["nodes"], data["edges"] = FAILING["nodes"], FAILING["edges"]      # 알림 워크플로우도 실패하게
    project2.graph_data = data
    db.commit()
    _run_failing(db, project_id=2, trigger_source="error_trigger")
    db.commit()
    assert len(_runs(db, 2)) == 1 and _runs(db, 1) == [], "연쇄 금지"
    db.close()


@pytest.mark.parametrize("setting", [None, 0, "abc", 1, 999, 3])
def test_설정이_없거나_자기_자신_없는_프로젝트_다른_소유자면_부르지_않는다(factory, setting):
    db = factory()
    _set_error_workflow(db, 1, setting)
    _run_failing(db)
    db.commit()
    assert len(_runs(db, 1)) == 1 and _runs(db, 1)[0].status == "failed"
    assert _runs(db, 2) == [] and _runs(db, 3) == []
    db.close()


def test_성공한_실행과_mock_출처의_실패는_부르지_않는다(factory, monkeypatch):
    db = factory()
    _run_failing(db, trigger_source="mock")
    db.commit()
    assert _runs(db, 2) == []

    monkeypatch.setattr(http_request, "call", lambda *a, **k: '{"ok": true}')
    _run_failing(db)
    db.commit()
    assert _runs(db, 1)[-1].status == "succeeded" and _runs(db, 2) == []
    db.close()


def test_db_가_없으면_조용히_넘어간다(monkeypatch):
    monkeypatch.setattr(http_request, "call", AlwaysFail())
    result, _tokens, logs = execution.start(FAILING["nodes"], FAILING["edges"], trigger_source="manual", project_id=1)
    assert "HTTP Request Error" in result


def test_에러_워크플로우의_예외는_원래_실패를_바꾸지_않는다(factory, monkeypatch):
    db = factory()
    real = execution.start
    calls = {"n": 0}

    def flaky_start(nodes, edges, **kw):
        calls["n"] += 1
        if kw.get("trigger_source") == "error_trigger":
            raise RuntimeError("알림 워크플로우가 터졌다")
        return real(nodes, edges, **kw)

    monkeypatch.setattr(execution, "start", flaky_start)
    result, _tokens, _logs = _run_failing(db)
    assert "HTTP Request Error" in result and calls["n"] == 2
    db.close()


def test_trigger_source_목록에_error_trigger_가_있다():
    assert error_trigger.TRIGGER_SOURCE in execution.TRIGGER_SOURCES
    assert error_trigger.configured_error_workflow_id(models.Project(graph_data={"errorWorkflowId": "7"})) == 7
    assert error_trigger.configured_error_workflow_id(models.Project(graph_data={"errorWorkflowId": -1})) is None
    assert error_trigger.configured_error_workflow_id(models.Project(graph_data=None)) is None
