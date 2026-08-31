"""Wave 1 공식 연동 노드(RSS·Gmail·Drive, 우선 백로그 8번) 테스트.

test_youtube_connector 와 같은 방식 — 실제 API 없이 정의의 mock 시나리오로 성공과
실패 경로(인증/한도/타임아웃/형식 오류)를 통과시킨다.
"""

from __future__ import annotations

import io
import pathlib

import pytest

import node_definition
from connectors import mock
from connectors.errors import ConnectorError
from connectors.services import drive, gmail, rss

RSS_DEF = node_definition.get_definition("rssTriggerNode")
GMAIL_TRIGGER = node_definition.get_definition("gmailTriggerNode")
GMAIL_ACTION = node_definition.get_definition("gmailNode")
DRIVE_DEF = node_definition.get_definition("googleDriveNode")


def session_for(definition, scenario: str):
    transport = mock.transport_for(definition.mock, scenario)
    return definition.connector.new_session(transport=transport, sleep=lambda _: None)


# ── 정의 계약 ──────────────────────────────────────────────────────────
def test_definitions_declare_valid_connector_blocks():
    for definition in (RSS_DEF, GMAIL_TRIGGER, GMAIL_ACTION, DRIVE_DEF):
        assert definition.connector is not None
        assert definition.connector.validate_against_registry() == []
        # 모드마다 부수효과 등급이 있어야 dry-run 이 정확히 분류한다(ADR-0008 로딩 검증과 동일 취지).
        for mode in definition.connector.modes:
            assert mode in definition.connector.sideEffectByMode, (definition.type, mode)


def test_write_modes_are_classified_as_external_write():
    assert node_definition.get_definition("gmailNode").sideEffect == "external-write"
    assert DRIVE_DEF.connector.sideEffectByMode["upload_file"] == "external-write"
    assert DRIVE_DEF.connector.sideEffectByMode["search_files"] == "external-read"


# ── RSS ────────────────────────────────────────────────────────────────
def test_rss_first_run_sets_baseline_without_notifying():
    result = rss.poll_new_items(RSS_DEF, feed_url="https://blog.example/rss.xml",
                                session=session_for(RSS_DEF, "success"))
    assert result["first_run"] is True
    assert result["items"] == []
    assert set(result["cursor"]["seen_ids"]) == {"post-1", "post-2"}


def test_rss_reports_only_unseen_items():
    cursor = {"seen_ids": ["post-1"]}
    result = rss.poll_new_items(RSS_DEF, feed_url="https://blog.example/rss.xml",
                                cursor=cursor, session=session_for(RSS_DEF, "success"))
    assert [item["id"] for item in result["items"]] == ["post-2"]
    assert result["items"][0]["title"] == "두 번째 글"
    assert result["items"][0]["link"] == "https://blog.example/2"


def test_rss_rejects_non_feed_documents():
    with pytest.raises(ConnectorError) as exc_info:
        rss.poll_new_items(RSS_DEF, feed_url="https://blog.example/rss.xml",
                           session=session_for(RSS_DEF, "invalid_feed"))
    assert "형식이 아니다" in str(exc_info.value.detail)


def test_rss_rejects_non_http_urls():
    with pytest.raises(ConnectorError):
        rss.poll_new_items(RSS_DEF, feed_url="file:///etc/passwd",
                           session=session_for(RSS_DEF, "success"))


def test_rss_parses_atom_feeds():
    atom = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><id>a1</id><title>아톰 글</title><link rel="alternate" href="https://x/a1"/>'
            '<summary>요약</summary><published>2026-08-27T00:00:00Z</published></entry></feed>')
    items = rss.parse_feed(atom)
    assert items == [{"id": "a1", "title": "아톰 글", "link": "https://x/a1",
                      "summary": "요약", "published_at": "2026-08-27T00:00:00Z"}]


