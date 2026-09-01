"""artifacts.py — 첨부 전송의 공통 ArtifactRef 조회 서비스 (ADR-0018, 우선 백로그 20 FILE-SEND-0).

예전에는 발송 노드가 앞 노드의 **결과 문자열에서 `uploads/...` 를 정규식으로 찾아** 그 경로를
그대로 열었다. 그건 파일 전송 계약이 아니라 경로 문자열 추측이라, 생성 노드의 출력 모양이
바뀌거나 실행 작업 디렉터리가 달라지면 조용히 동작을 멈췄고, 무엇보다 **누구 파일인지 확인하지
않았다**(`os.path.exists` 하나가 전부였다).

이 모듈이 그 자리를 대신한다. 외부 계약은 `ArtifactRef` 하나이고, 안에서만 저장 테이블별
adapter 를 쓴다:

  - `uploaded_files`  — 인증된 업로드, 생성 이미지, 포스터, 문서 결과가 모두 여기 등록된다(정본).
  - `image_artifacts` — 이미지 생성의 버전 기록. `artifact_id` 로 들어오면 같은 파일의 업로드 행으로
                        되돌려 준다(두 id 체계를 호출부가 알 필요가 없다).

`resolve()` 는 소유자·프로젝트·TTL·저장 루트·심볼릭 링크·정규 파일·크기·MIME·hash 를 **전부 통과한
뒤에만** 읽기 stream 을 연다. 실패는 ARTIFACT_* typed error 다(error_catalog.json).

경로·저장 이름은 이 모듈 밖으로 나가지 않는다. 나가는 것은 `artifact_id` 와 정규화된 표시 이름뿐이다.
"""

from __future__ import annotations

import datetime
import hashlib
import mimetypes
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from node_errors import NodeError, NodeErrorException, make_error

# 저장 루트. upload_security 와 같은 값을 읽는다 — 두 곳이 어긋나면 한쪽이 통과시킨 경로를
# 다른 쪽이 거부하는 상태가 된다.
DEFAULT_UPLOAD_DIR = "uploads"

# kind 는 사용자·정책이 보는 분류다. connector 정책이 "이미지만" 같은 제한을 걸 때 쓴다.
KIND_IMAGE = "image"
KIND_DOCUMENT = "document"
KIND_PDF = "pdf"
KIND_ARCHIVE = "archive"
KIND_OTHER = "other"
ARTIFACT_KINDS = (KIND_IMAGE, KIND_DOCUMENT, KIND_PDF, KIND_ARCHIVE, KIND_OTHER)

# 형식을 확정하지 못한 파일. 채널은 이 값을 인라인으로 렌더하지 않는다.
GENERIC_MIME = "application/octet-stream"

_KIND_BY_EXTENSION = {
    ".png": KIND_IMAGE, ".jpg": KIND_IMAGE, ".jpeg": KIND_IMAGE, ".gif": KIND_IMAGE,
    ".webp": KIND_IMAGE, ".bmp": KIND_IMAGE, ".svg": KIND_IMAGE,
    ".pdf": KIND_PDF,
    ".doc": KIND_DOCUMENT, ".docx": KIND_DOCUMENT, ".hwp": KIND_DOCUMENT, ".hwpx": KIND_DOCUMENT,
    ".txt": KIND_DOCUMENT, ".md": KIND_DOCUMENT, ".csv": KIND_DOCUMENT, ".json": KIND_DOCUMENT,
    ".ppt": KIND_DOCUMENT, ".pptx": KIND_DOCUMENT, ".xls": KIND_DOCUMENT, ".xlsx": KIND_DOCUMENT,
    ".zip": KIND_ARCHIVE, ".tar": KIND_ARCHIVE, ".gz": KIND_ARCHIVE, ".7z": KIND_ARCHIVE,
}

# 확장자만 믿지 않는다(§4.10 범위 원칙). 실제 파일 앞부분의 signature 로 한 번 더 확인한다 —
# `.png` 로 저장된 HTML 이나 실행 파일이 이미지로 통과하면 안 된다.
_MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),   # docx/xlsx/pptx/hwpx/zip 공통
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/x-ole-storage"),  # doc/xls/ppt/hwp
)
_RIFF_WEBP = (b"RIFF", b"WEBP")

# 파일명 정규화: 경로 구분자·제어문자·개행은 제거한다. 개행 하나가 남으면 MIME
# `Content-Disposition` 헤더에 줄이 하나 더 생긴다(header injection).
_UNSAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\\r\n\"]+")
_MAX_FILENAME_LENGTH = 120

# `uploads/...` 문자열 → 등록된 artifact 로 되돌리는 legacy adapter 가 쓰는 패턴
# (integration_nodes.py·discord_bot.py 의 예전 정규식과 같다).
LEGACY_UPLOAD_PATH_RE = re.compile(r"uploads/[^\s\"'<>]+")


def upload_root() -> Path:
    """허용 저장 루트. resolver 는 이 밖의 경로를 절대 열지 않는다."""
    return Path(os.getenv("UPLOAD_DIR", DEFAULT_UPLOAD_DIR)).resolve()


class ArtifactError(NodeErrorException):
    """ARTIFACT_* typed error 를 담은 예외. 호출부(발송 adapter)가 NodeResult 로 감싼다."""


def _fail(code: str, *, artifact_id: Optional[str] = None, index: Optional[int] = None,
          node_type: Optional[str] = None, node_id: Optional[str] = None,
          internal: Any = None, **details) -> "ArtifactError":
    safe: Dict[str, Any] = dict(details)
    if artifact_id:
        # 식별자는 사용자가 UI 에서 보는 값이라 그대로 남긴다 — 경로·저장 이름과 달리 비밀이 아니다.
        safe["artifactId"] = artifact_id
    if index is not None:
        safe["attachmentIndex"] = index
    return ArtifactError(make_error(
        code, effect_state="not_started", safe_details=safe,
        node_type=node_type, node_id=node_id, internal_message=internal,
    ))


def safe_filename(raw: str | None, *, fallback_extension: str = "") -> str:
    """전송에 쓸 표시 이름. 경로 문자·제어문자를 없애고 길이를 자른다.

    원본 이름은 사용자가 올린 값이거나 LLM 이 지은 값이라 그대로 헤더에 넣으면 안 된다.
    """
    name = unicodedata.normalize("NFC", str(raw or "").strip())
    name = os.path.basename(name.replace("\\", "/"))
    name = _UNSAFE_FILENAME_CHARS.sub("", name).strip(" .")
    if not name or name in {".", ".."}:
        name = f"attachment{fallback_extension}"
    if len(name) > _MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and len(extension) <= 12:
            keep = _MAX_FILENAME_LENGTH - len(extension) - 1
            name = f"{stem[:keep]}.{extension}"
        else:
            name = name[:_MAX_FILENAME_LENGTH]
    return name


def kind_for(filename: str, mime_type: str | None = None) -> str:
    """사용자·정책이 보는 분류. 형식을 확정하지 못한 파일은 `other` 로 남는다.

    확장자보다 MIME 이 우선이다 — `.png` 라는 이름이 붙었어도 실제 형식이 이미지가 아니면
    이미지라고 부르지 않는다(정책의 "이미지만" 제한이 그 이름을 믿으면 안 된다).
    """
    mime = (mime_type or "").lower()
    if mime == GENERIC_MIME:
        # 실제 signature 로 확정하지 못했다는 뜻이다. 확장자만 보고 되돌리면 위장 파일이 통과한다.
        return KIND_OTHER
    if mime.startswith("image/"):
        return KIND_IMAGE
    if mime == "application/pdf":
        return KIND_PDF
    extension = Path(filename or "").suffix.lower()
    if extension in _KIND_BY_EXTENSION:
        return _KIND_BY_EXTENSION[extension]
    if mime.startswith("text/"):
        return KIND_DOCUMENT
    return KIND_OTHER


def guess_mime_type(filename: str, declared: str | None = None) -> str:
    if declared and "/" in declared:
        return declared.split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(filename or "")
    return (guessed or GENERIC_MIME).lower()


def sniff_mime_type(path: Path) -> Optional[str]:
    """파일 앞부분의 signature 로 본 실제 형식. 판단할 수 없으면 None."""
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return None
    if head[:4] == _RIFF_WEBP[0] and head[8:12] == _RIFF_WEBP[1]:
        return "image/webp"
    for signature, mime in _MAGIC_SIGNATURES:
        if head.startswith(signature):
            return mime
    return None


# 확장자로 "선언"된 형식과 실제 signature 가 어긋날 때의 판단. 채널이 인라인으로 렌더하는
# 형식(이미지·PDF)일수록 선언을 믿으면 안 된다 — `.png` 로 올린 HTML 이 이미지 자리에 들어가면
# 받는 쪽에서 무엇으로 처리될지 우리가 통제할 수 없다.
_SNIFF_AMBIGUOUS = {"application/zip", "application/x-ole-storage"}
_INLINE_RENDERED_PREFIXES = ("image/", "video/", "audio/")


