"""업로드 인증·용량·보존·경로 검증 (ADR-0010) 테스트."""

from __future__ import annotations

import datetime
import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import upload_security
from database import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([models.User(id=1, name="owner"), models.User(id=2, name="other")])
    db.commit()
    return db


def add_file(db, owner, size, *, name=None, expires_at=None, path=None):
    record = models.UploadedFile(
        stored_name=name or f"f{db.query(models.UploadedFile).count()}.pdf",
        original_name="doc.pdf", owner_user_id=owner, size_bytes=size,
        purpose="node", created_at=datetime.datetime.utcnow(), expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return record


# ── 용량 ───────────────────────────────────────────────────────────────
def test_usage_is_counted_per_owner():
    db = make_db()
    add_file(db, 1, 1000)
    add_file(db, 1, 2000)
    add_file(db, 2, 9999)
    assert upload_security.current_usage(db, 1) == (3000, 2)
    assert upload_security.current_usage(db, 2) == (9999, 1)


def test_byte_quota_blocks_before_writing(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("UPLOAD_QUOTA_BYTES_PER_USER", "5000")
    db = make_db()
    add_file(db, 1, 4500)

    upload_security.ensure_quota(db, 1, 400)          # 여유 안
    with pytest.raises(HTTPException) as caught:
        upload_security.ensure_quota(db, 1, 900)      # 초과
    assert caught.value.status_code == 413
    assert "용량 한도" in caught.value.detail


def test_file_count_quota_is_enforced(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("UPLOAD_QUOTA_FILES_PER_USER", "2")
    db = make_db()
    add_file(db, 1, 1)
    add_file(db, 1, 1)
    with pytest.raises(HTTPException) as caught:
        upload_security.ensure_quota(db, 1, 1)
    assert "파일 수 한도" in caught.value.detail


def test_quota_of_one_user_does_not_affect_another(monkeypatch):
    monkeypatch.setenv("UPLOAD_QUOTA_BYTES_PER_USER", "5000")
    db = make_db()
    add_file(db, 2, 4900)
    upload_security.ensure_quota(db, 1, 4000)  # 예외가 나면 실패


# ── 보존 ───────────────────────────────────────────────────────────────
def test_expired_uploads_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_security, "UPLOAD_DIR", tmp_path)
    db = make_db()
    past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    future = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    (tmp_path / "old.pdf").write_bytes(b"x" * 10)
    (tmp_path / "new.pdf").write_bytes(b"y" * 10)
    add_file(db, 1, 10, name="old.pdf", expires_at=past)
    add_file(db, 1, 10, name="new.pdf", expires_at=future)

    summary = upload_security.purge_expired_uploads(db)

    assert summary["removed_files"] == 1
    assert not (tmp_path / "old.pdf").exists()
    assert (tmp_path / "new.pdf").exists()
    assert db.query(models.UploadedFile).count() == 1


def test_untracked_files_are_never_touched(tmp_path, monkeypatch):
    """이 기능 도입 전에 올라온 파일은 소유자를 알 수 없다. 추측해서 지우면 사용자의
    워크플로우가 참조하던 결과물이 조용히 사라진다."""
    monkeypatch.setattr(upload_security, "UPLOAD_DIR", tmp_path)
    db = make_db()
    (tmp_path / "legacy.pdf").write_bytes("소중한 파일".encode())

    upload_security.purge_expired_uploads(db)

    assert (tmp_path / "legacy.pdf").exists()


def test_a_file_that_cannot_be_deleted_keeps_its_record(tmp_path, monkeypatch):
    """지워진 척하고 기록만 없애면 실제 디스크 사용량과 장부가 어긋난다."""
    monkeypatch.setattr(upload_security, "UPLOAD_DIR", tmp_path)
    db = make_db()
    past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    (tmp_path / "locked.pdf").write_bytes(b"x")
    add_file(db, 1, 1, name="locked.pdf", expires_at=past)

    def boom(self):
        raise OSError("권한 없음")

    monkeypatch.setattr(pathlib.Path, "unlink", boom)
    upload_security.purge_expired_uploads(db)
    assert db.query(models.UploadedFile).count() == 1


def test_record_sets_an_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_RETENTION_DAYS", "7")
    db = make_db()
    stored = tmp_path / "a.pdf"
    stored.write_bytes(b"x" * 5)
    record = upload_security.record_upload(
        db, stored_path=stored, original_name="a.pdf", owner_user_id=1, purpose="node"
    )
    db.commit()
    assert record.size_bytes == 5
    assert 6 < (record.expires_at - record.created_at).days <= 7


# ── 경로 검증 공용화 ───────────────────────────────────────────────────
def test_path_outside_the_upload_directory_is_rejected(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    outsider = tmp_path / "secret.pdf"
    outsider.write_bytes(b"x" * 10)

    for candidate in (str(outsider), "../secret.pdf", "/etc/passwd"):
        with pytest.raises(upload_security.UnsafeUploadPath):
            upload_security.resolve_stored_path(
                candidate, allowed_extensions={".pdf"}, max_bytes=1000, upload_root=root
            )


def test_allowlist_is_per_purpose(tmp_path):
    """문서 요약 앱에 실행 파일이 올라갈 이유가 없고, 반대로 영상은 문서 목록에 없다."""
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"v" * 10)

    with pytest.raises(upload_security.UnsafeUploadPath):
        upload_security.resolve_stored_path(
            "clip.mp4", allowed_extensions=upload_security.GENERAL_UPLOAD_EXTENSIONS,
            max_bytes=1000, upload_root=root,
        )
    resolved = upload_security.resolve_stored_path(
        "clip.mp4", allowed_extensions=upload_security.VIDEO_UPLOAD_EXTENSIONS,
        max_bytes=1000, upload_root=root,
    )
    assert resolved.name == "clip.mp4"


def test_empty_and_oversized_files_are_rejected(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "empty.pdf").write_bytes(b"")
    (root / "big.pdf").write_bytes(b"x" * 500)

    with pytest.raises(upload_security.UnsafeUploadPath):
        upload_security.resolve_stored_path("empty.pdf", allowed_extensions={".pdf"}, max_bytes=1000, upload_root=root)
    with pytest.raises(upload_security.UnsafeUploadPath):
        upload_security.resolve_stored_path("big.pdf", allowed_extensions={".pdf"}, max_bytes=100, upload_root=root)


def test_youtube_node_uses_the_shared_validator(tmp_path):
    """파일을 다루는 노드가 늘 때마다 같은 검사를 다시 짜지 않게 공용화했다."""
    from connectors.errors import ConnectorError
    from connectors.services import youtube

    root = tmp_path / "uploads"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"v" * 10)

    assert youtube.resolve_upload_path("clip.mp4", upload_root=root).name == "clip.mp4"
    with pytest.raises(ConnectorError):
        youtube.resolve_upload_path("../escape.mp4", upload_root=root)


# ── HTTP 경로 ──────────────────────────────────────────────────────────
SCENARIO = '''
import io, os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ["UPLOAD_QUOTA_FILES_PER_USER"] = "2"
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
owner = models.User(id=1, google_id="g1", email="o@e.st", name="owner")
db.add(owner)
db.add(models.Project(id=5, user_id=1, title="공개 앱", visibility="public", graph_data={"nodes": [], "edges": []}))
db.add(models.Project(id=6, user_id=1, title="비공개 앱", visibility="private", graph_data={"nodes": [], "edges": []}))
db.commit()

client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

def upload(data=None, token=False):
    headers = {}
    if token:
        main.app.dependency_overrides[main.get_current_user_required] = lambda: owner
        import jwt as _jwt
        headers["Authorization"] = "Bearer " + _jwt.encode({"user_id": 1}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
    return client.post("/api/upload", files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 hello"), "application/pdf")},
                       data=data or {}, headers=headers)

# 익명 + 프로젝트 정보 없음 -> 거부
r = upload()
check("익명 업로드 거부", r.status_code == 401, r.text)

# 익명 + 비공개 프로젝트 -> 거부 (남의 용량 소모 방지)
r = upload({"project_id": "6"})
check("비공개 앱으로 익명 업로드 거부", r.status_code == 401, r.text)

# 익명 + 공개 프로젝트 -> 허용, 소유자 몫으로 기록
r = upload({"project_id": "5", "purpose": "app"})
check("공개 앱에서 익명 업로드 허용", r.status_code == 200, r.text)
check("만료 시각이 응답에 있다", bool(r.json().get("expires_at")), r.text)

row = db.query(models.UploadedFile).order_by(models.UploadedFile.id.desc()).first()
db.refresh(row)
check("용량은 앱 소유자 몫", row.owner_user_id == 1, str(row.owner_user_id))
check("익명이라 업로더는 비어 있다", row.uploaded_by_user_id is None, str(row.uploaded_by_user_id))
check("용도가 기록된다", row.purpose == "app", row.purpose)

# 로그인 사용자 -> 본인 몫
r = upload(token=True)
check("로그인 업로드 허용", r.status_code == 200, r.text)
row = db.query(models.UploadedFile).order_by(models.UploadedFile.id.desc()).first()
check("업로더가 기록된다", row.uploaded_by_user_id == 1, str(row.uploaded_by_user_id))

# 파일 수 한도(2) 초과
r = upload(token=True)
check("파일 수 한도 초과 거부", r.status_code == 413, r.text)

# 한도로 거절된 요청이 디스크에 파일을 남기지 않았는지
stored = {f.stored_name for f in db.query(models.UploadedFile).all()}
on_disk = {p.name for p in __import__("pathlib").Path("uploads").glob("*.pdf")}
check("거절된 업로드가 디스크에 남지 않는다", on_disk <= stored, f"{on_disk - stored}")

# 사용량 조회
main.app.dependency_overrides[main.get_current_user_required] = lambda: owner
r = client.get("/api/uploads/usage")
check("사용량 조회", r.status_code == 200 and r.json()["used_files"] == 2, r.text)

# ── 용도별 허용 목록 (백로그 18: 파일 컴포넌트의 영상 업로드) ──
user2 = models.User(id=2, google_id="g2", email="v@e.st", name="video-user")
db.add(user2)
db.commit()
import jwt as _jwt
video_headers = {"Authorization": "Bearer " + _jwt.encode({"user_id": 2}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)}

def upload_as(name, content_type, data, headers):
    return client.post("/api/upload", files={"file": (name, io.BytesIO(b"x" * 64), content_type)},
                       data=data, headers=headers)

r = upload_as("clip.mp4", "video/mp4", {"purpose": "video"}, video_headers)
check("purpose=video 로 mp4 허용", r.status_code == 200, r.text)
row = db.query(models.UploadedFile).order_by(models.UploadedFile.id.desc()).first()
check("video 용도가 기록된다", row.purpose == "video", row.purpose)

r = upload_as("clip.mp4", "video/mp4", {"purpose": "app"}, video_headers)
check("일반 용도로는 mp4 거부", r.status_code == 415, r.text)

r = upload_as("doc.pdf", "application/pdf", {"purpose": "video"}, video_headers)
check("video 용도로는 pdf 거부", r.status_code == 415, r.text)

print("ALL OK")
'''


def test_upload_endpoint_authorization_and_quota(tmp_path):
    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")

    scenario = tmp_path / "scenario.py"
    scenario.write_text(SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()

    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'up.db'}", str(BACKEND_DIR)],
        cwd=workdir, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout


# ── _safe_user_path 소유권 (교차 사용자 파일 읽기 차단) ─────────────────────
# 예전에는 uploads/ 안이기만 하면 통과해, 예측 가능한 이름(uploads/서식.hwpx)으로 남의
# 생성·업로드 파일을 워크플로우에서 읽을 수 있었다. _safe_user_path 가 DB 소유권을 본다.

def _compiled_safe_user_path(db, owner_user_id, upload_dir):
    """생성 코드의 _safe_user_path 를 실제 러너와 같은 네임스페이스로 얻는다."""
    import json as _json
    import os
    import graph
    import node_generators  # noqa: F401

    os.environ["UPLOAD_DIR"] = str(upload_dir)
    src = graph.compile_workflow(
        [{"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}}],
        [],
    )
    ns = {"db": db, "models": models, "json": _json, "__owner_user_id__": owner_user_id}
    exec(compile(src, "<gen>", "exec"), ns)  # noqa: S102
    return ns["_safe_user_path"]


def test_safe_user_path_blocks_reading_another_users_file(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "shared_name.txt").write_text("owner 1 의 비밀", encoding="utf-8")

    db = make_db()
    add_file(db, owner=1, size=10, name="shared_name.txt")

    target = "uploads/shared_name.txt"
    monkeypatch.chdir(tmp_path)

    owner_path = _compiled_safe_user_path(db, 1, upload_dir)(target)
    assert owner_path is not None, "소유자 본인은 읽을 수 있어야 한다"

    stranger_path = _compiled_safe_user_path(db, 2, upload_dir)(target)
    assert stranger_path is None, "타인은 읽을 수 없어야 한다"

    anon_path = _compiled_safe_user_path(db, None, upload_dir)(target)
    assert anon_path is None, "익명은 남의 파일을 읽을 수 없어야 한다"


def test_safe_user_path_allows_unregistered_paths(tmp_path, monkeypatch):
    """DB 에 없는 경로(생성 직전 임시 등)는 종전대로 경로 가둠만 적용한다 — 소유권을 물을
    대상이 없으므로 막지 않는다."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "scratch.txt").write_text("x", encoding="utf-8")

    db = make_db()
    monkeypatch.chdir(tmp_path)

    path = _compiled_safe_user_path(db, 1, upload_dir)("uploads/scratch.txt")
    assert path is not None


def test_safe_user_path_still_rejects_paths_outside_uploads(tmp_path, monkeypatch):
    """소유권 검사를 더해도 경로 탈출 방어는 그대로다."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    db = make_db()
    monkeypatch.chdir(tmp_path)

    fn = _compiled_safe_user_path(db, 1, upload_dir)
    assert fn("../../../etc/passwd") is None
    assert fn("uploads/../../secret") is None
