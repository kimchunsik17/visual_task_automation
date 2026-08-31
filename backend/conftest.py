"""pytest 공통 설정.

Database Query 는 운영에서 SQLite URI 를 열지 않는다(서버 파일 읽기 방지, ADR-0017 database_policy).
테스트는 SQLite 파일을 fixture 로 쓰므로 여기서만 허용한다.
"""

import os

os.environ.setdefault("DATABASE_QUERY_ALLOW_SQLITE", "1")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow_render: Chromium 렌더가 필요한 느린 테스트 (포맷 스튜디오 pdf/png)")

