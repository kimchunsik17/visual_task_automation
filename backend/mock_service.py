"""mock_service.py — Mock 탭의 시나리오 탐지와 실행 (ADR-0009).

에디터의 Mock 탭이 쓰는 backend. 노드별로 화면을 하드코딩하지 않고, 그래프에 실제로 놓인
노드의 정의(`mock` 블록)에서 무엇을 흉내 낼 수 있는지 읽어낸다 — 노드를 추가해도 이 파일을
고칠 일이 없어야 한다는 것이 설계 조건이다.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from connectors import mock as mock_fixtures
from connectors import mock_runtime
import node_definition

# 실행 트리거가 되는 노드. 사용자는 여기에 넣을 payload 를 고른다.
ENTRY_NODE_TYPES = {"webhookNode", "dynamicInputNode", "startNode", "scheduleNode"}

# webhookNode 는 아직 NodeDefinition 이 없다(이전 대상이 아니다). 그동안 Mock 탭이 비어 보이지
# 않도록 대표적인 수신 payload 를 여기 둔다. 노드가 이전되면 정의의 mock 블록으로 옮긴다.
WEBHOOK_SAMPLE_PAYLOADS = [
    {
        "id": "order_created",
        "label": "주문 생성 (커머스)",
        "payload": {
            "event": "order.created",
            "order_id": "ORD-20260828-0001",
            "customer": {"name": "김민준", "phone": "010-0000-0000"},
            "items": [{"name": "무선 이어폰", "quantity": 1, "price": 89000}],
            "total": 89000,
        },
    },
    {
        "id": "form_submitted",
        "label": "폼 제출 (문의 접수)",
        "payload": {
            "event": "form.submitted",
            "name": "이서연",
            "email": "seoyeon@example.com",
            "message": "제품 재입고 일정이 궁금합니다.",
        },
    },
    {
        "id": "plain_text",
        "label": "단순 텍스트",
        "payload": {"text": "안녕하세요, 이건 목업 요청입니다."},
    },
]

# 사용자에게 보여줄 시나리오 이름.
SCENARIO_LABELS = {
    "success": "성공",
    "auth_failed": "인증 실패 (401)",
    "rate_limited": "호출 한도 (429)",
    "not_found": "대상 없음 (404)",
    "server_error": "서버 오류 (500)",
    "timeout": "응답 없음 (timeout)",
}


def _nodes(graph_data: Any) -> List[Dict[str, Any]]:
    nodes = (graph_data or {}).get("nodes") if isinstance(graph_data, dict) else None
    return [n for n in (nodes or []) if isinstance(n, dict)]


def describe_graph(graph_data: Any) -> Dict[str, Any]:
    """이 워크플로우에서 무엇을 목업으로 돌릴 수 있는지 알려준다."""
    entries: List[Dict[str, Any]] = []
    mockable: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []

    for node in _nodes(graph_data):
        node_type = node.get("type")
        node_id = node.get("id")
        if node_type in ENTRY_NODE_TYPES:
            entries.append({
                "node_id": node_id,
                "node_type": node_type,
                "samples": WEBHOOK_SAMPLE_PAYLOADS if node_type == "webhookNode" else [],
            })
            continue

        definition = node_definition.get_definition(node_type)
        scenarios = mock_fixtures.scenario_names(definition.mock) if definition else []
        if scenarios:
            mockable.append({
                "node_id": node_id,
                "node_type": node_type,
                "service": definition.connector.service if definition.connector else node_type,
                "label": definition.display.label,
                "scenarios": [{"id": name, "label": SCENARIO_LABELS.get(name, name)} for name in scenarios],
            })
        elif definition is not None or node_type:
            # 외부와 통신하지 않는 노드(llmNode, conditionNode 등)는 목업이 필요 없다.
            # 통신하는데 정의가 없는 노드만 "아직 목업할 수 없다"로 알린다.
            if _talks_to_outside(node_type):
                unsupported.append({"node_id": node_id, "node_type": node_type})

    return {
        "entries": entries,
        "mockable_nodes": mockable,
        "unsupported_nodes": unsupported,
        "scenario_presets": [{"id": name, "label": label} for name, label in SCENARIO_LABELS.items()],
    }


# 정의로 이전되지 않은 채 외부 통신을 하는 노드들. 이 목록이 비어 가는 것이 이전 진행률이다.
_LEGACY_EXTERNAL_NODE_TYPES = {
    "emailNode", "kakaoNode", "discordNode", "telegramNode", "slackNode", "notionNode",
    "googleSheetsNode", "googleCalendarNode", "tossNode", "paymentLinkNode", "webCrawlerNode",
    "databaseNode",
}


def _talks_to_outside(node_type: Optional[str]) -> bool:
    return node_type in _LEGACY_EXTERNAL_NODE_TYPES


def run(
    graph_data: Any,
    *,
    db,
    project_id: int,
    entry_node_id: str = "",
    payload: Any = None,
    scenario: str = "success",
    scenario_by_node: Optional[Dict[str, str]] = None,
    start_node_id: Optional[str] = None,
    stop_node_id: Optional[str] = None,
    scope_node_ids: Optional[list] = None,
    pinned_outputs: Optional[Dict[str, Any]] = None,
    sample_input: Any = None,
) -> Dict[str, Any]:
    """워크플로우를 mock 모드로 실행한다.

    실제 배포(Live Mode)와 무관하고, 실제 자격증명을 읽지 않으며, 바깥으로 나가는 요청이
    하나도 없다. 그래서 사용자가 아무것도 등록하지 않은 상태에서도 처음부터 끝까지 돌려볼 수 있다.

    entry_node_id 는 "트리거 노드에 payload 를 넣는다" 는 뜻이고(전체 실행),
    start_node_id 는 "그 노드부터 컴파일해 돌린다" 는 뜻이다(범위 실행, EDITOR_SHORTCUTS §7.4).
    둘은 다른 축이라 함께 쓸 수 있다 — 범위 실행에서는 sample_input 이 직전 노드 출력 자리에 들어간다.
    이 조합이 Slice 4 의 완료 기준("외부 API 를 실제 호출하지 않고 한 노드를 검증")을 만든다.
    """
    from graph import run_workflow

    nodes = _nodes(graph_data)
    edges = (graph_data or {}).get("edges") if isinstance(graph_data, dict) else None
    edges = [e for e in (edges or []) if isinstance(e, dict)]

    inputs: Dict[str, Any] = {}
    if entry_node_id:
        inputs[entry_node_id] = payload if isinstance(payload, str) else json.dumps(payload or {}, ensure_ascii=False)
    # 범위 실행 인자는 kwargs 로 섞지 않는다 — inputs 의 키는 사용자가 정한 노드 id 라
    # 'entry_node_id' 라는 이름의 노드가 있으면 조용히 덮어쓴다(user_inputs 와 같은 이유).
    scope_kwargs: Dict[str, Any] = {"stop_node_id": stop_node_id, "scope_node_ids": scope_node_ids,
                                    "pinned_outputs": pinned_outputs}
    if start_node_id:
        scope_kwargs["entry_node_id"] = start_node_id
        scope_kwargs["approval_payload"] = sample_input if isinstance(sample_input, str) else (
            "" if sample_input is None else json.dumps(sample_input, ensure_ascii=False))

    context = mock_runtime.MockContext(scenario=scenario, scenario_by_node=scenario_by_node or {})
    started = time.monotonic()
    with mock_runtime.activate(context):
        try:
            result_text, tokens, logs = run_workflow(
                nodes, edges, db=db, session_id=f"mock_{project_id}", project_id=project_id,
                user_inputs=inputs, **scope_kwargs
            )
            failed = False
        except Exception as exc:  # 실행 엔진 자체가 죽어도 Mock 탭은 이유를 보여줘야 한다
            result_text, tokens, logs = f"목업 실행 실패: {exc}", {}, []
            failed = True

    # 성공 판정을 결과 문자열에서 추측하지 않는다. 예전 방식("❌" 포함 여부)은 노드마다
    # 실패 표기가 달라(⚠️, "Error:", 한국어 문구) 전부 실패했는데도 성공으로 보고했다.
    # 목업에서는 오간 요청이 남으므로 그걸 근거로 판단한다.
    failed_requests = [
        request for request in context.requests
        if request.error_code is not None or (request.status is not None and not 200 <= request.status < 300)
    ]

    # 아무 노드도 실행되지 않았는데 초록 체크를 보여주면 사용자는 검증이 끝났다고 오해한다
    # (연결이 끊긴 그래프, 빈 그래프에서 실제로 그랬다).
    # 실행 엔진 수준 실패(노드가 잡지 못한 예외)는 node_type='workflow' step 으로 남는다(ADR-0016) —
    # 노드 수에 세지 않고 실패로 본다. 요청 기록이 없어도 판별되는 유일한 근거다.
    from node_errors import runtime as _node_error_runtime
    runtime_failed = _node_error_runtime.summarize_logs(logs)["runtime_failed"] if isinstance(logs, list) else False
    executed_nodes = (
        len([step for step in logs if isinstance(step, dict) and step.get("node_type") != _node_error_runtime.WORKFLOW_NODE_TYPE])
        if isinstance(logs, list) else 0
    )

    return {
        "success": not failed and not runtime_failed and not failed_requests and executed_nodes > 0,
        "failed_request_count": len(failed_requests),
        "executed_node_count": executed_nodes,
        "simulated_wait_seconds": round(context.simulated_wait_seconds, 2),
        "result": result_text,
        "logs": logs,
        # LLM 노드는 목업 대상이 아니라 실제로 호출된다 — 토큰이 얼마나 들었는지 그대로 보여준다.
        "token_usage": tokens,
        "requests": [request.to_dict() for request in context.requests],
        "requests_truncated": context.truncated,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "scenario": scenario,
    }
