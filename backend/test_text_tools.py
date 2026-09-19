"""개발 편의 노드 4종(백로그 34 DEV-2, ADR-0033) — text_tools 와 생성기·정의의 계약 테스트.

이 파일이 지키는 문장:

  1. **결정적이다.** 같은 입력이면 같은 출력. LLM·시계·난수를 쓰지 않는다.
  2. **실패는 사용자가 고칠 수 있는 코드로 드러난다.** ToolError.reason 은 error_catalog 의 코드고, 그래프 실행에서는 NodeError 로 로그에 남아
     error 갈래(ENGINE-3)가 받는다. 결과 문자열에 스택트레이스가 섞이지 않는다.
  3. **직전 노드 출력과 바인딩이 자연스럽게 이어진다.** 대상 텍스트를 비우면 직전 출력, ⚡ 바인딩은 런타임 조회(test_node_bindings 가 대조).
  4. **템플릿은 표현식 언어가 아니다.** 자리표시자·반복·조건만 있고, 없는 값은 정책(empty/keep/error)대로 처리된다.
"""

from __future__ import annotations

import json

import pytest

import mock_service
import node_definition
import regex_assist
import text_tools as tt
from node_errors import catalog as error_catalog
from text_tools import ToolError


def _reason(func, *args, **kwargs):
    with pytest.raises(ToolError) as exc:
        func(*args, **kwargs)
    return exc.value


# ── 1. 정규식 ──────────────────────────────────────────────────────────────

def test_이름_그룹으로_첫_매치와_모든_매치를_뽑는다():
    text = "fix: ABC-12 처리, XYZ-9 는 다음에"
    first = tt.regex_extract(text, r"(?P<ticket>[A-Z]+-\d+)")
    assert first["match"] == "ABC-12" and first["groups"] == {"ticket": "ABC-12"} and first["positional"] == ["ABC-12"]
    assert (first["start"], first["end"]) == (5, 11)
    assert tt.regex_extract(text, r"(?P<ticket>[A-Z]+-\d+)", mode="all", group="ticket") == ["ABC-12", "XYZ-9"]
    assert tt.regex_extract(text, r"(?P<ticket>[A-Z]+-\d+)", group="1") == "ABC-12"
    assert [m["groups"]["ticket"] for m in tt.regex_extract(text, r"(?P<ticket>[A-Z]+-\d+)", mode="all")] == ["ABC-12", "XYZ-9"]


def test_test_와_replace_모드_그리고_플래그():
    assert tt.regex_extract("Hello", r"^hello$", mode="test") is False
    assert tt.regex_extract("Hello", r"^hello$", mode="test", ignore_case=True) is True
    assert tt.regex_extract("a\nb", r"^b$", mode="test", multiline=True) is True
    assert tt.regex_extract("a\nb", r"a.b", mode="test", dot_all=True) is True
    assert tt.regex_extract("ABC-12 done", r"(?P<t>[A-Z]+-\d+)", mode="replace", replacement=r"[\g<t>]") == "[ABC-12] done"


def test_매치가_없으면_빈_값이고_옵션을_켜면_실패로():
    assert tt.regex_extract("없음", r"\d+") == ""
    assert tt.regex_extract("없음", r"\d+", mode="all") == []
    assert _reason(tt.regex_extract, "없음", r"\d+", fail_if_no_match=True).reason == "REGEX_NO_MATCH"
    assert _reason(tt.regex_extract, "없음", r"\d+", mode="all", fail_if_no_match=True).reason == "REGEX_NO_MATCH"


@pytest.mark.parametrize("pattern, kwargs", [
    ("(", {}), ("", {}), ("a" * 3000, {}), (r"(?P<a>x)", {"group": "b"}), (r"(x)", {"group": "5"}), (r"x", {"mode": "zap"}),
    (r"(x)", {"mode": "replace", "replacement": r"\9"}),
])
def test_잘못된_정규식_그룹_모드는_REGEX_INVALID(pattern, kwargs):
    assert _reason(tt.regex_extract, "x", pattern, **kwargs).reason == "REGEX_INVALID"


def test_입력_상한을_넘으면_TOOL_INPUT_TOO_LARGE(monkeypatch):
    monkeypatch.setattr(tt, "MAX_INPUT_CHARS", 10)
    err = _reason(tt.regex_extract, "x" * 11, r"x")
    assert err.reason == "TOOL_INPUT_TOO_LARGE" and err.safe_details["limit"] == 10 and err.field == "source"


def test_구조가_아닌_입력도_문자열로_다룬다():
    assert tt.regex_extract({"a": 12}, r"\d+", group="0") == "12"
    assert tt.regex_extract(None, r"\d+", mode="test") is False


# ── 2. diff ────────────────────────────────────────────────────────────────

