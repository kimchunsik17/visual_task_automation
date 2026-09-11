"""run_events — 실행 진행 이벤트(노드 경계 pub/sub + SSE, 백로그 32 ENGINE-1 3단계, ADR-0028) 테스트.

계약: (1) 실행한 사용자(executor_user_id)의 구독자에게 node_finished(두 엔진)·node_started(인터프리터)·run_finished 가
순서대로 간다 · (2) 이벤트는 실행 결과·로그·기록을 바꾸지 않는다 · (3) 실행한 사용자를 모르거나 RUN_EVENTS=0 이면 이벤트가
없다 · (4) 큐가 가득 차도 실행은 멈추지 않는다 · (5) SSE 본문은 ready → run 이벤트 → keepalive 순이다.
"""

from __future__ import annotations

import asyncio
import copy
import json
import queue

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import models
import run_events
from database import Base


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
    session.add_all([models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000),
                     models.Project(id=10, user_id=1, title="이벤트 테스트", graph_data={})])
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def inbox():
    sub = run_events.subscribe(1)
    yield sub
    run_events.unsubscribe(sub)


def _drain(sub):
    events = []
    while True:
        try:
            events.append(sub.queue.get_nowait())
        except queue.Empty:
            return events


def _run(db, nodes, edges, **kw):
    kw.setdefault("trigger_source", "manual")
    kw.setdefault("executor_user_id", 1)
    kw.setdefault("project_id", 10)
    kw.setdefault("session_id", "editor")
    return execution.start(copy.deepcopy(nodes), copy.deepcopy(edges), db=db, **kw)


