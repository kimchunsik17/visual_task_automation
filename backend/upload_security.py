"""upload_security.py — 업로드 파일의 검증·소유·용량·보존 (ADR-0010).

파일이 서버에 들어오는 경로(업로드)와 워크플로우가 파일을 읽는 경로(경로 검증)를 한 곳에서
다룬다. 예전에는 업로드에 인증이 없었고, 경로 검증은 YouTube 노드 안에만 있었다.
"""

from __future__ import annotations

import datetime
import os
import uuid
from pathlib import Path
from typing import Collection, Optional

from fastapi import HTTPException, UploadFile, status


UPLOAD_DIR = Path("uploads")
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_CONTEXT_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_CONTEXT_FILES = 5
# 사용자 한 명이 차지할 수 있는 총 용량과 파일 수. 익명 업로드는 앱 소유자 몫으로 계산되므로
# 공개된 앱 하나가 서버 디스크를 통째로 채우는 것을 여기서 막는다.
DEFAULT_QUOTA_BYTES_PER_USER = 200 * 1024 * 1024
DEFAULT_QUOTA_FILES_PER_USER = 200
# 업로드 파일 보존 기간. 지나면 정리 대상이 된다.
DEFAULT_RETENTION_DAYS = 30

# 영상은 일반 업로드 허용 목록에 없다 — 문서 요약 앱에 실행 파일이 올라갈 이유가 없듯,
# 용도별로 목록을 따로 둔다(YouTube 업로드 노드가 이 목록을 쓴다).
VIDEO_UPLOAD_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".mpeg", ".mpg", ".wmv",
}

GENERAL_UPLOAD_EXTENSIONS = {
    ".csv", ".doc", ".docx", ".gif", ".hwp", ".hwpx", ".jpeg", ".jpg",
    ".json", ".md", ".pdf", ".png", ".ppt", ".pptx", ".txt", ".webp",
    ".xls", ".xlsx",
}
CONTEXT_UPLOAD_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt"}

# 커뮤니티 글 이미지. 문서·표는 받지 않는다 — 글에 붙는 것은 보여줄 그림이지 자료가 아니다.
IMAGE_UPLOAD_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def max_upload_bytes() -> int:
    return _positive_int_env("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)


def max_context_bytes() -> int:
    return _positive_int_env("MAX_CONTEXT_FILE_BYTES", DEFAULT_MAX_CONTEXT_BYTES)


def max_context_files() -> int:
    return _positive_int_env("MAX_CONTEXT_FILES", DEFAULT_MAX_CONTEXT_FILES)


def quota_bytes_per_user() -> int:
    return _positive_int_env("UPLOAD_QUOTA_BYTES_PER_USER", DEFAULT_QUOTA_BYTES_PER_USER)


def quota_files_per_user() -> int:
    return _positive_int_env("UPLOAD_QUOTA_FILES_PER_USER", DEFAULT_QUOTA_FILES_PER_USER)


def retention_days() -> int:
    return _positive_int_env("UPLOAD_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)


def validate_filename(filename: str | None, allowed_extensions: Collection[str]) -> tuple[str, str]:
    safe_name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid filename is required.",
        )

    extension = Path(safe_name).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed extensions: {allowed}",
        )
    return safe_name, extension


async def save_upload_limited(
    upload: UploadFile,
    *,
    allowed_extensions: Collection[str],
    max_bytes: int,
) -> tuple[Path, str]:
    original_name, extension = validate_filename(upload.filename, allowed_extensions)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
    total_bytes = 0

    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit.",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty files are not allowed.")

    return destination, original_name


# ── 소유·용량·보존 ──────────────────────────────────────────────────────
def current_usage(db, owner_user_id: int) -> tuple[int, int]:
    """이 사용자 몫으로 잡혀 있는 (총 바이트, 파일 수)."""
    from sqlalchemy import func

    import models

    row = (
        db.query(func.coalesce(func.sum(models.UploadedFile.size_bytes), 0), func.count(models.UploadedFile.id))
        .filter(models.UploadedFile.owner_user_id == owner_user_id)
        .one()
    )
    return int(row[0] or 0), int(row[1] or 0)


def ensure_quota(db, owner_user_id: int, incoming_bytes: int) -> None:
    """용량을 넘기면 저장 전에 막는다. 디스크에 쓰고 나서 되돌리는 것보다 안전하다."""
    used_bytes, used_files = current_usage(db, owner_user_id)
    max_bytes, max_files = quota_bytes_per_user(), quota_files_per_user()

    if used_files + 1 > max_files:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"업로드 파일 수 한도({max_files}개)를 초과했습니다. 오래된 파일이 정리되면 다시 올릴 수 있습니다.",
        )
    if used_bytes + incoming_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"업로드 용량 한도({max_bytes // (1024 * 1024)}MB)를 초과했습니다. "
                   f"현재 {used_bytes // (1024 * 1024)}MB 사용 중입니다.",
        )


