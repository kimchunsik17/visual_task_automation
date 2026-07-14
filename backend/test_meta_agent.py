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
from meta_agent import FlowGraph, FlowNode, FlowEdge, validate_flow, auto_layout


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
