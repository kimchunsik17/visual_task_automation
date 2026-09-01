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


def test_missing_api_routes_are_404_for_every_method():
    """GET 만 고치면 반쪽이다. dist 가 있을 때 `GET /{full_path:path}` catch-all 이 /api 경로를
    잡아버려, POST 는 '경로는 매칭됐는데 메서드가 없다' 가 되어 405 로 나갔다. 배포에서
    라우트가 빠졌을 때 405 는 "있는데 메서드가 틀렸나?" 로 읽혀 추적을 엉뚱한 데로 보낸다."""
    import os as _os
    _os.environ.setdefault("DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app, raise_server_exceptions=False)
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        r = client.request(method, "/api/no-such-route-xyz")
        assert r.status_code == 404, f"{method} 가 {r.status_code} 를 돌려줬다"
        assert r.headers["content-type"].startswith("application/json")


def test_wrong_method_on_a_real_api_route_still_says_405():
    """없는 경로를 404 로 바꾸면서 진짜 405 까지 뭉개면 API 계약이 나빠진다 — 라우트가
    실재하는데 메서드만 다른 경우는 405 와 Allow 헤더가 정확한 답이다."""
    import os as _os
    _os.environ.setdefault("DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app, raise_server_exceptions=False)

    r = client.request("POST", "/api/features")          # GET 전용 라우트
    assert r.status_code == 405, r.text
    assert "GET" in (r.headers.get("Allow") or "")

    r = client.request("GET", "/api/auth/google")        # POST 전용 라우트
    assert r.status_code == 405, r.text
    assert "POST" in (r.headers.get("Allow") or "")


# ── httpRequestNode SSRF (url_guard 배선) ──────────────────────────────────
# 이 노드는 저장소에서 유일하게 목적지가 자유롭다 — URL 을 사용자·LLM 이 정한다.
# 정책(url_guard)은 webCrawlerNode 에서 이미 돌고 있었는데 이쪽만 배선이 빠져 있었다.

def _http_definition():
    import node_definition
    return node_definition.get_definition("httpRequestNode")


@pytest.mark.parametrize("url,label", [
    ("http://169.254.169.254/latest/meta-data/", "클라우드 메타데이터"),
    ("http://127.0.0.1:5432/", "루프백"),
    ("http://10.0.0.1/admin", "사설 대역"),
    ("http://localhost:8000/api/features", "localhost 이름"),
    ("file:///etc/passwd", "http 아닌 스킴"),
])
def test_http_request_node_refuses_internal_targets(url, label):
    """요청을 **보내기 전에** 세운다 — transport 가 한 번도 불리지 않아야 한다."""
    from connectors.errors import ConnectorError
    from connectors.services import http_request
    from connectors.session import Response

    seen = []

    def _transport(*a, **k):
        seen.append(a)
        return Response(200, {}, {})

    session = _http_definition().connector.new_session(transport=_transport, sleep=lambda _: None)
    with pytest.raises(ConnectorError):
        http_request.call(_http_definition(), method="GET", url=url, session=session)
    assert seen == [], f"{label}: 차단됐어야 하는데 요청이 나갔다"


def test_http_request_node_refuses_redirect_into_internal_address():
    """초기 URL 만 검사하면 공격자가 자기 서버에서 302 로 내부를 가리켜 우회할 수 있다.
    requests 는 응답 훅을 다음 요청 **전에** 부르므로 거기서 세운다."""
    from connectors.errors import ConnectorError
    from connectors.services import http_request

    class _Resp:
        def __init__(self, location, base):
            self.status_code, self.url = 302, base
            self.headers = {"Location": location}
        is_redirect = True
        is_permanent_redirect = False

    with pytest.raises(ConnectorError):
        http_request._redirect_guard(_Resp("http://169.254.169.254/", "https://evil.test/r"))
    # 상대 경로도 현재 URL 기준으로 풀어서 본다
    with pytest.raises(ConnectorError):
        http_request._redirect_guard(_Resp("/internal", "http://127.0.0.1/x"))


def test_http_request_node_allows_ordinary_public_targets():
    """정상 외부 주소까지 막으면 노드가 죽는다."""
    from connectors.services import http_request
    http_request._guard_url("https://api.openai.com/v1/models")


def test_mock_replay_is_not_blocked_by_the_ssrf_guard():
    """mock 재생은 네트워크를 타지 않는다(재생 transport 가 끼워진다). check_url 은 DNS 를
    해석하므로, 목업 시나리오의 가짜 호스트를 막아버리면 Mock 탭이 통째로 죽는다."""
    import json as _json
    from connectors import mock_runtime
    from connectors.services import http_request

    with mock_runtime.activate(mock_runtime.MockContext(scenario="success")):
        body = http_request.call(_http_definition(), method="GET", url="https://api.example.invalid/x")
    assert _json.loads(body) == {"ok": True, "message": "목업 응답입니다"}


# ── 검증 오류가 제출한 값을 되비치지 않는다 ────────────────────────────────

def test_validation_errors_do_not_echo_the_submitted_value():
    """pydantic 의 exc.errors() 는 각 항목에 `input`(제출 값 원본)을 싣는다. 그대로 돌려주면
    검증에 실패한 요청 본문이 응답과 로그에 되비친다 — 토큰·비밀번호를 잘못된 형식으로
    보내면 그 값이 그대로 나온다."""
    import os as _os
    _os.environ.setdefault("DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app, raise_server_exceptions=False)
    secret = "sk-proj-MUST-NOT-APPEAR-IN-RESPONSE"

    r = client.post("/api/auth/google", json={"token": 12345, "leaked": secret})

    assert r.status_code == 422, r.text
    assert secret not in r.text
    assert "12345" not in r.text, "제출한 값이 응답에 그대로 실렸다"
    for item in r.json()["detail"]:
        assert set(item.keys()) == {"loc", "msg", "type"}, item


def test_safe_validation_errors_drops_input_and_ctx():
    """ctx 에 직렬화 불가능한 값이 들어와 500 이 되던 경로도 같이 닫힌다."""
    import main

    raw = [
        {"loc": ("body", "token"), "msg": "Input should be a valid string",
         "type": "string_type", "input": "sk-proj-SECRET", "ctx": {"error": object()}},
        "문자열 항목은 무시한다",
    ]
    safe = main._safe_validation_errors(raw)

    assert safe == [{"loc": ["body", "token"], "msg": "Input should be a valid string",
                     "type": "string_type"}]
    import json as _json
    _json.dumps(safe)  # 직렬화 가능해야 한다