def record_upload(
    db,
    *,
    stored_path: Path,
    original_name: str,
    owner_user_id: int,
    uploaded_by_user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    purpose: str = "node",
    content_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
):
    """업로드를 기록한다. 커밋은 호출부가 한다(요청 트랜잭션과 같이 묶기 위해서다).

    공개 식별자(`artifact_id`)와 내용 hash(`sha256`)는 여기서 함께 남긴다(ADR-0018) — 업로드가
    들어오는 경로가 여럿이라(에디터 노드·챗봇 첨부·앱 입력·이미지 생성) 각 호출부에 맡기면
    한 경로만 빠져도 그 파일은 영원히 첨부할 수 없는 상태가 된다.
    """
    import hashlib
    import uuid as _uuid

    import models

    digest = hashlib.sha256()
    try:
        with stored_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        sha256 = digest.hexdigest()
    except OSError:
        # hash 를 못 구해도 기록은 남긴다. 그 경우 전송 직전 검증이 크기 비교로 내려간다.
        sha256 = None

    now = datetime.datetime.utcnow()
    record = models.UploadedFile(
        stored_name=stored_path.name,
        artifact_id=_uuid.uuid4().hex,
        original_name=original_name,
        owner_user_id=owner_user_id,
        uploaded_by_user_id=uploaded_by_user_id,
        project_id=project_id,
        purpose=purpose,
        size_bytes=size_bytes if size_bytes is not None else stored_path.stat().st_size,
        content_type=content_type,
        sha256=sha256,
        created_at=now,
        expires_at=now + datetime.timedelta(days=retention_days()),
    )
    db.add(record)
    return record


def purge_expired_uploads(db, *, now: Optional[datetime.datetime] = None, limit: int = 500) -> dict:
    """보존 기간이 지난 업로드를 지운다.

    ⚠️ 기록이 없는 파일(이 기능 도입 전에 올라온 것)은 건드리지 않는다. 소유자를 알 수 없는
    파일을 추측해서 지우면 사용자의 워크플로우가 참조하던 결과물이 조용히 사라진다.
    """
    import models

    now = now or datetime.datetime.utcnow()
    expired = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.expires_at.isnot(None), models.UploadedFile.expires_at <= now)
        .limit(limit)
        .all()
    )

    removed_files = 0
    removed_bytes = 0
    for record in expired:
        path = UPLOAD_DIR / record.stored_name
        try:
            if path.is_file():
                path.unlink()
                removed_files += 1
                removed_bytes += record.size_bytes or 0
        except OSError as exc:
            # 파일을 못 지웠으면 기록도 남겨둔다 — 지워진 척하고 용량만 비면 실제 사용량과 어긋난다.
            print(f"[uploads] {record.stored_name} 삭제 실패, 기록 유지: {exc}")
            continue
        db.delete(record)

    db.commit()
    return {"checked": len(expired), "removed_files": removed_files, "removed_bytes": removed_bytes}


# ── 워크플로우가 파일을 읽을 때의 경로 검증 ────────────────────────────
class UnsafeUploadPath(ValueError):
    """업로드 디렉터리 밖이거나 허용되지 않는 파일. 호출부가 자기 오류 형식으로 감싼다."""


def resolve_stored_path(
    raw_path: str,
    *,
    allowed_extensions: Collection[str],
    max_bytes: int,
    upload_root: Optional[Path] = None,
) -> Path:
    """워크플로우 노드가 넘겨받은 파일 경로를 검증해서 실제 경로로 바꾼다.

    경로는 대개 앞 노드가 만들었거나 LLM 이 채운 문자열이다. 검증 없이 열면 `/etc/passwd`
    같은 서버 파일이 외부로 업로드되거나 첨부될 수 있다 — 되돌릴 수 없는 동작이라 실행 전에 막는다.
    (원래 YouTube 노드 안에만 있던 검사를 파일을 다루는 노드가 공유하도록 올렸다.)
    """
    if not raw_path or not str(raw_path).strip():
        raise UnsafeUploadPath("파일 경로가 비어 있다")

    root = (upload_root or Path(os.getenv("UPLOAD_DIR", str(UPLOAD_DIR)))).resolve()
    candidate = Path(str(raw_path).strip()).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError:
        raise UnsafeUploadPath(f"업로드 디렉터리 밖의 경로는 쓸 수 없다: {raw_path}") from None

    if resolved.suffix.lower() not in allowed_extensions:
        raise UnsafeUploadPath(
            f"허용되지 않는 확장자다({resolved.suffix or '없음'}). 허용: {', '.join(sorted(allowed_extensions))}"
        )
    if not resolved.is_file():
        raise UnsafeUploadPath(f"파일이 없다: {raw_path}")

    size = resolved.stat().st_size
    if size == 0:
        raise UnsafeUploadPath("빈 파일은 쓸 수 없다")
    if size > max_bytes:
        raise UnsafeUploadPath(f"파일이 한도({max_bytes // (1024 * 1024)}MB)를 넘는다")
    return resolved
