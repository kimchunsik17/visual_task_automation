"""커뮤니티 Q&A (ADR-0021, 우선 백로그 23) 계약 테스트.

§4.12 검증 매트릭스의 층을 따른다 — 정화·권한·공개 범위·Q&A·오류 발췌·가져오기·XSS·남용.

이 파일이 지키는 두 문장:
  1. **정화 규칙이 없는 노드는 공개될 수 없다.** 새 노드를 규칙 없이 추가하면 여기서 깨진다.
  2. **가시성은 화면이 아니라 API 응답에서 적용된다.**
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import community_identity as identity
import community_posts as posts
import community_safety as safety
import community_sanitize as sanitize
import community_shares as shares
import models
from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.User(id=1, name="민수", email="minsu@example.com", role="user"),
        models.User(id=2, name="영희", email="younghee@example.com", role="user"),
        models.User(id=3, name="철수", email="chulsoo@example.com", role="user"),
        models.User(id=9, name="운영", email="mod@example.com", role="moderator"),
    ])
    session.commit()
    # "mod" 는 예약어다(사칭 방지) — 운영자도 일반 핸들을 쓴다.
    for uid, handle in [(1, "minsu"), (2, "younghee"), (3, "chulsoo"), (9, "mod-user")]:
        identity.create_profile(session, session.query(models.User).get(uid), handle=handle)
    yield session
    session.close()


def _u(db, uid):
    return db.query(models.User).get(uid)


def _befriend(db, a, b):
    db.add_all([models.Friendship(user_id=a, friend_id=b), models.Friendship(user_id=b, friend_id=a)])
    db.commit()


def _question(db, author_id=1, **kw):
    kw.setdefault("title", "디스코드 발송이 안 됩니다")
    kw.setdefault("body", "포스터를 만들어 보내려는데 오류가 납니다.")
    return posts.create_post(db, _u(db, author_id), kind=kw.pop("kind", "question"), **kw)


# ── 1. 정화 — 이 기능의 보안 핵심 ────────────────────────────────────────
SECRET_GRAPH = {"nodes": [
    {"id": "s1", "type": "startNode", "data": {}},
    {"id": "llm", "type": "llmNode", "data": {"model": "gpt-5.6-terra", "apiKey": "sk-REAL-SECRET",
                                              "systemPrompt": "문의는 me@corp.com 010-1234-5678"}},
    {"id": "db", "type": "databaseNode", "data": {"connectionString": "{{API_CENTER:database#42}}",
                                                  "query": "SELECT 1"}},
    {"id": "dc", "type": "discordNode", "data": {"botToken": "MTIz.REAL.TOKEN", "channelId": "123",
                                                 "attachments": {"mode": "select", "artifactIds": ["a1"]}}},
    {"id": "em", "type": "emailNode", "data": {"smtp_credentials": "me@corp.com:app-password"}},
    {"id": "v1", "type": "valueNode", "data": {"value": "결과 uploads/9f2a.pdf", "file_path": "uploads/9f2a.pdf"}},
    {"id": "http", "type": "httpRequestNode", "data": {"method": "GET", "url": "https://x",
                                                       "headers": '{"Authorization":"Bearer REAL"}'}},
], "edges": [{"source": "s1", "target": "llm"}], "discord_bot_token": "DEPLOY-SECRET"}


@pytest.mark.parametrize("secret", [
    "sk-REAL-SECRET", "MTIz.REAL.TOKEN", "app-password", "Bearer REAL",
    "me@corp.com", "010-1234-5678", "uploads/9f2a.pdf", "a1", "#42", "DEPLOY-SECRET",
])
def test_sanitize_removes_every_known_secret(secret):
    clean, _ = sanitize.sanitize_graph(SECRET_GRAPH)
    assert secret not in json.dumps(clean, ensure_ascii=False)


@pytest.mark.parametrize("kept", ["{{API_CENTER:database}}", "SELECT 1", "gpt-5.6-terra"])
def test_sanitize_keeps_what_makes_the_workflow_useful(kept):
    """자격증명 **reference** 는 남는다 — 가져간 사람이 자기 것을 채우는 자리다."""
    clean, _ = sanitize.sanitize_graph(SECRET_GRAPH)
    assert kept in json.dumps(clean, ensure_ascii=False)


def test_sanitize_refuses_node_types_without_rules():
    with pytest.raises(sanitize.SanitizeRefused) as exc:
        sanitize.sanitize_graph({"nodes": [{"id": "x", "type": "brandNewNode",
                                            "data": {"token": "secret"}}], "edges": []})
    assert exc.value.unknown_types == ["brandNewNode"]


def test_every_executable_node_type_has_sanitize_rules():
    """**새 노드를 정화 규칙 없이 추가하면 이 테스트가 깨진다.**

    §4.12 는 "정의가 없으면 거부"라고 썼지만, 실제 워크플로우가 쓰는 기본 노드 대부분이 정의가
    없어서 그대로 적용하면 전부 거부된다. 판정 기준을 "규칙이 등록됐는가"로 바꾸고, 그 대신
    커버리지를 여기서 강제한다 — 안전 성질은 같다.
    """
    import node_generators  # noqa: F401  (생성기 등록 트리거)
    import node_registry

    registry = node_registry.node_registry
    registered = set(getattr(registry, "_generators", {}) or getattr(registry, "generators", {}))
    if not registered:   # 등록부 내부 구조가 바뀌면 카탈로그로 대신 확인한다
        import node_definition
        registered = set(node_definition.defined_types()) | set(sanitize.LEGACY_RULES)
    missing = sorted(t for t in registered if sanitize.rule_for(t) is None)
    assert missing == [], f"정화 규칙이 없는 노드 타입: {missing}"


def test_sanitize_reports_what_will_be_cleared_before_publishing():
    preview = sanitize.preview(SECRET_GRAPH)
    assert preview["ok"] is True
    cleared = {(c["nodeId"], c["field"]) for c in preview["cleared"]}
    assert ("llm", "apiKey") in cleared and ("em", "smtp_credentials") in cleared
    assert "database" in preview["requiredCredentials"]
    assert "arbitrary_url" in preview["riskFlags"]


def test_python_node_is_flagged_but_not_stripped():
    """코드 자체가 내용이라 지우면 워크플로우가 사라진다. 대신 위험 표시를 단다(§4.12 고지 목적)."""
    graph = {"nodes": [{"id": "py", "type": "pythonNode",
                        "data": {"code": "output_data = input_data.upper()"}}], "edges": []}
    clean, report = sanitize.sanitize_graph(graph)
    assert clean["nodes"][0]["data"]["code"] == "output_data = input_data.upper()"
    assert "arbitrary_code" in report.risk_flags


def test_sanitize_is_idempotent():
    once, _ = sanitize.sanitize_graph(SECRET_GRAPH)
    twice, _ = sanitize.sanitize_graph(once)
    assert once == twice


def test_sanitize_strips_execution_results_injected_by_the_editor():
    """에디터의 enrich 는 직전 실행 결과 전문을 bindingContext 로 **모든 노드**에 복제해
    넣는다. sanitize 가 아는 필드만 지우고 나머지 키를 그대로 복사했기 때문에, 예전에는
    그 실행 결과가 공개 템플릿·공유 스냅샷으로 샜다. 이제 렌더·실행용 키를 통째로 뗀다."""
    graph = {
        "nodes": [
            {"id": "n1", "type": "startNode", "data": {}},
            {"id": "n2", "type": "llmNode", "data": {
                "systemPrompt": "요약해줘", "model": "gpt-4o-mini",
                # enrich 주입분
                "bindingContext": {"results": {"n1": "영업비밀-실행결과", "n2": "민감출력"},
                                   "nodes": [], "edges": []},
                "className": "ai-highlight", "isPinnedOutput": True,
                "isExecuting": False, "actualTokens": 999, "executionStatus": "done",
            }},
            {"id": "n3", "type": "outputNode", "data": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"},
                  {"id": "e2", "source": "n2", "target": "n3"}],
    }
    clean, _ = sanitize.sanitize_graph(graph)
    blob = json.dumps(clean, ensure_ascii=False)

    assert "영업비밀-실행결과" not in blob
    assert "민감출력" not in blob
    for key in ("bindingContext", "className", "isPinnedOutput", "isExecuting",
                "actualTokens", "executionStatus"):
        assert key not in blob, f"{key} 가 공개 스냅샷으로 샜다"

    # 실제 설정은 그대로 남아야 한다 — 가져간 사람이 워크플로를 쓸 수 있어야 한다.
    n2 = next(n for n in clean["nodes"] if n["id"] == "n2")
    assert n2["data"]["model"] == "gpt-4o-mini"
    assert n2["data"]["systemPrompt"] == "요약해줘"


# ── 2. 공개 범위 (§9-10) ────────────────────────────────────────────────
def test_friends_only_posts_are_hidden_from_non_friends_and_guests(db):
    post = _question(db, author_id=1, visibility="friends")
    assert [p.id for p in posts.list_posts(db, viewer_id=1)] == [post.id], "작성자는 본다"
    assert posts.list_posts(db, viewer_id=2) == [], "친구가 아니면 안 보인다"
    assert posts.list_posts(db, viewer_id=None) == [], "비로그인은 안 보인다"

    _befriend(db, 1, 2)
    assert [p.id for p in posts.list_posts(db, viewer_id=2)] == [post.id], "친구는 본다"


def test_unfriending_immediately_hides_a_friends_only_post(db):
    post = _question(db, author_id=1, visibility="friends")
    _befriend(db, 1, 2)
    assert posts.can_view(db, post, 2) is True
    db.query(models.Friendship).delete()
    db.commit()
    assert posts.can_view(db, post, 2) is False


def test_public_posts_are_visible_to_guests(db):
    post = _question(db, author_id=1, visibility="public")
    assert [p.id for p in posts.list_posts(db, viewer_id=None)] == [post.id]


# ── 3. 차단이 Q&A 에도 적용된다 ─────────────────────────────────────────
def test_blocked_authors_disappear_from_lists_and_answers(db):
    post = _question(db, author_id=1)
    posts.create_answer(db, _u(db, 2), post, body="이렇게 해보세요")
    assert len(posts.list_answers(db, post, viewer_id=3)) == 1

    safety.block(db, _u(db, 3), _u(db, 2))
    assert posts.list_answers(db, post, viewer_id=3) == [], "차단한 사람의 답변은 빠진다"

    safety.block(db, _u(db, 3), _u(db, 1))
    assert posts.list_posts(db, viewer_id=3) == [], "차단한 사람의 글도 빠진다"


# ── 4. Q&A 의미론 ───────────────────────────────────────────────────────
def test_only_the_asker_can_accept_and_only_one_answer_stays_accepted(db):
    post = _question(db, author_id=1)
    first = posts.create_answer(db, _u(db, 2), post, body="A")
    second = posts.create_answer(db, _u(db, 3), post, body="B")

    with pytest.raises(posts.PostError):
        posts.accept_answer(db, _u(db, 2), post, first)   # 답변자가 자기 답을 채택할 수 없다

    posts.accept_answer(db, _u(db, 1), post, first)
    assert post.accepted_answer_id == first.id and first.is_accepted is True

    posts.accept_answer(db, _u(db, 1), post, second)
    db.refresh(first)
    assert post.accepted_answer_id == second.id
    assert second.is_accepted is True and first.is_accepted is False, "채택은 하나뿐이다"


def test_accepted_flag_and_post_pointer_never_disagree(db):
    post = _question(db, author_id=1)
    answer = posts.create_answer(db, _u(db, 2), post, body="A")
    posts.accept_answer(db, _u(db, 1), post, answer)
    posts.unaccept_answer(db, _u(db, 1), post)
    db.refresh(answer)
    accepted = db.query(models.Answer).filter(models.Answer.is_accepted.is_(True)).count()
    assert post.accepted_answer_id is None and accepted == 0


def test_accepted_answer_sorts_first(db):
    post = _question(db, author_id=1)
    posts.create_answer(db, _u(db, 2), post, body="A")
    late = posts.create_answer(db, _u(db, 3), post, body="B")
    posts.toggle_like(db, _u(db, 1), target_type="answer", target_id=late.id)
    posts.accept_answer(db, _u(db, 1), post, late)
    assert posts.list_answers(db, post, viewer_id=1)[0].id == late.id


def test_you_cannot_like_your_own_content(db):
    post = _question(db, author_id=1)
    with pytest.raises(posts.PostError):
        posts.toggle_like(db, _u(db, 1), target_type="post", target_id=post.id)


def test_liking_twice_toggles_off(db):
    post = _question(db, author_id=1)
    assert posts.toggle_like(db, _u(db, 2), target_type="post", target_id=post.id)["likeCount"] == 1
    assert posts.toggle_like(db, _u(db, 2), target_type="post", target_id=post.id)["likeCount"] == 0


def test_answers_are_only_for_questions(db):
    showcase = _question(db, author_id=1, kind="showcase")
    with pytest.raises(posts.PostError):
        posts.create_answer(db, _u(db, 2), showcase, body="답")


def test_unanswered_sort_puts_open_questions_first(db):
    answered = _question(db, author_id=1, title="답이 있는 질문")
    posts.create_answer(db, _u(db, 2), answered, body="A")
    open_one = _question(db, author_id=1, title="답이 없는 질문")
    assert posts.list_posts(db, viewer_id=1, sort="unanswered")[0].id == open_one.id


# ── 5. XSS·입력 정리 ────────────────────────────────────────────────────
@pytest.mark.parametrize("payload, banned", [
    ("<script>alert(1)</script>안녕", "<script"),
    ('<img src=x onerror="steal()">', "onerror"),
    ("[클릭](javascript:alert(1))", "javascript:"),
    ("<iframe src='//evil'></iframe>", "<iframe"),
])
def test_markdown_is_sanitized_on_the_server(payload, banned):
    assert banned.lower() not in posts.sanitize_markdown(payload).lower()


def test_normal_markdown_survives():
    body = "## 제목\n\n- 목록\n- `코드`\n\n[링크](https://example.com)"
    assert posts.sanitize_markdown(body) == body


def test_tags_are_normalized_and_capped():
    assert posts.normalize_tags(["Discord", "discord", "  파일 전송 ", "a" * 40, "x", "y", "z"]) \
        == ["discord", "파일전송", "a" * 24, "x", "y"]


# ── 6. 오류 발췌 ────────────────────────────────────────────────────────
def test_execution_excerpt_carries_only_the_public_payload(db):
    from node_errors import make_error

    post = _question(db, author_id=1)
    error = make_error("DELIVERY_AUTH_FAILED", safe_details={"provider": "discord"},
                       internal_message="Bot token MTIz.REAL.TOKEN rejected")
    row = shares.attach_excerpt(db, post, node_error=error.to_dict(), node_type="discordNode")
    payload = json.dumps(shares.public_excerpt(row), ensure_ascii=False)

    assert row.error_code == "DELIVERY_AUTH_FAILED" and row.error_category == "delivery"
    assert "MTIz.REAL.TOKEN" not in payload
    assert "requestId" not in payload and error.request_id not in payload


def test_excerpt_requires_a_real_error_code(db):
    post = _question(db, author_id=1)
    with pytest.raises(shares.ShareError):
        shares.attach_excerpt(db, post, node_error={"userMessage": "그냥 문구"})


# ── 7. 공유와 가져오기 ──────────────────────────────────────────────────
# 공유는 dry-run 구조 검사를 통과해야 한다 — 가져간 사람의 첫 경험이 "실행이 안 된다"가 되면 안 된다.
# 그래서 여기서는 SECRET_GRAPH(정화 테스트용 노드 뭉치)가 아니라 **실제로 이어진** 그래프를 쓴다.
SHARE_GRAPH = {"nodes": [
    {"id": "s1", "type": "startNode", "data": {}},
    {"id": "v1", "type": "valueNode", "data": {"value": "결과 uploads/9f2a.pdf",
                                               "file_path": "uploads/9f2a.pdf"}},
    # 자격증명 reference 는 살아남아야 한다 — 가져간 사람이 자기 것을 채우는 자리다.
    {"id": "db", "type": "databaseNode", "data": {"connectionString": "{{API_CENTER:database#42}}",
                                                  "query": "SELECT 1"}},
    {"id": "llm", "type": "llmNode", "data": {"model": "gpt-5.6-terra", "apiKey": "sk-REAL-SECRET",
                                              "systemPrompt": "문의는 me@corp.com 으로"}},
    {"id": "dc", "type": "discordNode", "data": {"botToken": "MTIz.REAL.TOKEN",
                                                 "channelId": "123456789012345678"}},
], "edges": [
    {"id": "e1", "source": "s1", "target": "v1"},
    {"id": "e2", "source": "v1", "target": "db"},
    {"id": "e3", "source": "db", "target": "llm"},
    {"id": "e4", "source": "llm", "target": "dc"},
]}


def _project(db, user_id=1, graph=None):
    project = models.Project(user_id=user_id, title="포스터 자동화",
                             graph_data=graph or SHARE_GRAPH, current_revision=3)
    db.add(project)
    db.commit()
    return project


def test_sharing_stores_a_sanitized_immutable_snapshot(db):
    post = _question(db, author_id=1)
    project = _project(db)
    share = shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id, project=project)

    blob = json.dumps(share.graph_snapshot, ensure_ascii=False)
    assert "sk-REAL-SECRET" not in blob and "app-password" not in blob
    assert share.source_revision == 3

    # 원본 프로젝트를 고쳐도 스냅샷은 그대로다 — 포인터가 아니라 사본이다.
    project.graph_data = {"nodes": [], "edges": []}
    db.commit()
    assert len(share.graph_snapshot["nodes"]) > 0


def test_you_can_only_share_your_own_workflow(db):
    post = _question(db, author_id=1)
    project = _project(db, user_id=2)
    with pytest.raises(shares.ShareError):
        shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id, project=project)


def test_sharing_refuses_graphs_with_unknown_node_types(db):
    post = _question(db, author_id=1)
    project = _project(db, graph={"nodes": [{"id": "x", "type": "brandNewNode", "data": {}}], "edges": []})
    with pytest.raises(shares.ShareError) as exc:
        shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id, project=project)
    assert "brandNewNode" in str(exc.value)


def test_import_creates_a_private_copy_with_lineage(db):
    post = _question(db, author_id=1)
    share = shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id,
                                project=_project(db))
    copy = shares.import_share(db, _u(db, 2), share)

    assert copy.user_id == 2 and copy.visibility == "private"
    assert f"share #{share.id}" in copy.description and "revision 3" in copy.description
    assert copy.graph_data == share.graph_snapshot
    assert share.import_count == 1
    assert copy.id != post.id


def test_import_preview_shows_what_must_be_filled_in(db):
    post = _question(db, author_id=1)
    share = shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id,
                                project=_project(db))
    preview = shares.import_preview(share)
    assert "database" in preview["requiredCredentials"]
    fields = {(n["nodeId"], n["field"]) for n in preview["needsInput"]}
    assert ("llm", "apiKey") in fields and ("v1", "file_path") in fields


def test_import_preview_exposes_python_code_in_full(db):
    """코드 전문을 접지 않고 보여준다 — 보안이 아니라 **무엇을 가져오는지 알고 가져간다**는 문제다."""
    post = _question(db, author_id=1)
    graph = {"nodes": [{"id": "s1", "type": "startNode", "data": {}},
                       {"id": "py", "type": "pythonNode", "data": {"code": "output_data = 1"}},
                       {"id": "out", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "s1", "target": "py"},
                       {"id": "e2", "source": "py", "target": "out"}]}
    share = shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id,
                                project=_project(db, graph=graph))
    preview = shares.import_preview(share)
    assert preview["pythonCode"] == [{"nodeId": "py", "code": "output_data = 1"}]
    assert "arbitrary_code" in preview["riskFlags"]


def test_a_post_can_only_carry_one_workflow(db):
    post = _question(db, author_id=1)
    shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id, project=_project(db))
    with pytest.raises(shares.ShareError):
        shares.create_share(db, _u(db, 1), owner_type="post", owner_id=post.id, project=_project(db))


# ── 8. 권한과 삭제 ──────────────────────────────────────────────────────
def test_only_the_author_edits_and_deletes(db):
    post = _question(db, author_id=1)
    with pytest.raises(posts.PostError):
        posts.edit_post(db, _u(db, 2), post, title="가로채기")
    with pytest.raises(posts.PostError):
        posts.delete_post(db, _u(db, 2), post)


def test_staff_can_remove_and_the_post_leaves_listings_but_survives_for_review(db):
    post = _question(db, author_id=1)
    posts.delete_post(db, _u(db, 9), post, is_staff=True)
    assert posts.list_posts(db, viewer_id=1) == []
    # soft delete — 신고 조사 중에 근거가 사라지면 안 된다.
    assert db.query(models.Post).filter(models.Post.id == post.id).first() is not None
    assert post.status == "removed" and post.deleted_at is not None


# ── 글 이미지 ───────────────────────────────────────────────────────────
def _upload(db, *, owner_id, artifact_id, expires_in_days=7):
    """만료 시계가 켜진 커뮤니티 업로드 하나."""
    row = models.UploadedFile(
        artifact_id=artifact_id, owner_user_id=owner_id, uploaded_by_user_id=owner_id,
        original_name=f"{artifact_id}.png", stored_name=f"{artifact_id}.png",
        content_type="image/png", size_bytes=100, purpose="community",
        created_at=datetime.datetime.utcnow(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=expires_in_days))
    db.add(row)
    db.commit()
    return row


def test_images_attached_to_a_post_stop_expiring(db):
    """멀쩡한 글의 그림이 보존 기간이 지났다고 사라지면 안 된다."""
    row = _upload(db, owner_id=1, artifact_id="img-1")
    post = posts.create_post(db, _u(db, 1), kind="question", title="그림 질문",
                             body="본문", image_artifact_ids=["img-1"])
    posts.pin_images(db, post.image_artifact_ids)
    db.commit()

    assert post.image_artifact_ids == ["img-1"]
    assert row.expires_at is None


def test_deleting_a_post_re_arms_its_images_for_cleanup(db):
    """고정만 하고 풀지 않으면 지워진 글의 그림이 영원히 쌓인다."""
    row = _upload(db, owner_id=1, artifact_id="img-2")
    post = posts.create_post(db, _u(db, 1), kind="question", title="그림 질문",
                             body="본문", image_artifact_ids=["img-2"])
    posts.pin_images(db, post.image_artifact_ids)
    db.commit()
    assert row.expires_at is None

    posts.delete_post(db, _u(db, 1), post)

    # 곧바로 지우지 않는다 — soft delete 라 되살아날 수 있다.
    assert row.expires_at is not None
    assert row.expires_at > datetime.datetime.utcnow()


def test_staff_removal_also_re_arms_the_images(db):
    row = _upload(db, owner_id=1, artifact_id="img-3")
    post = posts.create_post(db, _u(db, 1), kind="question", title="그림 질문",
                             body="본문", image_artifact_ids=["img-3"])
    posts.pin_images(db, post.image_artifact_ids)
    db.commit()

    posts.delete_post(db, _u(db, 9), post, is_staff=True)

    assert row.expires_at is not None
