"""커뮤니티 안전·정체성 공통 기반 (ADR-0020, 우선 백로그 22) 계약 테스트.

§4.16 검증 매트릭스의 층을 따른다 — 핸들·이메일 비노출·차단·신고/조치·권한·rate limit·알림·보존.

이 파일이 지키는 한 문장: **차단은 화면이 아니라 API 응답에서 적용된다.** 화면에서만 숨기면
API 를 직접 부르는 경로가 그대로 남는다.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import community_identity as identity
import community_safety as safety
import models
import notifications
import rate_limit
from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="김민수", email="minsu@example.com", role="user"),
        models.User(id=2, name="Park Younghee", email="younghee@example.com", role="user"),
        models.User(id=3, name="관리자", email="admin@example.com", role="admin"),
        models.User(id=4, name="Mod", email="mod@example.com", role="moderator"),
    ])
    session.commit()
    yield session
    session.close()


def _user(db, uid):
    return db.query(models.User).filter(models.User.id == uid).first()


def _profile(db, uid, handle):
    return identity.create_profile(db, _user(db, uid), handle=handle)


def _friend(db, a, b):
    db.add_all([models.Friendship(user_id=a, friend_id=b), models.Friendship(user_id=b, friend_id=a)])
    db.commit()


# ── 1. 핸들 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("handle, ok", [
    ("minsu", True), ("min-su-2", True), ("a1b", True),
    ("ab", False),                       # 너무 짧다
    ("a" * 21, False),                   # 너무 길다
    ("-minsu", False), ("minsu-", False),
    ("min--su", False),                  # 하이픈 연속
    ("Minsu", True),                     # 대문자는 소문자로 정규화된다
    ("min_su", False), ("민수", False), ("min su", False),
    ("admin", False), ("official", False), ("workflow-ai", False),
])
def test_handle_rules(handle, ok):
    if ok:
        assert identity.normalize(handle) == handle.lower()
    else:
        with pytest.raises(identity.HandleError):
            identity.normalize(handle)


def test_confusable_handles_cannot_impersonate(db):
    _profile(db, 1, "workflow-team")
    # `w0rkfl0w-team` 은 눈으로 구분되지 않는다 — 정규형이 같으면 중복으로 본다.
    assert identity.is_taken(db, "w0rkfl0w-team")
    with pytest.raises(identity.HandleError):
        identity.create_profile(db, _user(db, 2), handle="w0rkfl0w-team")


def test_profiles_are_created_on_first_entry_not_backfilled(db):
    """핸들은 커뮤니티 최초 진입 시 만든다 — 가입만 한 사용자는 공개 표면에 **없다**."""
    assert identity.get_profile(db, 1) is None
    assert identity.find_by_handle(db, "minsu") is None

    _profile(db, 1, "minsu")
    assert identity.find_by_handle(db, "minsu").user_id == 1
    # 다른 사용자는 여전히 없다.
    assert identity.get_profile(db, 2) is None


def test_suggested_handle_is_derived_and_unique(db):
    suggestion = identity.suggest(db, _user(db, 2))
    assert identity.normalize(suggestion) == suggestion
    _profile(db, 2, suggestion)
    assert identity.suggest(db, _user(db, 1)) != suggestion


def test_public_profile_never_carries_an_email(db):
    profile = _profile(db, 1, "minsu")
    payload = identity.public_profile(profile)
    assert "minsu@example.com" not in str(payload)
    assert set(payload) == {"handle", "displayName", "bio", "avatarArtifactId", "joinedAt", "suspended"}


# ── 2. 차단 ─────────────────────────────────────────────────────────────
def test_block_removes_friendship_and_notifies_the_blocked_side(db):
    _profile(db, 1, "minsu"); _profile(db, 2, "younghee")
    _friend(db, 1, 2)
    db.add(models.FriendRequest(from_user_id=2, to_user_id=1, status="pending"))
    db.commit()

    safety.block(db, _user(db, 1), _user(db, 2))

    assert db.query(models.Friendship).count() == 0, "차단하면 친구 관계가 해제된다"
    assert db.query(models.FriendRequest).filter(models.FriendRequest.status == "pending").count() == 0
    notice = db.query(models.Notification).filter(models.Notification.user_id == 2).one()
    assert notice.kind == "blocked" and notice.quiet is True
    # 이유를 알리면 곧바로 해명·보복 접촉이 된다.
    assert "minsu" not in (notice.body or "") and "차단한" not in (notice.body or "")


def test_block_hides_both_directions(db):
    """차단당한 쪽도 상대를 보지 못해야 한다 — 한쪽만 숨기면 반쪽짜리다."""
    _profile(db, 1, "minsu"); _profile(db, 2, "younghee")
    safety.block(db, _user(db, 1), _user(db, 2))
    assert safety.hidden_user_ids(db, 1) == {2}
    assert safety.hidden_user_ids(db, 2) == {1}
    assert safety.is_blocked_between(db, 1, 2) and safety.is_blocked_between(db, 2, 1)


def test_unblock_does_not_restore_friendship(db):
    _profile(db, 1, "minsu"); _profile(db, 2, "younghee")
    _friend(db, 1, 2)
    safety.block(db, _user(db, 1), _user(db, 2))
    assert safety.unblock(db, _user(db, 1), _user(db, 2)) is True
    assert safety.hidden_user_ids(db, 1) == set()
    assert db.query(models.Friendship).count() == 0, "끊은 친구를 자동으로 되돌리지 않는다"


def test_blocking_yourself_is_refused(db):
    _profile(db, 1, "minsu")
    with pytest.raises(safety.SafetyError):
        safety.block(db, _user(db, 1), _user(db, 1))


def test_blocking_twice_is_idempotent(db):
    _profile(db, 1, "minsu"); _profile(db, 2, "younghee")
    safety.block(db, _user(db, 1), _user(db, 2))
    safety.block(db, _user(db, 1), _user(db, 2))
    assert db.query(models.Block).count() == 1


# ── 3. 신고와 조치 ──────────────────────────────────────────────────────
def test_report_validates_target_and_reason(db):
    with pytest.raises(safety.SafetyError):
        safety.report(db, _user(db, 1), target_type="workflow", target_id="1", reason="spam")
    with pytest.raises(safety.SafetyError):
        safety.report(db, _user(db, 1), target_type="post", target_id="1", reason="지어낸사유")


def test_duplicate_open_reports_do_not_inflate_the_queue(db):
    first = safety.report(db, _user(db, 1), target_type="post", target_id="7", reason="spam")
    again = safety.report(db, _user(db, 1), target_type="post", target_id="7", reason="harassment")
    assert first.id == again.id and db.query(models.Report).count() == 1


def test_resolving_a_report_stamps_when_retention_starts(db):
    """보존 30일은 **신고 처리가 끝난 시점부터** 센다 — 조사 중에 근거가 사라지면 안 된다."""
    row = safety.report(db, _user(db, 1), target_type="post", target_id="7", reason="spam")
    assert row.resolved_at is None
    safety.resolve_report(db, _user(db, 3), row.id, status="reviewing")
    assert row.resolved_at is None, "검토 중에는 보존 시계가 돌지 않는다"
    safety.resolve_report(db, _user(db, 3), row.id, status="resolved")
    assert row.resolved_at is not None


def test_suspension_blocks_writing_but_keeps_reading_and_is_reversible(db):
    _profile(db, 1, "minsu")
    safety.suspend_user(db, _user(db, 3), _user(db, 1), days=7, reason="도배")
    profile = identity.get_profile(db, 1)
    assert identity.is_suspended(profile) is True
    assert db.query(models.Notification).filter(models.Notification.user_id == 1).count() == 1

    safety.restore_user(db, _user(db, 3), _user(db, 1))
    assert identity.is_suspended(identity.get_profile(db, 1)) is False
    actions = [a.action for a in db.query(models.ModerationAction).order_by(models.ModerationAction.id).all()]
    assert actions == ["suspend", "restore"], "되돌리기도 이력에 남는다"
    assert all(a.admin_id == 3 for a in db.query(models.ModerationAction).all())


def test_suspending_a_member_without_a_profile_is_refused(db):
    with pytest.raises(safety.SafetyError):
        safety.suspend_user(db, _user(db, 3), _user(db, 2), days=1)


# ── 4. 권한 ─────────────────────────────────────────────────────────────
def test_roles_separate_staff_from_admin(db):
    assert safety.is_staff(_user(db, 1)) is False
    assert safety.is_staff(_user(db, 4)) is True and safety.is_admin(_user(db, 4)) is False
    assert safety.is_staff(_user(db, 3)) is True and safety.is_admin(_user(db, 3)) is True


def test_admin_emails_only_bootstraps_the_first_admin(db, monkeypatch):
    db.query(models.User).filter(models.User.id == 3).first().role = "user"
    db.commit()
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    assert safety.bootstrap_admins(db) == 1
    assert _user(db, 3).role == "admin"
    # 두 번째 호출은 아무것도 바꾸지 않는다 — 부트스트랩이지 동기화가 아니다.
    assert safety.bootstrap_admins(db) == 0


# ── 5. rate limit ───────────────────────────────────────────────────────
def test_rate_limit_counts_in_the_database_not_in_the_process(db):
    """저장소가 DB 라는 것이 이 기능의 요점이다 — 워커가 늘어도 한도가 그대로여야 한다."""
    for _ in range(3):
        rate_limit.hit(db, "user:1", "post.create")
    rows = db.query(models.RateLimitCounter).all()
    assert len(rows) == 1 and rows[0].count == 3

    # 다른 "워커"(별도 세션)에서 세도 같은 행이 이어진다.
    other = sessionmaker(bind=db.get_bind())()
    try:
        assert rate_limit.hit(other, "user:1", "post.create") == 4
    finally:
        other.close()


def test_rate_limit_blocks_past_the_limit(db):
    rule = rate_limit.rule_for("post.create")
    for _ in range(rule.limit):
        rate_limit.enforce(db, "user:1", "post.create")
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.enforce(db, "user:1", "post.create")
    assert exc.value.limit == rule.limit and exc.value.retry_after > 0


def test_new_accounts_get_a_stricter_limit(db):
    assert rate_limit.rule_for("post.create", is_new_account=True).limit \
        < rate_limit.rule_for("post.create").limit


def test_windows_roll_over(db):
    now = datetime.datetime.utcnow()
    rate_limit.hit(db, "user:1", "post.create", now=now)
    later = now + datetime.timedelta(seconds=rate_limit.rule_for("post.create").window_seconds + 1)
    rate_limit.hit(db, "user:1", "post.create", now=later)
    assert db.query(models.RateLimitCounter).count() == 2, "윈도우가 바뀌면 행이 갈린다"


def test_expired_counters_are_purged(db):
    past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    db.add(models.RateLimitCounter(key="user:1:post.create:0", count=5, expires_at=past))
    db.commit()
    assert rate_limit.purge_expired(db) == 1
    assert db.query(models.RateLimitCounter).count() == 0


def test_rate_limit_can_be_switched_off(db, monkeypatch):
    monkeypatch.setenv("COMMUNITY_RATE_LIMIT", "0")
    for _ in range(rate_limit.rule_for("post.create").limit + 5):
        rate_limit.enforce(db, "user:1", "post.create")


# ── 6. 알림 ─────────────────────────────────────────────────────────────
def test_quiet_notifications_are_not_counted_in_the_badge(db):
    notifications.notify(db, user_id=1, kind="friend_request", body="요청")
    notifications.notify(db, user_id=1, kind="blocked", body="차단됨", quiet=True)
    assert notifications.unread_count(db, 1) == 1
    assert len(notifications.list_for(db, 1)) == 2, "목록에는 둘 다 남는다"


def test_notifications_from_blocked_users_are_hidden(db):
    _profile(db, 1, "minsu"); _profile(db, 2, "younghee")
    notifications.notify(db, user_id=1, kind="friend_request", actor_id=2, body="요청")
    assert len(notifications.list_for(db, 1)) == 1
    safety.block(db, _user(db, 1), _user(db, 2))
    assert notifications.list_for(db, 1) == [] or all(
        n["actor"] is None for n in notifications.list_for(db, 1)
    )


def test_marking_read_updates_the_badge(db):
    for _ in range(3):
        notifications.notify(db, user_id=1, kind="friend_request", body="요청")
    assert notifications.unread_count(db, 1) == 3
    assert notifications.mark_read(db, 1) == 3
    assert notifications.unread_count(db, 1) == 0


def test_actor_without_a_profile_is_not_exposed_by_name(db):
    """프로필이 없는 사용자를 이메일·실명으로 대체하지 않는다."""
    notifications.notify(db, user_id=1, kind="friend_request", actor_id=2, body="요청")
    entry = notifications.list_for(db, 1)[0]
    assert entry["actor"] is None
    assert "younghee@example.com" not in str(entry)


# ── 7. 검수 도구 (COMMUNITY-4) ──────────────────────────────────────────
def _post(db, author_id=1, title="문제가 되는 글", body="본문"):
    import community_posts

    return community_posts.create_post(db, _user(db, author_id), kind="question",
                                       title=title, body=body)


def test_report_preview_shows_what_was_reported(db):
    _profile(db, 1, "minsu")
    post = _post(db)
    preview = safety.target_preview(db, "post", str(post.id))
    assert preview["found"] is True and preview["title"] == "문제가 되는 글"
    assert preview["author"]["handle"] == "minsu"
    # 이메일은 검수 화면에도 나가지 않는다.
    assert "minsu@example.com" not in str(preview)


def test_preview_of_a_missing_target_is_not_an_error(db):
    assert safety.target_preview(db, "post", "99999") == {"found": False}
    assert safety.target_preview(db, "workflow", "1") == {"found": False}


def test_content_moderation_hides_and_restores_with_a_trail(db):
    import community_posts

    _profile(db, 1, "minsu")
    post = _post(db)
    safety.moderate_content(db, _user(db, 3), target_type="post", target_id=str(post.id),
                            action="hide", reason="신고 처리")
    assert community_posts.list_posts(db, viewer_id=1) == []

    safety.moderate_content(db, _user(db, 3), target_type="post", target_id=str(post.id),
                            action="restore")
    assert [p.id for p in community_posts.list_posts(db, viewer_id=1)] == [post.id]

    actions = [a.action for a in db.query(models.ModerationAction).order_by(models.ModerationAction.id).all()]
    assert actions == ["hide", "restore"], "되돌리기도 이력에 남는다"


def test_moderating_an_unknown_target_is_refused(db):
    with pytest.raises(safety.SafetyError):
        safety.moderate_content(db, _user(db, 3), target_type="workflow", target_id="1", action="hide")
    with pytest.raises(safety.SafetyError):
        safety.moderate_content(db, _user(db, 3), target_type="post", target_id="1", action="지어낸조치")


def test_emergency_switch_stops_writes_and_records_who_did_it(db):
    """긴급 스위치는 조치 이력으로 표현된다 — 재배포 없이 끌 수 있고 누가 껐는지가 남는다."""
    assert safety.community_writes_enabled(db) is True

    safety.set_community_writes(db, _user(db, 3), enabled=False, reason="스팸 대응")
    assert safety.community_writes_enabled(db) is False
    action = db.query(models.ModerationAction).order_by(models.ModerationAction.id.desc()).first()
    assert action.target_type == "community" and action.admin_id == 3 and action.reason == "스팸 대응"

    safety.set_community_writes(db, _user(db, 3), enabled=True)
    assert safety.community_writes_enabled(db) is True


def test_action_history_carries_handles_not_emails(db):
    _profile(db, 3, "admin-one")
    post = _post(db)
    safety.moderate_content(db, _user(db, 3), target_type="post", target_id=str(post.id), action="hide")
    entry = safety.recent_actions(db)[0]
    assert entry["admin"]["handle"] == "admin-one" and entry["action"] == "hide"
    assert "admin@example.com" not in str(entry)
