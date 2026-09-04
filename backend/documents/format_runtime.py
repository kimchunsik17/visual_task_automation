"""documents/format_runtime.py — formatNode 실행 런타임 (생성 코드가 부르는 단일 진입점).

hwpx_runtime 과 같은 원칙: 이 모듈이 DB(포맷 라이브러리·artifact)와 렌더러를 잇고,
렌더러(format_renderer)는 순수하게 남는다.

실패는 FormatNodeError(reason = error_catalog 의 FORMAT_* 코드)로 올라간다 —
생성 코드가 NodeError 로 변환해 실행 로그·프론트 안내에 쓴다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from . import hwpx
from .format_presets import PRESETS_BY_ID
from .format_renderer import render_format
from .format_spec import FormatSpecError, missing_required_fields, validate_format_spec
from .hwpx_runtime import HwpxNodeError, _image_loader, normalize_path

_STRIP_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$")


class FormatNodeError(ValueError):
    def __init__(self, message: str, *, reason: str = "FORMAT_SPEC_INVALID",
                 missing_fields: Optional[list] = None):
        super().__init__(message)
        self.reason = reason
        self.missing_fields = list(missing_fields or [])


def load_format(format_id: str, *, db=None, owner_user_id: Optional[int] = None) -> Dict[str, Any]:
    """프리셋 → 사용자 라이브러리 순으로 찾는다. 없으면 FORMAT_NOT_FOUND."""
    format_id = str(format_id or "").strip()
    if not format_id:
        raise FormatNodeError("포맷이 선택되지 않았습니다. 노드에서 포맷을 선택해주세요.",
                              reason="FORMAT_NOT_FOUND")
    preset = PRESETS_BY_ID.get(format_id)
    if preset is not None:
        return preset
    if db is not None:
        import models
        query = db.query(models.DocumentFormat).filter(models.DocumentFormat.id == format_id)
        # 소유 검증 — 다른 사용자의 포맷 id 를 넘겨도 열리지 않는다.
        if owner_user_id is not None:
            query = query.filter(models.DocumentFormat.owner_user_id == owner_user_id)
        row = query.first()
        if row is not None:
            try:
                return validate_format_spec(row.spec)
            except FormatSpecError as exc:
                raise FormatNodeError(f"저장된 포맷이 잘못되어 있습니다: {exc}",
                                      reason="FORMAT_SPEC_INVALID") from None
    raise FormatNodeError(f"포맷을 찾을 수 없습니다: {format_id}", reason="FORMAT_NOT_FOUND")


def _values_from(explicit_json: str, incoming: Any) -> Dict[str, Any]:
    """빈칸 값 해석 — data.values(JSON) 가 있으면 그것, 없으면 직전 노드 출력에서."""
    source = explicit_json if (explicit_json or "").strip() else incoming
    if source is None:
        return {}
    if isinstance(source, dict):
        return source
    text = _STRIP_FENCE_RE.sub("", str(source).strip())
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {}  # 직전 출력이 JSON 이 아니면 빈칸 자동 매핑 없음 — required 검사가 잡는다
    return parsed if isinstance(parsed, dict) else {}


def _resolve_image_values(spec: Dict[str, Any], values: Dict[str, Any], *,
                          db=None, owner_user_id: Optional[int] = None) -> Dict[str, Any]:
    """image 빈칸 값이 artifact id 가 아니라 파일 경로(uploads/…)면 등록된 artifact 로 역조회한다.

    이미지 생성 노드가 다음 노드로 넘기는 값은 artifact id 가 아니라 파일 경로라서, LLM 이
    그 경로를 빈칸 값에 옮겨 적으면 여기서 id 로 이어진다(시연 포스터 흐름: 이미지 생성 →
    빈칸 JSON 조립 → formatNode). 임의 로컬 경로를 여는 통로가 아니다 — lookup_by_stored_path
    는 **등록된 파일로 역조회되는 경우에만** 값을 주고, 소유·만료·경로·hash 검증은 렌더 시
    _image_loader 의 resolve() 가 그대로 수행한다.
    """
    if db is None:
        return values
    image_fields = {f["name"] for f in spec.get("fields", []) if f.get("kind") == "image"}
    if not image_fields:
        return values
    import artifacts

    resolved = dict(values)
    for name in image_fields:
        raw = str(resolved.get(name) or "").strip()
        if not raw or artifacts.lookup(db, raw) is not None:
            continue  # 비었거나 이미 artifact id
        ref = artifacts.lookup_by_stored_path(db, raw, owner_user_id=owner_user_id)
        if ref is not None and ref.artifact_id:
            resolved[name] = ref.artifact_id
    return resolved


def default_output_name(spec: Dict[str, Any], output: str) -> str:
    """포맷 이름을 따서 짓되, 실행마다 겹치지 않게 짧은 임의 문자열을 붙인다(hwpx_runtime 과 동일)."""
    import uuid
    base = re.sub(r"[^\w가-힣 .-]", "", str(spec.get("name") or "문서")).strip() or "문서"
    return f"{base[:40]}_{uuid.uuid4().hex[:6]}.{output}"


def run(*, format_id: str, output: str = "", values_json: str = "", incoming: Any = None,
        output_path: str = "", db=None, owner_user_id: Optional[int] = None) -> Dict[str, Any]:
    spec = load_format(format_id, db=db, owner_user_id=owner_user_id)

    chosen_output = (output or "").strip() or spec["output"]["default"]
    # 포맷 정본의 output.allowed 를 여기서 강제한다 — 렌더러의 layout 단위 검사만으로는
    # "시말서를 xlsx 로" 같은 정본 밖 조합이 조용히 성공한다(감사 지적).
    allowed = [str(o) for o in (spec.get("output") or {}).get("allowed") or []]
    if allowed and chosen_output not in allowed:
        raise FormatNodeError(
            f"'{spec.get('name') or format_id}' 포맷의 출력은 {', '.join(allowed)} 만 가능합니다: "
            f"{chosen_output!r}", reason="FORMAT_OUTPUT_UNSUPPORTED")
    values = _values_from(values_json, incoming)
    values = _resolve_image_values(spec, values, db=db, owner_user_id=owner_user_id)

    # 필수 빈칸 누락은 needs_input 성격 — 코드가 아니라 사용자가 채울 문제라서 먼저 알려준다.
    missing = missing_required_fields(spec, values)
    if missing:
        labels = {f["name"]: (f.get("label") or f["name"]) for f in spec.get("fields", [])}
        raise FormatNodeError(
            "필수 빈칸이 비어 있습니다: " + ", ".join(f"{labels[m]}({m})" for m in missing),
            reason="FORMAT_FIELD_MISSING", missing_fields=missing)

    try:
        target = normalize_path(output_path) if output_path else normalize_path(
            default_output_name(spec, chosen_output))
    except HwpxNodeError as exc:
        # hwpx_runtime 의 경로 규칙을 빌려 쓰므로 예외도 여기서 FORMAT_* 로 옮긴다 —
        # 그대로 새면 생성 코드의 generic except 가 '문서 포맷 처리 실패' 로 뭉갠다.
        raise FormatNodeError(str(exc), reason="FORMAT_SPEC_INVALID") from None

    # 물리 파일은 소유자 디렉토리 밑에 쓰고, 반환하는 'path' 는 공개 형태(uploads/<이름>)를
    # 유지한다 — hwpx_runtime.create 와 같은 계약(등록·다음 노드 읽기가 소유자 디렉토리로 푼다).
    from upload_security import physical_output_path

    physical = physical_output_path(target, owner_user_id)
    try:
        result = render_format(spec, values, chosen_output, physical,
                               image_loader=_image_loader(db, owner_user_id))
    except FormatSpecError as exc:
        raise FormatNodeError(str(exc), reason=exc.reason,
                              missing_fields=exc.missing_fields) from None
    except (hwpx.SpecError, hwpx.UnsupportedFeature) as exc:
        # 하위 렌더러(hwpx/docx/xlsx)·이미지 로더의 오류 — 사용자가 고칠 수 있는 문구이므로
        # FORMAT_* 코드에 실어 그대로 보여준다.
        raise FormatNodeError(str(exc), reason="FORMAT_SPEC_INVALID") from None

    return {"path": target, "layout": result["layout"], "output": chosen_output,
            "format_id": spec.get("id") or format_id, "format_name": spec.get("name")}
