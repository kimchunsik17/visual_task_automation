"""artifact_refs — 첨부 전송의 공통 ArtifactRef 식별자 (ADR-0018, 우선 백로그 20)

`uploaded_files` 에 `artifact_id`(공개 식별자)와 `sha256`(등록 시점 내용 hash)을 추가한다.

왜 저장 이름(uuid 파일명)을 그대로 쓰지 않는가: 저장 위치·이름은 object storage 전환 때 바뀌는
내부 값이고, 그래프·실행 로그·전송 결과에는 남으면 안 되는 값이다(§4.10 출시 게이트). 공개
식별자를 따로 두면 그래프에는 `artifactId` 만 남고, 실제 경로는 서버 resolver 안에서만 다룬다.

기존 행은 `artifact_id` 를 백필한다 — 안 하면 이 기능 도입 전에 올라온 파일은 영원히 첨부할 수
없다. `sha256` 은 백필하지 않는다(파일을 전부 다시 읽어야 하고, 없으면 resolver 가 전송 직전
검증을 건너뛰고 크기·MIME 만 확인한다).

Revision ID: 0010_artifact_refs
Revises: 0009_credential_labels
Create Date: 2026-08-29
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "0010_artifact_refs"
down_revision: Union[str, Sequence[str], None] = "0009_credential_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("uploaded_files") as batch:
        batch.add_column(sa.Column("artifact_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("sha256", sa.String(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id FROM uploaded_files WHERE artifact_id IS NULL")
    ).fetchall()
    for row in rows:
        connection.execute(
            sa.text("UPDATE uploaded_files SET artifact_id = :aid WHERE id = :rid"),
            {"aid": uuid.uuid4().hex, "rid": row[0]},
        )

    op.create_index("ix_uploaded_files_artifact_id", "uploaded_files", ["artifact_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_artifact_id", table_name="uploaded_files")
    with op.batch_alter_table("uploaded_files") as batch:
        batch.drop_column("sha256")
        batch.drop_column("artifact_id")