def test_diff_요약과_unified_본문():
    result = tt.text_diff("a\nb\nc\n", "a\nB\nc\nd\n", old_label="prod", new_label="staging")
    assert result["changed"] is True and result["added"] == 2 and result["removed"] == 1
    assert result["diff"].startswith("--- prod\n+++ staging\n@@")
    assert "-b\n+B" in result["diff"] and result["diff"].endswith("+d")
    assert (result["oldLines"], result["newLines"]) == (3, 4)


def test_같으면_changed_false_이고_diff_는_빈_문자열():
    result = tt.text_diff("같다\n", "같다\n")
    assert result == {**result, "changed": False, "added": 0, "removed": 0, "diff": ""}


def test_JSON_정규화는_키_순서만_다른_설정을_변경으로_보지_않는다():
    old = '{"b": 1, "a": {"y": 2, "x": 1}}'
    new = '{"a": {"x": 1, "y": 2}, "b": 1}'
    assert tt.text_diff(old, new)["changed"] is True
    assert tt.text_diff(old, new, normalize_json=True)["changed"] is False
    assert tt.text_diff(old, '{"a": {"x": 1, "y": 3}, "b": 1}', normalize_json=True)["changed"] is True
    assert tt.text_diff("json 아님", new, normalize_json=True)["changed"] is True, "한쪽이 JSON 이 아니면 원문 그대로 비교"


def test_공백_무시와_문맥_줄_수():
    assert tt.text_diff("a  b\n", "a b\n", ignore_whitespace=True)["changed"] is False
    wide = tt.text_diff("\n".join(str(i) for i in range(20)), "\n".join("X" if i == 10 else str(i) for i in range(20)), context_lines=1)
    assert wide["diff"].count("\n") == 6, wide["diff"]  # 헤더 2 + @@ 1 + 문맥 1 - 1 + 1 문맥 1
    assert tt.text_diff("a", "b", context_lines="abc")["changed"] is True


# ── 3. 형식 변환 ────────────────────────────────────────────────────────────

SAMPLE = {"name": "svc", "replicas": 3, "ports": [80, 443], "env": {"DEBUG": False, "REGION": "kr"},
          "containers": [{"name": "app", "image": "app:1"}, {"name": "sidecar", "image": "log:2"}]}


def test_JSON_YAML_TOML_왕복이_값을_보존한다():
    as_json = json.dumps(SAMPLE, ensure_ascii=False)
    yaml_text = tt.data_convert(as_json, to_format="yaml")
    toml_text = tt.data_convert(yaml_text, from_format="yaml", to_format="toml")
    back = tt.data_convert(toml_text, from_format="toml", to_format="json", indent=0)
    assert json.loads(back) == SAMPLE
    assert "[[containers]]" in toml_text and "[env]" in toml_text and 'DEBUG = false' in toml_text
    assert "replicas: 3" in yaml_text


def test_자동_감지는_JSON_TOML_YAML_순서다():
    assert tt.parse_structured('{"a": 1}')[1] == "json"
    assert tt.parse_structured('a = 1\n[b]\nc = "x"')[1] == "toml"
    assert tt.parse_structured("a: 1\nb:\n  - x\n")[1] == "yaml"
    assert tt.data_convert("a: 1", to_format="json", indent=0) == '{"a": 1}'


@pytest.mark.parametrize("text, from_format", [("그냥 문장", "auto"), ("", "auto"), ("{bad json", "json"), ("a: [1", "yaml"), ("a = ", "toml")])
def test_읽지_못하면_CONVERT_PARSE_FAILED(text, from_format):
    err = _reason(tt.data_convert, text, from_format=from_format)
    assert err.reason == "CONVERT_PARSE_FAILED" and err.field == "source"


def test_TOML_이_표현하지_못하는_값은_경로와_함께_CONVERT_UNSUPPORTED():
    err = _reason(tt.data_convert, '{"a": {"b": null}}', to_format="toml")
    assert err.reason == "CONVERT_UNSUPPORTED" and err.safe_details["path"] == "a.b"
    assert _reason(tt.data_convert, "[1, 2]", to_format="toml").reason == "CONVERT_UNSUPPORTED"
    assert _reason(tt.data_convert, '{"a": 1}', to_format="xml").reason == "CONVERT_UNSUPPORTED"


def test_키_정렬과_유니코드_키_그리고_TOML_인용_키():
    out = tt.data_convert('{"b": 1, "a": 2, "한글 키": "값"}', to_format="toml", sort_keys=True)
    assert out.splitlines()[0] == "a = 2" and '"한글 키" = "값"' in out
    yaml_out = tt.data_convert('{"b": 1, "a": 2}', to_format="yaml", sort_keys=True)
    assert yaml_out.splitlines() == ["a: 2", "b: 1"]


