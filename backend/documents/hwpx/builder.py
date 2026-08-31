"""documents/hwpx/builder.py — `DocumentSpec`(JSON) 으로 새 HWPX 를 만든다 (계획 §3.2).

■ 왜 스펙을 따로 두는가

노드가 받는 것은 대개 LLM 이 만든 JSON 이다. 그걸 곧바로 문서 API 호출로 옮기면 "무엇이
지원되는지"가 코드 흐름 안에 숨는다. 스펙을 명시하면 (1) 지원하지 않는 것을 **조용히 빠뜨리지
않고 실패시킬 수 있고**, (2) LLM 에게 알려줄 형식이 곧 검사 대상이 된다.

■ 지원하지 않는 것을 조용히 넘기지 않는다

1차 범위는 heading·paragraph·table·image·page_break 다. 자유 배치 도형, 수식, 차트, 매크로,
배포용/암호 문서는 범위 밖이고, 그런 블록이 오면 `UnsupportedFeature` 로 **실패한다**.
조용히 빠뜨리면 사용자는 문서를 열어 보고서야 알게 된다.

■ 이미지는 Artifact 로만 받는다

`artifactId` 만 받고 임의 서버 경로나 URL 은 열지 않는다(§3.3). 실제 해석은 호출자가 넘긴
`image_loader` 가 한다 — 이 모듈은 DB 도 네트워크도 모른다.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

SUPPORTED_BLOCKS = ("heading", "paragraph", "table", "image", "page_break")

# heading level → (글자 크기 pt, 굵게). 한/글 기본 스타일 id 는 문서마다 달라 신뢰할 수 없어서
# 문자 서식으로 표현한다. **시각적 확인은 한/글 release gate 에서 한다.**
_HEADING_STYLE = {1: 18, 2: 15, 3: 13}

MAX_BLOCKS = 2000
MAX_TABLE_CELLS = 5000

# 이미지 형식은 확장자 문자열로 넘긴다. 라이브러리가 받는 것만 허용한다.
IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp"}


class SpecError(ValueError):
    """스펙이 잘못됐다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str = "HWPX_INVALID_SPEC"):
        super().__init__(message)
        self.reason = reason


class UnsupportedFeature(SpecError):
    """1차 범위 밖의 블록이다. 조용히 빠뜨리지 않고 여기서 멈춘다."""

    def __init__(self, message: str):
        super().__init__(message, reason="HWPX_UNSUPPORTED_FEATURE")


ImageLoader = Callable[[str], Tuple[bytes, str]]


def _require_str(value: Any, *, field: str, allow_empty: bool = False) -> str:
    if value is None and allow_empty:
        return ""
    if not isinstance(value, str):
        raise SpecError(f"{field} 는 문자열이어야 합니다.")
    if not value and not allow_empty:
        raise SpecError(f"{field} 가 비어 있습니다.")
    return value


def _apply_page(document, page: Dict[str, Any]) -> None:
    if not page:
        return
    if not isinstance(page, dict):
        raise SpecError("page 는 객체여야 합니다.")

    kwargs: Dict[str, Any] = {}
    size = page.get("size")
    if size:
        kwargs["paper_size"] = _require_str(size, field="page.size")
    orientation = page.get("orientation")
    if orientation:
        if orientation not in ("portrait", "landscape"):
            raise SpecError("page.orientation 은 portrait 또는 landscape 여야 합니다.")
        kwargs["orientation"] = orientation

    margins = page.get("marginsMm")
    if margins is not None:
        if not isinstance(margins, (list, tuple)) or len(margins) != 4:
            raise SpecError("page.marginsMm 는 [왼쪽, 오른쪽, 위, 아래] 네 개여야 합니다.")
        try:
            left, right, top, bottom = (float(v) for v in margins)
        except (TypeError, ValueError):
            raise SpecError("page.marginsMm 의 값은 숫자여야 합니다.") from None
        kwargs["margins_mm"] = {"left": left, "right": right, "top": top, "bottom": bottom}

    if kwargs:
        try:
            document.set_page_setup(**kwargs)
        except Exception as exc:
            raise SpecError(f"쪽 설정을 적용하지 못했습니다: {exc}") from exc


def _add_heading(document, block: Dict[str, Any]) -> None:
    level = block.get("level", 1)
    if level not in _HEADING_STYLE:
        raise SpecError(f"heading.level 은 {sorted(_HEADING_STYLE)} 중 하나여야 합니다.")
    text = _require_str(block.get("text"), field="heading.text")
    style = document.ensure_run_style(bold=True, size=_HEADING_STYLE[level])
    document.add_paragraph(text, char_pr_id_ref=style)


def _add_paragraph(document, block: Dict[str, Any]) -> None:
    text = _require_str(block.get("text"), field="paragraph.text", allow_empty=True)
    document.add_paragraph(text)


def _add_table(document, block: Dict[str, Any]) -> None:
    columns = block.get("columns")
    rows = block.get("rows")
    if not isinstance(columns, list) or not columns:
        raise SpecError("table.columns 는 비어 있지 않은 배열이어야 합니다.")
    if not isinstance(rows, list):
        raise SpecError("table.rows 는 배열이어야 합니다.")

    width = len(columns)
    for index, row in enumerate(rows):
        if not isinstance(row, list):
            raise SpecError(f"table.rows[{index}] 는 배열이어야 합니다.")
        if len(row) != width:
            raise SpecError(
                f"table.rows[{index}] 의 칸 수({len(row)})가 columns({width})와 다릅니다."
            )
    total_cells = width * (len(rows) + 1)
    if total_cells > MAX_TABLE_CELLS:
        raise SpecError(f"표가 너무 큽니다({total_cells}칸, 상한 {MAX_TABLE_CELLS}칸).")

    table = document.add_table(rows=len(rows) + 1, cols=width)
    _make_table_flow(table)
    for column_index, header in enumerate(columns):
        table.set_cell_text(0, column_index, "" if header is None else str(header))
    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row):
            table.set_cell_text(row_index, column_index, "" if value is None else str(value))


