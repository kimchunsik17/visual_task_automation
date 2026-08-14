"""
test_meta_agent.py — Validator(validate_flow) 단위 테스트

실행: pytest test_meta_agent.py -v

워크플로우 문서(챗봇_agent_빌드_workflow.md) Phase 1 요구 케이스:
  정상 / 순환 / 고아 엣지 / start·output 누락
+ 계약(계약_Flow_JSON.md §3) 반영 검증:
  노드별 data 필수 필드, llmNode model enum, conditionNode rules/sourceHandle 일치,
  httpRequestNode/jsonParserNode/delayNode(2026-07-14 확장분) 필수 필드
+ auto_layout: 기존 position 보존(2026-07-14 프론트 통합 리뷰에서 발견)
"""

import pytest
import time
import meta_agent
from meta_agent import FlowGraph, FlowNode, FlowEdge, validate_flow, auto_layout, repair_disconnected_flow, make_tools


def N(id, type, data=None):
    return FlowNode(id=id, type=type, data=data or {})


def E(id, source, target, sourceHandle=None):
    return FlowEdge(id=id, source=source, target=target, sourceHandle=sourceHandle)


# ── 기본 4케이스 (workflow.md Phase 1 명시) ──────────────────────────────

def test_정상_flow_통과():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "promptNode", {"userPrompt": "요약해줘"}),
            N("n3", "llmNode", {"model": "gpt-4o-mini", "systemPrompt": "너는 요약가다"}),
            N("n4", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3"), E("e3", "n3", "n4")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_순환이면_실패():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "promptNode", {"userPrompt": "x"}),
            N("n3", "llmNode", {"model": "gpt-4o-mini", "systemPrompt": "x"}),
            N("n4", "outputNode"),
        ],
        edges=[
            E("e1", "n1", "n2"), E("e2", "n2", "n3"),
            E("e3", "n3", "n2"),  # n3 -> n2 역방향 = 순환
            E("e4", "n3", "n4"),
        ],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("순환" in e for e in errs)


def test_고아_엣지면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "outputNode")],
        edges=[E("e1", "n1", "nX")],  # nX 존재하지 않음
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("존재하지 않는 노드" in e for e in errs)


def test_repair가_도달할_수_없는_잔여_노드만_제거한다():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "outputNode"),
            N("n3", "mergeNode", {"mergeStrategy": "join_newline"}),
        ],
        edges=[E("e1", "n1", "n2")],
    )

    repaired, notes = repair_disconnected_flow(g)
    ok, errors = validate_flow(repaired)

    assert ok is True
    assert errors == []
    assert [node.id for node in repaired.nodes] == ["n1", "n2"]
    assert any("n3" in note for note in notes)


def test_repair가_multi_agent_tool_배선을_보존한다():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "multiAgentNode", {"mode": "supervisor"}),
            N("n3", "llmNode", {"model": "gpt-4o-mini", "systemPrompt": "요약"}),
            N("n4", "outputNode"),
        ],
        edges=[
            E("e1", "n1", "n2"),
            FlowEdge(id="e2", source="n3", target="n2", targetHandle="tools"),
            E("e3", "n2", "n4"),
        ],
    )

    repaired, _ = repair_disconnected_flow(g)

    assert {node.id for node in repaired.nodes} == {"n1", "n2", "n3", "n4"}
    assert {edge.id for edge in repaired.edges} == {"e1", "e2", "e3"}


def test_tools가_마지막_완전_유효_그래프를_보존한다():
    initial = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "outputNode")],
        edges=[E("e1", "n1", "n2")],
    )
    tools, get_current, _, get_last_valid = make_tools(initial)

    tools[1].invoke({"node_type": "startNode", "data": {}})

    current_ok, _ = validate_flow(get_current())
    last_valid_ok, _ = validate_flow(get_last_valid())
    assert current_ok is False
    assert last_valid_ok is True
    assert len(get_last_valid().nodes) == 2


