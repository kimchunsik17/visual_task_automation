"""templates.slug 를 실제로 unique 하게 만든다

Revision ID: 0022_templates_slug_unique
Revises: 0021_document_formats

모델과 스키마가 어긋나 있었다:

    models.py:801                 slug = Column(String, unique=True, nullable=False, index=True)
    0014_community_templates.py:46  op.create_index("ix_templates_slug", "templates", ["slug"])
                                    → **unique 가 아니다**

대조군으로 0015_workspaces.py:28 은 같은 자리에서 `unique=True` 를 선언한다 — 0014 의 누락이다.
모델만 보고 "DB 가 막아준다" 고 가정하는 코드가 중복 slug 를 만들 수 있고, 그러면 조회가
어느 행을 돌려줄지 정해지지 않는다(slug 는 공개 템플릿 URL 의 키다).

운영에 중복이 0건인 지금이 고치기 가장 싼 시점이다. 그래도 이 마이그레이션이 다른 DB(스테이징,
로컬 사본)에서도 돌 수 있으므로 **중복이 있으면 조용히 넘어가지 않고 멈춘다** — 어느 행을
살릴지는 사람이 정해야 한다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_templates_slug_unique"
down_revision = "0021_document_formats"
branch_labels = None
depends_on = None

_INDEX = "ix_templates_slug"


def _abort_if_duplicates(connection) -> None:
    rows = connection.execute(sa.text(
        "SELECT slug, COUNT(*) AS n FROM templates GROUP BY slug HAVING COUNT(*) > 1"
    )).fetchall()
    if rows:
        detail = ", ".join(f"{r[0]}({r[1]}건)" for r in rows[:10])
        raise RuntimeError(
            "templates.slug 에 중복이 있어 unique 인덱스를 만들 수 없다. 어느 행을 살릴지는 "
            f"사람이 정해야 한다 — 중복 slug: {detail}"
        )


def upgrade() -> None:
    connection = op.get_bind()
    _abort_if_duplicates(connection)

    # 이름이 같은 인덱스를 unique 로 바꾸려면 지웠다 다시 만들어야 한다(양쪽 엔진 공통).
    # 0014 를 거치지 않고 만들어진 DB 도 있을 수 있어 없으면 조용히 넘어간다.
    try:
        op.drop_index(_INDEX, table_name="templates")
    except Exception:
        pass
    op.create_index(_INDEX, "templates", ["slug"], unique=True)


def downgrade() -> None:
    try:
        op.drop_index(_INDEX, table_name="templates")
    except Exception:
        pass
    op.create_index(_INDEX, "templates", ["slug"])
