"""이메일 수신자 자리표시자 {{USER_EMAIL}} 해석(delivery_runtime.resolve_recipient).

시연 콘텐츠의 이메일 노드는 수신자를 자리표시자로 두고 발송 직전 실행 계정의 이메일로 푼다 —
게스트의 실제 이메일은 입장 뒤 최초 1회 등록되므로 시딩 시점에는 알 수 없기 때문이다.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from delivery_runtime import USER_EMAIL_PLACEHOLDER, resolve_recipient, send_smtp


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_placeholder_resolves_to_owner_email():
    db = _db()
    real = models.User(google_id="g1", email="visitor@example.com", name="v")
    guest = models.User(google_id="demo-guest-x", email="guest-x@demo.local", name="게스트")
    db.add_all([real, guest]); db.commit()

    assert resolve_recipient(USER_EMAIL_PLACEHOLDER, db=db, owner_user_id=real.id) == "visitor@example.com"
    # 게스트의 임시 주소(@demo.local)는 받을 수 없으니 비운다 — 존재하지 않는 주소로 보내지 않는다
    assert resolve_recipient(USER_EMAIL_PLACEHOLDER, db=db, owner_user_id=guest.id) == ""
    # 자리표시자가 아닌 값은 손대지 않는다 / 소유자를 모르면 빈 값
    assert resolve_recipient("a@b.c", db=db, owner_user_id=guest.id) == "a@b.c"
    assert resolve_recipient(USER_EMAIL_PLACEHOLDER, db=None, owner_user_id=0) == ""


def test_send_smtp_explains_unregistered_recipient():
    """이메일을 아직 등록하지 않은 게스트가 실행하면 노드 설정 오류가 아니라 등록 안내로 끝난다."""
    db = _db()
    guest = models.User(google_id="demo-guest-y", email="guest-y@demo.local", name="게스트")
    db.add(guest); db.commit()

    res = send_smtp(smtp_server="localhost", smtp_port=25, smtp_user="u", smtp_password="p",
                    to_email=USER_EMAIL_PLACEHOLDER, subject="s", body="본문", db=db, owner_user_id=guest.id)
    assert res.error is not None and res.error.code == "VALIDATION_REQUIRED"
    assert "등록" in str(res) and "본문" in str(res)      # 안내 + 만들려던 본문은 남긴다


def test_unsaved_editor_run_resolves_recipient_to_executor(monkeypatch):
    """저장 전 그래프(project_id 없음)를 실행해도 이메일 노드 수신자는 실행한 사용자의 이메일로 풀린다.
    2026-09-06 부스 점검: 소유자가 0 으로 남아 게스트의 에디터 실행에서 메일이 한 통도 가지 않았다."""
    import delivery_runtime
    from graph import run_workflow

    db = _db()
    guest = models.User(google_id="demo-guest-z", email="visitor@example.com", name="(시연용)방문자", token_balance=1000)
    db.add(guest); db.commit()
    captured = {}

    def fake_send_smtp(**kw):
        captured["to_email"] = delivery_runtime.resolve_recipient(kw["to_email"], db=kw.get("db"), owner_user_id=kw.get("owner_user_id", 0))
        from node_errors.contract import NodeResult
        return NodeResult.success({"provider": "smtp"}, display="보냄")
    monkeypatch.setattr(delivery_runtime, "send_smtp", fake_send_smtp)
    monkeypatch.setenv("SMTP_USER", "u@test"); monkeypatch.setenv("SMTP_PASSWORD", "p")

    nodes = [
        {"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}},
        {"id": "v", "type": "valueNode", "data": {"value": "본문"}, "position": {"x": 0, "y": 0}},
        {"id": "m", "type": "emailNode", "data": {"toEmail": USER_EMAIL_PLACEHOLDER, "subject": "s"}, "position": {"x": 0, "y": 0}},
        {"id": "o", "type": "outputNode", "data": {}, "position": {"x": 0, "y": 0}},
    ]
    edges = [{"id": "e1", "source": "s", "target": "v"}, {"id": "e2", "source": "v", "target": "m"}, {"id": "e3", "source": "m", "target": "o"}]
    run_workflow(nodes, edges, db=db, session_id="editor", project_id=None, executor_user_id=guest.id)
    assert captured.get("to_email") == "visitor@example.com", captured
