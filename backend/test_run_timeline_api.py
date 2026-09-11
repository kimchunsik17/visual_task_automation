"""실행 타임라인 API 배선(main.py) — 목록·상세·권한·스트림 스위치가 실제 앱에서 돈다 (ENGINE-1 3단계, ADR-0028).

test_admin_demo_routes 와 같은 방식: 별도 sqlite 로 main.app 을 띄우는 서브프로세스 시나리오. 실행은 execution.start 로
실제로 한 번 돌려 기록을 만들고, 그 기록을 API 로 읽는다.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
SCENARIO = r'''
import os, sys, datetime as _dt
os.environ["DATABASE_URL"] = sys.argv[1]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER",
          "OPENROUTER_BASE_URL", "PICKLE_API_KEY"):
    os.environ[k] = ""
os.environ["EXECUTION_ENGINE"] = "legacy"
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models, execution
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
other = models.User(google_id="g-other", email="other@example.com", name="Other", token_balance=1000)
db.add_all([owner, other]); db.commit()
project = models.Project(user_id=owner.id, title="타임라인", graph_data={"nodes": [], "edges": []})
db.add(project); db.commit()

nodes = [{"id": "s", "type": "startNode", "data": {}}, {"id": "v", "type": "valueNode", "data": {"value": "값"}},
         {"id": "o", "type": "outputNode", "data": {}}]
edges = [{"source": "s", "target": "v"}, {"source": "v", "target": "o"}]
result, tokens, logs = execution.start(nodes, edges, trigger_source="manual", db=db, project_id=project.id,
                                       executor_user_id=owner.id, session_id="editor", default_input="")
assert result == "값", result
db.commit()

def hdr(u):
    tok = main.jwt.encode({"user_id": u.id, "email": u.email, "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1)},
                          main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
    return {"Authorization": f"Bearer {tok}"}

# 1) 목록 — step 없이, 최신 먼저
r = client.get(f"/api/projects/{project.id}/workflow-runs", headers=hdr(owner)); assert r.status_code == 200, r.text
runs = r.json()["runs"]
assert len(runs) == 1 and runs[0]["status"] == "succeeded" and runs[0]["stepCount"] == 3 and "steps" not in runs[0], runs
assert runs[0]["triggerSource"] == "manual" and runs[0]["engine"] == "legacy" and runs[0]["executorUserId"] == owner.id
# 2) 상세 — step 포함
d = client.get(f"/api/projects/{project.id}/workflow-runs/{runs[0]['id']}", headers=hdr(owner)); assert d.status_code == 200, d.text
steps = d.json()["steps"]
assert [s["nodeId"] for s in steps] == ["s", "v", "o"] and steps[1]["outputPreview"] == "값" and steps[1]["status"] == "succeeded"
# 3) 권한 — 남의 프로젝트는 존재를 알리지 않는다(VIEW 없음 → 404), 비로그인은 401/403
assert client.get(f"/api/projects/{project.id}/workflow-runs", headers=hdr(other)).status_code in (403, 404)
assert client.get(f"/api/projects/{project.id}/workflow-runs/{runs[0]['id']}", headers=hdr(other)).status_code in (403, 404)
assert client.get(f"/api/projects/{project.id}/workflow-runs").status_code in (401, 403)
assert client.get(f"/api/projects/{project.id}/workflow-runs/999999", headers=hdr(owner)).status_code == 404
assert client.get(f"/api/projects/999999/workflow-runs", headers=hdr(owner)).status_code == 404
# 4) 스트림 — 꺼져 있으면 404, 비로그인은 401/403 (열린 스트림 본문은 test_run_events 가 직접 검증한다)
os.environ["RUN_EVENTS"] = "0"
assert client.get("/api/workflow-runs/stream", headers=hdr(owner)).status_code == 404
os.environ["RUN_EVENTS"] = "1"
assert client.get("/api/workflow-runs/stream").status_code in (401, 403)
# 5) FlowExecutionLog 연결 — 에디터 경로처럼 record_usage 를 남기면 run_id 가 붙는다
from usage_tracking import record_usage
log = record_usage(db, billable_user_id=owner.id, actor_user_id=owner.id, project_id=project.id, token_usage=tokens, result=result)
db.commit()
assert log.run_id == runs[0]["id"], (log.run_id, runs[0]["id"])
# 6) 옛 runs 목록(FlowExecutionLog)에는 run_id 가 덧붙어 타임라인으로 건너갈 수 있다 — 기존 필드는 그대로.
legacy = client.get(f"/api/projects/{project.id}/runs", headers=hdr(owner)); assert legacy.status_code == 200, legacy.text
assert isinstance(legacy.json(), list) and legacy.json()[0]["run_id"] == runs[0]["id"] and "result_summary" in legacy.json()[0]
print("RUN TIMELINE API OK")
'''


def test_run_timeline_routes_end_to_end(tmp_path):
    scenario_path = tmp_path / "run_timeline_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'runs.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "RUN TIMELINE API OK" in result.stdout
