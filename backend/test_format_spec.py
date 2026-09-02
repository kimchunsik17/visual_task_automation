"""FormatSpec(포맷 스튜디오 계획 Phase 0)의 검증·채움·렌더 검사."""

import io
import struct
import zlib

import pytest

from documents import format_presets
from documents.format_renderer import render_format
from documents.format_spec import (
    FormatSpecError, fields_json_schema, missing_required_fields,
    resolve_design_html, resolve_document_spec, validate_format_spec,
)
from documents.hwpx_runtime import validate as hwpx_validate


# ── 테스트 재료 ──────────────────────────────────────────────────────────

def _png_bytes() -> bytes:
    """1×1 불투명 PNG — 외부 파일 없이 만드는 최소 이미지."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def fake_image_loader(artifact_id):
    return _png_bytes(), "png"


DOC_SPEC = {
    "version": 1, "name": "테스트 문서", "layout": "document",
    "output": {"default": "hwpx", "allowed": ["hwpx", "docx", "pdf", "xlsx"]},
    "fields": [
        {"name": "title", "label": "제목", "kind": "text", "required": True},
        {"name": "body", "label": "본문", "kind": "multiline", "required": True},
        {"name": "items", "label": "항목", "kind": "rows", "columns": ["이름", "값"]},
        {"name": "stamp", "label": "도장", "kind": "image"},
    ],
    "blocks": [
        {"type": "heading", "level": 1, "text": "{{title}}"},
        {"type": "paragraph", "text": "{{body}}"},
        {"type": "table", "fromField": "items"},
        {"type": "image", "fromField": "stamp", "widthMm": 20},
    ],
}

DESIGN_SPEC = {
    "version": 1, "name": "테스트 포스터", "layout": "design",
    "output": {"default": "png", "allowed": ["png", "pdf"]},
    "fields": [
        {"name": "headline", "label": "헤드라인", "kind": "text", "required": True},
        {"name": "photo", "label": "사진", "kind": "image"},
    ],
    "design": {
        "width": 400, "height": 300,
        "theme": {"primaryColor": "#ff0055", "fontFamily": "Pretendard"},
        "html": "<h1>{{headline}}</h1><img data-field=\"photo\">",
        "css": "h1 { color: var(--fs-primaryColor); }",
    },
}


# ── 검증 ────────────────────────────────────────────────────────────────

def test_validate_accepts_well_formed_specs():
    assert validate_format_spec(DOC_SPEC)["layout"] == "document"
    assert validate_format_spec(DESIGN_SPEC)["layout"] == "design"


def test_validate_rejects_undeclared_placeholder():
    spec = {**DOC_SPEC, "blocks": DOC_SPEC["blocks"] + [{"type": "paragraph", "text": "{{ghost}}"}]}
    with pytest.raises(FormatSpecError, match="선언되지 않은 변수"):
        validate_format_spec(spec)


def test_validate_rejects_unused_required_field():
    spec = {**DOC_SPEC, "fields": DOC_SPEC["fields"] + [
        {"name": "orphan", "label": "고아", "kind": "text", "required": True}]}
    with pytest.raises(FormatSpecError, match="쓰이지 않는 필드"):
        validate_format_spec(spec)


def test_validate_rejects_rows_field_in_design():
    spec = {**DESIGN_SPEC, "fields": DESIGN_SPEC["fields"] + [
        {"name": "rows1", "kind": "rows", "columns": ["a"]}]}
    with pytest.raises(FormatSpecError, match="rows 필드는 문서"):
        validate_format_spec(spec)


def test_validate_rejects_fromfield_kind_mismatch():
    spec = {**DOC_SPEC, "blocks": [{"type": "table", "fromField": "title"}]}
    with pytest.raises(FormatSpecError, match="kind=rows"):
        validate_format_spec(spec)


def test_validate_rejects_wrong_output_for_layout():
    spec = {**DESIGN_SPEC, "output": {"default": "hwpx", "allowed": ["hwpx"]}}
    with pytest.raises(FormatSpecError, match="출력은"):
        validate_format_spec(spec)


# ── 채움 ────────────────────────────────────────────────────────────────

VALUES = {"title": "보고", "body": "내용입니다.",
          "items": [["a", "1"], {"이름": "b", "값": "2"}], "stamp": "art_1"}


def test_resolve_document_substitutes_and_expands_rows():
    resolved = resolve_document_spec(validate_format_spec(DOC_SPEC), VALUES)
    assert resolved["blocks"][0]["text"] == "보고"
    table = resolved["blocks"][2]
    assert table["columns"] == ["이름", "값"]
    assert table["rows"] == [["a", "1"], ["b", "2"]]  # list[list]·list[dict] 관용
    assert resolved["blocks"][3]["artifactId"] == "art_1"


def test_resolve_document_skips_optional_empty_table_and_image():
    resolved = resolve_document_spec(validate_format_spec(DOC_SPEC),
                                     {"title": "t", "body": "b"})
    types = [b["type"] for b in resolved["blocks"]]
    assert "table" not in types and "image" not in types


def test_resolve_document_missing_required_raises_with_field_list():
    with pytest.raises(FormatSpecError) as exc:
        resolve_document_spec(validate_format_spec(DOC_SPEC), {"title": "t"})
    assert exc.value.reason == "FORMAT_FIELD_MISSING"
    assert exc.value.missing_fields == ["body"]
    assert missing_required_fields(DOC_SPEC, {"title": "t"}) == ["body"]


def test_resolve_design_escapes_html_in_values():
    html, width, height = resolve_design_html(
        validate_format_spec(DESIGN_SPEC),
        {"headline": "<script>alert(1)</script>공지"},
        None)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "공지" in html
    assert (width, height) == (400, 300)
    assert "--fs-primaryColor: #ff0055;" in html


def test_resolve_design_injects_image_and_drops_empty_slot():
    spec = validate_format_spec(DESIGN_SPEC)
    with_image, _, _ = resolve_design_html(
        spec, {"headline": "h", "photo": "art_9"}, lambda a: f"data:image/png;base64,AAA_{a}")
    assert 'src="data:image/png;base64,AAA_art_9"' in with_image
    without_image, _, _ = resolve_design_html(spec, {"headline": "h"}, None)
    assert "<img" not in without_image  # 값 없는 선택 슬롯은 제거


# ── LLM 축소 스키마 (§4.2-b) ─────────────────────────────────────────────

def test_fields_schema_excludes_resolved_and_image_fields():
    schema = fields_json_schema(DOC_SPEC, exclude=("title",))
    assert "title" not in schema["properties"]          # 바인딩으로 해결된 필드 제외
    assert "stamp" not in schema["properties"]          # image 는 LLM 이 만들 수 없다
    assert schema["properties"]["items"]["type"] == "array"
    assert schema["required"] == ["body"]


# ── 프리셋 ──────────────────────────────────────────────────────────────

def test_all_presets_are_valid_and_unique():
    ids = [p["id"] for p in format_presets.PRESETS]
    assert len(ids) == len(set(ids)) and len(ids) >= 7
    layouts = {p["layout"] for p in format_presets.PRESETS}
    assert layouts == {"document", "design"}


def _example_values(spec):
    values = {}
    for field in spec["fields"]:
        kind = field.get("kind", "text")
        if kind == "rows":
            values[field["name"]] = [["예" for _ in field["columns"]]]
        elif kind == "image":
            values[field["name"]] = "art_test"
        else:
            values[field["name"]] = field.get("example") or f"예시 {field.get('label')}"
    return values


@pytest.mark.parametrize("preset", [p for p in format_presets.PRESETS if p["layout"] == "document"],
                         ids=lambda p: p["id"])
@pytest.mark.parametrize("output", ["hwpx", "docx", "xlsx"])
def test_document_presets_render(preset, output, tmp_path):
    if output not in preset["output"]["allowed"]:
        pytest.skip(f"{preset['id']} 는 {output} 미지원")
    target = tmp_path / f"{preset['id']}.{output}"
    result = render_format(preset, _example_values(preset), output, str(target),
                           image_loader=fake_image_loader)
    assert target.exists() and target.stat().st_size > 0
    assert result["layout"] == "document"
    if output == "hwpx":
        report = hwpx_validate(str(target))
        assert not report.get("blocking"), f"hwpx 열림 검증 실패: {report}"


@pytest.mark.slow_render
def test_document_preset_pdf_renders(tmp_path):
    """pdf 는 Chromium 렌더라 무겁다 — 대표 1종만."""
    preset = format_presets.PRESETS_BY_ID["incident-report"]
    target = tmp_path / "incident.pdf"
    render_format(preset, _example_values(preset), "pdf", str(target),
                  image_loader=fake_image_loader)
    assert target.stat().st_size > 1000 and target.read_bytes()[:5] == b"%PDF-"


@pytest.mark.slow_render
@pytest.mark.parametrize("preset_id,output", [("event-poster", "png"), ("tri-fold-pamphlet", "pdf"),
                                              ("card-news", "png"), ("certificate-award", "pdf")])
def test_design_presets_render(preset_id, output, tmp_path):
    preset = format_presets.PRESETS_BY_ID[preset_id]
    target = tmp_path / f"{preset_id}.{output}"
    render_format(preset, _example_values(preset), output, str(target),
                  image_loader=fake_image_loader)
    assert target.stat().st_size > 1000


def test_render_rejects_output_not_allowed_for_layout(tmp_path):
    with pytest.raises(FormatSpecError, match="출력은"):
        render_format(DESIGN_SPEC, {"headline": "h"}, "hwpx", str(tmp_path / "x.hwpx"))


def test_frontend_formats_bundle_is_up_to_date():
    from export_node_definitions import FORMATS_BUNDLE_PATH, render_formats_bundle
    assert FORMATS_BUNDLE_PATH.exists(), "python backend/export_node_definitions.py 를 실행하라"
    assert FORMATS_BUNDLE_PATH.read_text(encoding="utf-8") == render_formats_bundle(), (
        "documentFormats.json 번들이 정본과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    )