def test_NaN_은_JSON_으로_쓸_수_없다():
    assert _reason(tt.dump_structured, {"x": float("nan")}, "json").reason == "CONVERT_UNSUPPORTED"
    assert "nan" in tt.dump_structured({"x": float("nan")}, "toml")


# ── 4. 템플릿 ──────────────────────────────────────────────────────────────

VARS = {"title": "주간 보고", "count": 2, "ok": True, "items": [{"name": "A", "value": 1.0, "done": True}, {"name": "B", "value": 2.5, "done": False}],
        "meta": {"owner": {"login": "octocat"}}, "tags": ["x", "y"]}


def test_자리표시자_경로_반복_조건():
    template = ("# {{title}} ({{count}})\n"
                "{{#each items}}{{@number}}. {{this.name}}={{this.value}} {{#if this.done}}✓{{else}}✗{{/if}} by {{meta.owner.login}}\n{{/each}}"
                "{{#if tags}}tags: {{#each tags}}{{this}}{{#if @last}}{{else}},{{/if}}{{/each}}{{/if}}\n"
                "raw={{items[1].name}} json={{meta}}")
    out = tt.render_template(template, VARS)
    assert out == ("# 주간 보고 (2)\n1. A=1 ✓ by octocat\n2. B=2.5 ✗ by octocat\ntags: x,y\n"
                   'raw=B json={"owner": {"login": "octocat"}}')


def test_없는_값은_정책대로_empty_keep_error():
    assert tt.render_template("[{{nope}}]", {}) == "[]"
    assert tt.render_template("[{{nope}}]", {}, missing="keep") == "[{{nope}}]"
    err = _reason(tt.render_template, "[{{nope.deep}}]", {}, missing="error")
    assert err.reason == "TEMPLATE_VAR_MISSING" and err.safe_details["path"] == "nope.deep"
    assert tt.render_template("{{#each nope}}x{{/each}}-", {}) == "-"
    assert _reason(tt.render_template, "{{#each nope}}x{{/each}}", {}, missing="error").reason == "TEMPLATE_VAR_MISSING"


@pytest.mark.parametrize("template", ["{{#each a}}x", "x{{/if}}", "{{#if a}}{{/each}}", "{{}}", "{{#each}}{{/each}}", "{{else}}"])
def test_문법_오류는_TEMPLATE_SYNTAX_INVALID(template):
    err = _reason(tt.render_template, template, {"a": [1]})
    assert err.reason == "TEMPLATE_SYNTAX_INVALID" and err.field == "template" and "position" in err.safe_details


def test_변수를_비우면_직전_출력을_JSON_으로_읽고_아니면_input_으로():
    assert tt.render_template("{{a}}", "", upstream_text='{"a": 7}') == "7"
    assert tt.render_template("<{{input}}>", None, upstream_text="그냥 텍스트") == "<그냥 텍스트>"
    assert tt.render_template("{{#each items}}{{this}};{{/each}}", None, upstream_text="[1, 2]") == "1;2;"
    assert tt.render_template("{{value}}|{{input}}", None, upstream_text="42") == "42|42"
    assert tt.render_template("{{a}} {{input}}", '{"a": 1}', upstream_text="원문") == "1 원문", "변수 JSON 을 줘도 원문은 input 으로"
    assert _reason(tt.render_template, "{{a}}", "{bad").reason == "TEMPLATE_VARIABLES_INVALID"
    assert tt.render_template("{{a}}", {"a": 1}) == "1", "dict 를 그대로 받는다(바인딩)"


def test_객체_반복과_값_형식():
    assert tt.render_template("{{#each m}}{{key}}={{value}};{{/each}}", {"m": {"a": 1, "b": [1, 2]}}) == "a=1;b=[1, 2];"
    assert tt.render_template("{{f}}|{{g}}|{{t}}|{{n}}", {"f": 2.0, "g": 2.5, "t": False, "n": None}) == "2|2.5|false|"


def test_템플릿이_참조하는_최상위_변수_목록():
    assert tt.template_variables("{{title}} {{#each items}}{{this.x}} {{outer}}{{/each}} {{#if ok}}{{meta.a}}{{/if}}") == ["title", "items", "ok", "meta"]
    assert tt.template_variables("{{#each a}}") == []


# ── 5. 정의·카탈로그·오류 코드 ─────────────────────────────────────────────

UTILITY_TYPES = ("regexExtractNode", "textDiffNode", "dataConvertNode", "templateRenderNode")


@pytest.mark.parametrize("node_type", UTILITY_TYPES)
def test_정의는_결정적_비커넥터다(node_type):
    definition = node_definition.get_definition(node_type)
    assert definition is not None and definition.connector is None and definition.sideEffect == "none"
    assert definition.credentials == [] and definition.capabilities == [] and definition.category == "code"


