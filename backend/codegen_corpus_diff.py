"""codegen_corpus_diff.py — 생성 소스 등가성 대조 (백로그 32 ENGINE-0 동안 쓰는 개발 도구).

무엇을 하나
  git 의 어느 시점(기본 HEAD)에 있던 `backend/graph.py` 를 별도 모듈로 올리고, 작업 트리의 graph.py 와
  나란히 코퍼스 전체를 컴파일해 생성 소스를 줄 단위로 대조한다. 순회 규칙·프렐류드·생성기를 손댄 뒤
  "옛 엔진과 바이트 단위로 같은가"(로드맵 §3.1 검증 매트릭스 '회귀')를 확인하는 용도다.

코퍼스
  공식 템플릿 107종(+ stop/entry/scope/pinned/project 변형) · 큐레이션 시드 142종 · 등록된 모든 노드 타입의
  최소 그래프. 커뮤니티 갤러리 템플릿(DB 전용)은 포함하지 않는다 — 필요하면 --projects-json 으로 넘긴다.

정규화
  포스터·문서 노드가 **컴파일 시점**에 뽑는 랜덤 파일명(uploads/poster_bb1527.png 등)만 `_HEX.` 로 바꾼다.
  이것 말고 컴파일 시점 비결정성은 없어야 한다 — 새로 생기면 이 도구가 잡는다.

사용
  cd backend && venv/Scripts/python codegen_corpus_diff.py            # HEAD 대 작업 트리
  venv/Scripts/python codegen_corpus_diff.py --ref origin/dev --show 5
  venv/Scripts/python codegen_corpus_diff.py --projects-json exported_graphs.json   # [{title, nodes, edges}, …] 추가
종료 코드: 차이 0 이면 0, 아니면 1.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import subprocess
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_run.db")
os.environ.setdefault("JWT_SECRET", "codegen-corpus-diff")
for _flag in ("DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER", "LLM_BASE_URL", "OPENROUTER_BASE_URL",
              "OPENROUTER_API_KEY", "PICKLE_API_KEY"):
    os.environ[_flag] = ""

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RANDOM_FILENAME = re.compile(r"_[0-9a-f]{6}\.(png|jpg|jpeg|hwpx|docx|pdf|txt|html)")


def normalize(source: str) -> str:
    return RANDOM_FILENAME.sub(r"_HEX.\1", source)


def load_graph_module_at(ref: str):
    """git ref 시점의 backend/graph.py 를 'graph_at_<ref>' 이름의 모듈로 올린다.
    node_registry·node_generators 등 나머지 모듈은 작업 트리의 것을 공유한다 — 대조 대상은 graph.py 다."""
    src = subprocess.check_output(["git", "show", f"{ref}:backend/graph.py"], cwd=HERE).decode("utf-8")
    name = "graph_at_" + re.sub(r"[^A-Za-z0-9_]", "_", ref)
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(src, f"<{ref}:backend/graph.py>", "exec"), module.__dict__)
    return module


def corpus(extra_projects_json: str | None):
    import official_templates
    import seed_curated_templates as curated
    from node_registry import node_registry
    import node_generators  # noqa: F401

    for t in official_templates.TEMPLATES:
        g = t["graph"]
        nodes, edges = g["nodes"], g["edges"]
        yield f"official:{t['title']}", nodes, edges, {}
        ids = [n["id"] for n in nodes]
        if len(ids) >= 3:
            yield f"official:{t['title']}|stop", nodes, edges, {"stop_node_id": ids[1]}
            yield f"official:{t['title']}|entry", nodes, edges, {"entry_node_id": ids[1]}
            yield f"official:{t['title']}|scope", nodes, edges, {"scope_node_ids": ids[:3]}
            yield f"official:{t['title']}|pinned", nodes, edges, {"pinned_outputs": {ids[1]: "PINNED"}}
            yield f"official:{t['title']}|project", nodes, edges, {"project_id": 77}
    for title, _category, tpl in curated.TEMPLATES:
        d = tpl.model_dump()
        yield f"curated:{title}", d["nodes"], d["edges"], {}
    for node_type in sorted(node_registry._generators.keys()):
        nodes = [{"id": "s", "type": "startNode", "data": {}}, {"id": "n", "type": node_type, "data": {}},
                 {"id": "o", "type": "outputNode", "data": {}}]
        edges = [{"id": "e1", "source": "s", "target": "n"}, {"id": "e2", "source": "n", "target": "o"}]
        yield f"smoke:{node_type}", nodes, edges, {}
    if extra_projects_json:
        with open(extra_projects_json, encoding="utf-8") as f:
            for i, p in enumerate(json.load(f)):
                yield f"project:{p.get('title') or i}", p["nodes"], p["edges"], {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="HEAD", help="옛 graph.py 를 읽을 git ref (기본 HEAD)")
    ap.add_argument("--show", type=int, default=2, help="차이 나는 그래프 몇 개의 diff 를 보여줄지")
    ap.add_argument("--projects-json", default=None, help="추가 그래프 [{title,nodes,edges}] JSON 파일")
    args = ap.parse_args()

    old = load_graph_module_at(args.ref)
    import graph as new

    total, different = 0, []
    for key, nodes, edges, kw in corpus(args.projects_json):
        total += 1
        a = normalize(old.compile_workflow(nodes, edges, **kw))
        b = normalize(new.compile_workflow(nodes, edges, **kw))
        if a != b:
            different.append(key)
            if len(different) <= args.show:
                print(f"=== {key}")
                diff = difflib.unified_diff(a.splitlines(), b.splitlines(), args.ref, "worktree", lineterm="", n=1)
                print("\n".join(list(diff)[:40]))
    print(f"compared {total} graphs against {args.ref}; different after normalization: {len(different)}")
    for k in different[:30]:
        print("  ", k)
    return 0 if not different else 1


if __name__ == "__main__":
    sys.exit(main())