@pytest.mark.asyncio
async def test_generate_flow_tool이_전체_시간_제한을_지킨다(monkeypatch):
    def slow_generate(*args, **kwargs):
        time.sleep(0.1)
        return FlowGraph(nodes=[N("n1", "startNode"), N("n2", "outputNode")], edges=[E("e1", "n1", "n2")])

    monkeypatch.setattr(meta_agent, "generate_flow", slow_generate)
    monkeypatch.setenv("LLM_GENERATION_TIMEOUT_SECONDS", "0.01")
    tools, _, _, _ = make_tools(FlowGraph(nodes=[], edges=[]))

    result = await tools[5].ainvoke({"request": "요약 봇 만들어줘"})

    assert "시간 제한" in result


def test_start_누락이면_실패():
    g = FlowGraph(nodes=[N("n1", "promptNode", {"userPrompt": "x"}), N("n2", "outputNode")], edges=[E("e1", "n1", "n2")])
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("startNode" in e for e in errs)


def test_output_누락이면_실패():
    g = FlowGraph(nodes=[N("n1", "startNode"), N("n2", "promptNode", {"userPrompt": "x"})], edges=[E("e1", "n1", "n2")])
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("outputNode" in e for e in errs)


# ── 계약 §3 반영 케이스 (data 필수 필드 / conditionNode) ──────────────────

def test_중복_노드_id면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n1", "outputNode")],
        edges=[],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("중복된 노드 id" in e for e in errs)


def test_promptNode_userPrompt_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "promptNode", {}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("userPrompt" in e for e in errs)


def test_llmNode_model이_허용목록_밖이면_실패():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "llmNode", {"model": "not-a-real-model", "systemPrompt": "x"}),
            N("n3", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("model" in e for e in errs)


def test_tokenizerNode_method_잘못되면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "tokenizerNode", {"method": "wrong"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("tokenizerNode" in e for e in errs)


def test_conditionNode_rules_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "conditionNode", {}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3", sourceHandle="else")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("rules가 없다" in e for e in errs)


def test_conditionNode_sourceHandle이_rule_id도_else도_아니면_실패():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "conditionNode", {"rules": [{"id": "r1", "operator": "==", "value": "yes"}]}),
            N("n3", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3", sourceHandle="rXXX")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("sourceHandle" in e for e in errs)


def test_conditionNode_정상_분기는_통과():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "conditionNode", {"rules": [{"id": "r1", "operator": "==", "value": "yes"}]}),
            N("n3", "outputNode"),
            N("n4", "outputNode"),
        ],
        edges=[
            E("e1", "n1", "n2"),
            E("e2", "n2", "n3", sourceHandle="r1"),
            E("e3", "n2", "n4", sourceHandle="else"),
        ],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


# ── 신규 노드 3종 (httpRequestNode·jsonParserNode·delayNode, 2026-07-14 확장) ──