def _make_table_flow(table) -> None:
    """긴 표가 쪽을 넘어 이어지게 한다.

    라이브러리는 표를 만들 때 `<hp:pos treatAsChar="1">` 을 박아 넣는다 — 표를 **글자 하나처럼**
    다루겠다는 뜻이라, 한/글에서 그 표는 쪽을 넘어 나뉘지 못한다. 40행짜리 표를 넣으면 첫 쪽에
    들어가는 만큼만 보이고 나머지는 잘린 것처럼 보인다(2026-08-30 한/글 확인에서 실제로 관찰됨 —
    데이터는 41행이 다 들어 있었고 표시만 잘렸다).

    `treatAsChar="0"` 이면 문단에 얹힌 블록 객체가 되어, 이미 붙어 있는 `pageBreak="CELL"` 규칙
    대로 셀 경계에서 나뉜다. 머리글 행도 쪽마다 반복하게 해서 두 번째 쪽부터 무슨 열인지 알 수 있게 한다.
    """
    element = getattr(table, "element", None)
    if element is None:
        return
    element.set("repeatHeader", "1")
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == "pos":
            child.set("treatAsChar", "0")
            break


def _add_image(document, block: Dict[str, Any], image_loader: Optional[ImageLoader]) -> None:
    artifact_id = block.get("artifactId")
    if not artifact_id:
        # 경로나 URL 을 받지 않는 것이 요점이다 — 받으면 서버 파일을 문서에 실어 보낼 수 있다.
        raise SpecError("image 블록은 artifactId 로만 지정할 수 있습니다(경로·URL 은 받지 않습니다).")
    if image_loader is None:
        raise SpecError("이 실행에서는 이미지를 넣을 수 없습니다(Artifact 해석기가 없습니다).")

    data, image_format = image_loader(str(artifact_id))
    image_format = str(image_format or "").lower().lstrip(".")
    if image_format not in IMAGE_FORMATS:
        raise SpecError(
            f"지원하지 않는 이미지 형식입니다: {image_format or '(알 수 없음)'} "
            f"— {', '.join(sorted(IMAGE_FORMATS))} 만 넣을 수 있습니다."
        )

    kwargs: Dict[str, Any] = {}
    if block.get("widthMm") is not None:
        try:
            kwargs["width_mm"] = float(block["widthMm"])
        except (TypeError, ValueError):
            raise SpecError("image.widthMm 는 숫자여야 합니다.") from None
    if block.get("heightMm") is not None:
        try:
            kwargs["height_mm"] = float(block["heightMm"])
        except (TypeError, ValueError):
            raise SpecError("image.heightMm 는 숫자여야 합니다.") from None
    document.add_picture(data, image_format, **kwargs)


def _add_page_break(document, block: Dict[str, Any]) -> None:
    # 새 문단에 pageBreak 속성을 달아 다음 내용이 새 쪽에서 시작하게 한다.
    document.add_paragraph("", pageBreak="1")


_BUILDERS = {
    "heading": lambda doc, block, loader: _add_heading(doc, block),
    "paragraph": lambda doc, block, loader: _add_paragraph(doc, block),
    "table": lambda doc, block, loader: _add_table(doc, block),
    "image": _add_image,
    "page_break": lambda doc, block, loader: _add_page_break(doc, block),
}


def validate_spec(spec: Dict[str, Any]) -> None:
    """만들기 전에 스펙만 본다. 절반쯤 만들어진 문서를 내보내지 않기 위해서다."""
    if not isinstance(spec, dict):
        raise SpecError("DocumentSpec 은 객체여야 합니다.")
    blocks = spec.get("blocks")
    if blocks is None:
        blocks = []
    if not isinstance(blocks, list):
        raise SpecError("blocks 는 배열이어야 합니다.")
    if len(blocks) > MAX_BLOCKS:
        raise SpecError(f"블록이 너무 많습니다({len(blocks)}개, 상한 {MAX_BLOCKS}개).")
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise SpecError(f"blocks[{index}] 는 객체여야 합니다.")
        kind = block.get("type")
        if kind not in _BUILDERS:
            raise UnsupportedFeature(
                f"blocks[{index}] 의 '{kind}' 는 아직 만들 수 없습니다. "
                f"지금 지원하는 것: {', '.join(SUPPORTED_BLOCKS)}"
            )


def build(spec: Dict[str, Any], output_path: str, *,
          image_loader: Optional[ImageLoader] = None) -> Dict[str, Any]:
    """`DocumentSpec` 대로 새 HWPX 를 만들어 저장하고, 무엇을 넣었는지 돌려준다."""
    from hwpx.document import HwpxDocument

    validate_spec(spec)

    document = HwpxDocument.new()
    _apply_page(document, spec.get("page") or {})

    title = spec.get("title")
    if title:
        _add_heading(document, {"level": 1, "text": _require_str(title, field="title")})

    counts: Dict[str, int] = {}
    for index, block in enumerate(spec.get("blocks") or []):
        kind = block["type"]
        try:
            _BUILDERS[kind](document, block, image_loader)
        except SpecError as exc:
            # 어느 블록에서 멈췄는지 알려준다 — 블록이 수십 개면 이게 없으면 못 찾는다.
            raise type(exc)(f"blocks[{index}]: {exc}") from None
        counts[kind] = counts.get(kind, 0) + 1

    document.save_to_path(output_path)
    return {
        "path": output_path,
        "title": title or "",
        "blocks": counts,
        "blockCount": sum(counts.values()),
    }
