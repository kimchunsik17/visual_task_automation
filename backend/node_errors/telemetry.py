"""node_errors/telemetry.py — 오류 code 별 운영 지표 (ADR-0016 ERROR-4.3).

NodeExecutionLog 의 telemetry 컬럼(error_code, error_category, effect_state, error_legacy)만
집계한다. 사용자 입력·provider 원문·경로는 컬럼에 없으므로 여기서도 나올 수 없다.

두 숫자가 결정에 쓰인다 —
  legacy_ratio     legacy 문구 비율. 이전율 게이트(문자열 검색 제거 시점)를 수치로 정한다.
  internal_unknown INTERNAL_UNKNOWN 이 어느 노드에서 반복되는지. 구체적 code 로 승격할 후보다.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func

import models


def summary(db, *, days: int = 7, limit: int = 20) -> Dict[str, Any]:
    since = datetime.datetime.utcnow() - datetime.timedelta(days=max(1, int(days)))
    base = db.query(models.NodeExecutionLog).filter(models.NodeExecutionLog.start_time >= since)
    total_steps = base.count()
    error_steps = base.filter(models.NodeExecutionLog.status == "error").count()
    structured = base.filter(models.NodeExecutionLog.error_code.isnot(None))
    structured_count = structured.count()
    legacy_count = structured.filter(models.NodeExecutionLog.error_legacy.is_(True)).count()

    def _group(*columns, where=None):
        query = db.query(*columns, func.count(models.NodeExecutionLog.id).label("count")).filter(
            models.NodeExecutionLog.start_time >= since,
            models.NodeExecutionLog.error_code.isnot(None),
        )
        if where is not None:
            query = query.filter(where)
        return query.group_by(*columns).order_by(func.count(models.NodeExecutionLog.id).desc()).limit(limit).all()

    by_code = [
        {"code": code, "category": category, "count": count}
        for code, category, count in _group(models.NodeExecutionLog.error_code, models.NodeExecutionLog.error_category)
    ]
    by_node_type = [
        {"node_type": node_type, "code": code, "count": count}
        for node_type, code, count in _group(models.NodeExecutionLog.node_type, models.NodeExecutionLog.error_code)
    ]
    by_effect_state = [
        {"effect_state": state, "count": count}
        for state, count in _group(models.NodeExecutionLog.effect_state)
    ]
    internal_unknown = [
        {"node_type": node_type, "count": count}
        for node_type, count in _group(models.NodeExecutionLog.node_type,
                                       where=models.NodeExecutionLog.error_code == "INTERNAL_UNKNOWN")
    ]
    return {
        "since": since.isoformat(),
        "total_steps": total_steps,
        "error_steps": error_steps,
        "structured_error_steps": structured_count,
        "legacy_error_steps": legacy_count,
        "legacy_ratio": round(legacy_count / structured_count, 4) if structured_count else 0.0,
        "by_code": by_code,
        "by_node_type": by_node_type,
        "by_effect_state": by_effect_state,
        "internal_unknown_by_node_type": internal_unknown,
    }
