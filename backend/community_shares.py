"""community_shares.py — 워크플로우 공유와 가져오기 (ADR-0021, 우선 백로그 23 COMMUNITY-2).

**공유는 복사가 아니라 스냅샷이다.** 글에 붙는 워크플로우는 프로젝트를 가리키는 포인터가 아니라
게시 시점의 불변 사본이다(ADR-0006 `ProjectRevision` 과 같은 이유). 포인터로 두면 작성자가 자기
프로젝트를 고칠 때 남이 이미 읽은 글의 내용이 조용히 바뀐다.

**가져오기는 실행하지 않는다.** 사본을 만들고, 무엇을 채워야 하는지 보여주고, 실행은 사용자가 자기
계정에서 직접 한다. 그래서 `needs_input` 목록과 `risk_flags` 를 가져오기 **전에** 보여준다.

실행 오류 발췌(`ExecutionExcerpt`)도 여기 있다. 실행 로그를 통째로 붙이면 접속 문자열·토큰·서버
경로가 그대로 새므로, ADR-0016 `NodeError v1` 의 **공개 payload 만** 옮긴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import community_sanitize

MAX_SNAPSHOT_NODES = 200


class ShareError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 공유 규칙 위반."""


def create_share(db, owner_user, *, owner_type: str, owner_id: int, project) -> "models.WorkflowShare":
    """프로젝트의 현재 그래프를 정화해 불변 스냅샷으로 붙인다.

    정화에 실패하면(규칙 없는 노드 타입) 게시 자체가 거부된다 — 새 노드가 정화 규칙 없이 공개되는
    경로를 원천 차단한다.
    """
    import models

    if owner_type not in ("post", "answer"):
        raise ShareError("워크플로우를 붙일 수 없는 대상입니다.")
    if project is None or project.user_id != owner_user.id:
        raise ShareError("본인의 워크플로우만 공유할 수 있습니다.")

    graph = project.graph_data or {}
    if len(graph.get("nodes") or []) > MAX_SNAPSHOT_NODES:
        raise ShareError(f"노드가 {MAX_SNAPSHOT_NODES}개를 넘는 워크플로우는 공유할 수 없습니다.")

    try:
        snapshot, report = community_sanitize.sanitize_graph(graph)
    except community_sanitize.SanitizeRefused as exc:
        raise ShareError(str(exc)) from None

    # 깨진 워크플로우를 공유하지 않는다 — 가져간 사람의 첫 경험이 "실행이 안 된다"가 되면 안 된다.
    # dry-run 은 외부 호출을 하지 않고 구조 검사와 생성 코드 컴파일까지만 한다(ADR-0009).
    from dry_run import dry_run_workflow

    checked = dry_run_workflow(snapshot)
    if not (checked.structural_passed and checked.compile_passed):
        raise ShareError("워크플로우 구조에 문제가 있어 공유할 수 없습니다: "
                         + "; ".join(checked.issues[:3]))

    existing = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.owner_type == owner_type,
        models.WorkflowShare.owner_id == int(owner_id),
    ).first()
    if existing:
        raise ShareError("이미 워크플로우가 붙어 있습니다.")

    share = models.WorkflowShare(
        owner_type=owner_type, owner_id=int(owner_id),
        source_project_id=project.id, source_revision=getattr(project, "current_revision", None),
        graph_snapshot=snapshot, schema_version=1,
        node_types=report.node_types, required_credentials=report.required_credentials,
        risk_flags=report.risk_flags, created_at=datetime.datetime.utcnow(),
    )
    db.add(share)
    db.commit()
    return share


def public_share(share, *, include_graph: bool = False) -> Dict[str, Any]:
    """목록·상세에 나가는 모양. 그래프는 상세에서만 싣는다(목록이 무거워진다)."""
    if share is None:
        return None
    payload = {
        "id": share.id,
        "nodeTypes": list(share.node_types or []),
        "requiredCredentials": list(share.required_credentials or []),
        "riskFlags": list(share.risk_flags or []),
        "nodeCount": len((share.graph_snapshot or {}).get("nodes") or []),
        "importCount": share.import_count or 0,
        "sourceRevision": share.source_revision,
    }
    if include_graph:
        payload["graph"] = share.graph_snapshot
    return payload


