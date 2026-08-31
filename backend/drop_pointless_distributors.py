"""목록을 받지 못하는 **무의미한 분배 노드**를 뺀다 (1회성 도구).

`distributorNode` 는 앞 단계가 넘긴 값을 목록으로 보고 항목마다 반복한다. 그런데 값이
리스트가 아니면 이렇게 감싼다.

    if not isinstance(dist_list, list):
        dist_list = [dist_list]          # 문자열 하나 → 항목 하나

앞이 `dynamicInputNode`(텍스트 한 칸)나 `startNode` 면 **항상 1회만 돈다.** 반복하는 것처럼
보이지만 실제로는 통짜 텍스트가 그대로 다음 노드로 간다. 캔버스만 복잡해지고, 항목별 API 를
부르는 노드(jusoNode 등)가 뒤에 있으면 통짜 텍스트를 받아 실패한다.

**목록을 만드는 노드가 앞에 있는 분배기는 건드리지 않는다** — 23개가 정상으로 쓰고 있다.

    python -m drop_pointless_distributors            # 미리보기
    python -m drop_pointless_distributors --apply
"""

from __future__ import annotations

import argparse
import collections
import copy
from typing import Any, Dict, List, Tuple

# 목록을 만들어 내는 노드. 이 중 하나가 상류에 있으면 분배기는 제 역할을 한다.
LIST_SOURCES = {
    "jsonParserNode", "databaseNode", "naverSearchNode", "rssTriggerNode", "youtubeNode",
    "youtubeTriggerNode", "gmailTriggerNode", "gmailNode", "googleSheetsNode", "dataGoKrNode",
    "naverSearchTriggerNode", "httpRequestNode", "webhookNode",
}
# 값을 그대로 흘려보내는 노드 — 원천을 찾을 때 통과시킨다.
PASSTHROUGH = {"conditionNode", "mergeNode", "delayNode", "humanApprovalNode",
               "promptNode", "valueNode"}


def _sources(edges) -> Dict[str, List[str]]:
    inc = collections.defaultdict(list)
    for e in edges:
        inc[e.get("target")].append(e.get("source"))
    return inc


def receives_a_list(node_id: str, types, inc) -> bool:
    seen, stack, roots = set(), list(inc[node_id]), []
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if types.get(current) in PASSTHROUGH:
            stack.extend(inc[current])
        else:
            roots.append(types.get(current))
    return any(root in LIST_SOURCES for root in roots)


def _terminals(start_ids, edges, skip) -> List[str]:
    """본체 사슬의 끝 노드들 — 여기가 `done` 대상에 이어져야 한다."""
    out = collections.defaultdict(list)
    for e in edges:
        if e.get("source") in skip:
            continue
        out[e.get("source")].append(e.get("target"))
    seen, stack, ends = set(), list(start_ids), []
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if out[current]:
            stack.extend(out[current])
        else:
            ends.append(current)
    return ends


def drop(graph: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    fixed = copy.deepcopy(graph)
    nodes = fixed.get("nodes") or []
    edges = fixed.get("edges") or []
    types = {n["id"]: n.get("type") for n in nodes}
    inc = _sources(edges)

    targets = [nid for nid, ty in types.items()
               if ty == "distributorNode" and not receives_a_list(nid, types, inc)]
    if not targets:
        return fixed, []

    for node_id in targets:
        incoming = [e for e in edges if e.get("target") == node_id]
        body = [e for e in edges if e.get("source") == node_id
                and (e.get("sourceHandle") or "") != "done"]
        done = [e for e in edges if e.get("source") == node_id
                and (e.get("sourceHandle") or "") == "done"]

        # 본체의 끝을 먼저 찾아 둔다(분배기를 지우기 전에).
        ends = _terminals([e["target"] for e in body], edges, skip={node_id})

        edges = [e for e in edges
                 if e.get("source") != node_id and e.get("target") != node_id]

        # 앞 → 본체. 들어오던 엣지의 갈래 이름(conditionNode 의 handle 등)을 그대로 옮긴다.
        for before in incoming:
            for after in body:
                edges.append({
                    "id": f"e-{before['source']}-{after['target']}",
                    "source": before["source"], "target": after["target"],
                    **({"sourceHandle": before["sourceHandle"]}
                       if before.get("sourceHandle") else {}),
                })
        # 본체 끝 → 완료 대상. 반복이 없어졌으니 그냥 이어 붙이면 된다.
        for end in ends:
            for after in done:
                edges.append({"id": f"e-{end}-{after['target']}",
                              "source": end, "target": after["target"]})

    fixed["nodes"] = [n for n in nodes if n["id"] not in targets]
    # 같은 짝이 두 번 생기지 않게 정리한다.
    unique, seen_pairs = [], set()
    for e in edges:
        key = (e.get("source"), e.get("target"), e.get("sourceHandle") or "")
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        unique.append(e)
    fixed["edges"] = unique
    return fixed, sorted(targets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--version", default="1.5.0")
    parser.add_argument("--only", default="", help="쉼표로 구분한 slug 목록만 처리")
    args = parser.parse_args()

    import community_templates
    import models
    from database import SessionLocal

    db = SessionLocal()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    rows = db.query(models.Template).filter(
        models.Template.is_curated.is_(True),
        models.Template.status.in_(("published", "in_review")),
    ).order_by(models.Template.id.asc()).all()

    hits, failures = [], []
    for template in rows:
        if only and template.slug not in only:
            continue
        version = db.query(models.TemplateVersion).filter_by(id=template.latest_version_id).first()
        share = (db.query(models.WorkflowShare).filter_by(id=version.workflow_share_id).first()
                 if version else None)
        if share is None or str(version.version) == str(args.version):
            continue
        fixed, dropped = drop(share.graph_snapshot or {})
        if not dropped:
            continue
        hits.append((template.slug, template.title, dropped, fixed))
        if not args.apply:
            continue
        actor = db.query(models.User).filter(models.User.id == template.owner_id).first()
        try:
            community_templates.revise_curated(
                db, actor, template, graph=fixed, version=args.version,
                changelog="목록을 받지 못해 1회만 돌던 분배 노드 제거", reviewer="구조 정리")
        except Exception as exc:      # noqa: BLE001
            db.rollback()
            failures.append((template.slug, str(exc)[:200]))

    print(f"무의미한 분배 노드가 있는 템플릿: {len(hits)}개")
    for slug, title, dropped, fixed in hits:
        print(f"\n   {slug} — {title[:36]}   제거: {', '.join(dropped)}")
        print(f"     남은 엣지: {[(e['source'], e.get('sourceHandle') or '', e['target']) for e in fixed['edges']]}")
    if failures:
        print(f"\n실패 {len(failures)}건:")
        for slug, err in failures:
            print(f"   {slug}: {err}")
    if not args.apply:
        print("\n(--apply 를 붙이면 새 버전으로 반영합니다)")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
