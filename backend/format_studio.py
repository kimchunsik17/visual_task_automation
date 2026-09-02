"""format_studio.py — 포맷 스튜디오의 AI 생성 (`POST /api/formats/generate`).

자연어 요청("시말서 양식 만들어줘", "세미나 포스터")을 FormatSpec 초안으로 만든다.
생성 결과는 저장이 아니라 **스튜디오 편집기에 로드되는 초안**이다 — 사용자가 다듬고 저장한다.

생성 LLM 의 출력은 Structured Output 으로 FormatSpec 골격을 강제하고, 마지막에
validate_format_spec 을 통과한 것만 돌려준다(미선언 변수 참조 같은 스펙 위반은 여기서 걸린다).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from documents.format_spec import FormatSpecError, validate_format_spec

MAX_PROMPT_CHARS = 2000


# ── Structured Output 스키마 ─────────────────────────────────────────────
# blocks/design 을 느슨한 dict 로 받으면 LLM 이 지원 밖 블록을 지어내므로, 스키마 수준에서
# 형태를 강제하고 세부 규칙(참조 무결성 등)은 validate_format_spec 이 마저 잡는다.

class GeneratedField(BaseModel):
    name: str = Field(description="영문 camelCase 필드 이름 (예: authorName)")
    label: str = Field(description="사람이 읽는 한국어 라벨")
    kind: Literal["text", "multiline", "rows", "image"] = "text"
    required: bool = False
    columns: Optional[List[str]] = Field(default=None, description="kind=rows 일 때 열 이름들")
    example: Optional[str] = Field(default=None, description="미리보기용 예시값")


class GeneratedBlock(BaseModel):
    type: Literal["heading", "paragraph", "table", "image", "page_break"]
    level: Optional[int] = Field(default=None, description="heading 전용: 1|2|3")
    text: Optional[str] = Field(default=None, description="heading/paragraph 의 내용. {{필드이름}} 참조 가능")
    columns: Optional[List[str]] = Field(default=None, description="정적 table 의 열 이름들")
    rows: Optional[List[List[str]]] = Field(default=None, description="정적 table 의 행들. 셀에 {{필드}} 가능")
    fromField: Optional[str] = Field(default=None, description="table←rows 필드 / image←image 필드 연결")


class GeneratedDesign(BaseModel):
    width: int = Field(default=794, description="px. 세로 A4=794×1123, 가로=1123×794")
    height: int = 1123
    html: str = Field(description="body 안에 들어갈 HTML. 텍스트 자리는 {{필드}}, 이미지 자리는 <img data-field=\"필드이름\">")
    css: str = Field(description="스타일. 색·글꼴은 var(--fs-primaryColor) 같은 테마 변수를 쓴다")
    theme: Dict[str, str] = Field(
        default_factory=lambda: {"primaryColor": "#4f7cff", "backgroundColor": "#ffffff",
                                 "textColor": "#0f172a", "mutedColor": "#5b6474",
                                 "fontFamily": "Pretendard"})


class GeneratedFormatSpec(BaseModel):
    name: str = Field(description="포맷 이름 (예: 시말서)")
    description: str = ""
    layout: Literal["document", "design"]
    fields: List[GeneratedField]
    blocks: Optional[List[GeneratedBlock]] = Field(default=None, description="layout=document 전용")
    design: Optional[GeneratedDesign] = Field(default=None, description="layout=design 전용")


_SYSTEM = """너는 문서 포맷 설계 도우미다. 사용자의 요청을 읽고 FormatSpec(빈칸 선언 + 골격)을 만든다.

[공통 규칙]
- fields 가 빈칸의 정본이다. 골격이 참조하는 모든 {{이름}} 과 fromField 는 fields 에 선언돼야 한다.
- 반대로, required=true 로 선언한 필드는 골격 어디선가 반드시 쓰여야 한다.
- 고정 문구(제목·항목명·안내문)는 골격에 그대로 쓰고, 실행마다 달라질 내용만 빈칸으로 만든다.
- 필드 이름은 영문 camelCase, 라벨은 한국어. 미리보기용 example 을 가능한 한 채운다.

[layout=document — 시말서·제안서·보고서 같은 문서]
- blocks 만 쓴다. 블록은 heading(level 1~3)·paragraph·table·image·page_break 다섯 가지뿐이다.
- 반복되는 행(경력 사항, 일정표 등)은 kind=rows 필드(columns 포함)를 선언하고
  {"type":"table","fromField":"필드이름"} 으로 연결한다.
- 서명/사진은 kind=image 필드 + {"type":"image","fromField":"필드이름"} 으로.
- 정적 표(항목|내용 2열 인적사항 등)는 columns/rows 를 직접 쓰고 셀에 {{필드}} 를 넣는다.

[layout=design — 포스터·팜플렛·카드뉴스]
- design(html/css/theme)만 쓴다. 너는 전문 그래픽 디자이너다 — 여백·타이포 위계·색 대비를 갖춘
  완성된 레이아웃을 만들어라. 밋밋한 흰 배경에 텍스트 나열은 실패작이다.
