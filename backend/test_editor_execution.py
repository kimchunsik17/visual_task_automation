"""에디터 테스트·디버깅 기능(EDITOR_SHORTCUTS §7, Slice 4·5) 백엔드 계약 테스트."""

import pathlib

import pytest

from graph import compile_workflow, run_workflow

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def test_메모_노드는_실행에서_제외된다():
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "본문"}},
        {"id": "n3", "type": "outputNode", "data": {}},
        {"id": "m1", "type": "memoNode", "data": {"text": "여기는 크롤링 파이프라인"}},
    ]
    edges = [
        {"source": "n1", "target": "v1"},
        {"source": "v1", "target": "n3"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert "Unsupported" not in result
    assert result == "본문"
    assert all(step["node_id"] != "m1" for step in logs)


def test_메모만_있는_그래프는_빈_그래프로_안내된다():
    source = compile_workflow([{"id": "m1", "type": "memoNode", "data": {"text": "메모"}}], [])
    assert source.startswith("Error: Graph is empty")


def test_부분_실행은_진입_노드부터_샘플_입력으로_돈다():
    nodes = [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": "상류 값"}},
        {"id": "p1", "type": "jsonParserNode", "data": {"mode": "extract", "extractKey": "name"}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "n1", "target": "v1"},
        {"source": "v1", "target": "p1"},
        {"source": "p1", "target": "n3"},
    ]
    result, _, logs = run_workflow(
        nodes, edges,
        entry_node_id="p1", approval_payload='{"name": "샘플"}',
    )
    assert result == "샘플"                      # 샘플 입력이 직전 노드 출력 자리에 들어감
    executed = [step["node_id"] for step in logs]
    assert "v1" not in executed and "n1" not in executed   # 상류는 실행되지 않음
    assert "p1" in executed and "n3" in executed


# ── 분배(distributorNode)의 결과 수집 ────────────────────────────────────
def _distributor_flow(body_nodes, body_edges, *, value='["가나다", "라마바", "사아자"]'):
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": value}},
        {"id": "p1", "type": "jsonParserNode", "data": {"mode": "parse"}},
        {"id": "d1", "type": "distributorNode", "data": {}},
        {"id": "o1", "type": "outputNode", "data": {}},
        *body_nodes,
    ]
    edges = [
        {"source": "s1", "target": "v1"},
        {"source": "v1", "target": "p1"},
        {"source": "p1", "target": "d1"},
        {"source": "d1", "target": "o1", "sourceHandle": "done"},
        *body_edges,
    ]
    return nodes, edges


def test_분배는_항목별_결과를_모두_모은다():
    """예전에는 반복마다 누적 변수를 덮어써서 **마지막 항목 하나만** 남았다.

    "문단 여러 개를 한 번에 번역" 같은 워크플로우가 마지막 문단만 내놓았다(실제로 겪음).
    loopNode 는 직전 결과를 다음 회차에 넘기는 게 의도라 그대로 두지만, distributorNode 는
    "목록 각각 처리" 라 결과를 모아야 한다.
    """
    nodes, edges = _distributor_flow(
        [{"id": "m1", "type": "mergeNode", "data": {}}],
        [{"source": "d1", "target": "m1"}],
    )
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert result == "가나다\n라마바\n사아자"


def test_분배_결과는_리스트가_아니라_문자열로_넘어간다():
    """리스트를 그대로 넘기면 뒤에 오는 노드(메시지 본문·출력)가 `['a', 'b']` 를 받아 깨진다."""
    nodes, edges = _distributor_flow([], [])
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert isinstance(result, str) and "[" not in result


def test_빈_항목은_이어_붙일_때_빠진다():
    """조건 분기로 건너뛴 항목이 빈 줄로 남으면 결과가 지저분해진다."""
    nodes, edges = _distributor_flow([], [], value='["가나다", "", "사아자"]')
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert result == "가나다\n사아자"


def test_항목이_없으면_원본_입력이_새어나오지_않는다():
    """누적 변수를 원본 목록으로 시작하면 처리한 게 없을 때 파싱 전 값이 그대로 나간다."""
    nodes, edges = _distributor_flow([], [], value="[]")
    result, _, _ = run_workflow(nodes, edges, default_input="")
    assert result == ""


# ── 범위 실행과 고정 출력 (§7.3·§7.4, Slice 4 완성) ──────────────────────
def _chain():
    """s1 → a(값) → b(대문자) → c(출력). 하류 노드가 상류 결과를 그대로 이어받는 최소 그래프."""
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "a", "type": "valueNode", "data": {"value": "상류 결과"}},
        {"id": "b", "type": "valueNode", "data": {"value": "중간 결과"}},
        {"id": "c", "type": "outputNode", "data": {}},
    ]
    edges = [{"source": "s1", "target": "a"}, {"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
    return nodes, edges


def _ran(logs):
    return [step["node_id"] for step in logs]


def test_여기까지_실행은_하류를_돌리지_않는다():
    nodes, edges = _chain()
    _, _, logs = run_workflow(nodes, edges, stop_node_id="b", default_input="")
    assert _ran(logs) == ["s1", "a", "b"]      # c 는 실행되지 않는다


def test_이_노드만_실행은_진입과_정지가_같은_노드다():
    nodes, edges = _chain()
    result, _, logs = run_workflow(nodes, edges, entry_node_id="b", stop_node_id="b",
                                   approval_payload="샘플 입력", default_input="")
    assert _ran(logs) == ["b"]
    assert result == "중간 결과"


def test_선택_영역만_실행한다():
    nodes, edges = _chain()
    _, _, logs = run_workflow(nodes, edges, scope_node_ids=["a", "b"], default_input="")
    assert _ran(logs) == ["a", "b"]            # s1(상류)과 c(하류)는 범위 밖


def test_범위에_노드가_없으면_안내로_끝난다():
    nodes, edges = _chain()
    source = compile_workflow(nodes, edges, scope_node_ids=["없는노드"])
    assert source.startswith("Error: 선택한 실행 범위에")


def test_고정_출력은_그_노드를_실행하지_않고_하류로_흘린다():
    nodes, edges = _chain()
    result, _, logs = run_workflow(nodes, edges, pinned_outputs={"a": "고정된 상류 출력"}, default_input="")
    pinned_step = next(step for step in logs if step["node_id"] == "a")
    assert pinned_step["pinned"] is True and pinned_step["status"] == "success"
    assert pinned_step["result_data"] == "고정된 상류 출력"
    assert "a" in _ran(logs) and "b" in _ran(logs)         # 하류는 계속 실행된다
    assert "고정된 상류 출력" in result                     # 고정 값이 하류 노드 입력으로 흘렀다


def test_고정_출력의_경고_문구는_이번_실행의_오류가_아니다():
    """사용자가 고정해 둔 값 안의 '[⚠️ ...]' 를 이번 실행의 실패로 세면 안 된다(ADR-0016 legacy 감지)."""
    nodes, edges = _chain()
    _, _, logs = run_workflow(nodes, edges, pinned_outputs={"a": "본문\n\n[⚠️ 카카오 발송 실패]"}, default_input="")
    pinned_step = next(step for step in logs if step["node_id"] == "a")
    assert pinned_step["status"] == "success" and pinned_step["error"] is None


def test_고정_출력은_생성_코드에_문자열로만_들어간다():
    """따옴표·개행이 섞인 값이 생성 코드를 깨뜨리지 않아야 한다."""
    nodes, edges = _chain()
    source = compile_workflow(nodes, edges, pinned_outputs={"a": '따옴표 " 와 \n 줄바꿈'})
    assert not source.startswith("Error"), source
    compile(source, "<pinned>", "exec")


# ── API 계층 E2E — 범위 실행이 실제 엔드포인트로 이어지는가 ────────────────
SCENARIO = '''
import json, os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
owner = models.User(id=1, google_id="g1", email="o@e.st", name="owner", token_balance=100000)
db.add(owner)
graph = {
    "nodes": [
        {"id": "w1", "type": "webhookNode", "data": {}},
        {"id": "h1", "type": "httpRequestNode", "data": {"method": "POST", "url": "https://api.example.com/x", "body": "{}"}},
        {"id": "o1", "type": "outputNode", "data": {}},
    ],
    "edges": [
        {"source": "w1", "target": "h1"},
        {"source": "h1", "target": "o1"},
    ],
}
db.add(models.Project(id=5, user_id=1, title="범위 실행", graph_data=graph))
db.commit()
main.app.dependency_overrides[main.get_current_user_required] = lambda: owner
main.app.dependency_overrides[main.get_current_user] = lambda: owner
client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

# 목업으로 한 노드만 — 외부 호출 없이 입력→출력을 확인한다(Slice 4 완료 기준)
res = client.post("/api/projects/5/mock/run", json={
    "graph_data": graph, "start_node_id": "h1", "stop_node_id": "h1",
    "sample_input": "샘플", "scenario": "success",
})
check("목업 노드 실행 200", res.status_code == 200, res.text)
body = res.json()
check("그 노드만 실행됐다", [s["node_id"] for s in body["logs"]] == ["h1"], json.dumps(body["logs"], ensure_ascii=False))
check("목업이라 성공으로 판정된다", body["success"] is True, res.text)
check("외부로 나간 요청이 아니라 목업 기록이다", all(r["node_id"] == "h1" for r in body["requests"]), res.text)

# 목업 실패 시나리오도 노드 단위로 재현된다
res = client.post("/api/projects/5/mock/run", json={
    "graph_data": graph, "start_node_id": "h1", "stop_node_id": "h1",
    "sample_input": "샘플", "scenario": "auth_failed",
})
step = res.json()["logs"][0]
check("실패 시나리오가 code 로 온다", step["error"]["code"] == "CREDENTIAL_INVALID", json.dumps(step, ensure_ascii=False))

# 고정 출력이 있으면 그 노드는 목업 요청조차 보내지 않는다
res = client.post("/api/projects/5/mock/run", json={
    "graph_data": graph, "entry_node_id": "w1", "payload": {"a": 1},
    "pinned_outputs": {"h1": '{"pinned": true}'}, "scenario": "success",
})
body = res.json()
pinned = next(s for s in body["logs"] if s["node_id"] == "h1")
check("고정 출력이 실행을 대체한다", pinned["pinned"] is True and pinned["result_data"] == '{"pinned": true}', json.dumps(pinned, ensure_ascii=False))
check("고정된 노드는 목업 요청도 없다", all(r["node_id"] != "h1" for r in body["requests"]), json.dumps(body["requests"], ensure_ascii=False))

# 실제 실행 경로도 범위 인자를 받는다(여기까지 실행)
res = client.post("/api/execute", json={
    "project_id": 5, "nodes": graph["nodes"], "edges": graph["edges"], "stop_node_id": "w1",
})
check("여기까지 실제 실행 200", res.status_code == 200, res.text)
check("하류는 실행되지 않았다", [s["node_id"] for s in res.json()["logs"]] == ["w1"], res.text)

res = client.post("/api/execute", json={
    "project_id": 5, "nodes": graph["nodes"], "edges": graph["edges"], "stop_node_id": "nope",
})
check("없는 stop_node_id 는 400", res.status_code == 400, res.text)

print("ALL OK")
'''


def test_범위_실행_API_시나리오(tmp_path):
    import subprocess
    import sys

    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")
    scenario = tmp_path / "scenario.py"
    scenario.write_text(SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()
    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'app.db'}", str(BACKEND_DIR)],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout
