"""message_stream.py — 쪽지 실시간 전달 (ADR-0022, 우선 백로그 24 MSG-2).

**SSE 를 고른 이유.** 양방향 WebSocket 은 인증·재연결·sticky session·배포 구성이 함께 따라온다.
쪽지는 본질적으로 "받는 스트림 + 보내는 요청"이라 서버 → 클라이언트 단방향(SSE) + POST 전송으로
충분하다. 폴링은 지연과 부하를 동시에 나쁘게 만들어 채택하지 않았다.

**DB 가 정본이고 브로커는 지연 최적화다.** 스트림 루프는 깨어날 때마다 DB 에서 `last_id` 이후의
메시지를 읽는다. 깨우는 것은 (a) 같은 프로세스의 전송 신호(즉시) 또는 (b) 하트비트 타임아웃이다.
그래서 워커가 여러 개여서 브로커 신호를 놓쳐도 **하트비트 주기 안에 반드시 전달된다** — 인메모리
브로커에만 기대면 워커가 늘어나는 순간 조용히 유실된다.

**배포 구성이 필요하다.** nginx 가 `proxy_buffering` 을 켠 채로 두면 이벤트가 버퍼에 갇혀 늦게
도착한다. 응답에 `X-Accel-Buffering: no` 를 넣어 nginx 에 직접 알리고, 배포 문서에도 남긴다.
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
from typing import AsyncIterator, Dict, Optional, Set

# 하트비트 겸 DB 재확인 주기. 브로커 신호를 놓친 경우의 **최대 지연**이 이 값이다.
HEARTBEAT_SECONDS = 15.0
# 한 사용자가 동시에 열 수 있는 스트림 수. 탭을 여러 개 열 수 있어야 하지만 무제한은 아니다.
MAX_STREAMS_PER_USER = 4
MAX_CATCHUP = 100

_waiters: Dict[int, Set[asyncio.Event]] = collections.defaultdict(set)


def enabled() -> bool:
    return os.getenv("MESSAGING_V1", "1").strip().lower() not in {"0", "false", "off", "no"}


def stream_count(user_id: int) -> int:
    return len(_waiters.get(user_id, ()))


def publish(user_ids) -> None:
    """전송 직후 호출한다. 같은 프로세스의 대기자를 깨울 뿐, **전달을 보장하는 것은 DB 다.**"""
    for user_id in user_ids:
        for event in list(_waiters.get(int(user_id), ())):
            event.set()


def _sse(event: str, data, event_id: Optional[int] = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def _fetch_new(db_factory, user_id: int, last_id: int):
    """`last_id` 이후 내가 받아야 할 메시지. 차단·참가자 판정은 messaging 이 이미 한 규칙을 따른다."""
    import messaging
    import models

    db = db_factory()
    try:
        member_ids = [m.conversation_id for m in db.query(models.ConversationMember).filter(
            models.ConversationMember.user_id == user_id).all()]
        if not member_ids:
            return []
        rows = db.query(models.Message).filter(
            models.Message.conversation_id.in_(member_ids),
            models.Message.id > last_id,
            models.Message.sender_id != user_id,
        ).order_by(models.Message.id.asc()).limit(MAX_CATCHUP).all()

        payload = []
        for row in rows:
            conversation = db.query(models.Conversation).filter(
                models.Conversation.id == row.conversation_id).first()
            if conversation is None:
                continue
            other_id = messaging.other_participant(conversation, user_id)
            # **구독도 전송과 같은 판정을 쓴다.** 전송만 막고 구독을 열어 두면 차단한 상대의
            # 메시지가 스트림으로 흘러 들어온다.
            if not messaging.can_message(db, user_id, other_id):
                continue
            if user_id in (row.deleted_for_user_ids or []):
                continue
            payload.append(messaging.public_message(row, user_id))
        return payload
    finally:
        db.close()


async def event_stream(db_factory, user_id: int, last_event_id: int = 0) -> AsyncIterator[str]:
    """SSE 본문. 재연결은 정상 동작이지 예외가 아니다 — `Last-Event-ID` 로 놓친 구간을 메운다."""
    waiter = asyncio.Event()
    _waiters[user_id].add(waiter)
    last_id = int(last_event_id or 0)
    try:
        yield _sse("ready", {"lastEventId": last_id, "heartbeatSeconds": HEARTBEAT_SECONDS})
        while True:
            # DB 를 먼저 읽는다 — 브로커 신호를 놓쳤어도 여기서 메운다.
            new_messages = await asyncio.to_thread(_fetch_new, db_factory, user_id, last_id)
            for message in new_messages:
                last_id = max(last_id, message["id"])
                yield _sse("message", message, event_id=message["id"])

            waiter.clear()
            try:
                await asyncio.wait_for(waiter.wait(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                # 하트비트는 주석 줄이다. 프록시가 연결을 끊지 않게 하고, 동시에 DB 재확인을 부른다.
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        raise
    finally:
        _waiters[user_id].discard(waiter)
        if not _waiters[user_id]:
            _waiters.pop(user_id, None)
