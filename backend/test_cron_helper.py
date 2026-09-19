"""cronHelper (백로그 34 DEV-2, ADR-0034) — 한국어 → cron 규칙, 미리보기, LLM 폴백 계약 테스트.

  1. **규칙은 결정적이다.** 흔한 한국어 일정 표현이 정해진 cron 으로 바뀐다. 못 알아들으면 None — 억지로 맞추지 않는다.
  2. **미리보기는 스케줄러와 같은 해석기.** APScheduler CronTrigger 로 다음 N회를 계산한다(Asia/Seoul).
  3. **LLM 폴백도 검증을 거친다.** 만들어 준 cron 이 틀리면 실패로 드러난다.
"""

from __future__ import annotations

import datetime

import pytest

import cron_helper as ch

NOW = datetime.datetime(2026, 9, 19, 3, 0, tzinfo=datetime.timezone.utc)   # 토요일 12:00 KST


@pytest.mark.parametrize("text, cron", [
    ("매일 오전 9시", "0 9 * * *"),
    ("매일 9시 30분", "30 9 * * *"),
    ("매일 오후 6시", "0 18 * * *"),
    ("매일 18:45", "45 18 * * *"),
    ("매일 정오", "0 12 * * *"),
    ("매일 자정", "0 0 * * *"),
    ("매일 저녁 8시 반", "30 20 * * *"),
    ("매일 새벽 12시", "0 0 * * *"),
    ("평일 오전 9시 30분", "30 9 * * 1-5"),
    ("주말 오전 10시", "0 10 * * 0,6"),
    ("매주 월요일 10시", "0 10 * * 1"),
    ("매주 월,수,금 10시", "0 10 * * 1,3,5"),
    ("매주 월·수 10시 반", "30 10 * * 1,3"),
    ("토요일 아침 8시", "0 8 * * 6"),
    ("매월 1일 9시", "0 9 1 * *"),
    ("매달 15일 오후 2시 30분", "30 14 15 * *"),
    ("매시간", "0 * * * *"),
    ("30분마다", "*/30 * * * *"),
    ("매 5분", None),
    ("2시간마다", "0 */2 * * *"),
    ("매일 아침", "0 9 * * *"),
    ("매주", "0 9 * * 1"),
])
def test_한국어_일정을_cron_으로(text, cron):
    parsed = ch.parse_korean(text)
    if cron is None:
        # "매 5분" 은 '마다' 가 없어 규칙이 아니다 — LLM 폴백으로 넘긴다.
        assert parsed is None or parsed["cron"] != "*/5 * * * *"
        return
    assert parsed is not None and parsed["cron"] == cron, parsed
    ch.validate(parsed["cron"])


def test_시각을_생략하면_오전_9시로_두고_그_사실을_표시한다():
    parsed = ch.parse_korean("매일 아침")
    assert parsed["assumedTime"] is True and parsed["cron"] == "0 9 * * *"
    assert ch.parse_korean("평일 오전 9시 30분")["assumedTime"] is False


@pytest.mark.parametrize("text", ["", "다음 주에 한 번", "회의 끝나고", "아무때나", "매월 마지막 날 오전 9시", "격주 월요일 10시",
                                  "매월 첫째 월요일", "분기마다 첫 영업일"])
def test_모르는_표현은_None_이라_LLM_폴백으로_간다(text):
    assert ch.parse_korean(text) is None


