from __future__ import annotations

import ast
import time
from collections import deque
from typing import Any, Optional

from pydantic import BaseModel, Field

from graph import compile_workflow
from meta_agent import FlowGraph, validate_flow
from node_registry import node_registry


DRY_RUN_SCHEMA_VERSION = "dry-run-v1"

# These nodes may cross the process boundary or persist data. A dry-run records the
# intended operation but never imports or invokes the generated runtime handler.
SIDE_EFFECT_NODE_TYPES = {
    "databaseNode",
    "discordNode",
    "emailNode",
    "fileModifierNode",
    "googleCalendarNode",
    "googleSheetsNode",
    "httpRequestNode",
    "kakaoNode",
    "notionNode",
    "paymentLinkNode",
    "posterGeneratorNode",
    "slackNode",
    "telegramNode",
    "tossNode",
    "webCrawlerNode",
}
TRIGGER_NODE_TYPES = {
    "discordTriggerNode", "scheduleNode", "startNode", "telegramTriggerNode", "webhookNode",
}

# NodeDefinition 을 가진 노드는 위 하드코딩 목록에 손으로 넣지 않고 정의에서 파생시킨다
# (ADR-0008). 목록에 넣는 걸 잊으면 새 연동 노드가 dry-run 을 조용히 통과해 실제로 외부에
# 쓰기를 해버린다 — 그 실수를 구조적으로 막는다.
import node_definition as _node_definition  # noqa: E402

SIDE_EFFECT_NODE_TYPES |= _node_definition.types_with_external_writes()
TRIGGER_NODE_TYPES |= _node_definition.trigger_types()
ARBITRARY_CODE_NODE_TYPES = {"pythonNode"}
HIGH_RISK_NODE_TYPES = {
    "databaseNode", "paymentLinkNode", "tossNode", "fileModifierNode", "posterGeneratorNode",
}
# 'attachments' 는 발송 노드의 첨부 포트다(ADR-0018) — 제어 흐름이 아니라 파일 배선이라
# graph.compile_workflow 와 같은 기준으로 도달 가능성 계산에서 뺀다.
IGNORED_EDGE_HANDLES = {"template", "tools", "attachments"}


class DryRunStep(BaseModel):
    node_id: str
    node_type: str
    status: str
    detail: str


class DryRunResult(BaseModel):
    schema_version: str = DRY_RUN_SCHEMA_VERSION
    success: bool
    structural_passed: bool
    compile_passed: bool
    reachable_node_count: int = 0
    blocked_side_effect_count: int = 0
    high_risk_node_count: int = 0
    steps: list[DryRunStep] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    latency_ms: int = 0


def _reachable_node_ids(nodes: list[dict], edges: list[dict]) -> list[str]:
    node_ids = {str(node.get("id")) for node in nodes}
    incoming = {
        str(edge.get("target")) for edge in edges
        if edge.get("targetHandle") not in IGNORED_EDGE_HANDLES
    }
    roots = [
        str(node.get("id")) for node in nodes
        if node.get("type") in TRIGGER_NODE_TYPES
    ]
    if not roots:
        roots = [str(node.get("id")) for node in nodes if str(node.get("id")) not in incoming]

    forward: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("targetHandle") in IGNORED_EDGE_HANDLES:
            continue
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in node_ids and target in node_ids:
            forward.setdefault(source, []).append(target)

    ordered: list[str] = []
    seen: set[str] = set()
    queue = deque(roots)
    while queue:
        node_id = queue.popleft()
        if node_id in seen or node_id not in node_ids:
            continue
        seen.add(node_id)
        ordered.append(node_id)
        queue.extend(forward.get(node_id, []))
    return ordered


def dry_run_workflow(graph_data: Optional[dict]) -> DryRunResult:
    """Validate and simulate a graph without executing generated workflow code."""
    started = time.perf_counter()
    graph_data = graph_data or {}
    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []
    issues: list[str] = []

    try:
        graph = FlowGraph.model_validate({
            "title": graph_data.get("title", ""),
            "description": graph_data.get("description", ""),
            "nodes": nodes,
            "edges": edges,
        })
        structural_passed, validation_errors = validate_flow(graph)
        issues.extend(validation_errors)
    except Exception as exc:
        structural_passed = False
        issues.append(f"FlowGraph schema 오류: {exc}")

    compile_passed = False
    try:
        source = compile_workflow(nodes, edges)
        if source.startswith("Error"):
            raise ValueError(source)
        ast.parse(source, filename="<dry-run-workflow>")
        compile(source, "<dry-run-workflow>", "exec")
        compile_passed = True
    except Exception as exc:
        issues.append(f"생성 코드 컴파일 오류: {exc}")

    nodes_by_id = {str(node.get("id")): node for node in nodes}
    reachable_ids = _reachable_node_ids(nodes, edges)
    steps: list[DryRunStep] = []
    blocked_count = 0
    high_risk_count = 0
    for node_id in reachable_ids:
        node = nodes_by_id[node_id]
        node_type = str(node.get("type") or "unknown")
        if not node_registry.has_node(node_type):
            steps.append(DryRunStep(
                node_id=node_id, node_type=node_type, status="error",
                detail="등록되지 않은 노드 타입",
            ))
            issues.append(f"{node_id}({node_type})은 실행기에 등록되지 않았다")
        elif node_type in SIDE_EFFECT_NODE_TYPES:
            blocked_count += 1
            high_risk_count += int(node_type in HIGH_RISK_NODE_TYPES)
            steps.append(DryRunStep(
                node_id=node_id, node_type=node_type, status="blocked",
                detail="외부 호출 또는 영구 변경을 차단하고 계약만 검증함",
            ))
        elif node_type in ARBITRARY_CODE_NODE_TYPES:
            blocked_count += 1
            high_risk_count += 1
            steps.append(DryRunStep(
                node_id=node_id, node_type=node_type, status="blocked",
                detail="사용자 Python 코드를 실행하지 않고 생성 코드 문법만 검증함",
            ))
        else:
            steps.append(DryRunStep(
                node_id=node_id, node_type=node_type, status="simulated",
                detail="노드 실행 계약과 연결 경로 확인 완료",
            ))

    has_step_errors = any(step.status == "error" for step in steps)
    return DryRunResult(
        success=structural_passed and compile_passed and not has_step_errors,
        structural_passed=structural_passed,
        compile_passed=compile_passed,
        reachable_node_count=len(reachable_ids),
        blocked_side_effect_count=blocked_count,
        high_risk_node_count=high_risk_count,
        steps=steps,
        issues=issues,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
