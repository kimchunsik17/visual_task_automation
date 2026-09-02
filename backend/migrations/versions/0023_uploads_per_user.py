"""uploaded_files.stored_name 전역 unique → (owner_user_id, stored_name) 복합 unique

Revision ID: 0023_uploads_per_user
Revises: 0022_templates_slug_unique

업로드·생성 파일의 물리 위치가 소유자 디렉토리(uploads/u<id>/)로 나뉜다. 생성 파일은
이름을 사용자가 정할 수 있어서(uploads/서식.hwpx) 전역 unique 면 서로 다른 사용자의 같은
이름이 충돌했고, 등록 하이재킹 가드가 두 번째 사용자의 등록을 포기하게 만들었다. 디렉토리를
나누면 이름 충돌 자체가 없으므로 unique 도 소유자 안으로 좁힌다.

디스크의 기존 파일 이동은 DB 마이그레이션이 아니라 별도 스크립트가 한다
(scripts/server/07-uploads-per-user-move.sh) — 장부(owner)가 있는 파일만 옮기고, 소유자를
모르는 파일은 레거시 루트에 남긴다(ADR-0010: 추측해서 옮기지/지우지 않는다). 이동 전에도
resolver 가 레거시 루트로 폴백하므로 코드 배포 순서와 무관하게 동작한다.

⚠️ 존재 확인은 inspector 로 한다 — batch_alter_table 안의 try/except 는 소용없다:
SQLite 에서는 작업이 with 블록 종료 시점에 실행돼 예외가 try 밖에서 터지고, PostgreSQL
에서는 실패한 DROP 이 트랜잭션을 오염시켜 다음 문장이 전부 실패한다(PR #41 리뷰).
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_uploads_per_user"
down_revision = "0022_templates_slug_unique"
branch_labels = None
depends_on = None

_INDEX = "ix_uploaded_files_stored_name"
_UQ = "uq_uploaded_files_owner_stored_name"
_TABLE = "uploaded_files"


def _existing(connection):
    inspector = sa.inspect(connection)
    indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    uniques = {uc["name"] for uc in inspector.get_unique_constraints(_TABLE)}
    # SQLite 는 unique 인덱스를 인덱스 목록으로만 보고하기도 한다.
    return indexes, uniques


def upgrade() -> None:
    indexes, uniques = _existing(op.get_bind())

    # 전역 unique 인덱스를 일반 인덱스로 바꾼다(stored_name 단독 조회는 여전히 많다 —
    # legacy 경로 역조회, 이미지 join). 그 위에 (owner, stored_name) 복합 unique 를 얹는다.
    with op.batch_alter_table(_TABLE) as batch:
        if _INDEX in indexes:
            batch.drop_index(_INDEX)
        batch.create_index(_INDEX, ["stored_name"])
        if _UQ not in uniques and _UQ not in indexes:
            batch.create_unique_constraint(_UQ, ["owner_user_id", "stored_name"])


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT stored_name, COUNT(*) AS n FROM uploaded_files GROUP BY stored_name HAVING COUNT(*) > 1"
    )).fetchall()
    if rows:
        detail = ", ".join(f"{r[0]}({r[1]}건)" for r in rows[:10])
        raise RuntimeError(
            "stored_name 이 여러 소유자에 걸쳐 존재해 전역 unique 로 되돌릴 수 없다: " + detail
        )
    indexes, uniques = _existing(connection)
    with op.batch_alter_table(_TABLE) as batch:
        if _UQ in uniques:
            batch.drop_constraint(_UQ, type_="unique")
        if _INDEX in indexes:
            batch.drop_index(_INDEX)
        batch.create_index(_INDEX, ["stored_name"], unique=True)
