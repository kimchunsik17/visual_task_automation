"""engine_shadow_diff.py — 두 엔진을 mock 모드로 나란히 돌려 결과·로그·토큰을 대조 (백로그 32 ENGINE-0 4단계 섀도).

무엇을 하나
  코퍼스(공식 템플릿 107 · 큐레이션 시드 142 · 등록 노드 타입 최소 그래프)를 legacy(생성 소스 exec)와
  interpreter(정적 계획 실행)로 각각 실행하고 결과 문자열 · 실행 로그(노드 순서·상태·결과·오류 코드) · 토큰 집계를
  대조한다. 로드맵 §3.1 "코퍼스에서 차이 0 이 전환 조건" 의 실행 층이다(소스 층은 codegen_corpus_diff.py).

바깥으로 나가는 것이 없어야 한다
  - connectors: mock_runtime 활성(ADR-0009) — 커넥터 노드는 mock transport 로 간다.
  - LLM: LLM_PROVIDER=mock (llm.providers.MockProvider, LLM_MOCK_RESPONSE 로 결정적 응답).
  - 나머지 네트워크: socket 수준에서 차단한다(getaddrinfo·connect 가 예외). 두 엔진이 같은 실패를 겪는다.
  - time.sleep 은 무시(delayNode), 포스터 렌더는 스텁, 업로드 루트는 임시 디렉토리, db 는 None.
  이 도구는 두 엔진의 **차이**를 찾는 것이 목적이다 — 개별 노드가 mock 환경에서 실패하는 것은 정상이다.

정규화
  시각(start/end_time)·오류 requestId·컴파일/실행 시점 랜덤 파일명(_xxxxxx.png 등)만 지운다.

사용
  cd backend && venv/Scripts/python engine_shadow_diff.py            # 전체 코퍼스
  venv/Scripts/python engine_shadow_diff.py --only official --show 5
  venv/Scripts/python engine_shadow_diff.py --projects-json exported_graphs.json
종료 코드: 차이 0 이면 0, 아니면 1.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import socket
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_run.db")
os.environ.setdefault("JWT_SECRET", "engine-shadow-diff")
os.environ["LLM_PROVIDER"] = "mock"
os.environ.setdefault("LLM_MOCK_RESPONSE", '{"summary": "mock", "items": ["a", "b"]}')
for _flag in ("DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_BASE_URL", "OPENROUTER_BASE_URL", "OPENROUTER_API_KEY",
              "PICKLE_API_KEY", "LLM_EXECUTION_PROVIDER", "LLM_ROUTING_MODE", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    os.environ[_flag] = ""
_UPLOAD_ROOT = tempfile.mkdtemp(prefix="shadow-uploads-")
os.environ["UPLOAD_DIR"] = _UPLOAD_ROOT

RANDOM_FILENAME = re.compile(r"_[0-9a-f]{6}\.(png|jpg|jpeg|hwpx|docx|pdf|txt|html)")
# NodeResult 를 문자열로 흘리는 노드(databaseNode 등)는 오류의 requestId(난수)가 result_data 문자열 안에 들어간다.
REQUEST_ID_IN_TEXT = re.compile(r'("requestId"\s*:\s*")[0-9a-f]+(")')


def _block_network() -> None:
    def _refuse(*_a, **_k):
        raise OSError("engine_shadow_diff: network blocked")

    socket.getaddrinfo = _refuse  # type: ignore[assignment]
    socket.socket.connect = _refuse  # type: ignore[assignment]
    socket.socket.connect_ex = _refuse  # type: ignore[assignment]
    socket.create_connection = _refuse  # type: ignore[assignment]


def _neutralize_side_effects() -> None:
    time.sleep = lambda *_a, **_k: None  # type: ignore[assignment]
    try:
        import poster_generator

        def _stub_render(html, out_path, **_k):
            with open(out_path, "wb") as f:
                f.write(b"stub")
            return out_path

        poster_generator.render_html_to_file = _stub_render  # type: ignore[assignment]
    except Exception:
        pass


def normalize_text(s) -> str:
    return REQUEST_ID_IN_TEXT.sub(r"\1HEX\2", RANDOM_FILENAME.sub(r"_HEX.\1", str(s)))


def normalize_logs(logs) -> list:
    out = []
    for step in logs or []:
        err = step.get("error") or None
        if err:
            err = {k: v for k, v in err.items() if k != "requestId"}
            err = json.loads(normalize_text(json.dumps(err, ensure_ascii=False, sort_keys=True)))
        out.append({
            "node_id": step.get("node_id"), "node_type": step.get("node_type"), "status": step.get("status"),
            "result_status": step.get("result_status"), "pinned": bool(step.get("pinned")),
            "result_data": normalize_text(step.get("result_data")) if step.get("result_data") is not None else None,
            "error": err,
            "artifacts": [normalize_text(json.dumps(a, ensure_ascii=False, sort_keys=True)) for a in (step.get("artifacts") or [])],
        })
    return out


def corpus(only: str | None, extra_projects_json: str | None):
    import official_templates
    import seed_curated_templates as curated
    from node_registry import node_registry
    import node_generators  # noqa: F401

    if only in (None, "official"):
        for t in official_templates.TEMPLATES:
            g = t["graph"]
            yield f"official:{t['title']}", g["nodes"], g["edges"]
    if only in (None, "curated"):
        for title, _category, tpl in curated.TEMPLATES:
            d = tpl.model_dump()
            yield f"curated:{title}", d["nodes"], d["edges"]
    if only in (None, "smoke"):
        for node_type in sorted(node_registry._generators.keys()):
            nodes = [{"id": "s", "type": "startNode", "data": {}}, {"id": "n", "type": node_type, "data": {}},
                     {"id": "o", "type": "outputNode", "data": {}}]
            edges = [{"id": "e1", "source": "s", "target": "n"}, {"id": "e2", "source": "n", "target": "o"}]
            yield f"smoke:{node_type}", nodes, edges
    if extra_projects_json:
        with open(extra_projects_json, encoding="utf-8") as f:
            for i, p in enumerate(json.load(f)):
                yield f"project:{p.get('title') or i}", p["nodes"], p["edges"]


def run_engine(engine: str, nodes, edges):
    import execution
    from connectors import mock_runtime

    os.environ["EXECUTION_ENGINE"] = engine
    context = mock_runtime.MockContext(scenario="success", scenario_by_node={})
    with mock_runtime.activate(context):
        try:
            # 실행은 언제나 execution.start 를 지난다(test_execution_entry 의 규칙). 오프라인 대조는 평가 러너와 같은 출처다.
            result, tokens, logs = execution.start(copy.deepcopy(nodes), copy.deepcopy(edges), trigger_source="evaluation",
                                                   db=None, session_id=f"shadow_{engine}", project_id=None,
                                                   default_input="섀도 대조 입력", approval_decisions={})
        except Exception as exc:  # 엔진이 예외를 밖으로 던지면 그것도 대조 대상이다
            result, tokens, logs = f"<<raised {type(exc).__name__}: {exc}>>", {}, []
    return {"result": normalize_text(result), "tokens": tokens, "logs": normalize_logs(logs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["official", "curated", "smoke"], default=None)
    ap.add_argument("--show", type=int, default=3, help="차이 나는 그래프 몇 개의 diff 를 보여줄지")
    ap.add_argument("--projects-json", default=None, help="추가 그래프 [{title,nodes,edges}] JSON 파일")
    args = ap.parse_args()

    _block_network()
    _neutralize_side_effects()

    total, different = 0, []
    started = time.monotonic()
    for key, nodes, edges in corpus(args.only, args.projects_json):
        total += 1
        legacy = run_engine("legacy", nodes, edges)
        interp = run_engine("interpreter", nodes, edges)
        if legacy != interp:
            different.append(key)
            if len(different) <= args.show:
                print(f"=== {key}")
                a = json.dumps(legacy, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
                b = json.dumps(interp, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
                print("\n".join(list(difflib.unified_diff(a, b, "legacy", "interpreter", lineterm="", n=2))[:60]))
    elapsed = time.monotonic() - started
    print(f"compared {total} graphs in {elapsed:.1f}s; different after normalization: {len(different)}")
    for k in different[:40]:
        print("  ", k)
    return 0 if not different else 1


if __name__ == "__main__":
    sys.exit(main())
