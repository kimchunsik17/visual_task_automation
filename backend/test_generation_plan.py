"""GenerationPlan과 adaptive candidate (우선 백로그 10번, §4.4) 테스트."""

import pytest

import generation_plan
from generation_plan import (
    begin_plan,
    build_generation_plan,
    collect_plan,
    current_plan,
    rank_candidates,
    record_candidates,
)
from meta_agent import FlowGraph


def graph_of(*types, edges=(), data_by_id=None):
    nodes = [
        {"id": f"n{i}", "type": t, "position": None, "data": (data_by_id or {}).get(f"n{i}", {})}
        for i, t in enumerate(types, start=1)
    ]
    return FlowGraph(title="t", description="d", nodes=nodes,
                     edges=[{"id": f"e{i}", "source": s, "target": t2} for i, (s, t2) in enumerate(edges)])


# ── adaptive fan-out 정책 표 (§4.4) ─────────────────────────────────────
def test_단순_저위험_요청은_후보_1개다():
    plan = build_generation_plan("입력받은 글을 요약해서 보여줘")
    assert (plan.complexity, plan.risk_level, plan.candidate_count) == ("simple", "low", 1)
    assert plan.evaluation_policy == "structural"


def test_조건_분기_요청은_후보_2개와_dry_run이다():
    plan = build_generation_plan("리뷰 점수가 3점 미만이면 경고, 아니면 감사 메일을 보내줘")
    assert plan.complexity == "complex"
    assert plan.candidate_count == 2
    assert plan.evaluation_policy == "dry-run"


def test_결제_삭제_게시는_고위험으로_정책_검사를_받는다():
    plan = build_generation_plan("결제 링크를 만들어 발송해줘")
    assert plan.risk_level == "high"
    assert (plan.candidate_count, plan.evaluation_policy) == (2, "policy-check")


def test_기존_그래프_수정은_후보_1개다():
    plan = build_generation_plan("조건 분기를 추가해줘", has_existing_graph=True)
    assert plan.candidate_count == 1


def test_로컬_라우팅에서는_병렬_후보를_끈다(monkeypatch):
    monkeypatch.setenv("LLM_ROUTING_MODE", "local")
    plan = build_generation_plan("리뷰 점수가 3점 미만이면 경고, 아니면 메일")
    assert plan.candidate_count == 1


def test_adaptive는_기본으로_꺼져_있다(monkeypatch):
    monkeypatch.delenv("GENERATION_ADAPTIVE_CANDIDATES", raising=False)
    assert generation_plan.adaptive_candidates_enabled() is False
    monkeypatch.setenv("GENERATION_ADAPTIVE_CANDIDATES", "1")
    assert generation_plan.adaptive_candidates_enabled() is True


# ── 결정론적 후보 랭킹 (§4.4 품질 선택 기준) ────────────────────────────
def test_구조_통과_후보가_실패_후보를_이긴다():
    broken = graph_of("startNode", "llmNode")  # llmNode 필수 필드 없음 + 연결 없음 + 종료 없음
    healthy = graph_of(
        "startNode", "promptNode", "llmNode", "outputNode",
        edges=[("n1", "n2"), ("n2", "n3"), ("n3", "n4")],
        data_by_id={
            "n2": {"userPrompt": "요약해줘"},
            "n3": {"model": "gpt-4o-mini", "systemPrompt": "s"},
        },
    )
    best, scores = rank_candidates([broken, healthy], labels=["fast", "precise"])
    assert best == 1
    assert scores[1]["structural_passed"] is True
    assert scores[0]["structural_passed"] is False


def test_같은_품질이면_단순한_그래프를_고른다():
    lean = graph_of(
        "startNode", "promptNode", "llmNode", "outputNode",
        edges=[("n1", "n2"), ("n2", "n3"), ("n3", "n4")],
        data_by_id={"n2": {"userPrompt": "p"}, "n3": {"model": "gpt-4o-mini", "systemPrompt": "s"}},
    )
    bloated = graph_of(
        "startNode", "promptNode", "llmNode", "llmNode", "mergeNode", "outputNode",
        edges=[("n1", "n2"), ("n2", "n3"), ("n2", "n4"), ("n3", "n5"), ("n4", "n5"), ("n5", "n6")],
        data_by_id={
            "n2": {"userPrompt": "p"},
            "n3": {"model": "gpt-4o-mini", "systemPrompt": "s"},
            "n4": {"model": "gpt-4o-mini", "systemPrompt": "s"},
        },
    )
    best, scores = rank_candidates([bloated, lean])
    assert best == 1
    assert scores[1]["node_count"] < scores[0]["node_count"]


def test_구조_기대_신호가_의도_위반_후보를_감점한다():
    """1차 게이트 악화 사례 ①의 회귀 테스트 — 반복 요청인데 loopNode 없는 후보가
    dry-run 통과나 단순함을 이유로 이기면 안 된다(커버리지 계층 > dry-run/복잡도 계층)."""
    from generation_plan import _rank_key, structure_gaps

    assert structure_gaps("문장을 최대 3번 반복해서 다듬어줘", {"startNode", "llmNode"}) == ["loopNode"]
    assert structure_gaps("문장을 최대 3번 반복해서 다듬어줘", {"loopNode", "llmNode"}) == []
    assert structure_gaps("상품 목록의 각 항목을 처리해줘", {"llmNode"}) == ["distributorNode"]
    assert structure_gaps("요약해서 보여줘", {"llmNode"}) == []

    base = dict(eliminated=False, structural_passed=True, structural_error_count=0,
                coverage_issue_count=0, dry_run_passed=True, node_count=4)
    violating = {**base, "structure_gaps": ["loopNode"]}
    conforming = {**base, "structure_gaps": [], "node_count": 7, "dry_run_passed": False}
    assert _rank_key(conforming) > _rank_key(violating)


def test_전부_실패해도_최선을_고른다():
    worse = graph_of("startNode", "llmNode", "llmNode")
    bad = graph_of("startNode", "llmNode")
    best, _ = rank_candidates([worse, bad])
    assert best in (0, 1)  # 예외 없이 결정된다 — repair 경로가 이어받는다


# ── 수집기와 트레이스 ───────────────────────────────────────────────────
def test_계획은_수집기로_기록되고_회수_후_비워진다():
    plan = begin_plan("결제 후 알림", "low")
    assert current_plan() is plan
    record_candidates(plan, [{"label": "fast", "eliminated": False}], 0)
    record = collect_plan()
    assert record["risk_level"] == "high"
    assert record["chosen_index"] == 0
    assert collect_plan() is None
    assert current_plan() is None


def test_생성_트레이스에_계획이_실린다():
    from generation_trace import build_generation_trace

    trace = build_generation_trace(
        trace_id="t1", thread_id="th", message="m", complexity_level="low",
        graph_data={"nodes": [], "edges": []}, outcome="chat", status="completed", latency_ms=1,
        generation_plan={"schema_version": "generation-plan-v1", "candidate_count": 2},
    )
    assert trace["generation_plan"]["candidate_count"] == 2
