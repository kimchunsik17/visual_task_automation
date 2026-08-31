"""커뮤니티 템플릿 (ADR-0023, 우선 백로그 12) 계약 테스트.

§4.14 검증 매트릭스의 층을 따른다 — 불변성·게시 게이트·정화 회귀·호환성·설치 계보·업그레이드·
권한·품질 신호·이름.

이 파일이 지키는 두 문장:
  1. **게시된 버전은 절대 바뀌지 않는다.** 바뀌면 "v1.0 을 설치했다"는 기록이 거짓말이 된다.
  2. **자기도 안 돌려본 워크플로우는 템플릿이 될 수 없다.**
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import community_identity as identity
import community_templates as templates
import models
from database import Base
from usage_tracking import OUTCOME_SUCCESS

GRAPH = {"nodes": [
    {"id": "s1", "type": "startNode", "data": {}},
    {"id": "llm", "type": "llmNode", "data": {"model": "gpt-5.6", "apiKey": "sk-SECRET",
                                              "systemPrompt": "요약해줘"}},
    {"id": "dc", "type": "discordNode", "data": {"botToken": "REAL.TOKEN",
                                                 "channelId": "123456789012345678"}},
], "edges": [{"id": "e1", "source": "s1", "target": "llm"},
             {"id": "e2", "source": "llm", "target": "dc"}]}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="작성자", email="a@t.com", role="user"),
        models.User(id=2, name="설치자", email="b@t.com", role="user"),
        models.User(id=9, name="운영", email="m@t.com", role="moderator"),
    ])
    session.commit()
    for uid, handle in [(1, "author-one"), (2, "user-two"), (9, "keeper-one")]:
        identity.create_profile(session, session.query(models.User).get(uid), handle=handle)
    yield session
    session.close()


def _u(db, uid):
    return db.query(models.User).get(uid)


def _project(db, user_id=1, graph=None, ran=True):
    project = models.Project(user_id=user_id, title="요약 봇",
                             graph_data=graph or GRAPH, current_revision=4)
    db.add(project)
    db.commit()
    if ran:
        _record_success(db, project.id)
    return project


def _record_success(db, project_id):
    db.add(models.FlowExecutionLog(project_id=project_id, outcome=OUTCOME_SUCCESS,
                                   execution_time=datetime.datetime.utcnow(), status="success"))
    db.commit()


def _publish(db, project=None, slug="summary-bot", **kw):
    return templates.publish(db, _u(db, 1), project=project or _project(db),
                             slug=slug, title=kw.pop("title", "요약 봇"), **kw)


# ── 1. 게시 게이트 ──────────────────────────────────────────────────────
def test_a_workflow_you_never_ran_cannot_become_a_template(db):
    """가장 값싼 품질 게이트 — 실행 로그 조회 하나로 심사 인력 없이 걸러진다."""
    project = _project(db, ran=False)
    gate = templates.evaluate_gate(db, project, _u(db, 1))
    assert gate["ok"] is False
    assert [c for c in gate["checks"] if c["id"] == "executed"][0]["ok"] is False

    with pytest.raises(templates.TemplateError) as exc:
        _publish(db, project=project)
    assert "실행 성공" in str(exc.value)


def test_a_workflow_you_ran_passes_the_gate(db):
    gate = templates.evaluate_gate(db, _project(db), _u(db, 1))
    assert gate["ok"] is True and gate["executedAt"] is not None
    assert all(c["ok"] for c in gate["checks"])


def test_broken_workflows_are_refused(db):
    """깨진 것을 "검증됨" 라벨을 달고 내보내지 않는다."""
    project = _project(db, graph={"nodes": [{"id": "dc", "type": "discordNode", "data": {}}],
                                  "edges": []})
    gate = templates.evaluate_gate(db, project, _u(db, 1))
    assert [c for c in gate["checks"] if c["id"] == "dry_run"][0]["ok"] is False


def test_unknown_node_types_are_refused(db):
    project = _project(db, graph={"nodes": [{"id": "x", "type": "brandNewNode", "data": {}}],
                                  "edges": []})
    gate = templates.evaluate_gate(db, project, _u(db, 1))
    assert [c for c in gate["checks"] if c["id"] == "sanitize"][0]["ok"] is False


def test_python_node_is_a_conditional_gate_not_a_ban(db, monkeypatch):
    """§4.15 의 실행 격리가 켜져 있으면 허용된다 — 영구 금지가 아니다."""
    graph = {"nodes": [{"id": "s1", "type": "startNode", "data": {}},
                       {"id": "py", "type": "pythonNode", "data": {"code": "output_data = 1"}},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "s1", "target": "py"},
                       {"id": "e2", "source": "py", "target": "o1"}]}
    project = _project(db, graph=graph)

    monkeypatch.setenv("PYTHON_NODE_ISOLATION", "1")
    assert [c for c in templates.evaluate_gate(db, project, _u(db, 1))["checks"]
            if c["id"] == "python"][0]["ok"] is True

    monkeypatch.setenv("PYTHON_NODE_ISOLATION", "0")
    check = [c for c in templates.evaluate_gate(db, project, _u(db, 1))["checks"]
             if c["id"] == "python"][0]
    assert check["ok"] is False and "실행 격리가 배포되면" in check["detail"]


def test_high_risk_nodes_go_to_review_instead_of_publishing(db):
    graph = {"nodes": [{"id": "s1", "type": "startNode", "data": {}},
                       {"id": "db1", "type": "databaseNode",
                        "data": {"connectionString": "{{API_CENTER:database}}", "query": "SELECT 1"}},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "s1", "target": "db1"},
                       {"id": "e2", "source": "db1", "target": "o1"}]}
    template, _ = _publish(db, project=_project(db, graph=graph), slug="db-report")
    assert template.status == "in_review", "고위험 노드는 사람이 본다"
    assert template.published_at is None


# ── 2. 이름 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("slug, ok", [
    ("summary-bot", True), ("a1b", True),
    ("ab", False), ("-lead", False), ("trail-", False), ("a--b", False),
    ("official", False), ("workflow-ai", False), ("대문자없음X", False),
])
def test_slug_rules(slug, ok):
    if ok:
        assert templates.normalize_slug(slug) == slug
    else:
        with pytest.raises(templates.TemplateError):
            templates.normalize_slug(slug)


def test_duplicate_slugs_are_refused(db):
    _publish(db)
    with pytest.raises(templates.TemplateError):
        _publish(db, project=_project(db))


# ── 3. 불변성 ───────────────────────────────────────────────────────────
def test_editing_the_source_project_does_not_change_a_published_version(db):
    project = _project(db)
    template, version = _publish(db, project=project)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).first()
    before = json.dumps(share.graph_snapshot, ensure_ascii=False)

    project.graph_data = {"nodes": [], "edges": []}
    db.commit()
    db.refresh(share)
    assert json.dumps(share.graph_snapshot, ensure_ascii=False) == before


def test_a_new_version_leaves_the_old_one_untouched(db):
    project = _project(db)
    template, first = _publish(db, project=project)
    first_share_id = first.workflow_share_id

    second = templates.publish_version(db, _u(db, 1), template, project=project,
                                       version="1.1.0", changelog="문구 수정")
    db.refresh(first)
    assert first.workflow_share_id == first_share_id and first.status == "published"
    assert template.latest_version_id == second.id
    assert second.version == "1.1.0"


def test_duplicate_versions_are_refused(db):
    project = _project(db)
    template, _ = _publish(db, project=project)
    with pytest.raises(templates.TemplateError):
        templates.publish_version(db, _u(db, 1), template, project=project, version="1.0.0")


def test_version_must_be_semver(db):
    with pytest.raises(templates.TemplateError):
        _publish(db, version="v1")


def test_yanking_blocks_new_installs_but_not_existing_copies(db):
    template, version = _publish(db)
    project = templates.install(db, _u(db, 2), template, version)
    templates.yank_version(db, _u(db, 1), version)

    with pytest.raises(templates.TemplateError):
        templates.install(db, _u(db, 2), template, version)
    # 이미 설치한 사본은 그대로다 — 회수는 불가능하다.
    assert db.query(models.Project).filter(models.Project.id == project.id).first() is not None


# ── 4. 정화 회귀 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("secret", ["sk-SECRET", "REAL.TOKEN"])
def test_published_templates_carry_no_secrets(db, secret):
    """템플릿 경로가 §4.12 와 **같은** 정화 함수를 쓴다 — 우회 경로가 없다."""
    _, version = _publish(db)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).first()
    assert secret not in json.dumps(share.graph_snapshot, ensure_ascii=False)


# ── 5. 호환성 ───────────────────────────────────────────────────────────
def test_compatibility_records_node_versions_at_publish_time(db):
    _, version = _publish(db)
    recorded = version.compatibility["nodeTypeVersions"]
    assert recorded["llmNode"] == 1 and recorded["discordNode"] == 1
    assert templates.check_compatibility(db, version)["compatible"] is True


def test_installing_is_blocked_when_a_node_definition_changed(db, monkeypatch):
    """노드 정의가 바뀐 뒤 예전 템플릿을 설치하면 **조용히 깨지지 않고** 차단된다."""
    template, version = _publish(db)
    version.compatibility = {"graphSchemaVersion": 1,
                             "nodeTypeVersions": {"llmNode": 1, "discordNode": 99}}
    db.commit()

    report = templates.check_compatibility(db, version)
    assert report["compatible"] is False
    assert report["changedNodeTypes"][0]["nodeType"] == "discordNode"
    with pytest.raises(templates.TemplateError) as exc:
        templates.install(db, _u(db, 2), template, version)
    assert "맞지 않습니다" in str(exc.value)


def test_installing_is_blocked_when_a_node_type_disappeared(db):
    template, version = _publish(db)
    version.compatibility = {"nodeTypeVersions": {"goneNode": 1}}
    db.commit()
    assert templates.check_compatibility(db, version)["missingNodeTypes"] == ["goneNode"]


# ── 6. 설치와 계보 ──────────────────────────────────────────────────────
def test_install_creates_a_private_copy_with_lineage(db):
    template, version = _publish(db)
    project = templates.install(db, _u(db, 2), template, version)

    assert project.user_id == 2 and project.visibility == "private"
    assert "summary-bot" in project.description and "1.0.0" in project.description
    install = db.query(models.TemplateInstall).one()
    assert install.installed_by == 2 and install.installed_project_id == project.id
    assert template.install_count == 1
    # 사본에도 비밀은 없다.
    assert "sk-SECRET" not in json.dumps(project.graph_data, ensure_ascii=False)


def test_nodes_without_positions_are_laid_out_before_install(db):
    """위치 없는 템플릿도 연결 순서대로 떨어져 보여야 한다."""
    template, version = _publish(db)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).one()
    positions = {node["id"]: node["position"] for node in share.graph_snapshot["nodes"]}

    assert len({(position["x"], position["y"]) for position in positions.values()}) == len(positions)
    assert positions["s1"]["x"] < positions["llm"]["x"] < positions["dc"]["x"]


def test_publish_preserves_an_existing_manual_layout(db):
    graph = json.loads(json.dumps(GRAPH))
    expected = {
        "s1": {"x": 45, "y": 210},
        "llm": {"x": 610, "y": 70},
        "dc": {"x": 1120, "y": 340},
    }
    for node in graph["nodes"]:
        node["position"] = expected[node["id"]]

    _template, version = _publish(db, project=_project(db, graph=graph), slug="manual-layout")
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).one()

    assert {node["id"]: node["position"] for node in share.graph_snapshot["nodes"]} == expected


def test_install_repairs_a_legacy_snapshot_stacked_at_zero_without_mutating_it(db):
    """이미 게시된 구형 템플릿도 재게시 없이 설치 시 복구한다."""
    template, version = _publish(db, slug="legacy-layout")
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).one()
    legacy_snapshot = json.loads(json.dumps(share.graph_snapshot))
    for node in legacy_snapshot["nodes"]:
        node["position"] = {"x": 0, "y": 0}
    share.graph_snapshot = legacy_snapshot
    db.commit()

    project = templates.install(db, _u(db, 2), template, version)
    installed_positions = [node["position"] for node in project.graph_data["nodes"]]

    assert len({(position["x"], position["y"]) for position in installed_positions}) == 3
    assert all(node["position"] == {"x": 0, "y": 0} for node in share.graph_snapshot["nodes"])


def test_suspended_templates_cannot_be_installed(db):
    template, version = _publish(db)
    template.status = "suspended"
    db.commit()
    with pytest.raises(templates.TemplateError):
        templates.install(db, _u(db, 2), template, version)


# ── 7. 업그레이드 알림 ──────────────────────────────────────────────────
def test_a_new_version_notifies_installers_without_touching_their_copies(db):
    template, version = _publish(db)
    project = templates.install(db, _u(db, 2), template, version)
    before = json.dumps(project.graph_data, ensure_ascii=False)

    templates.publish_version(db, _u(db, 1), template, project=_project(db),
                              version="2.0.0", changelog="큰 변경")
    notice = db.query(models.Notification).filter(
        models.Notification.user_id == 2, models.Notification.kind == "template_update").one()
    assert "2.0.0" in notice.body
    # **자동 업그레이드는 하지 않는다** — 사용자가 이미 사본을 고쳤을 수 있다.
    db.refresh(project)
    assert json.dumps(project.graph_data, ensure_ascii=False) == before


# ── 8. 품질 신호 ────────────────────────────────────────────────────────
def test_first_run_outcome_is_recorded_once(db):
    template, version = _publish(db)
    project = templates.install(db, _u(db, 2), template, version)

    templates.record_first_run(db, project.id, "success")
    templates.record_first_run(db, project.id, "error")   # 두 번째는 무시된다
    install = db.query(models.TemplateInstall).one()
    assert install.first_run_outcome == "success"


def test_quality_signals_come_from_runs_not_install_counts(db):
    template, version = _publish(db)
    for user_id in (2, 9):
        project = templates.install(db, _u(db, user_id), template, version)
        templates.record_first_run(db, project.id, "success" if user_id == 2 else "error")

    signals = templates.quality_signals(db, template)
    assert signals["installs"] == 2 and signals["measuredRuns"] == 2
    assert signals["firstRunSuccessRate"] == 0.5


def test_templates_without_measured_runs_sort_below_measured_ones(db):
    good, good_version = _publish(db, project=_project(db), slug="good-one")
    templates.record_first_run(db, templates.install(db, _u(db, 2), good, good_version).id, "success")
    _publish(db, project=_project(db), slug="unmeasured-one")

    order = [t.slug for t in templates.list_templates(db, sort="quality")]
    assert order[0] == "good-one", "측정된 실행이 있는 쪽이 위로 온다"


def test_install_sort_looks_at_every_template_not_just_the_newest(db):
    """설치 수 정렬은 **자르기 전에** 세워야 한다.

    예전에는 최신 N개를 먼저 자른 뒤 파이썬에서 다시 정렬해서, 오래된 인기 템플릿이
    목록에 아예 못 들어왔다. 홈 화면의 인기 아이디어가 이 정렬에 기댄다.
    """
    popular, _ = _publish(db, project=_project(db), slug="old-but-popular")
    popular.install_count = 12
    for index in range(5):
        _publish(db, project=_project(db), slug=f"newer-{index}")
    db.commit()

    order = [t.slug for t in templates.list_templates(db, sort="installs", limit=3)]
    assert order[0] == "old-but-popular"


# ── 8b. 소개 페이지: 운영자 수정·좋아요·댓글 ────────────────────────────
def test_운영자는_남이_올린_템플릿의_겉면을_고칠_수_있다(db):
    template, _ = _publish(db, project=_project(db), slug="typo-one")
    templates.edit_template(db, _u(db, 9), template, title="고친 제목",
                            description="한 줄 요약", intro_body="## 이렇게 씁니다")
    assert template.title == "고친 제목"
    assert template.intro_body.startswith("## 이렇게 씁니다")


def test_ADMIN_EMAILS_로만_어드민인_계정도_고칠_수_있다(db, monkeypatch):
    """DB 의 role 이 아직 user 여도 운영자다.

    `bootstrap_admins()` 가 돌기 전(또는 아예 안 도는 환경)에는 role 이 그대로 'user' 다.
    그때 `is_staff` 만 보면 **관리자 화면은 열리는데 템플릿 수정만 막히는** 상태가 된다 —
    실제로 그렇게 나갔다.
    """
    monkeypatch.setenv("ADMIN_EMAILS", "b@t.com")
    template, _ = _publish(db, project=_project(db), slug="env-admin")
    admin = _u(db, 2)
    assert admin.role == "user" and admin.email == "b@t.com"

    templates.edit_template(db, admin, template, title="운영자가 고침")
    assert template.title == "운영자가 고침"


def test_운영_권한_판정은_한_곳에서_한다(db, monkeypatch):
    """main 과 community_safety 가 따로 ADMIN_EMAILS 를 읽으면 판정이 갈린다."""
    import community_safety

    monkeypatch.setenv("ADMIN_EMAILS", "b@t.com")
    assert community_safety.has_staff_access(_u(db, 2)) is True      # 부트스트랩 어드민
    assert community_safety.has_staff_access(_u(db, 9)) is True      # moderator
    assert community_safety.has_staff_access(_u(db, 1)) is False     # 일반 사용자
    assert community_safety.has_staff_access(None) is False


def test_남의_템플릿을_아무나_고칠_수는_없다(db):
    template, _ = _publish(db, project=_project(db), slug="mine-only")
    with pytest.raises(templates.TemplateError):
        templates.edit_template(db, _u(db, 2), template, title="가로채기")


def test_겉면을_고쳐도_게시된_스냅샷은_그대로다(db):
    """이 파일의 첫 문장이 여기서도 지켜져야 한다 — 가져간 사람의 사본이 바뀌면 안 된다."""
    template, version = _publish(db, project=_project(db), slug="frozen-one")
    before = json.dumps(
        db.query(models.WorkflowShare).get(version.workflow_share_id).graph_snapshot,
        sort_keys=True)
    templates.edit_template(db, _u(db, 9), template, title="제목만 바꿈")
    after = json.dumps(
        db.query(models.WorkflowShare).get(version.workflow_share_id).graph_snapshot,
        sort_keys=True)
    assert before == after
    assert template.latest_version_id == version.id, "겉면 수정은 새 버전을 만들지 않는다"


def test_공식_템플릿_로직_수정은_새_버전을_만든다(db):
    template, first = templates.publish_curated(
        db, _u(db, 9), graph=GRAPH, slug="official-one", title="공식")
    _, second = templates.revise_curated(db, _u(db, 9), template, graph=GRAPH, version="1.1.0",
                                         changelog="출력 노드 연결")
    assert template.latest_version_id == second.id
    assert second.id != first.id
    assert db.query(models.TemplateVersion).get(first.id).status == "published", \
        "예전 버전은 살아 있어야 한다 — 그걸 설치한 사람의 기록이 있다"


def test_일반_템플릿은_이_경로로_로직을_못_고친다(db):
    """일반 템플릿은 '본인이 돌려본 프로젝트' 가 근거다. 그래프를 직접 넣게 하면 그 근거가 사라진다."""
    template, _ = _publish(db, project=_project(db), slug="user-one")
    with pytest.raises(templates.TemplateError):
        templates.revise_curated(db, _u(db, 9), template, graph=GRAPH, version="1.1.0")


def test_섬네일은_소개에_넣은_이미지_중에서만_고른다(db):
    template, _ = _publish(db, project=_project(db), slug="thumb-one")
    with pytest.raises(templates.TemplateError):
        templates.edit_template(db, _u(db, 9), template, thumbnail_artifact_id="남의-파일-id")
    templates.edit_template(db, _u(db, 9), template, intro_image_ids=["img-1", "img-2"])
    templates.edit_template(db, _u(db, 9), template, thumbnail_artifact_id="img-2")
    assert template.thumbnail_artifact_id == "img-2"


def test_좋아요는_한_번이고_자기_것에는_못_누른다(db):
    import community_posts

    template, _ = _publish(db, project=_project(db), slug="liked-one")
    with pytest.raises(community_posts.PostError):
        community_posts.toggle_like(db, _u(db, 1), target_type="template", target_id=template.id)

    first = community_posts.toggle_like(db, _u(db, 2), target_type="template", target_id=template.id)
    assert first == {"liked": True, "likeCount": 1}
    again = community_posts.toggle_like(db, _u(db, 2), target_type="template", target_id=template.id)
    assert again == {"liked": False, "likeCount": 0}, "다시 누르면 취소다"


def test_템플릿_댓글은_같은_표를_쓰고_집계가_따라간다(db):
    import community_posts

    template, _ = _publish(db, project=_project(db), slug="talked-one")
    row = community_posts.create_comment(db, _u(db, 2), target_type="template",
                                         target_id=template.id, body="잘 쓰고 있어요")
    assert template.comment_count == 1
    assert db.query(models.Comment).filter_by(target_type="template").count() == 1

    community_posts.delete_comment(db, _u(db, 2), row)
    assert template.comment_count == 0
    assert community_posts.list_comments(db, target_type="template",
                                         target_ids=[template.id], viewer_id=2) == []


def test_템플릿도_신고할_수_있다(db):
    import community_safety

    template, _ = _publish(db, project=_project(db), slug="reported-one")
    row = community_safety.report(db, _u(db, 2), target_type="template",
                                  target_id=str(template.id), reason="spam")
    assert row.target_type == "template"


def test_메타데이터는_스냅샷에서_그때그때_센다(db):
    template, version = _publish(db, project=_project(db), slug="meta-one")
    share = db.query(models.WorkflowShare).get(version.workflow_share_id)
    meta = templates.graph_metadata(share)
    assert meta["nodeCount"] == 3 and meta["edgeCount"] == 2
    assert meta["triggerType"] == "startNode", "startNode 도 시작 노드다(dry_run 이 정본)"
    assert meta["usesAi"] is True


# ── 8c. 캔버스 메모 ─────────────────────────────────────────────────────
MEMO_GRAPH = {
    "nodes": [
        {"id": "s1", "type": "startNode", "position": {"x": 80, "y": 80}, "data": {}},
        {"id": "out", "type": "outputNode", "position": {"x": 550, "y": 80}, "data": {}},
        {"id": "memo1", "type": "memoNode", "position": {"x": 80, "y": -170},
         "data": {"text": "여기를 채우세요 hong@example.com",
                  "memoContent": {"version": 1,
                                  "segments": [{"text": "여기를 채우세요 hong@example.com"}]},
                  "memoSize": {"width": 320, "height": 132}}},
    ],
    "edges": [{"id": "e1", "source": "s1", "target": "out"}],
}


def test_메모가_붙은_그래프도_게시된다(db):
    """`memoNode` 에 정화 규칙이 없으면 SanitizeRefused 로 **게시 자체가 막힌다.**

    캔버스 주석은 실행 그래프가 아니지만 스냅샷에는 들어간다 — 규칙이 없으면 메모를 하나
    붙인 순간 그 템플릿은 영영 올라가지 못한다.
    """
    template, version = templates.publish_curated(
        db, _u(db, 9), graph=MEMO_GRAPH, slug="memo-one", title="메모 있는 템플릿")
    snapshot = db.query(models.WorkflowShare).get(version.workflow_share_id).graph_snapshot
    memos = [n for n in snapshot["nodes"] if n["type"] == "memoNode"]
    assert len(memos) == 1, "메모가 스냅샷에서 사라지면 안내가 통째로 없어진다"
    assert memos[0]["position"] == {"x": 80, "y": -170}, "메모 자리는 그대로 유지된다"
    assert memos[0]["data"]["memoSize"] == {"width": 320, "height": 132}, (
        "크기는 data.memoSize 로만 살아남는다 — 정화가 width/height 를 버린다")


def test_메모_본문도_정화된다(db):
    """메모는 사람이 쓴 자유 텍스트다. 여기에 적힌 연락처가 그대로 공개되면 안 된다."""
    _, version = templates.publish_curated(
        db, _u(db, 9), graph=MEMO_GRAPH, slug="memo-scrub", title="메모 정화")
    snapshot = db.query(models.WorkflowShare).get(version.workflow_share_id).graph_snapshot
    memo = next(n for n in snapshot["nodes"] if n["type"] == "memoNode")
    assert "hong@example.com" not in json.dumps(memo, ensure_ascii=False)


def test_메모는_시작_노드로_세지_않는다(db):
    """메모에 들어오는 엣지가 없다고 '고아 노드' 로 잡히면 구조 검사에서 게시가 막힌다."""
    template, _ = templates.publish_curated(
        db, _u(db, 9), graph=MEMO_GRAPH, slug="memo-start", title="메모 시작")
    assert template.status == "published"


# ── 9. 권한 ─────────────────────────────────────────────────────────────
def test_you_can_only_publish_your_own_workflow(db):
    with pytest.raises(templates.TemplateError):
        templates.publish(db, _u(db, 2), project=_project(db, user_id=1), slug="stolen",
                          title="가로채기")


def test_only_the_owner_publishes_versions_or_yanks(db):
    project = _project(db)
    template, version = _publish(db, project=project)
    with pytest.raises(templates.TemplateError):
        templates.publish_version(db, _u(db, 2), template, project=project, version="1.1.0")
    with pytest.raises(templates.TemplateError):
        templates.yank_version(db, _u(db, 2), version)


def test_public_payload_carries_handles_not_emails(db):
    template, _ = _publish(db)
    payload = json.dumps(templates.public_template(db, template), ensure_ascii=False)
    assert "a@t.com" not in payload and "author-one" in payload


# ── 공식(큐레이션) 게시 — 게이트 3번의 유일한 예외 (2026-08-30) ─────────
#
# 면제한 것은 "만든 사람이 돌려봤는가" 하나뿐이다. 나머지 네 게이트는 그대로 적용된다.
# 이 파일이 지키는 문장: **면제가 다른 게이트까지 열어 주지 않는다.**

def _curated(db, slug="official-bot", graph=None, **kw):
    return templates.publish_curated(
        db, _u(db, 9), graph=graph or GRAPH, slug=slug,
        title=kw.pop("title", "공식 요약 봇"),
        source=kw.pop("source", "n8n: Auto Categorise Emails"),
        reviewer=kw.pop("reviewer", "keeper-one"), **kw)


def test_공식_템플릿은_실행_이력_없이_게시된다(db):
    """일반 게시라면 여기서 막힌다 — 프로젝트도 실행 로그도 없다."""
    template, version = _curated(db)
    assert template.status in ("published", "in_review")
    assert template.is_curated is True
    assert version.publish_gate["executionVerifiedAt"] is None


def test_면제한_사실이_기록에_남는다(db):
    """숨은 예외로 두면 나중에 '왜 실행 이력이 없지' 를 설명할 수 없다."""
    _template, version = _curated(db)
    gate = version.publish_gate
    assert gate["curated"] is True
    assert gate["curatedReason"]
    assert gate["source"] == "n8n: Auto Categorise Emails"
    assert gate["reviewedBy"] == "keeper-one"


def test_공식_여부가_사용자에게_보인다(db):
    template, _v = _curated(db)
    assert templates.public_template(db, template)["isCurated"] is True


def test_일반_게시는_공식으로_표시되지_않는다(db):
    template, _v = _publish(db)
    assert bool(template.is_curated) is False
    assert templates.public_template(db, template)["isCurated"] is False


# ── 면제가 다른 게이트를 열어 주지 않는다 ───────────────────────────────

def test_공식이어도_정화는_그대로_적용된다(db):
    """비밀 값이 스냅샷에 남으면 안 된다 — 공식이라서 예외가 되지 않는다."""
    template, _v = _curated(db)
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.owner_type == "template",
        models.WorkflowShare.owner_id == template.id).first()
    dumped = json.dumps(share.graph_snapshot, ensure_ascii=False)
    assert "sk-SECRET" not in dumped and "REAL.TOKEN" not in dumped


def test_공식이어도_깨진_그래프는_거부한다(db):
    broken = {"nodes": [{"id": "x", "type": "llmNode", "data": {}}], "edges": []}
    with pytest.raises(templates.TemplateError) as exc:
        _curated(db, slug="broken-one", graph=broken)
    assert "구조" in str(exc.value)


def test_공식이어도_고위험은_검토_상태로_간다(db):
    """`arbitrary_url` 같은 flag 가 붙으면 바로 공개하지 않는다."""
    risky = {"nodes": [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "h1", "type": "httpRequestNode",
         "data": {"url": "https://example.com/api", "method": "GET"}},
        {"id": "o1", "type": "outputNode", "data": {}},
    ], "edges": [{"id": "e1", "source": "s1", "target": "h1"},
                 {"id": "e2", "source": "h1", "target": "o1"}]}
    template, _v = _curated(db, slug="risky-one", graph=risky)
    assert template.status == "in_review", "고위험인데 바로 공개됐다"


def test_공식이어도_분류_규칙을_지킨다(db):
    with pytest.raises(templates.TemplateError):
        _curated(db, slug="bad-cat", category="productivity")


def test_공식이어도_주소가_겹치면_거부한다(db):
    _curated(db, slug="same-slug")
    with pytest.raises(templates.TemplateError):
        _curated(db, slug="same-slug")


def test_프로젝트_없이도_설치할_수_있다(db):
    """공식 템플릿은 source_project_id 가 없다 — 설치 경로가 그것에 기대면 안 된다."""
    template, version = _curated(db, slug="installable-one")
    share = db.query(models.WorkflowShare).filter(
        models.WorkflowShare.id == version.workflow_share_id).first()
    assert share.source_project_id is None
    assert share.graph_snapshot["nodes"], "설치할 내용이 비어 있다"
