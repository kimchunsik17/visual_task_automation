"""node_errors/catalog.py — 중앙 오류 catalog 로더와 검증 (ADR-0016).

정본은 저장소 루트 `error_catalog.json` 하나다. 여기서 읽어 검증하고, 프론트엔드 번들과
문서는 `export_node_definitions.py` 가 이 모듈의 payload 로 만든다(ADR-0005/0007 과 같은 방식).

검증은 로딩 시점에 한 번 하고 실패하면 예외로 멈춘다 — code 중복·형식 위반·없는 category 를
런타임 오류로 발견하는 것보다 CI(test_node_errors) 에서 잡는 편이 낫다.
"""

from __future__ import annotations

import json
import pathlib
import re
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

CATALOG_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "error_catalog.json"

CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
MESSAGE_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$")

EffectState = Literal["not_applicable", "not_started", "unknown", "applied"]
EFFECT_STATES = ("not_applicable", "not_started", "unknown", "applied")

# 이 상태에서는 "다시 보내면 두 번 갈 수 있다" — 자동 재시도를 절대 하지 않는다.
UNSAFE_TO_RETRY_EFFECT_STATES = frozenset({"unknown", "applied"})


class CatalogError(ValueError):
    """catalog 파일 자체가 잘못됐다(형식·중복·참조)."""


