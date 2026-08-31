"""connectors/cursor.py — Trigger 가 "어디까지 처리했는지" (한국형 노드 계획 Phase 0, §7).

예전에는 이 로직이 `graph.py` 안에서 **문자열로 조립돼 생성 코드에 박혔다.** 그래서 테스트할
방법이 없었고, 저장 위치도 `NodeMemory` 를 `session_id='__cursor__'` 로 빌려 쓰는 형태였다.
대화 기억용 표에 세션이 아닌 상태를 끼워 넣은 것이라 workspace 격리·provider 구분·형식 버전·
lease 를 둘 자리가 없었다.

■ 이 모듈이 지키는 것

  1. **없는 cursor 와 못 읽는 cursor 를 구분한다.** 트리거는 `cursor == {}` 를 "첫 실행"으로
     읽고 과거를 통지하지 않는다(`rss.poll_new_items` 의 `first_run = not cursor`). 그래서
     "정말 처음"과 "있는데 못 읽었다"를 같게 다루면 **조용히 과거를 다시 통지한다.** 후자는
     예외로 올려서 시끄럽게 실패시킨다.
  2. **이행기 읽기.** 새 표에 행이 없으면 옛 자리를 한 번 더 본다. 마이그레이션 0017 이 값을
     옮기지만, 그 사이에 만들어진 행이 남아 있어도 재통지가 나지 않게 한다.
  3. **lease.** 같은 노드를 두 워커가 동시에 폴링하면 둘 다 통지한다. 먼저 잡은 쪽만 진행한다.
"""

from __future__ import annotations

import datetime
import json
import socket
import os
from typing import Any, Dict, Optional

# 지금 코드가 쓰는 cursor 형식. 형식을 바꿀 때 올리고, 읽는 쪽은 모르는 버전을 거부한다.
CURRENT_VERSION = 1
DEFAULT_LEASE_SECONDS = 300

LEGACY_SESSION_ID = "__cursor__"


class CursorUnreadable(RuntimeError):
    """cursor 가 있는데 읽을 수 없다. **첫 실행으로 강등하면 안 된다.**"""


def _now(now: Optional[datetime.datetime] = None) -> datetime.datetime:
    return now or datetime.datetime.utcnow()


