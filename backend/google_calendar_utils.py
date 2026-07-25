"""
google_calendar_utils.py — googleCalendarNode가 쓰는 구글 캘린더 읽기/쓰기 헬퍼.

google_sheets_utils.py와 동일한 서비스 계정(GOOGLE_SERVICE_ACCOUNT_JSON)을 그대로 재사용한다 —
사용자는 다룰 캘린더를 그 서비스 계정 이메일과 "공유"(일정 변경 권한)만 해두면 된다. 시트와
스코프만 다를 뿐(calendar), 새로 인증을 설정할 필요가 없다.

무거운 google-api-python-client SDK 대신, 이미 설치돼 있는 google-auth의
AuthorizedSession(자동 토큰 갱신 포함)으로 캘린더 REST API를 직접 호출한다 — 이 코드베이스의
다른 연동 노드(discordNode/telegramNode/kakaoNode)들이 전부 requests로 REST API를 직접 호출하는
방식과 일관성을 맞췄다.

설정 방법(구글 시트와 동일한 서비스 계정을 이미 등록해뒀다면 추가 설정 없음):
  1. (아직 안 했다면) google_sheets_utils.py 상단 설명대로 서비스 계정을 만들고
     backend/.env의 GOOGLE_SERVICE_ACCOUNT_JSON에 등록한다.
  2. 사용할 구글 캘린더를 열어 설정 > "특정 사용자와 공유"에서 그 서비스 계정 이메일을
     "일정 변경" 권한으로 추가한다.
  3. 캘린더 설정 페이지에 있는 "캘린더 ID"(보통 본인 gmail 주소이거나
     ...@group.calendar.google.com 형식)를 googleCalendarNode의 calendarId에 넣는다.
"""
import json
import os
import datetime

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_API_BASE = "https://www.googleapis.com/calendar/v3"

_session = None
_session_error = None


def _load_session():
    global _session, _session_error
    if _session is not None or _session_error is not None:
        return _session

    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    try:
        if raw_json:
            info = json.loads(raw_json)
            creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
        elif key_file and os.path.exists(key_file):
            creds = Credentials.from_service_account_file(key_file, scopes=_SCOPES)
        else:
            _session_error = (
                "Google 서비스 계정이 설정되지 않았습니다 — backend/.env에 "
                "GOOGLE_SERVICE_ACCOUNT_JSON(서비스 계정 키 JSON 전체) 또는 "
                "GOOGLE_SERVICE_ACCOUNT_FILE(키 파일 경로)을 등록해주세요."
            )
            return None
        _session = AuthorizedSession(creds)
    except Exception as e:
        _session_error = f"Google 서비스 계정 인증 실패: {e}"
        return None
    return _session


def is_configured() -> bool:
    return _load_session() is not None


def _check(resp, calendar_id):
    if resp.status_code >= 400:
        raise RuntimeError(
            f"캘린더 요청이 실패했습니다({calendar_id}): {resp.status_code} {resp.text[:300]}. "
            "캘린더를 서비스 계정 이메일과 공유(일정 변경 권한)했는지, 캘린더 ID가 맞는지 확인해주세요."
        )


def list_events(calendar_id: str, time_min: str = None, time_max: str = None, max_results: int = 10) -> list:
    session = _load_session()
    if session is None:
        raise RuntimeError(_session_error)
    params = {
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": time_min or (datetime.datetime.utcnow().isoformat() + "Z"),
    }
    if time_max:
        params["timeMax"] = time_max
    resp = session.get(f"{_API_BASE}/calendars/{calendar_id}/events", params=params, timeout=10)
    _check(resp, calendar_id)
    items = resp.json().get("items", [])
    return [
        {
            "id": ev.get("id"),
            "summary": ev.get("summary", ""),
            "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date"),
            "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date"),
            "location": ev.get("location", ""),
            "htmlLink": ev.get("htmlLink", ""),
        }
        for ev in items
    ]


def create_event(calendar_id: str, event: dict) -> dict:
    """event는 최소한 summary/start/end가 있어야 한다. start/end는 그냥 문자열(ISO datetime,
    타임존 포함 예: "2026-08-01T10:00:00+09:00")로 주면 알아서 {"dateTime": ...} 형태로 감싼다 —
    이미 {"dateTime":...} 형태의 dict로 줘도 그대로 통과시킨다(하루 종일 일정의 {"date":...}
    형태도 지원하기 위함)."""
    session = _load_session()
    if session is None:
        raise RuntimeError(_session_error)

    def _wrap_time(v):
        if isinstance(v, dict):
            return v
        return {"dateTime": v}

    body = {
        "summary": event.get("summary", "제목 없음"),
    }
    if event.get("description"):
        body["description"] = event["description"]
    if event.get("location"):
        body["location"] = event["location"]
    if event.get("start"):
        body["start"] = _wrap_time(event["start"])
    if event.get("end"):
        body["end"] = _wrap_time(event["end"])

    resp = session.post(f"{_API_BASE}/calendars/{calendar_id}/events", json=body, timeout=10)
    _check(resp, calendar_id)
    created = resp.json()
    return {
        "id": created.get("id"),
        "summary": created.get("summary", ""),
        "htmlLink": created.get("htmlLink", ""),
        "start": created.get("start", {}).get("dateTime") or created.get("start", {}).get("date"),
        "end": created.get("end", {}).get("dateTime") or created.get("end", {}).get("date"),
    }
