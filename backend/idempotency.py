"""idempotency.py — 트리거 중복 제거 키 (백로그 32 ENGINE-3 4단계, ADR-0030 추기).

왜
  발신자(GitHub·GitLab·결제/폼 서비스)는 2xx 를 못 받으면 같은 이벤트를 다시 보낸다. 재전송마다 워크플로우가 돌면 메일이 두 통 나간다.
  같은 이벤트는 run 하나 — `workflow_runs.idempotency_key`(unique, 0024 부터 자리)가 그것을 못 박는다. 스케줄 슬롯 키(ENGINE-2 3단계)와
  같은 컬럼을 쓴다.

키를 어디서 읽나
  1. 발신자가 준 전달 id 헤더(`X-GitHub-Delivery`, `X-GitLab-Event-UUID`, `Idempotency-Key`, `X-Idempotency-Key`) — 재전송은 같은 id 다.
  2. 헤더가 없으면 **webhookNode 설정 `dedupeByPayload`** 가 켜진 경우에만 payload 해시(sha256, 키 정렬). 기본은 꺼짐 — 같은 본문이
     며칠 뒤 다시 오는 것이 정당한 새 이벤트인 웹훅(폼 제출 등)이 있고, unique 는 영구라 시간 창이 없다.
  3. 둘 다 없으면 None — 중복 제거 없이 실행한다(예전과 같다).

RSS 항목 id 는 rssTriggerNode 의 cursor(SEEN_WINDOW)가 이미 같은 일을 한다 — 여기 두지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

DELIVERY_HEADERS = ("X-GitHub-Delivery", "X-GitLab-Event-UUID", "Idempotency-Key", "X-Idempotency-Key")
DEDUPE_PAYLOAD_KEY = "dedupeByPayload"     # webhookNode data
MAX_HEADER_VALUE = 200


def _header(headers: Optional[Mapping[str, str]], name: str) -> Optional[str]:
    if not headers:
        return None
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    if value is None:  # 대소문자 무시 — Starlette Headers 는 이미 그렇지만 dict 로 받을 때를 위해
        lowered = {str(k).lower(): v for k, v in headers.items()}
        value = lowered.get(name.lower())
    value = str(value).strip() if value is not None else ""
    return value[:MAX_HEADER_VALUE] or None


def payload_digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def dedupe_by_payload(node: Optional[dict]) -> bool:
    data = (node or {}).get("data") or {}
    value = data.get(DEDUPE_PAYLOAD_KEY)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes"}
    return bool(value)


def webhook_key(project_id, headers: Optional[Mapping[str, str]], payload: Any, *, node: Optional[dict] = None) -> Optional[str]:
    """웹훅 한 번의 idempotency_key. 전달 id 헤더 → (설정 시) payload 해시 → None."""
    for name in DELIVERY_HEADERS:
        value = _header(headers, name)
        if value:
            return f"webhook:{project_id}:{name.lower()}:{value}"
    if dedupe_by_payload(node):
        return f"webhook:{project_id}:sha256:{payload_digest(payload)}"
    return None
