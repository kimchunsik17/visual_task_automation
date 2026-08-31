"""반복 안에서 **아무 일도 안 하는 병합 노드**를 뺀다 (1회성 도구).

`mergeNode` 는 여러 갈래의 결과를 합치는 노드다. 들어오는 선이 하나뿐이고 나가는 선도 없으면
값 하나를 그대로 돌려주고 끝난다 — 캔버스에서만 자리를 차지한다.

    merge_vals = [str(__node_results__.get('n450', ''))]   # 값 하나
    merge_out  = '\\n'.join(merge_vals)                     # 하나짜리 join = 그대로

들어오는 선이 둘 이상인 병합은 **건드리지 않는다.** 그건 조건 분기를 합치는 정상 사용이고
242개 중 69개가 그렇게 쓰고 있다.

    python -m drop_noop_merge_nodes            # 미리보기
    python -m drop_noop_merge_nodes --apply
"""

from __future__ import annotations

import argparse
import collections
import copy
from typing import Any, Dict, List, Tuple


def find_noop_merges(graph: Dict[str, Any]) -> List[str]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    incoming = collections.Counter(e.get("target") for e in edges)
    outgoing = collections.Counter(e.get("source") for e in edges)
    return [n["id"] for n in nodes
            if n.get("type") == "mergeNode"
            and incoming[n["id"]] <= 1
            and outgoing[n["id"]] == 0]


def drop(graph: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """뺀 그래프와 뺀 노드 id 를 돌려준다. 원본은 건드리지 않는다."""
    fixed = copy.deepcopy(graph)
    targets = set(find_noop_merges(fixed))
    if not targets:
        return fixed, []
    fixed["nodes"] = [n for n in (fixed.get("nodes") or []) if n["id"] not in targets]
    # 이 병합으로 들어오던 선도 함께 뺀다. 나가는 선은 애초에 없다(그게 no-op 의 조건이다).
    fixed["edges"] = [e for e in (fixed.get("edges") or [])
                      if e.get("source") not in targets and e.get("target") not in targets]
    return fixed, sorted(targets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--version", default="1.4.0")
    args = parser.parse_args()

    import community_templates
    import models
    from database import SessionLocal

    db = SessionLocal()
    rows = db.query(models.Template).filter(
        models.Template.is_curated.is_(True),
        models.Template.status.in_(("published", "in_review")),
    ).order_by(models.Template.id.asc()).all()

    hits, failures = [], []
    for template in rows:
        version = db.query(models.TemplateVersion).filter_by(id=template.latest_version_id).first()
        share = (db.query(models.WorkflowShare).filter_by(id=version.workflow_share_id).first()
                 if version else None)
        if share is None or str(version.version) == str(args.version):
            continue
        fixed, dropped = drop(share.graph_snapshot or {})
        if not dropped:
            continue
        hits.append((template.slug, template.title, dropped))
        if not args.apply:
            continue
        actor = db.query(models.User).filter(models.User.id == template.owner_id).first()
        try:
            community_templates.revise_curated(
                db, actor, template, graph=fixed, version=args.version,
                changelog="아무 일도 하지 않던 병합 노드 제거", reviewer="구조 정리")
        except Exception as exc:      # noqa: BLE001
            db.rollback()
            failures.append((template.slug, str(exc)[:160]))

    print(f"아무 일도 안 하는 병합 노드가 있는 템플릿: {len(hits)}개")
    for slug, title, dropped in hits:
        print(f"   {slug:<12} {title[:34]:<36} 제거: {', '.join(dropped)}")
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
