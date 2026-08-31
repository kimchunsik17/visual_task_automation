"""Statistics aggregation with explicit period and billing semantics."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import models
from usage_tracking import EVENT_WORKFLOW_EXECUTION, legacy_event_type, usage_bucket, usage_outcome


VALID_TIME_RANGES = {"hourly", "weekly", "monthly", "yearly"}


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unsupported timezone: {name}") from exc


def _month_start(value: dt.datetime, months_delta: int) -> dt.datetime:
    month_index = value.year * 12 + value.month - 1 + months_delta
    year, zero_based_month = divmod(month_index, 12)
    return value.replace(year=year, month=zero_based_month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def period_definition(time_range: str, timezone_name: str, now: Optional[dt.datetime] = None) -> dict:
    if time_range not in VALID_TIME_RANGES:
        raise ValueError(f"Unsupported time range: {time_range}")

    timezone = resolve_timezone(timezone_name)
    now_utc = now or dt.datetime.now(dt.timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.timezone.utc)
    local_now = now_utc.astimezone(timezone)

    if time_range == "hourly":
        current_bucket = local_now.replace(minute=0, second=0, microsecond=0)
        start_local = current_bucket - dt.timedelta(hours=23)
        end_local = current_bucket + dt.timedelta(hours=1)
        step = "hour"
        bucket_count = 24
    elif time_range == "weekly":
        current_bucket = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = current_bucket - dt.timedelta(days=6)
        end_local = current_bucket + dt.timedelta(days=1)
        step = "day"
        bucket_count = 7
    elif time_range == "monthly":
        current_bucket = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = current_bucket - dt.timedelta(days=29)
        end_local = current_bucket + dt.timedelta(days=1)
        step = "day"
        bucket_count = 30
    else:
        current_bucket = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_local = _month_start(current_bucket, -11)
        end_local = _month_start(current_bucket, 1)
        step = "month"
        bucket_count = 12

    duration = end_local.astimezone(dt.timezone.utc) - start_local.astimezone(dt.timezone.utc)
    previous_end_local = start_local
    previous_start_utc = previous_end_local.astimezone(dt.timezone.utc) - duration

    return {
        "timezone": timezone,
        "start_local": start_local,
        "end_local": end_local,
        "start_utc": start_local.astimezone(dt.timezone.utc).replace(tzinfo=None),
        "end_utc": end_local.astimezone(dt.timezone.utc).replace(tzinfo=None),
        "previous_start_utc": previous_start_utc.replace(tzinfo=None),
        "previous_end_utc": previous_end_local.astimezone(dt.timezone.utc).replace(tzinfo=None),
        "step": step,
        "bucket_count": bucket_count,
    }


def _billable_filter(user_id: int):
    return or_(
        models.FlowExecutionLog.billable_user_id == user_id,
        and_(
            models.FlowExecutionLog.billable_user_id.is_(None),
            models.FlowExecutionLog.user_id == user_id,
        ),
    )


def _as_local(value: Optional[dt.datetime], timezone: ZoneInfo) -> Optional[dt.datetime]:
    if value is None:
        return None
    aware = value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone)


def _bucket_key(value: dt.datetime, step: str) -> str:
    if step == "hour":
        return value.strftime("%Y-%m-%d %H:00")
    if step == "month":
        return value.strftime("%Y-%m")
    return value.date().isoformat()


def _bucket_label(key: str, step: str) -> str:
    if step == "hour":
        return key[-5:]
    if step == "month":
        return key
    return key[-5:]


def _bucket_starts(period: dict):
    current = period["start_local"]
    for _ in range(period["bucket_count"]):
        yield current
        if period["step"] == "hour":
            current += dt.timedelta(hours=1)
        elif period["step"] == "day":
            current += dt.timedelta(days=1)
        else:
            current = _month_start(current, 1)


def build_statistics(
    db: Session,
    user: models.User,
    *,
    time_range: str = "weekly",
    timezone_name: str = "Asia/Seoul",
    now: Optional[dt.datetime] = None,
) -> dict:
    period = period_definition(time_range, timezone_name, now)
    ownership = _billable_filter(user.id)

    period_logs = (
        db.query(models.FlowExecutionLog)
        .filter(
            ownership,
            models.FlowExecutionLog.execution_time >= period["start_utc"],
            models.FlowExecutionLog.execution_time < period["end_utc"],
        )
        .order_by(models.FlowExecutionLog.execution_time.asc())
        .all()
    )

    empty_bucket = lambda: {"execution": 0, "agent": 0, "app_builder": 0, "evaluation": 0}
    buckets = {_bucket_key(start, period["step"]): empty_bucket() for start in _bucket_starts(period)}
    usage_by_type = empty_bucket()
    project_totals = defaultdict(int)
    execution_count = 0
    successful_executions = 0

    for log in period_logs:
        total = max(0, int(log.total_tokens or 0))
        category = usage_bucket(log.event_type, log.status, log.token_usage_details)
        usage_by_type[category] += total
        project_totals[log.project_id] += total

        local_time = _as_local(log.execution_time, period["timezone"])
        key = _bucket_key(local_time, period["step"]) if local_time else None
        if key in buckets:
            buckets[key][category] += total

        normalized_type = log.event_type or legacy_event_type(log.status, log.token_usage_details)
        if normalized_type == EVENT_WORKFLOW_EXECUTION:
            execution_count += 1
            if usage_outcome(log.outcome, log.status, log.error_message) == "success":
                successful_executions += 1

    period_total = sum(usage_by_type.values())
    previous_total = (
        db.query(func.sum(models.FlowExecutionLog.total_tokens))
        .filter(
            ownership,
            models.FlowExecutionLog.execution_time >= period["previous_start_utc"],
            models.FlowExecutionLog.execution_time < period["previous_end_utc"],
        )
        .scalar()
        or 0
    )
    lifetime_used = db.query(func.sum(models.FlowExecutionLog.total_tokens)).filter(ownership).scalar() or 0

    project_ids = [project_id for project_id in project_totals if project_id is not None]
    project_titles = {}
    if project_ids:
        project_titles = dict(
            db.query(models.Project.id, models.Project.title)
            .filter(models.Project.id.in_(project_ids))
            .all()
        )

    project_usage = []
    deleted_total = 0
    for project_id, total in project_totals.items():
        if total <= 0:
            continue
        if project_id is None:
            project_usage.append({"project_id": None, "title": "미지정 프로젝트", "tokens": total})
        elif project_id in project_titles:
            project_usage.append({"project_id": project_id, "title": project_titles[project_id], "tokens": total})
        else:
            deleted_total += total
    if deleted_total:
        project_usage.append({"project_id": -1, "title": "삭제된 프로젝트", "tokens": deleted_total})
    project_usage.sort(key=lambda item: item["tokens"], reverse=True)

    chart_data = [
        {
            "date": _bucket_label(key, period["step"]),
            "fullDate": key,
            "tokens": sum(values.values()),
            **values,
        }
        for key, values in buckets.items()
    ]
    change_rate = None if previous_total == 0 else (period_total - previous_total) / previous_total
    success_rate = None if execution_count == 0 else successful_executions / execution_count

    return {
        # Compatibility fields used by the current page and older clients.
        "total_used": period_total,
        "remaining": int(user.token_balance or 0),
        "total_allocated": int(user.token_balance or 0) + int(lifetime_used),
        "chart_data": chart_data,
        "project_usage": project_usage,
        "usage_by_type": usage_by_type,
        "period": {
            "preset": time_range,
            "from": period["start_local"].isoformat(),
            "to": period["end_local"].isoformat(),
            "timezone": timezone_name,
            "granularity": period["step"],
        },
        "summary": {
            "period_tokens": period_total,
            "previous_period_tokens": int(previous_total),
            "change_rate": change_rate,
            "remaining_tokens": int(user.token_balance or 0),
            "lifetime_tokens": int(lifetime_used),
            "execution_count": execution_count,
            "success_rate": success_rate,
        },
        "cost": {
            "usd_micros": None,
            "kind": "unavailable",
            "pricing_version": None,
        },
        "meta": {
            "has_usage": bool(period_logs),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    }
