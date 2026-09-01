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
    # 403 이 아니라 404 다 — 남의 프로젝트는 "권한이 없다"가 아니라 "없다"고 답해
    # 존재 자체를 알리지 않는다. 느슨하게 (403, 404) 로 두면 이 성질이 깨져도 통과한다.
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Project not found"


def test_other_user_cannot_borrow_project_credentials(owner_and_project):
    """payload.project_id 로 남의 자격증명을 빌려 쓰던 경로."""
    _o, other, project = owner_and_project
    r = client.post("/api/execute", headers=_headers(other),
                    json={"nodes": GRAPH["nodes"], "edges": GRAPH["edges"], "project_id": project.id})
    # 403 이 아니라 404 다 — 남의 프로젝트는 "권한이 없다"가 아니라 "없다"고 답해
    # 존재 자체를 알리지 않는다. 느슨하게 (403, 404) 로 두면 이 성질이 깨져도 통과한다.
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Project not found"


def test_other_user_cannot_run_private_project(owner_and_project):
    _o, other, project = owner_and_project
    r = client.post(f"/api/projects/{project.id}/run", json={}, headers=_headers(other))
    # 403 이 아니라 404 다 — 남의 프로젝트는 "권한이 없다"가 아니라 "없다"고 답해
    # 존재 자체를 알리지 않는다. 느슨하게 (403, 404) 로 두면 이 성질이 깨져도 통과한다.
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Project not found"


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
    # not in (401,403,404) 로 두면 500 도 통과한다 — 권한은 통과했는데 실행이
    # 깨진 상태를 "기능 보존" 으로 오해하게 된다.
    assert r.status_code == 200, r.text


def test_owner_can_still_deploy_and_run(owner_and_project):
    owner, _x, project = owner_and_project
    assert client.post(f"/api/deploy/{project.id}", json={"mode": "none"},
                       headers=_headers(owner)).status_code == 200
    r = client.post(f"/api/projects/{project.id}/run", json={}, headers=_headers(owner))
    assert r.status_code == 200, r.text


# ── 경로 순회 (2026-08-31 적대적 리뷰) ────────────────────────────────────
def test_spa_catchall_blocks_path_traversal():
    """catch-all 이 os.path.join(dist, full_path) 를 그대로 열어, 0.0.0.0:8000 직접 접근 +
    curl --path-as-is 로 `/../../backend/.env` 가 인증 없이 유출됐다. dist 밖은 index 로 폴백해야 한다."""
    import os
    frontend_dist = getattr(main, "FRONTEND_DIST", None)
    if not frontend_dist or not os.path.isdir(frontend_dist):
        pytest.skip("이 배포에는 FRONTEND_DIST 가 없다(개발 서버) — catch-all 이 등록되지 않는다")

    # TestClient 는 경로를 정규화하지 않으므로 순회를 그대로 실어 보낼 수 있다.
    for evil in ("../../backend/.env", "../.env", "../../../../etc/passwd"):
        r = client.get(f"/{evil}")
        # 200 이어도 내용이 index.html 이면 안전하다. 민감 파일 내용이 나오면 실패.
        body = r.text
        assert "JWT_SECRET" not in body and "DATABASE_URL" not in body and "OPENAI_API_KEY" not in body, \
            f"{evil} 로 .env 가 새어 나온다"
        assert not body.startswith("root:"), f"{evil} 로 /etc/passwd 가 새어 나온다"


