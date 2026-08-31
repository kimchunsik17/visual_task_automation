"""db_query_parameters.py — Database Query 의 이름 있는 바인드 파라미터 (ADR-0017, DB-2.3).

쿼리 문자열에 값을 문자열 보간하면 SQL injection 이 된다. 값은 항상 `:이름` 바인드 파라미터로
넘기고, 이름·타입·출처는 노드 정의(databaseNode.json 의 parameters)에 선언한다. 여기서는 선언과
쿼리에 실제로 등장한 자리표시자를 맞추고 값을 타입에 맞게 바꾼다 — 전부 DB 에 접속하기 전에.

    parameters[]: { name, source: "value" | "input", value, path, type, required }

`source=input` 은 직전 노드 출력에서 값을 가져온다. path 가 비어 있으면 출력 전체(문자열),
`a.b[0].c` 형식이면 출력을 JSON 으로 해석한 뒤 그 경로의 값을 쓴다. 테이블·컬럼 이름을 파라미터로
바꾸는 identifier 보간은 지원하지 않는다(값만 바인드된다).
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from node_errors import NodeError, make_error

PARAMETER_TYPES = ("string", "integer", "number", "boolean", "date", "datetime", "json")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class ParameterError(ValueError):
    def __init__(self, error: NodeError):
        super().__init__(error.user_message)
        self.error = error


def _error(code: str, message: str, *, index: Optional[int], name: str, node_id: Optional[str], **details) -> ParameterError:
    field = f"parameters[{index}]" if index is not None else "parameters"
    safe = {"field": field, "label": name}
    safe.update({k: v for k, v in details.items() if v is not None})
    return ParameterError(make_error(code, field=field, user_message=message, safe_details=safe,
                                     node_type="databaseNode", node_id=node_id))


def _strip_json_fence(text: str) -> str:
    value = str(text).strip()
    if value.startswith("```"):
        value = value[3:]
        if value[:4].lower().startswith("json"):
            value = value[4:]
        if "```" in value:
            value = value[: value.rfind("```")]
    return value.strip()


def read_path(upstream: Any, path: str) -> Any:
    """직전 노드 출력에서 경로 값을 읽는다. path 가 비어 있으면 출력 그대로(문자열이면 문자열)."""
    if not path or not str(path).strip():
        return upstream
    data = upstream
    if isinstance(data, str):
        try:
            data = json.loads(_strip_json_fence(data))
        except (ValueError, TypeError):
            raise KeyError("upstream is not JSON")
    for match in _PATH_TOKEN_RE.finditer(str(path).strip()):
        key, index = match.group(1), match.group(2)
        if index is not None:
            if not isinstance(data, list):
                raise KeyError(path)
            position = int(index)
            if position >= len(data):
                raise KeyError(path)
            data = data[position]
        else:
            if isinstance(data, dict) and key in data:
                data = data[key]
            elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
                data = data[int(key)]
            else:
                raise KeyError(path)
    return data


def coerce(value: Any, type_name: str) -> Any:
    """선언된 타입으로 바꾼다. 못 바꾸면 ValueError."""
    type_name = (type_name or "string").lower()
    if value is None:
        return None
    if type_name == "string":
        return value if isinstance(value, str) else (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
    if type_name == "integer":
        if isinstance(value, bool):
            raise ValueError("boolean is not an integer")
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if re.match(r"^[+-]?\d+$", text):
            return int(text)
        raise ValueError(f"{value!r} is not an integer")
    if type_name == "number":
        if isinstance(value, bool):
            raise ValueError("boolean is not a number")
        if isinstance(value, (int, float)):
            return value
        return float(str(value).strip())
    if type_name == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "t", "on"}:
            return True
        if text in {"false", "0", "no", "n", "f", "off"}:
            return False
        raise ValueError(f"{value!r} is not a boolean")
    if type_name == "date":
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value).strip()[:10])
    if type_name == "datetime":
        if isinstance(value, datetime.datetime):
            return value
        return datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if type_name == "json":
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        text = _strip_json_fence(str(value))
        json.loads(text)  # 형식 검사
        return text
    raise ValueError(f"unknown parameter type {type_name}")


def normalize_definitions(parameters: Any) -> List[Dict[str, Any]]:
    """노드 data.parameters 를 정규화한다(생성 코드에 literal 로 심기 전)."""
    result: List[Dict[str, Any]] = []
    for item in parameters or []:
        if not isinstance(item, dict):
            continue
        result.append({
            "name": str(item.get("name") or "").strip(),
            "source": "input" if str(item.get("source") or "value") == "input" else "value",
            "value": "" if item.get("value") is None else str(item.get("value")),
            "path": str(item.get("path") or "").strip(),
            "type": str(item.get("type") or "string").lower() if str(item.get("type") or "string").lower() in PARAMETER_TYPES else "string",
            "required": bool(item.get("required", True)),
        })
    return result


def bind_parameters(
    definitions: Iterable[Dict[str, Any]],
    placeholders: Iterable[str],
    upstream: Any = None,
    *,
    node_id: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """선언(definitions) × 쿼리 자리표시자(placeholders) → 바인드 값 dict. 실패는 ParameterError.

    - 쿼리에 있는데 선언이 없는 이름          → VALIDATION_REQUIRED
    - 선언 이름이 식별자 형식이 아님           → VALIDATION_INVALID_TYPE
    - required 인데 값이 비어 있음(input 경로 없음 포함) → VALIDATION_REQUIRED
    - 타입 변환 실패                          → VALIDATION_INVALID_TYPE
    overrides 는 미리보기(Test step)에서 사용자가 직접 넣은 값이다.
    """
    definitions = list(definitions or [])
    placeholders = list(placeholders or [])
    declared: Dict[str, int] = {}
    for index, definition in enumerate(definitions):
        name = str(definition.get("name") or "").strip()
        if not name:
            raise _error("VALIDATION_REQUIRED", f"{index + 1}번째 파라미터에 이름이 없습니다.", index=index, name=f"#{index}", node_id=node_id)
        if not _NAME_RE.match(name):
            raise _error("VALIDATION_INVALID_TYPE", f"파라미터 이름 '{name}' 은 영문·숫자·밑줄만 쓸 수 있습니다.", index=index, name=name, node_id=node_id, expected="identifier")
        if name in declared:
            raise _error("VALIDATION_INVALID_TYPE", f"파라미터 이름 '{name}' 이 중복됩니다.", index=index, name=name, node_id=node_id)
        declared[name] = index

    missing = [p for p in placeholders if p not in declared]
    if missing:
        raise _error("VALIDATION_REQUIRED", f"쿼리에 쓰인 파라미터 :{missing[0]} 의 정의가 없습니다. 파라미터 목록에 추가해주세요.",
                     index=None, name=missing[0], node_id=node_id)

    values: Dict[str, Any] = {}
    for name, index in declared.items():
        if name not in placeholders:
            continue  # 선언만 있고 쿼리에 없는 파라미터는 무시한다(바인드하면 드라이버가 거절할 수 있다)
        definition = definitions[index]
        type_name = str(definition.get("type") or "string").lower()
        required = bool(definition.get("required", True))
        raw: Any
        if overrides is not None and name in overrides:
            raw = overrides[name]
        elif str(definition.get("source") or "value") == "input":
            try:
                raw = read_path(upstream, str(definition.get("path") or ""))
            except KeyError:
                raw = None
        else:
            raw = definition.get("value")
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if required:
                raise _error("VALIDATION_REQUIRED", f"파라미터 :{name} 의 값이 비어 있습니다.", index=index, name=name, node_id=node_id)
            values[name] = None
            continue
        try:
            values[name] = coerce(raw, type_name)
        except (ValueError, TypeError):
            raise _error("VALIDATION_INVALID_TYPE", f"파라미터 :{name} 의 값을 {type_name} 타입으로 바꿀 수 없습니다.",
                         index=index, name=name, node_id=node_id, expected=type_name, receivedType=type(raw).__name__)
    return values
