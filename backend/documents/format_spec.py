"""documents/format_spec.py — FormatSpec(포맷 정본)의 검증·치환.

계획: Documents/plans/DOCUMENT_FORMAT_STUDIO_PLAN.md §3.

포맷 = fields(빈칸 선언) + 골격. 골격은 layout 에 따라 둘 중 하나다:
  - document: blocks — hwpx DocumentSpec 5블록(heading·paragraph·table·image·page_break)
               + 참조 문법 {{field}} / fromField. 출력 hwpx·docx·pdf·xlsx.
  - design  : design.html/css/theme — 포스터·팜플렛. 출력 pdf·png
               (렌더는 poster_generator.render_html_to_file 재사용).

이 모듈은 순수 함수다 — DB·네트워크·파일을 모른다. 이미지 해석(artifactId → bytes)은
호출자가 주입한다(hwpx builder 의 image_loader 와 같은 원칙).

치환은 파일이 아니라 스펙(JSON)·HTML 문자열 단계에서 일어난다 — fileModifier 의
"XML 텍스트 노드 분할로 {{key}} 치환 실패" 문제가 구조적으로 없다.
"""

from __future__ import annotations

import html as html_module
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .hwpx.builder import SUPPORTED_BLOCKS

SUPPORTED_LAYOUTS = ("document", "design")
SUPPORTED_FIELD_KINDS = ("text", "multiline", "rows", "image")
DOCUMENT_OUTPUTS = ("hwpx", "docx", "pdf", "xlsx")
DESIGN_OUTPUTS = ("pdf", "png")

MAX_FIELDS = 50
MAX_DESIGN_HTML_CHARS = 200_000
MAX_DESIGN_CSS_CHARS = 100_000

_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# 디자인 html 의 이미지 슬롯: <img ... data-field="이름" ...>
_IMG_SLOT_RE = re.compile(r"<img\b[^>]*\bdata-field=[\"']([A-Za-z_][A-Za-z0-9_]*)[\"'][^>]*>", re.IGNORECASE)


class FormatSpecError(ValueError):
    """스펙 또는 채움 값이 잘못됐다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str = "FORMAT_SPEC_INVALID",
                 missing_fields: Optional[List[str]] = None):
        super().__init__(message)
        self.reason = reason
        self.missing_fields = list(missing_fields or [])


# ── 검증 ────────────────────────────────────────────────────────────────


def _collect_placeholders(text: str) -> List[str]:
    return [m.group(1) for m in _PLACEHOLDER_RE.finditer(text or "")]


def _iter_block_texts(block: Dict[str, Any]):
    """블록 안에서 {{참조}} 가 나타날 수 있는 문자열들."""
    for key in ("text",):
        if isinstance(block.get(key), str):
            yield block[key]
    if isinstance(block.get("columns"), list):
        for col in block["columns"]:
            if isinstance(col, str):
                yield col
    if isinstance(block.get("rows"), list):
        for row in block["rows"]:
            if isinstance(row, list):
                for cell in row:
                    if isinstance(cell, str):
                        yield cell


def validate_format_spec(spec: Any) -> Dict[str, Any]:
    """FormatSpec 을 검증하고 정규화해 돌려준다. 저장·실행 양쪽의 관문."""
    if not isinstance(spec, dict):
        raise FormatSpecError("포맷은 JSON 객체여야 합니다.")

    name = spec.get("name")
    if not isinstance(name, str) or not name.strip():
        raise FormatSpecError("포맷 name 이 비어 있습니다.")

    layout = spec.get("layout", "document")
    if layout not in SUPPORTED_LAYOUTS:
        raise FormatSpecError(f"layout 은 {SUPPORTED_LAYOUTS} 중 하나여야 합니다: {layout!r}")

    allowed_outputs = DOCUMENT_OUTPUTS if layout == "document" else DESIGN_OUTPUTS
    output = spec.get("output") or {}
    if not isinstance(output, dict):
        raise FormatSpecError("output 은 객체여야 합니다.")
    out_allowed = output.get("allowed") or list(allowed_outputs)
    bad = [o for o in out_allowed if o not in allowed_outputs]
    if bad:
        raise FormatSpecError(f"{layout} 포맷의 출력은 {allowed_outputs} 만 가능합니다: {bad}")
    out_default = output.get("default") or out_allowed[0]
    if out_default not in out_allowed:
        raise FormatSpecError(f"output.default {out_default!r} 가 allowed 에 없습니다.")

    # fields
    fields = spec.get("fields")
    if not isinstance(fields, list):
        raise FormatSpecError("fields 는 배열이어야 합니다.")
    if len(fields) > MAX_FIELDS:
        raise FormatSpecError(f"필드가 너무 많습니다({len(fields)}개, 상한 {MAX_FIELDS}개).")
    field_by_name: Dict[str, Dict[str, Any]] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise FormatSpecError(f"fields[{index}] 는 객체여야 합니다.")
        fname = field.get("name")
        if not isinstance(fname, str) or not _FIELD_NAME_RE.match(fname):
            raise FormatSpecError(
                f"fields[{index}].name 은 영문·숫자·밑줄(첫 글자는 영문/밑줄)이어야 합니다: {fname!r}")
        if fname in field_by_name:
            raise FormatSpecError(f"필드 이름이 중복됩니다: {fname}")
        kind = field.get("kind", "text")
        if kind not in SUPPORTED_FIELD_KINDS:
            raise FormatSpecError(f"fields[{index}].kind 는 {SUPPORTED_FIELD_KINDS} 중 하나여야 합니다.")
        if kind == "rows":
            if layout == "design":
                raise FormatSpecError("rows 필드는 문서(document) 포맷 전용입니다(v1).")
            columns = field.get("columns")
            if not isinstance(columns, list) or not columns:
                raise FormatSpecError(f"rows 필드 {fname} 에는 columns(열 이름 배열)가 필요합니다.")
        field_by_name[fname] = field

    referenced: set = set()

    if layout == "document":
        blocks = spec.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise FormatSpecError("document 포맷에는 blocks(배열)가 필요합니다.")
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                raise FormatSpecError(f"blocks[{index}] 는 객체여야 합니다.")
            btype = block.get("type")
            if btype not in SUPPORTED_BLOCKS:
                raise FormatSpecError(
                    f"blocks[{index}].type {btype!r} 는 지원하지 않습니다"
                    f"({', '.join(SUPPORTED_BLOCKS)} 만 가능).")
            from_field = block.get("fromField")
            if from_field is not None:
                field = field_by_name.get(from_field)
                if field is None:
                    raise FormatSpecError(f"blocks[{index}].fromField 가 선언되지 않은 필드입니다: {from_field}")
                expected = "rows" if btype == "table" else "image" if btype == "image" else None
                if expected is None:
                    raise FormatSpecError(f"fromField 는 table·image 블록에서만 쓸 수 있습니다(blocks[{index}]).")
                if field.get("kind", "text") != expected:
                    raise FormatSpecError(
                        f"blocks[{index}] ({btype})의 fromField 는 kind={expected} 필드여야 합니다: "
                        f"{from_field} 는 {field.get('kind')} 입니다.")
                referenced.add(from_field)
            for text in _iter_block_texts(block):
                for ph in _collect_placeholders(text):
                    if ph not in field_by_name:
                        raise FormatSpecError(f"blocks[{index}] 가 선언되지 않은 변수를 참조합니다: {{{{{ph}}}}}")
                    if field_by_name[ph].get("kind", "text") in ("rows", "image"):
                        raise FormatSpecError(
                            f"{{{{{ph}}}}} 는 {field_by_name[ph].get('kind')} 필드라 텍스트 치환에 쓸 수 없습니다"
                            f" — fromField 를 쓰세요(blocks[{index}]).")
                    referenced.add(ph)
    else:  # design
        design = spec.get("design")
        if not isinstance(design, dict):
            raise FormatSpecError("design 포맷에는 design(객체)이 필요합니다.")
        html = design.get("html")
        if not isinstance(html, str) or not html.strip():
            raise FormatSpecError("design.html 이 비어 있습니다.")
        if len(html) > MAX_DESIGN_HTML_CHARS:
            raise FormatSpecError(f"design.html 이 너무 큽니다(상한 {MAX_DESIGN_HTML_CHARS}자).")
        css = design.get("css") or ""
        if not isinstance(css, str):
            raise FormatSpecError("design.css 는 문자열이어야 합니다.")
        if len(css) > MAX_DESIGN_CSS_CHARS:
            raise FormatSpecError(f"design.css 가 너무 큽니다(상한 {MAX_DESIGN_CSS_CHARS}자).")
        theme = design.get("theme") or {}
        if not isinstance(theme, dict) or not all(
                isinstance(k, str) and isinstance(v, (str, int, float)) for k, v in theme.items()):
            raise FormatSpecError("design.theme 은 {이름: 문자열/숫자} 객체여야 합니다.")
        for ph in _collect_placeholders(html) + _collect_placeholders(css):
            if ph not in field_by_name:
                raise FormatSpecError(f"design 이 선언되지 않은 변수를 참조합니다: {{{{{ph}}}}}")
            if field_by_name[ph].get("kind", "text") == "image":
                raise FormatSpecError(
                    f"{{{{{ph}}}}} 는 image 필드입니다 — <img data-field=\"{ph}\"> 슬롯을 쓰세요.")
            referenced.add(ph)
        for slot in _IMG_SLOT_RE.findall(html):
            field = field_by_name.get(slot)
            if field is None:
                raise FormatSpecError(f"이미지 슬롯이 선언되지 않은 필드를 가리킵니다: data-field=\"{slot}\"")
            if field.get("kind", "text") != "image":
                raise FormatSpecError(f"data-field=\"{slot}\" 슬롯은 kind=image 필드여야 합니다.")
            referenced.add(slot)

    # 채워도 어디에도 쓰이지 않는 필수 필드 = 스펙 버그. 저장 시점에 거부한다.
    unused_required = [
        name for name, field in field_by_name.items()
        if field.get("required") and name not in referenced
    ]
    if unused_required:
        raise FormatSpecError(
            f"필수로 선언됐지만 골격 어디에서도 쓰이지 않는 필드가 있습니다: {', '.join(unused_required)}")

    normalized = dict(spec)
    normalized["layout"] = layout
    normalized["output"] = {"default": out_default, "allowed": list(out_allowed)}
    return normalized


# ── 채움(값 해석) 공통 ───────────────────────────────────────────────────


def missing_required_fields(spec: Dict[str, Any], values: Dict[str, Any]) -> List[str]:
    missing = []
    for field in spec.get("fields", []):
        if not field.get("required"):
            continue
        value = (values or {}).get(field["name"])
        if value is None or (isinstance(value, str) and not value.strip()) \
                or (isinstance(value, list) and not value):
            missing.append(field["name"])
    return missing


def _require_filled(spec: Dict[str, Any], values: Dict[str, Any]) -> None:
    missing = missing_required_fields(spec, values)
    if missing:
        labels = {f["name"]: f.get("label") or f["name"] for f in spec.get("fields", [])}
        raise FormatSpecError(
            "필수 빈칸이 비어 있습니다: " + ", ".join(f"{labels[m]}({m})" for m in missing),
            reason="FORMAT_FIELD_MISSING", missing_fields=missing)


def _substitute(text: str, values: Dict[str, Any], *, escape_html: bool = False) -> str:
    def _repl(match: re.Match) -> str:
        value = values.get(match.group(1))
        rendered = "" if value is None else str(value)
        return html_module.escape(rendered) if escape_html else rendered
    return _PLACEHOLDER_RE.sub(_repl, text or "")


def _normalize_rows(field: Dict[str, Any], value: Any) -> List[List[str]]:
    """rows 값 관용 해석 — LLM/바인딩이 주는 흔한 형태(list[list] · list[dict])를 받는다."""
    columns = field.get("columns") or []
    if value is None:
        return []
    if not isinstance(value, list):
        raise FormatSpecError(f"{field['name']} 값은 배열이어야 합니다(행 목록).")
    rows: List[List[str]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(["" if item.get(c) is None else str(item.get(c)) for c in columns])
        elif isinstance(item, list):
            row = ["" if v is None else str(v) for v in item]
            # 칸 수를 columns 에 맞춘다 — 모자라면 빈칸, 넘치면 자름(hwpx builder 는 불일치를 거부한다)
            row = (row + [""] * len(columns))[: len(columns)]
            rows.append(row)
        else:
            rows.append(([str(item)] + [""] * len(columns))[: len(columns)])
    return rows


# ── document: FormatSpec + values → DocumentSpec(hwpx builder 입력) ──────


def resolve_document_spec(spec: Dict[str, Any], values: Dict[str, Any]) -> Dict[str, Any]:
    if spec.get("layout", "document") != "document":
        raise FormatSpecError("document 포맷이 아닙니다.")
    _require_filled(spec, values or {})
    values = values or {}
    field_by_name = {f["name"]: f for f in spec.get("fields", [])}

    blocks: List[Dict[str, Any]] = []
    for block in spec.get("blocks", []):
        btype = block.get("type")
        from_field = block.get("fromField")
        if from_field is not None:
            field = field_by_name[from_field]
            value = values.get(from_field)
            if btype == "table":
                rows = _normalize_rows(field, value)
                if not rows and not field.get("required"):
                    continue  # 선택 표는 값이 없으면 통째로 생략
                blocks.append({"type": "table", "columns": list(field.get("columns") or []), "rows": rows})
            else:  # image
                artifact_id = value
                if not artifact_id:
                    continue  # 선택 이미지는 생략 (필수는 _require_filled 가 이미 막았다)
                resolved = {k: v for k, v in block.items() if k != "fromField"}
                resolved["artifactId"] = str(artifact_id)
                blocks.append(resolved)
            continue

        resolved = dict(block)
        for key in ("text",):
            if isinstance(resolved.get(key), str):
                resolved[key] = _substitute(resolved[key], values)
        if isinstance(resolved.get("columns"), list):
            resolved["columns"] = [
                _substitute(c, values) if isinstance(c, str) else c for c in resolved["columns"]]
        if isinstance(resolved.get("rows"), list):
            resolved["rows"] = [
                [_substitute(c, values) if isinstance(c, str) else c for c in row]
                if isinstance(row, list) else row
                for row in resolved["rows"]]
        blocks.append(resolved)

    document_spec: Dict[str, Any] = {
        "title": _substitute(spec.get("title") or spec.get("name") or "문서", values),
        "blocks": blocks,
    }
    if isinstance(spec.get("page"), dict):
        document_spec["page"] = spec["page"]
    return document_spec


# ── design: FormatSpec + values → 렌더용 HTML ────────────────────────────

ImageDataUri = Callable[[str], str]  # artifactId → "data:image/png;base64,..."


def resolve_design_html(spec: Dict[str, Any], values: Dict[str, Any],
                        image_data_uri: Optional[ImageDataUri] = None) -> Tuple[str, int, int]:
    """치환·테마 주입이 끝난 완전한 HTML 문서와 (width, height)를 돌려준다.

    sanitize(스크립트 제거)와 실제 렌더는 poster_generator.render_html_to_file 이 한다 —
    여기서는 조립만 한다.
    """
    if spec.get("layout") != "design":
        raise FormatSpecError("design 포맷이 아닙니다.")
    _require_filled(spec, values or {})
    values = values or {}
    design = spec.get("design") or {}
    field_by_name = {f["name"]: f for f in spec.get("fields", [])}

    # 텍스트 치환은 HTML 이스케이프 — 값에 태그가 들어와도 마크업이 되지 않는다.
    body = _substitute(design.get("html") or "", values, escape_html=True)
    css = _substitute(design.get("css") or "", values, escape_html=False)

    # 이미지 슬롯: src 를 artifact data URI 로. 값이 없는 선택 슬롯은 img 태그 제거.
    def _fill_slot(match: re.Match) -> str:
        slot = match.group(1)
        artifact_id = values.get(slot)
        if not artifact_id:
            return ""
        if image_data_uri is None:
            raise FormatSpecError("이 실행에서는 이미지를 넣을 수 없습니다(Artifact 해석기가 없습니다).",
                                  reason="FORMAT_IMAGE_FORBIDDEN")
        data_uri = image_data_uri(str(artifact_id))
        tag = match.group(0)
        tag = re.sub(r"\bsrc=([\"']).*?\1", "", tag, flags=re.IGNORECASE)
        return tag.replace("<img", f'<img src="{data_uri}"', 1)

    body = _IMG_SLOT_RE.sub(_fill_slot, body)

    # 테마 → CSS 변수(--fs-*). css 를 몰라도 스튜디오에서 색·글꼴을 바꿀 수 있는 지점.
    theme = design.get("theme") or {}
    theme_lines = [f"  --fs-{re.sub(r'[^A-Za-z0-9_-]', '', str(k))}: {str(v)};" for k, v in theme.items()]
    font = theme.get("fontFamily")
    font_rule = f"body {{ font-family: '{font}', 'Pretendard', sans-serif; }}\n" if font else ""
    style = ":root {\n" + "\n".join(theme_lines) + "\n}\n" + font_rule + (css or "")

    width = int(design.get("width") or 794)
    height = int(design.get("height") or 1123)
    html_doc = (
        "<html><head><meta charset=\"utf-8\">"
        f"<style>{style}</style></head>"
        f"<body>{body}</body></html>"
    )
    return html_doc, width, height


# ── LLM 용 축소 스키마 (§4.2-b) ──────────────────────────────────────────


def fields_json_schema(spec: Dict[str, Any], exclude: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """빈칸 채움 LLM 의 Structured Output 스키마. exclude(바인딩·고정값으로 이미 해결된
    필드)를 뺀 나머지만 담는다 — LLM 은 비정형 해석이 필요한 필드만 만든다.
    image 필드는 LLM 이 만들 수 없으므로 항상 제외한다."""
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for field in spec.get("fields", []):
        name = field["name"]
        kind = field.get("kind", "text")
        if name in exclude or kind == "image":
            continue
        description = field.get("label") or name
        if field.get("description"):
            description += f" — {field['description']}"
        if kind == "rows":
            columns = field.get("columns") or []
            properties[name] = {
                "type": "array",
                "description": f"{description} (각 행은 {columns} 순서의 문자열 배열)",
                "items": {"type": "array", "items": {"type": "string"}},
            }
        else:
            properties[name] = {"type": "string", "description": description}
        if field.get("required"):
            required.append(name)
    # title 은 OpenAI structured output 의 json_schema.name 이 된다(^[a-zA-Z0-9_-]+$ 만 허용).
    # 포맷 이름은 대개 한글이라 그대로 쓰면 400 으로 거부되므로, 이름은 description 으로 옮긴다.
    name = str(spec.get("name") or "")
    safe = "".join(c for c in name if c.isascii() and (c.isalnum() or c in "_-"))
    return {
        "title": safe or "FormatValues",
        "description": f"{name} 포맷의 빈칸 값" if name else "포맷의 빈칸 값",
        "type": "object",
        "properties": properties,
        "required": required,
    }
