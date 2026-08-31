"""Alembic 환경 설정 (ADR-0006).

■ 디렉터리 이름이 'alembic' 이 아니라 'migrations' 인 이유
  서버는 cwd 를 backend/ 로 두고 뜬다. 그 자리에 'alembic' 이라는 디렉터리가 있으면
  파이썬이 그걸 네임스페이스 패키지로 잡아서 실제 alembic 라이브러리를 가려버리고,
  `from alembic import command` 가 ImportError 로 죽는다(실제로 배포에서 발견했다).

DB 접속 정보는 alembic.ini 가 아니라 애플리케이션과 같은 곳(DATABASE_URL 환경변수)에서
읽는다 — 두 군데에 적어두면 스테이징/운영에서 서로 다른 DB를 가리키는 사고가 난다.
"""

from logging.config import fileConfig
import os
import pathlib
import sys

from sqlalchemy import engine_from_config, pool

from alembic import context

# alembic 은 backend/ 밖에서도 실행될 수 있으므로 backend/ 를 import 경로에 넣는다.
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base, SQLALCHEMY_DATABASE_URL  # noqa: E402
import models  # noqa: E402,F401  (Base.metadata 에 모든 테이블을 등록하기 위한 import)

config = context.config

# 호출부가 URL을 이미 정해줬으면(db_migrate.ensure_schema 가 그렇게 한다) 그걸 그대로 쓴다.
# 여기서 무조건 환경변수로 덮어쓰면, 특정 DB를 지정해 마이그레이션을 돌리려는 호출이
# 조용히 다른 DB를 향하게 된다.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", SQLALCHEMY_DATABASE_URL))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite 는 ALTER 지원이 제한적이라 배치 모드가 필요하다(로컬 개발 DB 대응).
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
