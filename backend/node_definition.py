"""node_definition.py — NodeDefinition v1 로더/검증기/카탈로그 렌더러 (ADR-0005).

노드 하나의 UI 필드, 기본값, 조건부 표시, 허용값, 검증 메시지, LLM 카탈로그 설명을
저장소 루트 `node_definitions/<type>.json` 한 곳에서 관리한다. 예전에는 같은 사실이
세 곳에 흩어져 있었다:

  - 프론트 설정 UI      : frontend/src/customNodes.jsx 의 노드별 JSX
  - 서버 validator      : meta_agent._validate_node_data 의 type별 if/elif
  - LLM 노드 카탈로그   : meta_agent.NODE_CATALOG 문자열

셋이 서로 모르는 사이라 허용값 하나만 바뀌어도 세 파일을 같이 고쳐야 했고, 실제로
어긋나면 "UI에서는 고를 수 있는데 검증에서 막히는" 종류의 버그가 났다. 이 모듈은
정의 파일을 읽어 세 소비자에게 같은 사실을 공급한다.

■ v1 범위: httpRequestNode, llmNode, conditionNode (vertical slice)
■ 검증 메시지는 이전 하드코딩 구현의 문구를 그대로 옮겼다 — flow_validation.py 의
  정규식 규칙(NODE_DATA_INVALID 등)과 repair 로직이 메시지 문구에 의존하기 때문이다.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

import node_bindings
from connectors import mock_runtime
from connectors.contract import ConnectorSpec

# backend/ 의 부모 = 저장소 루트. 정의 파일은 프론트/백엔드 어느 쪽 소유도 아니므로
# 루트에 둔다(프론트는 export_node_definitions.py 가 만든 번들을 읽는다).
DEFINITIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "node_definitions"

# NODE_CATALOG 항목의 '- nodeType      : ' 접두사 폭. 기존 카탈로그 원문과 동일하게 맞춘다.
_CATALOG_TYPE_WIDTH = 15


class _Strict(BaseModel):
    """정의 파일의 오타를 로딩 시점에 잡기 위해 모르는 키를 거부한다."""

    model_config = ConfigDict(extra="forbid")


class WhenClause(_Strict):
    field: str
    truthy: bool = True
    # equals가 있으면 truthy 대신 값 일치로 판정한다 (예: mode == "extract"일 때만 적용).
    equals: Optional[Any] = None
    # 값이 이 접두사로 시작하면 게이트를 닫는다. discordNode 의 botToken 처럼 한 필드가 두 가지
    # 형태(Webhook URL / 봇 토큰)를 겸할 때, 한쪽에서만 필요한 후속 필드를 가리키기 위한 것이다.
    notStartsWith: Optional[str] = None


class ValidationRule(_Strict):
    # digits: 값이 있을 때만, 숫자로만 이뤄졌는지 본다(존재 여부는 required/present가 담당).
    #         Discord 채널 ID 같은 스노우플레이크 식별자가 지어낸 값인지 거르는 용도다.
    rule: Literal["required", "present", "enum", "jsonObject", "unique", "number", "digits"]
    message: str
    # number: 값이 있을 때만 검사한다(존재 여부는 required/present가 담당).
    #         message는 숫자가 아닐 때, minMessage는 min 미만일 때의 문구다.
    min: Optional[float] = None
    minMessage: Optional[str] = None
    # enum: 허용값은 같은 필드의 options에서 가져온다(UI 선택지 = 검증 허용값 보장).
    allowMissing: bool = False
    # jsonObject: 파싱된 최상위 객체에 반드시 있어야 하는 키 -> 없을 때의 메시지
    requireKeys: Dict[str, str] = Field(default_factory=dict)
    # 다른 필드가 truthy일 때만 이 규칙을 적용한다.
    when: Optional[WhenClause] = None


class FieldOption(_Strict):
    value: Any
    label: str


class ShowWhen(_Strict):
    field: str
    truthy: bool = True
    equals: Optional[Any] = None
    # 값이 여럿일 때. `equals` 하나로는 "inspect 이거나 validate 일 때" 를 못 쓴다 —
    # 그러면 필드를 늘 보이게 두거나 같은 필드를 두 벌 선언하게 된다.
    oneOf: Optional[List[Any]] = None


class CredentialRef(_Strict):
    provider: str


class NodeField(_Strict):
    name: str
    # "attachments" 는 발송 노드의 첨부 포트 설정이다(ADR-0018) — 값이 아니라 파일 참조
    # (artifactId)를 담고, 편집기는 파일 chip 과 provider 한도를 보여준다.
    kind: Literal["text", "textarea", "number", "checkbox", "select", "secret", "json",
                  "repeatable", "attachments"]
    label: Optional[str] = None
    placeholder: Optional[str] = None
    default: Any = None
    options: List[FieldOption] = Field(default_factory=list)
    showWhen: Optional[ShowWhen] = None
    credential: Optional[CredentialRef] = None
    ui: Dict[str, Any] = Field(default_factory=dict)
    validation: List[ValidationRule] = Field(default_factory=list)
    # kind == "repeatable" 일 때 각 항목이 갖는 필드들과, 오류 메시지에서 항목을
    # 가리킬 때 쓸 필드 이름(값이 비어 있으면 '#인덱스'로 대신한다).
    itemFields: List["NodeField"] = Field(default_factory=list)
    labelField: Optional[str] = None


class NodeDisplay(_Strict):
    label: str
    collapsedLabel: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    headerColor: Optional[str] = None


class NodePort(_Strict):
    name: str
    dataType: str = "any"
    label: Optional[str] = None


class DynamicOutputs(_Strict):
    from_: str = Field(alias="from")
    idField: str

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class NodeCredential(_Strict):
    name: str
    provider: str
    optional: bool = False


class LLMMeta(_Strict):
    # NODE_CATALOG 항목 본문. '- nodeType      : ' 접두사를 뺀 나머지(줄바꿈 포함) 원문.
    description: str


class NodeDefinition(_Strict):
    type: str
    version: int
    category: str
    display: NodeDisplay
    inputs: List[NodePort] = Field(default_factory=list)
    outputs: List[NodePort] = Field(default_factory=list)
    dynamicOutputs: Optional[DynamicOutputs] = None
    fields: List[NodeField] = Field(default_factory=list)
    credentials: List[NodeCredential] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    sideEffect: Literal["none", "external-read", "external-write"] = "none"
    executor: str
    # 목업 계약. v1에서는 빈 채로 두고 Mock 탭 vertical slice(백로그 7)에서 채운다.
    mock: Dict[str, Any] = Field(default_factory=dict)
    # 공식 연동 노드만 갖는 블록(ADR-0007). 서비스, 동작 모드, 필요한 scope, 재시도/페이지네이션
    # 정책, 모드별 부수효과를 선언한다. 연동이 아닌 노드는 이 블록이 없다.
    connector: Optional[ConnectorSpec] = None
    llm: LLMMeta

    def field(self, name: str) -> Optional[NodeField]:
        return next((f for f in self.fields if f.name == name), None)

    def new_session(self, **kwargs):
        """이 노드의 정책이 반영된 호출 창구를 만든다.

        mock 실행 모드(ADR-0009)가 켜져 있으면 실제 네트워크 대신 이 정의의 `mock` 시나리오를
        재생하는 transport 를 끼운다. 노드 실행 코드는 mock 인지 아닌지를 알 필요가 없다.
        """
        if self.connector is None:
            raise ValueError(f"{self.type}: connector 블록이 없어 세션을 만들 수 없다")
        if "transport" not in kwargs:
            transport = mock_runtime.transport_for(self)
            if transport is not None:
                kwargs["transport"] = transport
                # 목업에서는 재시도 대기를 실제로 자지 않는다 — 기다릴 시간은 기록만 한다.
                kwargs.setdefault("sleep", mock_runtime.sleeper())
        return self.connector.new_session(**kwargs)


NodeField.model_rebuild()


def _load() -> Dict[str, NodeDefinition]:
    definitions: Dict[str, NodeDefinition] = {}
    if not DEFINITIONS_DIR.is_dir():
        return definitions
    for path in sorted(DEFINITIONS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        defn = NodeDefinition.model_validate(raw)
        if defn.type != path.stem:
            raise ValueError(f"{path.name}: 파일명과 type('{defn.type}')이 다르다")
        if defn.connector is not None:
            problems = defn.connector.validate_against_registry()
            # mock 계약도 같이 본다 — "성공만 흉내 내는 mock" 은 목업 탭에서 초록불을 켜면서
            # 실제로 사용자를 막는 경로를 하나도 알려주지 않는다(connectors/mock.py 의 규칙).
            from connectors import mock as _mock_fixtures
            problems += _mock_fixtures.validate_mock(defn.mock, defn.connector, label=defn.type)
            if problems:
                raise ValueError(f"{path.name}: " + "; ".join(problems))
        definitions[defn.type] = defn
    return definitions


NODE_DEFINITIONS: Dict[str, NodeDefinition] = _load()


def get_definition(node_type: str) -> Optional[NodeDefinition]:
    return NODE_DEFINITIONS.get(node_type)


def defined_types() -> List[str]:
    return sorted(NODE_DEFINITIONS)


def option_values(node_type: str, field_path: str) -> set:
    """'model' 또는 'rules.operator'(repeatable 항목 필드) 형태의 경로에서 허용값 집합을 얻는다.
    ALLOWED_MODELS 같은 상수를 정의에서 파생시키기 위한 진입점."""
    defn = NODE_DEFINITIONS.get(node_type)
    if defn is None:
        return set()
    head, _, tail = field_path.partition(".")
    field = defn.field(head)
    if field is None:
        return set()
    if tail:
        field = next((f for f in field.itemFields if f.name == tail), None)
        if field is None:
            return set()
    return {opt.value for opt in field.options}


# ── 검증 ────────────────────────────────────────────────────────────────
def _format(message: str, *, node_id: str, value: Any = None, allowed: str = "", label: str = "") -> str:
    return message.format(
        node_id=node_id,
        value=value,
        value_repr=repr(value),
        allowed=allowed,
        label=label,
    )


def _gate_open(rule: ValidationRule, scope: Dict[str, Any]) -> bool:
    if rule.when is None:
        return True
    if rule.when.equals is not None:
        return scope.get(rule.when.field) == rule.when.equals
    if bool(scope.get(rule.when.field)) != rule.when.truthy:
        return False
    if rule.when.notStartsWith is not None:
        return not str(scope.get(rule.when.field) or "").startswith(rule.when.notStartsWith)
    return True


def _check_rule(
    rule: ValidationRule,
    field: NodeField,
    scope: Dict[str, Any],
    node_id: str,
    label: str,
    seen: Optional[set] = None,
    bound_fields: frozenset = frozenset(),
) -> Optional[str]:
    """규칙 하나를 평가해 위반 메시지를 돌려준다(통과면 None)."""
    if not _gate_open(rule, scope):
        return None
    value = scope.get(field.name)

    if rule.rule == "required":
        # 데이터 바인딩이 걸린 필드는 값이 실행 시점에 앞 노드에서 온다 — 지금 비어 있는 게 정상이다.
        # 이 예외가 없으면 "toEmail 을 웹훅 값에 연결" 이 검증에서 계속 막힌다(계획 §6).
        if not value and field.name not in bound_fields:
            return _format(rule.message, node_id=node_id, value=value, label=label)

    elif rule.rule == "present":
        # value=""는 "비어있는지 검사"하는 정상적인 규칙이라 통과시키고, 키 자체가
        # 없거나 None인 경우만 위반으로 본다.
        if field.name not in scope or value is None:
            return _format(rule.message, node_id=node_id, value=value, label=label)

    elif rule.rule == "enum":
        allowed_values = {opt.value for opt in field.options}
        allowed_text = ", ".join(sorted(str(v) for v in allowed_values))
        missing = field.name not in scope or value is None
        if missing and rule.allowMissing:
            return None
        if missing or value not in allowed_values:
            return _format(rule.message, node_id=node_id, value=value, allowed=allowed_text, label=label)

    elif rule.rule == "unique":
        if seen is not None and value is not None:
            if value in seen:
                return _format(rule.message, node_id=node_id, value=value, label=label)
            seen.add(value)

    elif rule.rule == "number":
        if field.name in scope and value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return _format(rule.message, node_id=node_id, value=value, label=label)
            if rule.min is not None and number < rule.min:
                return _format(rule.minMessage or rule.message, node_id=node_id, value=value, label=label)

    elif rule.rule == "digits":
        if value not in (None, "") and not str(value).isdigit():
            return _format(rule.message, node_id=node_id, value=value, label=label)

    elif rule.rule == "jsonObject":
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return _format(rule.message, node_id=node_id, value=value, label=label)
        if isinstance(parsed, dict):
            for key, key_message in rule.requireKeys.items():
                if not parsed.get(key):
                    return _format(key_message, node_id=node_id, value=value, label=label)

    return None


def _validate_field(
    field: NodeField,
    scope: Dict[str, Any],
    node_id: str,
    label: str = "",
    seen: Optional[Dict[str, set]] = None,
    bound_fields: frozenset = frozenset(),
) -> List[str]:
    """한 필드의 규칙을 순서대로 보되, 첫 위반에서 멈춘다(예전 if/elif 사슬과 동일한 동작)."""
    for rule in field.validation:
        message = _check_rule(
            rule, field, scope, node_id, label,
            seen=None if seen is None else seen.setdefault(field.name, set()),
            bound_fields=bound_fields,
        )
        if message:
            return [message]
    return []


def validate_node_data(node_type: str, node_id: str, data: Optional[Dict[str, Any]]) -> List[str]:
    """정의에 선언된 필수/허용값/조건부 규칙으로 노드 data를 검증한다.
    정의가 없는 노드 타입은 빈 리스트를 돌려주므로, 호출부가 기존 하드코딩 검증으로
    이어가면 된다(마이그레이션 중 두 방식이 공존한다)."""
    defn = NODE_DEFINITIONS.get(node_type)
    if defn is None:
        return []

    scope = data or {}
    # 바인딩이 걸린 필드는 필수 검사에서 면제한다. 지원 필드 목록으로 한 번 걸러서,
    # 엉뚱한 필드에 붙인 바인딩이 필수 검사를 조용히 무력화하지 못하게 한다
    # (그 바인딩 자체는 node_bindings.validate_bindings 가 따로 거부한다).
    bindings = scope.get("bindings") if isinstance(scope.get("bindings"), dict) else {}
    bound_fields = frozenset(
        name for name, spec in (bindings or {}).items()
        if isinstance(spec, dict)
        and spec.get("source")
        and name in node_bindings.bindable_fields(node_type)
        # 선택 연결(required: false)은 면제하지 않는다 — 값이 없을 때 그냥 넘어가므로
        # 필드가 비어 있으면 실행 시 진짜로 값 없이 동작한다. 그때는 대체값이 있어야 한다.
        and spec.get("required", True) is not False
    )
    errors: List[str] = []
    for field in defn.fields:
        if field.kind == "repeatable":
            field_errors = _validate_field(field, scope, node_id)
            if field_errors:
                errors.extend(field_errors)
                continue
            items = scope.get(field.name) or []
            seen: Dict[str, set] = {}
            for index, item in enumerate(items):
                item = item if isinstance(item, dict) else {}
                # 예전 구현과 동일하게, labelField 값이 있으면 그 값으로 없으면 '#인덱스'로 가리킨다.
                item_label = (item.get(field.labelField) if field.labelField else None) or f"#{index}"
                for item_field in field.itemFields:
                    errors.extend(_validate_field(item_field, item, node_id, item_label, seen))
        else:
            errors.extend(_validate_field(field, scope, node_id, bound_fields=bound_fields))
    return errors


# ── LLM 카탈로그 ────────────────────────────────────────────────────────
def catalog_entry(node_type: str) -> str:
    """meta_agent.NODE_CATALOG에 그대로 끼워 넣을 수 있는 항목 텍스트를 만든다."""
    defn = NODE_DEFINITIONS[node_type]
    return f"- {node_type:<{_CATALOG_TYPE_WIDTH}}: {defn.llm.description}"


def definitions_payload() -> Dict[str, Any]:
    """API 응답과 프론트 번들에 쓰는 직렬화 형태."""
    return {
        node_type: defn.model_dump(mode="json", by_alias=True, exclude_none=True)
        for node_type, defn in sorted(NODE_DEFINITIONS.items())
    }


# meta_agent.NODE_CATALOG 템플릿에서 "이 항목은 정의 파일에서 온다"를 표시하는 자리표시자.
CATALOG_PLACEHOLDER = "{{NODE_DEFINITION}}"


def inject_catalog_entries(template: str) -> str:
    """'- nodeType      : {{NODE_DEFINITION}}' 자리표시 줄을 정의 파일의 설명으로 채운다.

    카탈로그 원문을 정의 파일로 옮기면서도 항목 순서와 문구를 그대로 유지하기 위한 장치다.
    자리표시자가 가리키는 정의 파일이 없으면 조용히 빈칸으로 남기지 않고 즉시 실패한다 —
    프롬프트에서 노드 설명이 통째로 사라지면 생성 품질이 떨어지는데, 그건 눈에 잘 띄지 않는다.
    """
    import re

    pattern = re.compile(r"^(- (\w+)\s*: )" + re.escape(CATALOG_PLACEHOLDER) + r"\n", re.M)

    def _replace(match: "re.Match[str]") -> str:
        prefix, node_type = match.group(1), match.group(2)
        if node_type not in NODE_DEFINITIONS:
            raise KeyError(
                f"NODE_CATALOG가 '{node_type}' 항목을 정의 파일에서 가져오려 하는데 "
                f"{DEFINITIONS_DIR}/{node_type}.json 이 없다"
            )
        # 템플릿 줄의 접두사('- 노드명   : ')를 그대로 쓴다 — 기존 카탈로그의 항목별 패딩이
        # 균일하지 않아서(15자 초과 이름 등) 접두사를 재조립하면 원문과 달라진다.
        return prefix + NODE_DEFINITIONS[node_type].llm.description

    return pattern.sub(_replace, template)


# ── 정의에서 파생되는 노드 분류 ────────────────────────────────────────
# 예전에는 dry_run.py 가 "외부에 영향을 주는 노드"를 하드코딩 집합으로 들고 있었다. 노드를
# 추가하면서 그 목록에 넣는 걸 잊으면, 새 노드는 dry-run 에서 조용히 실행 대상으로 통과한다.
# 이제 정의의 sideEffect / connector.sideEffectByMode 에서 파생시킨다(ADR-0008).
def types_with_external_writes() -> set:
    """어떤 모드로든 외부에 쓰기를 하는 노드 타입."""
    result = set()
    for node_type, defn in NODE_DEFINITIONS.items():
        if defn.sideEffect == "external-write":
            result.add(node_type)
        elif defn.connector and defn.connector.writes_externally(None):
            result.add(node_type)
    return result


def trigger_types() -> set:
    """플로우의 시작점이 되는 노드 타입."""
    return {
        node_type for node_type, defn in NODE_DEFINITIONS.items()
        if (defn.connector and defn.connector.role == "trigger") or defn.category == "trigger"
    }
