"""python_node_survey.py — 저장된 pythonNode 코드를 유형별로 집계한다 (§4.15 PYEXEC-2).

두 가지를 답한다.

  1. **호환**: 새로 넣은 정적 상한(PYEXEC-0)에 기존 워크플로우가 걸리는가?
     하나라도 걸리면 사용자의 저장된 그래프가 갑자기 실행되지 않는다는 뜻이라, 상한을 올리거나
     예외 경로를 둬야 한다.
  2. **수요**: 사람들이 pythonNode 로 실제로 무엇을 하는가?
     상위 유형이 뚜렷하면 선언형 `transformNode` 설계로 이어진다(§9-13). 뚜렷하지 않으면
     만들지 않는다 — 쓰이지 않을 노드를 늘리는 비용이 더 크다.

읽기 전용이다. 실행하지 않고 파싱만 한다.

    python backend/python_node_survey.py
"""

from __future__ import annotations

import ast
import collections
import json
import sys

# 유형 분류는 휴리스틱이다. 정확한 이름표가 아니라 "무엇이 많은가"의 신호로만 쓴다.
CATEGORY_HINTS = [
    ("json_reshape", {"keys", "values", "items", "get", "setdefault"}),
    ("filter_select", {"filter", "any", "all"}),
    ("string_format", {"join", "split", "replace", "strip", "lower", "upper", "splitlines"}),
    ("aggregate", {"sum", "len", "max", "min", "sorted", "count"}),
]


def _classify(code: str) -> tuple[str, set]:
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return "unparseable", set()
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Name):
            used.add(node.id)
    for name, markers in CATEGORY_HINTS:
        if used & markers:
            return name, used
    return "other", used


def main() -> int:
    from database import SessionLocal
    import models
    from workflow_security import WorkflowSecurityError, validate_python_node_code

    db = SessionLocal()
    try:
        projects = db.query(models.Project).all()
        categories = collections.Counter()
        symbols = collections.Counter()
        rejected = []
        total = 0

        for project in projects:
            graph = project.graph_data or {}
            for node in (graph.get("nodes") or []):
                if not isinstance(node, dict) or node.get("type") != "pythonNode":
                    continue
                code = str((node.get("data") or {}).get("code") or "")
                total += 1
                category, used = _classify(code)
                categories[category] += 1
                symbols.update(used)
                try:
                    validate_python_node_code(code)
                except WorkflowSecurityError as exc:
                    rejected.append({
                        "project_id": project.id, "node_id": node.get("id"),
                        "reason": str(exc), "bytes": len(code.encode("utf-8")),
                    })

        print(f"프로젝트 {len(projects)}개 · pythonNode {total}개\n")
        print("── 새 정적 상한 호환 ──")
        if not rejected:
            print("  거부 0건 — 기존 워크플로우가 새 상한에 걸리지 않는다.")
        else:
            print(f"  ⚠️ 거부 {len(rejected)}건 — 상한을 올리거나 예외 경로가 필요하다.")
            for item in rejected[:20]:
                print(f"    project={item['project_id']} node={item['node_id']} :: {item['reason']}")

        print("\n── 유형 분포 ──")
        for name, count in categories.most_common():
            share = f"{count / total * 100:.0f}%" if total else "-"
            print(f"  {name:14} {count:4}  {share}")

        print("\n── 자주 쓰인 이름·메서드 (상위 20) ──")
        for name, count in symbols.most_common(20):
            print(f"  {name:16} {count}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