def _effective_mime(path: Path, declared: str) -> str:
    sniffed = sniff_mime_type(path)
    if sniffed and sniffed not in _SNIFF_AMBIGUOUS:
        return sniffed
    if sniffed in _SNIFF_AMBIGUOUS:
        # zip/OLE 컨테이너는 docx·xlsx·hwpx·pptx 를 전부 포함해 signature 로 더 좁힐 수 없다.
        # 이 경우에만 선언 값을 유지한다.
        return declared
    # signature 를 알아보지 못했는데 선언은 인라인 렌더 형식이면 일반 바이너리로 낮춘다.
    if any((declared or "").startswith(prefix) for prefix in _INLINE_RENDERED_PREFIXES):
        return GENERIC_MIME
    return declared


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ArtifactRef:
    """§4.10 목표 계약의 `ArtifactRef`. 경로·저장 이름은 `_stored_name` 으로만 갖고 밖으로 내보내지 않는다."""

    artifact_id: str
    owner_user_id: int
    project_id: Optional[int]
    kind: str
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: Optional[str]
    created_at: Optional[datetime.datetime]
    expires_at: Optional[datetime.datetime]
    source: str = "upload"
    purpose: Optional[str] = None
    _stored_name: str = ""

    def to_public_dict(self) -> Dict[str, Any]:
        """UI·실행 로그로 나가는 모양. 저장 이름과 경로는 들어가지 않는다."""
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind,
            "filename": self.original_name,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
        }

    @property
    def expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= datetime.datetime.utcnow())


# ── 등록 ────────────────────────────────────────────────────────────────
def new_artifact_id() -> str:
    return uuid.uuid4().hex


def register_generated_file(
    db,
    *,
    path: str | Path,
    owner_user_id: int,
    project_id: Optional[int] = None,
    purpose: str = "generated",
    original_name: Optional[str] = None,
    content_type: Optional[str] = None,
    commit: bool = True,
) -> Optional[ArtifactRef]:
    """포스터·문서 등 **생성 노드가 만든 파일**을 artifact 로 등록한다(FILE-SEND-0 ②).

    예전에는 이런 파일이 디스크에만 생기고 어떤 기록도 남지 않아서, 소유자·만료를 확인할 방법이
    없었고 정리 작업도 손대지 못했다. 등록 실패는 생성 자체를 실패시키지 않는다 — 파일은 이미
    만들어졌고, 등록이 없으면 첨부만 못 할 뿐이다.
    """
    try:
        import models

        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = (upload_root() / Path(path).name).resolve()
        if not resolved.is_file():
            return None

        existing = (
            db.query(models.UploadedFile)
            .filter(models.UploadedFile.stored_name == resolved.name)
            .first()
        )
        # 같은 stored_name 의 행이 **다른 사용자** 것이면 건드리지 않는다. stored_name 은 output_path
        # 에서 오고 사용자가 고정할 수 있어(uploads/서식.hwpx), 남의 파일명과 충돌시키면 예전에는
        # 그 행의 size·hash 를 덮어쓰고 남의 artifact_id 를 이 호출자에게 돌려줬다 — 남의 파일을
        # 자기 산출물로 첨부할 수 있는 경로였다. 등록을 포기한다(파일은 이미 디스크에 있고,
        # 등록이 없으면 첨부만 못 할 뿐이다).
        if existing is not None and (owner_user_id or 0) not in (existing.owner_user_id, 0):
            return None
        size_bytes = resolved.stat().st_size
        digest = sha256_of(resolved)
        display_name = safe_filename(original_name or resolved.name, fallback_extension=resolved.suffix)
        mime_type = guess_mime_type(display_name, content_type)

        if existing:
            # 같은 경로에 다시 렌더한 경우(output_path 를 사용자가 고정한 그래프). 내용이 바뀌었으니
            # hash·크기를 새로 맞춘다 — 안 그러면 전송 직전 hash 검증이 자기 파일을 거부한다.
            existing.size_bytes = size_bytes
            existing.sha256 = digest
            if not existing.artifact_id:
                existing.artifact_id = new_artifact_id()
            record = existing
        else:
            now = datetime.datetime.utcnow()
            from upload_security import retention_days

            record = models.UploadedFile(
                stored_name=resolved.name,
                artifact_id=new_artifact_id(),
                original_name=display_name,
                owner_user_id=owner_user_id or 0,
                uploaded_by_user_id=None,
                project_id=project_id,
                purpose=purpose,
                size_bytes=size_bytes,
                content_type=mime_type,
                sha256=digest,
                created_at=now,
                expires_at=now + datetime.timedelta(days=retention_days()),
            )
            db.add(record)

        if commit:
            db.commit()
        else:
            db.flush()
        return _ref_from_upload(record)
    except Exception as exc:  # 등록 실패가 생성 노드를 죽이지 않는다
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[artifacts] 생성 파일 등록 실패({path}): {exc}")
        return None


