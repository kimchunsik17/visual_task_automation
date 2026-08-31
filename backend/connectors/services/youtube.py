"""connectors/services/youtube.py — YouTube 공식 연동 노드의 실행부 (ADR-0008).

공통 계약(ADR-0007)의 첫 실제 소비자다. 서비스 고유한 것만 여기 두고, 타임아웃·재시도·
오류 분류·페이지 넘기기·rate limit 은 ConnectorSession 이 처리한다. 그래서 이 파일에는
`requests` 호출도, status_code 비교도, 재시도 루프도 없다.

■ 노드가 두 개인 이유
  youtubeTriggerNode : 채널에 새 영상이 올라왔는지 본다(읽기 전용, cursor 로 중복 제거)
  youtubeNode        : 업로드/정보 수정/댓글/재생목록 (전부 외부 쓰기)

■ 중복 실행
  트리거는 마지막으로 처리한 영상의 게시 시각과 id 집합을 cursor 로 들고 다닌다. 게시 시각만
  쓰면 같은 초에 올라온 영상을 놓치거나 중복 통지하므로, 시각과 id 를 함께 본다.
"""

from __future__ import annotations

import datetime
import mimetypes
import os
import pathlib
from typing import Any, Callable, Dict, List, Optional

from ..errors import INVALID_REQUEST, ConnectorError
from ..pagination import PaginationConfig
from ..session import ConnectorSession

SERVICE = "YouTube"
API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"

TRIGGER_NODE_TYPE = "youtubeTriggerNode"
ACTION_NODE_TYPE = "youtubeNode"

# 업로드는 되돌릴 수 없는 외부 게시라 크기 한도를 따로 둔다(허용 확장자는 upload_security 공용).
DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024

PRIVACY_STATUSES = {"private", "unlisted", "public"}


def _session(definition, **kwargs: Any) -> ConnectorSession:
    """노드 정의의 정책이 반영된 호출 창구. mock 실행 모드면 자동으로 시나리오를 탄다."""
    return definition.new_session(**kwargs)


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 파일 검증 ──────────────────────────────────────────────────────────
def resolve_upload_path(raw_path: str, *, upload_root: Optional[pathlib.Path] = None) -> pathlib.Path:
    """업로드할 영상 경로를 검증한다.

    검사 자체는 upload_security.resolve_stored_path 가 공유한다(ADR-0010) — 파일을 다루는
    노드가 늘 때마다 같은 검사를 다시 짜지 않기 위해서다. 여기서는 YouTube 에 맞는 허용
    확장자와 크기 한도만 정하고, 실패를 이 커넥터의 오류 형식으로 감싼다.
    """
    from upload_security import UnsafeUploadPath, VIDEO_UPLOAD_EXTENSIONS, resolve_stored_path

    max_bytes = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
    try:
        return resolve_stored_path(
            raw_path,
            allowed_extensions=VIDEO_UPLOAD_EXTENSIONS,
            max_bytes=max_bytes,
            upload_root=upload_root,
        )
    except UnsafeUploadPath as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from None


# ── 트리거 ─────────────────────────────────────────────────────────────
def _uploads_playlist_id(session: ConnectorSession, token: str, channel_id: str) -> str:
    params = {"part": "contentDetails"}
    if channel_id:
        params["id"] = channel_id
    else:
        params["mine"] = "true"
    payload = session.get(f"{API_BASE}/channels", headers=_auth(token), params=params).json()
    items = (payload or {}).get("items") or []
    if not items:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="채널을 찾지 못했다. 채널 ID 를 확인하거나 비워서 내 채널을 쓰도록 하라",
        )
    playlist_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not playlist_id:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="채널의 업로드 재생목록을 찾지 못했다")
    return playlist_id


