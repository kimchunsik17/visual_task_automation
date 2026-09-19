"""cron_helper.py — 한국어 → cron, 다음 실행 미리보기 (백로그 34 DEV-2 cronHelper, ADR-0034).

scheduleNode 는 cron 표현식 하나(`data.cronExpression`)를 받는다. 사용자는 "평일 오전 9시 30분" 처럼 말하고 싶고, 무엇보다 **자기가 적은
표현식이 언제 도는지** 알고 싶다. 여기서 둘을 한다.

  parse_korean(text)      규칙 기반 — 매일/평일/주말/매주 요일/매월 N일/매시간/N분마다 + 시각(오전·오후·정오·자정·H시 M분·HH:MM).
                          못 알아들으면 None. 결정적이라 테스트로 고정한다.
  suggest(text)           규칙이 실패하면 LLM(구조화 출력)에 맡기되, 결과를 CronTrigger 로 **검증**하고 다음 실행 시각을 함께 돌려준다.
  next_runs(expr)         APScheduler 의 CronTrigger 로 다음 N회 — 스케줄러(scheduler.py)와 같은 해석기를 쓰므로 미리보기와 실제가 어긋나지 않는다.
  describe(expr)          흔한 모양(매일/매주/매월/매시간/N분마다)을 한국어 한 문장으로.

시간대는 스케줄러와 같은 서버 로컬(기본 Asia/Seoul). 초 단위·`L`·`#` 같은 확장은 다루지 않는다 — from_crontab 이 받지 않는다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

DEFAULT_TZ = "Asia/Seoul"
DEFAULT_HOUR = 9
MAX_TEXT_CHARS = 200
WEEKDAYS = {"일": 0, "월": 1, "화": 2, "수": 3, "목": 4, "금": 5, "토": 6}
WEEKDAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"]


class CronHelperError(ValueError):
    """사용자에게 그대로 보여도 되는 실패."""


# ── 검증·미리보기 ──────────────────────────────────────────────────────────

_APS_DAY_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
_DOW_RANGE = re.compile(r"^(\d)(?:-(\d))?(?:/(\d+))?$")


def _convert_dow(field: str) -> str:
    """표준 crontab 요일(0/7=일 … 6=토) → APScheduler 이름.

    APScheduler 3.x 의 `CronTrigger.from_crontab` 은 **역사적 실수로 0 을 월요일**로 읽는다(공식 문서 경고, issue 286). 그대로 쓰면 편집기가
    만든 `… * * 1`(월요일)이 화요일에 돈다. 숫자 토큰을 이름 목록으로 펼쳐 넘기면 해석이 하나로 고정된다. `*`·`*/n`·이미 이름인 토큰은 그대로.
    """
    tokens = []
    for raw in str(field).split(","):
        token = raw.strip()
        if not token or token == "*" or token.startswith("*/") or not token[0].isdigit():
            tokens.append(token)
            continue
        m = _DOW_RANGE.match(token)
        if not m:
            tokens.append(token)
            continue
        start, end, step = int(m.group(1)), (int(m.group(2)) if m.group(2) else None), int(m.group(3) or 1)
        if start > 7 or (end is not None and end > 7) or step < 1:
            tokens.append(token)          # 검증 단계에서 APScheduler 가 거절하게 둔다
            continue
        stop = end if end is not None else start
        days = list(range(start, stop + 1, step)) if stop >= start else list(range(start, 8)) + list(range(0, stop + 1))
        tokens.extend(_APS_DAY_NAMES[d % 7] for d in days)
    seen: List[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return ",".join(seen)


def to_trigger(expr: str, timezone: Any = None):
    """5칸 crontab 문자열 → APScheduler CronTrigger — **표준 요일 번호(0=일요일)** 로. 스케줄러(scheduler.py)와 미리보기가 같은 함수를 쓴다.
    틀리면 ValueError(APScheduler 문구 그대로)."""
    from apscheduler.triggers.cron import CronTrigger

    values = str(expr or "").split()
    if len(values) != 5:
        raise ValueError(f"Wrong number of fields; got {len(values)}, expected 5")
    minute, hour, day, month, dow = values
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=_convert_dow(dow), timezone=timezone)


def validate(expr: str):
    """5칸 cron 을 CronTrigger 로. 틀리면 CronHelperError."""
    text = str(expr or "").strip()
    if not text:
        raise CronHelperError("cron 표현식이 비어 있습니다.")
    if len(text.split()) != 5:
        raise CronHelperError("cron 은 '분 시 일 월 요일' 다섯 칸이어야 합니다.")
    try:
        return to_trigger(text, timezone=DEFAULT_TZ)
    except (ValueError, TypeError) as exc:
        raise CronHelperError(f"cron 표현식이 잘못됐습니다: {exc}") from None


def next_runs(expr: str, *, count: int = 5, now: Optional[datetime.datetime] = None) -> List[str]:
    trigger = validate(expr)
    import zoneinfo

    tz = zoneinfo.ZoneInfo(DEFAULT_TZ)
    # CronTrigger 는 now 와 같은 시각도 "다음" 으로 돌려준다 — 미리보기는 '지금 이후' 여야 하므로 1초 뒤부터 본다.
    current = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz) + datetime.timedelta(seconds=1)
    runs: List[str] = []
    previous = None
    for _ in range(max(1, min(int(count), 20))):
        nxt = trigger.get_next_fire_time(previous, current if previous is None else previous)
        if nxt is None:
            break
        runs.append(nxt.isoformat())
        previous = nxt
    return runs


def _num(value: str) -> Optional[int]:
    return int(value) if re.fullmatch(r"\d+", value or "") else None


def _dow_label(field: str) -> Optional[str]:
    if field == "*":
        return "매일"
    if field in ("1-5", "1,2,3,4,5"):
        return "평일"
    if field in ("0,6", "6,0"):
        return "주말"
    parts = []
    for token in field.split(","):
        if re.fullmatch(r"[0-6]", token):
            parts.append(WEEKDAY_NAMES[int(token)])
        elif re.fullmatch(r"[0-6]-[0-6]", token):
            a, b = token.split("-")
            parts.append("~".join(WEEKDAY_NAMES[int(x)] for x in (a, b)))
        else:
            return None
    return "매주 " + "·".join(parts) + "요일"


def _time_label(hour: int, minute: int) -> str:
    if hour == 0 and minute == 0:
        return "자정"
    if hour == 12 and minute == 0:
        return "정오"
    meridiem = "오전" if hour < 12 else "오후"
    h12 = hour if hour <= 12 else hour - 12
    if h12 == 0:
        h12 = 12
    return f"{meridiem} {h12}시" + (f" {minute}분" if minute else "")


def describe(expr: str) -> str:
    """흔한 모양만 한국어로. 그 밖은 표현식을 그대로 돌려준다(틀린 설명보다 낫다)."""
    try:
        validate(expr)
    except CronHelperError:
        return str(expr or "")
    minute, hour, dom, month, dow = str(expr).split()
    m, h = _num(minute), _num(hour)
    if month != "*":
        return expr
    if minute.startswith("*/") and hour == "*" and dom == "*" and dow == "*":
        return f"{minute[2:]}분마다"
    if minute == "*" and hour == "*" and dom == "*" and dow == "*":
        return "매분"
    if m is not None and hour.startswith("*/") and dom == "*" and dow == "*":
        return f"{hour[2:]}시간마다 ({m}분)"
    if m is not None and hour == "*" and dom == "*" and dow == "*":
        return f"매시간 {m}분"
    if m is not None and h is not None:
        when = _time_label(h, m)
        if dom == "*" and dow == "*":
            return f"매일 {when}"
        if dom == "*":
            label = _dow_label(dow)
            if label:
                return f"{label} {when}"
        if dow == "*" and _num(dom) is not None:
            return f"매월 {int(dom)}일 {when}"
    return expr


# ── 한국어 → cron (규칙) ────────────────────────────────────────────────────

_TIME_HHMM = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")
_TIME_KO = re.compile(r"(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?(?:\s*반)?")
_EVERY_MIN = re.compile(r"(?:매\s*)?(\d{1,3})\s*분\s*(?:마다|간격|에\s*한\s*번)")
_EVERY_HOUR = re.compile(r"(?:매\s*)?(\d{1,2})\s*시간\s*(?:마다|간격|에\s*한\s*번)")
_MONTHLY = re.compile(r"매\s*(?:월|달)\s*(\d{1,2})\s*일")
_WEEKDAYS_TOKEN = re.compile(r"([일월화수목금토](?:\s*[,·/및와과]?\s*[일월화수목금토])*)\s*요일")
# "매주 월,수,금 10시" 처럼 '요일' 을 생략하는 말도 흔하다 — '매주' 뒤의 요일 글자 묶음을 본다.
_WEEKDAYS_AFTER_EVERY_WEEK = re.compile(r"매\s*주\s*([일월화수목금토](?:\s*[,·/및와과]?\s*[일월화수목금토])*)")


def _parse_time(text: str) -> Optional[tuple]:
    """(hour, minute). 오전/오후/새벽/저녁/밤/정오/자정 을 본다. 없으면 None."""
    if "정오" in text:
        return 12, 0
    if "자정" in text:
        return 0, 0
    m = _TIME_HHMM.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = _TIME_KO.search(text)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else (30 if "반" in m.group(0) else 0)
    before = text[:m.start()]
    pm = any(word in before for word in ("오후", "저녁", "밤"))
    am = any(word in before for word in ("오전", "아침", "새벽"))
    if pm and hour < 12:
        hour += 12
    if am and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _parse_days(text: str) -> Optional[str]:
    if "평일" in text:
        return "1-5"
    if "주말" in text:
        return "0,6"
    m = _WEEKDAYS_TOKEN.search(text) or _WEEKDAYS_AFTER_EVERY_WEEK.search(text)
    if m:
        days = sorted({WEEKDAYS[ch] for ch in m.group(1) if ch in WEEKDAYS})
        if days:
            return ",".join(str(d) for d in days)
    if re.search(r"매\s*주(?!\s*[일월화수목금토])", text):
        return "1"          # 요일 없는 '매주' 는 월요일로
    return None


def parse_korean(text: str) -> Optional[Dict[str, Any]]:
    """{cron, explanation, assumedTime} 또는 None(규칙으로 못 알아들음)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return None
    m = _EVERY_MIN.search(text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 59:
            return {"cron": f"*/{n} * * * *", "explanation": f"{n}분마다", "assumedTime": False}
    m = _EVERY_HOUR.search(text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 23:
            return {"cron": f"0 */{n} * * *", "explanation": f"{n}시간마다(정각)", "assumedTime": False}
    if re.search(r"매\s*시간|한\s*시간\s*마다|시간마다", text):
        return {"cron": "0 * * * *", "explanation": "매시간 정각", "assumedTime": False}

    # 규칙으로 정확히 옮길 수 없는 말은 억지로 맞추지 않는다 — "매월 마지막 날", "격주", "첫째 월요일" 은 표준 5칸 cron 으로 표현되지 않거나
    # 해석이 갈린다. None 을 돌려 LLM 폴백(검증 포함)으로 보낸다.
    if re.search(r"격\s*주|마지막\s*(날|일)|말일|첫째|둘째|셋째|넷째|영업일|분기|반기|매년|매\s*해", text):
        return None
    if re.search(r"매\s*(월|달)", text) and not _MONTHLY.search(text):
        return None

    parsed_time = _parse_time(text)
    hour, minute = parsed_time if parsed_time else (DEFAULT_HOUR, 0)
    assumed = parsed_time is None
    when = _time_label(hour, minute)

    monthly = _MONTHLY.search(text)
    if monthly:
        day = int(monthly.group(1))
        if 1 <= day <= 31:
            return {"cron": f"{minute} {hour} {day} * *", "explanation": f"매월 {day}일 {when}", "assumedTime": assumed}
    days = _parse_days(text)
    if days:
        label = _dow_label(days) or "매주"
        return {"cron": f"{minute} {hour} * * {days}", "explanation": f"{label} {when}", "assumedTime": assumed}
    if re.search(r"매일|하루에\s*한\s*번|매\s*아침|아침마다|저녁마다|밤마다|날마다", text) or parsed_time:
        return {"cron": f"{minute} {hour} * * *", "explanation": f"매일 {when}", "assumedTime": assumed}
    return None


# ── LLM 폴백 ──────────────────────────────────────────────────────────────

_SYSTEM = (
    "너는 한국어 일정 설명을 5칸 cron(분 시 일 월 요일, 표준 crontab, 초 없음, L/#/W 없음)으로 바꾸는 도우미다. "
    "요일은 0=일요일 … 6=토요일. 시간대는 Asia/Seoul 로 이미 맞춰져 있으니 변환하지 않는다. 시각이 없으면 오전 9시로 두고 그 사실을 explanation 에 적는다. "
    "explanation 은 한국어 한 문장."
)


class SuggestedCron(BaseModel):
    cron: str = Field(description="5칸 cron 표현식")
    explanation: str = Field(default="", description="언제 도는지 한국어 한 문장")


def _default_llm():
    from meta_agent import get_llm

    return get_llm(complexity_level="low").with_structured_output(SuggestedCron, method="function_calling")


def suggest(text: str, *, llm: Any = None, allow_llm: bool = True, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """{cron, explanation, next[], source('rules'|'llm'), assumedTime}. 실패는 CronHelperError."""
    text = str(text or "").strip()
    if not text:
        raise CronHelperError("일정을 말로 적어 주세요 — 예: 평일 오전 9시 30분.")
    if len(text) > MAX_TEXT_CHARS:
        raise CronHelperError(f"설명이 너무 깁니다(상한 {MAX_TEXT_CHARS}자).")
    parsed = parse_korean(text)
    if parsed is not None:
        validate(parsed["cron"])
        return {**parsed, "source": "rules", "next": next_runs(parsed["cron"], now=now)}
    if not allow_llm:
        raise CronHelperError("규칙으로 알아듣지 못한 표현입니다. 예: '매일 오전 9시', '평일 18시 30분', '매주 월·수 10시', '매월 1일 9시', '30분마다'.")
    llm = llm or _default_llm()
    candidate = llm.invoke([("system", _SYSTEM), ("user", f"일정: {text}")])
    if not isinstance(candidate, SuggestedCron):
        candidate = SuggestedCron.model_validate(candidate if isinstance(candidate, dict) else getattr(candidate, "__dict__", {}))
    validate(candidate.cron)
    return {"cron": candidate.cron.strip(), "explanation": candidate.explanation or describe(candidate.cron), "assumedTime": False,
            "source": "llm", "next": next_runs(candidate.cron, now=now)}


def preview(expr: str, *, count: int = 5, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    return {"cron": str(expr or "").strip(), "description": describe(expr), "next": next_runs(expr, count=count, now=now)}
