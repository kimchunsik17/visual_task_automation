"""db_migrate.py — 애플리케이션 시작 시 DB 스키마를 head 로 맞춘다 (ADR-0006).

이 프로젝트는 그동안 `Base.metadata.create_all()` 로 테이블을 만들어 왔다. create_all 은
"없는 테이블만 만들고 이미 있는 테이블은 건드리지 않는" 동작이라, 모델에 컬럼을 추가해도
운영 DB에는 반영되지 않았다 — 그리고 그 사실이 런타임 쿼리 오류로만 드러났다.

그래서 Alembic 을 도입하면서, 이미 create_all 로 만들어진 DB 도 자동으로 인계받는다:

    alembic_version 없음 + projects 없음        → 새 DB. 전체 마이그레이션 실행
    alembic_version 없음 + projects 있음        → 기존 DB. 기준선으로 stamp 한 뒤 upgrade
    alembic_version 있음                        → 평소대로 upgrade

애매한 상태(마이그레이션 이력은 없는데 신규 테이블이 이미 있는 경우)는 추측해서 넘어가지
않고 명확한 오류로 멈춘다 — 절반만 적용된 스키마로 서비스가 뜨는 것이 더 나쁘기 때문이다.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
# 마이그레이션 스크립트는 backend/migrations/ 에 있다. 'alembic' 이라는 이름을 쓰지 않는 이유는
# 서버의 cwd 가 backend/ 라서, 같은 이름의 디렉터리가 실제 alembic 라이브러리를 가리기 때문이다.

# create_all 로 만들어진 기존 DB 를 인계할 때 stamp 할 지점 = Alembic 도입 직전 스키마.
BASELINE_REVISION = "0001_baseline"
# 기준선 이후에 추가된 테이블. 이게 이미 있는데 alembic 이력이 없으면 상태를 단정할 수 없다.
POST_BASELINE_TABLE = "project_revisions"


def _alembic_config(database_url: str):
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def ensure_schema(engine: Engine, database_url: Optional[str] = None) -> str:
    """스키마를 head 로 맞추고, 무엇을 했는지 알려주는 문자열을 돌려준다.

    실패하면 예외를 그대로 올린다. 호출부가 조용히 넘어가지 말라는 뜻이다 —
    스키마가 안 맞는 채로 뜨면 첫 쿼리에서 사용자에게 오류로 드러난다.
    """
    from alembic import command

    url = database_url or str(engine.url.render_as_string(hide_password=False))
    config = _alembic_config(url)

    tables = set(inspect(engine).get_table_names())
    has_history = "alembic_version" in tables
    has_legacy_schema = "projects" in tables

    if not has_history and has_legacy_schema:
        if POST_BASELINE_TABLE in tables:
            raise RuntimeError(
                f"마이그레이션 이력(alembic_version)이 없는데 '{POST_BASELINE_TABLE}' 테이블이 이미 있다. "
                "create_all 로 신규 테이블만 만들어진 상태로 보이며, 어느 지점으로 stamp 해야 할지 "
                "단정할 수 없다. DB 상태를 확인한 뒤 `alembic stamp <revision>` 으로 직접 지정하라."
            )
        # 기준선 스키마와 동일한 DB 라고 보고 이력만 심어준 뒤 이후 마이그레이션을 적용한다.
        command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
        return f"기존 DB를 {BASELINE_REVISION}로 stamp 한 뒤 head 까지 적용했다"

    command.upgrade(config, "head")
    return "head 까지 적용했다" if has_history else "새 DB에 전체 마이그레이션을 적용했다"
