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


# main.py 는 JWT_SECRET 이 없으면 부팅을 거부한다(설정 누락이 조용히 넘어가지 않게). 테스트는
# .env 없이 clean clone 에서도 돌아야 하므로 여기서 테스트 전용 값을 세운다. setdefault 라
# 실제 .env 나 셸 환경이 있으면 그쪽이 이긴다.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-not-for-any-real-deployment")


# ── 시연 플래그 중화 (2026-09-04) ─────────────────────────────────────────
# 로컬 backend/.env 에 시연 플래그(DEMO_UI·HIDDEN_NODE_TYPES 등)를 켜 두면 load_dotenv 가
# 테스트 프로세스에도 주입해 스위트가 비결정적으로 깨진다 — 실제로 HIDDEN_NODE_TYPES=jusoNode
# 하나로 카탈로그·별칭·커뮤니티 정렬·시연 로그인 테스트 5건이 로컬에서만 실패했다.
# 빈 문자열로 **미리 채워** 두면 load_dotenv(override=False)가 .env 값을 덮지 못한다(pop 은
# 답이 아니다 — 지우면 .env 가 다시 채운다). 플래그가 필요한 테스트는 monkeypatch.setenv 나
# 서브프로세스 시나리오 안의 명시적 대입으로 직접 켠다.
for _demo_flag in ("DEMO_UI", "HIDDEN_NODE_TYPES", "DEMO_LOGIN_CODE", "DEMO_LOGIN_SEATS",
                   "DEMO_SHARED_CREDENTIALS_USER_ID", "DEMO_SHARED_CREDENTIALS_PROVIDERS",
                   "DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX"):
    os.environ[_demo_flag] = ""

# LLM 라우팅 설정도 같은 이유로 중화한다(2026-09-05) — 로컬 .env 가 PICKLE 게이트웨이
# (LLM_PROVIDER=openrouter, OPENROUTER_BASE_URL=https://llm.pcl.kr/v1)로 바뀌면서 "기본 provider 는
# openai", "openrouter 기본 주소는 openrouter.ai" 같은 단정이 로컬에서만 깨진다. 빈 문자열은
# load_llm_settings 가 미설정으로 읽는다. provider 를 바꿔 보는 테스트는 monkeypatch.setenv 로 켠다.
for _llm_flag in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "OPENROUTER_BASE_URL",
                  "OPENROUTER_API_KEY", "PICKLE_API_KEY", "OPENROUTER_STRICT_FIELDS"):
    os.environ[_llm_flag] = ""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow_render: Chromium 렌더가 필요한 느린 테스트 (포맷 스튜디오 pdf/png)")



def minimal_subprocess_env(**overrides) -> dict:
    """자식 파이썬을 띄울 때 쓰는 최소 환경.

    이 환경을 좁히는 목적은 **부모의 DATABASE_URL 을 물려주지 않는 것**이지 OS 필수 변수까지
    지우는 것이 아니다. 그런데 `{"PATH": "/usr/bin:/bin", ...}` 처럼 POSIX 경로만 넘기면
    Windows 에서는 인터프리터가 아예 뜨지 않는다 —

        Fatal Python error: _Py_HashRandomization_Init:
        failed to get random numbers to initialize Python

    Windows 의 난수 초기화가 SystemRoot 를 필요로 하기 때문이다. 부모에서 그대로 가져와야
    하는 것만 골라 넘긴다(비밀은 없다). 호출부가 DATABASE_URL 등을 overrides 로 덮는다.
    """
    import os

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    # SystemRoot·COMSPEC 은 Windows 필수, TEMP/TMP 는 tempfile 이 쓴다.
    for key in ("SystemRoot", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env
