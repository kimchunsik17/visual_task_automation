"""connectors/services/drive.py — Google Drive 액션의 실행부 (Wave 1, 우선 백로그 8번).

파일 입력을 후속 문서·AI 노드로 잇는 기반이다(로드맵 §4.7 Wave 1). 업로드 경로 검증은
YouTube 와 같은 이유로 upload_security 를 공유한다 — 경로는 대개 앞 노드나 LLM 이 만든
문자열이라, 검증 없이 열면 서버 파일이 외부 저장소로 새어 나간다.

■ 모드: search_files, upload_file, create_share_link, download_file.
  download_file 은 Wave 1 에서 제외돼 있었다 — 전송 계층(Response.body = json/text)이 바이너리를
  안전하게 다루지 못해 받은 파일이 조용히 깨졌고, 받은 파일을 소유자·만료 기록 없이 디스크에
  떨어뜨릴 수도 없었다. 이제 둘 다 해결됐다(`ConnectorSession.download` 의 스트리밍,
  ADR-0018 의 artifact 등록) — 받은 파일은 artifactId 로 돌아가 발송 노드가 그대로 첨부한다.
"""

from __future__ import annotations

import mimetypes
import os
import pathlib
from typing import Any, Callable, Dict, Optional

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession, ResponseTooLarge

SERVICE = "Google Drive"
API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

ACTION_NODE_TYPE = "googleDriveNode"

DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024
_FILE_FIELDS = "id,name,mimeType,webViewLink,modifiedTime,size"


def max_download_bytes() -> int:
    """내려받기 한도. 업로드보다 훨씬 작게 잡는다 — 받은 파일은 우리 디스크의 사용자 quota 를
    쓰고, 곧바로 메일·Discord 첨부 한도에 부딪히기 때문이다."""
    from drive_downloads import max_download_bytes as _limit

    return _limit()


def _session(definition, **kwargs: Any) -> ConnectorSession:
    return definition.new_session(**kwargs)


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _require(params: Dict[str, Any], field: str, label: str) -> str:
    value = str(params.get(field) or "").strip()
    if not value:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}이(가) 비어 있다")
    return value


