"""node_bodies — 노드 본문 렌더러 (백로그 32 ENGINE-0 2단계, 하이브리드 래퍼의 재료) 테스트.

계약: (1) 어떤 노드 타입이 "본문만 떼어 내어 exec 할 수 있는가(wrappable)"는 정확히 NATIVE_FLOW_TYPES 의
보수다 · (2) 떼어 낸 본문을 프렐류드 네임스페이스 위에서 차례로 exec 하면 옛 엔진(compile_workflow → exec)과
같은 실행 로그·노드 결과·최종 값을 낸다 · (3) 하류 호출 기록(prev_res_var·active_llm_id)이 생성기의 배선과 같다.
"""

from __future__ import annotations

import json

import pytest

import graph
import graph_traversal as gt
import models
import node_bodies
from node_registry import node_registry

ALL_TYPES = sorted(node_registry._generators.keys())


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None, target_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    if target_handle is not None:
        e["targetHandle"] = target_handle
    return e


def _render(nodes, edges, node_id, **kw):
    prepared = gt.prepare_graph(nodes, edges)
    idx = gt.classify_edges(prepared.edges)
    return node_bodies.render_node_body(node_id, node_dict=prepared.node_dict, forward_edges=idx.forward_edges,
                                        incoming_edges=idx.incoming_edges, **kw)


# ── 1. 감쌀 수 있는 타입의 목록 ────────────────────────────────────────────

@pytest.mark.parametrize("node_type", ALL_TYPES)
def test_최소_그래프에서_본문은_모듈_수준_파이썬으로_파싱된다(node_type):
    nodes = [N("s", "startNode"), N("n", node_type), N("o", "outputNode")]
    r = _render(nodes, [E("s", "n"), E("n", "o")], "n", prev_res_var="last_result")
    assert r.lines, f"{node_type}: 본문이 비었다"
    assert node_bodies.parses_standalone(r), f"{node_type}: indent='' 본문이 파싱되지 않는다"


@pytest.mark.parametrize("node_type", ALL_TYPES)
def test_감쌀_수_없는_타입은_정확히_NATIVE_FLOW_TYPES_다(node_type):
    """흐름 노드가 아닌 모든 타입은 최소 그래프에서 wrappable 이어야 한다. 흐름 노드는 대표 그래프
    (핸들·본문 간선을 갖춘)에서 wrappable 이 아니어야 한다 — 양쪽이 어긋나면 인터프리터가 어떤
    노드를 직접 구현해야 하는지 목록이 틀린 것이다."""
    if node_type not in node_bodies.NATIVE_FLOW_TYPES:
        nodes = [N("s", "startNode"), N("n", node_type), N("o", "outputNode")]
        r = _render(nodes, [E("s", "n"), E("n", "o")], "n", prev_res_var="last_result")
        assert r.wrappable, f"{node_type}: nests={r.nests_downstream} terminal={r.terminal_statement} branches={r.branches}"
    else:
        r = _representative_flow_render(node_type)
        assert not r.wrappable, f"{node_type}: 대표 그래프에서 본문만 떼어 낼 수 있다고 나온다"


def _representative_flow_render(node_type):
    if node_type == "conditionNode":
        nodes = [N("s", "startNode"), N("n", "conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": "x"}]),
                 N("a", "valueNode"), N("b", "valueNode")]
        edges = [E("s", "n"), E("n", "a", "r1"), E("n", "b", "else")]
    elif node_type == "humanApprovalNode":
        nodes = [N("s", "startNode"), N("n", "humanApprovalNode"), N("a", "valueNode"), N("b", "valueNode")]
        edges = [E("s", "n"), E("n", "a", "approved"), E("n", "b", "rejected")]
    elif node_type == "loopNode":
        nodes = [N("s", "startNode"), N("n", "loopNode", maxIterations=2), N("a", "valueNode"), N("d", "valueNode")]
        edges = [E("s", "n"), E("n", "a", "loop_start"), E("n", "d", "done")]
    elif node_type == "distributorNode":
        nodes = [N("s", "startNode"), N("n", "distributorNode"), N("a", "valueNode"), N("d", "valueNode")]
        edges = [E("s", "n"), E("n", "a"), E("n", "d", "done")]
    else:  # breakNode · outputNode — 본문 자체가 return/break 를 낸다
        nodes = [N("s", "startNode"), N("n", node_type)]
        edges = [E("s", "n")]
    return _render(nodes, edges, "n", prev_res_var="last_result")


