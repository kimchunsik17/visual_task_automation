"""pytest 공통 설정.

Database Query 는 운영에서 SQLite URI 를 열지 않는다(서버 파일 읽기 방지, ADR-0017 database_policy).
테스트는 SQLite 파일을 fixture 로 쓰므로 여기서만 허용한다.
"""

import os
import sys

os.environ.setdefault("DATABASE_QUERY_ALLOW_SQLITE", "1")

# ── 운영 DB 차단 가드 (2026-08-31) ────────────────────────────────────────
# test_auth_enforcement.py 가 SessionLocal() 을 그대로 써서 운영 RDS 에 붙어, 테스트가 만든
# 사용자·공유가 운영 표에 남았다(적대적 감사에서 발견). 어떤 테스트도 실수로 운영 DB 를
# 잡지 못하게, DATABASE_URL 이 설정돼 있지 않으면 **테스트 전용 sqlite 로 강제**하고,
# 운영으로 보이는 호스트가 잡히면 수집 단계에서 즉시 멈춘다.
_DANGEROUS_DB_HOSTS = ("rds.amazonaws.com", "database-1", "amazonaws.com")


def _is_production_db(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _DANGEROUS_DB_HOSTS)


# import 되는 어떤 모듈(database.py 등)보다 먼저 세워야 한다 — 그래서 conftest 최상단이다.
_env_url = os.environ.get("DATABASE_URL", "")
if not _env_url:
    # 아무도 명시하지 않았으면 운영 .env 의 postgres 를 잡는 대신 테스트 sqlite 를 쓴다.
    os.environ["DATABASE_URL"] = "sqlite:///./test_run.db"
elif _is_production_db(_env_url):
    sys.stderr.write(
        "\n[conftest] 거부: DATABASE_URL 이 운영 DB 를 가리킨다. 테스트는 운영에 붙지 않는다.\n"
        f"           {_env_url.split('@')[-1]}\n"
        "           테스트용 sqlite 나 TEST_POSTGRES_URL 로 바꿔라.\n\n")
    raise SystemExit(2)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow_render: Chromium 렌더가 필요한 느린 테스트 (포맷 스튜디오 pdf/png)")

