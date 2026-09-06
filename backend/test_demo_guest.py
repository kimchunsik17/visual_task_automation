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

# 7) 최초 1회 프로필 등록 — 실제 이메일 + '(시연용)이름'. 잘못된 주소·임시 도메인은 422
hdr = {"Authorization": f"Bearer {body['access_token']}"}
assert client.post("/api/auth/guest/profile", json={"email": "not-an-email"}, headers=hdr).status_code == 422
assert client.post("/api/auth/guest/profile", json={"email": "x@demo.local"}, headers=hdr).status_code == 422
ok = client.post("/api/auth/guest/profile", json={"email": "visitor@example.com", "name": "홍길동"}, headers=hdr)
assert ok.status_code == 200, ok.text
assert ok.json()["user"]["name"] == "(시연용)홍길동" and ok.json()["user"]["email"] == "visitor@example.com"
db.expire_all()
assert db.query(models.User).get(uid).email == "visitor@example.com"
# 이름을 비우면 이메일 앞부분을 쓴다 (다시 호출 = 수정)
ok2 = client.post("/api/auth/guest/profile", json={"email": "jane@example.com", "name": ""}, headers=hdr)
assert ok2.status_code == 200 and ok2.json()["user"]["name"] == "(시연용)jane"
# 8) 복사된 이메일 노드의 수신자는 자리표시자다 — 등록한 이메일로 발송 직전에 풀린다
from seed_demo_booth import USER_EMAIL_PLACEHOLDER
mail_nodes = [n for p in db.query(models.Project).filter(models.Project.user_id == uid).all()
              for n in p.graph_data["nodes"] if n["type"] == "emailNode"]
assert mail_nodes and all(n["data"]["toEmail"] == USER_EMAIL_PLACEHOLDER for n in mail_nodes)
# 9) 시연 콘텐츠 5종을 받은 뒤에도 게스트는 자기 워크플로우를 만들 수 있다 — 상한 셈에서 [시연] 접두 제외
made = client.post("/api/projects", json={"title": "내 첫 워크플로우", "description": "테스트",
                                          "graph_data": {"nodes": [{"id": "s", "type": "startNode", "data": {}, "position": {"x": 0, "y": 0}}], "edges": []}},
                   headers=hdr)
assert made.status_code == 200, made.text
# 상한 자체는 살아 있다 — 시연 콘텐츠를 뺀 수동 워크플로우가 MAX_MANUAL_WORKFLOWS(기본 5)에 닿으면 400
for i in range(4):
    assert client.post("/api/projects", json={"title": f"wf{i}", "description": "t", "graph_data": {"nodes": [], "edges": []}}, headers=hdr).status_code == 200
capped = client.post("/api/projects", json={"title": "wf-over", "description": "t", "graph_data": {"nodes": [], "edges": []}}, headers=hdr)
assert capped.status_code == 400 and "최대 5개" in capped.json()["detail"], capped.text
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
