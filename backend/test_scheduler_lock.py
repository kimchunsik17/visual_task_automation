"""스케줄 실행 중복 발화 방지 — advisory lock (백로그 32 ENGINE 선행 항목) 테스트.

계약: 같은 프로젝트의 스케줄 실행은 한 번에 하나만 돈다. 잠금을 못 잡은 발화는 실행 없이 끝난다.
PostgreSQL 이면 세션 advisory lock, 아니면(테스트 sqlite) 프로세스 안 집합으로 같은 의미를 낸다.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import execution
import models
import scheduler
from database import Base

NS = execution.SCHEDULE_LOCK_NAMESPACE


def test_local_lock_is_exclusive_per_key_and_released_on_exit():
    with execution.advisory_lock(NS, 41) as first:
        assert first is True
        with execution.advisory_lock(NS, 41) as second:
            assert second is False, "같은 키는 두 번 잡히면 안 된다"
        with execution.advisory_lock(NS, 42) as other_key:
            assert other_key is True, "다른 키는 독립이다"
        with execution.advisory_lock(NS + 1, 41) as other_ns:
            assert other_ns is True, "다른 namespace 는 독립이다"
    with execution.advisory_lock(NS, 41) as again:
        assert again is True, "빠져나오면 풀려야 한다"


def test_local_lock_is_released_even_when_body_raises():
    with pytest.raises(RuntimeError):
        with execution.advisory_lock(NS, 43) as acquired:
            assert acquired
            raise RuntimeError("본문 실패")
    with execution.advisory_lock(NS, 43) as again:
        assert again is True


def test_scheduled_run_is_skipped_while_another_holds_the_lock(monkeypatch):
    monkeypatch.setattr(execution, "start", lambda *a, **k: pytest.fail("잠금이 잡혀 있으면 실행하면 안 된다"))
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: pytest.fail("DB 도 열지 않아야 한다"))
    with execution.advisory_lock(NS, 77) as held:
        assert held
        scheduler.execute_scheduled_project(77)  # 조용히 스킵


@pytest.fixture
def scheduled_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com", token_balance=10_000),
        models.Project(id=77, user_id=1, title="아침 브리핑", graph_data={
            "is_live": True,
            "nodes": [{"id": "s", "type": "scheduleNode", "data": {"cronExpression": "0 7 * * *"}},
                      {"id": "o", "type": "outputNode", "data": {}}],
            "edges": [{"source": "s", "target": "o"}],
        }),
    ])
    session.commit()
    session.close()
    yield factory
    engine.dispose()


def test_scheduled_run_goes_through_execution_start_with_schedule_source(monkeypatch, scheduled_db):
    monkeypatch.setattr(scheduler, "SessionLocal", scheduled_db)
    calls = []

    def fake_start(nodes, edges, *, trigger_source, **kwargs):
        calls.append({"trigger_source": trigger_source, "project_id": kwargs.get("project_id"),
                      "session_id": kwargs.get("session_id"), "node_types": [n["type"] for n in nodes]})
        return "브리핑 발송 완료", {"total_tokens": 12}, []

    monkeypatch.setattr(execution, "start", fake_start)
    scheduler.execute_scheduled_project(77)

    assert calls == [{"trigger_source": "schedule", "project_id": 77, "session_id": "scheduled_77",
                      "node_types": ["scheduleNode", "outputNode"]}]
    # 잠금은 끝나면 풀린다 — 다음 발화가 스킵되지 않는다.
    with execution.advisory_lock(NS, 77) as free:
        assert free is True


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="PostgreSQL advisory lock 은 실 DB 에서만")
def test_postgres_advisory_lock_is_exclusive_across_connections():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    try:
        with execution.advisory_lock(NS, 990001, bind=engine) as first:
            assert first is True
            with execution.advisory_lock(NS, 990001, bind=engine) as second:
                assert second is False, "다른 연결에서도 같은 키는 막혀야 한다"
        with execution.advisory_lock(NS, 990001, bind=engine) as again:
            assert again is True, "unlock 이 실제로 풀어야 한다 — 풀리지 않으면 다음 발화가 영영 스킵된다"
    finally:
        engine.dispose()
