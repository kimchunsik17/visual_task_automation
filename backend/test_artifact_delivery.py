"""Artifact 기반 Discord·Email 파일 전송 (ADR-0018, 우선 백로그 20) 계약 테스트.

§4.10 검증 매트릭스의 층을 그대로 따른다 — 단위(소유·TTL·MIME·크기·파일명·경로), Discord 통합,
SMTP 통합, Gmail 통합, 편집기 E2E(생성 → 발송), 보안 회귀, 실행 경로 회귀.

핵심 규칙 하나만 기억하면 된다: **외부 네트워크 호출 전에 전부 검증하고, 하나라도 실패하면
아무것도 보내지 않는다.** 아래 테스트 대부분이 그 규칙을 다른 각도에서 확인한다.
"""

from __future__ import annotations

import base64
import datetime
import email
import email.policy
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import artifacts
import delivery_attachments as attach
import delivery_runtime
import models
import node_definition
from artifacts import ArtifactError
from database import Base
from graph import compile_workflow, run_workflow

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 40
)
PDF_BYTES = b"%PDF-1.4\n" + b"x" * 200


# ── fixture ─────────────────────────────────────────────────────────────
@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(root))
    return root


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="Owner", email="owner@example.com"),
        models.User(id=2, name="Other", email="other@example.com"),
        models.Project(id=10, user_id=1, title="flow", graph_data={}),
        models.Project(id=11, user_id=1, title="other flow", graph_data={}),
    ])
    session.commit()
    yield session
    session.close()


def _store(uploads, db, *, name="poster.png", content=PNG_BYTES, owner=1, project=10,
           mime="image/png", expires_in_days=30, purpose="node"):
    """디스크 파일 + 등록 행을 함께 만든다. 실제 업로드 경로와 같은 모양이어야 한다."""
    import uuid

    stored = uploads / f"{uuid.uuid4().hex}{Path(name).suffix}"
    stored.write_bytes(content)
    now = datetime.datetime.utcnow()
    record = models.UploadedFile(
        stored_name=stored.name,
        artifact_id=uuid.uuid4().hex,
        original_name=name,
        owner_user_id=owner,
        project_id=project,
        purpose=purpose,
        size_bytes=len(content),
        content_type=mime,
        sha256=artifacts.sha256_of(stored),
        created_at=now,
        expires_at=(now + datetime.timedelta(days=expires_in_days)) if expires_in_days is not None else None,
    )
    db.add(record)
    db.commit()
    return record


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Recorder:
    """requests.post 대역. 마지막 호출의 인자를 남긴다."""

    def __init__(self, response=None):
        self.response = response or _FakeResponse(200, {"id": "m1", "channel_id": "c9"})
        self.calls = []

    def post(self, url, **kwargs):
        # 파일 내용은 호출 시점에 읽어 둔다 — 나중에는 handle 이 닫혀 있어야 정상이다.
        files = kwargs.get("files") or {}
        snapshot = {key: (value[0], value[1].read(), value[2] if len(value) > 2 else None)
                    for key, value in files.items()}
        self.calls.append({"url": url, "kwargs": kwargs, "files": snapshot,
                           "handles": [value[1] for value in files.values()]})
        return self.response


# ── 1. 단위: 소유·TTL·MIME·크기·파일명·경로 ─────────────────────────────
def test_resolve_checks_owner_and_project_before_opening(uploads, db):
    record = _store(uploads, db)
    resolved = artifacts.resolve(db, record.artifact_id, owner_user_id=1, project_id=10)
    assert resolved.ref.kind == "image" and resolved.ref.mime_type == "image/png"
    assert resolved.path.parent == artifacts.upload_root()

    with pytest.raises(ArtifactError) as other_user:
        artifacts.resolve(db, record.artifact_id, owner_user_id=2, project_id=10)
    assert other_user.value.error.code == "ARTIFACT_FORBIDDEN"

    with pytest.raises(ArtifactError) as other_project:
        artifacts.resolve(db, record.artifact_id, owner_user_id=1, project_id=11)
    assert other_project.value.error.code == "ARTIFACT_FORBIDDEN"


def test_expired_and_missing_and_forged_ids_are_rejected(uploads, db):
    expired = _store(uploads, db, expires_in_days=-1)
    with pytest.raises(ArtifactError) as exc:
        artifacts.resolve(db, expired.artifact_id, owner_user_id=1, project_id=10)
    assert exc.value.error.code == "ARTIFACT_EXPIRED"

    with pytest.raises(ArtifactError) as forged:
        artifacts.resolve(db, "deadbeef" * 4, owner_user_id=1, project_id=10)
    assert forged.value.error.code == "ARTIFACT_NOT_FOUND"

    deleted = _store(uploads, db)
    (artifacts.upload_root() / deleted.stored_name).unlink()
    with pytest.raises(ArtifactError) as gone:
        artifacts.resolve(db, deleted.artifact_id, owner_user_id=1, project_id=10)
    assert gone.value.error.code == "ARTIFACT_NOT_FOUND"


