"""project_revisions.py — 프로젝트 저장 이력과 낙관적 동시성 (ADR-0006).

`Project.graph_data` 를 바로 덮어쓰지 않고 저장할 때마다 스냅샷을 남긴다. 그래야
두 탭에서 같은 워크플로우를 편집했을 때 나중 저장이 앞선 변경을 조용히 지우지 않고,
지워졌더라도 되돌릴 수 있다.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import models

# 노드가 "달라졌는지" 볼 때 무시할 키. 캔버스에서 노드를 옮기기만 한 것은 설정 변경과
# 성격이 다르고, 충돌 화면에서 알려줘 봐야 판단에 도움이 안 된다.
_IGNORED_NODE_KEYS = {"position", "positionAbsolute", "measured", "width", "height", "selected", "dragging"}


def _as_dict(graph_data: Any) -> Dict[str, Any]:
    return graph_data if isinstance(graph_data, dict) else {}


def _items_by_id(graph_data: Any, key: str) -> Dict[str, Dict[str, Any]]:
    items = _as_dict(graph_data).get(key) or []
    if not isinstance(items, list):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        result[str(item.get("id") or f"#{index}")] = item
    return result


def graph_summary(graph_data: Any) -> Dict[str, Any]:
    """목록 화면에서 스냅샷 전체를 읽지 않고도 규모를 보여주기 위한 요약."""
    nodes = _items_by_id(graph_data, "nodes")
    node_types: Dict[str, int] = {}
    for node in nodes.values():
        node_type = str(node.get("type") or "unknown")
        node_types[node_type] = node_types.get(node_type, 0) + 1
    return {
        "nodes": len(nodes),
        "edges": len(_items_by_id(graph_data, "edges")),
        "node_types": node_types,
    }


def _comparable_node(node: Dict[str, Any]) -> str:
    return json.dumps(
        {k: v for k, v in node.items() if k not in _IGNORED_NODE_KEYS},
        sort_keys=True, ensure_ascii=False, default=str,
    )


def diff_graphs(before: Any, after: Any) -> Dict[str, Any]:
    """두 그래프 사이에서 무엇이 달라졌는지 노드/엣지 id 로 알려준다.

    노드의 `changed` 는 위치 변경을 제외한 실제 설정 차이만 센다(_IGNORED_NODE_KEYS 참고).
    """
    before_nodes, after_nodes = _items_by_id(before, "nodes"), _items_by_id(after, "nodes")
    before_edges, after_edges = _items_by_id(before, "edges"), _items_by_id(after, "edges")

    changed = [
        node_id for node_id in sorted(set(before_nodes) & set(after_nodes))
        if _comparable_node(before_nodes[node_id]) != _comparable_node(after_nodes[node_id])
    ]
    return {
        "nodes": {
            "added": sorted(set(after_nodes) - set(before_nodes)),
            "removed": sorted(set(before_nodes) - set(after_nodes)),
            "changed": changed,
        },
        "edges": {
            "added": sorted(set(after_edges) - set(before_edges)),
            "removed": sorted(set(before_edges) - set(after_edges)),
        },
    }


def latest_revision(db: Session, project_id: int) -> Optional[models.ProjectRevision]:
    return (
        db.query(models.ProjectRevision)
        .filter(models.ProjectRevision.project_id == project_id)
        .order_by(models.ProjectRevision.revision.desc())
        .first()
    )


def revision_at(db: Session, project_id: int, revision: int) -> Optional[models.ProjectRevision]:
    return (
        db.query(models.ProjectRevision)
        .filter(
            models.ProjectRevision.project_id == project_id,
            models.ProjectRevision.revision == revision,
        )
        .first()
    )


def _is_unchanged(previous: models.ProjectRevision, project: models.Project) -> bool:
    return (
        previous.graph_data == project.graph_data
        and previous.title == project.title
        and previous.description == project.description
    )


def record_revision(
    db: Session,
    project: models.Project,
    *,
    author_user_id: Optional[int],
    source: str = "user",
) -> Optional[models.ProjectRevision]:
    """프로젝트의 현재 상태를 새 revision 으로 남기고 current_revision 을 올린다.

    직전 revision 과 내용이 같으면 아무것도 만들지 않고 None 을 돌려준다 — 배포 전 저장처럼
    같은 그래프를 연달아 저장하는 경로가 있어서, 그대로 두면 이력이 의미 없이 불어난다.
    커밋은 호출부가 한다(저장 트랜잭션과 같이 묶기 위해서다).
    """
    previous = latest_revision(db, project.id)
    if previous is not None and _is_unchanged(previous, project):
        return None

    revision = models.ProjectRevision(
        project_id=project.id,
        revision=(project.current_revision or 0) + 1,
        title=project.title,
        description=project.description,
        graph_data=project.graph_data,
        author_user_id=author_user_id,
        source=source,
        summary=graph_summary(project.graph_data),
    )
    db.add(revision)
    project.current_revision = revision.revision
    return revision


def conflict_detail(
    db: Session, project: models.Project, base_revision: int, incoming_graph: Any
) -> Dict[str, Any]:
    """409 응답 본문. 클라이언트가 무엇 때문에 막혔는지 판단할 수 있을 만큼만 담는다."""
    base = revision_at(db, project.id, base_revision)
    detail: Dict[str, Any] = {
        "code": "REVISION_CONFLICT",
        "message": "이 워크플로우가 다른 곳에서 먼저 저장됐다. 덮어쓰기 전에 확인이 필요하다.",
        "base_revision": base_revision,
        "current_revision": project.current_revision,
        "current_summary": graph_summary(project.graph_data),
    }
    if base is not None:
        # 내가 편집을 시작한 시점 이후 서버에서 무엇이 바뀌었는지.
        detail["server_changes_since_base"] = diff_graphs(base.graph_data, project.graph_data)
        # 내 변경이 그 위에 어떤 영향을 주는지.
        detail["my_changes_since_base"] = diff_graphs(base.graph_data, incoming_graph)
    return detail


def revision_to_dict(revision: models.ProjectRevision, include_graph: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "revision": revision.revision,
        "title": revision.title,
        "description": revision.description,
        "author_user_id": revision.author_user_id,
        "source": revision.source,
        "summary": revision.summary or {},
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }
    if include_graph:
        payload["graph_data"] = revision.graph_data
    return payload


def list_revisions(db: Session, project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = (
        db.query(models.ProjectRevision)
        .filter(models.ProjectRevision.project_id == project_id)
        .order_by(models.ProjectRevision.revision.desc())
        .limit(limit)
        .all()
    )
    return [revision_to_dict(row) for row in rows]