def test_httpRequestNode_정상_통과():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/weather"}),
            N("n3", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_httpRequestNode_url_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "httpRequestNode", {"method": "GET"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("url" in e for e in errs)


def test_httpRequestNode_method_허용목록_밖이면_실패():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "httpRequestNode", {"method": "PATCH", "url": "https://x.com"}),
            N("n3", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("method" in e for e in errs)


def test_jsonParserNode_extract_모드인데_extractKey_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "jsonParserNode", {"mode": "extract"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("extractKey" in e for e in errs)


def test_jsonParserNode_parse_모드는_extractKey_없어도_통과():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "jsonParserNode", {"mode": "parse"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_jsonParserNode_mode_잘못되면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "jsonParserNode", {"mode": "transform"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("mode" in e for e in errs)


def test_delayNode_seconds_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "delayNode", {}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("seconds" in e for e in errs)


def test_delayNode_seconds_음수면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "delayNode", {"seconds": -3}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("0 이상" in e for e in errs)


def test_delayNode_seconds_숫자아니면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "delayNode", {"seconds": "abc"}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("숫자" in e for e in errs)


def test_delayNode_정상_통과():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "delayNode", {"seconds": 5}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_신규노드_3종_섞인_전체flow_통과():
    """FEWSHOT 예시2(날씨 API) 패턴 그대로: start -> http -> jsonParser -> prompt -> llm -> output"""
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/weather"}),
            N("n3", "jsonParserNode", {"mode": "extract", "extractKey": "summary"}),
            N("n4", "promptNode", {"userPrompt": "다음 날씨 정보를 한국어로 요약해줘"}),
            N("n5", "llmNode", {"model": "gpt-4o-mini", "systemPrompt": "너는 날씨 캐스터다"}),
            N("n6", "outputNode"),
        ],
        edges=[
            E("e1", "n1", "n2"), E("e2", "n2", "n3"), E("e3", "n3", "n4"),
            E("e4", "n4", "n5"), E("e5", "n5", "n6"),
        ],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


# ── dynamicInputNode / webCrawlerNode (2026-07-14 추가) ──────────────────

def test_dynamicInputNode_webCrawlerNode_섞인_전체flow_통과():
    """FEWSHOT 예시3+4 패턴: start -> dynamicInput(URL) -> webCrawler(url 비움, 직전 출력 사용) -> prompt -> llm -> output"""
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "dynamicInputNode", {"inputLabel": "크롤링할 URL", "testValue": "https://example.com"}),
            N("n3", "webCrawlerNode", {"url": ""}),
            N("n4", "promptNode", {"userPrompt": "다음 웹페이지 내용을 요약해줘"}),
            N("n5", "llmNode", {"model": "gpt-4o-mini", "systemPrompt": "너는 요약 전문가다"}),
            N("n6", "outputNode"),
        ],
        edges=[
            E("e1", "n1", "n2"), E("e2", "n2", "n3"), E("e3", "n3", "n4"),
            E("e4", "n4", "n5"), E("e5", "n5", "n6"),
        ],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_webCrawlerNode_url_없고_incoming도_없으면_실패():
    g = FlowGraph(
        nodes=[N("n1", "webCrawlerNode", {"url": ""}), N("n2", "outputNode")],
        edges=[E("e1", "n1", "n2")],
    )
    ok, errs = validate_flow(g, require_complete=False)
    assert ok is False
    assert any("url이 없고 연결된 이전 노드도 없다" in e for e in errs)


def test_webCrawlerNode_url_없고_직전이_startNode뿐이면_실패():
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "webCrawlerNode", {"url": ""}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is False
    assert any("직전 노드가 startNode뿐이라" in e for e in errs)


def test_webCrawlerNode_url_채워져있으면_incoming_없어도_통과():
    g = FlowGraph(
        nodes=[
            N("n1", "startNode"),
            N("n2", "webCrawlerNode", {"url": "https://example.com"}),
            N("n3", "outputNode"),
        ],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


def test_dynamicInputNode_data_비어있어도_통과():
    """inputLabel/testValue 둘 다 선택값이므로 data가 비어있어도 유효하다."""
    g = FlowGraph(
        nodes=[N("n1", "startNode"), N("n2", "dynamicInputNode", {}), N("n3", "outputNode")],
        edges=[E("e1", "n1", "n2"), E("e2", "n2", "n3")],
    )
    ok, errs = validate_flow(g)
    assert ok is True
    assert errs == []


# ── auto_layout: 기존 position 보존 (2026-07-14 프론트 통합 리뷰에서 발견) ──

def test_auto_layout_기존_position_보존하고_새노드만_배치():
    g = FlowGraph(
        nodes=[
            FlowNode(id="n1", type="startNode", data={}, position={"x": 500, "y": 300}),
            FlowNode(id="n2", type="outputNode", data={}, position={"x": 900, "y": 300}),
            FlowNode(id="n3", type="promptNode", data={"userPrompt": "x"}),  # 새 노드, position 없음
        ],
        edges=[E("e1", "n1", "n3"), E("e2", "n3", "n2")],
    )
    result = auto_layout(g)
    pos = {n["id"]: n["position"] for n in result["nodes"]}
    assert pos["n1"] == {"x": 500, "y": 300}
    assert pos["n2"] == {"x": 900, "y": 300}
    assert pos["n3"]["x"] > 900  # 기존 노드들과 안 겹치게 오른쪽에 새로 배치


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