def poll_new_videos(
    definition,
    token: str,
    *,
    channel_id: str = "",
    cursor: Optional[Dict[str, Any]] = None,
    max_results: int = 10,
    session: Optional[ConnectorSession] = None,
) -> Dict[str, Any]:
    """마지막 실행 이후 올라온 영상만 돌려주고, 다음 실행에 쓸 cursor 를 함께 준다.

    첫 실행에서는 아무것도 통지하지 않고 cursor 만 잡는다 — 그러지 않으면 워크플로우를 켠
    순간 과거 영상 전부에 대해 알림이 쏟아진다.
    """
    session = session or _session(definition)
    cursor = cursor or {}
    playlist_id = _uploads_playlist_id(session, token, channel_id)

    config = definition.connector.pagination_config()
    collected = session.collect(
        f"{API_BASE}/playlistItems",
        headers=_auth(token),
        params={"part": "snippet,contentDetails", "playlistId": playlist_id},
        config=PaginationConfig(
            style=config.style, cursor_param=config.cursor_param, cursor_path=config.cursor_path,
            items_path=config.items_path, limit_param="maxResults",
            page_size=min(max_results, 50), max_pages=config.max_pages, max_items=max_results,
        ),
    )

    videos: List[Dict[str, Any]] = []
    for item in collected.items:
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        video_id = details.get("videoId") or (snippet.get("resourceId") or {}).get("videoId")
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "published_at": details.get("videoPublishedAt") or snippet.get("publishedAt") or "",
            "channel_title": snippet.get("channelTitle", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    videos.sort(key=lambda v: v["published_at"])
    last_published = cursor.get("last_published_at") or ""
    seen_ids = set(cursor.get("seen_video_ids") or [])
    first_run = not cursor

    if first_run:
        fresh: List[Dict[str, Any]] = []
    else:
        # 게시 시각만 비교하면 같은 초에 올라온 영상을 놓치거나 중복 통지한다 — id 도 함께 본다.
        fresh = [
            video for video in videos
            if video["video_id"] not in seen_ids
            and (not last_published or video["published_at"] >= last_published)
        ]

    newest = max([v["published_at"] for v in videos] + [last_published]) if videos else last_published
    next_cursor = {
        "last_published_at": newest,
        # 같은 시각의 중복만 걸러내면 되므로 전체 id 를 들고 다니지 않는다.
        "seen_video_ids": sorted({v["video_id"] for v in videos if v["published_at"] == newest} | (
            seen_ids if newest == last_published else set()
        )),
    }
    return {
        "videos": fresh,
        "cursor": next_cursor,
        "first_run": first_run,
        "truncated": collected.truncated,
        "playlist_id": playlist_id,
    }


# ── 액션 ───────────────────────────────────────────────────────────────
def _upload_video(session, token, params, open_file: Callable[[pathlib.Path], Any]) -> Dict[str, Any]:
    path = resolve_upload_path(params.get("filePath", ""))
    privacy = (params.get("privacyStatus") or "private").strip()
    if privacy not in PRIVACY_STATUSES:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"공개 범위는 {', '.join(sorted(PRIVACY_STATUSES))} 중 하나여야 한다 (현재: {privacy})",
        )

    metadata = {
        "snippet": {
            "title": params.get("title") or path.stem,
            "description": params.get("description") or "",
        },
        "status": {"privacyStatus": privacy},
    }
    mime = mimetypes.guess_type(path.name)[0] or "video/*"
    with open_file(path) as stream:
        response = session.request(
            "POST",
            f"{UPLOAD_BASE}/videos",
            headers=_auth(token),
            params={"uploadType": "multipart", "part": "snippet,status"},
            files={
                "metadata": ("metadata.json", _json_bytes(metadata), "application/json"),
                "media": (path.name, stream, mime),
            },
        )
    body = response.json() or {}
    video_id = body.get("id", "")
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "privacy_status": privacy,
        "title": metadata["snippet"]["title"],
    }


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _require(params: Dict[str, Any], field: str, label: str) -> str:
    value = str(params.get(field) or "").strip()
    if not value:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}이(가) 비어 있다")
    return value