def ensure_artifact_id(db, record, *, commit: bool = True) -> str:
    """이 기능 도입 전에 올라온 행에 공개 식별자를 붙인다(마이그레이션 백필의 런타임 보완)."""
    if not record.artifact_id:
        record.artifact_id = new_artifact_id()
        if commit:
            db.commit()
    return record.artifact_id


# ── 조회 ────────────────────────────────────────────────────────────────
def _ref_from_upload(record, *, source: str = "upload") -> ArtifactRef:
    display_name = safe_filename(record.original_name or record.stored_name,
                                 fallback_extension=Path(record.stored_name or "").suffix)
    mime_type = guess_mime_type(display_name, record.content_type)
    return ArtifactRef(
        artifact_id=record.artifact_id or "",
        owner_user_id=int(record.owner_user_id or 0),
        project_id=record.project_id,
        kind=kind_for(display_name, mime_type),
        original_name=display_name,
        mime_type=mime_type,
        size_bytes=int(record.size_bytes or 0),
        sha256=record.sha256,
        created_at=record.created_at,
        expires_at=record.expires_at,
        source=source,
        purpose=record.purpose,
        _stored_name=record.stored_name,
    )


def _find_upload_record(db, artifact_id: str):
    """`artifact_id` 로 업로드 행을 찾는다. 이미지 생성의 artifact id 도 같은 파일로 이어준다."""
    import models

    record = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.artifact_id == artifact_id)
        .first()
    )
    if record:
        return record, "upload"

    image = (
        db.query(models.ImageArtifact)
        .filter(models.ImageArtifact.artifact_id == artifact_id)
        .first()
    )
    if image:
        record = (
            db.query(models.UploadedFile)
            .filter(models.UploadedFile.stored_name == image.stored_name)
            .first()
        )
        if record:
            return record, "image"
    return None, None


def lookup(db, artifact_id: str) -> Optional[ArtifactRef]:
    """검증 없이 메타데이터만 본다(Inspector 표시용). 전송 경로는 `resolve()` 를 쓴다."""
    if not artifact_id:
        return None
    record, source = _find_upload_record(db, str(artifact_id).strip())
    if not record:
        return None
    return _ref_from_upload(record, source=source or "upload")


def lookup_by_stored_path(db, raw_path: str) -> Optional[ArtifactRef]:
    """legacy `uploads/...` 문자열 → 등록된 artifact (FILE-SEND-2 ⑤).

    임의 로컬 경로를 열기 위한 통로가 아니다 — **등록된 파일로 역조회되는 경우에만** 값을 돌려주고,
    소유권 확인은 호출부의 `resolve()` 가 한다.
    """
    import models

    if not raw_path:
        return None
    name = os.path.basename(str(raw_path).replace("\\", "/").strip())
    if not name or name in {".", ".."}:
        return None
    record = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.stored_name == name)
        .first()
    )
    if not record:
        return None
    if not record.artifact_id:
        ensure_artifact_id(db, record)
    return _ref_from_upload(record)


def find_legacy_paths(text: str) -> List[str]:
    """결과 문자열에 남아 있는 `uploads/...` 후보들. 순서를 유지하고 중복은 없앤다."""
    seen: List[str] = []
    for match in LEGACY_UPLOAD_PATH_RE.findall(str(text or "")):
        if match not in seen:
            seen.append(match)
    return seen


@dataclass
class ResolvedArtifact:
    """검증을 통과한 artifact 와 그 실제 경로. 경로는 전송 adapter 안에서만 쓴다."""

    ref: ArtifactRef
    path: Path
    filename: str

    def open(self) -> BinaryIO:
        return self.path.open("rb")

    def read_bytes(self) -> bytes:
        with self.open() as handle:
            return handle.read()


