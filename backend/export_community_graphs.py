"""export_community_graphs.py — 커뮤니티 템플릿(선택: 사용자 프로젝트)의 그래프를 JSON 으로 내보낸다.

무엇을 위해
  engine_shadow_diff.py --projects-json 의 입력이다. 공식 템플릿·큐레이션 시드는 저장소 안에 있지만 커뮤니티 갤러리
  템플릿(242종)과 사용자 프로젝트는 DB 에만 있다 — 로드맵 §3.1 의 전환 조건("코퍼스에서 두 엔진 차이 0")을 채우려면
  이것들도 오프라인 대조에 넣어야 한다.

무엇을 내보내나
  - 게시된 템플릿(status=published)마다 **최신 게시 버전**의 그래프 스냅샷(TemplateVersion → WorkflowShare.graph_snapshot).
    제목은 `template:<slug>@<version>`.
  - --include-projects 를 주면 사용자 프로젝트의 graph_data 도(`project:<id>:<title>`). 실제 사용자 그래프라 대조 가치가
    가장 높다.

비밀을 내보내지 않기 위해
  그래프에는 자격증명 placeholder({{API_CENTER:…}})만 있어야 하지만, 옛 그래프에는 databaseNode 의 평문 접속 문자열이나
  노드 data 의 apiKey·accessToken 이 남아 있을 수 있다. run_workflow 와 같은 규칙으로 접속 문자열은 sentinel 로 바꾸고,
  비밀로 보이는 키는 비운다. 두 엔진이 같은(가려진) 그래프를 받으므로 대조는 그대로 성립한다.
  그래도 내보낸 파일은 저장소 밖 로컬에만 두라(.gitignore 대상이 아니다).

사용
  cd backend && venv/Scripts/python export_community_graphs.py ../../shadow_corpus.json
  venv/Scripts/python export_community_graphs.py out.json --include-projects
  venv/Scripts/python engine_shadow_diff.py --projects-json out.json
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from typing import Any, Dict, List, Optional

import models

# 노드 data 에서 비밀로 취급하는 키. placeholder 가 아닌 값은 비운다.
SECRET_DATA_KEYS = ("apiKey", "accessToken", "botToken", "token", "password", "secret", "clientSecret", "refreshToken")
_CREDENTIAL_REF = re.compile(r"^\{\{API_CENTER:[\w-]+(?:#\d+)?\}\}$")


def redact_nodes(nodes: List[dict]) -> List[dict]:
    """평문 비밀을 가린 깊은 복사. databaseNode.connectionString 은 run_workflow 와 같은 sentinel 규칙."""
    from db_query_runtime import LEGACY_PLAINTEXT_SENTINEL
    from meta_agent import PLACEHOLDER_URL

    out = copy.deepcopy(nodes)
    for node in out:
        if not isinstance(node, dict):
            continue
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        if node.get("type") == "databaseNode":
            cs = str(data.get("connectionString") or "").strip()
            if cs and cs != PLACEHOLDER_URL and not _CREDENTIAL_REF.match(cs):
                data["connectionString"] = LEGACY_PLAINTEXT_SENTINEL
        for key in SECRET_DATA_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value and not _CREDENTIAL_REF.match(value):
                data[key] = ""
    return out


def _latest_published_version(db, template) -> Optional[Any]:
    if template.latest_version_id:
        version = db.query(models.TemplateVersion).filter(models.TemplateVersion.id == template.latest_version_id).first()
        if version is not None and version.status == "published":
            return version
    return (db.query(models.TemplateVersion)
            .filter(models.TemplateVersion.template_id == template.id, models.TemplateVersion.status == "published")
            .order_by(models.TemplateVersion.published_at.desc(), models.TemplateVersion.id.desc())
            .first())


def template_graphs(db, *, status: str = "published") -> List[Dict[str, Any]]:
    rows = (db.query(models.Template).filter(models.Template.status == status)
            .order_by(models.Template.id.asc()).all())
    exported: List[Dict[str, Any]] = []
    for template in rows:
        version = _latest_published_version(db, template)
        if version is None:
            continue
        share = db.query(models.WorkflowShare).filter(models.WorkflowShare.id == version.workflow_share_id).first()
        graph = (share.graph_snapshot if share is not None else None) or {}
        nodes = graph.get("nodes") or []
        if not nodes:
            continue
        exported.append({
            "title": f"template:{template.slug}@{version.version}",
            "nodes": redact_nodes(nodes),
            "edges": [e for e in (graph.get("edges") or []) if isinstance(e, dict)],
        })
    return exported


def project_graphs(db) -> List[Dict[str, Any]]:
    exported: List[Dict[str, Any]] = []
    for project in db.query(models.Project).order_by(models.Project.id.asc()).all():
        graph = project.graph_data or {}
        nodes = graph.get("nodes") or []
        if not nodes:
            continue
        exported.append({
            "title": f"project:{project.id}:{project.title or ''}",
            "nodes": redact_nodes(nodes),
            "edges": [e for e in (graph.get("edges") or []) if isinstance(e, dict)],
        })
    return exported


def export_graphs(db, *, include_projects: bool = False, status: str = "published") -> List[Dict[str, Any]]:
    graphs = template_graphs(db, status=status)
    if include_projects:
        graphs.extend(project_graphs(db))
    return graphs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="내보낼 JSON 파일 경로 — 저장소 밖에 두라")
    ap.add_argument("--include-projects", action="store_true", help="사용자 프로젝트 graph_data 도 포함")
    ap.add_argument("--status", default="published", help="템플릿 상태 필터(기본 published)")
    args = ap.parse_args()

    from database import SessionLocal

    db = SessionLocal()
    try:
        graphs = export_graphs(db, include_projects=args.include_projects, status=args.status)
    finally:
        db.close()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(graphs, f, ensure_ascii=False)
    templates = sum(1 for g in graphs if g["title"].startswith("template:"))
    print(f"{len(graphs)} graphs ({templates} templates, {len(graphs) - templates} projects) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
