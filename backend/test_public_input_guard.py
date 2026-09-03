"""공개 실행 입력 상한(_reject_oversized_inputs)의 경계 검사 — 부스 체크리스트 7(입력 방어)."""

from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
user = models.User(id=1, google_id="guard", email="guard@example.com", name="guard")
db.add(user)
db.flush()
project = models.Project(user_id=1, title="공개 앱", visibility="public",
                         share_token="tok-guard",
                         graph_data={"nodes": [
                             {"id": "s", "type": "startNode", "data": {}},
                             {"id": "o", "type": "outputNode", "data": {}}],
                             "edges": [{"id": "e1", "source": "s", "target": "o"}]})
db.add(project)
db.commit()

client = TestClient(main.app)

# 실행 자체는 관심 밖(별도 테스트가 있다) — sqlite 의 노드 로그 시간 타입 문제를 피해서
# 가드만 본다. 가드는 run_workflow 호출 **전에** 동작해야 한다.
main.run_workflow = lambda *args, **kwargs: ("ok", {}, [])

# 1) 정상 입력은 통과한다 (길지만 상한 이내)
ok = client.post("/api/apps/tok-guard/execute", json={"inputs": {"text": "가" * 7000}})
assert ok.status_code == 200, ok.text

# 2) 값 하나가 상한(8,000자) 초과 → 422 (500 이 아니라 사용자 안내)
big = client.post("/api/apps/tok-guard/execute", json={"inputs": {"text": "가" * 8001}})
assert big.status_code == 422, big.text
assert "너무 깁니다" in big.json()["detail"]

# 3) 총합 상한(32,000자) 초과 → 422
bulk = client.post("/api/apps/tok-guard/execute",
                   json={"inputs": {f"k{i}": "가" * 7000 for i in range(5)}})
assert bulk.status_code == 422, bulk.text

# 4) 키 개수 상한(50개) 초과 → 422
keys = client.post("/api/apps/tok-guard/execute",
                   json={"inputs": {f"k{i}": "v" for i in range(51)}})
assert keys.status_code == 422, keys.text

# 5) /api/projects/{id}/run (앱 빌더 실행 경로)도 같은 상한을 쓴다
run_big = client.post(f"/api/projects/{project.id}/run", json={"inputs": {"text": "가" * 8001}})
assert run_big.status_code == 422, run_big.text

print("PUBLIC INPUT GUARD ALL OK")
'''


def test_public_input_guard_end_to_end(tmp_path):
    scenario_path = tmp_path / "guard_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'guard.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "PUBLIC INPUT GUARD ALL OK" in result.stdout
