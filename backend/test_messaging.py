"""친구 간 1:1 쪽지 (ADR-0022, 우선 백로그 24) 계약 테스트.

§4.13 검증 매트릭스의 층을 따른다 — 수신 범위·권한·전달·첨부·보존·보안·남용.

이 파일이 지키는 한 문장: **전송과 구독이 같은 판정을 쓴다.** 전송만 막고 구독을 열어 두면
차단한 상대의 메시지가 스트림으로 흘러 들어온다.
"""

from __future__ import annotations

import asyncio
import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import community_identity as identity
import community_safety as safety
import message_stream
import messaging
import models
from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="민수", email="a@t.com", role="user"),
        models.User(id=2, name="영희", email="b@t.com", role="user"),
        models.User(id=3, name="철수", email="c@t.com", role="user"),
        models.User(id=9, name="운영", email="m@t.com", role="moderator"),
    ])
    session.commit()
    for uid, handle in [(1, "minsu"), (2, "younghee"), (3, "chulsoo"), (9, "staff-one")]:
        identity.create_profile(session, session.query(models.User).get(uid), handle=handle)
    yield session
    session.close()


def _u(db, uid):
    return db.query(models.User).get(uid)


def _befriend(db, a, b):
    db.add_all([models.Friendship(user_id=a, friend_id=b), models.Friendship(user_id=b, friend_id=a)])
    db.commit()


def _unfriend(db, a, b):
    db.query(models.Friendship).filter(
        ((models.Friendship.user_id == a) & (models.Friendship.friend_id == b))
        | ((models.Friendship.user_id == b) & (models.Friendship.friend_id == a))
    ).delete(synchronize_session=False)
    db.commit()


def _chat(db, a=1, b=2):
    _befriend(db, a, b)
    return messaging.open_conversation(db, _u(db, a), _u(db, b))


# ── 1. 수신 범위 ────────────────────────────────────────────────────────
def test_strangers_cannot_message_each_other(db):
    assert messaging.can_message(db, 1, 2) is False
    with pytest.raises(messaging.MessagingForbidden):
        messaging.open_conversation(db, _u(db, 1), _u(db, 2))


def test_friends_can_message(db):
    _befriend(db, 1, 2)
    assert messaging.can_message(db, 1, 2) and messaging.can_message(db, 2, 1)


def test_blocking_closes_the_channel_in_both_directions(db):
    conversation = _chat(db)
    safety.block(db, _u(db, 2), _u(db, 1))
    assert messaging.can_message(db, 1, 2) is False
    assert messaging.can_message(db, 2, 1) is False
    with pytest.raises(messaging.MessagingForbidden):
        messaging.send_message(db, _u(db, 1), conversation, body="안녕")


def test_the_refusal_does_not_reveal_whether_it_was_a_block(db):
    """차단인지 비친구인지 구분해 알려주지 않는다 — 차단 사실이 API 로 새면 안 된다."""
    stranger = None
    try:
        messaging.require_can_message(db, 1, 3)
    except messaging.MessagingForbidden as exc:
        stranger = str(exc)

    _chat(db, 1, 2)
    safety.block(db, _u(db, 2), _u(db, 1))
    blocked = None
    try:
        messaging.require_can_message(db, 1, 2)
    except messaging.MessagingForbidden as exc:
        blocked = str(exc)
    assert stranger == blocked


def test_unfriending_keeps_the_history_but_stops_sending(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="첫 메시지")
    _unfriend(db, 1, 2)

    with pytest.raises(messaging.MessagingForbidden):
        messaging.send_message(db, _u(db, 1), conversation, body="두 번째")
    # 대화를 지우지 않는다 — 신고 조사 근거가 사라진다.
    assert len(messaging.list_messages(db, conversation, 1)) == 1
    assert messaging.list_conversations(db, 1)[0]["canSend"] is False


def test_you_cannot_message_yourself(db):
    assert messaging.can_message(db, 1, 1) is False


# ── 2. 대화 유일성과 권한 ───────────────────────────────────────────────
def test_a_pair_has_exactly_one_conversation_whoever_opens_it(db):
    _befriend(db, 1, 2)
    first = messaging.open_conversation(db, _u(db, 1), _u(db, 2))
    second = messaging.open_conversation(db, _u(db, 2), _u(db, 1))
    assert first.id == second.id
    assert db.query(models.Conversation).count() == 1
    assert first.user_a_id < first.user_b_id, "작은 id 가 항상 a 다"


