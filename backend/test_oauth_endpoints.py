"""OAuth 엔드포인트의 HTTP 경계 (한국형 노드 계획 Phase 0).

흐름 자체는 `test_oauth_flow.py` 가 본다. 여기서 확인하는 것은 HTTP 표면의 두 가지다.

  1. **시작·해제는 sudo 토큰이 필요하고, 콜백은 공개다.** 콜백이 공개인 건 실수가 아니라
     필수다 — provider 가 브라우저를 그리로 보낼 때 Authorization 헤더가 없다. 대신 "누구의
     토큰인가"를 세션이 아니라 state 가 정한다.
  2. **어떤 실패도 사용자를 사이트 밖으로 보내지 않는다.** 이 엔드포인트가 열린 리다이렉터가
     되면 피싱에 쓰인다.

`main` 을 임포트하면 시작 시 마이그레이션이 도는 탓에 운영 DB 를 건드린다. 그래서 다른 HTTP
테스트와 같이 임시 SQLite 를 가리키는 하위 프로세스에서 돌린다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

SCENARIO = '''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ["OAUTH_REDIRECT_BASE_URL"] = "https://wa-pnu.duckdns.org"
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from credential_crypto import encrypt_secret, decrypt_secret
from database import SessionLocal
from connectors import oauth_flow

db = SessionLocal()
user = models.User(id=1, google_id="g1", email="o@e.st", name="owner")
db.add(user)
db.add(models.UserApiKey(user_id=1, provider="naver_oauth_client",
                         api_key=encrypt_secret("cid:csecret")))
db.commit()
client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

P = "naver_user_oauth"

# ── 1. 시작·해제는 sudo 토큰이 필요하다 ────────────────────────────────
res = client.post(f"/api/oauth/{P}/start", json={})
check("start 는 비로그인 401", res.status_code == 401, f"{res.status_code} {res.text[:150]}")
res = client.delete(f"/api/oauth/{P}")
check("revoke 는 비로그인 401", res.status_code == 401, f"{res.status_code} {res.text[:150]}")

# ── 2. 콜백은 공개다 — 인증 없이도 401 이 아니라 리다이렉트한다 ────────
res = client.get(f"/api/oauth/{P}/callback?error=access_denied", follow_redirects=False)
check("동의 거부는 401 이 아니라 리다이렉트", res.status_code == 303, f"{res.status_code}")
check("거부 사유를 우리 화면으로 전달", "oauth_error=denied" in res.headers["location"],
      res.headers["location"])
check("거부해도 사이트 안에 머문다", res.headers["location"].startswith("/api-center"),
      res.headers["location"])

res = client.get(f"/api/oauth/{P}/callback?code=x&state=지어낸값", follow_redirects=False)
check("모르는 state 는 리다이렉트로 끝난다", res.status_code == 303, f"{res.status_code}")
check("state 실패 사유가 붙는다", "oauth_error=STATE_UNKNOWN" in res.headers["location"],
      res.headers["location"])
check("실패해도 사이트 안에 머문다", res.headers["location"].startswith("/api-center"),
      res.headers["location"])
check("토큰이 저장되지 않았다",
      db.query(models.UserApiKey).filter_by(user_id=1, provider=P).first() is None)

# ── 3. sudo 로 시작하면 동의 URL 과 등록할 콜백 주소를 준다 ────────────
main.app.dependency_overrides[main.get_sudo_user] = lambda: user
res = client.post(f"/api/oauth/{P}/start", json={"return_to": "/api-center"})
check("start 200", res.status_code == 200, f"{res.status_code} {res.text[:200]}")
body = res.json()
check("동의 URL 이 네이버로 간다", body["url"].startswith("https://nid.naver.com/oauth2.0/authorize"),
      body["url"][:80])
check("콘솔에 등록할 콜백 주소를 알려준다",
      body["callback_url"] == f"https://wa-pnu.duckdns.org/api/oauth/{P}/callback",
      body["callback_url"])
check("client_secret 이 URL 에 없다", "csecret" not in body["url"])

# ── 4. 사이트 밖으로 돌아가는 return_to 는 시작 단계에서 거부한다 ──────
res = client.post(f"/api/oauth/{P}/start", json={"return_to": "https://evil.example.com"})
check("외부 return_to 는 400", res.status_code == 400, f"{res.status_code} {res.text[:150]}")
check("거부 사유를 알려준다", "BAD_RETURN_TO" in res.text, res.text[:200])

# ── 5. 실제 왕복: 토큰 endpoint 만 가짜로 두고 끝까지 돌린다 ───────────
import requests

class _Resp:
    status_code = 200
    text = ""
    def json(self):
        return {"access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 3600}

requests.post = lambda *a, **k: _Resp()

state = db.query(models.OAuthState).filter_by(provider=P, consumed_at=None).first().state
res = client.get(f"/api/oauth/{P}/callback?code=CODE&state={state}", follow_redirects=False)
check("성공하면 303", res.status_code == 303, f"{res.status_code} {res.text[:200]}")
check("start 때 준 return_to 로 돌아간다", res.headers["location"].startswith("/api-center"),
      res.headers["location"])
check("연결됐다고 알려준다", f"connected={P}" in res.headers["location"], res.headers["location"])

row = db.query(models.UserApiKey).filter_by(user_id=1, provider=P).first()
check("토큰이 저장됐다", row is not None)
check("평문으로 저장되지 않았다", row.api_key != "AT-1")
check("복호화하면 받은 값이다", decrypt_secret(row.api_key) == "AT-1")
check("refresh_token 도 저장됐다", decrypt_secret(row.refresh_token) == "RT-1")

# ── 6. 같은 콜백을 다시 열어도 재사용되지 않는다 ───────────────────────
res = client.get(f"/api/oauth/{P}/callback?code=CODE&state={state}", follow_redirects=False)
check("재사용은 리다이렉트로 거부", res.status_code == 303, f"{res.status_code}")
check("재사용 사유가 붙는다",
      "oauth_error=STATE_" in res.headers["location"], res.headers["location"])

# ── 7. provider 목록이 등록할 콜백 주소를 함께 준다 ────────────────────
main.app.dependency_overrides[main.get_current_user_required] = lambda: user
res = client.get("/api/credential-providers")
check("provider 목록 200", res.status_code == 200, f"{res.status_code}")
entries = {p["id"]: p for p in res.json()["providers"]}
check("동의형 provider 는 callback_url 을 준다", "callback_url" in entries[P], list(entries[P]))
check("동의형이 아닌 provider 에는 없다", "callback_url" not in entries["openai"])
check("비밀값은 목록에 없다", "csecret" not in res.text)

# ── 8. 해제하면 사라진다 ───────────────────────────────────────────────
res = client.delete(f"/api/oauth/{P}")
check("revoke 200", res.status_code == 200, f"{res.status_code} {res.text[:150]}")
db.expire_all()
check("토큰이 지워졌다",
      db.query(models.UserApiKey).filter_by(user_id=1, provider=P).first() is None)

print("ALL OK")
'''


def test_oauth_엔드포인트_경계(tmp_path):
    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")
    scenario = tmp_path / "oauth_scenario.py"
    scenario.write_text(SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()
    backend_dir = pathlib.Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'oauth.db'}", str(backend_dir)],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout
