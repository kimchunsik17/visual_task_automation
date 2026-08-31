"""database_credentials.py — 명명된 Database 자격증명과 reference 해석 (ADR-0017, DB-1).

API 센터의 `database` provider 는 예전에 사용자당 한 행만 저장했다(provider 로 upsert). 개발/운영
DB 나 프로젝트별 DB 를 이름으로 고를 수 없었다. 이제 `user_api_keys` 에 `label` 을 두고 같은
provider 로 여러 행을 허용한다. 노드는 secret 을 모른다 — reference 만 저장한다.

    {{API_CENTER:database}}        기본 자격증명(한 개만 있을 때). 여러 개면 선택을 요구한다.
    {{API_CENTER:database#<id>}}   특정 자격증명

실행기(db_query_runtime)가 실행 직전에 소유자 기준으로 해석·복호화한다. 접속 URI 는 그래프,
revision, 생성 코드, 실행 로그 어디에도 복사되지 않는다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

import models
from credential_crypto import decrypt_secret, encrypt_secret
from database_policy import describe
from node_errors import NodeErrorException, make_error

PROVIDER = "database"
REF_RE = re.compile(r"^\{\{API_CENTER:database(?:#(\d+))?\}\}$")
DEFAULT_REF = "{{API_CENTER:database}}"

MISSING_MESSAGE = ("API 센터에 'Database' 자격증명이 아직 등록되지 않았습니다. "
                   "API 센터에서 읽기 전용 접속 문자열을 등록해주세요.")
AMBIGUOUS_MESSAGE = ("Database 자격증명이 여러 개 등록되어 있습니다. 노드에서 사용할 자격증명을 선택해주세요.")
UNKNOWN_MESSAGE = ("노드가 가리키는 Database 자격증명을 찾을 수 없습니다(삭제됐거나 다른 계정의 것입니다). "
                   "노드에서 자격증명을 다시 선택해주세요.")


def is_reference(value: Any) -> bool:
    return isinstance(value, str) and bool(REF_RE.match(value.strip()))


def parse_reference(value: str) -> Optional[int]:
    """reference 의 credential id. 기본 reference 면 None. reference 가 아니면 ValueError."""
    match = REF_RE.match((value or "").strip())
    if not match:
        raise ValueError("not a database credential reference")
    return int(match.group(1)) if match.group(1) else None


def make_reference(credential_id: Optional[int]) -> str:
    return DEFAULT_REF if credential_id is None else f"{{{{API_CENTER:database#{int(credential_id)}}}}}"


def _rows(db, user_id: int):
    return (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == PROVIDER)
        .order_by(models.UserApiKey.id.asc())
        .all()
    )


def _summary(row, *, is_default: bool) -> Dict[str, Any]:
    info = describe(decrypt_secret(row.api_key) or "")
    return {
        "id": row.id,
        "label": row.label or "",
        "reference": make_reference(None if is_default and not row.label else row.id),
        "dialect": info.get("dialect"),
        "host": info.get("host"),
        "database": info.get("database"),
        "valid": info.get("valid", False),
        "is_default": is_default,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_credentials(db, user_id: int) -> List[Dict[str, Any]]:
    """비밀 없는 목록. 노드의 선택 UI 와 API 센터 카드가 쓴다."""
    rows = _rows(db, user_id)
    return [_summary(row, is_default=(len(rows) == 1)) for row in rows]


def get_owned(db, user_id: int, credential_id: int):
    return (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.id == credential_id, models.UserApiKey.user_id == user_id,
                models.UserApiKey.provider == PROVIDER)
        .first()
    )


def validate_connection_string(connection_string: str) -> Dict[str, Any]:
    """저장 전 형식 검사. 비밀은 돌려주지 않는다."""
    info = describe(connection_string or "")
    if not info.get("valid") or not info.get("dialect"):
        raise ValueError("접속 문자열 형식이 올바르지 않습니다. 예: postgresql://user:password@host:5432/dbname")
    return info


def create(db, user_id: int, *, label: str, connection_string: str):
    validate_connection_string(connection_string)
    label = (label or "").strip()
    row = models.UserApiKey(user_id=user_id, provider=PROVIDER, api_key=encrypt_secret(connection_string), label=label or None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db, user_id: int, credential_id: int, *, label: Optional[str] = None, connection_string: Optional[str] = None):
    row = get_owned(db, user_id, credential_id)
    if row is None:
        return None
    if connection_string:
        validate_connection_string(connection_string)
        row.api_key = encrypt_secret(connection_string)
    if label is not None:
        row.label = label.strip() or None
    row.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(row)
    _invalidate_schema_cache(credential_id)
    return row


def delete(db, user_id: int, credential_id: int) -> bool:
    row = get_owned(db, user_id, credential_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    _invalidate_schema_cache(credential_id)
    return True


def _invalidate_schema_cache(credential_id: int) -> None:
    try:
        from database_diagnostics import invalidate_schema_cache
        invalidate_schema_cache(credential_id)
    except Exception:
        pass


def resolve(db, owner_user_id: Optional[int], reference: str, *, node_id: Optional[str] = None):
    """reference → (접속 문자열, 요약). 실패는 NodeErrorException(CREDENTIAL_MISSING / VALIDATION_REQUIRED).

    실행기 안에서만 불린다 — 복호화된 URI 는 이 함수의 반환값 이후로 엔진 생성에만 쓰이고
    로그·오류·생성 코드에는 들어가지 않는다.
    """
    common = dict(node_type="databaseNode", node_id=node_id, field="connectionString")
    try:
        credential_id = parse_reference(reference)
    except ValueError:
        raise NodeErrorException(make_error("CREDENTIAL_MISSING", user_message=MISSING_MESSAGE,
                                            safe_details={"provider": PROVIDER, "service": "Database"}, **common))
    if db is None or not owner_user_id:
        raise NodeErrorException(make_error("CREDENTIAL_MISSING", user_message=MISSING_MESSAGE,
                                            safe_details={"provider": PROVIDER, "service": "Database"}, **common))
    if credential_id is not None:
        row = get_owned(db, owner_user_id, credential_id)
        if row is None:
            raise NodeErrorException(make_error("CREDENTIAL_MISSING", user_message=UNKNOWN_MESSAGE,
                                                safe_details={"provider": PROVIDER, "service": "Database"}, **common))
    else:
        rows = _rows(db, owner_user_id)
        if not rows:
            raise NodeErrorException(make_error("CREDENTIAL_MISSING", user_message=MISSING_MESSAGE,
                                                safe_details={"provider": PROVIDER, "service": "Database"}, **common))
        if len(rows) > 1:
            # 한 릴리스 동안 기본 reference 는 "유일한 자격증명" 만 뜻한다 — 여러 개면 자동 선택하지 않는다(DB-1.5).
            raise NodeErrorException(make_error("VALIDATION_REQUIRED", user_message=AMBIGUOUS_MESSAGE,
                                                safe_details={"field": "connectionString", "label": "DB 연결"}, **common))
        row = rows[0]
    secret = decrypt_secret(row.api_key)
    if not secret:
        raise NodeErrorException(make_error("CREDENTIAL_INVALID", user_message="저장된 Database 자격증명을 복호화하지 못했습니다. API 센터에서 다시 등록해주세요.",
                                            safe_details={"provider": PROVIDER, "service": "Database"}, **common))
    return secret, _summary(row, is_default=(credential_id is None))
