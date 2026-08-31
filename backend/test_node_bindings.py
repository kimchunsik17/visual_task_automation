"""필드 데이터 바인딩(BindingSpec v1, 계획 DATA_FLOW_SEPARATION_PLAN Phase 0) 검사.

완료 기준(§8): UI 없이 data.bindings 만으로 웹훅 payload → emailNode.toEmail 이
LLM·jsonParser 없이 동작한다.
"""

from __future__ import annotations

import ast
import json

import pytest

import node_bindings
from dry_run import dry_run_workflow
from graph import compile_workflow
from meta_agent import FlowGraph, validate_flow


# ── 완료 기준 그래프: 웹훅 payload 의 값이 필드로 직접 들어간다 ──────────

def _webhook_email_graph(bindings=None, *, source="n1"):
    return (
        [
            {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/order"}},
            {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "요약가"}},
            {"id": "n3", "type": "emailNode", "data": {
                "toEmail": "", "subject": "주문 확인",
                "bindings": bindings if bindings is not None else {
                    "toEmail": {"source": source, "path": "customer.email"},
                },
            }},
        ],
        [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    )


def _preamble(source: str) -> dict:
    """생성 코드의 프리앰블만 실행해 런타임 헬퍼를 얻는다."""
    cut = source.index("def run_workflow(")
    namespace: dict = {}
    exec(source[:cut], namespace)  # noqa: S102 — 방금 생성한 코드다
    return namespace


# ── 계약(정적) ──────────────────────────────────────────────────────────

def test_bindings_are_parsed_and_normalized():
    node = {"id": "n3", "type": "emailNode", "data": {"bindings": {
        "toEmail": {"source": "n1", "path": "customer.email"},
        "subject": {"source": "n1"},                     # path 없음 = 출력 전체
        "bogus": "문자열은 무시",                          # dict 아님
        "noSource": {"path": "a"},                        # source 없음
    }}}
    parsed = node_bindings.bindings_of(node)
    assert set(parsed) == {"toEmail", "subject"}
    assert parsed["toEmail"] == {"source": "n1", "path": "customer.email", "required": True}
    assert parsed["subject"]["path"] == ""


def test_unsupported_field_is_rejected_not_ignored():
    """지원하지 않는 필드에 바인딩이 걸리면 조용히 무시하지 않는다 — 사용자는 '연결했는데
    값이 안 온다'만 겪게 되기 때문이다."""
    nodes, edges = _webhook_email_graph({"attachments": {"source": "n1"}})
    issues = node_bindings.validate_bindings(nodes, edges)
    assert any("바인딩을 지원하지 않는다" in issue for issue in issues), issues


def test_source_must_be_upstream_on_execution_path():
    nodes, edges = _webhook_email_graph()
    # n3 → n1 방향이 없으므로 n9 는 상류가 아니다
    nodes.append({"id": "n9", "type": "valueNode", "data": {"value": "x"}})
    nodes[2]["data"]["bindings"] = {"toEmail": {"source": "n9", "path": "a"}}
    issues = node_bindings.validate_bindings(nodes, edges)
    assert any("상류가 아니다" in issue for issue in issues), issues


def test_missing_source_and_self_reference_are_rejected():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "없는노드"}})
    assert any("노드가 없다" in i for i in node_bindings.validate_bindings(nodes, edges))
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "n3"}})
    assert any("자기 자신" in i for i in node_bindings.validate_bindings(nodes, edges))


def test_bad_path_syntax_is_rejected():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "n1", "path": "customer..email"}})
    assert any("경로" in i for i in node_bindings.validate_bindings(nodes, edges))


def test_validate_flow_surfaces_binding_issues():
    nodes, edges = _webhook_email_graph({"attachments": {"source": "n1"}})
    graph = FlowGraph(nodes=nodes, edges=edges)
    ok, errors = validate_flow(graph, require_complete=False)
    assert not ok and any("바인딩을 지원하지 않는다" in e for e in errors), errors


def test_extract_path_walks_dicts_and_lists():
    payload = {"customer": {"email": "a@b.com"}, "items": [{"name": "첫 항목"}]}
    assert node_bindings.extract_path(payload, "customer.email") == (True, "a@b.com")
    assert node_bindings.extract_path(payload, "items[0].name") == (True, "첫 항목")
    assert node_bindings.extract_path(payload, "items[5].name")[0] is False
    assert node_bindings.extract_path(payload, "없는키")[0] is False
    assert node_bindings.extract_path("문자열", "") == (True, "문자열")