# ── Gmail 트리거 ───────────────────────────────────────────────────────
def test_gmail_first_run_sets_baseline():
    result = gmail.poll_new_emails(GMAIL_TRIGGER, "tok", session=session_for(GMAIL_TRIGGER, "success"))
    assert result["first_run"] is True
    assert result["emails"] == []
    assert result["cursor"]["last_internal_ms"] == 1790000200000  # 최신 메일(m2) 기준점


def test_gmail_reports_new_emails_after_cursor():
    cursor = {"last_internal_ms": 1790000000000, "seen_ids": []}
    result = gmail.poll_new_emails(GMAIL_TRIGGER, "tok", cursor=cursor,
                                   session=session_for(GMAIL_TRIGGER, "success"))
    assert [email["message_id"] for email in result["emails"]] == ["m1", "m2"]  # 오래된 것부터
    assert result["emails"][1]["subject"] == "회의 일정"
    assert result["cursor"]["last_internal_ms"] == 1790000200000


def test_gmail_auth_failure_is_normalized():
    with pytest.raises(ConnectorError) as exc_info:
        gmail.poll_new_emails(GMAIL_TRIGGER, "bad", cursor={"last_internal_ms": 1, "seen_ids": []},
                              session=session_for(GMAIL_TRIGGER, "auth_failed"))
    assert exc_info.value.needs_credential  # 자격증명을 손봐야 하는 오류로 분류


# ── Gmail 액션 ─────────────────────────────────────────────────────────
def test_gmail_send_builds_raw_message():
    result = gmail.run_action(GMAIL_ACTION, "send_email", "tok",
                              {"to": "r@example.com", "subject": "안내", "body": "본문"},
                              session=session_for(GMAIL_ACTION, "success"))
    assert result == {"message_id": "sent1", "thread_id": "t9", "to": "r@example.com"}


def test_gmail_reply_threads_onto_original():
    result = gmail.run_action(GMAIL_ACTION, "reply_email", "tok",
                              {"messageId": "orig1", "body": "답장"},
                              session=session_for(GMAIL_ACTION, "success"))
    assert result["to"] == "sender@example.com"
    assert result["subject"] == "Re: 문의"
    assert result["thread_id"] == "t9"


def test_gmail_add_label_reuses_existing_label():
    result = gmail.run_action(GMAIL_ACTION, "add_label", "tok",
                              {"messageId": "m1", "labelName": "업무"},
                              session=session_for(GMAIL_ACTION, "success"))
    assert result["label_id"] == "Label_1"
    assert result["label_created"] is False


def test_gmail_unknown_mode_is_rejected():
    with pytest.raises(ConnectorError):
        gmail.run_action(GMAIL_ACTION, "delete_everything", "tok", {},
                         session=session_for(GMAIL_ACTION, "success"))


def test_gmail_send_requires_recipient():
    with pytest.raises(ConnectorError) as exc_info:
        gmail.run_action(GMAIL_ACTION, "send_email", "tok", {"subject": "s"},
                         session=session_for(GMAIL_ACTION, "success"))
    assert "수신자" in str(exc_info.value.detail)


# ── Google Drive ───────────────────────────────────────────────────────
def test_drive_search_escapes_query():
    result = drive.run_action(DRIVE_DEF, "search_files", "tok", {"query": "제안'서"},
                              session=session_for(DRIVE_DEF, "success"))
    assert result["query"] == "name contains '제안\\'서' and trashed = false"
    assert result["files"][0]["name"] == "제안서.docx"


def test_drive_upload_rejects_unsafe_paths(tmp_path):
    """업로드 경로는 서버 업로드 저장소 안, 허용 확장자만 통과한다(ADR-0010 공용 검사)."""
    with pytest.raises(ConnectorError):
        drive.resolve_upload_path("../../etc/passwd")
    with pytest.raises(ConnectorError):
        drive.resolve_upload_path("script.exe")


def test_drive_upload_sends_multipart(tmp_path, monkeypatch):
    """경로 검증(위 테스트)과 별개로 multipart 업로드 HTTP 흐름을 mock으로 검증한다."""
    document = tmp_path / "보고서.pdf"
    document.write_bytes(b"%PDF-1.4 mock")
    monkeypatch.setattr(drive, "resolve_upload_path", lambda raw, **kwargs: document)
    result = drive.run_action(
        DRIVE_DEF, "upload_file", "tok",
        {"filePath": str(document), "fileName": "월간 보고서.pdf"},
        session=session_for(DRIVE_DEF, "success"),
        open_file=lambda path: io.BytesIO(b"%PDF-1.4 mock"),
    )
    assert result["file_id"] == "file_up1"
    assert result["url"] == "https://drive.example/file_up1"


def test_drive_share_link_grants_reader_permission():
    result = drive.run_action(DRIVE_DEF, "create_share_link", "tok", {"fileId": "file1"},
                              session=session_for(DRIVE_DEF, "success"))
    assert result == {"file_id": "file1", "name": "제안서.docx", "share_url": "https://drive.example/file1"}


def test_drive_share_link_requires_file_id():
    with pytest.raises(ConnectorError) as exc_info:
        drive.run_action(DRIVE_DEF, "create_share_link", "tok", {},
                         session=session_for(DRIVE_DEF, "success"))
    assert "파일 ID" in str(exc_info.value.detail)


# ── Drive 내려받기 (백로그 20번 잔여 — 전송 계층 바이너리 지원 뒤에 추가) ──
class _CollectingSink:
    """`drive_downloads.ArtifactSink` 자리에 끼우는 테스트 대역. db 없이 바이트만 모은다."""

    def __init__(self, filename, mime_type):
        self.filename, self.mime_type = filename, mime_type
        self.buffer = io.BytesIO()
        self.result = {}
        self.closed = False

    def __enter__(self):
        return self.buffer

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        if exc_type is None:
            self.result = {"artifact_id": "art1", "size_bytes": len(self.buffer.getvalue()),
                           "mime_type": self.mime_type, "kind": "pdf"}
        return False


def _sink_factory():
    made = []

    def _make(*, filename, mime_type):
        sink = _CollectingSink(filename, mime_type)
        made.append(sink)
        return sink

    return _make, made


def test_drive_download_streams_binary_and_returns_an_artifact():
    """예전에는 본문이 json→text 로 해석돼 바이너리가 조용히 깨졌다 — 그래서 이 모드가 없었다.
    이제 `ConnectorSession.download` 가 바이트를 그대로 sink 로 흘려 넣는다."""
    make, made = _sink_factory()
    result = drive.run_action(
        DRIVE_DEF, "download_file", "tok", {"fileId": "file_dl1"},
        session=session_for(DRIVE_DEF, "success"), save_download=make,
    )
    assert result["file_id"] == "file_dl1" and result["name"] == "계약서.pdf"
    assert result["artifact_id"] == "art1"
    payload = made[0].buffer.getvalue()
    assert payload.startswith(b"%PDF-1.4"), payload[:16]
    assert result["size_bytes"] == len(payload)
    assert made[0].closed, "sink 는 성공 경로에서도 반드시 닫힌다"


def test_drive_download_rejects_google_docs_and_oversized_files(monkeypatch):
    """Google 문서는 그대로 받을 수 없고, 크기를 미리 아는 파일은 내려받기 전에 거절한다."""
    make, made = _sink_factory()

    class _Meta:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class _MetaSession:
        def __init__(self, body):
            self.body = body
            self.downloads = 0

        def get(self, url, **kwargs):
            return _Meta(self.body)

        def download(self, *a, **k):
            self.downloads += 1
            raise AssertionError("검증 전에 내려받으면 안 된다")

    google_doc = _MetaSession({"id": "d1", "name": "기획서", "mimeType": "application/vnd.google-apps.document"})
    with pytest.raises(ConnectorError) as exc_info:
        drive.run_action(DRIVE_DEF, "download_file", "tok", {"fileId": "d1"},
                         session=google_doc, save_download=make)
    assert "Google 문서" in str(exc_info.value.detail)

    huge = _MetaSession({"id": "d2", "name": "영상.mp4", "mimeType": "video/mp4",
                         "size": str(drive.max_download_bytes() + 1)})
    with pytest.raises(ConnectorError) as exc_info:
        drive.run_action(DRIVE_DEF, "download_file", "tok", {"fileId": "d2"},
                         session=huge, save_download=make)
    assert "한도" in str(exc_info.value.detail)
    assert made == [], "거절된 요청은 저장소를 건드리지 않는다"


