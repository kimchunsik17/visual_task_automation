"""community_identity.py — 커뮤니티 공개 표면의 정체성 (ADR-0020, 우선 백로그 22 SAFE-1).

핸들은 **커뮤니티에 처음 들어올 때** 만든다. 전체 백필을 하지 않는 이유는 셋이다.

  1. 구글 이름에서 만든 핸들은 중복되거나 한글이라 URL·멘션에 쓰기 어렵다.
  2. 커뮤니티를 쓸 생각이 없는 사용자에게 공개 이름을 강제하게 된다.
  3. 처음 들어오는 순간에는 사용자가 **왜 필요한지** 안다.

그래서 프로필이 없는 사용자는 공개 표면에 **존재하지 않는다** — 검색되지도, 친구로 찾아지지도
않는다. 결함이 아니라 기본값이 비공개라는 뜻이다.

이메일은 어떤 공개 응답에도 넣지 않는다. 예전에는 친구 추가가 이메일로만 가능해서 **이메일만 알면
계정 존재 여부가 확인됐다**(계정 열거). 공개 표면이 생기면 그 경로가 스팸의 입구가 된다.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Any, Dict, Optional

HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,18})[a-z0-9]$")
MIN_HANDLE = 3
MAX_HANDLE = 20

# 공식·시스템을 사칭하거나 경로와 충돌하는 이름. 소문자로만 비교한다.
RESERVED_HANDLES = {
    "admin", "administrator", "root", "system", "support", "help", "official", "staff",
    "workflow", "workflowai", "workflow-ai", "api", "www", "app", "me", "you", "null",
    "undefined", "settings", "login", "logout", "signup", "notifications", "community",
    "moderator", "mod", "team", "security", "billing", "test",
}

# 혼동되는 문자를 같은 것으로 취급해 사칭을 막는다(`workfl0w-ai` vs `workflow-ai`).
_CONFUSABLES = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "_": "-"})


class HandleError(ValueError):
    """핸들 규칙 위반. 호출부가 사용자에게 보여줄 문구를 그대로 담는다."""


def canonical(handle: str) -> str:
    """사칭 비교용 정규형. 저장은 원래 문자열로 하고 **중복 검사만** 이 값으로 한다."""
    return unicodedata.normalize("NFKC", str(handle or "")).lower().translate(_CONFUSABLES).replace("-", "")


def normalize(raw: str) -> str:
    handle = unicodedata.normalize("NFKC", str(raw or "")).strip().lower()
    if not (MIN_HANDLE <= len(handle) <= MAX_HANDLE):
        raise HandleError(f"핸들은 {MIN_HANDLE}~{MAX_HANDLE}자여야 합니다.")
    if not HANDLE_RE.match(handle):
        raise HandleError("핸들은 소문자·숫자·하이픈만 쓸 수 있고, 하이픈으로 시작하거나 끝날 수 없습니다.")
    if "--" in handle:
        raise HandleError("하이픈을 연달아 쓸 수 없습니다.")
    if handle in RESERVED_HANDLES or canonical(handle) in {canonical(r) for r in RESERVED_HANDLES}:
        raise HandleError("이미 예약된 이름입니다. 다른 핸들을 골라주세요.")
    return handle


def is_taken(db, handle: str, *, exclude_user_id: Optional[int] = None) -> bool:
    """중복 검사는 정규형으로 한다 — `work0flow` 로 `workoflow` 를 사칭하지 못하게."""
    import models

    target = canonical(handle)
    query = db.query(models.CommunityProfile)
    if exclude_user_id is not None:
        query = query.filter(models.CommunityProfile.user_id != exclude_user_id)
    return any(canonical(row.handle) == target for row in query.all())


def suggest(db, user) -> str:
    """가입 이름에서 만든 후보. **제안일 뿐 사용자가 정한다.**"""
    seed = unicodedata.normalize("NFKD", str(getattr(user, "name", "") or ""))
    seed = "".join(c for c in seed if not unicodedata.combining(c)).lower()
    seed = re.sub(r"[^a-z0-9]+", "-", seed).strip("-")
    seed = re.sub(r"-{2,}", "-", seed)[:MAX_HANDLE - 3].strip("-")
    if len(seed) < MIN_HANDLE:
        seed = f"user{getattr(user, 'id', 0)}"
    candidate = seed
    suffix = 1
    while True:
        try:
            normalized = normalize(candidate)
        except HandleError:
            candidate, suffix = f"user{getattr(user, 'id', 0)}-{suffix}", suffix + 1
            continue
        if not is_taken(db, normalized):
            return normalized
        suffix += 1
        candidate = f"{seed}-{suffix}"[:MAX_HANDLE].strip("-")


def get_profile(db, user_id: int):
    import models

    return db.query(models.CommunityProfile).filter(models.CommunityProfile.user_id == user_id).first()


def create_profile(db, user, *, handle: str, display_name: str = "", bio: str = ""):
    """커뮤니티 최초 진입 시 한 번 부른다. 이미 있으면 그대로 돌려준다."""
    import models

    existing = get_profile(db, user.id)
    if existing:
        return existing

    normalized = normalize(handle)
    if is_taken(db, normalized):
        raise HandleError("이미 사용 중인 핸들입니다.")

    profile = models.CommunityProfile(
        user_id=user.id,
        handle=normalized,
        display_name=(display_name or getattr(user, "name", "") or normalized)[:60],
        bio=(bio or "")[:300],
        created_at=datetime.datetime.utcnow(),
    )
    db.add(profile)
    db.commit()
    return profile


def find_by_handle(db, handle: str):
    import models

    try:
        normalized = normalize(handle)
    except HandleError:
        return None
    return db.query(models.CommunityProfile).filter(models.CommunityProfile.handle == normalized).first()


def public_profile(profile, *, user=None) -> Dict[str, Any]:
    """공개 응답의 모양. **이메일은 어떤 경우에도 들어가지 않는다.**"""
    if profile is None:
        return {"handle": None, "displayName": "(알 수 없는 사용자)", "avatarArtifactId": None}
    return {
        "handle": profile.handle,
        "displayName": profile.display_name or profile.handle,
        "bio": profile.bio or "",
        "avatarArtifactId": profile.avatar_artifact_id,
        "joinedAt": profile.created_at.isoformat() if profile.created_at else None,
        "suspended": bool(profile.suspended_until and profile.suspended_until > datetime.datetime.utcnow()),
    }


def is_suspended(profile) -> bool:
    return bool(profile and profile.suspended_until and profile.suspended_until > datetime.datetime.utcnow())