def test_legacy_는_노드가_끝날_때마다_이벤트를_내고_마지막에_run_finished_를_낸다(db, inbox, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    _run(db, *LINEAR, default_input="")
    events = _drain(inbox)
    run = db.query(models.WorkflowRun).one()

    assert [e["type"] for e in events] == ["node_finished"] * 3 + ["run_finished"]
    assert [(e["nodeId"], e["sequence"], e["status"]) for e in events[:3]] == [("s", 1, "succeeded"), ("v", 2, "succeeded"),
                                                                              ("o", 3, "succeeded")]
    assert events[1]["outputPreview"] == "값" and events[1]["nodeType"] == "valueNode"
    assert events[-1]["status"] == "succeeded" and events[-1]["runId"] == run.id
    assert all(e["runId"] == run.id and e["projectId"] == 10 and e["sessionId"] == "editor"
               and e["triggerSource"] == "manual" and e["engine"] == "legacy" and e["at"] for e in events)


def test_인터프리터는_노드_시작_이벤트도_내고_흐름_노드는_한_번만_시작한다(db, inbox, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENGINE", "interpreter")
    nodes = [N("s", "startNode"), N("v", "valueNode", value="x"), N("l", "loopNode", maxIterations=2),
             N("body", "dynamicInputNode", inputLabel="회차"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "l"), E("l", "body", "loop_start"), E("l", "o", "done")]
    _run(db, nodes, edges, body="+")
    events = _drain(inbox)
    kinds = [(e["type"], e.get("nodeId")) for e in events]

    # 시작/종료가 노드마다 짝을 이룬다. loop 는 머리에서 한 번 시작하고 회차가 다 끝난 뒤 한 번 종료된다(log_step 이 꼬리에 있다).
    assert kinds[:4] == [("node_started", "s"), ("node_finished", "s"), ("node_started", "v"), ("node_finished", "v")]
    assert kinds.count(("node_started", "l")) == 1 and kinds.count(("node_finished", "l")) == 1
    assert kinds.count(("node_started", "body")) == 2 and kinds.count(("node_finished", "body")) == 2
    assert kinds[-3:] == [("node_started", "o"), ("node_finished", "o"), ("run_finished", None)]
    assert all(e["engine"] == "interpreter" for e in events)


def test_실패한_실행은_run_finished_에_failed_와_요약을_싣는다(db, inbox):
    nodes = [N("s", "startNode"), N("l", "loopNode", maxIterations="abc"), N("o", "outputNode")]
    _run(db, nodes, [E("s", "l"), E("l", "o", "done")], default_input="")
    last = _drain(inbox)[-1]
    assert last["type"] == "run_finished" and last["status"] == "failed" and "abc" in last["errorSummary"]


def test_엔진_예외도_run_finished_failed_로_알린다(db, inbox, monkeypatch):
    import graph

    def boom(*a, **k):
        raise RuntimeError("엔진 폭발")

    monkeypatch.setattr(graph, "run_workflow", boom)
    with pytest.raises(RuntimeError):
        _run(db, *LINEAR)
    events = _drain(inbox)
    assert [e["type"] for e in events] == ["run_finished"] and events[0]["status"] == "failed"
    assert "엔진 폭발" in events[0]["errorSummary"]


def test_이벤트는_실행_결과_로그_기록을_바꾸지_않는다(db, inbox, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    with_events = _run(db, *LINEAR, default_input="")
    monkeypatch.setenv(run_events.RUN_EVENTS_ENV, "0")
    without_events = _run(db, *LINEAR, default_input="")
    strip = lambda logs: [(s["node_id"], s["status"], s["result_data"]) for s in logs]
    assert with_events[0] == without_events[0] and strip(with_events[2]) == strip(without_events[2])
    runs = db.query(models.WorkflowRun).order_by(models.WorkflowRun.id).all()
    assert [r.step_count for r in runs] == [3, 3]


def test_실행한_사용자를_모르면_이벤트가_없다(db, inbox):
    _run(db, *LINEAR, executor_user_id=None, default_input="")
    assert _drain(inbox) == []


def test_RUN_EVENTS_0_이면_이벤트가_없다(db, inbox, monkeypatch):
    monkeypatch.setenv(run_events.RUN_EVENTS_ENV, "0")
    _run(db, *LINEAR, default_input="")
    assert _drain(inbox) == []


def test_db_없이도_실행한_사용자가_있으면_이벤트는_간다(inbox):
    execution.start(*copy.deepcopy(LINEAR), trigger_source="manual", executor_user_id=1, default_input="")
    events = _drain(inbox)
    assert [e["type"] for e in events] == ["node_finished"] * 3 + ["run_finished"]
    assert events[-1]["runId"] is None and events[-1]["status"] == "succeeded"


def test_가득_찬_구독자는_이벤트를_버리고_실행은_계속된다(db, monkeypatch):
    monkeypatch.setattr(run_events, "QUEUE_MAX", 1)
    sub = run_events.subscribe(1)
    sub.queue = queue.Queue(maxsize=1)
    try:
        result, _t, _l = _run(db, *LINEAR, default_input="")
        assert result == "값"
        assert sub.queue.qsize() == 1 and sub.dropped == 3
    finally:
        run_events.unsubscribe(sub)


def test_구독_수와_해지(db):
    assert run_events.stream_count(1) == 0
    a, b = run_events.subscribe(1), run_events.subscribe(1)
    assert run_events.stream_count(1) == 2
    run_events.unsubscribe(a)
    run_events.unsubscribe(b)
    assert run_events.stream_count(1) == 0
    assert run_events.publish(1, {"type": "x"}) == 0


def test_sse_본문은_ready_뒤_이벤트_그리고_keepalive_순이다():
    async def scenario():
        stream = run_events.event_stream(7, heartbeat_seconds=0.2)
        first = await stream.__anext__()
        assert first.startswith("event: ready\n")
        assert run_events.stream_count(7) == 1
        run_events.publish(7, {"type": "node_finished", "nodeId": "v"})
        second = await stream.__anext__()
        assert second.startswith("event: run\n")
        payload = json.loads(second.split("data: ", 1)[1].strip())
        assert payload == {"type": "node_finished", "nodeId": "v"}
        third = await stream.__anext__()
        assert third == ": keepalive\n\n"
        await stream.aclose()
        assert run_events.stream_count(7) == 0

    asyncio.run(scenario())