def test_요일_번호는_표준_crontab_이다_0_이_일요일():
    """APScheduler 3.x from_crontab 은 0 을 월요일로 읽는다(문서 경고). to_trigger 가 이름으로 바꿔 넘겨 편집기의 '월요일' 이 월요일에 돈다."""
    sunday_noon = datetime.datetime(2026, 9, 20, 3, 0, tzinfo=datetime.timezone.utc)   # 2026-09-20 일요일 12:00 KST
    assert ch.next_runs("0 9 * * 1", count=1, now=sunday_noon) == ["2026-09-21T09:00:00+09:00"], "월요일"
    assert ch.next_runs("0 9 * * 0", count=1, now=sunday_noon) == ["2026-09-27T09:00:00+09:00"], "일요일(0)"
    assert ch.next_runs("0 9 * * 7", count=1, now=sunday_noon) == ["2026-09-27T09:00:00+09:00"], "일요일(7)"
    assert ch.next_runs("0 9 * * 0,6", count=2, now=sunday_noon) == ["2026-09-26T09:00:00+09:00", "2026-09-27T09:00:00+09:00"]
    assert ch._convert_dow("1-5") == "mon,tue,wed,thu,fri" and ch._convert_dow("0-6") == "sun,mon,tue,wed,thu,fri,sat"
    assert ch._convert_dow("*/2") == "*/2" and ch._convert_dow("mon-fri") == "mon-fri" and ch._convert_dow("5-0") == "fri,sat,sun"
    import pathlib
    source = (pathlib.Path(__file__).resolve().parent / "scheduler.py").read_text(encoding="utf-8")
    assert "cron_helper.to_trigger(" in source and "CronTrigger.from_crontab(" not in source, "스케줄러도 같은 해석기를 써야 미리보기와 어긋나지 않는다"


def test_설명은_흔한_모양만_한국어로_바꾸고_나머지는_그대로():
    assert ch.describe("30 9 * * 1-5") == "평일 오전 9시 30분"
    assert ch.describe("0 18 * * *") == "매일 오후 6시"
    assert ch.describe("0 0 1 * *") == "매월 1일 자정"
    assert ch.describe("*/15 * * * *") == "15분마다"
    assert ch.describe("0 */3 * * *") == "3시간마다 (0분)"
    assert ch.describe("0 10 * * 1,3,5") == "매주 월·수·금요일 오전 10시"
    assert ch.describe("0 9 * 6 *") == "0 9 * 6 *"
    assert ch.describe("bad") == "bad"


def test_다음_실행은_서울_시간으로_N회():
    runs = ch.next_runs("30 9 * * 1-5", count=3, now=NOW)
    assert runs == ["2026-09-21T09:30:00+09:00", "2026-09-22T09:30:00+09:00", "2026-09-23T09:30:00+09:00"], "토요일 정오 → 월요일부터"
    assert ch.next_runs("*/30 * * * *", count=2, now=NOW) == ["2026-09-19T12:30:00+09:00", "2026-09-19T13:00:00+09:00"]
    assert len(ch.next_runs("0 9 * * *", count=50, now=NOW)) == 20, "상한 20"


@pytest.mark.parametrize("bad", ["", "0 9 * *", "60 9 * * *", "a b c d e", "0 9 * * 7-9"])
def test_잘못된_cron_은_CronHelperError(bad):
    with pytest.raises(ch.CronHelperError):
        ch.validate(bad)


def test_preview_는_설명과_다음_실행을_함께():
    out = ch.preview("0 9 1 * *", count=2, now=NOW)
    assert out == {"cron": "0 9 1 * *", "description": "매월 1일 오전 9시", "next": ["2026-10-01T09:00:00+09:00", "2026-11-01T09:00:00+09:00"]}


class _FakeLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.answers.pop(0)


def test_suggest_는_규칙을_먼저_쓰고_LLM_을_부르지_않는다():
    llm = _FakeLLM([])
    out = ch.suggest("평일 오전 9시 30분", llm=llm, now=NOW)
    assert out["cron"] == "30 9 * * 1-5" and out["source"] == "rules" and out["next"][0] == "2026-09-21T09:30:00+09:00"
    assert llm.calls == []


def test_규칙이_실패하면_LLM_폴백을_검증해서_쓴다():
    llm = _FakeLLM([ch.SuggestedCron(cron="0 9 1,15 * *", explanation="1일과 15일 오전 9시")])
    out = ch.suggest("매월 첫날과 보름에 아침", llm=llm, now=NOW)
    assert out["cron"] == "0 9 1,15 * *" and out["source"] == "llm" and out["explanation"] == "1일과 15일 오전 9시"
    assert len(out["next"]) == 5 and len(llm.calls) == 1
    with pytest.raises(ch.CronHelperError):
        ch.suggest("격주로 이상하게", llm=_FakeLLM([ch.SuggestedCron(cron="0 9 * * 9")]), now=NOW)
    with pytest.raises(ch.CronHelperError):
        ch.suggest("   ", llm=_FakeLLM([]))
    with pytest.raises(ch.CronHelperError):
        ch.suggest("아무때나", allow_llm=False)
