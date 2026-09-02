"""documents/hwpx_runtime.py — `hwpxDocumentNode` 의 실제 동작 (계획 §3.2).

생성 코드에는 이 모듈을 한 번 부르는 것만 남긴다. 예전 문서 노드들이 zipfile·XML 조작을
문자열로 조립해 두는 바람에 **단위 테스트가 불가능했던 것**을 반복하지 않기 위해서다.

세 가지 모드가 있고 셋 다 외부로 나가지 않는다(`sideEffect: none`).

    create     직전 노드가 준 DocumentSpec(JSON) 으로 새 .hwpx 를 만든다
    inspect    기존 .hwpx 의 자리표시자와 구조를 알려준다
    validate   열리는 상태인지 검사한다(안전 검사 + 패키지 규칙)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, Optional

from . import hwpx

MODES = ("create", "inspect", "validate")

# 파일 이름에 쓰면 곤란한 것들. 경로 조작을 막는 것이 목적이라 넉넉히 지운다.
_UNSAFE_NAME = re.compile(r"[^0-9A-Za-z가-힣 ._-]+")


class HwpxNodeError(ValueError):
    """노드 실행을 멈춘다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


def _spec_from(value: Any) -> Dict[str, Any]:
    """직전 노드 출력에서 DocumentSpec 을 꺼낸다. LLM 출력이라 코드펜스가 붙어 오기도 한다."""
    if isinstance(value, dict):
        return value
    text = "" if value is None else str(value).strip()
    if not text:
        raise HwpxNodeError(
            "만들 문서 내용(DocumentSpec JSON)이 없습니다. 이 노드 앞에 JSON 을 만들어 주는 "
            "노드를 연결해주세요.",
            reason="HWPX_NO_SPEC",
        )
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except ValueError:
        raise HwpxNodeError(
            "만들 문서 내용을 JSON 으로 읽지 못했습니다. 앞 노드가 DocumentSpec JSON 을 "
            "내도록 해주세요.",
            reason="HWPX_SPEC_NOT_JSON",
        ) from None
    if not isinstance(parsed, dict):
        raise HwpxNodeError("DocumentSpec 은 객체여야 합니다.", reason="HWPX_SPEC_NOT_JSON")
    return parsed


def default_output_path(spec: Dict[str, Any]) -> str:
    """제목을 따서 이름을 짓는다. 실행마다 겹치지 않게 짧은 임의 문자열을 붙인다."""
    title = str(spec.get("title") or "문서").strip() or "문서"
    safe = _UNSAFE_NAME.sub("", title).strip() or "문서"
    return f"uploads/{safe[:40]}_{uuid.uuid4().hex[:6]}.hwpx"


def normalize_path(path: str) -> str:
    """받은 것을 **파일 이름**으로 보고 uploads/ 밑에 둔다.

    경로를 그대로 쓰지 않는 이유는 둘이다 — 노드가 서버 아무 곳에나 쓰지 못하게 하는 것과,
    사용자가 서버 경로를 알 필요가 없게 하는 것이다.
    """
    name = os.path.basename(str(path or "").replace("\\", "/"))
    if not name:
        raise HwpxNodeError("파일 이름이 비어 있습니다.", reason="HWPX_BAD_PATH")
    return "uploads/" + name


def resolve_source(db, artifact_id: str, *, owner_user_id: Optional[int],
                   project_id: Optional[int] = None) -> str:
    """살펴볼 파일의 실제 경로. **소유·만료·경로·해시를 artifacts.resolve 가 검증한다.**

    사용자가 경로를 직접 적게 두면 (1) 서버 경로를 알아야 하고 (2) 남의 파일을 가리킬 수 있다.
    Artifact id 로 받으면 둘 다 없어진다(ADR-0018).
    """
    import artifacts

    if not artifact_id:
        raise HwpxNodeError(
            "살펴볼 파일이 없습니다. 앞 노드가 만든 .hwpx 를 연결하거나 파일을 직접 골라주세요.",
            reason="HWPX_NO_SOURCE",
        )
    if db is None:
        raise HwpxNodeError("이 실행에서는 파일을 열 수 없습니다.", reason="HWPX_NO_SOURCE")
    resolved = artifacts.resolve(
        db, str(artifact_id), owner_user_id=owner_user_id or 0,
        project_id=project_id, node_type="hwpxDocumentNode", require_project_match=False,
    )
    return str(resolved.path)


def _image_loader(db, owner_user_id: Optional[int]):
    """DocumentSpec 의 `artifactId` 를 실제 바이트로 바꾼다. 경로·URL 은 받지 않는다(§3.3)."""
    if db is None:
        return None

    def load(artifact_id: str):
        import artifacts

        # lookup()이 주는 ArtifactRef 에는 경로가 없다(공개 봉투) — 예전 코드는 존재하지 않는
        # .path/.stored_path 속성을 getattr 로 더듬어 항상 None 이 됐고, 이미지가 든 문서
        # 생성이 전부 "이미지 파일이 없습니다" 로 죽었다(PR #41 리뷰). resolve() 가 소유·만료·
        # 경로·hash 검증과 소유자 디렉토리 해석을 전부 해 주므로 그 경로를 쓴다.
        try:
            resolved = artifacts.resolve(
                db, artifact_id, owner_user_id=owner_user_id or 0,
                node_type="hwpxDocumentNode", require_project_match=False,
            )
        except artifacts.ArtifactError as exc:
            raise hwpx.SpecError(f"이미지를 열 수 없습니다({artifact_id}): {exc.error.user_message}") from None
        return resolved.read_bytes(), resolved.path.suffix

    return load


