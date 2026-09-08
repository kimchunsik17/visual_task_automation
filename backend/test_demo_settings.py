"""시연 런타임 설정(demo_settings)과 어드민 시연 관리(demo_admin)."""
import datetime as dt
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import demo_admin
import demo_settings
import models
from usage_tracking import EVENT_WORKFLOW_EXECUTION


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "demo_runtime_settings.json"
    monkeypatch.setattr(demo_settings, "PATH", path)
    for key in demo_settings.KEYS:
        monkeypatch.delenv(key, raising=False)
    return path


def test_env_is_the_fallback_and_file_overrides_it(settings_file, monkeypatch):
    # 파일 없음 → .env(환경변수) 해석은 예전 호출부와 같다: bool 은 값이 있으면 켜짐
    assert demo_settings.get_bool("DEMO_UI") is False
    monkeypatch.setenv("DEMO_UI", "1"); monkeypatch.setenv("HIDDEN_NODE_TYPES", "jusoNode, tossNode")
    monkeypatch.setenv("DEMO_GUEST_TOKENS", "70000")
    assert demo_settings.get_bool("DEMO_UI") is True
    assert demo_settings.get_list("HIDDEN_NODE_TYPES") == ["jusoNode", "tossNode"]
    assert demo_settings.get_int("DEMO_GUEST_TOKENS", 50000) == 70000
    # 오버라이드가 이긴다
    snap = demo_settings.update({"DEMO_UI": False, "HIDDEN_NODE_TYPES": ["imageGenerationNode"], "DEMO_GUEST_TOKENS": 200000})
    assert demo_settings.get_bool("DEMO_UI") is False
    assert demo_settings.get_list("HIDDEN_NODE_TYPES") == ["imageGenerationNode"]
    assert demo_settings.get_int("DEMO_GUEST_TOKENS") == 200000
    assert snap["env"]["DEMO_UI"] is True and snap["overrides"]["DEMO_UI"] is False
    assert json.loads(settings_file.read_text())["DEMO_GUEST_TOKENS"] == 200000
    # None 은 오버라이드 삭제 = .env 로 복귀
    demo_settings.update({"DEMO_UI": None})
    assert demo_settings.get_bool("DEMO_UI") is True and "DEMO_UI" not in demo_settings.overrides()


def test_update_validates(settings_file):
    with pytest.raises(ValueError):
        demo_settings.update({"DEMO_GUEST_TOKENS": 10})          # 1,000 미만
    with pytest.raises(ValueError):
        demo_settings.update({"NOT_A_KEY": 1})
    demo_settings.update({"HIDDEN_NODE_TYPES": " a , b ,, a "})   # 문자열도 받아 정리한다
    assert demo_settings.get_list("HIDDEN_NODE_TYPES") == ["a", "b"]
    assert settings_file.exists() and not settings_file.with_suffix(".json.tmp").exists()


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _log(db, *, user, project=None, tokens=0, status="success", event=EVENT_WORKFLOW_EXECUTION, when=None, result=None, trigger="editor"):
    row = models.FlowExecutionLog(user_id=user, actor_user_id=user, billable_user_id=user, project_id=project,
                                  total_tokens=tokens, status=status, event_type=event, trigger_type=trigger,
                                  execution_time=when or dt.datetime.utcnow(), result=result)
    db.add(row); db.commit()
    return row


def test_overview_guests_cleanup_and_runs(settings_file):
    db = _db()
    admin = models.User(google_id="g-admin", email="admin@example.com", name="관리자", role="admin")
    g1 = models.User(google_id="demo-guest-a", email="visitor@example.com", name="(시연용)방문자", token_balance=150000)
    g2 = models.User(google_id="demo-guest-b", email="guest-b@demo.local", name="게스트 B", token_balance=200000)
    db.add_all([admin, g1, g2]); db.commit()
    p = models.Project(user_id=g1.id, title="[시연] 여행지 → 여행 일정표", graph_data={"nodes": [], "edges": []}); db.add(p); db.commit()
    _log(db, user=g1.id, project=p.id, tokens=7000)
    _log(db, user=g1.id, project=p.id, tokens=3000, status="error")
    _log(db, user=admin.id, tokens=500)
    _log(db, user=g1.id, event="email_sent", trigger="smtp")
    _log(db, user=1, event=demo_admin.EVENT_GUEST_ENTRY, trigger="guest_entry")
    _log(db, user=1, event="demo_credential_use", result=json.dumps({"providers": ["youtube_data_api"]}))
    _log(db, user=1, event="demo_credential_use", result=json.dumps({"providers": ["naver_api_hub"]}))
    _log(db, user=g1.id, tokens=99, when=dt.datetime.utcnow() - dt.timedelta(days=2))   # 어제 이전 — 오늘 집계에서 제외

    ov = demo_admin.overview(db)
    assert ov["guests"]["count"] == 2 and ov["guests"]["registered_email"] == 1
    assert ov["guests"]["tokens_used_today"] == 10000 and ov["guests"]["entries_today"] == 1
    assert ov["runs_today"] == {"total": 3, "success": 2, "failed": 1, "by_trigger": {"editor": 3}}
    assert ov["emails_today"] == 1
    assert ov["shared_credentials_today"] == {"youtube_data_api": 1, "naver_api_hub": 1}
    assert ov["settings"]["effective"]["DEMO_GUEST_MAX"] == 300

    rows = demo_admin.guests(db)
    assert [r["id"] for r in rows] == [g2.id, g1.id]
    assert rows[1]["runs"] == 3 and rows[1]["registered"] is True and rows[0]["registered"] is False

    runs = demo_admin.recent_runs(db, limit=10)
    assert runs[0]["user_name"] == "관리자" and runs[0]["is_guest"] is False
    assert runs[1]["project_title"].startswith("[시연]") and runs[1]["status"] == "error" and runs[1]["is_guest"] is True

    # 최근 활동자 유지 옵션: g1 은 방금 실행했으니 남고 g2 만 지워진다
    result = demo_admin.cleanup_guests(db, keep_active_minutes=30)
    assert result == {"deleted": 1, "kept_active": 1, "remaining": 1}
    result = demo_admin.cleanup_guests(db)
    assert result["deleted"] == 1 and result["remaining"] == 0
    assert db.query(models.Project).count() == 0                # 게스트 프로젝트도 함께
    assert db.query(models.User).filter(models.User.id == admin.id).count() == 1