def worker_identity() -> str:
    """lease 주인을 구분하는 이름. 프로세스가 죽으면 lease 는 만료로 풀린다."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _workspace_id_for(db, project_id: int) -> Optional[int]:
    import models

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    return getattr(project, "workspace_id", None) if project else None


def _row(db, project_id: int, node_id: str):
    import models

    return (
        db.query(models.ConnectorCursor)
        .filter(models.ConnectorCursor.project_id == project_id,
                models.ConnectorCursor.node_id == node_id)
        .first()
    )


def _legacy_cursor(db, project_id: int, node_id: str) -> Optional[Dict[str, Any]]:
    """마이그레이션 0017 이전 자리(`NodeMemory`)를 본다. 없으면 None."""
    import models

    row = (
        db.query(models.NodeMemory)
        .filter(models.NodeMemory.session_id == LEGACY_SESSION_ID,
                models.NodeMemory.project_id == project_id,
                models.NodeMemory.node_id == node_id)
        .first()
    )
    if not row or not row.history:
        return None
    try:
        value = json.loads(row.history)
    except (ValueError, TypeError) as exc:
        raise CursorUnreadable(
            f"옛 cursor 를 읽을 수 없다(project={project_id}, node={node_id})"
        ) from exc
    return value if isinstance(value, dict) else None


def load(db, *, project_id: int, node_id: str) -> Dict[str, Any]:
    """저장된 cursor. **정말 없을 때만** 빈 dict 를 돌려준다."""
    if not db:
        return {}
    row = _row(db, project_id, node_id)
    if row is None:
        legacy = _legacy_cursor(db, project_id, node_id)
        return legacy if legacy is not None else {}

    if row.cursor_version != CURRENT_VERSION:
        # 첫 실행으로 읽으면 과거를 통지한다. 시끄럽게 실패하는 편이 낫다.
        raise CursorUnreadable(
            f"모르는 cursor 형식 v{row.cursor_version}(project={project_id}, node={node_id}). "
            f"이 버전은 v{CURRENT_VERSION} 만 읽는다."
        )
    try:
        value = json.loads(row.cursor_json or "{}")
    except (ValueError, TypeError) as exc:
        raise CursorUnreadable(
            f"cursor 를 읽을 수 없다(project={project_id}, node={node_id})"
        ) from exc
    return value if isinstance(value, dict) else {}


def save(db, cursor: Dict[str, Any], *, project_id: int, node_id: str,
         provider: Optional[str] = None, now: Optional[datetime.datetime] = None) -> None:
    """cursor 를 저장한다. workspace 소유는 프로젝트에서 따라온다."""
    if not db:
        return
    import models

    row = _row(db, project_id, node_id)
    if row is None:
        row = models.ConnectorCursor(project_id=project_id, node_id=node_id)
        db.add(row)
    row.workspace_id = _workspace_id_for(db, project_id)
    if provider:
        row.provider = provider
    row.cursor_version = CURRENT_VERSION
    row.cursor_json = json.dumps(cursor or {}, ensure_ascii=False)
    row.updated_at = _now(now)
    db.commit()


# ── lease: 같은 노드를 두 번 폴링하지 않는다 ────────────────────────────

def acquire_lease(db, *, project_id: int, node_id: str, owner: Optional[str] = None,
                  seconds: int = DEFAULT_LEASE_SECONDS,
                  now: Optional[datetime.datetime] = None) -> bool:
    """폴링 권리를 잡는다. 이미 남이 유효한 lease 를 들고 있으면 False.

    같은 주인이 다시 부르면 갱신이다(재진입 허용) — 한 실행 안에서 load/save 가 여러 번
    일어나도 스스로를 막지 않아야 한다.
    """
    if not db:
        return True
    import models

    owner = owner or worker_identity()
    moment = _now(now)
    row = _row(db, project_id, node_id)
    if row is None:
        row = models.ConnectorCursor(project_id=project_id, node_id=node_id,
                                     cursor_version=CURRENT_VERSION, cursor_json="{}")
        db.add(row)

    held_by_other = (
        row.lease_owner is not None
        and row.lease_owner != owner
        and row.lease_expires_at is not None
        and row.lease_expires_at > moment
    )
    if held_by_other:
        db.rollback()
        return False

    row.lease_owner = owner
    row.lease_expires_at = moment + datetime.timedelta(seconds=seconds)
    db.commit()
    return True


def release_lease(db, *, project_id: int, node_id: str, owner: Optional[str] = None) -> None:
    """내가 잡은 lease 만 푼다. 남의 것은 건드리지 않는다."""
    if not db:
        return
    owner = owner or worker_identity()
    row = _row(db, project_id, node_id)
    if row is not None and row.lease_owner == owner:
        row.lease_owner = None
        row.lease_expires_at = None
        db.commit()


def purge_stale_leases(db, *, now: Optional[datetime.datetime] = None) -> int:
    """만료된 lease 를 비운다. 프로세스가 죽어 release 를 못 부른 경우를 정리한다."""
    if not db:
        return 0
    import models

    moment = _now(now)
    rows = (
        db.query(models.ConnectorCursor)
        .filter(models.ConnectorCursor.lease_owner.isnot(None),
                models.ConnectorCursor.lease_expires_at <= moment)
        .all()
    )
    for row in rows:
        row.lease_owner = None
        row.lease_expires_at = None
    if rows:
        db.commit()
    return len(rows)


# ── 어디부터 알릴 것인가 (Phase 3 F3, 2026-08-30) ───────────────────────
#
# 지금까지 이 정책이 트리거마다 따로 있었다. `rss.poll_new_items` 와
# `naver_search.poll_new_results` 가 **같은 일을 각자 구현했고**, 그래서 한쪽에서 찾은 결함
# (겹침 창 없음)이 다른 쪽에는 이미 고쳐져 있는 상태로 오래 남아 있었다. 여기로 올린다.
#
# 시작 모드가 셋인 이유:
#
#   baseline  처음 켰을 때 **아무것도 알리지 않는다.** 지금 보이는 것을 기준선으로만 삼는다.
#             기본값이다 — 트리거를 켜자마자 과거 글 50개가 쏟아지는 것이 가장 나쁜 첫인상이다.
#   backfill  처음에 지금 보이는 것을 **전부 알린다.** "지난 것부터 처리하고 싶다" 는 경우.
#   since     정한 시각 **이후 것만** 알린다. 중간부터 이어받을 때.
#
# 겹침 창(`window`)은 셋 모두에 적용된다. 피드·검색 인덱스는 항목이 밀려났다 돌아오고,
# 서버가 잠깐 적게 주기도 한다 — 마지막 응답만 기억하면 그때마다 "새 글"이 된다.

START_MODES = ("baseline", "backfill", "since")
DEFAULT_SEEN_WINDOW = 300


def _parse_time(value: Any) -> Optional[datetime.datetime]:
    """ISO 8601 이나 `datetime` 을 받는다. 못 읽으면 None — 시각 비교를 건너뛴다."""
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def select_new(
    cursor: Optional[Dict[str, Any]],
    items: list,
    *,
    key: str,
    seen_field: str = "seen_ids",
    window: int = DEFAULT_SEEN_WINDOW,
    start_mode: str = "baseline",
    since: Any = None,
    time_key: Optional[str] = None,
    limit: Optional[int] = None,
    version: int = CURRENT_VERSION,
) -> Dict[str, Any]:
    """새로 알릴 항목을 고르고 다음 cursor 를 만든다.

    `items` 는 dict 목록이고 `key` 가 그중 식별자 필드다(`rss` 는 `"id"`, 네이버 검색은
    `"link"`). `seen_field` 는 **저장된 cursor 의 필드 이름**이라 트리거마다 다를 수 있다 —
    이미 DB 에 있는 값을 못 읽게 되면 과거를 다시 알리므로 이름을 바꾸지 않는다.

    돌려주는 것: `items`(알릴 것), `first_run`, `cursor`(다음 실행에 줄 것),
    `pending`(`limit` 때문에 이번에 못 보낸 수 — 다음 실행에서 이어서 온다).
    """
    if start_mode not in START_MODES:
        raise ValueError(f"모르는 시작 모드: {start_mode} ({', '.join(START_MODES)} 중 하나)")

    cursor = cursor or {}
    stored_version = cursor.get("version")
    if cursor and stored_version not in (None, version):
        # 첫 실행으로 강등하지 않는다 — 그러면 과거를 통째로 다시 알린다.
        raise CursorUnreadable(
            f"모르는 cursor 형식 v{stored_version} (이 버전은 v{version} 만 읽는다)")

    seen = [str(x) for x in (cursor.get(seen_field) or [])]
    seen_set = set(seen)
    first_run = not cursor

    identified = [it for it in items if str(it.get(key) or "")]
    unseen = [it for it in identified if str(it[key]) not in seen_set]

    if first_run:
        if start_mode == "baseline":
            fresh = []
        elif start_mode == "backfill":
            fresh = unseen
        else:  # since
            boundary = _parse_time(since)
            if boundary is None:
                # 기준 시각을 못 읽으면 **아무것도 알리지 않는다.** 잘못 읽고 전부 보내는
                # 것보다, 한 번 조용한 편이 낫다.
                fresh = []
            else:
                fresh = [it for it in unseen
                         if (_parse_time(it.get(time_key)) or boundary) > boundary]
    else:
        fresh = unseen

    if limit is not None and limit >= 0:
        pending = max(0, len(fresh) - limit)
        fresh = fresh[:limit]
    else:
        pending = 0

    # **알린 것만** 기억한다. 첫 실행의 baseline 만 예외로 지금 보이는 것 전체를 기준선에 넣는다.
    if first_run and start_mode == "baseline":
        notified = {str(it[key]) for it in identified}
    else:
        notified = {str(it[key]) for it in fresh}

    # 겹침 창: 이번에 처리한 것을 앞에, 예전 것을 뒤에 두고 자른다.
    merged = [str(it[key]) for it in identified if str(it[key]) in notified]
    for item_id in seen:
        if item_id not in notified:
            merged.append(item_id)

    return {
        "items": fresh,
        "first_run": first_run,
        "pending": pending,
        "cursor": {"version": version, seen_field: merged[:window]},
    }
