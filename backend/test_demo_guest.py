"""시연 게스트 입장(/api/auth/guest)의 게이트·토큰 상한·콘텐츠 복사·정원 검사."""

from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
# 빈 문자열 대입 — pop 하면 main 의 load_dotenv 가 로컬 .env 의 시연 플래그를 다시 채운다
# (conftest 의 시연 플래그 중화와 같은 원리).
os.environ["DEMO_GUEST"] = ""
os.environ["DEMO_GUEST_TOKENS"] = ""
os.environ["DEMO_GUEST_MAX"] = ""
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

client = TestClient(main.app)
db = SessionLocal()

# 1) 기본 꺼짐 — 엔드포인트도 features 도 닫혀 있다
assert client.post("/api/auth/guest").status_code == 404
assert client.get("/api/features").json()["demo_guest"] is False

# 2) 켜면 게스트 계정이 만들어지고, 토큰 상한이 걸린 일반 사용자다(admin 아님)
os.environ["DEMO_GUEST"] = "1"
os.environ["DEMO_GUEST_TOKENS"] = "12345"
assert client.get("/api/features").json()["demo_guest"] is True
res = client.post("/api/auth/guest")
assert res.status_code == 200, res.text
body = res.json()
assert body["access_token"] and body["user"]["is_admin"] is False
uid = body["user"]["id"]
guest = db.query(models.User).get(uid)
assert guest.google_id.startswith("demo-guest-")
assert guest.email.endswith("@demo.local")
assert guest.token_balance == 12345, guest.token_balance

# 3) 시연 콘텐츠가 게스트 계정으로 복사된다 — 워크플로우 5종 + 앱 2종 + 전용 포맷 2종,
#    포맷 id 는 소유자별(-u<id>)이고 워크플로우의 formatNode 가 그 id 를 가리킨다
projects = db.query(models.Project).filter(models.Project.user_id == uid).all()
assert len(projects) == 5 and all(p.title.startswith("[시연] ") for p in projects)
assert db.query(models.CustomApp).filter(models.CustomApp.owner_id == uid).count() == 2
fmt_ids = {f.id for f in db.query(models.DocumentFormat)
           .filter(models.DocumentFormat.owner_user_id == uid).all()}
assert fmt_ids == {f"demo-travel-itinerary-u{uid}", f"demo-notice-poster-u{uid}"}, fmt_ids
poster_flow = next(p for p in projects if "포스터" in p.title)
poster_node = next(n for n in poster_flow.graph_data["nodes"] if n["type"] == "formatNode")
assert poster_node["data"]["formatId"] == f"demo-notice-poster-u{uid}"

# 4) 발급 토큰으로 인증이 실제로 통한다
me = client.get("/api/formats", headers={"Authorization": f"Bearer {body['access_token']}"})
assert me.status_code == 200, me.text
assert len(me.json()["formats"]) == 2

# 5) 게스트마다 별도 계정 — 서로의 콘텐츠·토큰이 섞이지 않는다
res2 = client.post("/api/auth/guest")
uid2 = res2.json()["user"]["id"]
assert uid2 != uid
assert db.query(models.Project).filter(models.Project.user_id == uid2).count() == 5

# 6) 정원 상한 — 초과하면 429 (인증 없는 입구의 행 폭주 방어)
os.environ["DEMO_GUEST_MAX"] = "2"
too_many = client.post("/api/auth/guest")
assert too_many.status_code == 429, too_many.text

print("DEMO GUEST ALL OK")
'''


def test_demo_guest_end_to_end(tmp_path):
    scenario_path = tmp_path / "demo_guest_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'guest.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "DEMO GUEST ALL OK" in result.stdout