def _update_metadata(session, token, params) -> Dict[str, Any]:
    video_id = _require(params, "videoId", "영상 ID")
    snippet: Dict[str, Any] = {}
    if params.get("title"):
        snippet["title"] = params["title"]
    if params.get("description"):
        snippet["description"] = params["description"]
    # YouTube 는 snippet 을 통째로 바꾸므로 categoryId 를 함께 보내야 기존 값이 날아가지 않는다.
    snippet["categoryId"] = str(params.get("categoryId") or "22")

    body: Dict[str, Any] = {"id": video_id, "snippet": snippet}
    parts = ["snippet"]
    privacy = (params.get("privacyStatus") or "").strip()
    if privacy:
        if privacy not in PRIVACY_STATUSES:
            raise ConnectorError(
                code=INVALID_REQUEST, service=SERVICE,
                detail=f"공개 범위는 {', '.join(sorted(PRIVACY_STATUSES))} 중 하나여야 한다 (현재: {privacy})",
            )
        body["status"] = {"privacyStatus": privacy}
        parts.append("status")

    session.request("PUT", f"{API_BASE}/videos", headers=_auth(token),
                    params={"part": ",".join(parts)}, json=body)
    return {"video_id": video_id, "updated_parts": parts, "privacy_status": privacy or "변경 없음"}


def _create_comment(session, token, params) -> Dict[str, Any]:
    video_id = _require(params, "videoId", "영상 ID")
    text = _require(params, "commentText", "댓글 내용")
    body = {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}
    response = session.post(f"{API_BASE}/commentThreads", headers=_auth(token),
                            params={"part": "snippet"}, json=body)
    return {"video_id": video_id, "comment_id": (response.json() or {}).get("id", "")}


def _add_to_playlist(session, token, params) -> Dict[str, Any]:
    video_id = _require(params, "videoId", "영상 ID")
    playlist_id = _require(params, "playlistId", "재생목록 ID")
    body = {"snippet": {"playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    response = session.post(f"{API_BASE}/playlistItems", headers=_auth(token),
                            params={"part": "snippet"}, json=body)
    return {"video_id": video_id, "playlist_id": playlist_id,
            "playlist_item_id": (response.json() or {}).get("id", "")}


_ACTIONS: Dict[str, Callable] = {
    "update_metadata": _update_metadata,
    "create_comment": _create_comment,
    "add_to_playlist": _add_to_playlist,
}


def describe_action(mode: str, params: Dict[str, Any]) -> str:
    """dry-run 요약. 실행하지 않고 '무엇이 일어날 뻔했는지' 를 사람이 읽을 문장으로 만든다."""
    if mode == "upload_video":
        privacy = params.get("privacyStatus") or "private"
        return (f"영상 파일 '{params.get('filePath', '')}' 을(를) 제목 "
                f"'{params.get('title', '(파일명)')}' / 공개 범위 '{privacy}' 로 업로드한다")
    if mode == "update_metadata":
        return f"영상 {params.get('videoId', '')} 의 정보를 수정한다 (공개 범위: {params.get('privacyStatus') or '변경 없음'})"
    if mode == "create_comment":
        text = str(params.get("commentText", ""))
        return f"영상 {params.get('videoId', '')} 에 댓글을 단다: \"{text[:40]}{'…' if len(text) > 40 else ''}\""
    if mode == "add_to_playlist":
        return f"영상 {params.get('videoId', '')} 을(를) 재생목록 {params.get('playlistId', '')} 에 추가한다"
    return f"알 수 없는 동작({mode})"


def run_action(
    definition,
    mode: str,
    token: str,
    params: Dict[str, Any],
    *,
    session: Optional[ConnectorSession] = None,
    open_file: Callable[[pathlib.Path], Any] = lambda path: path.open("rb"),
) -> Dict[str, Any]:
    """액션 하나를 실행한다. 실패는 전부 정규화된 ConnectorError 로 올라온다."""
    declared = definition.connector.modes
    if mode not in declared:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"'{mode}' 는 이 노드가 지원하지 않는 동작이다. 가능: {', '.join(declared)}",
        )
    session = session or _session(definition)
    if mode == "upload_video":
        result = _upload_video(session, token, params, open_file)
    else:
        result = _ACTIONS[mode](session, token, params)
    result["mode"] = mode
    result["telemetry"] = session.telemetry()
    return result
