"""regex_assist.py — 설명 → 정규식 제안 (regexExtractNode 의 AI 도우미, 백로그 34 DEV-2).

노드 자체는 LLM 을 쓰지 않는다 — 실행은 결정적이어야 한다. 대신 **편집할 때** 한 번, "무엇을 뽑을지" 를 말로 적으면 정규식을 만들어
주고, 만든 정규식을 여기서 컴파일해 보고 샘플에 실제로 적용한 결과까지 함께 돌려준다. 컴파일이 안 되는 정규식은 오류 문구를 붙여
한 번 더 시도한다 — 사용자에게 깨진 정규식을 채워 주는 것이 가장 나쁜 결과다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import text_tools

MAX_DESCRIPTION_CHARS = 2_000
MAX_SAMPLE_CHARS = 20_000
PREVIEW_LIMIT = 5

_SYSTEM = (
    "너는 Python `re` 정규식을 만드는 도우미다. 사용자가 텍스트에서 무엇을 뽑고 싶은지 설명하면 그 값을 잡는 정규식을 하나 만든다.\n"
    "규칙: (1) Python re 문법만. 룩비하인드 가변 길이·재귀·\\K 같은 PCRE 전용 기능은 쓰지 않는다. (2) 뽑을 값은 이름 그룹 (?P<이름>...) 으로 "
    "감싼다 — 이름은 영문 소문자·숫자·밑줄. (3) 샘플이 있으면 샘플에서 실제로 맞도록 만든다. (4) 필요 이상으로 넓게 잡지 않는다 — .* 대신 "
    "구체적인 문자 클래스. (5) 대소문자 무시·여러 줄·점이 줄바꿈 포함이 필요하면 해당 플래그를 true 로. (6) explanation 은 한국어 한두 문장."
)


class SuggestedRegex(BaseModel):
    pattern: str = Field(description="Python re 문법 정규식. 뽑을 값은 (?P<이름>...) 이름 그룹으로")
    ignore_case: bool = Field(default=False, description="대소문자를 무시해야 하면 true")
    multiline: bool = Field(default=False, description="^ $ 가 줄마다 맞아야 하면 true")
    dot_all: bool = Field(default=False, description=". 이 줄바꿈도 포함해야 하면 true")
    explanation: str = Field(default="", description="이 정규식이 무엇을 어떻게 잡는지 한국어 한두 문장")


class RegexAssistError(ValueError):
    """사용자에게 그대로 보여도 되는 실패."""


def _default_llm():
    from meta_agent import get_llm

    return get_llm(complexity_level="low").with_structured_output(SuggestedRegex, method="function_calling")


def _user_message(description: str, sample: str, previous_error: Optional[str] = None) -> str:
    text = f"뽑고 싶은 것: {description}"
    if sample:
        text += f"\n\n샘플 텍스트:\n```\n{sample}\n```"
    if previous_error:
        text += f"\n\n앞서 만든 정규식은 Python 에서 컴파일되지 않았다: {previous_error}\n같은 목적의 올바른 정규식을 다시 만들어라."
    return text


def suggest(description: str, sample: str = "", *, llm: Any = None) -> Dict[str, Any]:
    """설명(+샘플) → {pattern, ignoreCase, multiline, dotAll, explanation, matchCount, preview}. 실패는 RegexAssistError."""
    description = str(description or "").strip()
    sample = str(sample or "")
    if not description:
        raise RegexAssistError("무엇을 뽑을지 설명을 적어 주세요.")
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise RegexAssistError(f"설명이 너무 깁니다(상한 {MAX_DESCRIPTION_CHARS:,}자).")
    if len(sample) > MAX_SAMPLE_CHARS:
        sample = sample[:MAX_SAMPLE_CHARS]

    llm = llm or _default_llm()
    previous_error: Optional[str] = None
    generated: Optional[SuggestedRegex] = None
    for _attempt in range(2):
        candidate = llm.invoke([("system", _SYSTEM), ("user", _user_message(description, sample, previous_error))])
        if not isinstance(candidate, SuggestedRegex):
            candidate = SuggestedRegex.model_validate(candidate if isinstance(candidate, dict) else getattr(candidate, "__dict__", {}))
        try:
            text_tools.regex_extract("", candidate.pattern, mode="test", ignore_case=candidate.ignore_case,
                                     multiline=candidate.multiline, dot_all=candidate.dot_all)
        except text_tools.ToolError as exc:
            previous_error = str(exc)
            continue
        generated = candidate
        break
    if generated is None:
        raise RegexAssistError(f"컴파일되는 정규식을 만들지 못했습니다: {previous_error}")

    matches: List[Any] = []
    if sample:
        matches = text_tools.regex_extract(sample, generated.pattern, mode="all", ignore_case=generated.ignore_case,
                                           multiline=generated.multiline, dot_all=generated.dot_all)
    preview = [m.get("match") if isinstance(m, dict) else m for m in matches[:PREVIEW_LIMIT]]
    return {
        "pattern": generated.pattern,
        "ignoreCase": generated.ignore_case,
        "multiline": generated.multiline,
        "dotAll": generated.dot_all,
        "explanation": generated.explanation,
        "matchCount": len(matches),
        "preview": preview,
    }
