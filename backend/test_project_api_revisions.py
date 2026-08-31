"""저장 충돌(409)과 버전 되돌리기를 HTTP 수준에서 확인한다 (ADR-0006).

이 시나리오는 별도 프로세스에서 돌린다. `main` 을 임포트하면 그 시점의 DATABASE_URL 로
마이그레이션이 실행되는데, 같은 파이썬 프로세스에서 다른 테스트가 이미 `database` 를
임포트했을 수 있어서 어떤 DB 를 향할지 장담할 수 없다 — 개발자의 실제 DB 에 마이그레이션이
도는 사고를 막기 위해, 임시 sqlite 를 지정한 깨끗한 인터프리터에서 실행한다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

SCENARIO = '''
import json, os, sys

os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
user = models.User(id=1, google_id="g1", email="t@e.st", name="tester")
db.add(user)
db.commit()

# TestClient 를 컨텍스트 매니저로 쓰지 않으므로 startup 이벤트(스케줄러/봇)는 돌지 않는다.
main.app.dependency_overrides[main.get_current_user_required] = lambda: user
main.app.dependency_overrides[main.get_current_user] = lambda: user
client = TestClient(main.app)


def graph(*node_ids):
    return {
        "nodes": [{"id": n, "type": "llmNode", "position": {"x": 0, "y": 0}, "data": {}} for n in node_ids],
        "edges": [],
    }


def check(label, condition, extra=""):
    if not condition:
        print(f"FAIL: {label} {extra}")
        sys.exit(1)
    print(f"ok: {label}")


# ── 생성은 revision 1 을 남긴다 ──
created = client.post("/api/projects", json={"title": "W", "graph_data": graph("n1")})
check("생성 200", created.status_code == 200, created.text)
project_id = created.json()["id"]
check("생성 시 revision 1", created.json()["current_revision"] == 1, created.text)

# ── 조회는 current_revision 을 알려준다 ──
fetched = client.get(f"/api/projects/{project_id}")
check("조회가 current_revision 반환", fetched.json()["current_revision"] == 1, fetched.text)

# ── 정상 저장은 revision 을 올린다 ──
saved = client.put(f"/api/projects/{project_id}", json={"title": "W", "graph_data": graph("n1", "n2"), "base_revision": 1})
check("저장 200", saved.status_code == 200, saved.text)
check("저장 후 revision 2", saved.json()["current_revision"] == 2, saved.text)

# ── 낡은 base_revision 은 덮어쓰지 않고 409 ──
stale = client.put(f"/api/projects/{project_id}", json={"title": "W", "graph_data": graph("n1", "n9"), "base_revision": 1})
check("낡은 저장은 409", stale.status_code == 409, stale.text)
detail = stale.json()["detail"]
check("충돌 코드", detail["code"] == "REVISION_CONFLICT", json.dumps(detail))
check("서버 변경 diff", detail["server_changes_since_base"]["nodes"]["added"] == ["n2"], json.dumps(detail))
check("내 변경 diff", detail["my_changes_since_base"]["nodes"]["added"] == ["n9"], json.dumps(detail))

# ── 409 이후에도 서버 상태는 그대로여야 한다(덮어쓰기가 일어나지 않았는지) ──
after_conflict = client.get(f"/api/projects/{project_id}")
node_ids = [n["id"] for n in after_conflict.json()["graph_data"]["nodes"]]
check("409 뒤 서버 그래프 보존", node_ids == ["n1", "n2"], str(node_ids))

# ── 사용자가 덮어쓰기를 선택하면 저장된다 ──
forced = client.put(f"/api/projects/{project_id}", json={"title": "W", "graph_data": graph("n1", "n9"), "base_revision": 1, "force_overwrite": True})
check("덮어쓰기 200", forced.status_code == 200, forced.text)
check("덮어쓰기 후 revision 3", forced.json()["current_revision"] == 3, forced.text)

# ── base_revision 을 안 보내는 예전 클라이언트는 그대로 동작한다 ──
legacy = client.put(f"/api/projects/{project_id}", json={"title": "W", "graph_data": graph("n1")})
check("base_revision 없는 저장 200", legacy.status_code == 200, legacy.text)

# ── 이력 조회 ──
history = client.get(f"/api/projects/{project_id}/revisions")
revisions = history.json()["revisions"]
check("이력 4건", [r["revision"] for r in revisions] == [4, 3, 2, 1], json.dumps(revisions))

snapshot = client.get(f"/api/projects/{project_id}/revisions/2")
snapshot_nodes = [n["id"] for n in snapshot.json()["revision"]["graph_data"]["nodes"]]
check("스냅샷 2번 내용", snapshot_nodes == ["n1", "n2"], str(snapshot_nodes))

diff = client.get(f"/api/projects/{project_id}/revisions/2/diff", params={"against": 3})
check("diff 엔드포인트", diff.json()["diff"]["nodes"] == {"added": ["n9"], "removed": ["n2"], "changed": []}, diff.text)

# ── 되돌리기도 새 revision 으로 남는다 ──
restored = client.post(f"/api/projects/{project_id}/revisions/2/restore")
check("되돌리기 200", restored.status_code == 200, restored.text)
check("되돌린 뒤 revision 5", restored.json()["current_revision"] == 5, restored.text)
restored_nodes = [n["id"] for n in restored.json()["graph_data"]["nodes"]]
check("되돌린 내용", restored_nodes == ["n1", "n2"], str(restored_nodes))

# ── 남의 프로젝트 이력은 볼 수 없다 ──
other = models.User(id=2, google_id="g2", email="o@e.st", name="other")
db.add(other)
db.commit()
main.app.dependency_overrides[main.get_current_user_required] = lambda: other
forbidden = client.get(f"/api/projects/{project_id}/revisions")
check("타인의 이력은 403", forbidden.status_code == 403, forbidden.text)

print("ALL OK")
'''


def test_save_conflict_and_revision_history(tmp_path):
    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")

    scenario_path = tmp_path / "scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'api.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout
