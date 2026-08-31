"""인증 없이 남의 워크플로우를 실행·배포·열람할 수 있던 라우트를 막았는지 (2026-08-31).

공개 서버에서 실제로 열려 있던 구멍이다 — project_access 에 RUN/DEPLOY 가 선언돼 있는데
강제하는 호출부가 0곳이었고, 정수 id 만으로 남의 프로젝트를 실행하면 서버가 **소유자의
자격증명을 복호화**해서 썼다. 여기서 지키는 문장은 셋이다.

  1. 비로그인 요청은 실행·배포 라우트에 도달하지 못한다.
  2. 로그인했더라도 남의 프로젝트는 실행·배포할 수 없다.
  3ㅤ**공개 앱은 익명도 실행할 수 있다** — 링크를 받은 사람이 쓰는 것이 기능이다.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DISABLE_SCHEDULER", "1")

import main  # noqa: E402
import models  # noqa: E402
from database import SessionLocal  # noqa: E402

client = TestClient(main.app)

GRAPH = {"nodes": [{"id": "n1", "type": "startNode", "data": {}},
                   {"id": "n2", "type": "outputNode", "data": {}}],
         "edges": [{"id": "e1", "source": "n1", "target": "n2"}]}


@pytest.fixture
def owner_and_project():
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    owner = models.User(email=f"owner-{tag}@example.com", name="owner", token_balance=1000)
    other = models.User(email=f"other-{tag}@example.com", name="other", token_balance=1000)
    db.add_all([owner, other]); db.commit(); db.refresh(owner); db.refresh(other)
    project = models.Project(user_id=owner.id, title=f"t-{tag}", graph_data=GRAPH,
                             visibility="private", share_token=f"tok-{tag}")
    db.add(project); db.commit(); db.refresh(project)
    yield owner, other, project
    db.query(models.Project).filter(models.Project.id == project.id).delete()
    db.query(models.User).filter(models.User.id.in_([owner.id, other.id])).delete()
    db.commit(); db.close()


def _headers(user):
    """실제 JWT 를 만든다. 이 라우트들 중 일부(/api/projects/{id}/run, /api/apps/{token})는
    의존성이 아니라 Authorization 헤더를 직접 파싱하므로 dependency_overrides 로는 검증할 수 없다."""
    import datetime as _dt
    token = main.jwt.encode(
        {"user_id": user.id, "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1)},
        main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


# ── 1) 비로그인은 도달하지 못한다 ─────────────────────────────────────────
def test_deploy_requires_authentication(owner_and_project):
    _o, _x, project = owner_and_project
    assert client.post(f"/api/deploy/{project.id}", json={"mode": "fastapi"}).status_code == 401


def test_execute_requires_authentication():
    assert client.post("/api/execute", json={"nodes": GRAPH["nodes"], "edges": GRAPH["edges"]}).status_code == 401


def test_project_run_rejects_anonymous_for_private(owner_and_project):
    _o, _x, project = owner_and_project
    # 비공개 프로젝트는 익명 실행을 막는다. 조회 권한도 없으므로 존재를 알리지 않는다(404).
    assert client.post(f"/api/projects/{project.id}/run", json={}).status_code == 404


# ── 2) 남의 프로젝트는 실행·배포할 수 없다 ────────────────────────────────
def test_other_user_cannot_deploy(owner_and_project):
    _o, other, project = owner_and_project
    r = client.post(f"/api/deploy/{project.id}", json={"mode": "fastapi"}, headers=_headers(other))
    assert r.status_code in (403, 404), r.text


def test_other_user_cannot_borrow_project_credentials(owner_and_project):
    """payload.project_id 로 남의 자격증명을 빌려 쓰던 경로."""
    _o, other, project = owner_and_project
    r = client.post("/api/execute", headers=_headers(other),
                    json={"nodes": GRAPH["nodes"], "edges": GRAPH["edges"], "project_id": project.id})
    assert r.status_code in (403, 404), r.text


def test_other_user_cannot_run_private_project(owner_and_project):
    _o, other, project = owner_and_project
    r = client.post(f"/api/projects/{project.id}/run", json={}, headers=_headers(other))
    assert r.status_code in (403, 404), r.text


def test_shared_app_get_checks_visibility(owner_and_project):
    """GET 은 열려 있고 POST 만 막던 비대칭 — graph_data 안에 봇 토큰이 평문으로 산다."""
    _o, _x, project = owner_and_project
    assert client.get(f"/api/apps/{project.share_token}").status_code == 403


# ── 3) 공개 앱은 익명도 쓸 수 있어야 한다(기능 보존) ──────────────────────
def test_public_app_stays_readable_and_runnable(owner_and_project):
    owner, _x, project = owner_and_project
    db = SessionLocal()
    db.query(models.Project).filter(models.Project.id == project.id).update({"visibility": "public"})
    db.commit(); db.close()

    assert client.get(f"/api/apps/{project.share_token}").status_code == 200
    # 실행은 인증 없이도 권한 판정을 통과해야 한다(실제 실행 결과는 여기서 보지 않는다).
    r = client.post(f"/api/projects/{project.id}/run", json={})
    assert r.status_code not in (401, 403, 404), r.text


def test_owner_can_still_deploy_and_run(owner_and_project):
    owner, _x, project = owner_and_project
    assert client.post(f"/api/deploy/{project.id}", json={"mode": "none"},
                       headers=_headers(owner)).status_code == 200
    r = client.post(f"/api/projects/{project.id}/run", json={}, headers=_headers(owner))
    assert r.status_code not in (401, 403, 404), r.text
