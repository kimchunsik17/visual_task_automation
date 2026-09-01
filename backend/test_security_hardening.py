import io

import pytest
from fastapi import HTTPException, UploadFile

from credential_crypto import (
    CredentialDecryptionError,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
)
from upload_security import save_upload_limited, validate_filename
from workflow_security import (
    WorkflowSecurityError,
    validate_python_node_code,
    validate_workflow_graph,
)


def test_credentials_are_encrypted_and_authenticated(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "test-only-encryption-key")
    plaintext = "sk-secret-value"

    encrypted = encrypt_secret(plaintext)

    assert encrypted != plaintext
    assert is_encrypted(encrypted)
    assert decrypt_secret(encrypted) == plaintext

    tampered = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")
    with pytest.raises(CredentialDecryptionError):
        decrypt_secret(tampered)


def test_legacy_plaintext_credentials_remain_readable(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "test-only-encryption-key")
    assert decrypt_secret("legacy-secret") == "legacy-secret"


def test_filename_validation_uses_whitelist_and_strips_windows_paths():
    assert validate_filename(r"..\folder\report.PDF", {".pdf"}) == ("report.PDF", ".pdf")
    with pytest.raises(HTTPException) as exc_info:
        validate_filename("payload.sh", {".pdf"})
    assert exc_info.value.status_code == 415


@pytest.mark.asyncio
async def test_limited_upload_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    upload = UploadFile(filename="report.pdf", file=io.BytesIO(b"too large"))

    with pytest.raises(HTTPException) as exc_info:
        await save_upload_limited(upload, allowed_extensions={".pdf"}, max_bytes=3)

    assert exc_info.value.status_code == 413
    assert list((tmp_path / "uploads").iterdir()) == []


def test_python_node_allows_data_transforms_but_blocks_system_access():
    validate_python_node_code(
        "lines = [line for line in str(input_data).split(chr(10)) if line.strip()]\n"
        "output_data = chr(10).join(lines)"
    )

    with pytest.raises(WorkflowSecurityError, match="Import"):
        validate_python_node_code("import os\noutput_data = os.listdir('/')")
    with pytest.raises(WorkflowSecurityError):
        validate_python_node_code("output_data = input_data.__class__.__mro__")


def test_workflow_rejects_source_injection_in_node_id():
    nodes = [{"id": "n1'); __import__('os').system('id'); #", "type": "startNode", "data": {}}]
    with pytest.raises(WorkflowSecurityError, match="unsafe node id"):
        validate_workflow_graph(nodes, [])


# ── 인증 경계 (2026-08-29 정리) ──────────────────────────────────────────
AUTH_SCENARIO = '''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
db.add(models.User(id=1, google_id="g1", email="o@e.st", name="owner"))
db.commit()
client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

# 사용자가 반드시 있어야 하는 경로는 비로그인 시 401 이어야 한다.
# 예전에는 선택적 인증(get_current_user)을 쓰면서 user.id 를 그대로 읽어 500 이 났고,
# 프론트가 주기적으로 부르는 /api/approvals/count 가 매번 서버 오류로 기록됐다.
for path in ["/api/approvals/count", "/api/approvals", "/api/credential-providers", "/api/approvals/abc"]:
    res = client.get(path)
    check(f"{path} 는 비로그인 401", res.status_code == 401, f"{res.status_code} {res.text[:120]}")

res = client.post("/api/approvals/abc/decide", json={"decision": "approve"})
check("결정 API 도 비로그인 401", res.status_code == 401, res.text[:120])

# 'dev-mock-token' 백도어가 사라졌는지 — 이 문자열 하나로 더미 유저 인증이 통과되면 안 된다.
res = client.get("/api/approvals/count", headers={"Authorization": "Bearer dev-mock-token"})
check("dev-mock-token 은 더 이상 인증을 통과하지 못한다", res.status_code == 401, f"{res.status_code} {res.text[:120]}")
check("백도어 유저가 만들어지지 않았다", db.query(models.User).filter(models.User.id == 9999).first() is None)

# 정상 토큰은 그대로 통과한다.
import jwt as _jwt
token = _jwt.encode({"user_id": 1}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
res = client.get("/api/approvals/count", headers={"Authorization": f"Bearer {token}"})
check("정상 토큰은 통과한다", res.status_code == 200 and res.json()["count"] == 0, res.text[:120])

print("ALL OK")
'''


def test_인증이_필요한_경로는_500이_아니라_401을_돌려준다(tmp_path):
    import pathlib
    import subprocess
    import sys

    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")
    scenario = tmp_path / "auth_scenario.py"
    scenario.write_text(AUTH_SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()
    backend_dir = pathlib.Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'auth.db'}", str(backend_dir)],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout


@pytest.mark.skipif(
    not __import__("os").path.exists(
        __import__("os").path.join(
            __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))),
            "frontend", "dist")),
    reason="frontend/dist 가 없으면 catch-all 라우트 자체가 등록되지 않는다 (npm run build 필요)")
def test_unknown_api_routes_return_json_404_not_the_spa_shell():
    """없는 /api/ 경로가 index.html 200 으로 위장되지 않는다.

    catch-all(`@app.get("/{full_path:path}")`)이 모든 미매치 GET 에 index.html 을 돌려주는
    바람에, 배포 반영 실패와 오타 난 라우트가 '200 text/html' 로 보였다. 그러면 개발자가
    백엔드가 아니라 프론트부터 뒤진다 — 이 저장소의 실제 재발 이력이다.

    SPA 라우팅(/editor/123 등)은 그대로 index.html 을 받아야 하므로 함께 확인한다.
    """
    import os as _os
    _os.environ.setdefault("DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)

    r = client.get("/api/no-such-route-xyz")
    assert r.status_code == 404, f"없는 API 경로가 {r.status_code} 를 돌려줬다"
    assert r.headers["content-type"].startswith("application/json")

    spa = client.get("/editor/123")
    assert spa.status_code == 200 and spa.headers["content-type"].startswith("text/html"), \
        "SPA 라우팅이 깨졌다 — catch-all 이 index.html 을 내야 한다"
