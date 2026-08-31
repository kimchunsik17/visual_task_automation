"""YouTube 공식 연동 노드 (ADR-0008) 테스트.

실제 API 없이 정의의 mock 시나리오로 성공·인증 실패·호출 한도·타임아웃·잘못된 ID 를
모두 통과시킨다 — 진짜 계정으로는 실패 경로를 재현하기 어렵고, 정작 사용자를 막는 것은
그 실패 경로다.
"""

from __future__ import annotations

import datetime
import io
import pathlib

import pytest

import node_definition
from connectors import errors, mock
from connectors.errors import ConnectorError
from connectors.retry import RetryPolicy
from connectors.services import youtube

TRIGGER = node_definition.get_definition("youtubeTriggerNode")
ACTION = node_definition.get_definition("youtubeNode")


def session_for(definition, scenario: str, **kwargs):
    """정의의 mock 시나리오를 재생하는 세션. 실제 정책(타임아웃/재시도/rate limit)은 그대로 쓴다."""
    transport = mock.transport_for(definition.mock, scenario)
    session = definition.connector.new_session(transport=transport, sleep=lambda _: None, **kwargs)
    session.mock_transport = transport
    return session


# ── 정의와 계약 ────────────────────────────────────────────────────────
def test_definitions_declare_a_valid_connector_block():
    for definition in (TRIGGER, ACTION):
        assert definition.connector is not None
        assert definition.connector.validate_against_registry() == []


def test_action_modes_are_all_marked_as_external_writes():
    """업로드·수정·댓글·재생목록은 전부 되돌릴 수 없는 외부 게시다 — dry-run 이 막아야 한다."""
    for mode in ACTION.connector.modes:
        assert ACTION.connector.writes_externally(mode), mode


def test_trigger_is_read_only():
    assert TRIGGER.connector.writes_externally("new_video") is False


def test_dry_run_classification_comes_from_the_definitions():
    import dry_run

    assert "youtubeNode" in dry_run.SIDE_EFFECT_NODE_TYPES
    assert "youtubeTriggerNode" in dry_run.TRIGGER_NODE_TYPES


def test_every_scenario_the_release_gate_requires_is_present():
    for definition in (TRIGGER, ACTION):
        assert {"success", "auth_failed", "rate_limited", "not_found", "timeout"} <= set(
            mock.scenario_names(definition.mock)
        )


# ── 트리거 ─────────────────────────────────────────────────────────────
def test_first_run_records_a_cursor_without_notifying_anything():
    """워크플로우를 켠 순간 과거 영상 전부에 알림이 쏟아지면 안 된다."""
    result = youtube.poll_new_videos(TRIGGER, "token", session=session_for(TRIGGER, "success"))

    assert result["first_run"] is True
    assert result["videos"] == []
    assert result["cursor"]["last_published_at"] == "2026-08-27T09:00:00Z"


def test_second_run_reports_only_videos_newer_than_the_cursor():
    cursor = {"last_published_at": "2026-08-26T09:00:00Z", "seen_video_ids": ["vid_001"]}
    result = youtube.poll_new_videos(TRIGGER, "token", cursor=cursor, session=session_for(TRIGGER, "success"))

    assert [video["video_id"] for video in result["videos"]] == ["vid_002"]
    assert result["videos"][0]["url"] == "https://www.youtube.com/watch?v=vid_002"


def test_already_seen_videos_are_not_reported_twice():
    """게시 시각만 비교하면 같은 초에 올라온 영상을 중복 통지한다 — id 도 함께 봐야 한다."""
    cursor = {"last_published_at": "2026-08-27T09:00:00Z", "seen_video_ids": ["vid_002"]}
    result = youtube.poll_new_videos(TRIGGER, "token", cursor=cursor, session=session_for(TRIGGER, "success"))

    assert result["videos"] == []


