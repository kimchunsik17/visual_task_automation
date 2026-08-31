"""node_generators/delivery_support.py — 발송 노드 생성기의 첨부 포트 공통부 (ADR-0018, 백로그 20).

발송 노드(Discord·SMTP Email·Gmail)는 본문 포트와 **첨부 포트**를 따로 갖는다(§4.10 목표 계약).
어떤 선행 노드의 artifact 를 첨부할지는 그래프 구조로 정해지므로 codegen 시점에 결정할 수 있고,
실제 id 는 실행 중에 `__node_artifacts__` 에서 읽는다.

여기 한 곳에 모으는 이유: 채널마다 "어디서 파일을 가져오는가" 를 따로 쓰면 한쪽만 첨부 포트를
보고 다른 쪽은 본문 포트를 보는 상태가 생긴다. 예전 Discord 의 경로 정규식이 정확히 그랬다.
"""

from __future__ import annotations

ATTACHMENT_HANDLE = "attachments"


def attachment_source_ids(node_id, incoming_edges) -> list:
    """이 발송 노드가 첨부를 가져올 선행 노드들.

    `attachments` 핸들로 들어온 간선이 있으면 그것만 쓴다(사용자가 명시적으로 연결한 파일).
    없으면 본문이 흘러온 선행 노드를 그대로 쓴다 — "포스터 만들어서 디스코드로 보내줘" 처럼
    노드 두 개를 일자로 잇는 가장 흔한 그래프가 별도 배선 없이 동작해야 하기 때문이다.
    """
    edges = incoming_edges.get(node_id) or []
    explicit = [e.get("source") for e in edges if e.get("targetHandle") == ATTACHMENT_HANDLE]
    if explicit:
        return [source for source in explicit if source]
    return [e.get("source") for e in edges if e.get("source") and e.get("targetHandle") != "template"]


def upstream_artifacts_expr(node_id, incoming_edges) -> str:
    """생성 코드에 넣을 `_collect_artifacts(...)` 호출식."""
    sources = attachment_source_ids(node_id, incoming_edges)
    if not sources:
        return "[]"
    args = ", ".join(repr(str(source)) for source in sources)
    return f"_collect_artifacts({args})"


def attachments_config(node) -> dict:
    """노드 설정의 `attachments` 값을 `{mode, artifactIds}` 로 정규화한다."""
    from delivery_attachments import normalize_config

    return normalize_config((node.get("data") or {}).get("attachments"))