def import_share(db, user, share) -> "models.Project":
    """가져오기 — **사본을 만들고 계보를 남긴다. 실행하지 않는다.**"""
    import models

    if share is None:
        raise ShareError("공유된 워크플로우를 찾을 수 없습니다.")

    # 구버전 공개 스냅샷에는 위치가 없던 노드가 모두 (0, 0)으로 저장돼 있다. 원본 스냅샷은
    # 불변으로 남겨 두고, 설치되는 사본만 연결 구조에 맞춰 복구한다.
    snapshot = community_sanitize.ensure_readable_layout(
        share.graph_snapshot or {"nodes": [], "edges": []}
    )
    origin = db.query(models.Post).filter(models.Post.id == share.owner_id).first() \
        if share.owner_type == "post" else None
    title = f"[가져옴] {origin.title[:60]}" if origin else "[가져온 워크플로우]"

    project = models.Project(
        user_id=user.id, title=title,
        # 계보를 사본에 남긴다 — 어디서 왔고 어느 시점의 것인지.
        description=f"커뮤니티에서 가져온 워크플로우 (share #{share.id}, revision {share.source_revision}).",
        graph_data=snapshot, visibility="private",
    )
    db.add(project)
    share.import_count = (share.import_count or 0) + 1
    db.commit()
    return project


def import_preview(share) -> Dict[str, Any]:
    """가져오기 **전에** 보여줄 것 — 무엇이 필요하고 무엇을 채워야 하는가."""
    snapshot = (share.graph_snapshot or {}) if share else {}
    return {
        "nodeTypes": list(share.node_types or []),
        "requiredCredentials": list(share.required_credentials or []),
        "riskFlags": list(share.risk_flags or []),
        # 스냅샷은 이미 정화돼 있다 — 다시 돌리면 지울 것이 없어 빈 목록이 나온다.
        # 비어 있는 자격증명·비밀·경로 칸이 곧 "채워야 하는 칸"이다.
        "needsInput": community_sanitize.needs_input_for(snapshot),
        "nodeCount": len(snapshot.get("nodes") or []),
        # 임의 코드는 아니지만(ADR-0019 의 허용 목록) 무엇을 가져가는지는 알고 가져가야 한다.
        "pythonCode": [
            {"nodeId": n.get("id"), "code": (n.get("data") or {}).get("code", "")}
            for n in (snapshot.get("nodes") or []) if n.get("type") == "pythonNode"
        ],
    }


# ── 실행 오류 발췌 ──────────────────────────────────────────────────────
def attach_excerpt(db, post, *, node_error: Dict[str, Any], node_type: str = "",
                   occurred_at: Optional[datetime.datetime] = None):
    """NodeError v1 의 **공개 payload 만** 옮긴다.

    `requestId`·예외 원문·경로·접속 문자열은 넘어오지 않는다 — 그것들은 내부 기록(`ErrorRecord`)에
    남아 있고 공개 payload 에는 애초에 없다.
    """
    import models

    if not isinstance(node_error, dict) or not node_error.get("code"):
        raise ShareError("붙일 수 있는 오류 정보가 아닙니다.")

    row = models.ExecutionExcerpt(
        post_id=post.id,
        node_type=str(node_type or "")[:60] or None,
        error_code=str(node_error.get("code"))[:60],
        error_category=str(node_error.get("category") or "")[:40] or None,
        effect_state=str(node_error.get("effectState") or "")[:20] or None,
        user_message=str(node_error.get("userMessage") or "")[:500] or None,
        occurred_at=occurred_at or datetime.datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def public_excerpt(row) -> Dict[str, Any]:
    return {
        "nodeType": row.node_type,
        "errorCode": row.error_code,
        "errorCategory": row.error_category,
        "effectState": row.effect_state,
        "userMessage": row.user_message,
        "occurredAt": row.occurred_at.isoformat() if row.occurred_at else None,
    }
