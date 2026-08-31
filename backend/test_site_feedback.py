"""사이트 평가의 HTTP 경계.

여기서 지키는 것은 두 가지가 **동시에** 성립한다는 사실이다.

  1. **계정당 한 번만** 낼 수 있다. 예전에는 엔드포인트에 인증이 아예 없어 누구인지 알 수
     없었고, `/me` 는 늘 `{"submitted": false}` 를 돌려줬다 — 몇 번이든 낼 수 있었다.
  2. 그런데도 **평가 내용은 익명**이다. 중복을 막으려고 응답에 user_id 를 되돌리면 누가 무슨
     점수를 줬는지 그대로 드러난다. 그래서 '냈다는 사실' 만 별도 표에 적는다.

`main` 을 임포트하면 시작 시 마이그레이션이 돌아 운영 DB 를 건드린다. 그래서 다른 HTTP
테스트와 같이 임시 SQLite 를 가리키는 하위 프로세스에서 돌린다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

SCENARIO = '''
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])

from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

db = SessionLocal()
alice = models.User(id=1, google_id="g1", email="a@e.st", name="alice")
bob = models.User(id=2, google_id="g2", email="b@e.st", name="bob")
db.add_all([alice, bob])
db.commit()
client = TestClient(main.app)

def check(label, cond, extra=""):
    if not cond:
        print(f"FAIL: {label} {extra}"); sys.exit(1)
    print(f"ok: {label}")

def login(user):
    main.app.dependency_overrides[main.get_current_user_required] = lambda: user
    main.app.dependency_overrides[main.get_current_user] = lambda: user

def logout():
    main.app.dependency_overrides.pop(main.get_current_user_required, None)
    main.app.dependency_overrides.pop(main.get_current_user, None)

KEYS = list(main.SITE_FEEDBACK_QUESTIONS.keys())
FULL = {k: 4 for k in KEYS}

# ── 1. 문항 정본을 서버가 내려준다 ─────────────────────────────────────
res = client.get("/api/site-feedback/questions")
check("문항 목록 200", res.status_code == 200, f"{res.status_code} {res.text[:200]}")
sections = res.json()["sections"]
check("구획이 하나 이상 있다", len(sections) >= 1, str(len(sections)))
check("구획마다 정확히 네 문항 — 한 화면에 네 개씩 보여주는 전제다",
      all(len(s["questions"]) == 4 for s in sections),
      str([len(s["questions"]) for s in sections]))
check("화면이 쓰는 필드가 다 있다",
      all(set(q) >= {"key", "title", "help"} for s in sections for q in s["questions"]))
check("구획에도 제목과 안내가 있다",
      all(set(s) >= {"id", "title", "hint", "questions"} for s in sections))
check("평평한 목록과 개수가 같다",
      sum(len(s["questions"]) for s in sections) == len(KEYS))

# ── 2. 로그인하지 않으면 낼 수 없다 ────────────────────────────────────
res = client.post("/api/site-feedback", json={"scores": FULL})
check("비로그인 제출은 401", res.status_code == 401, f"{res.status_code} {res.text[:150]}")
check("비로그인 /me 는 판단하지 않는다",
      client.get("/api/site-feedback/me").json()["submitted"] is False)

# ── 3. 첫 제출은 되고, 내용은 익명으로 남는다 ──────────────────────────
login(alice)
check("내기 전 /me 는 False", client.get("/api/site-feedback/me").json()["submitted"] is False)
res = client.post("/api/site-feedback", json={"scores": FULL, "comment": "잘 쓰고 있어요"})
check("첫 제출 200", res.status_code == 200, f"{res.status_code} {res.text[:200]}")

db.expire_all()
rows = db.query(models.SiteFeedback).all()
check("한 행이 쌓였다", len(rows) == 1, str(len(rows)))
check("**응답에는 user_id 가 없다** — 익명 유지", rows[0].user_id is None, str(rows[0].user_id))
marks = db.query(models.SiteFeedbackSubmitter).all()
check("낸 사람 표에 한 줄이 생겼다", len(marks) == 1, str(len(marks)))
check("낸 사람이 alice 다", marks[0].user_id == 1, str(marks[0].user_id))
check("시각이 아니라 **날짜만** 남는다 — 응답과 시간으로 이어붙이기 어렵게",
      not hasattr(marks[0].submitted_on, "hour"), repr(marks[0].submitted_on))

# ── 4. 같은 계정은 두 번 낼 수 없다 ────────────────────────────────────
check("낸 뒤 /me 는 True", client.get("/api/site-feedback/me").json()["submitted"] is True)
res = client.post("/api/site-feedback", json={"scores": FULL})
check("두 번째 제출은 409", res.status_code == 409, f"{res.status_code} {res.text[:150]}")
db.expire_all()
check("두 번째 제출로 행이 늘지 않았다",
      db.query(models.SiteFeedback).count() == 1,
      str(db.query(models.SiteFeedback).count()))

# 사전 조회가 아니라 **기본키**가 막는지 확인한다 — 두 탭이 동시에 눌렀을 때 남는 방어선이다.
try:
    db.add(models.SiteFeedbackSubmitter(user_id=1, submitted_on=marks[0].submitted_on))
    db.commit()
    check("같은 사용자를 두 번 적을 수 없다", False, "두 번째 행이 들어갔다")
except Exception:
    db.rollback()
    check("같은 사용자를 두 번 적을 수 없다(기본키)", True)

# ── 5. 다른 계정은 낼 수 있다 ──────────────────────────────────────────
login(bob)
check("bob 은 아직 안 냈다", client.get("/api/site-feedback/me").json()["submitted"] is False)
res = client.post("/api/site-feedback", json={"scores": {KEYS[0]: 5}})
check("bob 의 제출 200", res.status_code == 200, f"{res.status_code} {res.text[:200]}")
db.expire_all()
check("행이 둘이 됐다", db.query(models.SiteFeedback).count() == 2)

# ── 6. 값 검사 ─────────────────────────────────────────────────────────
# bob 의 제출 기록을 지워 다시 낼 수 있는 상태로 돌린다 — 검사에 걸린 요청이 아무것도
# 남기지 않는다는 것을 보려면 아직 안 낸 계정이어야 한다.
login(bob)
db.query(models.SiteFeedbackSubmitter).filter_by(user_id=2).delete()
db.commit()

res = client.post("/api/site-feedback", json={"scores": {"없는문항": 3}})
check("모르는 문항은 400", res.status_code == 400, f"{res.status_code} {res.text[:150]}")
res = client.post("/api/site-feedback", json={"scores": {KEYS[0]: 9}})
check("1~5 밖의 점수는 400", res.status_code == 400, f"{res.status_code} {res.text[:150]}")
res = client.post("/api/site-feedback", json={"scores": {}})
check("점수가 하나도 없으면 400 — 전부 건너뛴 빈 응답을 막는다",
      res.status_code == 400, f"{res.status_code} {res.text[:150]}")
db.expire_all()
check("검사에 걸린 요청은 아무것도 남기지 않았다",
      db.query(models.SiteFeedback).count() == 2
      and db.query(models.SiteFeedbackSubmitter).filter_by(user_id=2).count() == 0)

# ── 7. 일부 문항만 답해도 받는다 ("잘 모르겠어요" 로 넘긴 문항) ────────
res = client.post("/api/site-feedback", json={"scores": {KEYS[0]: 3, KEYS[1]: 4}})
check("일부만 답한 제출도 200", res.status_code == 200, f"{res.status_code} {res.text[:200]}")

logout()
summary = client.get("/api/site-feedback/summary").json()
check("요약이 응답 수를 센다", summary["response_count"] == 3, str(summary["response_count"]))
last = summary["questions"][KEYS[-1]]
check("한 사람만 답한 문항은 그 한 표만 센다",
      last["count"] == 1 and last["average"] == 4.0, str(last))
first = summary["questions"][KEYS[0]]
check("세 사람이 답한 문항은 세 표를 평균낸다",
      first["count"] == 3 and first["average"] == 4.0, str(first))

print("ALL OK")
'''


def test_사이트_평가는_계정당_한_번이고_내용은_익명이다(tmp_path):
    pytest.importorskip("httpx", reason="fastapi.testclient 는 httpx 가 필요하다")
    scenario = tmp_path / "site_feedback_scenario.py"
    scenario.write_text(SCENARIO, encoding="utf-8")
    workdir = tmp_path / "run"
    workdir.mkdir()
    backend_dir = pathlib.Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(scenario), f"sqlite:///{tmp_path / 'feedback.db'}", str(backend_dir)],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "ALL OK" in result.stdout
