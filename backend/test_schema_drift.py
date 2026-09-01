"""모델과 마이그레이션이 어긋나지 않는지 — **unique 선언에 한정한** 계약 테스트.

넓은 드리프트 검사(`compare_metadata` 전수 비교)는 일부러 하지 않는다. 지금 32건이 나오는데
무시 목록을 크게 잡으면 무의미해지고 작게 잡으면 상시 빨강이라, "어디까지 검사할지" 를 먼저
정해야 하는 정책 과제다. 그건 남겨 두고, **실제로 터진 종류 하나**만 좁게 잡는다.

터진 것: `models.py:801` 은 `templates.slug` 를 `unique=True` 로 선언했는데
`0014_community_templates.py:46` 은 unique 가 아닌 인덱스를 만들었다. 모델만 보고 "DB 가
막아준다" 고 가정하는 코드가 중복을 만들 수 있었고, slug 는 공개 템플릿 URL 의 키다.
(`0022_templates_slug_unique` 에서 고쳤다.)

unique 만 보는 이유: 이건 **데이터 무결성 선언**이라 어긋나면 조용히 데이터가 망가진다.
나머지 드리프트(타입 미세 차이, 인덱스 유무)는 대체로 성능·표현의 문제라 급이 다르다.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

import db_migrate
import models  # noqa: F401  (Base.metadata 에 모든 테이블을 등록한다)
from database import Base


def _single_column_unique_names(inspector, table: str) -> set:
    """이 표에서 단일 컬럼에 unique 가 걸린 컬럼 이름들."""
    names = set()
    for index in inspector.get_indexes(table):
        if index.get("unique") and len(index["column_names"]) == 1:
            names.add(index["column_names"][0])
    for constraint in inspector.get_unique_constraints(table):
        if len(constraint["column_names"]) == 1:
            names.add(constraint["column_names"][0])
    return names


def test_every_unique_column_in_the_models_is_unique_in_the_migrated_schema(tmp_path):
    """마이그레이션만으로 만든 DB 에 대고 확인한다 — `create_all` 로 만들면 모델을 모델로
    검사하는 셈이라 이 어긋남을 영원히 못 잡는다."""
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    engine = create_engine(url)
    db_migrate.ensure_schema(engine, url)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # 마이그레이션이 실제로 돌았는지 먼저 못 박는다. 이게 없으면 표가 하나도 없을 때 아래
    # 루프가 전부 건너뛰어 **공허하게 통과**한다(실제로 이 테스트를 쓰다가 한 번 겪었다).
    assert "templates" in tables and len(tables) > 30, \
        f"마이그레이션이 제대로 돌지 않았다 — 표 {len(tables)}개: {sorted(tables)[:10]}"

    declared = [(t.name, c.name) for t in Base.metadata.sorted_tables
                for c in t.columns if c.unique and not c.primary_key]
    assert declared, "모델에 unique=True 컬럼이 하나도 없다 — 검사가 무의미해졌다"

    missing = []
    for table_name, column_name in declared:
        if table_name not in tables:
            continue
        if column_name not in _single_column_unique_names(inspector, table_name):
            missing.append(f"{table_name}.{column_name}")

    assert not missing, (
        "모델은 unique 라고 선언했는데 마이그레이션이 만든 스키마에는 없다. DB 가 막아줄 것이라 "
        "믿는 코드가 중복을 만들 수 있다 — 해당 컬럼에 unique 인덱스를 추가하는 마이그레이션이 "
        f"필요하다: {missing}"
    )