# ── 워크플로우 공유 owner_type 분기 (2026-08-31 라운드2 리뷰) ──────────────
def test_template_share_not_exposed_via_post_share_route():
    """owner_type 이 'template' 인 공유는 글에 속하지 않는다. 예전에는 post 가 아니면 전부
    answer 로 간주해, template share 가 무관한 공개 글의 visibility 로 통과해 in_review
    스냅샷을 노출했다. 이제 이 라우트는 template 공유를 404 로 거부해야 한다."""
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    u = models.User(email=f"sh-{tag}@e.com", name="u", token_balance=10)
    db.add(u); db.commit(); db.refresh(u)
    uid = u.id
    share = models.WorkflowShare(owner_type="template", owner_id=999999,
                                 graph_snapshot={"nodes": [], "edges": []}, schema_version=1)
    db.add(share); db.commit(); db.refresh(share)
    sid = share.id
    db.close()

    r = client.get(f"/api/community/shares/{sid}", headers=_headers(type("U", (), {"id": uid})()))
    assert r.status_code == 404, f"template 공유가 글 공유 라우트로 노출된다: {r.status_code}"

    db = SessionLocal()
    db.query(models.WorkflowShare).filter(models.WorkflowShare.id == sid).delete()
    db.query(models.User).filter(models.User.id == uid).delete()
    db.commit(); db.close()


def test_uploads_route_requires_ownership():
    """/uploads/{stored_name} 정적 마운트를 소유권 확인 라우트로 대체했다. 인증 없으면 401,
    남의 파일이면 404(존재를 알리지 않음)."""
    assert client.get("/uploads/output.hwpx").status_code == 401
    # 존재하지 않는 파일도 인증 후엔 404
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    u = models.User(email=f"up-{tag}@e.com", name="u", token_balance=10)
    db.add(u); db.commit(); db.refresh(u)
    uid = u.id
    db.close()
    r = client.get("/uploads/definitely-not-a-real-file.bin", headers=_headers(
        type("U", (), {"id": uid})()))
    assert r.status_code == 404
    db = SessionLocal()
    db.query(models.User).filter(models.User.id == uid).delete()
    db.commit(); db.close()


def test_orphan_run_details_are_not_readable_by_others():
    """GET /api/runs/{run_id} 의 fail-open 회귀 방지 (2026-09-01 재검증에서 미수정 확정).

    프로젝트가 삭제됐거나 project_id 가 NULL 인 '고아' 실행 로그는, 예전에는 라우트가
    `if project:` 를 그냥 통과해 **로그인한 아무 계정에게나** run.result 전문과 전 노드
    result_data 를 내줬다. 이제는 로그 소유자 본인만 열람할 수 있어야 한다.
    """
    db = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    owner = models.User(email=f"runowner-{tag}@e.com", name="ro", token_balance=10)
    other = models.User(email=f"runother-{tag}@e.com", name="rx", token_balance=10)
    db.add_all([owner, other]); db.commit(); db.refresh(owner); db.refresh(other)
    # project_id 없는 고아 로그. billable_user_id 로 소유자를 표시한다.
    log = models.FlowExecutionLog(
        user_id=owner.id, billable_user_id=owner.id, actor_user_id=owner.id,
        project_id=None, result="SECRET orphan run output", status="success", total_tokens=1)
    db.add(log); db.commit(); db.refresh(log)
    run_id, owner_id, other_id = log.id, owner.id, other.id
    db.close()

    try:
        # 남은 403 — 예전엔 200 이었다.
        r_other = client.get(f"/api/runs/{run_id}", headers=_headers(type("U", (), {"id": other_id})()))
        assert r_other.status_code == 403, f"고아 로그가 남에게 열렸다: {r_other.status_code}"
        # 소유자 본인은 200, 결과 전문을 받는다.
        r_owner = client.get(f"/api/runs/{run_id}", headers=_headers(type("U", (), {"id": owner_id})()))
        assert r_owner.status_code == 200, f"소유자가 못 봤다: {r_owner.status_code}"
        assert r_owner.json()["run"]["result"] == "SECRET orphan run output"
        # 비로그인도 당연히 막힌다.
        assert client.get(f"/api/runs/{run_id}").status_code == 401
    finally:
        db = SessionLocal()
        db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.id == run_id).delete()
        db.query(models.User).filter(models.User.id.in_([owner_id, other_id])).delete()
        db.commit(); db.close()
