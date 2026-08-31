import datetime as dt

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from statistics_service import build_statistics
from usage_tracking import (
    EVENT_WORKFLOW_EXECUTION,
    ensure_usage_tracking_schema,
    record_usage,
)


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def test_shared_app_usage_is_billed_to_owner_and_preserves_actor():
    db, _ = make_session()
    owner = models.User(id=1, name="Owner", token_balance=1000)
    actor = models.User(id=2, name="Actor", token_balance=700)
    project = models.Project(id=10, user_id=owner.id, title="Shared project")
    db.add_all([owner, actor, project])
    db.commit()

    log = record_usage(
        db,
        billable_user_id=owner.id,
        actor_user_id=actor.id,
        project_id=project.id,
        token_usage={"input_tokens": 80, "output_tokens": 40, "total_tokens": 120},
        payload="Shared app execution",
        result="ok",
        event_type=EVENT_WORKFLOW_EXECUTION,
        trigger_type="shared_app",
    )
    log.execution_time = dt.datetime(2026, 8, 27, 3, 0, 0)
    db.commit()

    db.refresh(owner)
    db.refresh(actor)
    assert owner.token_balance == 880
    assert actor.token_balance == 700
    assert log.user_id == owner.id
    assert log.billable_user_id == owner.id
    assert log.actor_user_id == actor.id

    response = build_statistics(
        db,
        owner,
        time_range="weekly",
        timezone_name="Asia/Seoul",
        now=dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc),
    )
    assert response["summary"]["period_tokens"] == 120
    assert response["summary"]["execution_count"] == 1
    assert response["summary"]["success_rate"] == 1
    assert response["project_usage"] == [
        {"project_id": project.id, "title": "Shared project", "tokens": 120}
    ]


def test_legacy_app_agent_status_is_classified_as_app_generation():
    db, _ = make_session()
    user = models.User(id=1, name="User", token_balance=500)
    db.add(user)
    db.add(models.FlowExecutionLog(
        user_id=user.id,
        billable_user_id=None,
        event_type=None,
        status="app_agent",
        total_tokens=75,
        execution_time=dt.datetime(2026, 8, 27, 1, 0, 0),
    ))
    db.commit()

    response = build_statistics(
        db,
        user,
        time_range="weekly",
        timezone_name="UTC",
        now=dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc),
    )
    assert response["usage_by_type"] == {
        "execution": 0,
        "agent": 0,
        "app_builder": 75,
        "evaluation": 0,
    }
    assert response["summary"]["execution_count"] == 0


def test_empty_period_returns_zero_buckets_and_explicit_empty_metadata():
    db, _ = make_session()
    user = models.User(id=1, name="User", token_balance=500)
    db.add(user)
    db.commit()

    response = build_statistics(
        db,
        user,
        time_range="weekly",
        timezone_name="Asia/Seoul",
        now=dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc),
    )
    assert response["meta"]["has_usage"] is False
    assert response["summary"]["period_tokens"] == 0
    assert response["summary"]["success_rate"] is None
    assert len(response["chart_data"]) == 7


def test_compatibility_migration_adds_and_backfills_usage_columns():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE flow_execution_logs ("
            "id INTEGER PRIMARY KEY, user_id INTEGER, status VARCHAR, total_tokens INTEGER)"
        ))
        connection.execute(text(
            "INSERT INTO flow_execution_logs (id, user_id, status, total_tokens) "
            "VALUES (1, 9, 'app_agent', 25)"
        ))

    ensure_usage_tracking_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("flow_execution_logs")}
    assert {"actor_user_id", "billable_user_id", "event_type", "outcome", "trigger_type", "request_id"} <= columns
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT actor_user_id, billable_user_id, event_type, outcome "
            "FROM flow_execution_logs WHERE id = 1"
        )).one()
    assert tuple(row) == (9, 9, "app_generation", "success")
