"""시연 공유 자격증명 폴백(demo_credentials)의 게이트·우선순위·기록 검사."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import demo_credentials

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


# ── 게이트: 환경변수 둘 다 있어야 켜진다 ────────────────────────────────

def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("DEMO_SHARED_CREDENTIALS_USER_ID", raising=False)
    monkeypatch.delenv("DEMO_SHARED_CREDENTIALS_PROVIDERS", raising=False)
    assert demo_credentials.fallback_user_id("juso") is None

    monkeypatch.setenv("DEMO_SHARED_CREDENTIALS_USER_ID", "1")
    assert demo_credentials.fallback_user_id("juso") is None  # provider 목록 없음

    monkeypatch.setenv("DEMO_SHARED_CREDENTIALS_PROVIDERS", "juso, data_go_kr")
    assert demo_credentials.fallback_user_id("juso") == 1
    assert demo_credentials.fallback_user_id("data_go_kr") == 1
    assert demo_credentials.fallback_user_id("naver") is None  # 허용 밖

    monkeypatch.setenv("DEMO_SHARED_CREDENTIALS_USER_ID", "abc")  # 오타 방어
    assert demo_credentials.fallback_user_id("juso") is None


# ── DB 경로 통합 (sqlite 서브프로세스 — 저장소 관례) ─────────────────────

SCENARIO = r'''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
os.environ.pop("DEMO_SHARED_CREDENTIALS_USER_ID", None)
os.environ.pop("DEMO_SHARED_CREDENTIALS_PROVIDERS", None)
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))

from database import engine, SessionLocal, Base
import models
Base.metadata.create_all(engine)

db = SessionLocal()
booth = models.User(id=1, google_id="booth", email="booth@example.com", name="booth")
visitor = models.User(id=2, google_id="visitor", email="visitor@example.com", name="visitor")
db.add_all([booth, visitor])
db.commit()

from credential_crypto import encrypt_secret
db.add(models.UserApiKey(user_id=1, provider="juso", api_key=encrypt_secret("U01TX-DEMO-KEY")))
db.add(models.UserApiKey(user_id=1, provider="naver", api_key=encrypt_secret("BOOTH-NAVER")))
db.add(models.UserApiKey(user_id=2, provider="data_go_kr", api_key=encrypt_secret("VISITOR-OWN-KEY")))
db.commit()

from connectors.errors import AUTH_MISSING, ConnectorError
from connectors.oauth import require_token
import demo_credentials

# 1) 기본 꺼짐 — 방문자에게 키가 없으면 그대로 AUTH_MISSING
try:
    require_token("juso", 2, db, service="도로명주소")
    raise SystemExit("폴백이 꺼져 있는데 키가 나왔다")
except ConnectorError as e:
    assert e.code == AUTH_MISSING, e.code

# 2) 켜면 부스 계정 키로 폴백 + 사용이 기록된다
os.environ["DEMO_SHARED_CREDENTIALS_USER_ID"] = "1"
os.environ["DEMO_SHARED_CREDENTIALS_PROVIDERS"] = "juso,data_go_kr"
token = require_token("juso", 2, db, service="도로명주소")
assert token == "U01TX-DEMO-KEY", "부스 계정 juso 키가 나와야 한다"
db.commit()
logs = db.query(models.FlowExecutionLog).filter(
    models.FlowExecutionLog.event_type == demo_credentials.EVENT_TYPE).all()
assert len(logs) == 1, f"사용 기록이 1건이어야 한다: {len(logs)}"
assert logs[0].actor_user_id == 2 and logs[0].billable_user_id == 1
assert "juso" in (logs[0].result or "")
assert "U01TX" not in (logs[0].result or ""), "비밀 값이 기록에 남으면 안 된다"

# 3) 사용자 본인 키가 우선 — 폴백도, 추가 기록도 없다
assert require_token("data_go_kr", 2, db, service="공공데이터포털") == "VISITOR-OWN-KEY"
db.commit()
count = db.query(models.FlowExecutionLog).filter(
    models.FlowExecutionLog.event_type == demo_credentials.EVENT_TYPE).count()
assert count == 1, "본인 키 사용은 기록 대상이 아니다"

# 4) 허용 목록 밖 provider 는 부스 계정에 키가 있어도 폴백하지 않는다
try:
    require_token("naver", 2, db, service="네이버")
    raise SystemExit("허용 밖 provider 가 폴백됐다")
except ConnectorError as e:
    assert e.code == AUTH_MISSING, e.code

# 5) 부스 계정 본인 실행은 폴백 개념이 없다(자기 키 사용, 기록 없음)
assert require_token("juso", 1, db, service="도로명주소") == "U01TX-DEMO-KEY"
db.commit()
count = db.query(models.FlowExecutionLog).filter(
    models.FlowExecutionLog.event_type == demo_credentials.EVENT_TYPE).count()
assert count == 1

# 6) placeholder 경로 — 이미 있는 키는 유지, 없는 것만 채운다
api_key_map = {"{{API_CENTER:data_go_kr}}": "OWNER-VALUE"}
added = demo_credentials.augment_api_key_map(db, api_key_map, owner_user_id=2)
assert api_key_map["{{API_CENTER:data_go_kr}}"] == "OWNER-VALUE"
assert api_key_map["{{API_CENTER:juso}}"] == "U01TX-DEMO-KEY"
assert added == {"{{API_CENTER:juso}}": "juso"}

# 7) 부스 계정 소유 프로젝트에는 placeholder 폴백을 만들지 않는다
assert demo_credentials.augment_api_key_map(db, {}, owner_user_id=1) == {}

print("DEMO CREDENTIALS ALL OK")
'''


def test_demo_credentials_end_to_end(tmp_path):
    scenario_path = tmp_path / "demo_credentials_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'demo.db'}"

    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "DEMO CREDENTIALS ALL OK" in result.stdout


def test_record_use_never_raises():
    """기록 실패가 실행을 멈추면 안 된다 — db 가 죽어 있어도 예외가 새지 않는다."""

    class _BrokenDb:
        def __getattr__(self, name):
            raise RuntimeError("db down")

    demo_credentials.record_use(_BrokenDb(), providers=["juso"], actor_user_id=2,
                                shared_user_id=1, source="connector")
