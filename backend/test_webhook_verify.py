"""인바운드 웹훅 하드닝 — 서명 검증·크기 상한·분당 상한 (백로그 34 DEV-0, ADR-0031).

계약: (1) HMAC SHA-256 은 원문 바이트로 계산해 `sha256=<hex>`/`<hex>` 둘 다 받고 불일치·헤더 없음·비밀 없음은 실패 · (2) 고정 토큰은
compare_digest · (3) verifySecret 은 API 센터 참조만 — 원문을 넣으면 해석되지 않아 실패 · (4) 본문 크기 상한(WEBHOOK_MAX_BODY_BYTES) ·
(5) 엔드포인트별 분당 상한(rate_limit webhook.receive) · (6) 엔드포인트: 정상 200 / 서명 불일치 401(실행·기록 없음) / 재전송 duplicate /
상한 초과 413·429 — GitHub ping 모양 payload 로 · (7) dedupeHeader 가 idempotency 키를 우선한다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import idempotency
import models
import rate_limit
import webhook_verify as wv
from credential_crypto import encrypt_secret
from database import Base

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
SECRET = "s3cret-from-api-center"
BODY = json.dumps({"zen": "Keep it logically awesome.", "hook_id": 12345678, "repository": {"full_name": "acme/site"}},
                  ensure_ascii=False).encode("utf-8")


def sig(secret: str, body: bytes, prefix: bool = True) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}" if prefix else digest


def node(**data):
    return {"id": "w", "type": "webhookNode", "data": data}


# ── 1·2·3. 판정 ─────────────────────────────────────────────────────────────

def test_설정은_모드별_기본_헤더와_기본_참조를_채운다():
    assert wv.settings_from_node(None) == wv.VerifySettings("none", "", None, None)
    s = wv.settings_from_node(node(verifyMode="hmac_sha256"))
    assert (s.header, s.secret_ref) == ("X-Hub-Signature-256", "{{API_CENTER:webhook_secret}}")
    s = wv.settings_from_node(node(verifyMode="static_token", verifyHeader=" X-My-Token ", dedupeHeader="X-Delivery"))
    assert (s.header, s.dedupe_header) == ("X-My-Token", "X-Delivery")
    assert wv.settings_from_node(node(verifyMode="HMAC_SHA256")).mode == "hmac_sha256", "대소문자 무시"
    assert wv.settings_from_node(node(verifyMode="rot13")).mode == "none", "모르는 모드는 none"


def test_hmac_은_원문_바이트로_계산하고_접두사_유무를_모두_받는다():
    s = wv.settings_from_node(node(verifyMode="hmac_sha256"))
    assert wv.verify(s, {"X-Hub-Signature-256": sig(SECRET, BODY)}, BODY, SECRET).ok
    assert wv.verify(s, {"x-hub-signature-256": sig(SECRET, BODY, prefix=False).upper()}, BODY, SECRET).ok, "헤더 이름·hex 대소문자 무시"
    assert not wv.verify(s, {"X-Hub-Signature-256": sig(SECRET, BODY + b" ")}, BODY, SECRET).ok, "본문 한 바이트만 달라도 불일치"
    assert not wv.verify(s, {"X-Hub-Signature-256": sig("other", BODY)}, BODY, SECRET).ok
    missing = wv.verify(s, {}, BODY, SECRET)
    assert not missing.ok and "헤더" in missing.reason
    no_secret = wv.verify(s, {"X-Hub-Signature-256": sig(SECRET, BODY)}, BODY, None)
    assert not no_secret.ok and "secret" in no_secret.reason


def test_고정_토큰과_none_모드():
    s = wv.settings_from_node(node(verifyMode="static_token"))
    assert wv.verify(s, {"X-Gitlab-Token": SECRET}, b"", SECRET).ok
    assert not wv.verify(s, {"X-Gitlab-Token": SECRET + "x"}, b"", SECRET).ok
    assert wv.verify(wv.settings_from_node(node()), {}, b"", None).ok, "none 은 항상 통과(예전과 같다)"


def test_비밀은_API_센터_참조만_해석된다():
    assert wv.parse_secret_ref("{{API_CENTER:webhook_secret}}") == ("webhook_secret", None)
    assert wv.parse_secret_ref("{{API_CENTER:webhook_secret#42}}") == ("webhook_secret", 42)
    assert wv.parse_secret_ref("s3cret-in-plaintext") is None, "원문은 참조가 아니다 — graph 에 넣으면 검증이 실패한다"
    assert wv.parse_secret_ref("") is None and wv.parse_secret_ref(None) is None


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    db = make()
    db.add(models.User(id=1, name="Owner", email="owner@example.com", token_balance=1000))
    db.add(models.User(id=2, name="Other", email="other@example.com", token_balance=1000))
    db.add(models.UserApiKey(id=10, user_id=1, provider="webhook_secret", api_key=encrypt_secret("old")))
    db.add(models.UserApiKey(id=11, user_id=1, provider="webhook_secret", api_key=encrypt_secret(SECRET)))
    db.add(models.UserApiKey(id=12, user_id=2, provider="webhook_secret", api_key=encrypt_secret("theirs")))
    db.commit()
    db.close()
    yield make
    engine.dispose()


def test_resolve_secret_은_소유자의_키만_최신_것을_또는_id_로_고른다(factory):
    db = factory()
    assert wv.resolve_secret(db, 1, "{{API_CENTER:webhook_secret}}") == SECRET, "같은 provider 가 여럿이면 최신(id 큰) 것"
    assert wv.resolve_secret(db, 1, "{{API_CENTER:webhook_secret#10}}") == "old"
    assert wv.resolve_secret(db, 1, "{{API_CENTER:webhook_secret#12}}") is None, "남의 키 id 는 내 것으로 해석되지 않는다"
    assert wv.resolve_secret(db, 1, "{{API_CENTER:github}}") is None
    assert wv.resolve_secret(db, 1, SECRET) is None
    assert wv.resolve_secret(None, 1, "{{API_CENTER:webhook_secret}}") is None
    db.close()


# ── 4·5. 상한 ───────────────────────────────────────────────────────────────

def test_본문_크기_상한은_환경변수로_조정되고_바닥이_있다(monkeypatch):
    monkeypatch.delenv(wv.MAX_BODY_ENV, raising=False)
    assert wv.max_body_bytes() == wv.MAX_BODY_BYTES_DEFAULT
    assert not wv.body_too_large(b"x" * wv.MAX_BODY_BYTES_DEFAULT) and wv.body_too_large(b"x" * (wv.MAX_BODY_BYTES_DEFAULT + 1))
    monkeypatch.setenv(wv.MAX_BODY_ENV, "100")
    assert wv.max_body_bytes() == 1024, "1 KiB 아래로는 내리지 않는다"
    monkeypatch.setenv(wv.MAX_BODY_ENV, "4096")
    assert wv.body_too_large(b"x" * 4097) and not wv.body_too_large(None)
    monkeypatch.setenv(wv.MAX_BODY_ENV, "많이")
    assert wv.max_body_bytes() == wv.MAX_BODY_BYTES_DEFAULT


def test_엔드포인트별_분당_상한_규칙이_있고_환경변수로_조정된다(monkeypatch):
    rule = rate_limit.rule_for(wv.RATE_ACTION)
    assert rule.window_seconds == 60 and rule.limit >= 60
    monkeypatch.setenv("RATE_LIMIT_WEBHOOK_RECEIVE", "3")
    assert rate_limit.rule_for(wv.RATE_ACTION).limit == 3


def test_dedupeHeader_가_있으면_그_헤더가_idempotency_키를_우선한다():
    n = node(dedupeHeader="X-My-Delivery")
    assert idempotency.webhook_key(7, {"X-My-Delivery": "abc", "X-GitHub-Delivery": "gh-1"}, {}, node=n) == "webhook:7:x-my-delivery:abc"
    assert idempotency.webhook_key(7, {"X-GitHub-Delivery": "gh-1"}, {}, node=n) == "webhook:7:x-github-delivery:gh-1", "없으면 기본 헤더로"


# ── 6. 엔드포인트 ───────────────────────────────────────────────────────────

SCENARIO = r'''
import os, sys, json, hmac, hashlib
os.environ["DATABASE_URL"] = sys.argv[1]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER",
          "OPENROUTER_BASE_URL", "PICKLE_API_KEY", "EXECUTION_QUEUE", "EXECUTION_WORKER_INPROCESS"):
    os.environ[k] = ""
os.environ["RATE_LIMIT_WEBHOOK_RECEIVE"] = "6"
os.environ["WEBHOOK_MAX_BODY_BYTES"] = "2048"
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models
from credential_crypto import encrypt_secret
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
SECRET = "s3cret-from-api-center"
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
db.add(owner); db.commit()
db.add(models.UserApiKey(user_id=owner.id, provider="webhook_secret", api_key=encrypt_secret(SECRET))); db.commit()
def project(title, **wdata):
    p = models.Project(user_id=owner.id, title=title, graph_data={"is_live": True,
        "nodes": [{"id": "w", "type": "webhookNode", "data": wdata}, {"id": "o", "type": "outputNode", "data": {}}],
        "edges": [{"source": "w", "target": "o"}]})
    db.add(p); db.commit(); return p
github = project("GitHub", verifyMode="hmac_sha256")
gitlab = project("GitLab", verifyMode="static_token", verifyHeader="X-Gitlab-Token")
custom = project("custom dedupe", dedupeHeader="X-My-Delivery")
runs = lambda pid: db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == pid).count()
logs = lambda pid: db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == pid).count()
JSON = {"Content-Type": "application/json"}
ping = json.dumps({"zen": "Keep it logically awesome.", "hook_id": 12345678, "hook": {"type": "Repository", "id": 12345678, "events": ["push"]},
                   "repository": {"id": 1296269, "full_name": "acme/site"}, "sender": {"login": "octocat"}}, ensure_ascii=False).encode("utf-8")
sig = lambda body, secret=SECRET: "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

# 정상: 올바른 서명 → 200 실행
r = client.post(f"/webhook/{github.id}", content=ping, headers={**JSON, "X-Hub-Signature-256": sig(ping), "X-GitHub-Delivery": "d-1"})
assert r.status_code == 200 and r.json()["status"] == "success", r.text
db.expire_all(); assert runs(github.id) == 1 and logs(github.id) == 1

# 서명 불일치·헤더 없음·다른 비밀 → 401, 실행·기록 없음, 응답에 사유 없음
for headers in ({"X-Hub-Signature-256": sig(ping, "wrong")}, {}, {"X-Hub-Signature-256": "sha256=deadbeef"}):
    r = client.post(f"/webhook/{github.id}", content=ping, headers={**JSON, **headers, "X-GitHub-Delivery": "d-x"})
    assert r.status_code == 401, r.text
    assert "불일치" not in r.text and "secret" not in r.text.lower(), "사유는 로그에만"
db.expire_all(); assert runs(github.id) == 1 and logs(github.id) == 1

# 본문 한 바이트를 바꾼 재전송(변조) → 401 · 같은 전달 id 정상 재전송 → duplicate
tampered = ping[:-1] + b" }"
assert client.post(f"/webhook/{github.id}", content=tampered, headers={**JSON, "X-Hub-Signature-256": sig(ping), "X-GitHub-Delivery": "d-2"}).status_code == 401
again = client.post(f"/webhook/{github.id}", content=ping, headers={**JSON, "X-Hub-Signature-256": sig(ping), "X-GitHub-Delivery": "d-1"})
assert again.status_code == 200 and again.json()["status"] == "duplicate", again.text
db.expire_all(); assert runs(github.id) == 1

# 고정 토큰(GitLab)
assert client.post(f"/webhook/{gitlab.id}", json={"object_kind": "push"}, headers={"X-Gitlab-Token": SECRET}).status_code == 200
assert client.post(f"/webhook/{gitlab.id}", json={"object_kind": "push"}, headers={"X-Gitlab-Token": "nope"}).status_code == 401
assert client.post(f"/webhook/{gitlab.id}", json={"object_kind": "push"}).status_code == 401

# 본문 크기 상한(2048B) → 413, 실행 없음
big = json.dumps({"pad": "x" * 3000}).encode()
r = client.post(f"/webhook/{gitlab.id}", content=big, headers={**JSON, "X-Gitlab-Token": SECRET})
assert r.status_code == 413, r.text

# dedupeHeader 우선: 같은 X-My-Delivery 는 duplicate, 다른 값은 새 실행
a = client.post(f"/webhook/{custom.id}", json={"n": 1}, headers={"X-My-Delivery": "m-1"})
b = client.post(f"/webhook/{custom.id}", json={"n": 2}, headers={"X-My-Delivery": "m-1"})
c = client.post(f"/webhook/{custom.id}", json={"n": 3}, headers={"X-My-Delivery": "m-2"})
assert (a.json()["status"], b.json()["status"], c.json()["status"]) == ("success", "duplicate", "success"), (a.text, b.text, c.text)

# 분당 상한(6/min, 엔드포인트별): gitlab 은 위에서 3번 세어졌다(413 은 상한 카운터보다 앞이라 세지 않는다) → 3번 더 200, 7번째는
# 429 + Retry-After. 다른 엔드포인트는 영향 없음
codes = [client.post(f"/webhook/{gitlab.id}", json={"i": i}, headers={"X-Gitlab-Token": SECRET}).status_code for i in range(3)]
assert codes == [200, 200, 200], codes
r = client.post(f"/webhook/{gitlab.id}", json={"i": 9}, headers={"X-Gitlab-Token": SECRET})
assert r.status_code == 429 and r.headers.get("retry-after"), r.headers
assert client.post(f"/webhook/{custom.id}", json={"n": 4}, headers={"X-My-Delivery": "m-3"}).status_code == 200
print("WEBHOOK VERIFY OK")
'''


def test_webhook_endpoint_hardening_end_to_end(tmp_path):
    scenario_path = tmp_path / "webhook_verify_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'verify.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout[-3000:]}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "WEBHOOK VERIFY OK" in result.stdout
