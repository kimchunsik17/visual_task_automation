"""시연 관리(어드민 패널) — 게스트 현황·정리, 최근 실행, 오늘의 발송/조회 수, 런타임 설정.

라우트는 main.py 에 있고 여기는 db 만 받는 순수 함수다. '오늘' 은 한국 시간(KST) 자정 기준이다 —
실행 시각은 UTC 로 저장되므로 KST 자정을 UTC 로 바꿔 비교한다.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List

from sqlalchemy import func

import demo_credentials
import demo_settings
import models
from usage_tracking import EVENT_WORKFLOW_EXECUTION

GUEST_PREFIX = "demo-guest-"
EVENT_EMAIL_SENT = "email_sent"
EVENT_GUEST_ENTRY = "demo_guest_entry"
KST = dt.timezone(dt.timedelta(hours=9))
# 외부 할당량(고정값 안내용) — 유튜브 검색 100단위/일 한도 10,000 → 이름 검색 100회, Gmail 일반 계정 발송 500통/일
QUOTAS = {"youtube_name_search_per_day": 100, "gmail_send_per_day": 500}


def today_start_utc(now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.timezone.utc)
    kst_midnight = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return kst_midnight.astimezone(dt.timezone.utc).replace(tzinfo=None)


def _guest_query(db):
    return db.query(models.User).filter(models.User.google_id.like(f"{GUEST_PREFIX}%"))


def _events_today(db, event_type: str, since: dt.datetime):
    return db.query(models.FlowExecutionLog).filter(
        models.FlowExecutionLog.event_type == event_type,
        models.FlowExecutionLog.execution_time >= since)


def overview(db) -> Dict[str, Any]:
    since = today_start_utc()
    guests = _guest_query(db).all()
    guest_ids = [g.id for g in guests]
    runs = _events_today(db, EVENT_WORKFLOW_EXECUTION, since).all()
    provider_counts: Dict[str, int] = {}
    for row in _events_today(db, demo_credentials.EVENT_TYPE, since).all():
        try:
            for provider in (json.loads(row.result or "{}").get("providers") or []):
                provider_counts[provider] = provider_counts.get(provider, 0) + 1
        except ValueError:
            continue
    guest_tokens_today = sum((r.total_tokens or 0) for r in runs if r.actor_user_id in guest_ids or r.user_id in guest_ids)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "day_start_utc": since.isoformat(),
        "guests": {
            "count": len(guests),
            "cap": demo_settings.get_int("DEMO_GUEST_MAX", 300),
            "entries_today": _events_today(db, EVENT_GUEST_ENTRY, since).count(),
            "registered_email": sum(1 for g in guests if g.email and not g.email.endswith("@demo.local")),
            "tokens_remaining_total": sum((g.token_balance or 0) for g in guests),
            "tokens_used_today": guest_tokens_today,
        },
        "runs_today": {
            "total": len(runs),
            "success": sum(1 for r in runs if (r.status or "success") == "success"),
            "failed": sum(1 for r in runs if (r.status or "success") != "success"),
            "by_trigger": _count_by(runs, lambda r: r.trigger_type or "editor"),
        },
        "emails_today": _events_today(db, EVENT_EMAIL_SENT, since).count(),
        "shared_credentials_today": provider_counts,
        "quotas": QUOTAS,
        "settings": demo_settings.snapshot(),
    }


def _count_by(rows, key) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        k = key(row)
        out[k] = out.get(k, 0) + 1
    return out


def guests(db) -> List[Dict[str, Any]]:
    rows = _guest_query(db).order_by(models.User.id.desc()).all()
    if not rows:
        return []
    ids = [g.id for g in rows]
    stats = dict()
    for uid, count, last in (db.query(models.FlowExecutionLog.actor_user_id, func.count(models.FlowExecutionLog.id),
                                      func.max(models.FlowExecutionLog.execution_time))
                             .filter(models.FlowExecutionLog.event_type == EVENT_WORKFLOW_EXECUTION,
                                     models.FlowExecutionLog.actor_user_id.in_(ids))
                             .group_by(models.FlowExecutionLog.actor_user_id).all()):
        stats[uid] = (count, last)
    return [{
        "id": g.id, "name": g.name, "email": g.email, "token_balance": g.token_balance,
        "registered": bool(g.email and not g.email.endswith("@demo.local")),
        "runs": stats.get(g.id, (0, None))[0],
        "last_run_at": stats.get(g.id, (0, None))[1].isoformat() if stats.get(g.id, (0, None))[1] else None,
    } for g in rows]


def cleanup_guests(db, *, keep_active_minutes: int = 0) -> Dict[str, Any]:
    """게스트 계정을 지운다(DELETE /api/users/me 와 같은 순서). keep_active_minutes 가 양수면 그 시간 안에
    실행 기록이 있는 게스트는 남긴다 — 부스에서 지금 쓰는 사람을 끊지 않기 위해서다."""
    rows = _guest_query(db).all()
    keep: set = set()
    if keep_active_minutes > 0:
        since = dt.datetime.utcnow() - dt.timedelta(minutes=keep_active_minutes)
        keep = {uid for (uid,) in db.query(models.FlowExecutionLog.actor_user_id)
                .filter(models.FlowExecutionLog.actor_user_id.in_([g.id for g in rows]) if rows else False,
                        models.FlowExecutionLog.execution_time >= since).distinct().all()}
    deleted = []
    for g in rows:
        if g.id in keep:
            continue
        db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.user_id == g.id) \
            .update({models.FlowExecutionLog.user_id: None}, synchronize_session=False)
        db.query(models.TrainingExample).filter(models.TrainingExample.user_id == g.id).delete(synchronize_session=False)
        db.query(models.GenerationTrace).filter(models.GenerationTrace.user_id == g.id).delete(synchronize_session=False)
        project_ids = [pid for (pid,) in db.query(models.Project.id).filter(models.Project.user_id == g.id)]
        if project_ids:
            db.query(models.BotLog).filter(models.BotLog.project_id.in_(project_ids)).delete(synchronize_session=False)
            db.query(models.Project).filter(models.Project.user_id == g.id).delete(synchronize_session=False)
        # ORM db.delete(user) 는 NOT NULL 인 document_formats.owner_user_id 를 NULL 로 바꾸려다 실패한다 —
        # 벌크 삭제로 DB 의 ondelete=CASCADE 에 맡긴다(정리 스크립트에서 실측).
        db.query(models.User).filter(models.User.id == g.id).delete(synchronize_session=False)
        deleted.append(g.id)
    db.commit()
    print(f"[demo-admin] 게스트 정리: 삭제 {len(deleted)}명, 유지 {len(keep)}명")
    return {"deleted": len(deleted), "kept_active": len(keep), "remaining": _guest_query(db).count()}


def recent_runs(db, limit: int = 30) -> List[Dict[str, Any]]:
    rows = (db.query(models.FlowExecutionLog)
            .filter(models.FlowExecutionLog.event_type == EVENT_WORKFLOW_EXECUTION)
            .order_by(models.FlowExecutionLog.execution_time.desc(), models.FlowExecutionLog.id.desc())
            .limit(max(1, min(limit, 200))).all())
    user_ids = {r.actor_user_id or r.user_id for r in rows if (r.actor_user_id or r.user_id)}
    project_ids = {r.project_id for r in rows if r.project_id}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()} if user_ids else {}
    projects = {p.id: p for p in db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()} if project_ids else {}
    out = []
    for r in rows:
        uid = r.actor_user_id or r.user_id
        u = users.get(uid)
        p = projects.get(r.project_id)
        out.append({
            "id": r.id, "time": r.execution_time.isoformat() if r.execution_time else None,
            "user_id": uid, "user_name": (u.name if u else None),
            "is_guest": bool(u and (u.google_id or "").startswith(GUEST_PREFIX)),
            "project_id": r.project_id, "project_title": (p.title if p else None),
            "status": r.status or "success", "trigger_type": r.trigger_type,
            "total_tokens": r.total_tokens or 0,
            "error": (r.error_message or "")[:200] or None,
        })
    return out
