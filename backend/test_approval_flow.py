"""사용자 승인 durable 대기·알림·재개 (ADR-0015) 테스트.

핵심 계약: 승인자가 본 payload 가 그대로 이어진다 · 결정은 한 번만 · 거절도 갈래가 있으면
액션이다 · 서버(세션)가 바뀌어도 DB의 대기 상태로 재개된다 · 알림 실패는 대기에 영향 없다.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import approval_service
import models
from database import Base
from graph import run_workflow

DRAFT = "자기소개서 초안 v1 — 저는 성실한 지원자입니다."


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory(),
    session = session[0]
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com"),
        models.User(id=2, name="Stranger", email="stranger@example.com"),
        models.Project(id=10, user_id=1, title="자소서 자동화", graph_data={}),
    ])
    session.commit()
    yield session, factory
    session.close()


def approval_graph(with_reject_branch=False, notify=None):
    data = {"message": "이 초안을 발송할까요?"}
    data.update(notify or {})
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": DRAFT}},
        {"id": "n2", "type": "humanApprovalNode", "data": data},
        {"id": "n3", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "n1", "target": "v1"},
        {"source": "v1", "target": "n2"},
    ]
    if with_reject_branch:
        nodes += [
            {"id": "v2", "type": "valueNode", "data": {"value": "거절되어 작성자에게 반려 알림을 보냈습니다."}},
            {"id": "n4", "type": "outputNode", "data": {}},
        ]
        edges += [
            {"source": "n2", "target": "n3", "sourceHandle": "approved"},
            {"source": "n2", "target": "v2", "sourceHandle": "rejected"},
            {"source": "v2", "target": "n4"},
        ]
    else:
        edges += [{"source": "n2", "target": "n3"}]
    return nodes, edges


def run_until_pause(db_session, **graph_kwargs):
    nodes, edges = approval_graph(**graph_kwargs)
    result, _, logs = run_workflow(nodes, edges, db=db_session, session_id="editor", project_id=10)
    return result, logs


# ── 대기 전환 ───────────────────────────────────────────────────────────
def test_승인_노드에_도달하면_대기_요청이_생긴다(db):
    session, _ = db
    result, logs = run_until_pause(session)

    assert "승인 대기" in result
    request = session.query(models.ApprovalRequest).one()
    assert request.status == "pending"
    assert request.user_id == 1 and request.project_id == 10
    assert request.node_id == "n2"
    assert DRAFT in request.payload          # 승인자가 볼 견본 = 직전 노드 출력
    assert request.message == "이 초안을 발송할까요?"
    assert request.graph_snapshot["nodes"]
    waiting = [step for step in logs if step.get("status") == "waiting"]
    assert waiting and waiting[0]["approval_request_id"] == request.request_id


def test_승인하면_저장된_payload로_그_지점부터_재개된다(db):
    session, _ = db
    run_until_pause(session)
    request = session.query(models.ApprovalRequest).one()

    decided, result, _, logs = approval_service.decide_and_resume(
        session, request_id=request.request_id, actor_user_id=1, decision="approve", comment="좋음",
    )
    assert decided.status == "approved"
    assert decided.resume_outcome == "success"
    assert DRAFT in result                     # 본 것이 그대로 이어진다
    executed = [step["node_id"] for step in logs]
    assert "v1" not in executed                # 상류는 재실행되지 않는다
    assert "n2" in executed and "n3" in executed


def test_거절하면_거절_갈래가_실행된다(db):
    session, _ = db
    run_until_pause(session, with_reject_branch=True)
    request = session.query(models.ApprovalRequest).one()

    decided, result, _, logs = approval_service.decide_and_resume(
        session, request_id=request.request_id, actor_user_id=1, decision="reject", comment="다시 써주세요",
    )
    assert decided.status == "rejected"
    assert "반려 알림" in result               # 거절 시 액션이 실제로 실행됨
    assert decided.comment == "다시 써주세요"


def test_거절_갈래가_없으면_깔끔히_중단으로_기록된다(db):
    session, _ = db
    run_until_pause(session)
    request = session.query(models.ApprovalRequest).one()

    decided, result, _, _ = approval_service.decide_and_resume(
        session, request_id=request.request_id, actor_user_id=1, decision="reject",
    )
    assert decided.status == "rejected"
    assert decided.resume_outcome == "halted"
    assert "거절되어 워크플로우를 중단" in result


# ── 권한·멱등성·내구성 ──────────────────────────────────────────────────
def test_소유자가_아니면_결정할_수_없다(db):
    session, _ = db
    run_until_pause(session)
    request = session.query(models.ApprovalRequest).one()

    with pytest.raises(PermissionError):
        approval_service.decide_and_resume(
            session, request_id=request.request_id, actor_user_id=2, decision="approve",
        )
    session.refresh(request)
    assert request.status == "pending"


def test_결정은_한_번만_유효하다(db):
    session, _ = db
    run_until_pause(session)
    request = session.query(models.ApprovalRequest).one()

    approval_service.decide_and_resume(
        session, request_id=request.request_id, actor_user_id=1, decision="approve",
    )
    with pytest.raises(RuntimeError):
        approval_service.decide_and_resume(
            session, request_id=request.request_id, actor_user_id=1, decision="reject",
        )
    session.refresh(request)
    assert request.status == "approved"


def test_다른_세션에서도_재개된다(db):
    """서버 재시작 시나리오 — 대기 상태의 근거는 메모리가 아니라 DB 행이다."""
    session, factory = db
    run_until_pause(session)
    request_id = session.query(models.ApprovalRequest).one().request_id
    session.close()

    fresh = factory()
    decided, result, _, _ = approval_service.decide_and_resume(
        fresh, request_id=request_id, actor_user_id=1, decision="approve",
    )
    assert decided.status == "approved"
    assert DRAFT in result
    fresh.close()


# ── 알림 ────────────────────────────────────────────────────────────────
def test_알림_실패는_대기_상태에_영향이_없다(db, monkeypatch):
    session, _ = db
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    result, _ = run_until_pause(session, notify={"notifyEmail": True, "notifyKakao": True})

    request = session.query(models.ApprovalRequest).one()
    assert request.status == "pending"
    assert set(request.notify_channels) == {"email", "kakao"}
    assert all(v.startswith(("skipped", "failed")) for v in request.notify_results.values())
    assert "승인 대기" in result


def test_요청_직렬화는_미리보기를_자른다(db):
    session, _ = db
    run_until_pause(session)
    request = session.query(models.ApprovalRequest).one()
    request.payload = "가" * 5000
    info = approval_service.request_to_dict(request)
    assert len(info["payload_preview"]) == approval_service.PREVIEW_CHARS
    assert info["payload_truncated"] is True
    full = approval_service.request_to_dict(request, include_full_payload=True)
    assert len(full["payload_preview"]) == 5000