def test_drive_download_requires_a_file_id_and_a_place_to_save():
    make, _ = _sink_factory()
    with pytest.raises(ConnectorError) as exc_info:
        drive.run_action(DRIVE_DEF, "download_file", "tok", {},
                         session=session_for(DRIVE_DEF, "success"), save_download=make)
    assert "파일 ID" in str(exc_info.value.detail)

    # 저장할 곳을 주지 않은 실행 경로는 조용히 버리는 대신 분명히 실패한다.
    with pytest.raises(ConnectorError) as exc_info:
        drive.run_action(DRIVE_DEF, "download_file", "tok", {"fileId": "file_dl1"},
                         session=session_for(DRIVE_DEF, "success"))
    assert "파일 저장" in str(exc_info.value.detail)


def test_session_download_stops_at_the_byte_limit():
    """한도 초과는 다 받은 뒤가 아니라 그 자리에서 끊는다 — 디스크를 먼저 쓰고 재면 늦다."""
    from connectors.session import ConnectorSession, Response, ResponseTooLarge

    class _Raw:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size):
            for _ in range(10):
                yield b"x" * 1024

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _transport(method, url, **kwargs):
        from connectors.session import _stream_body

        written = _stream_body(_Raw(), kwargs["stream_to"], kwargs["max_bytes"])
        return Response(status=200, headers={}, body={"bytes": written})

    session = ConnectorSession("Test", transport=_transport, sleep=lambda _: None)
    sink = io.BytesIO()
    assert session.download("https://x/y", stream_to=sink, max_bytes=10 * 1024).body == {"bytes": 10 * 1024}

    with pytest.raises(ResponseTooLarge):
        session.download("https://x/y", stream_to=io.BytesIO(), max_bytes=4 * 1024)


# ── 코드 생성 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("node_type, data", [
    ("rssTriggerNode", {"feedUrl": "https://blog.example/rss.xml", "maxItems": 5}),
    ("gmailTriggerNode", {"query": "from:a@b.c", "maxResults": 5}),
    ("gmailNode", {"mode": "send_email", "to": "r@x.com", "subject": "제\"목", "body": ""}),
    ("googleDriveNode", {"mode": "upload_file", "filePath": "{{last_result}}"}),
])
def test_generated_code_compiles(node_type, data):
    """생성기는 문자열 조립이라 오타가 실행 시점에야 드러난다 — 컴파일로 앞당긴다."""
    from graph import compile_workflow

    nodes = [
        {"id": "t1", "type": node_type, "data": data},
        {"id": "o1", "type": "outputNode", "data": {}},
    ]
    edges = [{"source": "t1", "target": "o1"}]
    source = compile_workflow(nodes, edges)
    assert not source.startswith("Error"), source
    compile(source, "<wave1>", "exec")


# ── rssTriggerNode cursor 회귀 (계획 §2 불일치 12, 2026-08-30) ──────────
#
# 예전 구현은 `next_cursor = 현재 피드의 id 전부` 였다. 두 가지가 깨졌다.
#
#   1. 피드에서 밀려났다 돌아온 항목이 "새 글" 로 다시 통지된다.
#   2. `max_items` 로 잘려 나간 항목까지 seen 에 들어가 **통지되지 않은 채 사라진다.**

def _feed(*ids):
    items = "".join(
        f"<item><guid>{i}</guid><title>{i}</title><link>https://e.com/{i}</link></item>"
        for i in ids)
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>"