- html 은 body 안 내용만. 텍스트 자리는 {{필드}}, 이미지 자리는 <img data-field="필드이름">.
- 색·글꼴은 반드시 theme 변수(css 에서 var(--fs-primaryColor) 등)로 써라 — 사용자가 테마만 바꿔서
  다른 분위기를 낼 수 있어야 한다. theme 키: primaryColor·backgroundColor·textColor·mutedColor·fontFamily.
- 크기: 세로 포스터 794×1123, 가로 팜플렛 1123×794. 루트 요소는 width:100%; height:100vh 로 채워라.
- script/iframe/외부 URL 은 금지다(렌더러가 차단한다).

요청이 문서인지 디자인물인지 분명치 않으면 문서(document)로 만든다."""


_IMPORT_SYSTEM = _SYSTEM + """

[가져온 문서를 포맷으로 바꾸는 작업 — 추가 규칙]
- 아래에 주어지는 것은 사용자가 올린 **실제 서식 파일**에서 추출한 구조(fields + blocks)다.
  이 문서의 골격을 재사용 가능한 포맷으로 바꿔라.
- 골격의 고정 문구(제목·항목명·안내문)는 **원문 그대로 유지한다** — 새로 지어내거나 빼지 마라.
  블록의 순서·구성도 유지한다(제목으로 보이는 짧은 첫 문단을 heading 으로 승격하는 것은 좋다).
- 실행마다 달라질 값(사람 이름·날짜·금액·본문 내용 등)만 빈칸으로 선언하고, 그 자리를
  {{필드이름}} 으로 바꿔라. 표의 "값" 칸(예: 항목|내용 2열의 내용 쪽)이 대표적인 빈칸이다.
- 이미 선언돼 있는 fields 는 이름을 그대로 유지하고(label·kind 는 다듬어도 된다) 지우지 마라.
- 확신이 없는 자리는 고정 문구로 남겨라 — 빈칸을 과하게 만드는 것보다 낫다."""

# 가져온 구조가 이보다 크면 LLM 다듬기를 건너뛴다(토큰·지연) — 결정적 초안은 그대로 쓸 수 있다.
MAX_IMPORT_STRUCT_CHARS = 12000


def refine_imported_spec(draft: Dict[str, Any]) -> Dict[str, Any]:
    """가져오기 초안(format_import.spec_from_file)을 근거로 빈칸을 제안한다.

    실패해도 초안이 정본이다 — 호출자(/api/formats/import)는 예외를 받으면 초안을 그대로
    돌려주고 응답에 건너뛴 이유를 명시한다(조용한 실패 금지).
    """
    payload = json.dumps({"fields": draft.get("fields"), "blocks": draft.get("blocks")},
                         ensure_ascii=False)
    if len(payload) > MAX_IMPORT_STRUCT_CHARS:
        raise FormatSpecError(
            f"문서가 너무 커서 AI 다듬기를 건너뜁니다({len(payload)}자, 상한 {MAX_IMPORT_STRUCT_CHARS}자).")

    from meta_agent import get_llm
    llm = get_llm(complexity_level="medium").with_structured_output(
        GeneratedFormatSpec, method="function_calling")
    generated = llm.invoke([
        ("system", _IMPORT_SYSTEM),
        ("user", f"가져온 문서 구조:\n{payload}\n(layout 은 반드시 document 로 만들어라.)"),
    ])

    spec = generated.model_dump(exclude_none=True)
    spec["layout"] = "document"
    spec.pop("design", None)
    # 이름·출력 형식은 파일에서 온 초안이 정본이다(이름은 파일 이름, 출력 기본값은 원본 확장자).
    spec["name"] = draft.get("name") or spec.get("name")
    refined = validate_format_spec(spec)
    if draft.get("output"):
        refined["output"] = draft["output"]
    return refined


def generate_format_spec(prompt: str, layout_hint: str = "") -> Dict[str, Any]:
    """요청문 → 검증까지 통과한 FormatSpec dict. 실패는 FormatSpecError 로 올린다."""
    prompt = str(prompt or "").strip()
    if not prompt:
        raise FormatSpecError("요청 내용이 비어 있습니다.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise FormatSpecError(f"요청이 너무 깁니다(상한 {MAX_PROMPT_CHARS}자).")

    from meta_agent import get_llm
    llm = get_llm(complexity_level="medium").with_structured_output(
        GeneratedFormatSpec, method="function_calling")

    hint = ""
    if layout_hint in ("document", "design"):
        hint = f"\n(layout 은 반드시 {layout_hint} 로 만들어라.)"
    generated = llm.invoke([
        ("system", _SYSTEM),
        ("user", f"요청: {prompt}{hint}"),
    ])

    spec = generated.model_dump(exclude_none=True)
    # Structured Output 이 채운 layout 별 여분 골격 제거 (document 인데 design 이 있는 등)
    if spec.get("layout") == "document":
        spec.pop("design", None)
    else:
        spec.pop("blocks", None)
    return validate_format_spec(spec)
