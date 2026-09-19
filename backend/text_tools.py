"""text_tools.py — 개발 편의 노드의 결정적 텍스트·데이터 도구 (백로그 34 DEV-2, ADR-0033).

네 노드(regexExtractNode·textDiffNode·dataConvertNode·templateRenderNode)의 실제 로직이 전부 여기 있다. 생성기(node_generators/
dev_tool_nodes.py)는 이 함수를 한 번 부르는 코드만 뱉는다 — 그래서 로직을 네트워크·DB 없이 직접 테스트할 수 있고, 두 엔진(legacy·
interpreter)이 같은 함수를 지난다.

공통 성질
  - **결정적**: 같은 입력이면 같은 출력. LLM·시계·난수를 쓰지 않는다. dry-run 에서 그대로 실행된다.
  - **외부 의존 없음**: 표준 라이브러리 + PyYAML(+ TOML 읽기는 tomllib/tomli). TOML 쓰기는 여기 작은 직렬화기로 — 의존성을 늘리지 않는다.
  - **실패는 ToolError**: reason 은 error_catalog.json 의 코드(REGEX_INVALID·CONVERT_PARSE_FAILED·TEMPLATE_VAR_MISSING …)이고 생성기가
    NodeError 로 승격한다(ADR-0016). 사용자가 고칠 수 있는 입력 문제라 전부 validation 범주·재시도 불가다.
  - **상한**: 입력 1 MB·출력 2 MB. 실행 로그와 run step 에 그대로 남는 값이라 무제한이면 DB 가 부푼다.

템플릿 문법(templateRenderNode)은 **표현식 언어가 아니다**(ADR-0026 원칙 — 값은 옮기기만 한다). 자리표시자·반복·조건 셋뿐이다:
    {{ path }}                         값. 경로는 바인딩과 같은 문법(a.b[0].c). dict/list 는 JSON 으로.
    {{#each path}} … {{/each}}         배열 반복. 안에서 {{this}} {{this.key}} {{@index}}(0부터) {{@number}}(1부터). 바깥 변수도 보인다.
    {{#if path}} … {{else}} … {{/if}}  truthy 판정(빈 문자열·0·빈 배열·null·false 는 거짓).
필터·연산·함수는 없다. 그런 변환은 llmNode 나 pythonNode 의 일이다.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

MAX_INPUT_CHARS = 1_000_000
MAX_OUTPUT_CHARS = 2_000_000
MAX_PATTERN_CHARS = 2_000
MAX_MATCHES = 10_000
MAX_LOOP_ITEMS = 10_000
MAX_TEMPLATE_DEPTH = 20


class ToolError(Exception):
    """사용자가 고칠 수 있는 입력 문제. reason 은 error_catalog.json 의 코드다."""

    def __init__(self, reason: str, message: str, *, field: Optional[str] = None, safe_details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.reason = reason
        self.field = field
        self.safe_details = dict(safe_details or {})
        if field and "field" not in self.safe_details:
            self.safe_details["field"] = field


def _check_input_size(text: str, field: str) -> None:
    if len(text) > MAX_INPUT_CHARS:
        raise ToolError("TOOL_INPUT_TOO_LARGE", f"입력이 너무 큽니다({len(text):,}자, 상한 {MAX_INPUT_CHARS:,}자).",
                        field=field, safe_details={"chars": len(text), "limit": MAX_INPUT_CHARS})


def _check_output_size(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        raise ToolError("TOOL_OUTPUT_TOO_LARGE", f"결과가 너무 큽니다({len(text):,}자, 상한 {MAX_OUTPUT_CHARS:,}자).",
                        safe_details={"chars": len(text), "limit": MAX_OUTPUT_CHARS})
    return text


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)


def to_output(value: Any) -> str:
    """노드 출력은 문자열 하나다 — 문자열은 그대로, 구조는 JSON(들여쓰기 2)으로."""
    if isinstance(value, str):
        return _check_output_size(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return _check_output_size(json.dumps(value, ensure_ascii=False, indent=2, default=str))


# ── 1. 정규식 추출 ──────────────────────────────────────────────────────────

REGEX_MODES = ("first", "all", "test", "replace")


def _compile(pattern: str, *, ignore_case: bool, multiline: bool, dot_all: bool) -> "re.Pattern[str]":
    pattern = str(pattern or "")
    if not pattern:
        raise ToolError("REGEX_INVALID", "정규식(pattern)이 비어 있습니다.", field="pattern")
    if len(pattern) > MAX_PATTERN_CHARS:
        raise ToolError("REGEX_INVALID", f"정규식이 너무 깁니다(상한 {MAX_PATTERN_CHARS}자).", field="pattern",
                        safe_details={"detail": f"{len(pattern)} chars"})
    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    if dot_all:
        flags |= re.DOTALL
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ToolError("REGEX_INVALID", f"정규식이 잘못됐습니다: {exc}", field="pattern",
                        safe_details={"detail": str(exc), "position": exc.pos}) from None


def _match_record(match: "re.Match[str]") -> Dict[str, Any]:
    return {
        "match": match.group(0),
        "groups": {name: value for name, value in match.groupdict().items()},
        "positional": list(match.groups()),
        "start": match.start(),
        "end": match.end(),
    }


def _group_value(match: "re.Match[str]", group: str) -> Any:
    key: Any = group.strip()
    if key.isdigit():
        key = int(key)
    try:
        return match.group(key)
    except (IndexError, error_type_for_group()):
        raise ToolError("REGEX_INVALID", f"그룹 '{group}' 이 정규식에 없습니다.", field="group",
                        safe_details={"detail": f"group {group!r} not in pattern"}) from None


def error_type_for_group():
    return re.error


def regex_extract(source: Any, pattern: str, *, mode: str = "first", group: str = "", ignore_case: bool = False,
                  multiline: bool = False, dot_all: bool = False, replacement: str = "", fail_if_no_match: bool = False) -> Any:
    """정규식으로 추출·검사·치환한다.

    mode  first   첫 매치 → {match, groups, positional, start, end} (group 지정 시 그 값만). 없으면 "" (fail_if_no_match 면 REGEX_NO_MATCH)
          all     모든 매치 → 배열(group 지정 시 문자열 배열). 없으면 []
          test    일치 여부 → true/false
          replace 치환한 전체 텍스트(replacement 에 \\1·\\g<name>)
    """
    text = _text(source)
    _check_input_size(text, "source")
    mode = str(mode or "first").strip().lower()
    if mode not in REGEX_MODES:
        raise ToolError("REGEX_INVALID", f"모드는 {', '.join(REGEX_MODES)} 중 하나여야 합니다: {mode!r}", field="mode")
    compiled = _compile(pattern, ignore_case=ignore_case, multiline=multiline, dot_all=dot_all)
    group = str(group or "").strip()

    if mode == "test":
        return compiled.search(text) is not None
    if mode == "replace":
        try:
            return compiled.sub(str(replacement or ""), text)
        except (re.error, IndexError) as exc:
            raise ToolError("REGEX_INVALID", f"치환 문자열이 잘못됐습니다: {exc}", field="replacement",
                            safe_details={"detail": str(exc)}) from None
    if mode == "all":
        records: List[Any] = []
        for match in compiled.finditer(text):
            records.append(_group_value(match, group) if group else _match_record(match))
            if len(records) >= MAX_MATCHES:
                break
        if not records and fail_if_no_match:
            raise ToolError("REGEX_NO_MATCH", "정규식에 맞는 부분이 없습니다.", field="pattern")
        return records
    match = compiled.search(text)
    if match is None:
        if fail_if_no_match:
            raise ToolError("REGEX_NO_MATCH", "정규식에 맞는 부분이 없습니다.", field="pattern")
        return ""
    return _group_value(match, group) if group else _match_record(match)


# ── 2. 텍스트 diff ─────────────────────────────────────────────────────────

def _normalize_for_diff(text: str, *, normalize_json: bool, ignore_whitespace: bool) -> str:
    if normalize_json:
        try:
            loaded = json.loads(text)
            text = json.dumps(loaded, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        except ValueError:
            pass
    if ignore_whitespace:
        text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    return text


def text_diff(old_text: Any, new_text: Any, *, old_label: str = "이전", new_label: str = "이후", context_lines: int = 3,
              normalize_json: bool = False, ignore_whitespace: bool = False) -> Dict[str, Any]:
    """unified diff 와 요약. changed 가 false 면 diff 는 빈 문자열이다 — 뒤의 조건 분기가 `changed` 하나만 보면 된다."""
    old = _text(old_text)
    new = _text(new_text)
    _check_input_size(old, "oldText")
    _check_input_size(new, "newText")
    try:
        context = max(0, min(int(context_lines), 1000))
    except (TypeError, ValueError):
        context = 3
    old_norm = _normalize_for_diff(old, normalize_json=normalize_json, ignore_whitespace=ignore_whitespace)
    new_norm = _normalize_for_diff(new, normalize_json=normalize_json, ignore_whitespace=ignore_whitespace)
    old_lines = old_norm.splitlines()
    new_lines = new_norm.splitlines()
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(old_label or "이전"),
                                           tofile=str(new_label or "이후"), n=context, lineterm=""))
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    diff_text = "\n".join(diff_lines)
    return {
        "changed": bool(diff_lines),
        "added": added,
        "removed": removed,
        "oldLines": len(old_lines),
        "newLines": len(new_lines),
        "oldLabel": str(old_label or "이전"),
        "newLabel": str(new_label or "이후"),
        "diff": _check_output_size(diff_text),
    }


# ── 3. JSON ↔ YAML ↔ TOML ─────────────────────────────────────────────────

CONVERT_FORMATS = ("json", "yaml", "toml")


def _toml_module():
    try:
        import tomllib  # Python 3.11+
        return tomllib
    except ImportError:
        try:
            import tomli
            return tomli
        except ImportError:  # pragma: no cover — requirements.txt 가 tomli 를 고정한다
            return None


def _parse_json(text: str) -> Any:
    return json.loads(text)


def _parse_yaml(text: str) -> Any:
    import yaml

    loaded = yaml.safe_load(text)
    if not isinstance(loaded, (dict, list)):
        raise ValueError("YAML 문서가 객체나 배열이 아닙니다(스칼라 하나)")
    return loaded


def _parse_toml(text: str) -> Any:
    module = _toml_module()
    if module is None:
        raise ToolError("CONVERT_UNSUPPORTED", "이 서버에는 TOML 파서가 없습니다.", safe_details={"toFormat": "toml", "detail": "tomllib/tomli 없음"})
    return module.loads(text)


def parse_structured(text: str, from_format: str = "auto") -> Tuple[Any, str]:
    """(값, 실제로 읽힌 형식). auto 는 JSON → TOML → YAML 순서다 — YAML 은 `a = 1` 같은 TOML 도 문자열 스칼라로 읽어 버리므로 마지막."""
    from_format = str(from_format or "auto").strip().lower()
    order = [from_format] if from_format in CONVERT_FORMATS else ["json", "toml", "yaml"]
    if from_format not in CONVERT_FORMATS and from_format != "auto":
        raise ToolError("CONVERT_PARSE_FAILED", f"입력 형식은 auto/json/yaml/toml 중 하나여야 합니다: {from_format!r}", field="fromFormat")
    if not text.strip():
        raise ToolError("CONVERT_PARSE_FAILED", "변환할 입력이 비어 있습니다.", field="source", safe_details={"fromFormat": from_format})
    errors: List[str] = []
    parsers = {"json": _parse_json, "yaml": _parse_yaml, "toml": _parse_toml}
    for name in order:
        try:
            return parsers[name](text), name
        except ToolError:
            raise
        except Exception as exc:  # json.JSONDecodeError · yaml.YAMLError · TOMLDecodeError · ValueError
            errors.append(f"{name}: {str(exc).splitlines()[0][:200]}")
    raise ToolError("CONVERT_PARSE_FAILED", f"입력을 {from_format} 으로 읽지 못했습니다.", field="source",
                    safe_details={"fromFormat": from_format, "detail": " | ".join(errors)[:600]})


_TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(key: Any) -> str:
    text = str(key)
    return text if _TOML_BARE_KEY.match(text) else json.dumps(text, ensure_ascii=False)


def _toml_scalar(value: Any, path: str) -> str:
    import datetime as _dt

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if value is None:
        raise ToolError("CONVERT_UNSUPPORTED", f"TOML 은 null 을 표현할 수 없습니다: {path or '(루트)'}",
                        safe_details={"toFormat": "toml", "path": path, "detail": "null"})
    raise ToolError("CONVERT_UNSUPPORTED", f"TOML 로 표현할 수 없는 값입니다: {path} ({type(value).__name__})",
                    safe_details={"toFormat": "toml", "path": path, "detail": type(value).__name__})


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _toml_inline(value: Any, path: str) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_inline(v, f'{path}.{k}')}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(item, f"{path}[{i}]") for i, item in enumerate(value)) + "]"
    return _toml_scalar(value, path)


def _toml_table(data: Dict[str, Any], prefix: str, out: List[str]) -> None:
    scalars = [(k, v) for k, v in data.items() if not isinstance(v, dict) and not _is_table_array(v)]
    tables = [(k, v) for k, v in data.items() if isinstance(v, dict)]
    arrays = [(k, v) for k, v in data.items() if _is_table_array(v)]
    if prefix and (scalars or not (tables or arrays)):
        out.append(f"[{prefix}]")
    for key, value in scalars:
        out.append(f"{_toml_key(key)} = {_toml_inline(value, f'{prefix}.{key}' if prefix else str(key))}")
    for key, value in tables:
        if scalars or out:
            out.append("")
        _toml_table(value, f"{prefix}.{_toml_key(key)}" if prefix else _toml_key(key), out)
    for key, items in arrays:
        full = f"{prefix}.{_toml_key(key)}" if prefix else _toml_key(key)
        for item in items:
            out.append("")
            out.append(f"[[{full}]]")
            inner: List[str] = []
            _toml_table(item, "", inner)
            out.extend(inner)


def dump_toml(data: Any) -> str:
    if not isinstance(data, dict):
        raise ToolError("CONVERT_UNSUPPORTED", "TOML 문서의 최상위는 객체(테이블)여야 합니다 — 배열이나 스칼라는 표현할 수 없습니다.",
                        safe_details={"toFormat": "toml", "path": "", "detail": type(data).__name__})
    out: List[str] = []
    _toml_table(data, "", out)
    text = "\n".join(out).strip("\n")
    return text + "\n" if text else ""


def dump_structured(data: Any, to_format: str = "yaml", *, indent: int = 2, sort_keys: bool = False) -> str:
    to_format = str(to_format or "yaml").strip().lower()
    try:
        indent = max(0, min(int(indent), 8))
    except (TypeError, ValueError):
        indent = 2
    if to_format == "json":
        try:
            return json.dumps(data, ensure_ascii=False, indent=indent or None, sort_keys=sort_keys, default=_json_default, allow_nan=False)
        except ValueError as exc:
            raise ToolError("CONVERT_UNSUPPORTED", f"JSON 으로 표현할 수 없는 값입니다: {exc}",
                            safe_details={"toFormat": "json", "path": "", "detail": str(exc)[:200]}) from None
    if to_format == "yaml":
        import yaml

        return yaml.safe_dump(_yaml_ready(data), allow_unicode=True, sort_keys=sort_keys, default_flow_style=False,
                              indent=indent or 2, width=1_000_000)
    if to_format == "toml":
        if sort_keys:
            data = _sorted(data)
        return dump_toml(data)
    raise ToolError("CONVERT_UNSUPPORTED", f"출력 형식은 json/yaml/toml 중 하나여야 합니다: {to_format!r}", field="toFormat",
                    safe_details={"toFormat": to_format})


def _json_default(value: Any) -> Any:
    import datetime as _dt

    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _yaml_ready(value: Any) -> Any:
    """safe_dump 가 모르는 타입(튜플·집합)을 배열로. 날짜는 YAML 이 직접 표현한다."""
    if isinstance(value, dict):
        return {str(k): _yaml_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_yaml_ready(v) for v in value]
    return value


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sorted(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, list):
        return [_sorted(v) for v in value]
    return value


def data_convert(source: Any, *, from_format: str = "auto", to_format: str = "yaml", indent: int = 2, sort_keys: bool = False) -> str:
    """JSON ↔ YAML ↔ TOML. 읽기는 파서가, 쓰기는 직렬화기가 — 값 구조(dict/list/스칼라)가 중간 표현이다."""
    text = _text(source)
    _check_input_size(text, "source")
    data, _ = parse_structured(text, from_format)
    return _check_output_size(dump_structured(data, to_format, indent=indent, sort_keys=sort_keys))


# ── 4. 템플릿 렌더 ─────────────────────────────────────────────────────────

MISSING_MODES = ("empty", "keep", "error")
_TAG_RE = re.compile(r"\{\{\s*(#each|#if|/each|/if|else)?\s*([^{}]*?)\s*\}\}")
_PATH_TOKEN = re.compile(r"[^.\[\]]+|\[\d+\]")


def _lookup(path: str, scopes: List[Dict[str, Any]]) -> Tuple[bool, Any]:
    """`this`·`@index`·경로를 안쪽 scope 부터 바깥으로 찾는다."""
    path = path.strip()
    if not path:
        return False, None
    tokens = _PATH_TOKEN.findall(path)
    if not tokens:
        return False, None
    head = tokens[0]
    for scope in reversed(scopes):
        if head.startswith("["):
            candidate = scope.get("this") if "this" in scope else None
            found, current = True, candidate
            rest = tokens
        elif head in scope:
            found, current = True, scope[head]
            rest = tokens[1:]
        else:
            continue
        for token in rest:
            if token.startswith("["):
                index = int(token[1:-1])
                if not isinstance(current, (list, tuple)) or index >= len(current):
                    return False, None
                current = current[index]
            elif isinstance(current, dict) and token in current:
                current = current[token]
            else:
                return False, None
        if found:
            return True, current
    return False, None


def _truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, dict, tuple)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def _parse_template(template: str) -> List[Any]:
    """토큰 → 트리. 노드: ("text", s) · ("var", path) · ("each", path, body) · ("if", path, body, else_body)."""
    stack: List[Tuple[str, str, List[Any], Optional[List[Any]], int]] = []
    root: List[Any] = []
    current = root
    pos = 0
    for match in _TAG_RE.finditer(template):
        if match.start() > pos:
            current.append(("text", template[pos:match.start()]))
        pos = match.end()
        kind, arg = match.group(1), (match.group(2) or "").strip()
        if kind is None:
            if not arg:
                raise ToolError("TEMPLATE_SYNTAX_INVALID", f"빈 자리표시자 {{{{}}}} 가 있습니다({match.start()}번째 글자).",
                                field="template", safe_details={"position": match.start(), "detail": "empty placeholder"})
            current.append(("var", arg))
        elif kind in ("#each", "#if"):
            if not arg:
                raise ToolError("TEMPLATE_SYNTAX_INVALID", f"{kind} 에 경로가 없습니다({match.start()}번째 글자).",
                                field="template", safe_details={"position": match.start(), "detail": f"{kind} without path"})
            if len(stack) >= MAX_TEMPLATE_DEPTH:
                raise ToolError("TEMPLATE_SYNTAX_INVALID", f"블록이 {MAX_TEMPLATE_DEPTH}겹보다 깊습니다.", field="template",
                                safe_details={"position": match.start(), "detail": "too deep"})
            body: List[Any] = []
            stack.append((kind[1:], arg, body, None, match.start()))
            current = body
        elif kind == "else":
            if not stack or stack[-1][0] != "if" or stack[-1][3] is not None:
                raise ToolError("TEMPLATE_SYNTAX_INVALID", f"{{{{else}}}} 가 #if 밖에 있습니다({match.start()}번째 글자).",
                                field="template", safe_details={"position": match.start(), "detail": "else outside if"})
            name, path, body, _, start = stack.pop()
            else_body: List[Any] = []
            stack.append((name, path, body, else_body, start))
            current = else_body
        else:  # /each · /if
            expected = kind[1:]
            if not stack or stack[-1][0] != expected:
                raise ToolError("TEMPLATE_SYNTAX_INVALID", f"{{{{{kind}}}}} 에 맞는 여는 태그가 없습니다({match.start()}번째 글자).",
                                field="template", safe_details={"position": match.start(), "detail": f"unbalanced {kind}"})
            name, path, body, else_body, _ = stack.pop()
            current = stack[-1][3] if (stack and stack[-1][3] is not None) else (stack[-1][2] if stack else root)
            current.append((name, path, body, else_body))
    if stack:
        name, path, _, _, start = stack[-1]
        raise ToolError("TEMPLATE_SYNTAX_INVALID", f"{{{{#{name} {path}}}}} 가 닫히지 않았습니다({start}번째 글자).",
                        field="template", safe_details={"position": start, "detail": f"unclosed #{name}"})
    if pos < len(template):
        current.append(("text", template[pos:]))
    return root


def _render_nodes(nodes: List[Any], scopes: List[Dict[str, Any]], missing: str, out: List[str]) -> None:
    for node in nodes:
        kind = node[0]
        if kind == "text":
            out.append(node[1])
        elif kind == "var":
            found, value = _lookup(node[1], scopes)
            if found:
                out.append(_format_value(value))
            elif missing == "keep":
                out.append("{{" + node[1] + "}}")
            elif missing == "error":
                raise ToolError("TEMPLATE_VAR_MISSING", f"템플릿 변수 '{node[1]}' 에 해당하는 값이 없습니다.", field="template",
                                safe_details={"path": node[1]})
        elif kind == "each":
            _, path, body, _ = node
            found, value = _lookup(path, scopes)
            if not found or value is None:
                if missing == "error":
                    raise ToolError("TEMPLATE_VAR_MISSING", f"반복 대상 '{path}' 에 해당하는 값이 없습니다.", field="template",
                                    safe_details={"path": path})
                continue
            if isinstance(value, dict):
                items: List[Any] = [{"key": k, "value": v} for k, v in value.items()]
            elif isinstance(value, (list, tuple)):
                items = list(value)
            else:
                items = [value]
            if len(items) > MAX_LOOP_ITEMS:
                raise ToolError("TOOL_INPUT_TOO_LARGE", f"반복 항목이 너무 많습니다({len(items):,}개, 상한 {MAX_LOOP_ITEMS:,}개).",
                                field="variables", safe_details={"chars": len(items), "limit": MAX_LOOP_ITEMS})
            for index, item in enumerate(items):
                frame: Dict[str, Any] = {"this": item, "@index": index, "@number": index + 1,
                                         "@first": index == 0, "@last": index == len(items) - 1}
                if isinstance(item, dict):
                    frame.update({k: v for k, v in item.items() if k not in frame})
                _render_nodes(body, scopes + [frame], missing, out)
        elif kind == "if":
            _, path, body, else_body = node
            found, value = _lookup(path, scopes)
            _render_nodes(body if (found and _truthy(value)) else (else_body or []), scopes, missing, out)


def coerce_variables(variables: Any, upstream_text: Any = None) -> Dict[str, Any]:
    """변수 JSON → dict. 비어 있으면 직전 노드 출력을 JSON 으로 읽고, JSON 이 아니면 {"input": 원문}. 배열이면 {"items": …}.
    원문은 언제나 `input` 으로도 볼 수 있다(사용자 키와 겹치면 사용자 키가 이긴다)."""
    raw = variables
    if isinstance(raw, (bytes, str)):
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not text.strip():
            raw = None
        else:
            try:
                raw = json.loads(text)
            except ValueError as exc:
                raise ToolError("TEMPLATE_VARIABLES_INVALID", f"변수(variables)가 JSON 이 아닙니다: {str(exc)[:120]}", field="variables",
                                safe_details={"detail": str(exc)[:200]}) from None
    upstream = _text(upstream_text) if upstream_text is not None else ""
    if raw is None:
        if upstream.strip():
            try:
                raw = json.loads(upstream)
            except ValueError:
                raw = {"input": upstream}
        else:
            raw = {}
    if isinstance(raw, list):
        raw = {"items": raw}
    elif not isinstance(raw, dict):
        raw = {"value": raw}
    result = dict(raw)
    if upstream and "input" not in result:
        result["input"] = upstream
    return result


def render_template(template: Any, variables: Any = None, *, upstream_text: Any = None, missing: str = "empty") -> str:
    text = _text(template)
    _check_input_size(text, "template")
    missing = str(missing or "empty").strip().lower()
    if missing not in MISSING_MODES:
        missing = "empty"
    scope = coerce_variables(variables, upstream_text)
    tree = _parse_template(text)
    out: List[str] = []
    _render_nodes(tree, [scope], missing, out)
    return _check_output_size("".join(out))


def template_variables(template: Any) -> List[str]:
    """템플릿이 참조하는 최상위 변수 이름(편집기 안내용). this/@… 와 반복 안 키는 뺀다."""
    names: List[str] = []
    try:
        tree = _parse_template(_text(template))
    except ToolError:
        return names

    def walk(nodes: List[Any], depth: int) -> None:
        for node in nodes:
            if node[0] == "var":
                head = _PATH_TOKEN.findall(node[1])
                if head and depth == 0 and not head[0].startswith(("[", "@")) and head[0] != "this" and head[0] not in names:
                    names.append(head[0])
            elif node[0] in ("each", "if"):
                head = _PATH_TOKEN.findall(node[1])
                if head and depth == 0 and not head[0].startswith(("[", "@")) and head[0] != "this" and head[0] not in names:
                    names.append(head[0])
                walk(node[2], depth + (1 if node[0] == "each" else 0))
                if node[3]:
                    walk(node[3], depth)

    walk(tree, 0)
    return names
