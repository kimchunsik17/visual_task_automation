"""GitLab Trigger / Action (백로그 34 DEV-3 2차, ADR-0036) 테스트.

  1. **REST v4 계약대로 부른다.** PRIVATE-TOKEN, 프로젝트 경로 URL 인코딩, 모드별 메서드·경로·본문. 인스턴스 주소는 정규화·SSRF 검사.
  2. **호출 전에 거른다.** 프로젝트 형식·iid·필수 값·변수 30개 상한.
  3. **트리거는 GitHub 과 같은 키로 평탄화된다.** object_kind 정본, X-Gitlab-Event 헤더는 보조. 필터는 실행 전에.
  4. **mock 은 전 모드를 덮고**, 엔드포인트는 X-Gitlab-Token(static_token) 기본 검증 위에서 걸러진 이벤트를 run 없이 200 으로 답한다.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import mock_service
import node_definition
import webhook_verify
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import gitlab
from connectors.session import ConnectorSession, Response

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
DEFINITION = node_definition.get_definition("gitlabNode")
TRIGGER_DEFINITION = node_definition.get_definition("gitlabTriggerNode")
TOKEN = "glpat-test-not-real"
SAMPLES = {s["id"]: s["payload"] for s in TRIGGER_DEFINITION.mock["samples"]}


class _Recorder:
    def __init__(self, status=200, body=None):
        self.calls = []
        self.status, self.body = status, body

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body if self.body is not None else {})


def _session(rec):
    return ConnectorSession("GitLab", transport=rec, sleep=lambda _s: None)


def _run(mode, rec, **params):
    params.setdefault("project", "acme/site")
    return gitlab.run_action(DEFINITION, mode, TOKEN, params, session=_session(rec))


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    import url_guard

    monkeypatch.setattr(url_guard, "check_url", lambda url: (url, "gitlab.com"))


# ── 1. REST 계약 ───────────────────────────────────────────────────────────

def test_PRIVATE_TOKEN_과_인코딩된_프로젝트_경로로_부른다():
    rec = _Recorder(body={"iid": 42})
    _run("mr.get", rec, number="42")
    call = rec.calls[0]
    assert call["url"] == "https://gitlab.com/api/v4/projects/acme%2Fsite/merge_requests/42"
    assert call["headers"]["PRIVATE-TOKEN"] == TOKEN and call["headers"]["Accept"] == "application/json"
    rec = _Recorder(body={"iid": 1})
    _run("mr.get", rec, project="1234", number="1", baseUrl="gitlab.example.com/group/x")
    assert rec.calls[0]["url"] == "https://gitlab.example.com/api/v4/projects/1234/merge_requests/1"


@pytest.mark.parametrize("mode, method, suffix, params", [
    ("issue.create", "POST", "/issues", {"title": "t", "body": "b", "labels": "bug, ui"}),
    ("issue.comment", "POST", "/issues/57/notes", {"number": "57", "body": "확인"}),
    ("issue.update", "PUT", "/issues/57", {"number": "57", "state": "close"}),
    ("mr.get", "GET", "/merge_requests/42", {"number": "42"}),
    ("mr.diff", "GET", "/merge_requests/42/changes", {"number": "!42"}),
    ("mr.merge", "PUT", "/merge_requests/42/merge", {"number": "42", "squash": True}),
    ("mr.comment", "POST", "/merge_requests/42/notes", {"number": "42", "body": "리뷰"}),
    ("pipeline.trigger", "POST", "/pipeline", {"ref": "main"}),
    ("pipeline.get", "GET", "/pipelines/318", {"pipelineId": "318"}),
    ("release.create", "POST", "/releases", {"tagName": "v1.0.0", "title": "v1"}),
    ("file.get", "GET", "/repository/files/docs%2FREADME.md/raw", {"path": "docs/README.md", "ref": "main"}),
])
def test_모드마다_정해진_메서드와_경로(mode, method, suffix, params):
    rec = _Recorder(status=201 if method == "POST" else 200, body={"iid": 42, "changes": []} if mode != "file.get" else "text")
    _run(mode, rec, **params)
    call = rec.calls[0]
    assert call["method"] == method and call["url"] == "https://gitlab.com/api/v4/projects/acme%2Fsite" + suffix


def test_이슈_생성과_수정_본문():
    rec = _Recorder(status=201, body={"iid": 58, "web_url": "u", "title": "t", "state": "opened", "labels": ["bug"]})
    result = _run("issue.create", rec, title="t", body="b", labels="bug, ui, bug")
    assert rec.calls[0]["json"] == {"title": "t", "description": "b", "labels": "bug,ui"} and result["number"] == 58
    rec = _Recorder(body={"iid": 57, "state": "closed"})
    _run("issue.update", rec, number="57", state="close", labels="bug")
    assert rec.calls[0]["json"] == {"state_event": "close", "labels": "bug"}
    rec = _Recorder(body={"iid": 57})
    _run("issue.update", rec, number="57", state="reopen", title="새 제목")
    assert rec.calls[0]["json"] == {"title": "새 제목", "state_event": "reopen"}


def test_MR_diff_는_changes_를_diff_텍스트로_합치고_상한을_표시한다(monkeypatch):
    rec = _Recorder(body={"changes": [{"old_path": "a.py", "new_path": "a.py", "diff": "@@ -1 +1 @@\n-x\n+y\n"},
                                      {"old_path": "b.py", "new_path": "b.py", "diff": "@@ -1 +1 @@\n-1\n+2\n"}]})
    result = _run("mr.diff", rec, number="42")
    assert result["files"] == 2 and result["diff"].startswith("diff --git a/a.py b/a.py\n@@") and "diff --git a/b.py" in result["diff"]
    monkeypatch.setattr(gitlab, "MAX_DIFF_CHARS", 10)
    assert _run("mr.diff", _Recorder(body={"changes": [{"old_path": "a", "new_path": "a", "diff": "x" * 50}]}), number="42")["truncated"] is True


def test_머지_옵션과_파이프라인_변수():
    rec = _Recorder(body={"iid": 42, "state": "merged", "merge_commit_sha": "abc"})
    result = _run("mr.merge", rec, number="42", squash=True, removeSourceBranch="true", commitTitle="머지")
    assert rec.calls[0]["json"] == {"squash": True, "merge_commit_message": "머지", "should_remove_source_branch": True}
    assert result["merged"] is True and result["sha"] == "abc"
    rec = _Recorder(status=201, body={"id": 319, "status": "created", "web_url": "u"})
    result = _run("pipeline.trigger", rec, variables='{"ENV": "staging", "DRY": true}')
    assert rec.calls[0]["json"] == {"ref": "main", "variables": [{"key": "ENV", "value": "staging"}, {"key": "DRY", "value": "true"}]}
    assert result["pipelineId"] == 319 and result["ref"] == "main"


def test_파일_읽기와_릴리스():
    rec = _Recorder(body="# 제목\n본문")
    result = _run("file.get", rec, path="/README.md")
    assert rec.calls[0]["params"] == {"ref": "main"} and result["content"] == "# 제목\n본문" and result["size"] == 7
    rec = _Recorder(status=201, body={"tag_name": "v1", "name": "v1", "_links": {"self": "https://gitlab.com/acme/site/-/releases/v1"}})
    result = _run("release.create", rec, tagName="v1", title="v1", body="노트", ref="main")
    assert rec.calls[0]["json"] == {"tag_name": "v1", "name": "v1", "description": "노트", "ref": "main"} and result["url"].endswith("/releases/v1")


# ── 2. 호출 전에 거른다 ───────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "acme", "../x", "acme/../site", "a b/c"])
def test_프로젝트_형식이_어긋나면_호출하지_않는다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run("mr.get", rec, project=bad, number="1")
    assert exc.value.code == "invalid_request" and rec.calls == []


def test_프로젝트는_GitLab_주소_형태도_받는다():
    assert gitlab.project_ref("https://gitlab.com/acme/site.git") == "acme%2Fsite"
    assert gitlab.project_ref("https://gitlab.com/acme/site/-/merge_requests/42") == "acme%2Fsite"
    assert gitlab.project_ref("1234") == "1234"


@pytest.mark.parametrize("mode, params", [
    ("mr.get", {"number": ""}), ("mr.get", {"number": "abc"}), ("issue.create", {"title": ""}), ("issue.comment", {"number": "1", "body": ""}),
    ("issue.update", {"number": "1"}), ("issue.update", {"number": "1", "state": "half"}), ("pipeline.get", {"pipelineId": "x"}),
    ("pipeline.trigger", {"variables": "not json"}), ("pipeline.trigger", {"variables": json.dumps({f"K{i}": "v" for i in range(31)})}),
    ("release.create", {"tagName": ""}), ("file.get", {"path": ""}), ("file.get", {"path": "../secret"}),
])
def test_잘못된_입력은_호출하지_않는다(mode, params):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run(mode, rec, **params)
    assert exc.value.code == "invalid_request" and rec.calls == []


def test_인스턴스_주소는_https_이고_SSRF_검사를_거친다(monkeypatch):
    with pytest.raises(ConnectorError):
        gitlab.normalize_base_url("http://gitlab.example.com")
    assert gitlab.normalize_base_url("") == "https://gitlab.com" and gitlab.normalize_base_url("https://gl.example.com:8443/a/b") == "https://gl.example.com:8443"
    import url_guard

    def block(url):
        raise url_guard.UrlBlocked("사설 주소", reason="PRIVATE")

    monkeypatch.setattr(url_guard, "check_url", block)
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run("mr.get", rec, number="1", baseUrl="https://10.0.0.5")
    assert "허용 목록" in (exc.value.detail or "") and rec.calls == []


def test_모르는_모드와_빈_토큰():
    with pytest.raises(ConnectorError) as exc:
        _run("wiki.create", _Recorder())
    assert exc.value.code == "invalid_request"
    with pytest.raises(ConnectorError) as exc:
        gitlab.run_action(DEFINITION, "mr.get", "", {"project": "a/b", "number": "1"}, session=_session(_Recorder()))
    assert exc.value.code == "auth_missing"


def test_비운_인스턴스_프로젝트_번호_태그는_트리거_출력에서_이어받는다():
    upstream = json.dumps({"repo": "acme/site", "number": 42, "tag": "v2", "instance": "https://gl.example.com"})
    params = gitlab.fill_from_upstream({"project": "", "number": "", "tagName": "", "baseUrl": ""}, upstream)
    assert (params["project"], params["number"], params["tagName"], params["baseUrl"]) == ("acme/site", "42", "v2", "https://gl.example.com")
    assert gitlab.fill_from_upstream({"project": "x/y"}, upstream)["project"] == "x/y"


# ── 3. 트리거 ──────────────────────────────────────────────────────────────

def test_샘플_세_종이_GitHub_과_같은_키로_평탄화된다():
    mr = gitlab.flatten_envelope(SAMPLES["merge_request_opened"])
    assert (mr["event"], mr["action"], mr["repo"], mr["number"], mr["branch"], mr["baseBranch"]) == ("merge_request", "open", "acme/site", 42, "feature/login-validation", "main")
    assert mr["labels"] == ["enhancement"] and mr["author"] == "octocat" and mr["instance"] == "https://gitlab.com" and mr["draft"] is False
    issue = gitlab.flatten_envelope(SAMPLES["issue_opened"])
    assert (issue["event"], issue["number"], issue["author"], issue["state"]) == ("issue", 57, "jane-doe", "opened")
    pipe = gitlab.flatten_envelope(SAMPLES["pipeline_failed"])
    assert (pipe["event"], pipe["status"], pipe["branch"], pipe["pipelineId"]) == ("pipeline", "failed", "main", 318)
    for item in (mr, issue, pipe):
        assert set(("event", "action", "repo", "instance", "number", "title", "body", "url", "branch", "labels", "raw", "delivery")) <= set(item)


def test_object_kind_가_정본이고_헤더는_보조다():
    assert gitlab.normalize_event("Merge Request Hook", {}) == "merge_request"
    assert gitlab.normalize_event("Push Hook", {"object_kind": "tag_push"}) == "tag_push"
    assert gitlab.normalize_event("Confidential Issue Hook", {}) == "issue"
    assert gitlab.normalize_event("", {}) == ""


def test_push_note_release_평탄화():
    push = {"object_kind": "push", "ref": "refs/heads/main", "after": "a1", "user_username": "octocat", "total_commits_count": 1,
            "project": {"path_with_namespace": "acme/site", "web_url": "https://gitlab.com/acme/site"},
            "commits": [{"id": "a1", "message": "fix: 로그인\n\n본문", "title": "fix: 로그인", "author": {"name": "Octo"}, "url": "u"}]}
    flat = gitlab.flatten_event("push", push)
    assert flat["branch"] == "main" and flat["sha"] == "a1" and flat["title"] == "fix: 로그인" and flat["commitCount"] == 1 and flat["author"] == "octocat"
    tag = gitlab.flatten_event("tag_push", {**push, "object_kind": "tag_push", "ref": "refs/tags/v1.0.0"})
    assert tag["tag"] == "v1.0.0" and tag["branch"] == ""
    note = gitlab.flatten_event("note", {"object_kind": "note", "user": {"username": "jane"}, "project": {"path_with_namespace": "a/b"},
                                         "object_attributes": {"note": "LGTM", "noteable_type": "MergeRequest", "url": "u"},
                                         "merge_request": {"iid": 42, "title": "MR", "source_branch": "f", "target_branch": "main"}})
    assert note["number"] == 42 and note["comment"] == "LGTM" and note["noteableType"] == "MergeRequest" and note["baseBranch"] == "main"
    rel = gitlab.flatten_event("release", {"object_kind": "release", "tag": "v2", "name": "v2 릴리스", "description": "노트", "url": "u", "action": "create",
                                           "project": {"path_with_namespace": "a/b"}})
    assert rel["tag"] == "v2" and rel["title"] == "v2 릴리스" and rel["action"] == "create"


def test_필터_이벤트_action_브랜치_라벨():
    mr = SAMPLES["merge_request_opened"]["payload"]
    ok = gitlab.trigger_matches
    assert ok({}, "Merge Request Hook", mr) == (True, "")
    assert ok({"events": "issue, pipeline"}, "Merge Request Hook", mr)[0] is False
    assert ok({"actionFilter": "merge"}, "Merge Request Hook", mr)[0] is False
    assert ok({"actionFilter": "open, reopen"}, "Merge Request Hook", mr)[0] is True
    assert ok({"branchFilter": "release/*"}, "Merge Request Hook", mr)[0] is False
    assert ok({"branchFilter": "main"}, "Merge Request Hook", mr)[0] is True
    assert ok({"labelFilter": "bug"}, "Merge Request Hook", mr)[0] is False
    assert ok({"labelFilter": "enhancement"}, "Merge Request Hook", mr)[0] is True
    assert ok({"branchFilter": "main"}, "Issue Hook", SAMPLES["issue_opened"]["payload"])[0] is True, "브랜치 없는 이벤트는 거르지 않는다"
    assert ok({}, "", {})[0] is False


def test_GitLab_트리거의_기본_검증은_static_token_이고_인바운드_표에_있다():
    assert webhook_verify.settings_from_node({"type": "gitlabTriggerNode", "data": {}}).mode == "static_token"
    assert webhook_verify.settings_from_node({"type": "gitlabTriggerNode", "data": {}}).header == "X-Gitlab-Token"
    assert "gitlabTriggerNode" in webhook_verify.INBOUND_NODE_TYPES
    assert webhook_verify.INBOUND_SERVICES["gitlabTriggerNode"]["module"] == "gitlab"


# ── 4. mock·그래프 ─────────────────────────────────────────────────────────

_MOCK_PARAMS = {"project": "acme/site", "number": "42", "title": "t", "body": "b", "labels": "bug", "tagName": "v2.3.0", "ref": "main",
                "pipelineId": "318", "path": "README.md"}


@pytest.mark.parametrize("mode", gitlab.MODES)
def test_성공_시나리오가_모든_모드를_재생한다(mode):
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    session = DEFINITION.new_session(transport=transport, sleep=lambda _s: None)
    result = gitlab.run_action(DEFINITION, mode, TOKEN, dict(_MOCK_PARAMS), session=session)
    assert result["mode"] == mode and result["instance"] == "https://gitlab.com"
    if mode == "mr.diff":
        assert result["diff"].startswith("diff --git") and result["files"] == 1
    if mode == "mr.get":
        assert result["number"] == 42 and result["baseBranch"] == "main"
    if mode == "file.get":
        assert "acme/site" in result["content"]


def test_모드_선언과_시나리오_계약():
    assert set(DEFINITION.connector.modes) == set(gitlab.MODES)
    for mode in gitlab.MODES:
        assert DEFINITION.connector.writes_externally(mode) == (mode not in gitlab.READ_MODES), mode
    assert not mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector, label="gitlabNode")


@pytest.mark.parametrize("scenario, code", [("auth_failed", "auth_invalid"), ("rate_limited", "rate_limited"), ("not_found", "not_found"), ("timeout", "timeout")])
def test_실패_시나리오(scenario, code):
    transport = mock_fixtures.transport_for(DEFINITION.mock, scenario)
    session = DEFINITION.new_session(transport=transport, sleep=lambda _s: None)
    with pytest.raises(ConnectorError) as exc:
        gitlab.run_action(DEFINITION, "mr.get", TOKEN, dict(_MOCK_PARAMS), session=session)
    assert exc.value.code == code


def test_목업_실행_트리거에서_액션까지_인스턴스_프로젝트_번호가_이어진다():
    graph = {"nodes": [{"id": "t1", "type": "gitlabTriggerNode", "data": {"events": "merge_request"}},
                       {"id": "g1", "type": "gitlabNode", "data": {"mode": "mr.comment", "body": "리뷰 완료"}},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "t1", "target": "g1"}, {"id": "e2", "source": "g1", "target": "o1"}]}
    described = mock_service.describe_graph(graph)
    assert [s["id"] for s in described["entries"][0]["samples"]] == ["merge_request_opened", "issue_opened", "pipeline_failed"]
    result = mock_service.run(graph, db=None, project_id=1, entry_node_id="t1", payload=SAMPLES["merge_request_opened"])
    assert result["success"] is True, result["result"]
    assert [r["url"] for r in result["requests"]] == ["https://gitlab.com/api/v4/projects/acme%2Fsite/merge_requests/42/notes"]
    assert result["requests"][0]["request_headers"].get("PRIVATE-TOKEN") == "[redacted]" or "PRIVATE-TOKEN" not in result["requests"][0]["request_headers"] \
        or result["requests"][0]["request_headers"]["PRIVATE-TOKEN"] != TOKEN


# ── 5. 엔드포인트 ─────────────────────────────────────────────────────────

SCENARIO = r'''
import os, sys, json
os.environ["DATABASE_URL"] = sys.argv[1]
for k in ("DEMO_GUEST", "DEMO_GUEST_TOKENS", "DEMO_GUEST_MAX", "DEMO_UI", "HIDDEN_NODE_TYPES", "LLM_PROVIDER",
          "OPENROUTER_BASE_URL", "PICKLE_API_KEY", "EXECUTION_QUEUE", "EXECUTION_WORKER_INPROCESS"):
    os.environ[k] = ""
sys.path.insert(0, sys.argv[2])
os.chdir(os.path.dirname(sys.argv[1].replace("sqlite:///", "")))
from fastapi.testclient import TestClient
import main, models, node_definition
from credential_crypto import encrypt_secret
from database import SessionLocal
client = TestClient(main.app)
db = SessionLocal()
SECRET = "gl-webhook-secret-token"
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
db.add(owner); db.commit()
db.add(models.UserApiKey(user_id=owner.id, provider="webhook_secret", api_key=encrypt_secret(SECRET))); db.commit()
def project(title, **tdata):
    p = models.Project(user_id=owner.id, title=title, graph_data={"is_live": True,
        "nodes": [{"id": "t", "type": "gitlabTriggerNode", "data": tdata}, {"id": "o", "type": "outputNode", "data": {}}],
        "edges": [{"source": "t", "target": "o"}]})
    db.add(p); db.commit(); return p
strict = project("MR/이슈 열림", events="merge_request, issue", actionFilter="open, reopen")
runs = lambda pid: db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == pid).count()
samples = {s["id"]: s["payload"] for s in node_definition.get_definition("gitlabTriggerNode").mock["samples"]}
def post(p, sample_id, event, uuid, *, token=SECRET, raw=None):
    body = raw if raw is not None else json.dumps(samples[sample_id]["payload"], ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Gitlab-Event": event, "X-Gitlab-Event-UUID": uuid}
    if token is not None:
        headers["X-Gitlab-Token"] = token
    return client.post(f"/webhook/{p.id}", content=body, headers=headers)

r = post(strict, "merge_request_opened", "Merge Request Hook", "u-1")
assert r.status_code == 200 and r.json()["status"] == "success", r.text
assert '"repo": "acme/site"' in r.json()["result"] and '"number": 42' in r.json()["result"] and '"instance": "https://gitlab.com"' in r.json()["result"]
db.expire_all(); assert runs(strict.id) == 1
assert post(strict, "merge_request_opened", "Merge Request Hook", "u-2", token="wrong").status_code == 401
assert post(strict, "merge_request_opened", "Merge Request Hook", "u-3", token=None).status_code == 401
r = post(strict, "pipeline_failed", "Pipeline Hook", "u-4")
assert r.status_code == 200 and r.json()["status"] == "ignored" and r.json()["event"] == "Pipeline Hook", r.text
closed = json.dumps({**samples["issue_opened"]["payload"], "object_attributes": {**samples["issue_opened"]["payload"]["object_attributes"], "action": "close"}}).encode()
assert post(strict, None, "Issue Hook", "u-5", raw=closed).json()["status"] == "ignored"
db.expire_all(); assert runs(strict.id) == 1
r = post(strict, "issue_opened", "Issue Hook", "u-6")
assert r.json()["status"] == "success", r.text
assert post(strict, "issue_opened", "Issue Hook", "u-6").json()["status"] == "duplicate"
db.expire_all(); assert runs(strict.id) == 2
print("GITLAB TRIGGER OK")
'''


def test_gitlab_trigger_endpoint_end_to_end(tmp_path):
    scenario_path = tmp_path / "gitlab_trigger_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'gitlab.db'}"
    result = subprocess.run([sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)], cwd=BACKEND_DIR,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, f"stdout:\n{result.stdout[-3000:]}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "GITLAB TRIGGER OK" in result.stdout