def test_trigger_auth_failure_is_actionable():
    with pytest.raises(ConnectorError) as caught:
        youtube.poll_new_videos(TRIGGER, "bad", session=session_for(TRIGGER, "auth_failed"))

    error = caught.value
    assert error.code == errors.AUTH_INVALID
    assert error.needs_credential and not error.retryable
    assert "API 센터" in error.user_message


def test_trigger_missing_channel_says_what_to_fix():
    with pytest.raises(ConnectorError) as caught:
        youtube.poll_new_videos(TRIGGER, "t", channel_id="UC_nope", session=session_for(TRIGGER, "not_found"))

    assert caught.value.code == errors.NOT_FOUND


def test_rate_limit_is_retried_for_reads_and_honours_retry_after():
    session = session_for(TRIGGER, "rate_limited")
    with pytest.raises(ConnectorError) as caught:
        youtube.poll_new_videos(TRIGGER, "t", session=session)

    assert caught.value.code == errors.RATE_LIMITED
    # Retry-After 30초가 정책의 max_delay(20초)를 넘으므로 붙잡아 두지 않고 바로 포기한다.
    assert session.attempts == 1


def test_timeout_is_classified_as_a_timeout_not_an_unknown_error():
    with pytest.raises(ConnectorError) as caught:
        youtube.poll_new_videos(TRIGGER, "t", session=session_for(TRIGGER, "timeout"))

    assert caught.value.code == errors.TIMEOUT


# ── 액션 ───────────────────────────────────────────────────────────────
def test_comment_uses_the_declared_endpoint_and_returns_the_id():
    session = session_for(ACTION, "success")
    result = youtube.run_action(ACTION, "create_comment", "t", {"videoId": "v1", "commentText": "좋아요"}, session=session)

    assert result["comment_id"] == "mock_comment_id"
    assert session.mock_transport.calls[0]["url"].endswith("/commentThreads")


def test_playlist_add_returns_the_item_id():
    result = youtube.run_action(
        ACTION, "add_to_playlist", "t", {"videoId": "v1", "playlistId": "PL1"},
        session=session_for(ACTION, "success"),
    )
    assert result["playlist_item_id"] == "mock_playlist_item_id"


def test_update_metadata_always_sends_category_id():
    """YouTube 는 snippet 을 통째로 바꾼다 — categoryId 를 빼면 기존 값이 날아간다."""
    session = session_for(ACTION, "success")
    youtube.run_action(ACTION, "update_metadata", "t", {"videoId": "v1", "title": "새 제목"}, session=session)
    assert session.mock_transport.calls[0]["method"] == "PUT"


def test_unknown_mode_is_rejected_before_any_call():
    session = session_for(ACTION, "success")
    with pytest.raises(ConnectorError) as caught:
        youtube.run_action(ACTION, "delete_channel", "t", {}, session=session)

    assert caught.value.code == errors.INVALID_REQUEST
    assert session.mock_transport.calls == []  # 요청이 나가지 않았다


def test_missing_required_field_is_rejected_before_any_call():
    session = session_for(ACTION, "success")
    with pytest.raises(ConnectorError):
        youtube.run_action(ACTION, "create_comment", "t", {"videoId": "v1", "commentText": ""}, session=session)
    assert session.mock_transport.calls == []


def test_write_actions_are_not_retried_on_timeout():
    """댓글을 다시 보내면 같은 댓글이 두 번 달린다 — 요청이 서버에 닿았는지 알 수 없기 때문이다."""
    session = session_for(ACTION, "timeout")
    with pytest.raises(ConnectorError):
        youtube.run_action(ACTION, "create_comment", "t", {"videoId": "v1", "commentText": "x"}, session=session)
    assert session.attempts == 1


# ── 업로드 파일 검증 ───────────────────────────────────────────────────
def test_upload_rejects_paths_outside_the_upload_directory(tmp_path):
    """경로는 대개 앞 노드나 LLM 이 만든 문자열이다. 검증 없이 열면 서버 파일이 공개 영상으로
    올라갈 수 있고, 그건 되돌릴 수 없다."""
    root = tmp_path / "uploads"
    root.mkdir()
    outsider = tmp_path / "secret.mp4"
    outsider.write_bytes(b"x" * 10)

    with pytest.raises(ConnectorError) as caught:
        youtube.resolve_upload_path(str(outsider), upload_root=root)
    assert "밖의 경로" in caught.value.detail

    with pytest.raises(ConnectorError):
        youtube.resolve_upload_path("../secret.mp4", upload_root=root)


def test_upload_rejects_disallowed_extensions(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "payload.sh").write_bytes(b"#!/bin/sh")

    with pytest.raises(ConnectorError) as caught:
        youtube.resolve_upload_path("payload.sh", upload_root=root)
    assert "확장자" in caught.value.detail


def test_upload_rejects_empty_and_oversized_files(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "empty.mp4").write_bytes(b"")
    with pytest.raises(ConnectorError):
        youtube.resolve_upload_path("empty.mp4", upload_root=root)

    (root / "big.mp4").write_bytes(b"x" * 1000)
    monkeypatch.setenv("MAX_VIDEO_UPLOAD_BYTES", "100")
    with pytest.raises(ConnectorError) as caught:
        youtube.resolve_upload_path("big.mp4", upload_root=root)
    assert "한도" in caught.value.detail


def test_upload_accepts_a_valid_file_and_posts_it(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"fake video bytes")
    monkeypatch.setenv("UPLOAD_DIR", str(root))

    session = session_for(ACTION, "success")
    result = youtube.run_action(
        ACTION, "upload_video", "t",
        {"filePath": "clip.mp4", "title": "테스트", "privacyStatus": "private"},
        session=session,
    )

    assert result["video_id"] == "mock_video_id"
    assert result["url"] == "https://www.youtube.com/watch?v=mock_video_id"
    assert session.mock_transport.calls[0]["url"].startswith(youtube.UPLOAD_BASE)


def test_upload_refuses_an_unknown_privacy_status(tmp_path, monkeypatch):
    """공개 범위를 잘못 넘기면 의도치 않게 전체 공개가 될 수 있다 — 값을 좁게 검사한다."""
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"v")
    monkeypatch.setenv("UPLOAD_DIR", str(root))

    with pytest.raises(ConnectorError) as caught:
        youtube.run_action(ACTION, "upload_video", "t",
                           {"filePath": "clip.mp4", "privacyStatus": "everyone"},
                           session=session_for(ACTION, "success"))
    assert "공개 범위" in caught.value.detail


def test_dry_run_summary_describes_the_effect_without_calling_anything():
    summary = youtube.describe_action("upload_video", {"filePath": "a.mp4", "title": "제목", "privacyStatus": "public"})
    assert "업로드한다" in summary and "public" in summary


# ── mock transport 자체 ────────────────────────────────────────────────
def test_mock_transport_fails_loudly_on_an_unexpected_request():
    """조용히 200 을 돌려주면 mock 이 실제 계약과 어긋나도 테스트가 통과해버린다."""
    transport = mock.transport_for(TRIGGER.mock, "success")
    with pytest.raises(mock.MockScenarioError):
        transport("GET", "https://www.googleapis.com/youtube/v3/전혀-다른-엔드포인트")


def test_unknown_scenario_name_lists_the_available_ones():
    with pytest.raises(mock.MockScenarioError) as caught:
        mock.transport_for(ACTION.mock, "없는시나리오")
    assert "success" in str(caught.value)


def test_once_rules_let_a_retry_scenario_be_expressed():
    transport = mock.MockTransport({
        "responses": [
            {"status": 503, "body": "일시 오류", "once": True},
            {"status": 200, "body": {"ok": True}},
        ]
    })
    from connectors.session import ConnectorSession

    session = ConnectorSession("X", transport=transport, retry_policy=RetryPolicy(max_attempts=3, jitter=0), sleep=lambda _: None)
    assert session.get("https://x.dev").json() == {"ok": True}
    assert session.attempts == 2
