"""generation_plan.py — GenerationPlan과 adaptive candidate 실험 (우선 백로그 10번, 로드맵 §4.4).

모든 요청에 후보를 병렬 생성하지 않는다 — 간단한 요청은 1개, 조건/반복/다중 연동/위험
요청만 2개를 만들어 결정론적 기준으로 고른다(adaptive fan-out). 이 모듈은 그 결정을
명시적인 계획(GenerationPlan)으로 만들고, 후보 선택을 LLM judge 없이 §4.4의 품질 선택
기준 순서로 수행한다:

  1. schema/보안 위반은 즉시 탈락
  2. structural·task coverage 점수
  3. dry-run 성공
  4. graph 복잡도 penalty
  (동점 의미 평가/judge 는 이 실험 범위 밖 — 결정론 기준으로 동점이면 첫 후보 유지)

실험 게이트(§4.4): 기존 평가 세트에서 단일 candidate 기준보다 채택률 또는 dry-run 통과율이
유의미하게 개선되고 비용 상한을 지킬 때만 기본값으로 전환한다. 그래서 adaptive 경로는
`GENERATION_ADAPTIVE_CANDIDATES=1` 일 때만 켜지고(기본 꺼짐), 계획과 후보 점수는 항상
generation trace 에 기록된다 — 전환 판단의 데이터가 된다. 비교 실행: generation_plan_eval.py.
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

GENERATION_PLAN_SCHEMA_VERSION = "generation-plan-v1"

# 결제/삭제/외부 게시 — 로드맵 adaptive 정책 표의 고위험 행. 위험 요청은 후보 2개와
# 정책 검사를 받는다(잘못 만들어진 그래프가 실행되면 되돌릴 수 없는 부류).
_RISK_PATTERN = re.compile(r"결제|환불|삭제|지워|게시|공개로|업로드|발행|publish|delete|payment|refund")
# 조건/반복/분산 — 구조가 갈라지는 요청은 첫 시도가 어긋나기 쉬워 후보 2개의 가치가 있다.
_COMPLEX_PATTERN = re.compile(r"조건|분기|이면|아니면|반복|각각|목록|나눠|합쳐|승인")

# 요청 표현 → 반드시 있어야 하는 노드 타입 (게이트 1차 비교의 악화 사례 ①에서 추가:
# 정밀 후보가 loopNode 없이 반복 요청을 구현했는데 TaskSpec 기반 coverage가 감점하지 못했다).
# 오탐이 거의 없는 고정밀 신호만 담는다 — 여기 걸리면 그 노드가 없는 후보는 의도 위반이다.
_STRUCTURE_SIGNALS = [
    (re.compile(r"반복(해|하여|해서|한)|번 반복"), "loopNode"),
    (re.compile(r"각각|하나씩|목록의 각|리스트의 각"), "distributorNode"),
    (re.compile(r"승인(하면|을 거쳐|을 받아|이 필요)"), "humanApprovalNode"),
    (re.compile(r"매일|매주|매시간|분마다|시간마다|정기적|스케줄|cron"), "scheduleNode"),
    (re.compile(r"웹훅|webhook"), "webhookNode"),
]


def structure_gaps(user_request: str, node_types: set) -> List[str]:
    # 요청이 구조적으로 요구하는데 그래프에 없는 노드 타입 목록.
    return [
        node_type for pattern, node_type in _STRUCTURE_SIGNALS
        if pattern.search(user_request or "") and node_type not in node_types
    ]


def adaptive_candidates_enabled() -> bool:
    return (os.getenv("GENERATION_ADAPTIVE_CANDIDATES") or "").strip().lower() in {"1", "true", "yes", "on"}


def max_candidates() -> int:
    try:
        return max(1, min(int(os.getenv("GENERATION_MAX_CANDIDATES", "2")), 3))
    except ValueError:
        return 2


@dataclass
class GenerationPlan:
    complexity: str                      # simple | complex
    risk_level: str                      # low | high
    reasons: List[str]
    required_integrations: List[str]
    candidate_count: int
    provider_route: str
    token_budget: int
    latency_budget_ms: int
    repair_budget: int
    evaluation_policy: str               # structural | dry-run | policy-check
    adaptive: bool                       # adaptive 경로가 실제로 켜져 있는지(env)
    # 실행 후 채워지는 결과 — 후보별 점수와 선택
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    chosen_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": GENERATION_PLAN_SCHEMA_VERSION,
            "complexity": self.complexity,
            "risk_level": self.risk_level,
            "reasons": self.reasons,
            "required_integrations": self.required_integrations,
            "candidate_count": self.candidate_count,
            "provider_route": self.provider_route,
            "token_budget": self.token_budget,
            "latency_budget_ms": self.latency_budget_ms,
            "repair_budget": self.repair_budget,
            "evaluation_policy": self.evaluation_policy,
            "adaptive": self.adaptive,
            "candidates": self.candidates,
            "chosen_index": self.chosen_index,
        }


def build_generation_plan(
    user_request: str,
    complexity_level: str = "low",
    *,
    task_spec=None,
    has_existing_graph: bool = False,
) -> GenerationPlan:
    """요청·TaskSpec에서 결정론적으로 계획을 만든다 — LLM 호출이 없어 비용이 0이다."""
    text = user_request or ""
    reasons: List[str] = []
    integrations = list(getattr(task_spec, "integrations", None) or [])

    risk_level = "low"
    spec_text = " ".join([
        getattr(task_spec, "goal", "") or "",
        *(getattr(task_spec, "actions", None) or []),
    ])
    if _RISK_PATTERN.search(text) or _RISK_PATTERN.search(spec_text):
        risk_level = "high"
        reasons.append("결제/삭제/외부 게시 신호 — 후보 2개와 정책 검사")

    complexity = "simple"
    if _COMPLEX_PATTERN.search(text) or (getattr(task_spec, "conditions", None) or []):
        complexity = "complex"
        reasons.append("조건/반복/분기 신호")
    if len(integrations) >= 2:
        complexity = "complex"
        reasons.append(f"연동 {len(integrations)}개")

    if has_existing_graph:
        # 기존 그래프 수정 — 후보를 여럿 만들면 사용자가 그린 부분까지 갈라진다.
        candidate_count = 1
        evaluation_policy = "structural"
        reasons.append("기존 그래프 수정 — 단일 후보")
    elif risk_level == "high":
        candidate_count = 2
        evaluation_policy = "policy-check"
    elif complexity == "complex":
        candidate_count = 2
        evaluation_policy = "dry-run"
    else:
        candidate_count = 1
        evaluation_policy = "structural"

    candidate_count = min(candidate_count, max_candidates())
    routing_mode = (os.getenv("LLM_ROUTING_MODE") or "provider").strip().lower()
    if routing_mode in {"local", "hybrid"}:
        # 로컬 단일 모델 서버는 병렬 후보가 VRAM/KV cache 경쟁으로 오히려 느려진다(§4.4).
        candidate_count = 1
        reasons.append(f"로컬 라우팅({routing_mode}) — 병렬 후보 비활성")

    return GenerationPlan(
        complexity=complexity,
        risk_level=risk_level,
        reasons=reasons,
        required_integrations=integrations,
        candidate_count=candidate_count,
        provider_route=routing_mode,
        token_budget=12_000 if candidate_count > 1 else 6_000,
        latency_budget_ms=75_000,
        repair_budget=1,
        evaluation_policy=evaluation_policy,
        adaptive=adaptive_candidates_enabled(),
    )


# ── 후보 점수화(결정론) ─────────────────────────────────────────────────
def score_candidate(graph, task_spec=None, user_request: str = "") -> Dict[str, Any]:
    """§4.4 품질 선택 기준의 결정론 부분. graph 는 meta_agent.FlowGraph 다.

    반환 dict 는 trace 에 그대로 실리므로 노드 수·오류 수 같은 수치만 담는다(내용 없음).
    """
    from dry_run import dry_run_workflow
    from meta_agent import validate_flow
    from llm.task_spec import task_coverage_issues

    structural_ok, structural_errors = validate_flow(graph, require_complete=True)

    coverage_issue_count = 0
    if task_spec is not None:
        try:
            coverage_issue_count = len(task_coverage_issues(task_spec, graph))
        except Exception:
            coverage_issue_count = 0

    dumped = graph.model_dump()
    dry = dry_run_workflow(dumped)
    node_count = len(dumped.get("nodes") or [])
    graph_types = {str(node.get("type") or "") for node in dumped.get("nodes") or []}
    gaps = structure_gaps(user_request, graph_types)

    # schema 는 FlowGraph 파싱 시점에 이미 강제됐고, 보안 위반은 compile 단계에서
    # validate_compiled_workflow 가 dry-run 의 컴파일 이슈로 드러난다.
    eliminated = any("Security" in issue or "보안" in issue for issue in dry.issues)
    return {
        "eliminated": eliminated,
        "structural_passed": structural_ok,
        "structural_error_count": len(structural_errors),
        "coverage_issue_count": coverage_issue_count,
        "structure_gaps": gaps,
        "dry_run_passed": bool(dry.success),
        "node_count": node_count,
    }


def _rank_key(score: Dict[str, Any]) -> Tuple:
    """클수록 좋은 정렬 키 — §4.4 기준 순서 그대로. 동점이면 후보 순서(첫 후보)가 이긴다."""
    return (
        not score["eliminated"],
        score["structural_passed"],
        -score["structural_error_count"],
        # 의도 커버리지 계층: TaskSpec coverage + 구조 기대 신호(반복→loopNode 등).
        -score["coverage_issue_count"],
        -len(score.get("structure_gaps") or []),
        score["dry_run_passed"],
        -score["node_count"],  # 같은 품질이면 단순한 그래프
    )


def rank_candidates(
    graphs: List[Any],
    task_spec=None,
    labels: Optional[List[str]] = None,
    user_request: str = "",
) -> Tuple[int, List[Dict[str, Any]]]:
    """후보들을 점수화해 (최선 인덱스, 점수 목록)을 돌려준다. 전부 탈락이어도 최선을 고른다
    — 호출부의 기존 repair 경로가 이어받는다."""
    scores = []
    for index, graph in enumerate(graphs):
        score = score_candidate(graph, task_spec, user_request=user_request)
        score["label"] = (labels or [])[index] if labels and index < len(labels) else f"candidate_{index}"
        scores.append(score)
    best = max(range(len(scores)), key=lambda index: _rank_key(scores[index]))
    return best, scores


# ── 턴 단위 수집기 (node_knowledge 와 같은 패턴) ────────────────────────
_active_plan: ContextVar[Optional[GenerationPlan]] = ContextVar("generation_plan", default=None)


def begin_plan(user_request: str, complexity_level: str, *, task_spec=None, has_existing_graph: bool = False) -> GenerationPlan:
    plan = build_generation_plan(
        user_request, complexity_level, task_spec=task_spec, has_existing_graph=has_existing_graph,
    )
    plan._task_spec = task_spec  # trace 직렬화에는 안 들어간다(to_dict 참고)
    _active_plan.set(plan)
    return plan


def current_plan() -> Optional[GenerationPlan]:
    return _active_plan.get()


def record_candidates(plan: GenerationPlan, scores: List[Dict[str, Any]], chosen_index: int) -> None:
    plan.candidates = scores
    plan.chosen_index = chosen_index


def collect_plan() -> Optional[Dict[str, Any]]:
    plan = _active_plan.get()
    _active_plan.set(None)
    return plan.to_dict() if plan is not None else None
