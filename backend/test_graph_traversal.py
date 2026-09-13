"""graph_traversal — 두 실행 엔진이 공유하는 순회 규칙 (백로그 32 ENGINE-0 3단계) 테스트.

계약: 여기 규칙은 compile_workflow 가 쓰던 것과 같다. 이 파일은 규칙을 그래프 수준에서 단정하고,
생성 소스의 등가성(바이트 동일)은 코퍼스 해시 대조(PR 본문)와 test_merge_rejoin.py 가 지킨다.
"""

from __future__ import annotations

import pytest

import graph
import graph_traversal as gt
from graph_traversal import GraphPreparationError, JoinGate


def N(id_, type_="valueNode", **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None, target_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    if target_handle is not None:
        e["targetHandle"] = target_handle
    return e


def _index(nodes, edges, **kw):
    prepared = gt.prepare_graph(nodes, edges, **kw)
    return prepared, gt.classify_edges(prepared.edges)


# ── prepare_graph ──────────────────────────────────────────────────────────

def test_memo_는_실행_대상이_아니고_빈_그래프는_같은_문구로_거부된다():
    prepared = gt.prepare_graph([N("s", "startNode"), N("memo", "memoNode"), N("o", "outputNode")],
                                [E("s", "o")])
    assert [n["id"] for n in prepared.nodes] == ["s", "o"]
    with pytest.raises(GraphPreparationError, match="Graph is empty"):
        gt.prepare_graph([], [])
    with pytest.raises(GraphPreparationError, match="Graph is empty"):
        gt.prepare_graph([N("memo", "memoNode")], [])
    # compile_workflow 가 사용자에게 돌려주는 문구와 같아야 한다 — 두 엔진이 같은 말을 한다.
    assert graph.compile_workflow([], []) == gt.ERROR_EMPTY_GRAPH


def test_scope_는_노드와_간선을_함께_잘라내고_비면_거부한다():
    nodes = [N("s", "startNode"), N("a"), N("b"), N("o", "outputNode")]
    edges = [E("s", "a"), E("a", "b"), E("b", "o")]
    prepared = gt.prepare_graph(nodes, edges, scope_node_ids=["a", "b"])
    assert [n["id"] for n in prepared.nodes] == ["a", "b"]
    assert prepared.edges == [E("a", "b")]
    with pytest.raises(GraphPreparationError, match="실행할 노드가 없습니다"):
        gt.prepare_graph(nodes, edges, scope_node_ids=["zzz"])


def test_stop_은_그_노드에서_나가는_간선만_지운다():
    nodes = [N("s", "startNode"), N("a"), N("b"), N("o", "outputNode")]
    edges = [E("s", "a"), E("a", "b"), E("b", "o")]
    prepared = gt.prepare_graph(nodes, edges, stop_node_id="a")
    assert prepared.edges == [E("s", "a"), E("b", "o")]
    assert len(prepared.nodes) == 4


def test_pinned_는_문자열_키로_정규화하고_None_은_버린다():
    prepared = gt.prepare_graph([N("s", "startNode"), N("a")], [E("s", "a")],
                                pinned_outputs={1: "하나", "a": None, "s": "시작"})
    assert prepared.pinned_outputs == {"1": "하나", "s": "시작"}


def test_보안_검증_실패는_같은_접두_문구다():
    with pytest.raises(GraphPreparationError, match=r"^Error: Security validation failed: "):
        gt.prepare_graph([N("dup"), N("dup")], [])


# ── classify_edges ─────────────────────────────────────────────────────────

def test_배선_간선은_실행_순서로_세지_않는다():
    edges = [
        E("s", "llm"), E("tool", "ma", target_handle="tools"), E("tpl", "fm", target_handle="template"),
        E("gen", "mail", target_handle="attachments"), E("body", "mail"),
    ]
    idx = gt.classify_edges(edges)
    assert idx.tool_node_ids == {"tool"}
    assert idx.forward_edges == {"s": [("llm", None)], "body": [("mail", None)]}
    assert idx.has_incoming == {"llm", "mail"}
    # incoming_edges 에는 배선 간선도 남는다 — 발송 노드가 첨부 출처를 여기서 찾는다.
    assert [i["source"] for i in idx.incoming_edges["mail"]] == ["gen", "body"]
    assert idx.incoming_edges["ma"] == [{"source": "tool", "targetHandle": "tools"}]


def test_첨부_간선만_있는_발송_노드는_첨부_간선을_제어_흐름으로_인정한다():
    idx = gt.classify_edges([E("s", "gen"), E("gen", "mail", target_handle="attachments")])
    assert idx.forward_edges["gen"] == [("mail", None)], "본문 간선이 없으면 첨부 간선이 실행 순서가 된다"
    assert "mail" in idx.has_incoming


def test_forward_edges_는_간선_순서를_지킨다():
    idx = gt.classify_edges([E("f", "b2", "h2"), E("f", "b1", "h1"), E("f", "b3")])
    assert idx.forward_edges["f"] == [("b2", "h2"), ("b1", "h1"), ("b3", None)]


# ── select_roots ───────────────────────────────────────────────────────────

def test_트리거_타입은_내장_5종에_정의_파생_트리거를_더한_것이다():
    types = gt.trigger_node_types()
    assert set(gt.BUILTIN_TRIGGER_TYPES) <= types
    assert len(types) > len(gt.BUILTIN_TRIGGER_TYPES), "node_definition 의 트리거(rss/youtube/gmail …)가 빠졌다"


def test_트리거가_있으면_다른_무입력_노드는_루트가_아니다():
    prepared, idx = _index([N("v"), N("s", "startNode"), N("o", "outputNode")], [E("s", "o")])
    assert [r["id"] for r in gt.select_roots(prepared, idx)] == ["s"]


def test_트리거가_없으면_입력_없는_비_llm_비_tool_노드가_루트다():
    nodes = [N("v"), N("p", "promptNode"), N("l", "llmNode"), N("ma", "multiAgentNode"), N("t", "llmNode"),
             N("o", "outputNode")]
    edges = [E("v", "p"), E("p", "l"), E("t", "ma", target_handle="tools"), E("ma", "o")]
    prepared, idx = _index(nodes, edges)
    # 'ma' 는 tool 간선만 받고 제어 간선은 안 들어온다 — 폴백 루트다. 't' 는 tool 이라 제외, 'l' 은 llmNode 라 제외.
    assert [r["id"] for r in gt.select_roots(prepared, idx)] == ["v", "ma"]
    # 'ma' 에 하류가 없으면 "연결된 루트만" 규칙으로 떨어진다.
    prepared2, idx2 = _index(nodes[:-1], edges[:-1])
    assert [r["id"] for r in gt.select_roots(prepared2, idx2)] == ["v"]


def test_루트가_여럿이면_하류가_있는_것만_남긴다():
    prepared, idx = _index([N("s1", "startNode"), N("s2", "startNode"), N("o", "outputNode")], [E("s1", "o")])
    assert [r["id"] for r in gt.select_roots(prepared, idx)] == ["s1"]


def test_순환만_있으면_최상위_첫_노드가_루트다():
    prepared, idx = _index([N("a"), N("b")], [E("a", "b"), E("b", "a")])
    assert [r["id"] for r in gt.select_roots(prepared, idx)] == ["a"]


def test_entry_는_그_노드_하나이고_모르는_id_는_거부한다():
    prepared, idx = _index([N("s", "startNode"), N("a"), N("o", "outputNode")], [E("s", "a"), E("a", "o")])
    assert [r["id"] for r in gt.select_roots(prepared, idx, entry_node_id="a")] == ["a"]
    with pytest.raises(GraphPreparationError, match="재개 지점 노드\\(zzz\\)"):
        gt.select_roots(prepared, idx, entry_node_id="zzz")


# ── join_expectations ──────────────────────────────────────────────────────

def test_fanout_이_다시_만나는_노드는_갈래_수만큼_기다린다():
    _, idx = _index([N("s", "startNode"), N("f"), N("b1"), N("b2"), N("m", "mergeNode")],
                    [E("s", "f"), E("f", "b1"), E("f", "b2"), E("b1", "m"), E("b2", "m")])
    assert gt.join_expectations(idx) == {"m": (2, {"b1", "b2"})}


def test_루프_되돌림_간선은_기다리지_않는다():
    # s → l → x → l : l 에 두 간선이 들어오지만 x 는 l 의 하류라 back-edge — 기다리면 영원히 못 만난다.
    _, idx = _index([N("s", "startNode"), N("l", "loopNode"), N("x")],
                    [E("s", "l"), E("l", "x", "loop_start"), E("x", "l")])
    assert gt.join_expectations(idx) == {}


def test_같은_source_가_다른_핸들로_두_번_들어오면_두_갈래다():
    _, idx = _index([N("s", "startNode"), N("c", "conditionNode"), N("m", "mergeNode")],
                    [E("s", "c"), E("c", "m", "r1"), E("c", "m", "else")])
    assert gt.join_expectations(idx) == {"m": (2, {"c"})}


# ── JoinGate ───────────────────────────────────────────────────────────────

def test_게이트는_마지막_갈래가_도착했을_때_합쳐진_visited_를_돌려준다():
    gate = JoinGate({"m": (2, {"b1", "b2"})})
    gate.mark_emitted("b1")
    assert gate.arrive("m", {"f", "b1"}) is None, "첫 도착은 기다린다"
    gate.mark_emitted("b2")
    assert gate.arrive("m", {"f", "b2"}) == {"f", "b1", "b2"}
    assert gate.pending == {}
    gate.mark_emitted("m")
    assert gate.arrive("m", {"x"}) is None, "이미 방출된 재합류는 다시 방출하지 않는다"


def test_형제_갈래에_걸친_재합류는_분기_안에_놓이지_않고_분기_뒤에서_한_번_방출된다():
    gate = JoinGate({"m": (2, {"b1", "b2"})})
    gate.begin_branch("c", "r1")
    gate.mark_emitted("b1")
    assert gate.arrive("m", {"b1"}) is None
    gate.end_branch()
    gate.begin_branch("c", "else")
    gate.mark_emitted("b2")
    assert gate.arrive("m", {"b2"}) is None, "다른 갈래가 실행되면 영영 못 만나는 자리다"
    gate.end_branch()

    emitted = []
    gate.flush_ready(lambda jid, visited: emitted.append((jid, visited)))
    assert emitted == [("m", {"b1", "b2"})]
    assert gate.pending == {}


def test_분기_안에서_완결되는_다이아몬드는_그_자리에_놓인다():
    gate = JoinGate({"m": (2, {"b1", "b2"})})
    gate.begin_branch("c", "r1")
    gate.mark_emitted("f2")
    gate.mark_emitted("b1")
    assert gate.arrive("m", {"b1"}) is None
    gate.mark_emitted("b2")
    assert gate.arrive("m", {"b2"}) == {"b1", "b2"}, "같은 갈래 안이면 지금 자리에 방출한다"
    gate.end_branch()


def test_flush_stranded_는_남은_재합류를_한_번씩_방출한다():
    gate = JoinGate({"m": (2, {"b1", "b2"}), "m2": (2, {"x", "y"})})
    gate.mark_emitted("b1")
    gate.arrive("m", {"b1"})
    gate.mark_emitted("x")
    gate.arrive("m2", {"x"})
    emitted = []
    gate.flush_stranded(lambda jid, visited: emitted.append(jid))
    assert sorted(emitted) == ["m", "m2"]
    assert gate.pending == {}


def test_path_compatible_은_접두사_관계다():
    assert JoinGate.path_compatible((), [("c", "r1")])
    assert JoinGate.path_compatible((("c", "r1"),), [])
    assert JoinGate.path_compatible((("c", "r1"),), [("c", "r1"), ("d", "x")])
    assert not JoinGate.path_compatible((("c", "r1"),), [("c", "else")])


# ── sibling_restore_source ─────────────────────────────────────────────────

def _fanout():
    nodes = [N("s", "startNode"), N("f"), N("t1", "dynamicInputNode"), N("t2", "dynamicInputNode"),
             N("c", "conditionNode"), N("b1"), N("b2"), N("one"), N("solo")]
    edges = [E("s", "f"), E("f", "t1"), E("f", "t2"), E("f", "c"), E("c", "b1", "r1"), E("c", "b2", "else"),
             E("one", "solo")]
    prepared, idx = _index(nodes, edges)
    return prepared.node_dict, idx


def test_병렬_fanout_의_갈래는_공유_변수로_받을_때만_복원한다():
    node_dict, idx = _fanout()
    assert gt.sibling_restore_source("t2", "last_result", node_dict=node_dict, index=idx) == "f"
    assert gt.sibling_restore_source("t2", "val_f", node_dict=node_dict, index=idx) is None, (
        "노드 전용 변수는 형제가 덮을 수 없다")


def test_배타_분기_갈래와_단일_하류는_복원하지_않는다():
    node_dict, idx = _fanout()
    assert gt.sibling_restore_source("b2", "last_result", node_dict=node_dict, index=idx) is None
    assert gt.sibling_restore_source("solo", "last_result", node_dict=node_dict, index=idx) is None


def test_제어_간선이_둘_이상_들어오면_복원하지_않는다():
    prepared, idx = _index([N("s", "startNode"), N("f"), N("g"), N("m", "mergeNode")],
                           [E("s", "f"), E("s", "g"), E("f", "m"), E("g", "m")])
    assert gt.sibling_restore_source("m", "last_result", node_dict=prepared.node_dict, index=idx) is None


# ── compile_workflow 위에서 ────────────────────────────────────────────────

def test_제어_간선으로_도달한_tool_노드도_컴파일된다():
    """예전에는 generate_block 의 죽은 판정 블록이 node 를 정의 전에 읽어 UnboundLocalError 로
    컴파일 전체가 죽었다(2026-09-06 확인) — tool 노드가 보통 간선으로도 연결된 그래프."""
    nodes = [N("s", "startNode"), N("e", "llmNode", systemPrompt="expert"),
             N("ma", "multiAgentNode", mode="supervisor"), N("o", "outputNode")]
    edges = [E("s", "e"), E("e", "ma", target_handle="tools"), E("s", "ma"), E("ma", "o")]
    src = graph.compile_workflow(nodes, edges)
    assert not src.startswith("Error")
    assert "# --- Multi-Agent Node (ma) ---" in src
