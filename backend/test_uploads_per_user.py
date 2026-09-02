"""업로드·생성 파일의 소유자별 물리 분리 (per-user 디렉토리) 회귀 테스트.

계약: **공개 문자열(`uploads/<이름>`)·stored_name·서빙 URL 은 그대로**, 물리 위치만
`uploads/u<owner_id>/<이름>` 으로 나뉜다. 디스크를 여는 쪽은 전부 "(소유자, 이름) →
소유자 디렉토리 우선, 없으면 레거시 루트" 리졸버를 거친다. 이관 전 파일(레거시 루트)도
계속 열려야 한다 — 서버의 기존 파일 이동은 별도 스크립트(scripts/server/07)가 한다.
"""

from __future__ import annotations

import datetime
import json as _json
import os
import pathlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import artifacts
import models
import upload_security
from database import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
)


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([models.User(id=1, name="owner"), models.User(id=2, name="other")])
    db.commit()
    return db


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    return root


# ── 경로 헬퍼 ──────────────────────────────────────────────────────────
def test_stored_file_path_prefers_owner_dir_and_falls_back_to_legacy_root(uploads):
    (uploads / "u1").mkdir()
    (uploads / "u1" / "a.txt").write_text("mine", encoding="utf-8")
    (uploads / "legacy.txt").write_text("old", encoding="utf-8")

    assert upload_security.stored_file_path("a.txt", 1) == uploads / "u1" / "a.txt"
    # 이관 전 파일: 소유자 디렉토리에 없으면 레거시 루트
    assert upload_security.stored_file_path("legacy.txt", 1) == uploads / "legacy.txt"
    # 소유자 미상(0/None)은 늘 루트
    assert upload_security.stored_file_path("legacy.txt", 0) == uploads / "legacy.txt"


def test_physical_output_path_creates_owner_dir_and_strips_public_prefix(uploads):
    out = upload_security.physical_output_path("uploads/보고서.hwpx", 7)
    assert pathlib.Path(out) == uploads / "u7" / "보고서.hwpx"
    assert (uploads / "u7").is_dir()
    # 소유자를 모르면 레거시 루트에 쓴다
    anon = upload_security.physical_output_path("이름만.txt", None)
    assert pathlib.Path(anon) == uploads / "이름만.txt"


# ── 같은 이름, 다른 사용자 ─────────────────────────────────────────────
def test_register_generated_file_same_name_two_users_both_register(uploads):
    """예전 평면 디렉토리에서는 남의 행과 이름이 겹치면 두 번째 사용자가 등록을 포기해야
    했다(하이재킹 가드). 소유자 디렉토리로 갈라진 뒤에는 각자 자기 행을 갖는다."""
    db = make_db()
    for owner in (1, 2):
        p = pathlib.Path(upload_security.physical_output_path("uploads/서식.png", owner))
        p.write_bytes(PNG_BYTES + str(owner).encode())

    ref1 = artifacts.register_generated_file(db, path="uploads/서식.png", owner_user_id=1, purpose="generated")
    ref2 = artifacts.register_generated_file(db, path="uploads/서식.png", owner_user_id=2, purpose="generated")
    assert ref1 is not None and ref2 is not None
    assert ref1.artifact_id != ref2.artifact_id

    # 각자 resolve 하면 각자 디렉토리의 자기 파일이 열린다.
    r1 = artifacts.resolve(db, ref1.artifact_id, owner_user_id=1, require_project_match=False)
    r2 = artifacts.resolve(db, ref2.artifact_id, owner_user_id=2, require_project_match=False)
    assert r1.path == (uploads / "u1" / "서식.png").resolve()
    assert r2.path == (uploads / "u2" / "서식.png").resolve()
    assert r1.read_bytes().endswith(b"1") and r2.read_bytes().endswith(b"2")


def test_register_generated_file_still_refuses_foreign_legacy_root_file(uploads):
    """레거시 루트의 파일에 남의 행만 있으면 등록을 포기한다 — 그 물리 파일은 남의 것일 수
    있고, 등록하면 resolve() 가 그 파일을 이 호출자에게 열어 준다(기존 하이재킹 가드 유지)."""
    db = make_db()
    (uploads / "legacy_name.png").write_bytes(PNG_BYTES)
    first = artifacts.register_generated_file(db, path="uploads/legacy_name.png", owner_user_id=1, purpose="generated")
    assert first is not None
    hijack = artifacts.register_generated_file(db, path="uploads/legacy_name.png", owner_user_id=2, purpose="generated")
    assert hijack is None