def test_content_change_after_registration_is_rejected(uploads, db):
    """등록 시점 hash 와 전송 직전 hash 를 비교한다 — 같은 이름으로 내용만 바꿔치기하면 막힌다."""
    record = _store(uploads, db)
    (artifacts.upload_root() / record.stored_name).write_bytes(PNG_BYTES + b"tampered")
    with pytest.raises(ArtifactError) as exc:
        artifacts.resolve(db, record.artifact_id, owner_user_id=1, project_id=10)
    assert exc.value.error.code == "ARTIFACT_NOT_FOUND"


def _symlinks_available() -> bool:
    """Windows 는 심볼릭 링크 생성에 관리자 권한이나 개발자 모드가 필요하다. 없으면 이 검사는
    수행할 수 없다 — 실패로 남겨 두면 '원래 빨간 테스트' 가 되어 진짜 회귀를 가린다.
    리눅스(운영·CI)에서는 항상 돌아간다."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        target = base / "t"
        target.write_text("x", encoding="utf-8")
        try:
            (base / "l").symlink_to(target)
            return True
        except (OSError, NotImplementedError):
            return False


@pytest.mark.skipif(not _symlinks_available(),
                    reason="심볼릭 링크를 만들 수 없는 환경(권한 없는 Windows)")
def test_symlink_and_paths_outside_the_root_are_never_opened(uploads, db, tmp_path):
    secret = tmp_path / "secret.png"
    secret.write_bytes(PNG_BYTES)
    link = uploads / "link.png"
    link.symlink_to(secret)

    record = _store(uploads, db)
    record.stored_name = "link.png"
    record.sha256 = None
    record.size_bytes = secret.stat().st_size
    db.commit()

    with pytest.raises(ArtifactError) as exc:
        artifacts.resolve(db, record.artifact_id, owner_user_id=1, project_id=10)
    assert exc.value.error.code == "ARTIFACT_FORBIDDEN"

    # `..` 를 담은 저장 이름도 루트 밖으로 나가지 못한다.
    record.stored_name = "../secret.png"
    db.commit()
    with pytest.raises(ArtifactError) as escape:
        artifacts.resolve(db, record.artifact_id, owner_user_id=1, project_id=10)
    assert escape.value.error.code in {"ARTIFACT_FORBIDDEN", "ARTIFACT_NOT_FOUND"}


@pytest.mark.parametrize("raw, expected", [
    ("../../etc/passwd", "passwd"),
    ('report"\r\nBcc: attacker@example.com.pdf', "reportBcc: attacker@example.com.pdf"),
    ("보고서 최종.docx", "보고서 최종.docx"),
    ("", "attachment"),
    ("   ...  ", "attachment"),
])
def test_filenames_are_normalized_against_path_and_header_injection(raw, expected):
    assert artifacts.safe_filename(raw) == expected


def test_declared_extension_cannot_fake_the_real_type(uploads, db):
    """확장자만 `.png` 인 파일은 image 로 통과하지 않는다 — 채널이 인라인으로 렌더하는 형식이다."""
    fake = _store(uploads, db, name="fake.png", content=b"<html>not an image</html>", mime="image/png")
    resolved = artifacts.resolve(db, fake.artifact_id, owner_user_id=1, project_id=10)
    assert resolved.ref.mime_type == "application/octet-stream" and resolved.ref.kind != "image"

    # 반대로 signature 가 다른 형식을 가리키면 그쪽을 믿는다.
    mislabeled = _store(uploads, db, name="doc.png", content=PDF_BYTES, mime="image/png")
    assert artifacts.resolve(db, mislabeled.artifact_id, owner_user_id=1,
                             project_id=10).ref.mime_type == "application/pdf"


def test_policy_rejects_too_many_too_big_and_unsupported_files(uploads, db, monkeypatch):
    records = [_store(uploads, db, name=f"f{i}.png") for i in range(3)]
    tight = attach.AttachmentPolicy(provider="discord", max_files=2, max_bytes_per_file=10 * 1024,
                                    max_total_bytes=10 * 1024, timeout_seconds=5.0)
    with pytest.raises(ArtifactError) as too_many:
        attach.validate_attachments(db, [r.artifact_id for r in records], owner_user_id=1,
                                    project_id=10, policy=tight)
    assert too_many.value.error.code == "ARTIFACT_TOO_LARGE"

    big = _store(uploads, db, name="big.png", content=PNG_BYTES + b"x" * 20_000)
    with pytest.raises(ArtifactError) as too_big:
        attach.validate_attachments(db, [big.artifact_id], owner_user_id=1, project_id=10, policy=tight)
    assert too_big.value.error.safe_details["limitBytes"] == 10 * 1024

    pdf = _store(uploads, db, name="doc.pdf", content=PDF_BYTES, mime="application/pdf")
    images_only = attach.AttachmentPolicy(provider="discord", max_files=5, max_bytes_per_file=10 * 1024 * 1024,
                                          max_total_bytes=10 * 1024 * 1024, timeout_seconds=5.0,
                                          allowed_mime_prefixes=("image/",))
    with pytest.raises(ArtifactError) as unsupported:
        attach.validate_attachments(db, [pdf.artifact_id], owner_user_id=1, project_id=10, policy=images_only)
    assert unsupported.value.error.code == "ARTIFACT_UNSUPPORTED_TYPE"


def test_duplicate_ids_are_attached_once(uploads, db):
    record = _store(uploads, db)
    resolved = attach.validate_attachments(
        db, [record.artifact_id, record.artifact_id], owner_user_id=1, project_id=10,
        policy=attach.policy_for("discord"),
    )
    assert len(resolved) == 1


def test_open_attachments_closes_every_handle_even_on_failure(uploads, db):
    records = [_store(uploads, db, name=f"f{i}.png") for i in range(2)]
    resolved = attach.validate_attachments(db, [r.artifact_id for r in records], owner_user_id=1,
                                           project_id=10, policy=attach.policy_for("discord"))
    captured = []
    with pytest.raises(RuntimeError):
        with attach.open_attachments(resolved) as opened:
            captured = [handle for _, handle, _ in opened]
            raise RuntimeError("전송 중 실패")
    assert captured and all(handle.closed for handle in captured)


# ── 2. Discord 통합 ─────────────────────────────────────────────────────
def test_discord_sends_body_and_multiple_attachments_together(uploads, db):
    """예전 경로는 첨부가 생기면 content 를 빈 값으로 만들어 캡션을 지웠다 — 그 회귀를 막는다."""
    first = _store(uploads, db, name="poster.png")
    second = _store(uploads, db, name="doc.pdf", content=PDF_BYTES, mime="application/pdf")
    recorder = _Recorder()

    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="신제품 공지입니다",
        db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "select", "artifactIds": [first.artifact_id, second.artifact_id]},
        node_id="dc", session=recorder,
    )

    assert result.ok
    call = recorder.calls[0]
    payload = json.loads(call["kwargs"]["data"]["payload_json"])
    assert payload["content"] == "신제품 공지입니다"
    assert set(call["files"]) == {"files[0]", "files[1]"}
    assert call["files"]["files[0]"][1] == PNG_BYTES
    assert result.data["provider"] == "discord" and result.data["messageId"] == "m1"
    assert [a["filename"] for a in result.data["attachments"]] == ["poster.png", "doc.pdf"]
    # 전송이 끝나면 descriptor 가 남지 않는다.
    assert all(handle.closed for handle in call["handles"])


def test_discord_webhook_and_bot_api_use_the_same_adapter(uploads, db):
    record = _store(uploads, db)
    for token, expected_url, has_auth in [
        ("https://discord.com/api/webhooks/1/abc", "https://discord.com/api/webhooks/1/abc", False),
        ("bot-token", f"{delivery_runtime.DISCORD_API_BASE}/channels/c9/messages", True),
    ]:
        recorder = _Recorder(_FakeResponse(204, None))
        result = delivery_runtime.send_discord(
            token=token, channel_id="c9", body="본문", db=db, owner_user_id=1, project_id=10,
            attachments_config={"mode": "select", "artifactIds": [record.artifact_id]},
            session=recorder,
        )
        assert result.ok, result.error
        assert recorder.calls[0]["url"] == expected_url
        assert ("Authorization" in recorder.calls[0]["kwargs"]["headers"]) is has_auth
        # multipart 에서는 Content-Type 을 우리가 정하지 않는다(requests 가 boundary 를 만든다).
        assert "Content-Type" not in recorder.calls[0]["kwargs"]["headers"]


def test_discord_without_attachments_still_sends_json_body(db):
    recorder = _Recorder()
    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="첨부 없음", db=db, owner_user_id=1,
        project_id=10, attachments_config={"mode": "none"}, session=recorder,
    )
    assert result.ok and recorder.calls[0]["kwargs"]["json"] == {"content": "첨부 없음"}


def test_discord_rate_limit_and_missing_credentials_are_typed(uploads, db):
    limited = _Recorder(_FakeResponse(429, None, {"Retry-After": "2"}, "rate limited"))
    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="본문", db=db, owner_user_id=1,
        project_id=10, attachments_config={"mode": "none"}, session=limited,
    )
    assert result.error.code == "DELIVERY_RATE_LIMITED" and result.error.retry_after_ms == 2000
    assert str(result).startswith("본문")

    missing = delivery_runtime.send_discord(token="", channel_id="", body="본문", db=db)
    assert missing.error.code == "CREDENTIAL_MISSING"
    assert "설정되지 않아" in str(missing)


def test_one_bad_attachment_stops_the_whole_send(uploads, db):
    good = _store(uploads, db, name="ok.png")
    expired = _store(uploads, db, name="old.png", expires_in_days=-1)
    recorder = _Recorder()

    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="본문", db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "select", "artifactIds": [good.artifact_id, expired.artifact_id]},
        session=recorder,
    )
    assert result.error.code == "ARTIFACT_EXPIRED"
    assert result.error.effect_state == "not_started"
    assert recorder.calls == [], "검증 실패 시 외부 호출이 나가면 안 된다"


# ── 3. SMTP 통합 ────────────────────────────────────────────────────────
class _FakeSMTP:
    sent = []

    def __init__(self, server, port, timeout=None):
        self.server, self.port, self.timeout = server, port, timeout
        self.logged_in = None

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        _FakeSMTP.sent.append(message)

    def quit(self):
        self.quit_called = True


def _send_mail(db, **overrides):
    _FakeSMTP.sent = []
    params = dict(
        smtp_server="smtp.example.com", smtp_port=587,
        smtp_user="sender@example.com", smtp_password="secret",
        to_email="receiver@example.com", subject="월간 보고서",
        body="본문입니다", db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "none"}, client_factory=_FakeSMTP,
    )
    params.update(overrides)
    return delivery_runtime.send_smtp(**params)


def test_smtp_builds_multipart_with_unicode_body_and_filename(uploads, db):
    record = _store(uploads, db, name="보고서 최종.pdf", content=PDF_BYTES, mime="application/pdf")
    result = _send_mail(db, attachments_config={"mode": "select", "artifactIds": [record.artifact_id]})

    assert result.ok, result.error
    message = _FakeSMTP.sent[0]
    assert message.is_multipart()
    body_part = message.get_body(preferencelist=("plain",))
    assert body_part.get_content().strip() == "본문입니다"
    attached = [part for part in message.iter_attachments()]
    assert len(attached) == 1
    assert attached[0].get_filename() == "보고서 최종.pdf"
    assert attached[0].get_content_type() == "application/pdf"
    assert attached[0].get_payload(decode=True) == PDF_BYTES
    assert result.data["attachments"][0]["sizeBytes"] == len(PDF_BYTES)


def test_smtp_header_injection_in_recipient_and_subject_is_neutralized(db):
    result = _send_mail(
        db,
        to_email="ok@example.com\r\nBcc: attacker@example.com",
        subject="제목\r\nX-Evil: 1",
    )
    assert result.ok
    message = _FakeSMTP.sent[0]
    assert message["Bcc"] is None and message["X-Evil"] is None
    assert "\n" not in message["Subject"] and "\r" not in message["Subject"]


def test_smtp_auth_and_missing_credentials_are_typed_and_private(db):
    import smtplib

    class _AuthFail(_FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    result = _send_mail(db, client_factory=_AuthFail)
    assert result.error.code == "DELIVERY_AUTH_FAILED" and result.error.effect_state == "not_started"
    assert "sender@example.com" not in json.dumps(result.error.to_dict())
    assert str(result).startswith("본문입니다") and "[⚠️ 이메일 발송 실패:" in str(result)

    missing = _send_mail(db, smtp_password="")
    assert missing.error.code == "CREDENTIAL_MISSING"

    no_recipient = _send_mail(db, to_email="   ")
    assert no_recipient.error.code == "VALIDATION_REQUIRED" and no_recipient.error.field == "toEmail"


def test_smtp_timeout_is_unknown_effect_and_not_auto_retried(db):
    class _Timeout(_FakeSMTP):
        def send_message(self, message):
            raise TimeoutError("timed out")

    result = _send_mail(db, client_factory=_Timeout)
    assert result.error.code == "DELIVERY_TIMEOUT"
    assert result.error.effect_state == "unknown" and result.error.safe_to_retry is False


# ── 4. Gmail 통합 ───────────────────────────────────────────────────────
class _GmailSession:
    def __init__(self, responses):
        self.responses, self.posts = responses, []

    def get(self, url, **kwargs):
        return _FakeResponse(200, self.responses["get"])

    def post(self, url, **kwargs):
        self.posts.append({"url": url, "json": kwargs.get("json")})
        return _FakeResponse(200, self.responses["post"])


def _decode_raw(raw):
    # 기본 정책은 구식 Message 를 돌려준다 — get_content()/iter_attachments() 를 쓰려면 default 정책이다.
    return email.message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")),
                                    policy=email.policy.default)


def _gmail_attachment(uploads, db, name="첨부.pdf"):
    record = _store(uploads, db, name=name, content=PDF_BYTES, mime="application/pdf")
    return attach.validate_attachments(db, [record.artifact_id], owner_user_id=1, project_id=10,
                                       policy=attach.policy_for("gmail"))


def test_gmail_send_reply_draft_all_carry_attachments(uploads, db):
    from connectors.services import gmail

    definition = node_definition.get_definition("gmailNode")
    resolved = _gmail_attachment(uploads, db)

    with attach.open_attachments(resolved) as opened:
        session = _GmailSession({"post": {"id": "m1", "threadId": "t9"}, "get": {}})
        sent = gmail.run_action(definition, "send_email", "tok", {
            "to": "a@b.c", "subject": "제목", "body": "본문", "__attachments__": opened,
        }, session=session)
    assert sent == {"message_id": "m1", "thread_id": "t9", "to": "a@b.c"}
    message = _decode_raw(session.posts[0]["json"]["raw"])
    assert message.is_multipart()
    assert [p.get_filename() for p in message.iter_attachments()] == ["첨부.pdf"]

    # 답장은 thread 를 유지하면서 첨부를 더한다.
    with attach.open_attachments(resolved) as opened:
        session = _GmailSession({
            "post": {"id": "m2", "threadId": "t9"},
            "get": {"threadId": "t9", "payload": {"headers": [
                {"name": "From", "value": "orig@example.com"},
                {"name": "Subject", "value": "문의"},
                {"name": "Message-ID", "value": "<abc@mail>"},
            ]}},
        })
        replied = gmail.run_action(definition, "reply_email", "tok", {
            "messageId": "orig1", "body": "답장 본문", "__attachments__": opened,
        }, session=session)
    assert replied["thread_id"] == "t9"
    assert session.posts[0]["json"]["threadId"] == "t9"
    reply = _decode_raw(session.posts[0]["json"]["raw"])
    assert reply["In-Reply-To"] == "<abc@mail>" and reply["References"] == "<abc@mail>"
    assert reply["Subject"] == "Re: 문의"
    assert [p.get_filename() for p in reply.iter_attachments()] == ["첨부.pdf"]

    with attach.open_attachments(resolved) as opened:
        session = _GmailSession({"post": {"id": "d1"}, "get": {}})
        draft = gmail.run_action(definition, "create_draft", "tok", {
            "to": "a@b.c", "subject": "임시", "body": "초안", "__attachments__": opened,
        }, session=session)
    assert draft["draft_id"] == "d1"
    drafted = _decode_raw(session.posts[0]["json"]["message"]["raw"])
    assert [p.get_filename() for p in drafted.iter_attachments()] == ["첨부.pdf"]


def test_gmail_without_attachments_keeps_a_plain_body(db):
    from connectors.services import gmail

    definition = node_definition.get_definition("gmailNode")
    session = _GmailSession({"post": {"id": "m1", "threadId": "t1"}, "get": {}})
    gmail.run_action(definition, "send_email", "tok", {"to": "a@b.c", "subject": "s", "body": "본문"},
                     session=session)
    message = _decode_raw(session.posts[0]["json"]["raw"])
    assert message.get_content().strip() == "본문"


# ── 5. 노드 설정과 legacy 이전 ──────────────────────────────────────────
@pytest.mark.parametrize("raw, expected", [
    (None, {"mode": "auto", "artifactIds": []}),
    ("none", {"mode": "none", "artifactIds": []}),
    (["a", "b"], {"mode": "select", "artifactIds": ["a", "b"]}),
    ({"mode": "select", "artifactIds": ["x"]}, {"mode": "select", "artifactIds": ["x"]}),
    ({"artifactIds": []}, {"mode": "auto", "artifactIds": []}),
    (12345, {"mode": "auto", "artifactIds": []}),
])
def test_attachment_config_shapes_normalize_to_one_form(raw, expected):
    assert attach.normalize_config(raw) == expected


def test_auto_mode_prefers_upstream_artifacts_over_legacy_paths(uploads, db):
    record = _store(uploads, db)
    ids = attach.collect_artifact_ids(
        {"mode": "auto"}, upstream_artifact_ids=[record.artifact_id],
        upstream_text="uploads/whatever.png", db=db, owner_user_id=1,
    )
    assert ids == [record.artifact_id]


def test_legacy_upload_paths_convert_only_when_registered_and_owned(uploads, db):
    mine = _store(uploads, db)
    theirs = _store(uploads, db, owner=2)

    converted = attach.collect_artifact_ids(
        {"mode": "auto"}, upstream_text=f"결과: uploads/{mine.stored_name}", db=db, owner_user_id=1)
    assert converted == [mine.artifact_id]

    # 남의 파일도, 등록되지 않은 임의 경로도 변환하지 않는다.
    assert attach.collect_artifact_ids(
        {"mode": "auto"}, upstream_text=f"uploads/{theirs.stored_name}", db=db, owner_user_id=1) == []
    assert attach.collect_artifact_ids(
        {"mode": "auto"}, upstream_text="uploads/../../etc/passwd", db=db, owner_user_id=1) == []
    assert attach.unresolved_legacy_paths(db, "uploads/gone.png", owner_user_id=1) == ["uploads/gone.png"]


def test_legacy_binding_can_be_switched_off(uploads, db, monkeypatch):
    record = _store(uploads, db)
    monkeypatch.setenv("ARTIFACT_DELIVERY_LEGACY_PATHS", "0")
    assert attach.collect_artifact_ids(
        {"mode": "auto"}, upstream_text=f"uploads/{record.stored_name}", db=db, owner_user_id=1) == []


def test_connector_flags_turn_attachments_off_without_breaking_text_delivery(uploads, db, monkeypatch):
    record = _store(uploads, db)
    monkeypatch.setenv("ARTIFACT_DELIVERY_DISCORD", "0")
    recorder = _Recorder()
    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="본문", db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "select", "artifactIds": [record.artifact_id]}, session=recorder,
    )
    assert result.ok and result.data["attachments"] == []
    assert recorder.calls[0]["kwargs"]["json"] == {"content": "본문"}

    monkeypatch.setenv("ARTIFACT_DELIVERY_V1", "0")
    assert attach.connector_enabled("smtp") is False


# ── 6. 편집기 E2E: 생성 → 발송 ──────────────────────────────────────────
def _graph(nodes, edges):
    return nodes, edges


def test_generated_code_wires_the_attachment_port(uploads):
    """첨부 포트로 들어온 간선이 발송 노드의 첨부 원본이 된다 — 본문 포트와 분리돼 있다."""
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "img", "type": "imageGenerationNode", "data": {"prompt": "포스터"}},
        {"id": "cap", "type": "valueNode", "data": {"value": "새 포스터입니다"}},
        {"id": "dc", "type": "discordNode", "data": {"botToken": "t", "channelId": "c"}},
    ]
    edges = [
        {"source": "s1", "target": "img"},
        {"source": "img", "target": "cap"},
        {"source": "cap", "target": "dc"},          # 본문 포트
        {"source": "img", "target": "dc", "targetHandle": "attachments"},  # 첨부 포트
    ]
    source = compile_workflow(nodes, edges)
    assert "upstream_artifact_ids=_collect_artifacts('img')" in source
    # 첨부 간선이 실행 순서를 바꾸지 않는다 — discordNode 는 한 번만 생성된다.
    assert source.count("# --- Discord Node (dc) ---") == 1


def test_attachment_only_edge_still_runs_the_delivery_node():
    """본문 포트를 빼먹고 첨부 포트에만 이었을 때 발송 노드가 통째로 실행되지 않으면 안 된다 —
    편집기에서 실제로 하기 쉬운 실수이고, 그 결과가 '아무 일도 일어나지 않음' 이면 원인을 찾을 수 없다."""
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "p1", "type": "posterGeneratorNode", "data": {}},
        {"id": "dc", "type": "discordNode", "data": {"botToken": "t", "channelId": "c"}},
    ]
    edges = [
        {"source": "s1", "target": "p1"},
        {"source": "p1", "target": "dc", "targetHandle": "attachments"},
    ]
    source = compile_workflow(nodes, edges)
    assert source.count("# --- Discord Node (dc) ---") == 1


def test_poster_and_file_nodes_register_their_output_as_artifacts():
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "p1", "type": "posterGeneratorNode", "data": {"outputFormat": "pdf"}},
    ]
    source = compile_workflow(nodes, [{"source": "s1", "target": "p1"}])
    assert "register_generated_file" in source and "_record_artifacts('p1'" in source


def test_uploaded_document_flows_to_smtp_email_end_to_end(uploads, db, monkeypatch):
    """업로드 문서 → 이메일 첨부. 실행 경로(run_workflow)를 그대로 지난다."""
    record = _store(uploads, db, name="계약서.pdf", content=PDF_BYTES, mime="application/pdf")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(delivery_runtime.smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.sent = []

    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "계약서를 보냅니다"}},
        {"id": "em", "type": "emailNode", "data": {
            "toEmail": "receiver@example.com", "subject": "계약서 송부",
            "attachments": {"mode": "select", "artifactIds": [record.artifact_id]},
        }},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "em"}]
    result_text, _, logs = run_workflow(nodes, edges, db=db, project_id=10, default_input="")

    step = next(entry for entry in logs if entry["node_id"] == "em")
    assert step["status"] == "success", step
    assert step["artifacts"][0]["artifactId"] == record.artifact_id
    message = _FakeSMTP.sent[0]
    assert [p.get_filename() for p in message.iter_attachments()] == ["계약서.pdf"]
    assert "계약서를 보냅니다" in result_text


def test_discord_end_to_end_keeps_caption_and_reports_attachments(uploads, db, monkeypatch):
    record = _store(uploads, db, name="poster.png")
    recorder = _Recorder()
    import requests

    monkeypatch.setattr(requests, "post", lambda url, **kwargs: recorder.post(url, **kwargs))

    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "새 포스터입니다"}},
        {"id": "dc", "type": "discordNode", "data": {
            "botToken": "bot-token", "channelId": "c9",
            "attachments": {"mode": "select", "artifactIds": [record.artifact_id]},
        }},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "dc"}]
    result_text, _, logs = run_workflow(nodes, edges, db=db, project_id=10, default_input="")

    payload = json.loads(recorder.calls[0]["kwargs"]["data"]["payload_json"])
    assert payload["content"] == "새 포스터입니다"
    assert result_text.startswith("새 포스터입니다")
    step = next(entry for entry in logs if entry["node_id"] == "dc")
    assert step["status"] == "success" and step["artifacts"][0]["filename"] == "poster.png"


# ── 7. 보안 회귀 ────────────────────────────────────────────────────────
def test_no_server_path_or_stored_name_leaks_into_results_or_logs(uploads, db, monkeypatch):
    record = _store(uploads, db, name="poster.png")
    recorder = _Recorder()
    import requests

    monkeypatch.setattr(requests, "post", lambda url, **kwargs: recorder.post(url, **kwargs))

    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "본문"}},
        {"id": "dc", "type": "discordNode", "data": {
            "botToken": "bot-token", "channelId": "c9",
            "attachments": {"mode": "select", "artifactIds": [record.artifact_id]},
        }},
    ]
    edges = [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "dc"}]
    result_text, _, logs = run_workflow(nodes, edges, db=db, project_id=10, default_input="")

    haystack = result_text + json.dumps(logs, ensure_ascii=False, default=str)
    assert record.stored_name not in haystack
    assert str(artifacts.upload_root()) not in haystack
    assert not re.search(r"(^|[^\w])/(home|etc|var|tmp)/", haystack)


def test_other_users_artifact_is_refused_before_any_network_call(uploads, db):
    theirs = _store(uploads, db, owner=2, project=None)
    recorder = _Recorder()
    result = delivery_runtime.send_discord(
        token="bot-token", channel_id="c9", body="본문", db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "select", "artifactIds": [theirs.artifact_id]}, session=recorder,
    )
    assert result.error.code == "ARTIFACT_FORBIDDEN" and recorder.calls == []


def test_public_ref_never_carries_the_stored_name(uploads, db):
    record = _store(uploads, db)
    ref = artifacts.lookup(db, record.artifact_id)
    payload = ref.to_public_dict()
    assert record.stored_name not in json.dumps(payload)
    assert set(payload) == {"artifactId", "kind", "filename", "mimeType", "sizeBytes",
                            "createdAt", "expiresAt", "source"}


# ── 8. 실행 경로 회귀 ───────────────────────────────────────────────────
def test_image_artifact_ids_resolve_through_the_same_service(uploads, db):
    """이미지 생성은 자기 버전 기록(ImageArtifact)의 id 를 내보낸다 — 같은 파일로 이어져야 한다."""
    record = _store(uploads, db, name="ai.png", purpose="generated-image")
    image = models.ImageArtifact(
        artifact_id="img-artifact-1", owner_user_id=1, project_id=10,
        stored_name=record.stored_name, revision_index=0, action="generate", provider="openai",
    )
    db.add(image)
    db.commit()

    resolved = artifacts.resolve(db, "img-artifact-1", owner_user_id=1, project_id=10)
    assert resolved.ref.source == "image" and resolved.filename == "ai.png"


def test_register_generated_file_is_idempotent_for_a_fixed_output_path(uploads, db):
    path = artifacts.upload_root() / "poster.png"
    path.write_bytes(PNG_BYTES)
    first = artifacts.register_generated_file(db, path=str(path), owner_user_id=1, project_id=10,
                                              purpose="generated-poster")
    path.write_bytes(PNG_BYTES + b"second render")
    second = artifacts.register_generated_file(db, path=str(path), owner_user_id=1, project_id=10,
                                               purpose="generated-poster")
    assert first.artifact_id == second.artifact_id
    # 다시 렌더한 내용으로 hash 가 갱신됐으므로 전송 직전 검증이 자기 파일을 거부하지 않는다.
    resolved = artifacts.resolve(db, second.artifact_id, owner_user_id=1, project_id=10)
    assert resolved.ref.size_bytes == len(PNG_BYTES + b"second render")


def test_downloaded_files_become_attachable_artifacts(uploads, db):
    """Drive 내려받기 → 첨부. §4.7 에서 "전송 계층 바이너리 지원 이후"로 미뤄뒀던 고리다.

    받은 파일이 artifact 로 등록되므로 경로 문자열 없이 발송 노드의 첨부가 된다.
    """
    import drive_downloads

    make = drive_downloads.sink_factory(db, owner_user_id=1, project_id=10)
    sink = make(filename="계약서.pdf", mime_type="application/pdf")
    with sink as stream:
        stream.write(PDF_BYTES)

    assert sink.result["size_bytes"] == len(PDF_BYTES)
    resolved = attach.validate_attachments(
        db, [sink.result["artifact_id"]], owner_user_id=1, project_id=10,
        policy=attach.policy_for("smtp"),
    )
    assert resolved[0].filename == "계약서.pdf" and resolved[0].ref.mime_type == "application/pdf"


def test_a_failed_download_leaves_nothing_behind(uploads, db):
    """중간에 끊긴 다운로드는 등록도, 파일도 남기지 않는다 — 반쯤 받은 파일이 첨부되면
    "첨부는 됐는데 열리지 않는" 상태가 된다."""
    import drive_downloads

    before = set(artifacts.upload_root().iterdir())
    make = drive_downloads.sink_factory(db, owner_user_id=1, project_id=10)
    sink = make(filename="끊긴.pdf", mime_type="application/pdf")
    with pytest.raises(RuntimeError):
        with sink as stream:
            stream.write(b"%PDF-1.4 partial")
            raise RuntimeError("연결 끊김")

    assert sink.result == {}
    assert set(artifacts.upload_root().iterdir()) == before


def test_every_delivery_channel_reads_the_same_policy_table():
    for provider in ("discord", "smtp", "gmail"):
        policy = attach.policy_for(provider)
        assert policy.provider == provider
        assert 0 < policy.max_bytes_per_file <= policy.max_total_bytes
        assert policy.max_files > 0 and policy.timeout_seconds > 0
    assert set(attach.policies_public()) == {"discord", "smtp", "gmail"}


def test_node_definitions_declare_the_attachment_port():
    for node_type in ("emailNode", "gmailNode"):
        definition = node_definition.get_definition(node_type)
        field = next(f for f in definition.fields if f.name == "attachments")
        assert field.kind == "attachments"
        assert any(port.name == "attachments" for port in definition.inputs)


def test_register_generated_file_does_not_hijack_another_users_row(uploads, db):
    """stored_name 은 output_path 에서 오고 사용자가 고정할 수 있다(uploads/서식.hwpx).
    남의 파일명과 충돌시켜도, 남의 artifact 행을 덮어쓰거나 그 id 를 돌려받으면 안 된다 —
    예전에는 그게 남의 파일을 자기 산출물로 첨부하는 경로였다."""
    path = artifacts.upload_root() / "shared_name.png"
    path.write_bytes(PNG_BYTES)

    # user 1 이 먼저 등록한다.
    first = artifacts.register_generated_file(db, path=str(path), owner_user_id=1, project_id=10,
                                              purpose="generated-poster")
    assert first is not None
    original_artifact_id = first.artifact_id

    # user 2 가 같은 이름으로 등록을 시도한다(내용을 바꿔서).
    path.write_bytes(PNG_BYTES + b"user2 content")
    hijack = artifacts.register_generated_file(db, path=str(path), owner_user_id=2, project_id=20,
                                               purpose="generated-poster")
    assert hijack is None, "남의 행을 가로챘다"

    # user 1 의 행은 그대로여야 한다 — 소유자·artifact_id 가 안 바뀐다.
    db.expire_all()
    import models
    row = db.query(models.UploadedFile).filter(
        models.UploadedFile.stored_name == "shared_name.png").one()
    assert row.owner_user_id == 1
    assert row.artifact_id == original_artifact_id


def test_register_generated_file_still_reuses_the_owners_own_row(uploads, db):
    """소유자 본인의 재렌더는 여전히 같은 행을 재사용해야 한다(멱등성 보존)."""
    path = artifacts.upload_root() / "mine.png"
    path.write_bytes(PNG_BYTES)
    a = artifacts.register_generated_file(db, path=str(path), owner_user_id=7, project_id=1,
                                          purpose="generated-poster")
    path.write_bytes(PNG_BYTES + b"again")
    b = artifacts.register_generated_file(db, path=str(path), owner_user_id=7, project_id=1,
                                          purpose="generated-poster")
    assert a is not None and b is not None
    assert a.artifact_id == b.artifact_id
