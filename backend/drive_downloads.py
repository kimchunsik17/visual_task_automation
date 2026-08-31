"""drive_downloads.py — 외부에서 받은 파일을 artifact 로 저장한다 (백로그 20번 잔여, §4.7).

Google Drive 의 `download_file` 이 그동안 빠져 있던 이유는 두 가지였다. 하나는 전송 계층이
바이너리를 다루지 못해 받은 파일이 조용히 깨지는 것이었고(`connectors.session.download` 로 해결),
다른 하나는 **받은 파일을 어디에 둘 것인가**였다. 소유자·만료·용량 기록 없이 디스크에 떨어뜨리면
정리할 수도, 첨부할 수도 없는 파일이 쌓인다.

이제 답이 있다 — 받은 파일은 다른 파일과 똑같이 artifact 로 등록된다(ADR-0018). 그래서
"Drive 에서 받아 → 이메일로 첨부" 가 경로 문자열 없이 이어진다.

connector 서비스 모듈(`connectors/services/drive.py`)은 db 를 모른다. 그쪽은 이 모듈이 만든
sink 를 주입받아 바이트만 흘려 넣는다.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import artifacts

DEFAULT_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


def max_download_bytes() -> int:
    try:
        value = int(os.getenv("MAX_DRIVE_DOWNLOAD_BYTES", DEFAULT_MAX_DOWNLOAD_BYTES))
    except ValueError:
        return DEFAULT_MAX_DOWNLOAD_BYTES
    return value if value > 0 else DEFAULT_MAX_DOWNLOAD_BYTES


class ArtifactSink:
    """`with` 안에서 바이트를 받고, 정상 종료하면 artifact 로 등록한다.

    실패하거나 중간에 끊기면 받다 만 파일을 지운다 — 반쯤 받은 파일이 등록되면 뒤에서
    "첨부는 됐는데 열리지 않는" 상태가 된다.
    """

    def __init__(self, db, *, filename: str, mime_type: str,
                 owner_user_id: int, project_id: Optional[int], purpose: str = "downloaded"):
        self.db = db
        self.filename = artifacts.safe_filename(filename)
        self.mime_type = mime_type
        self.owner_user_id = owner_user_id
        self.project_id = project_id
        self.purpose = purpose
        self.result: Dict[str, Any] = {}
        self._path: Optional[Path] = None
        self._handle = None

    def __enter__(self):
        root = artifacts.upload_root()
        root.mkdir(parents=True, exist_ok=True)
        # 저장 이름은 우리가 정한다 — 외부 서비스가 준 이름을 그대로 파일명으로 쓰면 경로 문자와
        # 중복이 그대로 디스크에 들어온다. 원본 이름은 표시용으로만 등록 행에 남는다.
        suffix = Path(self.filename).suffix.lower()
        self._path = root / f"{uuid.uuid4().hex}{suffix}"
        self._handle = self._path.open("xb")
        return self._handle

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._handle:
                self._handle.close()
        finally:
            self._handle = None

        if exc_type is not None or self._path is None:
            if self._path is not None:
                self._path.unlink(missing_ok=True)
            return False

        ref = artifacts.register_generated_file(
            self.db, path=self._path, owner_user_id=self.owner_user_id,
            project_id=self.project_id, purpose=self.purpose,
            original_name=self.filename, content_type=self.mime_type,
        )
        if ref is None:
            # 등록하지 못한 파일은 남기지 않는다(소유자를 모르는 파일을 쌓지 않는다).
            self._path.unlink(missing_ok=True)
            self.result = {}
            return False

        self.result = {
            "artifact_id": ref.artifact_id,
            "size_bytes": ref.size_bytes,
            "mime_type": ref.mime_type,
            "kind": ref.kind,
        }
        return False


def sink_factory(db, *, owner_user_id: int, project_id: Optional[int], purpose: str = "downloaded"):
    """connector 서비스에 넘길 `save_download` 콜러블."""

    def _make(*, filename: str, mime_type: str) -> ArtifactSink:
        return ArtifactSink(db, filename=filename, mime_type=mime_type,
                            owner_user_id=owner_user_id, project_id=project_id, purpose=purpose)

    return _make