def resolve_upload_path(raw_path: str, *, upload_root: Optional[pathlib.Path] = None) -> pathlib.Path:
    """업로드할 파일 경로 검증(ADR-0010 공용 검사). Drive 는 문서·이미지·영상 모두 다루므로
    일반 업로드 허용 목록과 영상 목록의 합집합을 쓴다."""
    from upload_security import (
        GENERAL_UPLOAD_EXTENSIONS, UnsafeUploadPath, VIDEO_UPLOAD_EXTENSIONS, resolve_stored_path,
    )

    max_bytes = int(os.getenv("MAX_DRIVE_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
    try:
        return resolve_stored_path(
            raw_path,
            allowed_extensions=GENERAL_UPLOAD_EXTENSIONS | VIDEO_UPLOAD_EXTENSIONS,
            max_bytes=max_bytes,
            upload_root=upload_root,
        )
    except UnsafeUploadPath as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from None


def _search_files(session, token, params, open_file, save_download) -> Dict[str, Any]:
    query = _require(params, "query", "검색어")
    # Drive 질의 문자열 리터럴 이스케이프 — 사용자가 q 문법 전체를 직접 쓰고 싶으면 "q:" 접두사.
    if query.startswith("q:"):
        drive_query = query[2:].strip()
    else:
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        drive_query = f"name contains '{escaped}' and trashed = false"
    listing = session.get(
        f"{API_BASE}/files",
        headers=_auth(token),
        params={
            "q": drive_query,
            "pageSize": min(int(params.get("maxResults") or 10), 50),
            "fields": f"files({_FILE_FIELDS})",
        },
    ).json() or {}
    return {"files": listing.get("files") or [], "query": drive_query}


def _upload_file(session, token, params, open_file: Callable[[pathlib.Path], Any], save_download) -> Dict[str, Any]:
    path = resolve_upload_path(params.get("filePath", ""))
    metadata: Dict[str, Any] = {"name": str(params.get("fileName") or "").strip() or path.name}
    folder_id = str(params.get("folderId") or "").strip()
    if folder_id:
        metadata["parents"] = [folder_id]
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with open_file(path) as stream:
        response = session.request(
            "POST",
            f"{UPLOAD_BASE}/files",
            headers=_auth(token),
            params={"uploadType": "multipart", "fields": _FILE_FIELDS},
            files={
                "metadata": ("metadata.json", _json_bytes(metadata), "application/json"),
                "media": (path.name, stream, mime),
            },
        )
    body = response.json() or {}
    return {
        "file_id": body.get("id", ""),
        "name": body.get("name", metadata["name"]),
        "url": body.get("webViewLink", ""),
        "mime_type": body.get("mimeType", mime),
    }


def _create_share_link(session, token, params, open_file, save_download) -> Dict[str, Any]:
    file_id = _require(params, "fileId", "파일 ID")
    # 링크를 아는 누구나 볼 수 있게 — 되돌릴 수 없는 공개는 아니지만 외부 노출이므로
    # 정의의 sideEffectByMode 는 external-write(승인/dry-run 대상)로 분류된다.
    session.post(
        f"{API_BASE}/files/{file_id}/permissions",
        headers=_auth(token),
        json={"role": "reader", "type": "anyone"},
    )
    info = session.get(
        f"{API_BASE}/files/{file_id}",
        headers=_auth(token),
        params={"fields": "id,name,webViewLink"},
    ).json() or {}
    return {"file_id": file_id, "name": info.get("name", ""), "share_url": info.get("webViewLink", "")}


def _download_file(session, token, params, open_file, save_download) -> Dict[str, Any]:
    """Drive 파일을 내려받아 artifact 로 등록한다. 반환값의 `artifact_id` 가 하류 발송 노드의 첨부다.

    저장 위치를 호출부(`drive_downloads.sink_factory`)가 정한다 — 이 모듈은 db 를 모르고,
    서버 파일 경로를 만들지도 않는다.
    """
    file_id = _require(params, "fileId", "파일 ID")
    if save_download is None:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="이 실행 경로는 파일 저장을 지원하지 않는다(다운로드 대상 없음)",
        )

    info = session.get(
        f"{API_BASE}/files/{file_id}", headers=_auth(token), params={"fields": _FILE_FIELDS},
    ).json() or {}
    name = str(info.get("name") or f"{file_id}")
    mime = str(info.get("mimeType") or "application/octet-stream")
    limit = max_download_bytes()

    # 크기를 미리 알 수 있으면 내려받기 전에 거절한다. Google 문서(google-apps/*)는 size 가
    # 없고 그대로 받을 수도 없다 — export 는 별도 범위라 여기서 분명히 끊는다.
    if mime.startswith("application/vnd.google-apps"):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"Google 문서 형식({mime})은 그대로 내려받을 수 없다. Drive 에서 파일로 변환한 뒤 사용해라",
        )
    declared_size = info.get("size")
    if declared_size is not None and int(declared_size) > limit:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"파일이 한도({limit // (1024 * 1024)}MB)를 넘는다",
        )

    sink = save_download(filename=name, mime_type=mime)
    try:
        with sink as stream:
            session.download(
                f"{API_BASE}/files/{file_id}",
                headers=_auth(token), params={"alt": "media"},
                stream_to=stream, max_bytes=limit,
            )
    except ResponseTooLarge as exc:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"파일이 한도({limit // (1024 * 1024)}MB)를 넘는다",
        ) from exc

    if not sink.result:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="내려받은 파일을 저장하지 못했다",
        )
    return {
        "file_id": file_id,
        "name": name,
        "url": info.get("webViewLink", ""),
        **sink.result,
    }


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


_ACTIONS = {
    "search_files": _search_files,
    "upload_file": _upload_file,
    "create_share_link": _create_share_link,
    "download_file": _download_file,
}


def run_action(
    definition,
    mode: str,
    token: str,
    params: Dict[str, Any],
    *,
    session: Optional[ConnectorSession] = None,
    open_file: Callable[[pathlib.Path], Any] = lambda path: path.open("rb"),
    save_download: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    declared = definition.connector.modes
    if mode not in declared:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"'{mode}' 는 이 노드가 지원하지 않는 동작이다. 가능: {', '.join(declared)}",
        )
    session = session or _session(definition)
    return _ACTIONS[mode](session, token, params, open_file, save_download)
