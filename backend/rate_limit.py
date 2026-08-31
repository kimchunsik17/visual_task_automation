"""rate_limit.py — 쓰기 엔드포인트 공통 호출 한도 (ADR-0020, 우선 백로그 22 SAFE-4).

**PostgreSQL 로 센다.** 인메모리가 아닌 이유는 지연이 아니라 실패 방식이다.

  - 지금은 `uvicorn --workers 1` 이라 인메모리도 정확하다. 그런데 2 vCPU 서버에서 워커를 늘릴 이유는
    충분하고, **늘리는 순간 한도가 조용히 N배 느슨해진다.** 아무도 눈치채지 못한다.
  - 서비스가 재시작을 자주 겪으면 프로세스 안의 카운터는 그때마다 초기화된다.
  - 16명·DB 14MB 규모에서 왕복 1~3ms 는 그 대가로 싸다. Redis 는 도입하지 않는다.

저장소는 이 모듈 안에만 있다. 나중에 바꿔도 호출부(`enforce`)는 그대로다.

고정 윈도우를 쓴다. 경계에서 잠깐 두 배가 될 수 있지만(윈도우 끝과 다음 시작에 몰리는 경우)
도배 방지 목적에는 충분하고, 슬라이딩 윈도우는 행이 요청 수만큼 늘어난다.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

# (최대 횟수, 윈도우 초). 커뮤니티 쓰기는 사람이 손으로 하는 일이라 넉넉할 이유가 없다.
DEFAULT_RULES = {
    "post.create": (10, 3600),
    "answer.create": (30, 3600),
    "comment.create": (60, 3600),
    "report.create": (20, 3600),
    "friend.request": (20, 3600),
    "profile.update": (10, 3600),
    "message.send": (120, 3600),
    "block.create": (60, 3600),
    # 네이버 검색 API 의 하루 한도(한국형 노드 계획 §4.0). 과금 구간이 없어 돈 문제는 아니지만,
    # 한도가 **키 단위로 공유**되므로 한 워크플로의 폭주가 나머지를 굶긴다. 그래서 우리가 먼저 센다.
    "naver.search": (25000, 86400),
    # 호스트당 하루 수집 요청 수(한국형 노드 계획 §6.5). 주체가 사용자가 아니라 **호스트**라
    # 사용자가 늘어도 상대 서버가 받는 총량은 늘지 않는다.
    #
    # 50 인 이유: 아카라이브 규정 8번은 "서버에 부하를 주는" 수집을 제한하는데 **구체적인
    # 횟수를 밝히지 않는다**(2026-08-30 사용자 확인). 기준을 모를 때 고를 수 있는 안전한
    # 값은 "누가 봐도 부하가 아닌" 쪽이다. 하루 50회는 최소 간격 1초와 겹쳐 놓고 보면
    # 사람이 브라우저로 읽는 것과 구분되지 않는 수준이다.
    "crawl.fetch": (50, 86400),
}

# 가입 직후에는 더 엄격하다. 우회 계정으로 도배하는 경로를 좁힌다.
NEW_ACCOUNT_HOURS = 24
NEW_ACCOUNT_FACTOR = 0.3


class RateLimited(Exception):
    """한도 초과. 호출부가 429 로 바꾼다."""

    def __init__(self, action: str, limit: int, window_seconds: int, retry_after: int):
        super().__init__(f"{action}: {limit}/{window_seconds}s 초과")
        self.action, self.limit = action, limit
        self.window_seconds, self.retry_after = window_seconds, retry_after


def enabled() -> bool:
    return os.getenv("COMMUNITY_RATE_LIMIT", "1").strip().lower() not in {"0", "false", "off", "no"}


@dataclass(frozen=True)
class Rule:
    limit: int
    window_seconds: int


def rule_for(action: str, *, is_new_account: bool = False) -> Rule:
    limit, window = DEFAULT_RULES.get(action, (60, 3600))
    override = os.getenv(f"RATE_LIMIT_{action.replace('.', '_').upper()}")
    if override:
        try:
            limit = max(1, int(override))
        except ValueError:
            pass
    if is_new_account:
        limit = max(1, int(limit * NEW_ACCOUNT_FACTOR))
    return Rule(limit=limit, window_seconds=window)


def _bucket(window_seconds: int, now: datetime.datetime) -> int:
    return int(now.timestamp()) // max(1, window_seconds)


def hit(db, subject: str, action: str, *, is_new_account: bool = False,
        now: Optional[datetime.datetime] = None) -> int:
    """카운터를 1 올리고 현재 값을 돌려준다. 한도 판단은 `enforce` 가 한다.

    `INSERT ... ON CONFLICT DO UPDATE` 한 문장이라 동시 요청에서도 값이 어긋나지 않는다.
    """
    now = now or datetime.datetime.utcnow()
    rule = rule_for(action, is_new_account=is_new_account)
    key = f"{subject}:{action}:{_bucket(rule.window_seconds, now)}"
    expires_at = now + datetime.timedelta(seconds=rule.window_seconds * 2)

    row = db.execute(
        text("""
            INSERT INTO rate_limit_counters (key, count, expires_at)
            VALUES (:key, 1, :expires_at)
            ON CONFLICT (key) DO UPDATE SET count = rate_limit_counters.count + 1
            RETURNING count
        """),
        {"key": key, "expires_at": expires_at},
    ).scalar()
    db.commit()
    return int(row or 1)


def enforce(db, subject: str, action: str, *, is_new_account: bool = False,
            now: Optional[datetime.datetime] = None) -> None:
    """한도를 넘으면 `RateLimited`. 넘지 않으면 조용히 통과한다."""
    if not enabled():
        return
    now = now or datetime.datetime.utcnow()
    rule = rule_for(action, is_new_account=is_new_account)
    count = hit(db, subject, action, is_new_account=is_new_account, now=now)
    if count > rule.limit:
        elapsed = int(now.timestamp()) % rule.window_seconds
        raise RateLimited(action, rule.limit, rule.window_seconds, rule.window_seconds - elapsed)


def purge_expired(db, *, now: Optional[datetime.datetime] = None, limit: int = 5000) -> int:
    """만료 행 정리. 업로드 보존 정리와 같은 방식으로 지연 삭제한다."""
    import models

    now = now or datetime.datetime.utcnow()
    keys = [row.key for row in db.query(models.RateLimitCounter)
            .filter(models.RateLimitCounter.expires_at < now).limit(limit).all()]
    if not keys:
        return 0
    deleted = db.query(models.RateLimitCounter).filter(
        models.RateLimitCounter.key.in_(keys)
    ).delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)