# ── 모드 ────────────────────────────────────────────────────────────────

def create(spec_source: Any, *, output_path: str = "", db=None,
           owner_user_id: Optional[int] = None) -> Dict[str, Any]:
    spec = _spec_from(spec_source)
    target = normalize_path(output_path) if output_path else default_output_path(spec)
    # 물리 파일은 소유자 디렉토리(uploads/u<id>/) 밑에 쓴다. 결과의 'path' 는 계속 공개
    # 형태(uploads/<이름>)를 돌려준다 — 프론트 링크·legacy 정규식·서빙 URL 계약이 그 형태고,
    # 등록(register_generated_file)·다음 노드의 읽기(_safe_user_path)가 소유자 디렉토리로 푼다.
    from upload_security import physical_output_path

    physical = physical_output_path(target, owner_user_id)
    try:
        info = hwpx.build(spec, physical, image_loader=_image_loader(db, owner_user_id))
    except hwpx.UnsupportedFeature as exc:
        raise HwpxNodeError(str(exc), reason="HWPX_UNSUPPORTED_FEATURE") from None
    except hwpx.SpecError as exc:
        raise HwpxNodeError(str(exc), reason="HWPX_INVALID_SPEC") from None
    info = dict(info)
    info["path"] = target
    return {"mode": "create", **info}


def inspect(source_path: str) -> Dict[str, Any]:
    """`source_path` 는 `resolve_source` 가 검증해 넘긴 실제 경로다."""
    path = source_path
    if not os.path.exists(path):
        raise HwpxNodeError(f"파일이 없습니다: {path}", reason="HWPX_NOT_FOUND")
    try:
        package = hwpx.HwpxPackage.open(path)
        keys = hwpx.template_keys(path)
    except hwpx.PackageRejected as exc:
        raise HwpxNodeError(str(exc), reason="HWPX_INVALID_PACKAGE") from None
    return {
        "mode": "inspect",
        "path": path,
        "placeholders": keys,
        "sections": len(package.section_names()),
        "entries": len(package.names),
    }


def validate(source_path: str) -> Dict[str, Any]:
    """열리는 상태인지 본다. **거부 사유를 예외가 아니라 결과로** 돌려준다 — 검사 자체가 목적이라
    실패도 정상 출력이다."""
    path = source_path
    if not os.path.exists(path):
        return {"mode": "validate", "path": path, "ok": False,
                "reason": "HWPX_NOT_FOUND", "message": f"파일이 없습니다: {path}"}
    try:
        package = hwpx.HwpxPackage.open(path)
    except hwpx.PackageRejected as exc:
        return {"mode": "validate", "path": path, "ok": False,
                "reason": exc.reason, "message": str(exc)}

    warnings = []
    if not package.section_names():
        warnings.append("본문 section 이 없습니다.")
    return {"mode": "validate", "path": path, "ok": True,
            "sections": len(package.section_names()),
            "entries": len(package.names), "warnings": warnings}


def run(mode: str, *, incoming: Any = None, output_path: str = "",
        source_artifact_id: str = "", db=None, owner_user_id: Optional[int] = None,
        project_id: Optional[int] = None) -> Dict[str, Any]:
    """생성 코드가 부르는 단일 진입점. 살펴볼 파일은 **경로가 아니라 artifact id** 로 받는다."""
    if mode not in MODES:
        raise HwpxNodeError(
            f"알 수 없는 동작입니다: {mode} — {', '.join(MODES)} 중 하나여야 합니다.",
            reason="HWPX_BAD_MODE",
        )
    if mode == "create":
        return create(incoming, output_path=output_path, db=db, owner_user_id=owner_user_id)
    path = resolve_source(db, source_artifact_id, owner_user_id=owner_user_id, project_id=project_id)
    result = inspect(path) if mode == "inspect" else validate(path)
    # 결과의 'path' 는 create 와 같은 공개 형태(uploads/<이름>)로 통일한다 — 물리 경로
    # (uploads/u<id>/...)를 결과 JSON 에 실으면 프론트 다운로드 링크가 404 가 되고 소유자
    # id·서버 배치가 노드 출력으로 새어 나간다(PR #41 리뷰).
    if "path" in result:
        result["path"] = "uploads/" + os.path.basename(str(result["path"]).replace("\\", "/"))
    if "message" in result and result.get("reason") == "HWPX_NOT_FOUND":
        result["message"] = f"파일이 없습니다: {result['path']}"
    return result