def resolve(
    db,
    artifact_id: str,
    *,
    owner_user_id: int,
    project_id: Optional[int] = None,
    index: Optional[int] = None,
    node_type: Optional[str] = None,
    node_id: Optional[str] = None,
    require_project_match: bool = True,
    verify_hash: bool = True,
    allow_any_owner: bool = False,
) -> ResolvedArtifact:
    """소유·만료·저장 루트·심볼릭 링크·정규 파일·hash 를 전부 확인한 artifact.

    실패는 ARTIFACT_* 예외다. **외부 네트워크 호출 전에** 호출하는 것이 이 함수의 존재 이유다 —
    검증이 전송 뒤에 오면 남의 파일이 이미 나간 뒤가 된다.
    """
    fail = lambda code, **kw: _fail(code, artifact_id=artifact_id, index=index,
                                    node_type=node_type, node_id=node_id, **kw)

    identifier = str(artifact_id or "").strip()
    if not identifier:
        raise fail("ARTIFACT_NOT_FOUND", internal="빈 artifactId")

    record, source = _find_upload_record(db, identifier)
    if not record:
        raise fail("ARTIFACT_NOT_FOUND", internal="등록된 artifact 가 없다")

    ref = _ref_from_upload(record, source=source or "upload")

    # 소유권 — 다른 사용자의 파일은 어떤 경우에도 열지 않는다.
    #
    # `allow_any_owner` 는 **호출부가 다른 권한 근거를 이미 확인했을 때만** 쓴다. 지금은 커뮤니티
    # 글 이미지 한 곳이다 — 그 이미지를 볼 자격은 소유권이 아니라 **글의 공개 범위**가 정하고,
    # 그 판단은 `community_posts.can_view` 한 곳에서 이미 끝난 뒤에 여기로 온다. 기본값이 False 인
    # 이유는 이 통로가 실수로 열리면 남의 파일이 그대로 나가기 때문이다.
    if not allow_any_owner and int(ref.owner_user_id or 0) != int(owner_user_id or 0):
        raise fail("ARTIFACT_FORBIDDEN", internal="소유자 불일치")
    # 프로젝트 경계 — 프로젝트에 묶인 파일은 그 프로젝트의 실행에서만 쓴다. 프로젝트가 없는
    # 파일(챗봇 첨부 등)은 소유자만 맞으면 된다.
    if require_project_match and ref.project_id is not None and project_id is not None:
        if int(ref.project_id) != int(project_id):
            raise fail("ARTIFACT_FORBIDDEN", internal="프로젝트 불일치")
    if ref.expired:
        raise fail("ARTIFACT_EXPIRED", internal="보존 기간 경과")

    root = upload_root()
    candidate = root / (record.stored_name or "")
    # symlink 를 따라간 뒤의 경로가 루트 안이어야 한다. `resolve()` 는 링크를 모두 푼다.
    resolved_path = candidate.resolve()
    try:
        resolved_path.relative_to(root)
    except ValueError:
        raise fail("ARTIFACT_FORBIDDEN", internal="저장 루트 밖의 경로") from None
    if candidate.is_symlink():
        raise fail("ARTIFACT_FORBIDDEN", internal="심볼릭 링크는 전송하지 않는다")
    if not resolved_path.is_file():
        raise fail("ARTIFACT_NOT_FOUND", internal="파일이 디스크에 없다")

    actual_size = resolved_path.stat().st_size
    if actual_size <= 0:
        raise fail("ARTIFACT_NOT_FOUND", internal="빈 파일")

    # 등록 metadata 와 실제 파일이 어긋나면 보내지 않는다(§4.10 "등록 시점과 전송 직전에 검증").
    if ref.sha256 and verify_hash:
        if sha256_of(resolved_path) != ref.sha256:
            raise fail("ARTIFACT_NOT_FOUND", internal="등록 뒤 파일 내용이 바뀌었다")
    elif ref.size_bytes and actual_size != ref.size_bytes:
        raise fail("ARTIFACT_NOT_FOUND", internal="등록 크기와 실제 크기가 다르다")

    ref = ArtifactRef(**{**ref.__dict__,
                         "mime_type": _effective_mime(resolved_path, ref.mime_type),
                         "size_bytes": actual_size})
    ref = ArtifactRef(**{**ref.__dict__, "kind": kind_for(ref.original_name, ref.mime_type)})

    return ResolvedArtifact(ref=ref, path=resolved_path, filename=ref.original_name)


def list_for_project(db, *, owner_user_id: int, project_id: Optional[int] = None,
                     limit: int = 50) -> List[ArtifactRef]:
    """Inspector 의 파일 선택 목록. 만료된 것은 빼고 최근 것부터."""
    import models

    now = datetime.datetime.utcnow()
    query = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.owner_user_id == owner_user_id)
        .filter(models.UploadedFile.artifact_id.isnot(None))
        .filter((models.UploadedFile.expires_at.is_(None)) | (models.UploadedFile.expires_at > now))
    )
    if project_id is not None:
        query = query.filter(
            (models.UploadedFile.project_id == project_id) | (models.UploadedFile.project_id.is_(None))
        )
    rows = query.order_by(models.UploadedFile.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [_ref_from_upload(row) for row in rows]
