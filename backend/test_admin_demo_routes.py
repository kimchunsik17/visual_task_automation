"""어드민 시연 관리 라우트 배선(main.py) — 요청 모델·관리자 의존성·설정 저장이 실제 앱에서 돈다."""
from __future__ import annotations
import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
SCENARIO = r'''
import os, sys, json
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ["DEMO_RUNTIME_SETTINGS_PATH"] = sys.argv[3]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES"):
    os.environ[k] = ""
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
admin = models.User(google_id="g-admin", email="admin@example.com", name="관리자", role="admin")
db.add(admin); db.commit()
import datetime as _dt
tok = main.jwt.encode({"user_id": admin.id, "email": admin.email, "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1)}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
hdr = {"Authorization": f"Bearer {tok}"}
# 1) 게스트 없이도 개요가 나온다 / 비관리자는 막힌다
ov = client.get("/api/admin/demo/overview", headers=hdr); assert ov.status_code == 200, ov.text
assert ov.json()["guests"]["count"] == 0 and ov.json()["settings"]["effective"]["DEMO_GUEST"] is False
assert client.get("/api/admin/demo/overview").status_code in (401, 403)
# 2) 설정 저장 → features 가 즉시 바뀐다(재기동 없이) → reset 으로 .env 복귀
assert client.get("/api/features").json()["demo_guest"] is False
put = client.put("/api/admin/demo/settings", json={"DEMO_GUEST": True, "DEMO_UI": True, "HIDDEN_NODE_TYPES": ["tossNode"], "DEMO_GUEST_TOKENS": 120000}, headers=hdr)
assert put.status_code == 200, put.text
feat = client.get("/api/features").json()
assert feat["demo_guest"] is True and feat["demo_ui"] is True and feat["hidden_nodes"] == ["tossNode"]
bad = client.put("/api/admin/demo/settings", json={"DEMO_GUEST_TOKENS": 5}, headers=hdr); assert bad.status_code == 422
# 3) 켜진 상태에서 게스트 입장 → 토큰 120000, 입장 이벤트 → 개요·목록·정리
g = client.post("/api/auth/guest"); assert g.status_code == 200, g.text
assert g.json()["user"]["id"] and db.query(models.User).get(g.json()["user"]["id"]).token_balance == 120000
ov = client.get("/api/admin/demo/overview", headers=hdr).json()
assert ov["guests"]["count"] == 1 and ov["guests"]["entries_today"] == 1
assert client.get("/api/admin/demo/guests", headers=hdr).json()["guests"][0]["registered"] is False
assert client.get("/api/admin/demo/runs?limit=5", headers=hdr).status_code == 200
res = client.post("/api/admin/demo/guests/cleanup", json={"keep_active_minutes": 0}, headers=hdr); assert res.status_code == 200, res.text
assert res.json()["deleted"] == 1 and res.json()["remaining"] == 0
# 4) reset → .env(비어 있음) 로 복귀
assert client.put("/api/admin/demo/settings", json={"reset": ["DEMO_GUEST", "DEMO_UI", "HIDDEN_NODE_TYPES", "DEMO_GUEST_TOKENS"]}, headers=hdr).status_code == 200
assert client.get("/api/features").json()["demo_guest"] is False
print("ADMIN DEMO ROUTES OK")
'''


def test_admin_demo_routes_end_to_end(tmp_path):
    scenario_path = tmp_path / "admin_demo_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'admin.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR), str(tmp_path / "demo_settings.json")],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ADMIN DEMO ROUTES OK" in result.stdout