def test_outsiders_cannot_read_or_send(db):
    conversation = _chat(db, 1, 2)
    with pytest.raises(messaging.MessagingError):
        messaging.list_messages(db, conversation, 3)
    with pytest.raises(messaging.MessagingError):
        messaging.send_message(db, _u(db, 3), conversation, body="끼어들기")


# ── 3. 전송·읽음 ────────────────────────────────────────────────────────
def test_sending_and_reading(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="안녕하세요")
    messaging.send_message(db, _u(db, 2), conversation, body="네 안녕하세요")

    rows = messaging.list_messages(db, conversation, 1)
    assert [m.body for m in rows] == ["안녕하세요", "네 안녕하세요"]
    assert messaging.public_message(rows[0], 1)["mine"] is True
    assert messaging.public_message(rows[1], 1)["mine"] is False


def test_unread_counts_only_the_other_side(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="1")
    messaging.send_message(db, _u(db, 1), conversation, body="2")
    assert messaging.unread_total(db, 2) == 2
    assert messaging.unread_total(db, 1) == 0, "보낸 사람에게는 이미 읽은 것이다"

    messaging.mark_read(db, conversation, 2)
    assert messaging.unread_total(db, 2) == 0


def test_empty_messages_are_refused(db):
    conversation = _chat(db)
    with pytest.raises(messaging.MessagingError):
        messaging.send_message(db, _u(db, 1), conversation, body="   ")


def test_body_is_capped(db):
    conversation = _chat(db)
    message = messaging.send_message(db, _u(db, 1), conversation, body="가" * 9000)
    assert len(message.body) == messaging.MAX_BODY


# ── 4. 삭제·숨김 (보존) ─────────────────────────────────────────────────
def test_deleting_only_affects_my_own_view(db):
    conversation = _chat(db)
    message = messaging.send_message(db, _u(db, 1), conversation, body="지울 메시지")
    messaging.delete_for_me(db, message, 1)

    assert messaging.list_messages(db, conversation, 1) == []
    assert len(messaging.list_messages(db, conversation, 2)) == 1, "상대 화면에는 남는다"
    # 신고 조사용 원본은 그대로다.
    assert db.query(models.Message).filter(models.Message.id == message.id).first().body == "지울 메시지"


def test_admin_removal_leaves_a_marker_and_a_trail(db):
    conversation = _chat(db)
    message = messaging.send_message(db, _u(db, 1), conversation, body="문제가 된 내용")
    messaging.remove_by_admin(db, _u(db, 9), message, reason="신고 처리")

    payload = messaging.public_message(message, 2)
    assert payload["removed"] is True and "문제가 된 내용" not in payload["body"]
    action = db.query(models.ModerationAction).one()
    assert action.target_type == "message" and action.admin_id == 9


def test_hiding_a_conversation_only_affects_my_list(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="안녕")
    messaging.hide_conversation(db, conversation, 1)
    assert messaging.list_conversations(db, 1) == []
    assert len(messaging.list_conversations(db, 2)) == 1


def test_a_hidden_conversation_returns_when_a_new_message_arrives(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="안녕")
    messaging.hide_conversation(db, conversation, 1)
    messaging.send_message(db, _u(db, 2), conversation, body="새 메시지")
    assert len(messaging.list_conversations(db, 1)) == 1


def test_blocked_conversations_leave_the_list(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="안녕")
    safety.block(db, _u(db, 1), _u(db, 2))
    assert messaging.list_conversations(db, 1) == []
    assert messaging.list_conversations(db, 2) == []


# ── 5. 첨부 (ADR-0018 과 같은 검증 경로) ────────────────────────────────
def test_attachments_go_through_the_shared_artifact_checks(db, tmp_path, monkeypatch):
    import artifacts

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    stored = tmp_path / "file.png"
    stored.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    record = models.UploadedFile(
        stored_name="file.png", artifact_id="art-1", original_name="그림.png",
        owner_user_id=1, project_id=None, purpose="node", size_bytes=stored.stat().st_size,
        content_type="image/png", sha256=artifacts.sha256_of(stored),
        created_at=datetime.datetime.utcnow(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=30),
    )
    db.add(record)
    db.commit()

    conversation = _chat(db)
    message = messaging.send_message(db, _u(db, 1), conversation, body="", artifact_ids=["art-1"])
    assert message.attachment_artifact_ids == ["art-1"]

    # 남의 파일은 붙일 수 없다 — ADR-0018 의 소유권 검사가 그대로 적용된다.
    with pytest.raises(messaging.MessagingError):
        messaging.send_message(db, _u(db, 2), conversation, body="", artifact_ids=["art-1"])


def test_attachment_errors_do_not_leak_paths(db):
    conversation = _chat(db)
    with pytest.raises(messaging.MessagingError) as exc:
        messaging.send_message(db, _u(db, 1), conversation, body="", artifact_ids=["없는id"])
    assert "uploads" not in str(exc.value) and "/" not in str(exc.value)


# ── 6. SSE 전달 ─────────────────────────────────────────────────────────
#
# 여기서는 `event_stream` 생성기를 직접 돌린다. FastAPI `TestClient` 로는 SSE 를 확인할 수 없다 —
# 스트리밍 응답에서 멈춘다(하네스의 한계이지 엔드포인트의 문제가 아니다). 엔드포인트 자체는
# 실제 uvicorn 서버에 curl 로 붙여 확인했다: `event: ready` → `id: N / event: message` 순서로
# 즉시 도착하고, 응답에 `X-Accel-Buffering: no` 가 실린다(nginx 버퍼링 방지).
def _factory(db):
    """스트림은 **자기 세션을 만들고 닫는다**(요청 하나가 아니라 오래 사는 연결이라서다).
    그래서 테스트도 공유 세션이 아니라 진짜 팩토리를 넘긴다 — 넘기면 스트림이 테스트 세션을 닫는다."""
    maker = sessionmaker(bind=db.get_bind())
    return lambda: maker()


def _collect(gen, count, timeout=6.0):
    async def run():
        out = []
        async for chunk in gen:
            out.append(chunk)
            # 메시지 이벤트는 `id: N` 줄이 먼저 온다(재개용 이벤트 id) — startswith 로는 못 센다.
            if len([c for c in out if "event: message" in c]) >= count:
                break
        return out
    return asyncio.run(asyncio.wait_for(run(), timeout))


def test_stream_delivers_messages_the_recipient_can_see(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="스트림 테스트")
    chunks = _collect(message_stream.event_stream(_factory(db), 2, 0), 1)
    body = "".join(chunks)
    assert "event: message" in body and "스트림 테스트" in body
    assert "event: ready" in body


def test_stream_resumes_from_last_event_id_without_duplicates(db):
    conversation = _chat(db)
    first = messaging.send_message(db, _u(db, 1), conversation, body="첫째")
    messaging.send_message(db, _u(db, 1), conversation, body="둘째")

    chunks = "".join(_collect(message_stream.event_stream(_factory(db), 2, first.id), 1))
    assert "둘째" in chunks and "첫째" not in chunks, "이미 받은 것을 다시 보내지 않는다"


def test_stream_applies_the_same_receive_scope_as_sending(db):
    """**전송과 구독이 같은 판정을 쓴다.** 이것이 이 파일의 핵심이다."""
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="차단 전 메시지")
    safety.block(db, _u(db, 2), _u(db, 1))

    rows = message_stream._fetch_new(_factory(db), 2, 0)
    assert rows == [], "차단한 상대의 메시지는 스트림으로도 오지 않는다"


def test_stream_skips_messages_i_deleted_for_myself(db):
    conversation = _chat(db)
    message = messaging.send_message(db, _u(db, 1), conversation, body="지운 것")
    messaging.delete_for_me(db, message, 2)
    assert message_stream._fetch_new(_factory(db), 2, 0) == []


def test_stream_never_echoes_my_own_messages(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="내가 보낸 것")
    assert message_stream._fetch_new(_factory(db), 1, 0) == []


def test_concurrent_streams_are_capped():
    assert message_stream.MAX_STREAMS_PER_USER >= 2
    assert message_stream.stream_count(12345) == 0


def test_publish_wakes_waiters_without_guaranteeing_delivery():
    """브로커는 **지연 최적화**이고 전달을 보장하는 것은 DB 다 — 워커가 늘어도 유실되지 않는다."""
    async def run():
        event = asyncio.Event()
        message_stream._waiters[777].add(event)
        try:
            message_stream.publish([777])
            return event.is_set()
        finally:
            message_stream._waiters.pop(777, None)
    assert asyncio.run(run()) is True


# ── 7. 보안 ─────────────────────────────────────────────────────────────
def test_message_bodies_never_appear_in_error_text(db):
    conversation = _chat(db)
    _unfriend(db, 1, 2)
    with pytest.raises(messaging.MessagingError) as exc:
        messaging.send_message(db, _u(db, 1), conversation, body="비밀 이야기")
    assert "비밀 이야기" not in str(exc.value)


def test_conversation_list_carries_handles_not_emails(db):
    conversation = _chat(db)
    messaging.send_message(db, _u(db, 1), conversation, body="안녕")
    payload = json.dumps(messaging.list_conversations(db, 1), ensure_ascii=False)
    assert "b@t.com" not in payload and "younghee" in payload