def test_흐름_노드는_왜_감쌀_수_없는지_이유가_드러난다():
    cond = _representative_flow_render("conditionNode")
    assert cond.nests_downstream and [b[1] for b in cond.branches] == ["r1", "else"]
    appr = _representative_flow_render("humanApprovalNode")
    assert appr.nests_downstream and [b[1] for b in appr.branches] == ["approved", "rejected"]
    loop = _representative_flow_render("loopNode")
    assert loop.nests_downstream and [d.target_id for d in loop.downstream] == ["a", "d"]
    dist = _representative_flow_render("distributorNode")
    assert dist.nests_downstream and [d.target_id for d in dist.downstream] == ["a", "d"]
    assert _representative_flow_render("outputNode").terminal_statement == "return"
    assert _representative_flow_render("breakNode").terminal_statement == "break"


def test_핸들이_없는_조건_노드는_본문만_보면_선형처럼_보인다():
    """함정 기록: 규칙·핸들이 없는 conditionNode 는 if False/else pass 만 내서 wrappable 로 보인다.
    그래서 인터프리터는 인스턴스가 아니라 **타입**(NATIVE_FLOW_TYPES)으로 직접 구현 대상을 고른다."""
    nodes = [N("s", "startNode"), N("n", "conditionNode"), N("o", "outputNode")]
    r = _render(nodes, [E("s", "n"), E("n", "o")], "n", prev_res_var="last_result")
    assert r.wrappable and r.downstream == []
    assert "conditionNode" in node_bodies.NATIVE_FLOW_TYPES


# ── 2. 하류 배선 기록 ──────────────────────────────────────────────────────

def test_하류_호출_기록은_생성기의_배선을_그대로_담는다():
    nodes = [N("s", "startNode"), N("v", "valueNode", value="안녕"), N("l", "llmNode"), N("m", "mergeNode"),
             N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "l"), E("l", "m"), E("m", "o")]
    s = _render(nodes, edges, "s", prev_res_var=None)
    assert [(d.target_id, d.prev_res_var, d.active_llm_id) for d in s.downstream] == [("v", None, None)]
    v = _render(nodes, edges, "v", prev_res_var=None)
    assert [(d.target_id, d.prev_res_var) for d in v.downstream] == [("l", "val_v")]
    llm = _render(nodes, edges, "l", prev_res_var="val_v")
    assert [(d.target_id, d.prev_res_var, d.active_llm_id) for d in llm.downstream] == [("m", "res_text_l", "l")]
    m = _render(nodes, edges, "m", prev_res_var=None)
    assert [(d.target_id, d.prev_res_var) for d in m.downstream] == [("o", "merge_out_m")]
    assert all(d.indent == "" for d in s.downstream + v.downstream + llm.downstream + m.downstream)


def test_등록되지_않은_타입은_compile_workflow_와_같은_Unsupported_블록을_낸다():
    nodes = [N("s", "startNode"), N("n", "noSuchNode"), N("o", "outputNode")]
    r = _render(nodes, [E("s", "n"), E("n", "o")], "n", prev_res_var="last_result")
    assert r.lines[0] == "# --- Unsupported Node (n) ---"
    assert "last_result = 'Unsupported node type: noSuchNode'" in r.lines
    assert [(d.target_id, d.prev_res_var) for d in r.downstream] == [("o", "last_result")]


# ── 3. 옛 엔진과의 등가성 — 선형 그래프를 본문 단위로 실행 ─────────────────