def test_오류_코드가_카탈로그에_있고_validation_범주다():
    for code in ("TOOL_INPUT_TOO_LARGE", "TOOL_OUTPUT_TOO_LARGE", "REGEX_INVALID", "REGEX_NO_MATCH", "CONVERT_PARSE_FAILED",
                 "CONVERT_UNSUPPORTED", "TEMPLATE_SYNTAX_INVALID", "TEMPLATE_VAR_MISSING", "TEMPLATE_VARIABLES_INVALID"):
        entry = error_catalog.get(code)
        assert entry.category == "validation" and entry.retryable is False and entry.resolution == "focus_field", code


# ── 6. 그래프 실행(두 엔진이 같은 생성기를 지난다) ──────────────────────────

def _graph(node_type, data, entry_payload):
    graph = {"nodes": [{"id": "w1", "type": "webhookNode", "data": {}},
                       {"id": "t1", "type": node_type, "data": data},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "w1", "target": "t1"}, {"id": "e2", "source": "t1", "target": "o1"}]}
    return mock_service.run(graph, db=None, project_id=1, entry_node_id="w1", payload=entry_payload)


def _step(result, node_id):
    return next(step for step in result["logs"] if step.get("node_id") == node_id)


def test_그래프_안에서_직전_출력을_받아_렌더한다():
    result = _graph("templateRenderNode", {"template": "PR #{{number}} {{title}} by {{author}}"},
                    {"number": 42, "title": "로그인 검사", "author": "octocat"})
    assert result["success"] is True, result["result"]
    assert _step(result, "t1")["result_data"] == "PR #42 로그인 검사 by octocat"


def test_그래프_안에서_정규식과_diff_와_변환이_이어진다():
    result = _graph("regexExtractNode", {"pattern": r"(?P<t>[A-Z]+-\d+)", "mode": "all", "group": "t"}, "ABC-1 과 DEF-22")
    assert json.loads(_step(result, "t1")["result_data"]) == ["ABC-1", "DEF-22"]
    result = _graph("textDiffNode", {"oldText": "a\nb", "newText": "{{last_result}}"}, "a\nc")
    diff = json.loads(_step(result, "t1")["result_data"])
    assert diff["changed"] is True and diff["added"] == 1 and diff["removed"] == 1
    result = _graph("dataConvertNode", {"toFormat": "toml"}, {"a": {"b": 1}})
    assert _step(result, "t1")["result_data"].strip() == "[a]\nb = 1"


def test_그래프_안의_실패는_NodeError_코드로_남고_결과에_스택이_섞이지_않는다():
    result = _graph("regexExtractNode", {"pattern": "(", "mode": "first"}, "x")
    step = _step(result, "t1")
    assert step["result_data"].startswith("[⚠️") and "Traceback" not in step["result_data"]
    error = step.get("error") or {}
    assert error.get("code") == "REGEX_INVALID", error
    assert error.get("field") == "pattern"
    result = _graph("templateRenderNode", {"template": "{{nope}}", "missing": "error"}, {"a": 1})
    assert (_step(result, "t1").get("error") or {}).get("code") == "TEMPLATE_VAR_MISSING"
    result = _graph("dataConvertNode", {"toFormat": "toml"}, "not structured")
    assert (_step(result, "t1").get("error") or {}).get("code") == "CONVERT_PARSE_FAILED"


# ── 7. 정규식 도우미 ───────────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.answers.pop(0)


def test_정규식_제안은_컴파일_확인_뒤_샘플_매치까지_돌려준다():
    llm = _FakeLLM([regex_assist.SuggestedRegex(pattern=r"(?P<ticket>[A-Z]+-\d+)", explanation="대문자-숫자 티켓")])
    out = regex_assist.suggest("티켓 번호", "ABC-1 그리고 DEF-22", llm=llm)
    assert out["pattern"] == r"(?P<ticket>[A-Z]+-\d+)" and out["matchCount"] == 2 and out["preview"] == ["ABC-1", "DEF-22"]
    assert out["explanation"] == "대문자-숫자 티켓" and out["ignoreCase"] is False


def test_컴파일_안_되는_제안은_한_번_다시_시도하고_그래도_안_되면_실패():
    llm = _FakeLLM([regex_assist.SuggestedRegex(pattern="("), regex_assist.SuggestedRegex(pattern=r"\d+", ignore_case=True)])
    out = regex_assist.suggest("숫자", "a1b22", llm=llm)
    assert out["pattern"] == r"\d+" and out["ignoreCase"] is True and len(llm.calls) == 2
    assert "컴파일되지 않았다" in llm.calls[1][1][1]
    with pytest.raises(regex_assist.RegexAssistError):
        regex_assist.suggest("숫자", "", llm=_FakeLLM([regex_assist.SuggestedRegex(pattern="("), regex_assist.SuggestedRegex(pattern="[")]))
    with pytest.raises(regex_assist.RegexAssistError):
        regex_assist.suggest("   ", "", llm=_FakeLLM([]))
