"""생성 코드의 문자열 이스케이프 검사.

graph.py 는 코드 생성기다 — 노드 data 의 값이 파이썬 소스의 문자열 리터럴로 들어간다.
그래서 값 안의 **백슬래시**를 먼저 이스케이프하지 않으면 리터럴이 깨진다:

    원본     "... [\\"시각\\"] ..."        (JSON 안에 이스케이프된 따옴표 = 백슬래시+따옴표)
    옛 처리   따옴표만 → 백슬래시+백슬래시+따옴표 → 소스에서 문자열이 조기 종료
    증상     "Security validation failed: generated workflow is invalid at line N"

2026-08-31 에 formatNode 의 "빈칸 채우기 LLM 삽입"(rows 필드 description 에 ["시각","내용"] 이
들어간다)이 이 버그를 드러냈지만, 원인은 46곳에 흩어져 있던 공통 이스케이프 순서였다.
올바른 순서는 **백슬래시가 항상 첫 번째**다.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

import graph

# 사람이 실제로 쓸 수 있고 옛 방식이면 반드시 깨지는 값들.
NASTY_VALUES = [
    '따옴표 "인용" 포함',
    '경로 C:\\temp\\report.hwpx',
    r'정규식 \d+ 과 \\ 이중 백슬래시',
    'JSON 예시: {"key": "value"}',
    '줄바꿈\n두 번째 줄\n세 번째',
    r'섞임: "a\"b" 그리고 C:\x\y',
]


def _compile(nodes, edges):
    """보안 검증기를 우회하지 않고 그대로 부른다 — 이 테스트의 관심사가 바로 그 관문이다."""
    return graph.compile_workflow(nodes, edges)


def _assign_value(source: str, variable: str):
    """생성 코드에서 `variable = <리터럴>` 의 실제 값을 AST 로 꺼낸다."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == variable:
            if isinstance(node.value, ast.Constant):
                return node.value.value
            if isinstance(node.value, ast.Call) and node.value.args:
                return ast.literal_eval(node.value.args[0])
    raise AssertionError(f"{variable} 할당을 찾지 못했다")


@pytest.mark.parametrize("value", NASTY_VALUES, ids=lambda v: repr(v)[:28])
def test_llm_system_prompt_survives_codegen(value):
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": value}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": "e1", "source": "n1", "target": "n2"},
             {"id": "e2", "source": "n2", "target": "n3"}]
    source = _compile(nodes, edges)
    assert not source.startswith("Error"), source[:200]
    assert _assign_value(source, "sys_prompt_n2") == value


@pytest.mark.parametrize("value", NASTY_VALUES, ids=lambda v: repr(v)[:28])
def test_prompt_node_user_prompt_survives_codegen(value):
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "promptNode", "data": {"userPrompt": value}},
        {"id": "n3", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "s"}},
        {"id": "n4", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}"} for i in (1, 2, 3)]
    source = _compile(nodes, edges)
    assert not source.startswith("Error"), source[:200]
    ast.parse(source)  # 문법 자체가 깨지지 않는 것이 1차 관문


def test_structured_output_schema_round_trips():
    """formatNode 의 '빈칸 채우기 LLM 삽입'이 만드는 스키마 — 이 버그의 실제 재현 경로."""
    schema = {
        "title": "시말서", "type": "object",
        "properties": {
            "timeline": {
                "type": "array",
                "description": '경위 (각 행은 ["시각", "내용"] 순서의 문자열 배열)',
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "summary": {"type": "string", "description": '사건 개요 — "무엇이" 일어났는지'},
        },
        "required": ["summary"],
    }
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {
            "model": "gpt-4o-mini", "systemPrompt": '너는 "빈칸 채우기" 도우미다.',
            "useStructuredOutput": True,
            "jsonSchema": json.dumps(schema, ensure_ascii=False, indent=2)}},
        {"id": "n3", "type": "formatNode", "data": {"formatId": "incident-report", "output": "hwpx"}},
        {"id": "n4", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}"} for i in (1, 2, 3)]
    source = _compile(nodes, edges)
    assert not source.startswith("Error"), source[:300]
    assert json.loads(_assign_value(source, "schema_dict_n2")) == schema


def test_condition_and_value_nodes_survive_backslash():
    """분기 비교값·고정값도 같은 경로를 탄다."""
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "valueNode", "data": {"value": r'경로 C:\a\b 와 "인용"'}},
        {"id": "n3", "type": "conditionNode", "data": {
            "rules": [{"id": "r1", "operator": "Contains", "value": r'C:\a'}]}},
        {"id": "n4", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": "e1", "source": "n1", "target": "n2"},
             {"id": "e2", "source": "n2", "target": "n3"},
             {"id": "e3", "source": "n3", "target": "n4", "sourceHandle": "r1"}]
    source = _compile(nodes, edges)
    assert not source.startswith("Error"), source[:200]
    ast.parse(source)