def test_resolve_falls_back_to_legacy_root_before_migration(uploads):
    """서버에서 파일 이동 스크립트를 아직 안 돌렸어도(레거시 루트) 전송은 계속돼야 한다."""
    db = make_db()
    (uploads / "old.png").write_bytes(PNG_BYTES)
    ref = artifacts.register_generated_file(db, path="uploads/old.png", owner_user_id=1, purpose="generated")
    assert ref is not None
    resolved = artifacts.resolve(db, ref.artifact_id, owner_user_id=1, require_project_match=False)
    assert resolved.path == (uploads / "old.png").resolve()


# ── 보존 정리 ──────────────────────────────────────────────────────────
def test_purge_removes_expired_file_from_owner_dir(uploads):
    db = make_db()
    p = uploads / "u1" / "만료.txt"
    p.parent.mkdir()
    p.write_text("x", encoding="utf-8")
    record = models.UploadedFile(
        stored_name="만료.txt", original_name="만료.txt", owner_user_id=1, size_bytes=1,
        purpose="node", created_at=datetime.datetime.utcnow(),
        expires_at=datetime.datetime.utcnow() - datetime.timedelta(days=1),
    )
    db.add(record)
    db.commit()

    report = upload_security.purge_expired_uploads(db)
    assert report["removed_files"] == 1
    assert not p.exists()


# ── 생성 코드의 읽기(_safe_user_path)·쓰기(_user_output_path) ────────────
def _compiled_helpers(db, owner_user_id, upload_dir):
    import graph
    import node_generators  # noqa: F401

    os.environ["UPLOAD_DIR"] = str(upload_dir)
    src = graph.compile_workflow(
        [{"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}}], [],
    )
    ns = {"db": db, "models": models, "json": _json, "__owner_user_id__": owner_user_id}
    exec(compile(src, "<gen>", "exec"), ns)  # noqa: S102
    return ns["_safe_user_path"], ns["_user_output_path"]


def test_safe_user_path_maps_public_string_to_owner_dir(uploads):
    (uploads / "u1").mkdir()
    (uploads / "u1" / "내파일.txt").write_text("mine", encoding="utf-8")
    db = make_db()

    safe, _ = _compiled_helpers(db, 1, uploads)
    resolved = safe("uploads/내파일.txt")
    assert resolved is not None and resolved == (uploads / "u1" / "내파일.txt").resolve()


def test_safe_user_path_blocks_another_users_directory(uploads):
    (uploads / "u2").mkdir()
    (uploads / "u2" / "남의것.txt").write_text("secret", encoding="utf-8")
    db = make_db()

    safe, _ = _compiled_helpers(db, 1, uploads)
    # 직접 경로로 남의 디렉토리를 가리켜도, 공개 문자열로 남의 이름을 가리켜도 열리지 않는다.
    assert safe("uploads/u2/남의것.txt") is None
    assert safe("uploads/남의것.txt") is None or not safe("uploads/남의것.txt").is_file()


def test_user_output_path_writes_under_owner_dir(uploads):
    db = make_db()
    _, out = _compiled_helpers(db, 1, uploads)
    path = out("uploads/결과.hwpx")
    assert pathlib.Path(path) == uploads / "u1" / "결과.hwpx"
    assert (uploads / "u1").is_dir()


# ── 런타임 쓰기 지점 ────────────────────────────────────────────────────
def test_hwpx_runtime_writes_into_owner_dir_but_reports_public_path(uploads):
    hwpx_runtime = pytest.importorskip("documents.hwpx_runtime")
    db = make_db()
    spec = {"title": "테스트문서", "blocks": [{"type": "paragraph", "text": "본문"}]}
    result = hwpx_runtime.create(spec, output_path="uploads/문서.hwpx", db=db, owner_user_id=1)
    assert result["path"] == "uploads/문서.hwpx"           # 공개 문자열 유지
    assert (uploads / "u1" / "문서.hwpx").is_file()          # 물리 파일은 소유자 디렉토리
    assert not (uploads / "문서.hwpx").exists()
