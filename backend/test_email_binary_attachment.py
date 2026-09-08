"""이메일 첨부가 이진 파일(PNG·DOCX)이어도 바이트와 형식이 그대로 SMTP 로 나가는지 — 실제 경로 전체.

artifact 등록 → 소유·정책 검증 → 열기(rb) → MIME 조립 → smtplib.send_message 직전까지를 그대로 태우고,
보내려던 메시지를 파싱해 첨부 바이트와 Content-Type 을 원본과 비교한다(2026-09-06 "텍스트가 아닌
첨부가 깨진다" 제보 재현용). PNG_BYTES·fixture 는 test_artifact_delivery 의 것을 그대로 쓴다.
"""
import email
import email.policy

import delivery_runtime
from test_artifact_delivery import PNG_BYTES, _store, db, uploads  # noqa: F401 — fixture 재사용

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_BYTES = b"PK\x03\x04" + bytes(range(256)) * 24          # ZIP 서명 + 모든 바이트 값


class _CaptureSmtp:
    """smtplib.SMTP 대역 — 보내려던 메시지의 직렬화 바이트만 남긴다."""
    sent = []

    def __init__(self, server, port, timeout=None):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        _CaptureSmtp.sent.append(message.as_bytes())

    def quit(self):
        pass


def test_binary_attachments_arrive_intact_with_their_type(uploads, db):
    png = _store(uploads, db, name="안내 포스터.png", content=PNG_BYTES, mime="image/png")
    docx = _store(uploads, db, name="여행 일정표.docx", content=DOCX_BYTES, mime=DOCX_MIME)

    res = delivery_runtime.send_smtp(
        smtp_server="smtp.test", smtp_port=587, smtp_user="sender@test", smtp_password="p",
        to_email="owner@example.com", subject="첨부 확인", body="본문",
        db=db, owner_user_id=1, project_id=10,
        attachments_config={"mode": "auto", "artifactIds": []},
        upstream_artifact_ids=[png.artifact_id, docx.artifact_id], upstream_text="",
        node_id="mail", client_factory=_CaptureSmtp,
    )
    assert res.error is None, str(res)

    parsed = email.message_from_bytes(_CaptureSmtp.sent[-1], policy=email.policy.default)
    parts = {part.get_filename(): part for part in parsed.iter_attachments()}
    assert set(parts) == {"안내 포스터.png", "여행 일정표.docx"}, set(parts)
    assert parts["안내 포스터.png"].get_payload(decode=True) == PNG_BYTES
    assert parts["안내 포스터.png"].get_content_type() == "image/png"
    assert parts["여행 일정표.docx"].get_payload(decode=True) == DOCX_BYTES
    # ZIP 서명을 가진 문서(docx·xlsx·hwpx)는 'application/zip' 이 아니라 문서 형식으로 나가야 한다 —
    # zip 으로 실리면 일부 메일 앱이 압축 파일로 다뤄 열지 못한다.
    assert parts["여행 일정표.docx"].get_content_type() == DOCX_MIME

    # 어드민 시연 패널의 "오늘 발송 수" 근거 — 성공 1건마다 email_sent 이벤트 한 행
    import models
    events = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.event_type == "email_sent").all()
    assert len(events) == 1 and events[0].actor_user_id == 1 and events[0].total_tokens == 0