def test_no_generator_escapes_quotes_before_backslash():
    """회귀 방지 — 새 생성기가 옛 순서를 다시 들여오면 여기서 막는다.

    이스케이프 체인에서 백슬래시 처리는 반드시 따옴표·개행 처리보다 앞이어야 한다.
    """
    backend = pathlib.Path(__file__).resolve().parent
    quote = r""".replace('"', '\\"')"""
    backslash = r""".replace('\\', '\\\\')"""
    offenders = []
    for path in [backend / "graph.py", *sorted((backend / "node_generators").glob("*.py"))]:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            if quote not in line:
                continue
            if backslash not in line:
                offenders.append(f"{path.name}:{lineno} 백슬래시 이스케이프 누락")
            elif line.index(backslash) > line.index(quote):
                offenders.append(f"{path.name}:{lineno} 백슬래시가 따옴표보다 뒤")
    assert not offenders, "생성 코드 이스케이프 순서 위반:\n" + "\n".join(offenders)


# ── OpenAI json_schema.name 규칙 (2026-08-31) ────────────────────────────
# langchain 은 JSON Schema 의 title 을 structured output 의 json_schema.name 으로 쓴다.
# OpenAI 는 그 name 에 ^[a-zA-Z0-9_-]+$ 만 허용하므로, 한글 제목("시말서")이면 400 으로 거부된다:
#   Invalid 'response_format.json_schema.name': string does not match pattern
# 사용자가 손으로 쓴 스키마도 같은 함정에 빠지므로 실행 시점에 정규화한다.

def _preamble_namespace(source: str) -> dict:
    cut = source.index("def run_workflow(")
    namespace: dict = {}
    exec(source[:cut], namespace)  # noqa: S102 — 방금 생성한 코드다
    return namespace


def _basic_structured_graph(schema: dict):
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {
            "model": "gpt-4o-mini", "systemPrompt": "s",
            "useStructuredOutput": True,
            "jsonSchema": json.dumps(schema, ensure_ascii=False)}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": "e1", "source": "n1", "target": "n2"},
             {"id": "e2", "source": "n2", "target": "n3"}]
    return nodes, edges


OPENAI_NAME_OK = re.compile(r"^[a-zA-Z0-9_-]+$")


@pytest.mark.parametrize("title,expect_desc", [
    ("시말서", True),                    # 전부 한글 → 남는 문자 없음
    ("주간 보고서 v2", True),            # 한글+공백 섞임
    ("Weekly_Report-2", False),          # 이미 안전 — 손대지 않는다
])
def test_schema_title_is_normalized_for_openai(title, expect_desc):
    schema = {"title": title, "type": "object",
              "properties": {"a": {"type": "string"}}, "required": ["a"]}
    source = _compile(*_basic_structured_graph(schema))
    assert not source.startswith("Error"), source[:200]
    namespace = _preamble_namespace(source)
    normalized = namespace["_safe_schema_name"](dict(schema))
    assert OPENAI_NAME_OK.match(normalized["title"]), normalized["title"]
    if expect_desc:
        # 원래 제목을 잃지 않는다 — description 으로 옮겨 모델이 맥락을 유지한다.
        assert normalized["description"] == title
    else:
        assert normalized["title"] == title


def test_schema_without_title_gets_default_name():
    source = _compile(*_basic_structured_graph({"type": "object", "properties": {}}))
    namespace = _preamble_namespace(source)
    assert namespace["_safe_schema_name"]({"type": "object"})["title"] == "Output"


def test_generated_code_normalizes_schema_before_use():
    """정규화 호출이 with_structured_output 앞에 실제로 들어가는지 — 순서가 뒤바뀌면 무의미하다."""
    schema = {"title": "시말서", "type": "object", "properties": {"a": {"type": "string"}}}
    source = _compile(*_basic_structured_graph(schema))
    assert "_safe_schema_name(schema_dict_n2)" in source
    assert source.index("_safe_schema_name(schema_dict_n2)") < source.index("with_structured_output(schema_dict_n2")


def test_format_fields_schema_title_is_openai_safe():
    """포맷 빈칸 스키마 생성기(백엔드)가 애초에 안전한 title 을 만드는지."""
    from documents.format_spec import fields_json_schema
    schema = fields_json_schema({"name": "시말서", "fields": [
        {"name": "summary", "label": "개요", "kind": "text", "required": True}]})
    assert OPENAI_NAME_OK.match(schema["title"]), schema["title"]
    assert "시말서" in schema["description"]