def _poll(feed_xml, cursor=None, max_items=10):
    from connectors.services import rss
    from connectors.session import ConnectorSession, Response

    transport = lambda method, url, **kw: Response(status=200, headers={}, body=feed_xml)
    session = ConnectorSession("RSS", transport=transport, sleep=lambda _s: None)
    return rss.poll_new_items(None, feed_url="https://e.com/feed", cursor=cursor,
                              max_items=max_items, session=session)


def test_첫_실행은_기준선만_만든다():
    result = _poll(_feed("a", "b", "c"))
    assert result["first_run"] is True and result["items"] == []
    assert set(result["cursor"]["seen_ids"]) == {"a", "b", "c"}


def test_새_항목만_통지한다():
    first = _poll(_feed("a", "b"))
    second = _poll(_feed("c", "a", "b"), cursor=first["cursor"])
    assert [i["id"] for i in second["items"]] == ["c"]


def test_밀려났다_돌아온_항목을_다시_통지하지_않는다():
    """이게 §2 불일치 12 다. 예전에는 'a' 가 새 글로 다시 잡혔다."""
    first = _poll(_feed("a", "b", "c"))
    # 피드가 잠깐 'a' 를 밀어냈다
    second = _poll(_feed("d", "b", "c"), cursor=first["cursor"])
    assert [i["id"] for i in second["items"]] == ["d"]
    # 다시 돌아왔다 — 새 글이 아니다
    third = _poll(_feed("a", "d", "b", "c"), cursor=second["cursor"])
    assert third["items"] == [], f"밀려났다 돌아온 항목이 재통지됐다: {third['items']}"


def test_피드가_잠깐_비어도_기억을_잃지_않는다():
    """서버 오류로 항목이 0개 온 뒤 원래대로 돌아오면, 예전 구현은 전부 다시 알렸다."""
    first = _poll(_feed("a", "b", "c"))
    empty = _poll(_feed(), cursor=first["cursor"])
    assert empty["items"] == []
    back = _poll(_feed("a", "b", "c"), cursor=empty["cursor"])
    assert back["items"] == [], f"피드 복구 후 재통지됐다: {back['items']}"


def test_잘려_나간_항목은_다음_실행에서_온다():
    """예전에는 max_items 를 넘은 것이 통지 없이 seen 으로 들어가 사라졌다."""
    first = _poll(_feed("base"))
    second = _poll(_feed("n1", "n2", "n3", "base"), cursor=first["cursor"], max_items=2)
    assert [i["id"] for i in second["items"]] == ["n1", "n2"]
    assert second["pending"] == 1
    third = _poll(_feed("n1", "n2", "n3", "base"), cursor=second["cursor"], max_items=2)
    assert [i["id"] for i in third["items"]] == ["n3"], "잘려 나간 항목이 사라졌다"


def test_겹침_창_크기를_넘으면_오래된_것부터_잊는다():
    from connectors.services import rss

    cursor = {"version": rss.CURSOR_VERSION,
              "seen_ids": [f"old{i}" for i in range(rss.SEEN_WINDOW)]}
    result = _poll(_feed("new1"), cursor=cursor, max_items=10)
    assert len(result["cursor"]["seen_ids"]) == rss.SEEN_WINDOW
    assert "new1" in result["cursor"]["seen_ids"]


def test_예전_cursor도_계속_읽는다():
    """version 이 없는 기존 cursor 가 DB 에 남아 있다 — 첫 실행으로 강등하면 과거를 다시 알린다."""
    legacy = {"seen_ids": ["a", "b"]}
    result = _poll(_feed("c", "a", "b"), cursor=legacy)
    assert result["first_run"] is False
    assert [i["id"] for i in result["items"]] == ["c"]
    assert result["cursor"]["version"] == 1


def test_모르는_cursor_형식은_거부한다():
    from connectors.errors import ConnectorError

    with pytest.raises(ConnectorError):
        _poll(_feed("a"), cursor={"version": 99, "seen_ids": []})