# ── 코드젠 ──────────────────────────────────────────────────────────────

def test_bound_field_becomes_runtime_lookup_not_literal():
    """§7 리스크 1 — 코드젠이 값을 컴파일 타임 리터럴로 굽는다. 바인딩된 필드는
    반드시 런타임 조회로 바뀌어야 한다."""
    nodes, edges = _webhook_email_graph()
    source = compile_workflow(nodes, edges)
    assert not source.startswith("Error"), source[:300]
    ast.parse(source)
    assert "_resolve_binding('n3', 'toEmail'" in source
    # 바인딩 없는 필드는 리터럴로 남는다(불필요한 런타임 조회를 만들지 않는다).
    assert "_resolve_binding('n3', 'subject'" not in source


def test_runtime_map_is_embedded_for_bound_nodes_only():
    nodes, edges = _webhook_email_graph()
    source = compile_workflow(nodes, edges)
    namespace = _preamble(source)
    assert namespace["__node_bindings__"] == {
        "n3": {"toEmail": {"source": "n1", "path": "customer.email", "required": True}}}


def test_unbound_graph_is_unchanged():
    """바인딩이 없는 기존 그래프는 런타임 조회가 끼어들지 않는다(후방 호환)."""
    nodes, edges = _webhook_email_graph({})
    source = compile_workflow(nodes, edges)
    assert "_resolve_binding(" not in source.split("def run_workflow(")[1]
    namespace = _preamble(source)
    assert namespace["__node_bindings__"] == {}


# ── 런타임 해석 ─────────────────────────────────────────────────────────

def _resolver(nodes, edges, *, results, meta=None):
    namespace = _preamble(compile_workflow(nodes, edges))
    namespace["__node_results__"].update(results)
    namespace["__node_meta__"].update(meta or {})
    return namespace["_resolve_binding"]


def test_resolves_json_path_from_upstream_result():
    """완료 기준 — 웹훅 payload 의 customer.email 이 LLM·jsonParser 없이 필드에 들어온다."""
    nodes, edges = _webhook_email_graph()
    resolve = _resolver(nodes, edges, results={
        "n1": json.dumps({"customer": {"email": "buyer@example.com"}, "orderId": 1024}),
    })
    assert resolve("n3", "toEmail", "") == "buyer@example.com"


def test_resolves_fenced_json_and_nested_list():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "n1", "path": "items[1].email"}})
    resolve = _resolver(nodes, edges, results={
        "n1": '```json\n{"items": [{"email": "a@x.com"}, {"email": "b@x.com"}]}\n```',
    })
    assert resolve("n3", "toEmail", "") == "b@x.com"


def test_whole_output_when_path_is_empty():
    nodes, edges = _webhook_email_graph({"subject": {"source": "n2"}})
    resolve = _resolver(nodes, edges, results={"n2": "요약된 제목"})
    assert resolve("n3", "subject", "기본") == "요약된 제목"


def test_dict_value_is_serialized_for_string_field():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "n1", "path": "customer"}})
    resolve = _resolver(nodes, edges, results={"n1": json.dumps({"customer": {"email": "a@b.com"}})})
    assert json.loads(resolve("n3", "toEmail", "")) == {"email": "a@b.com"}


def test_source_not_run_raises_domain_error():
    """분기로 소스가 실행되지 않은 경우 — 조용히 기본값으로 넘어가지 않는다."""
    nodes, edges = _webhook_email_graph()
    resolve = _resolver(nodes, edges, results={})
    from node_errors.contract import NodeErrorException
    with pytest.raises(NodeErrorException) as exc:
        resolve("n3", "toEmail", "")
    assert exc.value.error.code == "BINDING_SOURCE_NOT_RUN"


def test_source_error_does_not_leak_into_field():
    """ADR-0025 연장 — 오류 문구가 데이터로 위장해 필드에 들어가면 안 된다."""
    nodes, edges = _webhook_email_graph()
    resolve = _resolver(
        nodes, edges,
        results={"n1": "수집하지 않았습니다: robots.txt 차단"},
        meta={"n1": {"status": "error", "error_code": "URL_BLOCKED"}})
    from node_errors.contract import NodeErrorException
    with pytest.raises(NodeErrorException) as exc:
        resolve("n3", "toEmail", "")
    assert exc.value.error.code == "BINDING_SOURCE_FAILED"


