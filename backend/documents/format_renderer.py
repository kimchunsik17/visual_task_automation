"""documents/format_renderer.py — FormatSpec + values 를 실제 파일로 렌더하는 단일 진입점.

출력 매트릭스(계획 §3):
  document → hwpx(기존 hwpx 빌더) · docx(docx_builder) · xlsx(xlsx_builder)
             · pdf(블록→HTML 후 poster_generator 의 Chromium 인쇄 — 표·이미지 품질과
               렌더러 통일 때문에 PyMuPDF 흐름 렌더 대신 이 경로를 쓴다. 내용이 길면
               page.pdf 가 지정 크기(A4)로 자동 쪽나눔한다)
  design   → pdf · png (poster_generator.render_html_to_file 그대로 — sanitize 포함)

이미지 소스는 artifactId 뿐이고 해석은 주입받은 image_loader(artifactId → (bytes, 확장자))가
한다 — hwpx 빌더와 같은 원칙. 이 모듈도 DB 를 모른다.
"""

from __future__ import annotations

import base64
import html as html_module
import os
from typing import Any, Callable, Dict, Optional

from . import hwpx
from . import docx_builder, xlsx_builder
from .format_spec import (
    DESIGN_OUTPUTS, DOCUMENT_OUTPUTS, FormatSpecError,
    resolve_design_html, resolve_document_spec, validate_format_spec,
)
from .hwpx.builder import ImageLoader

# 문서류 pdf 의 쪽 크기 (A4 @96dpi)
_A4_WIDTH, _A4_HEIGHT = 794, 1123

_MIME_BY_FORMAT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                   "gif": "image/gif", "bmp": "image/bmp"}


def _data_uri(image_loader: Optional[ImageLoader]) -> Callable[[str], str]:
    def load(artifact_id: str) -> str:
        if image_loader is None:
            raise FormatSpecError("이 실행에서는 이미지를 넣을 수 없습니다(Artifact 해석기가 없습니다).",
                                  reason="FORMAT_IMAGE_FORBIDDEN")
        data, image_format = image_loader(str(artifact_id))
        mime = _MIME_BY_FORMAT.get(str(image_format or "").lower().lstrip("."), "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return load


def _document_spec_to_html(document_spec: Dict[str, Any],
                           image_loader: Optional[ImageLoader]) -> str:
    """문서류 pdf 경로 — 5블록을 인쇄용 HTML 로 옮긴다. 값은 전부 이스케이프한다."""
    to_data_uri = _data_uri(image_loader)
    esc = html_module.escape
    parts = []
    for block in document_spec.get("blocks", []):
        btype = block.get("type")
        if btype == "heading":
            level = int(block.get("level", 1))
            parts.append(f"<h{level}>{esc(block.get('text') or '')}</h{level}>")
        elif btype == "paragraph":
            parts.append(f"<p>{esc(block.get('text') or '')}</p>")
        elif btype == "table":
            head = "".join(f"<th>{esc('' if c is None else str(c))}</th>" for c in block.get("columns", []))
            body = "".join(
                "<tr>" + "".join(f"<td>{esc('' if v is None else str(v))}</td>" for v in row) + "</tr>"
                for row in block.get("rows", []))
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        elif btype == "image":
            uri = to_data_uri(block["artifactId"])
            width_attr = ""
            if block.get("widthMm") is not None:
                width_attr = f" style=\"width:{float(block['widthMm'])}mm\""
            parts.append(f"<img src=\"{uri}\"{width_attr}>")
        elif btype == "page_break":
            parts.append("<div class=\"pb\"></div>")
    style = (
        "body { padding: 18mm 16mm; color: #111; font-size: 11pt; line-height: 1.65; }"
        "h1 { font-size: 18pt; } h2 { font-size: 14pt; } h3 { font-size: 12pt; }"
        "table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; }"
        "th, td { border: 1px solid #999; padding: 6px 9px; font-size: 10.5pt; text-align: left;"
        " vertical-align: top; word-break: break-word; }"
        "th { background: #f1f4f8; }"
        "img { max-width: 100%; }"
        ".pb { page-break-after: always; }"
    )
    return f"<html><head><meta charset=\"utf-8\"><style>{style}</style></head><body>{''.join(parts)}</body></html>"


def render_format(spec: Any, values: Optional[Dict[str, Any]], output: str, output_path: str,
                  *, image_loader: Optional[ImageLoader] = None) -> Dict[str, Any]:
    """검증 → 채움 → 렌더. 결과 {path, layout, output} 를 돌려준다.

    실패는 FormatSpecError(reason 코드) 또는 하위 렌더러의 SpecError 로 올라온다 —
    실행기(formatNode)가 NodeError 로 변환한다.
    """
    normalized = validate_format_spec(spec)
    layout = normalized["layout"]
    allowed = DOCUMENT_OUTPUTS if layout == "document" else DESIGN_OUTPUTS
    if output not in allowed:
        raise FormatSpecError(f"{layout} 포맷의 출력은 {allowed} 만 가능합니다: {output!r}",
                              reason="FORMAT_OUTPUT_UNSUPPORTED")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if layout == "document":
        document_spec = resolve_document_spec(normalized, values or {})
        if output == "hwpx":
            hwpx.build(document_spec, output_path, image_loader=image_loader)
        elif output == "docx":
            docx_builder.build(document_spec, output_path, image_loader=image_loader)
        elif output == "xlsx":
            xlsx_builder.build(document_spec, output_path, image_loader=image_loader)
        else:  # pdf
            from poster_generator import render_html_to_file
            html_doc = _document_spec_to_html(document_spec, image_loader)
            render_html_to_file(html_doc, output_path,
                                width=_A4_WIDTH, height=_A4_HEIGHT, fmt="pdf")
    else:  # design
        from poster_generator import render_html_to_file
        html_doc, width, height = resolve_design_html(
            normalized, values or {}, _data_uri(image_loader) if image_loader else None)
        render_html_to_file(html_doc, output_path, width=width, height=height, fmt=output)

    return {"path": output_path, "layout": layout, "output": output}