def _strip(logs):
    return [(s["node_id"], s["node_type"], s["status"], s["result_data"]) for s in logs]


def _run_bodies_linearly(nodes, edges, runtime_inputs):
    """프렐류드를 한 번 exec 한 네임스페이스 위에서, 루트부터 하류 기록을 따라 본문을 차례로 exec 한다 —
    인터프리터가 선형 구간에서 할 일의 최소형이다."""
    prepared = gt.prepare_graph(nodes, edges)
    idx = gt.classify_edges(prepared.edges)
    roots = gt.select_roots(prepared, idx)
    assert len(roots) == 1

    lines = []
    graph.emit_module_prelude(lines, prepared.nodes, None)
    ns = {"db": None, "models": models, "json": json, "__owner_user_id__": 0}
    exec("\n".join(lines), ns)
    ns["kwargs"] = dict(runtime_inputs)
    ns["last_result"] = "No execution occurred."

    node_id, prev_res_var, active_llm_id = roots[0]["id"], None, None
    executed = []
    while node_id is not None:
        body = node_bodies.render_node_body(node_id, node_dict=prepared.node_dict, forward_edges=idx.forward_edges,
                                            incoming_edges=idx.incoming_edges, active_llm_id=active_llm_id,
                                            prev_res_var=prev_res_var)
        assert body.wrappable, f"{node_id}: 선형 구간이 아니다"
        exec(body.source, ns)
        executed.append(node_id)
        if body.downstream:
            nxt = body.downstream[0]
            node_id, prev_res_var, active_llm_id = nxt.target_id, nxt.prev_res_var, nxt.active_llm_id
        else:
            node_id = None
    return str(ns["last_result"]), ns["__execution_logs__"], ns["__node_results__"], executed


def test_본문_단위_실행은_옛_엔진과_같은_로그_결과_값을_낸다():
    nodes = [N("s", "startNode"), N("v", "valueNode", value="원본"), N("t", "dynamicInputNode", inputLabel="라벨"),
             N("m", "mergeNode", mergeStrategy="join_newline")]
    edges = [E("s", "v"), E("v", "t"), E("t", "m")]

    legacy_result, _tokens, legacy_logs = graph.run_workflow(nodes, edges, t="둘")
    result, logs, results, executed = _run_bodies_linearly(nodes, edges, {"t": "둘"})

    assert executed == ["s", "v", "t", "m"]
    assert result == legacy_result
    assert _strip(logs) == _strip(legacy_logs)
    # __node_results__ 는 하류(merge·바인딩)가 읽는 값이다 — 옛 엔진이 로그에 남긴 결과와 같아야 한다.
    assert {k: str(v) for k, v in results.items()} == {s["node_id"]: s["result_data"] for s in legacy_logs}
    assert results["m"] == legacy_result


def test_본문_단위_실행에서도_노드_오류가_로그에_같은_모양으로_남는다():
    """jsonParserNode 가 JSON 아닌 입력을 받으면 legacy 문구 오류로 기록된다 — 오류 경로도 같아야 한다."""
    nodes = [N("s", "startNode"), N("v", "valueNode", value="이건 JSON 이 아니다"),
             N("p", "jsonParserNode", mode="parse")]
    edges = [E("s", "v"), E("v", "p")]

    legacy_result, _tokens, legacy_logs = graph.run_workflow(nodes, edges)
    result, logs, _results, _executed = _run_bodies_linearly(nodes, edges, {})

    assert result == legacy_result
    assert _strip(logs) == _strip(legacy_logs)

    def _errors(steps):  # requestId 는 오류마다 새로 뽑는 난수다 — 그것만 빼고 같아야 한다
        return [({k: v for k, v in s["error"].items() if k != "requestId"} if s["error"] else None) for s in steps]

    assert _errors(logs) == _errors(legacy_logs)
    assert (_errors(logs)[-1] or {}).get("code") == "LEGACY_NODE_ERROR"