class UnknownErrorCode(KeyError):
    """catalog 에 없는 code 를 쓰려 했다 — 프로그래밍 오류다. 새 code 는 catalog 에 먼저 등록한다."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryMeta(_Strict):
    label: str
    icon: str
    description: str = ""


class ResolutionMeta(_Strict):
    label: str
    kind: Literal["navigate", "focus_field", "retry", "manual", "copy_request_id", "none"]
    target: Optional[str] = None


class ErrorCodeEntry(_Strict):
    code: str
    category: str
    owner: str
    messageKey: str
    userMessage: str
    retryable: bool = False
    effectStateDefault: EffectState = "not_applicable"
    resolution: str = "none"
    safeDetailKeys: List[str] = Field(default_factory=list)
    docs: Optional[str] = None
    deprecated: bool = False
    replacedBy: Optional[str] = None
    # 한 릴리스 동안만 유지하는 이행용 code(LEGACY_NODE_ERROR). 신규 분기가 의존하면 안 된다.
    transitional: bool = False

    @field_validator("code")
    @classmethod
    def _code_format(cls, value: str) -> str:
        if not CODE_RE.match(value):
            raise ValueError(f"code '{value}' 는 SCREAMING_SNAKE_CASE 의 DOMAIN_REASON 형식이어야 한다")
        return value

    @field_validator("messageKey")
    @classmethod
    def _message_key_format(cls, value: str) -> str:
        if not MESSAGE_KEY_RE.match(value):
            raise ValueError(f"messageKey '{value}' 는 'domain.reason' 형식이어야 한다")
        return value

    @field_validator("safeDetailKeys")
    @classmethod
    def _safe_keys_unique(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("safeDetailKeys 에 중복이 있다")
        for key in value:
            if not re.match(r"^[a-z][A-Za-z0-9]*$", key):
                raise ValueError(f"safeDetailKeys '{key}' 는 camelCase 여야 한다")
        return value


class ErrorCatalog(_Strict):
    version: int
    categories: Dict[str, CategoryMeta]
    resolutions: Dict[str, ResolutionMeta]
    codes: List[ErrorCodeEntry]
    # JSON 의 설명용 필드. 검증 대상은 아니다.
    _comment: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def problems(self) -> List[str]:
        """CI 가 막아야 하는 것들. 빈 리스트면 정상."""
        issues: List[str] = []
        seen: Dict[str, int] = {}
        message_keys: Dict[str, str] = {}
        for entry in self.codes:
            seen[entry.code] = seen.get(entry.code, 0) + 1
            if entry.category not in self.categories:
                issues.append(f"{entry.code}: category '{entry.category}' 가 categories 에 없다")
            if entry.resolution not in self.resolutions:
                issues.append(f"{entry.code}: resolution '{entry.resolution}' 이 resolutions 에 없다")
            if entry.messageKey in message_keys and message_keys[entry.messageKey] != entry.code:
                issues.append(f"{entry.code}: messageKey '{entry.messageKey}' 가 {message_keys[entry.messageKey]} 와 겹친다")
            message_keys.setdefault(entry.messageKey, entry.code)
            if entry.deprecated and not entry.replacedBy:
                issues.append(f"{entry.code}: deprecated 인데 replacedBy 가 없다")
            if entry.replacedBy and not entry.deprecated:
                issues.append(f"{entry.code}: replacedBy 는 deprecated=true 일 때만 쓴다")
            if entry.retryable and entry.effectStateDefault in UNSAFE_TO_RETRY_EFFECT_STATES:
                issues.append(f"{entry.code}: effectStateDefault={entry.effectStateDefault} 인 code 는 retryable 기본값이 true 일 수 없다")
        for code, count in seen.items():
            if count > 1:
                issues.append(f"code '{code}' 가 {count}번 선언됐다")
        for entry in self.codes:
            if entry.replacedBy:
                target = next((e for e in self.codes if e.code == entry.replacedBy), None)
                if target is None:
                    issues.append(f"{entry.code}: replacedBy '{entry.replacedBy}' 가 catalog 에 없다")
                elif target.deprecated:
                    issues.append(f"{entry.code}: replacedBy '{entry.replacedBy}' 도 deprecated 다 — 살아있는 code 를 가리켜야 한다")
        return issues


@lru_cache(maxsize=1)
def load() -> ErrorCatalog:
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError(f"오류 catalog 가 없다: {CATALOG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"오류 catalog JSON 이 잘못됐다: {exc}") from exc
    comment = raw.pop("_comment", None)
    try:
        catalog = ErrorCatalog.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise CatalogError(f"오류 catalog 검증 실패: {exc}") from exc
    catalog._comment = comment
    problems = catalog.problems()
    if problems:
        raise CatalogError("오류 catalog 검증 실패:\n- " + "\n- ".join(problems))
    return catalog


def _index() -> Dict[str, ErrorCodeEntry]:
    return {entry.code: entry for entry in load().codes}


def get(code: str) -> ErrorCodeEntry:
    """code 의 catalog 항목. deprecated 항목은 그대로 돌려준다 — 대체 판단은 `resolve()` 가 한다."""
    entry = _index().get(code)
    if entry is None:
        raise UnknownErrorCode(code)
    return entry


def resolve(code: str) -> ErrorCodeEntry:
    """deprecated alias 면 대체 code 항목을 돌려준다(한 단계만 — 체인은 catalog 검증이 막는다)."""
    entry = get(code)
    if entry.deprecated and entry.replacedBy:
        return get(entry.replacedBy)
    return entry


def has(code: str) -> bool:
    return code in _index()


def all_codes() -> List[str]:
    return [entry.code for entry in load().codes]


def categories() -> Dict[str, CategoryMeta]:
    return load().categories


def resolutions() -> Dict[str, ResolutionMeta]:
    return load().resolutions


def payload() -> Dict[str, Any]:
    """프론트엔드 번들용. 클라이언트는 code → category/resolution/메시지 fallback 을 여기서 찾는다."""
    catalog = load()
    return {
        "version": catalog.version,
        "categories": {key: meta.model_dump() for key, meta in catalog.categories.items()},
        "resolutions": {key: meta.model_dump() for key, meta in catalog.resolutions.items()},
        "codes": {
            entry.code: {
                "category": entry.category,
                "messageKey": entry.messageKey,
                "userMessage": entry.userMessage,
                "retryable": entry.retryable,
                "effectStateDefault": entry.effectStateDefault,
                "resolution": entry.resolution,
                "deprecated": entry.deprecated,
                "replacedBy": entry.replacedBy,
                "transitional": entry.transitional,
            }
            for entry in catalog.codes
        },
    }


def render_markdown() -> str:
    """`Documents/ERROR_CATALOG.md` — catalog 의 docs 링크가 가리키는 문서. 사람이 고치지 않는다."""
    catalog = load()
    lines = [
        "# 공통 오류 catalog (NodeError v1)",
        "",
        "이 문서는 `error_catalog.json` 에서 `python backend/export_node_definitions.py` 가 생성한다.",
        "직접 고치지 마라 — 정본을 고치고 다시 생성한다(ADR-0016).",
        "",
        "| code | category | owner | 기본 retry | effectState 기본 | 해결 동작 | 사용자 문구 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in catalog.codes:
        resolution = catalog.resolutions[entry.resolution].label
        flags = " (deprecated → " + entry.replacedBy + ")" if entry.deprecated else (" (이행용)" if entry.transitional else "")
        lines.append(
            f"| <a id=\"{entry.code.lower()}\"></a>`{entry.code}`{flags} | {entry.category} | {entry.owner} | "
            f"{'예' if entry.retryable else '아니오'} | `{entry.effectStateDefault}` | {resolution} | {entry.userMessage} |"
        )
    lines += [
        "",
        "## safeDetails 허용 key",
        "",
        "공개 payload 의 `safeDetails` 에는 아래 key 만 들어갈 수 있다. provider 원문, stack, SQL, credential, 경로는 어떤 key 로도 넣지 않는다.",
        "",
    ]
    for entry in catalog.codes:
        keys = ", ".join(f"`{k}`" for k in entry.safeDetailKeys) or "(없음)"
        lines.append(f"- `{entry.code}`: {keys}")
    lines.append("")
    return "\n".join(lines)
