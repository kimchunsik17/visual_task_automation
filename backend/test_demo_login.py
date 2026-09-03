"""시연장 로그인(/api/auth/demo)의 게이트·코드 검증·좌석 계정 검사."""

from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ.pop("DEMO_LOGIN_CODE", None)
os.environ.pop("DEMO_LOGIN_SEATS", None)
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

client = TestClient(main.app)
db = SessionLocal()

# 1) 기본 꺼짐 — 엔드포인트도 features 도 닫혀 있다
assert client.post("/api/auth/demo", json={"code": "x", "seat": 1}).status_code == 404
features = client.get("/api/features").json()
assert features["demo_login"] is False

# 2) 켜면 features 에 드러나고, 틀린 코드는 401
os.environ["DEMO_LOGIN_CODE"] = "booth-2026"
features = client.get("/api/features").json()
assert features["demo_login"] is True and features["demo_login_seats"] == 3
assert client.post("/api/auth/demo", json={"code": "wrong", "seat": 1}).status_code == 401

# 3) 좌석 범위 밖은 422
assert client.post("/api/auth/demo", json={"code": "booth-2026", "seat": 0}).status_code == 422
assert client.post("/api/auth/demo", json={"code": "booth-2026", "seat": 4}).status_code == 422

# 4) 맞는 코드 — 좌석 계정 생성 + JWT 발급, admin 아님
res = client.post("/api/auth/demo", json={"code": "booth-2026", "seat": 2})
assert res.status_code == 200, res.text
body = res.json()
assert body["access_token"] and body["user"]["is_admin"] is False
assert body["user"]["email"] == "booth2@demo.local"

# 발급된 토큰으로 인증이 실제로 통한다
me = client.get("/api/formats", headers={"Authorization": f"Bearer {body['access_token']}"})
assert me.status_code == 200, me.text

# 5) 같은 좌석 재로그인 — 같은 계정(작업물 유지)
res2 = client.post("/api/auth/demo", json={"code": "booth-2026", "seat": 2})
assert res2.json()["user"]["id"] == body["user"]["id"]
assert db.query(models.User).filter(models.User.google_id.like("demo-booth-%")).count() == 1

# 6) 좌석 수는 DEMO_LOGIN_SEATS 로 조절
os.environ["DEMO_LOGIN_SEATS"] = "5"
assert client.get("/api/features").json()["demo_login_seats"] == 5
assert client.post("/api/auth/demo", json={"code": "booth-2026", "seat": 5}).status_code == 200

print("DEMO LOGIN ALL OK")
'''


def test_demo_login_end_to_end(tmp_path):
    scenario_path = tmp_path / "demo_login_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'login.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "DEMO LOGIN ALL OK" in result.stdout