def test_missing_path_raises_unless_optional():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "n1", "path": "customer.phone"}})
    resolve = _resolver(nodes, edges, results={"n1": json.dumps({"customer": {"email": "a@b.com"}})})
    from node_errors.contract import NodeErrorException
    with pytest.raises(NodeErrorException) as exc:
        resolve("n3", "toEmail", "")
    assert exc.value.error.code == "BINDING_PATH_MISSING"

    # required=False 면 기본값으로 조용히 넘어간다 — 선택 필드용 탈출구.
    nodes2, edges2 = _webhook_email_graph(
        {"toEmail": {"source": "n1", "path": "customer.phone", "required": False}})
    resolve2 = _resolver(nodes2, edges2, results={"n1": json.dumps({"customer": {}})})
    assert resolve2("n3", "toEmail", "fallback@x.com") == "fallback@x.com"


# ── dry_run ─────────────────────────────────────────────────────────────

def test_dry_run_passes_for_valid_bindings():
    nodes, edges = _webhook_email_graph()
    result = dry_run_workflow({"nodes": nodes, "edges": edges})
    assert result.compile_passed, result.issues
    assert not any("바인딩" in issue for issue in result.issues), result.issues


def test_dry_run_reports_invalid_binding():
    nodes, edges = _webhook_email_graph({"toEmail": {"source": "없는노드"}})
    result = dry_run_workflow({"nodes": nodes, "edges": edges})
    assert any("바인딩" in issue for issue in result.issues), result.issues


# ── 지원 목록 드리프트 ──────────────────────────────────────────────────

# 각 노드가 코드젠까지 가는 데 필요한 최소 data. 바인딩 대상 필드도 기본값을 넣어 둔다 —
# 바인딩이 있으면 생성기가 리터럴 대신 런타임 조회를 쓰는지가 이 테스트의 관심사다.
MINIMAL_DATA = {
    "emailNode": {"toEmail": "a@b.com", "subject": "제목"},
    "discordNode": {"channelId": "1234"},
    "slackNode": {"channel": "#general", "message": "안녕"},
    "telegramNode": {"botToken": "t", "chatId": "1234"},
    "kakaoNode": {"accessToken": "t", "receiver": ""},
    "httpRequestNode": {"method": "GET", "url": "https://example.com"},
    "formatNode": {"formatId": "incident-report", "output": "hwpx"},
    "webCrawlerNode": {"url": "https://example.com"},
    "valueNode": {"value": ""},
}


@pytest.mark.parametrize("node_type,field", [
    (t, f) for t, fields in node_bindings.BINDABLE_FIELDS.items() for f in fields
], ids=lambda v: v if isinstance(v, str) else str(v))
def test_declared_bindable_fields_are_actually_wired(node_type, field):
    """BINDABLE_FIELDS 에 선언했지만 생성기가 런타임 조회로 바꾸지 않으면, 사용자는
    바인딩을 걸어도 값이 안 오는 것을 겪는다. 실제 컴파일 결과로 대조한다."""
    assert node_type in MINIMAL_DATA, f"{node_type}: MINIMAL_DATA 에 최소 data 를 추가하라"
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "promptNode", "data": {"userPrompt": "x"}},
        {"id": "n3", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "s"}},
        {"id": "n4", "type": node_type, "data": {
            **MINIMAL_DATA[node_type],
            "bindings": {field: {"source": "n3", "path": "value"}},
        }},
    ]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}"} for i in (1, 2, 3)]
    source = compile_workflow(nodes, edges)
    assert not source.startswith("Error"), f"{node_type}.{field}: {source[:200]}"
    assert f"_resolve_binding('n4', {field!r}" in source, (
        f"{node_type}.{field} 은 BINDABLE_FIELDS 에 있지만 생성기가 런타임 조회로 바꾸지 않는다")


# --- 변수 허브 (계획 §5-5) ------------------------------------------------------
# 이름이 붙은 valueNode 는 "값 그대로"를 내보낸다. 앞 결과에 이어 붙이면 하류가 path 없이
# 허브를 바인딩했을 때 앞 결과까지 섞여 들어간다 — 허브의 의미가 깨진다.

def _hub_source(value_data):
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "promptNode", "data": {"userPrompt": "x"}},
        {"id": "n3", "type": "valueNode", "data": value_data},
        {"id": "n4", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}"} for i in (1, 2, 3)]
    source = compile_workflow(nodes, edges)
    assert not source.startswith("Error"), source[:300]
    return source


def test_named_value_node_does_not_append_previous_result():
    source = _hub_source({"varName": "담당자", "value": "ops@example.com"})
    assert 'val_n3 = "ops@example.com"' in source
    assert "[Value]:" not in source


def test_unnamed_value_node_keeps_appending_previous_result():
    """후방 호환 — 이름 없는 valueNode 는 기존처럼 앞 결과에 이어 붙인다."""
    source = _hub_source({"value": "ops@example.com"})
    assert "[Value]:" in source


def test_bound_value_node_takes_upstream_path_only():
    source = _hub_source({
        "varName": "받는사람",
        "value": "fallback@example.com",
        "bindings": {"value": {"source": "n2", "path": "customer.email"}},
    })
    assert "val_n3 = _resolve_binding('n3', 'value', 'fallback@example.com')" in source
    assert "[Value]:" not in source


# --- 프롬프트 통합 (계획 §6) ----------------------------------------------

def test_binding_guide_is_injected_into_generation_prompts():
    """가이드가 4개 생성 프롬프트에 들어가고, 카탈로그 트리밍 후에도 남아야 한다 —
    트리밍은 SYSTEM.replace(NODE_CATALOG, ...) 방식이라 블록이 카탈로그 뒤에 있어야 한다."""
    import meta_agent
    block = node_bindings.BINDING_CATALOG
    for name in ("SYSTEM", "MEDIUM_SYSTEM", "PRECISE_SYSTEM", "AGENT_SYSTEM_PROMPT"):
        prompt = getattr(meta_agent, name)
        assert block in prompt, f"{name} 에 [데이터 바인딩] 블록이 없다"
        trimmed = prompt.replace(meta_agent.NODE_CATALOG, "TRIMMED", 1)
        assert block in trimmed, f"{name} 트리밍 후 블록이 사라진다"


def test_binding_guide_lists_every_bindable_field():
    """가이드는 BINDABLE_FIELDS 에서 파생한다 — 손으로 적은 목록이 갈라지는 것을 막는다."""
    guide = node_bindings.render_binding_guide()
    for node_type, fields in node_bindings.BINDABLE_FIELDS.items():
        assert node_type in guide, f"{node_type} 이 가이드에 없다"
        for field in fields:
            assert field in guide, f"{node_type}.{field} 이 가이드에 없다"


def test_path_documented_sources_exist_in_catalog():
    """path 를 허용한 소스가 실제로 카탈로그에 있는 노드인지 — 이름이 바뀌거나 노드가
    사라지면 모델에게 없는 노드의 경로를 가르치게 된다."""
    import meta_agent
    for node_type in node_bindings.PATH_DOCUMENTED_SOURCES:
        assert f"- {node_type}" in meta_agent.NODE_CATALOG, (
            f"{node_type} 이 NODE_CATALOG 에 없다 — PATH_DOCUMENTED_SOURCES 를 갱신하라")


def test_fewshot_examples_are_valid_json_and_pass_validation():
    """few-shot 은 모델이 그대로 흉내내는 정답지다. 파싱조차 안 되는 예시는
    잘못된 이스케이프를 가르친다(2026-08-31: jsonSchema 의 \\" 와 value 의 \\n 이
    파이썬 리터럴에서 소비돼 프롬프트에 깨진 JSON 이 들어가 있었다)."""
    import json
    import re

    import meta_agent
    from meta_agent import FlowGraph, validate_flow

    # 유일한 예외: 사용자가 실제 주소를 주지 않은 발송 예시는 toEmail 을 일부러 비워 둔다
    # (지어내지 않는 쪽이 맞다 — 카탈로그 규칙). 그 외 검증 오류는 실제 결함이다.
    ALLOWED = {"toEmail이 없다"}

    for name in ("FEWSHOT_FAST", "FEWSHOT_PRECISE"):
        fewshot = getattr(meta_agent, name)
        found = re.findall(r"\[예시(\d+)\] 요청: .*?\n(\{.*?\n\]\})", fewshot, re.S)
        assert len(found) >= 15, f"{name} 예시 추출이 깨졌다({len(found)}개)"
        for index, raw in found:
            data = json.loads(raw)          # 파싱 실패는 그대로 테스트 실패
            _, errors = validate_flow(FlowGraph(**data))
            unexpected = [e for e in errors if not any(a in e for a in ALLOWED)]
            assert not unexpected, f"{name} 예시{index}: {unexpected}"


def test_fewshot_teaches_bindings():
    """바인딩 예시가 두 티어 모두에 있어야 한다 — 규칙만 있고 예시가 없으면 잘 안 쓴다."""
    import meta_agent
    for name in ("FEWSHOT_FAST", "FEWSHOT_PRECISE"):
        assert '"bindings"' in getattr(meta_agent, name), f"{name} 에 바인딩 예시가 없다"


def test_bound_required_field_passes_validation():
    """바인딩이 걸린 필수 필드는 지금 비어 있어도 통과해야 한다 — 아니면 '값을 연결했는데
    검증이 막는' 상태가 된다. 반대로 바인딩이 없으면 그대로 막혀야 한다."""
    from meta_agent import FlowGraph, validate_flow

    def flow(email_data):
        return FlowGraph(**{
            "nodes": [
                {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/x"}},
                {"id": "n2", "type": "emailNode", "data": email_data},
            ],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        })

    bound = {"toEmail": "", "subject": "s",
             "bindings": {"toEmail": {"source": "n1", "path": "email"}}}
    assert validate_flow(flow(bound))[0], validate_flow(flow(bound))[1]
    assert not validate_flow(flow({"toEmail": "", "subject": "s"}))[0]
    # 지원하지 않는 필드에 붙인 바인딩으로는 필수 검사를 무력화할 수 없다
    sneaky = {"toEmail": "", "subject": "s",
              "bindings": {"body": {"source": "n1", "path": ""}}}
    assert not validate_flow(flow(sneaky))[0]


# --- bind_field 대화형 편집 도구 (계획 §6-3) --------------------------------

def _bind_tool_fixture():
    import meta_agent
    from meta_agent import FlowGraph
    graph = FlowGraph(title="", description="", nodes=[
        {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/order"}},
        {"id": "n2", "type": "emailNode", "data": {"toEmail": "a@b.com", "subject": "주문"}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ], edges=[{"id": "e1", "source": "n1", "target": "n2"},
              {"id": "e2", "source": "n2", "target": "n3"}])
    tools, get_graph, _c, _l = meta_agent.make_tools(graph)
    return next(t for t in tools if t.name == "bind_field"), get_graph


def test_bind_field_creates_binding():
    bind, get_graph = _bind_tool_fixture()
    result = bind.invoke({"node_id": "n2", "field": "toEmail",
                          "source_node_id": "n1", "path": "customer.email"})
    assert "실패" not in result, result
    node = next(n for n in get_graph().nodes if n.id == "n2")
    assert node.data["bindings"]["toEmail"] == {"source": "n1", "path": "customer.email"}


def test_bind_field_clears_binding_with_empty_source():
    bind, get_graph = _bind_tool_fixture()
    bind.invoke({"node_id": "n2", "field": "toEmail", "source_node_id": "n1", "path": ""})
    result = bind.invoke({"node_id": "n2", "field": "toEmail", "source_node_id": ""})
    assert "실패" not in result, result
    node = next(n for n in get_graph().nodes if n.id == "n2")
    assert "bindings" not in node.data


def test_bind_field_rejects_unsupported_field():
    bind, get_graph = _bind_tool_fixture()
    result = bind.invoke({"node_id": "n2", "field": "body", "source_node_id": "n1"})
    assert "실패" in result and "지원하지 않는다" in result
    node = next(n for n in get_graph().nodes if n.id == "n2")
    assert "bindings" not in node.data


def test_bind_field_rejects_downstream_source():
    """뒤 노드를 가리키면 실행 시점에 값이 없다 — 검증이 잡아 롤백해야 한다."""
    bind, get_graph = _bind_tool_fixture()
    result = bind.invoke({"node_id": "n2", "field": "toEmail", "source_node_id": "n3"})
    assert "실패" in result, result
    node = next(n for n in get_graph().nodes if n.id == "n2")
    assert "bindings" not in node.data


def test_bind_field_is_registered_as_a_tool():
    """도구 목록에서 빠지면 프롬프트에만 존재하는 유령 도구가 된다."""
    import meta_agent
    from meta_agent import FlowGraph
    tools, _g, _c, _l = meta_agent.make_tools(FlowGraph(title="", description="", nodes=[], edges=[]))
    assert "bind_field" in {t.name for t in tools}
    assert "bind_field" in meta_agent.AGENT_SYSTEM_PROMPT


def test_repair_removes_unexecutable_bindings():
    """생성 모델이 다른 노드의 필드 이름을 옮겨 적는 일이 실제로 관찰됐다(formatNode.toEmail).
    그 바인딩은 실행에 아무 영향이 없는데 검증만 실패시킨다 — 결정적 수리에서 정리한다.
    사용자가 만든 바인딩은 이 경로를 타지 않는다(에디터에서는 validate_bindings 가 거부)."""
    from meta_agent import FlowGraph, repair_disconnected_flow, validate_flow

    graph = FlowGraph(title="", description="", nodes=[
        {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/x"}},
        {"id": "n2", "type": "formatNode", "data": {
            "formatId": "incident-report", "output": "hwpx",
            "bindings": {"values": {"source": "n1", "path": ""},
                         "toEmail": {"source": "n1", "path": "managerEmail"}}}},
        {"id": "n3", "type": "emailNode", "data": {
            "toEmail": "", "subject": "시말서",
            "bindings": {"toEmail": {"source": "n9", "path": "managerEmail"}}}},
    ], edges=[{"id": "e1", "source": "n1", "target": "n2"},
              {"id": "e2", "source": "n2", "target": "n3"}])

    repaired, notes = repair_disconnected_flow(graph)
    by_id = {n.id: n for n in repaired.nodes}
    # 지원하는 필드는 그대로, 지원하지 않는 필드는 사라진다
    assert set(by_id["n2"].data["bindings"]) == {"values"}
    # 없는 소스를 가리킨 바인딩도 제거된다(그 노드는 필수값 검사로 돌아간다)
    assert "bindings" not in by_id["n3"].data
    assert any("toEmail" in note for note in notes), notes


# --- 문서 노드 공동 선별 (2026-08-31 평가에서 발견) ------------------------

def test_document_requests_always_offer_format_node():
    """선별 LLM 이 구형 문서 경로만 고르면 formatNode 는 카탈로그에 아예 없어서 생성이 쓸
    방법이 없다(설명 수정으로는 못 고친다 — 설명이 프롬프트에 들어가지 않으니까)."""
    import meta_agent

    for trigger in ("templateAnalyzerNode", "fileModifierNode", "hwpxDocumentNode", "posterGeneratorNode"):
        augmented = meta_agent.apply_selection_augmentation(["startNode", trigger, "emailNode"])
        assert "formatNode" in augmented, trigger
        catalog = meta_agent.build_trimmed_catalog(["startNode", trigger, "emailNode"])
        assert "- formatNode" in catalog, f"{trigger}: 트리밍된 카탈로그에 formatNode 항목이 없다"


def test_selection_augmentation_does_not_fire_on_unrelated_requests():
    """문서와 무관한 요청에 formatNode 설명을 끼워 넣으면 프롬프트만 길어진다."""
    import meta_agent
    augmented = meta_agent.apply_selection_augmentation(["startNode", "webCrawlerNode", "slackNode"])
    assert "formatNode" not in augmented
    catalog = meta_agent.build_trimmed_catalog(["startNode", "webCrawlerNode", "slackNode"])
    assert "- formatNode" not in catalog


def test_selection_augmentation_keeps_order_and_uniqueness():
    import meta_agent
    already = ["hwpxDocumentNode", "formatNode", "emailNode"]
    assert meta_agent.apply_selection_augmentation(already) == already


def test_optional_binding_does_not_exempt_required_field():
    """선택 연결(required: false)은 값이 없으면 그냥 넘어간다 — 필드까지 비어 있으면 실행 시
    진짜로 값 없이 동작하므로 대체값이 필요하다. 필수 연결만 면제 대상이다."""
    from meta_agent import FlowGraph, validate_flow

    def flow(email_data):
        return FlowGraph(**{
            "nodes": [
                {"id": "n1", "type": "webhookNode", "data": {"method": "POST", "path": "/x"}},
                {"id": "n2", "type": "emailNode", "data": email_data},
            ],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        })

    optional_empty = {"toEmail": "", "subject": "s",
                     "bindings": {"toEmail": {"source": "n1", "path": "email", "required": False}}}
    assert not validate_flow(flow(optional_empty))[0], "선택 연결 + 빈 필드는 막아야 한다"

    # 대체값이 있으면 통과한다 — 값이 없을 때 이 값으로 보낸다는 뜻이 분명하다
    optional_with_default = {"toEmail": "ops@example.com", "subject": "s",
                             "bindings": {"toEmail": {"source": "n1", "path": "email", "required": False}}}
    assert validate_flow(flow(optional_with_default))[0], validate_flow(flow(optional_with_default))[1]


# --- 안정화 측정 도구 (backend/binding_stabilization_eval.py) ----------------
# 도구가 조용히 썩는 것을 막는다 — 크레딧이 없어 실제 측정은 미뤘지만(계획 §10),
# 판정 로직은 LLM 없이 검사할 수 있다.

def test_stabilization_tool_path_classifier():
    import binding_stabilization_eval as tool

    prompt = "웹훅으로 주문이 들어오면 주문한 사람에게 메일 보내줘."
    invented = {"nodes": [
        {"id": "n1", "type": "webhookNode", "data": {}},
        {"id": "n2", "type": "emailNode", "data": {
            "bindings": {"toEmail": {"source": "n1", "path": "customer.email"}}}},
    ]}
    # 요청에 키 이름이 없고 웹훅은 출력 형식이 문서화된 소스가 아니다 → 지어낸 경로
    assert tool.classify_binding_paths(prompt, invented)["invented"]
    # 요청이 키를 말했으면 근거가 있다
    assert not tool.classify_binding_paths(
        "웹훅으로 문의가 오면 email 키의 주소로 메일 보내줘.", invented)["invented"]
    # 출력 형식이 문서화된 소스는 요청에 키가 없어도 허용된다
    documented = {"nodes": [
        {"id": "n1", "type": "naverSearchNode", "data": {}},
        {"id": "n2", "type": "webCrawlerNode", "data": {
            "bindings": {"url": {"source": "n1", "path": "items[0].link"}}}},
    ]}
    verdict = tool.classify_binding_paths("네이버에서 찾아서 첫 글 크롤링해줘", documented)
    assert verdict["grounded"] and not verdict["invented"]


def test_stabilization_tool_probe_prompts_do_not_name_keys():
    """탐침 프롬프트가 키 이름을 말해버리면 측정이 무의미해진다 — 대조군과 구분을 지킨다."""
    import binding_stabilization_eval as tool
    for prompt in tool.PATH_PROBE_PROMPTS:
        lowered = prompt.lower()
        assert not any(key in lowered for key in ("email", "name", "id", "키")), prompt
    assert any("email" in p.lower() for p in tool.PATH_CONTROL_PROMPTS)


def test_path_grammar_allows_top_level_arrays():
    """rssTriggerNode·gmailTriggerNode 등은 **새 항목 배열**을 그대로 내보내므로 경로가
    "[0].link" 로 시작한다. 가이드 힌트와 에디터 픽커가 그 경로를 만들어 내는데도 문법이
    거부하고 있었다(2026-08-31 템플릿 작성 중 발견)."""
    valid = ["customer.email", "items[0].link", "[0].link", "[0]", "[0][1]",
             "data.rows[0][0]", "받는사람.이메일"]
    invalid = ["a..b", ".link", "[0]link", "a.", "[a]"]
    for path in valid:
        assert node_bindings._PATH_OK.match(path), path
    for path in invalid:
        assert not node_bindings._PATH_OK.match(path), path

    # 런타임 추출도 같은 경로를 따라가야 한다 — 문법만 열고 추출이 못 따라가면 실행에서 죽는다
    assert node_bindings.extract_path([{"link": "https://x"}], "[0].link") == (True, "https://x")
    assert node_bindings.extract_path(["a", "b"], "[1]") == (True, "b")


def test_top_level_array_path_passes_flow_validation():
    """문법만 고치고 validate_bindings 경로를 놓치면 여전히 게시·생성이 막힌다."""
    from meta_agent import FlowGraph, validate_flow
    graph = FlowGraph(**{
        "nodes": [
            {"id": "n1", "type": "rssTriggerNode", "data": {"feedUrl": "https://example.com/rss", "maxItems": 5}},
            {"id": "n2", "type": "webCrawlerNode", "data": {
                "url": "", "output": "text",
                "bindings": {"url": {"source": "n1", "path": "[0].link"}}}},
            {"id": "n3", "type": "outputNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"},
                  {"id": "e2", "source": "n2", "target": "n3"}],
    })
    ok, errors = validate_flow(graph)
    assert ok, errors
