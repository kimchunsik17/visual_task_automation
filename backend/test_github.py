"""GitHub Trigger / Action (백로그 34 DEV-1, ADR-0032) 테스트.

이 파일이 지키는 문장:

  1. **REST 계약대로 부른다.** Bearer 토큰·`X-GitHub-Api-Version`·`application/vnd.github+json`, 모드별 메서드·경로·본문.
     PR diff 는 같은 URL 에 Accept 만 다르다.
  2. **호출 전에 거른다.** repo 형식·번호·필수 값·workflow inputs 25개 상한은 나가기 전에 잡는다 — 한도(5,000/h)를 축내며 배울 이유가 없다.
  3. **한도는 한도로 읽는다.** GitHub 1차 한도는 `403 + x-ratelimit-remaining: 0` 이다. 권한 오류로 안내하면 사용자가 토큰 권한을 헛되이 뒤진다.
  4. **트리거는 실행 전에 거른다.** events·action·브랜치·라벨 필터에 걸린 전달은 run 을 만들지 않고 200 으로 답한다. 통과한 이벤트는
     이벤트 종류가 달라도 같은 키(repo·number·title·url …)로 평탄화된다.
  5. **mock 은 모든 모드를 덮는다.** 성공 시나리오에 없는 모드가 있으면 목업 탭에서 그 모드만 MockScenarioError 로 깨진다.
"""

from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import sys
import time

import pytest

import node_definition
import webhook_verify
from connectors import errors, mock_runtime
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import github
from connectors.session import ConnectorSession, Response

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
DEFINITION = node_definition.get_definition("githubNode")
TRIGGER_DEFINITION = node_definition.get_definition("githubTriggerNode")
TOKEN = "github_pat_test_not_real"
SAMPLES = {sample["id"]: sample["payload"] for sample in TRIGGER_DEFINITION.mock["samples"]}


class _Recorder:
    """호출 내용을 잡아 두는 transport. 상태·본문을 호출 순서대로 줄 수도 있다."""

    def __init__(self, status=200, body=None, sequence=None):
        self.calls = []
        self.status, self.body = status, body
        self.sequence = list(sequence or [])

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.sequence:
            status, body = self.sequence.pop(0)
            return Response(status=status, headers={}, body=body)
        return Response(status=self.status, headers={}, body=self.body if self.body is not None else {})


def _session(transport):
    return ConnectorSession("GitHub", transport=transport, sleep=lambda _s: None)


def _run(mode, transport, **params):
    params.setdefault("repo", "acme/site")
    return github.run_action(DEFINITION, mode, TOKEN, params, session=_session(transport))


# ── 1. REST 계약 ───────────────────────────────────────────────────────────

def test_Bearer_토큰과_API_버전_헤더로_부른다():
    rec = _Recorder(body={"number": 42})
    _run("pr.get", rec, number="42")
    call = rec.calls[0]
    assert call["method"] == "GET" and call["url"] == "https://api.github.com/repos/acme/site/pulls/42"
    headers = call["headers"]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["X-GitHub-Api-Version"] == github.API_VERSION
    assert headers["Accept"] == "application/vnd.github+json"


@pytest.mark.parametrize("mode, method, suffix, params", [
    ("issue.create", "POST", "/issues", {"title": "t", "body": "b", "labels": "bug, ui", "assignees": "octocat"}),
    ("issue.comment", "POST", "/issues/42/comments", {"number": "42", "body": "확인"}),
    ("pr.comment", "POST", "/issues/42/comments", {"number": "#42", "body": "리뷰"}),
    ("issue.update", "PATCH", "/issues/42", {"number": "42", "state": "closed"}),
    ("pr.get", "GET", "/pulls/42", {"number": "42"}),
    ("pr.merge", "PUT", "/pulls/42/merge", {"number": "42", "mergeMethod": "rebase", "commitTitle": "머지"}),
    ("release.create", "POST", "/releases", {"tagName": "v1.0.0", "title": "v1", "draft": True}),
    ("release.generate_notes", "POST", "/releases/generate-notes", {"tagName": "v1.0.0", "previousTagName": "v0.9.0"}),
    ("workflow.dispatch", "POST", "/actions/workflows/deploy.yml/dispatches", {"workflowId": "deploy.yml", "ref": "main"}),
    ("dependabot.list", "GET", "/dependabot/alerts", {"severity": "high, critical", "ecosystem": "npm", "perPage": "500"}),
    ("file.get", "GET", "/contents/docs/README.md", {"path": "docs/README.md", "ref": "main"}),
])
def test_모드마다_정해진_메서드와_경로로_간다(mode, method, suffix, params):
    body = [] if mode == "dependabot.list" else {"number": 42, "encoding": "base64", "content": ""}
    rec = _Recorder(status=204 if mode == "workflow.dispatch" else 200, body=body)
    _run(mode, rec, **params)
    call = rec.calls[0]
    assert call["method"] == method
    assert call["url"] == "https://api.github.com/repos/acme/site" + suffix


def test_이슈_생성_본문은_라벨과_담당자를_배열로_싣는다():
    rec = _Recorder(status=201, body={"number": 58, "html_url": "https://github.com/acme/site/issues/58", "title": "t", "state": "open"})
    result = _run("issue.create", rec, title="t", body="b", labels="bug, ui, bug", assignees="octocat")
    assert rec.calls[0]["json"] == {"title": "t", "body": "b", "labels": ["bug", "ui"], "assignees": ["octocat"]}
    assert result["number"] == 58 and result["url"].endswith("/issues/58") and result["mode"] == "issue.create"


def test_PR_diff_는_같은_URL_에_Accept_만_다르고_상한을_넘으면_잘라_표시한다(monkeypatch):
    monkeypatch.setattr(github, "MAX_DIFF_CHARS", 20)
    rec = _Recorder(body="diff --git a/x b/x\n" * 5)
    result = _run("pr.diff", rec, number="42")
    assert rec.calls[0]["headers"]["Accept"] == "application/vnd.github.diff"
    assert rec.calls[0]["url"].endswith("/pulls/42")
    assert result["truncated"] is True and len(result["diff"]) == 20 and result["chars"] == 95


def test_머지_요청은_merge_method_와_commit_title_을_싣는다():
    rec = _Recorder(body={"merged": True, "sha": "abc", "message": "ok"})
    result = _run("pr.merge", rec, number="42", mergeMethod="rebase", commitTitle="머지")
    assert rec.calls[0]["json"] == {"merge_method": "rebase", "commit_title": "머지"}
    assert result["merged"] is True and result["mergeMethod"] == "rebase"


def test_라벨_제거는_라벨마다_DELETE_하고_없던_라벨의_404_는_넘어간다():
    rec = _Recorder(sequence=[(404, {"message": "Label does not exist"}), (200, [{"name": "ui"}])])
    result = _run("issue.labels", rec, number="42", labelAction="remove", labels="bug, stale")
    assert [c["method"] for c in rec.calls] == ["DELETE", "DELETE"]
    assert rec.calls[0]["url"].endswith("/issues/42/labels/bug") and rec.calls[1]["url"].endswith("/issues/42/labels/stale")
    assert result["removed"] == ["stale"] and result["labels"] == ["ui"]


def test_라벨_교체는_PUT_추가는_POST():
    rec = _Recorder(body=[{"name": "bug"}])
    _run("issue.labels", rec, number="42", labelAction="set", labels="bug")
    assert rec.calls[0]["method"] == "PUT" and rec.calls[0]["json"] == {"labels": ["bug"]}
    rec = _Recorder(body=[{"name": "bug"}])
    _run("issue.labels", rec, number="42", labelAction="add", labels="bug")
    assert rec.calls[0]["method"] == "POST"


def test_릴리스_본문이_비면_GitHub_자동_노트를_켜고_비지_않으면_본문을_보낸다():
    rec = _Recorder(status=201, body={"id": 1, "tag_name": "v1", "html_url": "u"})
    _run("release.create", rec, tagName="v1", title="이름", targetCommitish="main")
    payload = rec.calls[0]["json"]
    assert payload["generate_release_notes"] is True and "body" not in payload
    assert payload["name"] == "이름" and payload["target_commitish"] == "main" and payload["draft"] is False
    rec = _Recorder(status=201, body={"id": 1, "tag_name": "v1", "html_url": "u"})
    _run("release.create", rec, tagName="v1", body="노트", prerelease="true")
    payload = rec.calls[0]["json"]
    assert payload["body"] == "노트" and "generate_release_notes" not in payload and payload["prerelease"] is True


def test_워크플로우_inputs_는_문자열로_바꿔_보내고_ref_기본값은_main():
    rec = _Recorder(status=204, body="")
    result = _run("workflow.dispatch", rec, workflowId="deploy.yml", inputs='{"env": "staging", "dry": true, "n": 3}')
    assert rec.calls[0]["json"] == {"ref": "main", "inputs": {"env": "staging", "dry": "true", "n": "3"}}
    assert result["dispatched"] is True and result["ref"] == "main"


def test_Dependabot_조회는_상태_심각도_생태계를_쿼리로_싣고_per_page_를_100_으로_깎는다():
    rec = _Recorder(body=[{"number": 3, "state": "open", "security_advisory": {"severity": "high", "summary": "s"},
                          "dependency": {"package": {"ecosystem": "npm", "name": "lodash"}}, "html_url": "u"}])
    result = _run("dependabot.list", rec, alertState="open", severity="high, critical", ecosystem="npm", perPage="500")
    assert rec.calls[0]["params"] == {"state": "open", "severity": "high,critical", "ecosystem": "npm", "per_page": 100}
    assert result["count"] == 1 and result["alerts"][0]["package"] == "lodash" and result["alerts"][0]["severity"] == "high"


def test_파일_읽기는_base64_를_풀고_디렉터리는_목록으로_준다():
    text = "# README\n한글도 그대로\n"
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    rec = _Recorder(body={"type": "file", "path": "README.md", "sha": "s", "size": 9, "encoding": "base64",
                          "content": encoded[:10] + "\n" + encoded[10:], "html_url": "u"})
    result = _run("file.get", rec, path="/README.md")
    assert result["content"] == text and result["binary"] is False and result["truncated"] is False
    rec = _Recorder(body=[{"name": "a.md", "path": "docs/a.md", "type": "file", "size": 1}])
    result = _run("file.get", rec, path="docs")
    assert result["type"] == "dir" and result["entries"][0]["path"] == "docs/a.md"


def test_저장소는_GitHub_주소_형태도_받아_owner_repo_로_정규화한다():
    assert github.normalize_repo("https://github.com/acme/site.git") == "acme/site"
    assert github.normalize_repo(" acme/site ") == "acme/site"


# ── 2. 호출 전에 거른다 ───────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "acme", "acme/site/extra", "../x", "acme/..", "a b/c"])
def test_저장소_형식이_어긋나면_호출하지_않는다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run("pr.get", rec, repo=bad, number="1")
    assert exc.value.code == "invalid_request" and rec.calls == []


@pytest.mark.parametrize("mode, params", [
    ("pr.get", {"number": ""}), ("pr.get", {"number": "abc"}), ("pr.get", {"number": "0"}),
    ("issue.create", {"title": ""}), ("issue.comment", {"number": "1", "body": ""}),
    ("issue.labels", {"number": "1", "labelAction": "add", "labels": ""}), ("issue.labels", {"number": "1", "labelAction": "zap", "labels": "x"}),
    ("issue.update", {"number": "1"}), ("issue.update", {"number": "1", "state": "half"}),
    ("pr.merge", {"number": "1", "mergeMethod": "fast"}), ("release.create", {"tagName": ""}),
    ("workflow.dispatch", {"workflowId": ""}), ("workflow.dispatch", {"workflowId": "x.yml", "inputs": "not json"}),
    ("workflow.dispatch", {"workflowId": "x.yml", "inputs": json.dumps({f"k{i}": "v" for i in range(26)})}),
    ("file.get", {"path": ""}), ("file.get", {"path": "../secret"}),
])
def test_잘못된_입력은_호출하지_않는다(mode, params):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run(mode, rec, **params)
    assert exc.value.code == "invalid_request" and rec.calls == []


def test_모르는_모드와_빈_토큰은_호출하지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _run("repo.delete", rec)
    assert exc.value.code == "invalid_request" and rec.calls == []
    with pytest.raises(ConnectorError) as exc:
        github.run_action(DEFINITION, "pr.get", "", {"repo": "acme/site", "number": "1"}, session=_session(rec))
    assert exc.value.code == "auth_missing" and rec.calls == []


def test_비운_repo_number_tagName_은_직전_트리거_출력에서_이어받는다():
    upstream = json.dumps({"repo": "acme/site", "number": 42, "tag": "v2.3.0", "title": "x"})
    params = github.fill_from_upstream({"repo": "", "number": "", "tagName": "", "title": ""}, upstream)
    assert (params["repo"], params["number"], params["tagName"], params["title"]) == ("acme/site", "42", "v2.3.0", "")
    kept = github.fill_from_upstream({"repo": "other/repo", "number": "7"}, upstream)
    assert (kept["repo"], kept["number"]) == ("other/repo", "7")
    assert github.fill_from_upstream({"repo": ""}, "그냥 텍스트")["repo"] == ""


def test_parse_list_는_쉼표_줄바꿈_JSON_배열을_모두_받고_중복을_없앤다():
    assert github.parse_list("bug, ui\nbug") == ["bug", "ui"]
    assert github.parse_list('["a", "b"]') == ["a", "b"]
    assert github.parse_list(["x", " y "]) == ["x", "y"]
    assert github.parse_list("") == [] and github.parse_list(None) == []


# ── 3. 한도는 한도로 읽는다 ───────────────────────────────────────────────

def test_403_에_x_ratelimit_remaining_0_은_권한_오류가_아니라_한도다():
    reset = int(time.time()) + 120
    error = errors.from_response(403, service="GitHub", body={"message": "API rate limit exceeded"},
                                 headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)})
    assert error.code == "rate_limited" and error.retryable
    assert 100 <= error.retry_after <= 121
    plain = errors.from_response(403, service="GitHub", body={"message": "Resource not accessible"}, headers={"x-ratelimit-remaining": "4999"})
    assert plain.code == "auth_forbidden"


def test_429_에_Retry_After_가_없으면_x_ratelimit_reset_으로_대기시간을_잡는다():
    error = errors.from_response(429, service="GitHub", headers={"x-ratelimit-reset": str(int(time.time()) + 30)})
    assert error.code == "rate_limited" and 10 <= error.retry_after <= 31
    explicit = errors.from_response(429, service="GitHub", headers={"Retry-After": "60", "x-ratelimit-reset": "1"})
    assert explicit.retry_after == 60.0


# ── 4. 트리거: 평탄화와 필터 ──────────────────────────────────────────────

def test_샘플_네_종이_같은_키로_평탄화된다():
    flat = {name: github.flatten_envelope(payload) for name, payload in SAMPLES.items()}
    pr = flat["pull_request_opened"]
    assert (pr["event"], pr["action"], pr["repo"], pr["number"]) == ("pull_request", "opened", "acme/site", 42)
    assert pr["branch"] == "feature/login-validation" and pr["baseBranch"] == "main" and pr["labels"] == ["enhancement"]
    assert pr["url"].endswith("/pull/42") and pr["author"] == "octocat" and pr["delivery"].startswith("72d3162e")
    issue = flat["issues_opened"]
    assert (issue["event"], issue["number"], issue["author"]) == ("issues", 57, "jane-doe") and issue["title"].startswith("결제")
    release = flat["release_published"]
    assert (release["event"], release["tag"], release["action"]) == ("release", "v2.3.0", "published")
    ci = flat["workflow_run_failed"]
    assert (ci["event"], ci["status"], ci["conclusion"], ci["branch"], ci["name"]) == ("workflow_run", "completed", "failure", "main", "CI")
    for item in flat.values():
        assert set(("event", "action", "repo", "number", "title", "body", "url", "branch", "labels", "raw", "delivery")) <= set(item)


def test_이벤트_헤더_없이_원본_payload_만_오면_모양으로_추정하고_JSON_이_아니면_raw_로_남긴다():
    raw = SAMPLES["pull_request_opened"]["payload"]
    flat = github.flatten_envelope(json.dumps(raw))
    assert flat["event"] == "pull_request" and flat["number"] == 42 and flat["delivery"] == ""
    assert github.infer_event({"issue": {}, "comment": {}}) == "issue_comment"
    assert github.infer_event({"ref": "refs/heads/main", "after": "abc", "commits": []}) == "push"
    assert github.infer_event({"zen": "z", "hook_id": 1}) == "ping"
    plain = github.flatten_envelope("그냥 텍스트")
    assert plain["event"] == "" and plain["raw"] == "그냥 텍스트"
    empty = github.flatten_envelope("<<No input provided>>")
    assert empty["event"] == "" and empty["repo"] == ""


def test_push_는_브랜치와_커밋_목록을_태그_푸시는_tag_를_준다():
    push = {"ref": "refs/heads/main", "after": "a1", "compare": "https://github.com/acme/site/compare/x...y",
            "head_commit": {"id": "a1", "message": "fix: 로그인\n\n본문", "url": "u"}, "pusher": {"name": "octocat"},
            "commits": [{"id": "a1", "message": "fix: 로그인", "author": {"name": "octocat"}, "url": "u"}],
            "repository": {"full_name": "acme/site"}}
    flat = github.flatten_event("push", push)
    assert flat["branch"] == "main" and flat["sha"] == "a1" and flat["title"] == "fix: 로그인" and flat["commitCount"] == 1
    tag = github.flatten_event("push", {**push, "ref": "refs/tags/v1.0.0"})
    assert tag["tag"] == "v1.0.0" and tag["branch"] == ""


def test_필터_이벤트_action_브랜치_라벨():
    pr = SAMPLES["pull_request_opened"]["payload"]
    ok = github.trigger_matches
    assert ok({}, "pull_request", pr) == (True, "")
    assert ok({"events": "issues, release"}, "pull_request", pr)[0] is False
    assert ok({"events": "pull_request"}, "pull_request", pr)[0] is True
    assert ok({"actionFilter": "closed"}, "pull_request", pr)[0] is False
    assert ok({"actionFilter": "opened, reopened"}, "pull_request", pr)[0] is True
    assert ok({"branchFilter": "release/*"}, "pull_request", pr)[0] is False
    assert ok({"branchFilter": "main"}, "pull_request", pr)[0] is True, "PR 은 base 브랜치가 맞아도 통과"
    assert ok({"branchFilter": "feature/*"}, "pull_request", pr)[0] is True, "head 브랜치도 본다"
    assert ok({"labelFilter": "bug"}, "pull_request", pr)[0] is False
    assert ok({"labelFilter": "bug, enhancement"}, "pull_request", pr)[0] is True
    labeled = {**pr, "action": "labeled", "label": {"name": "needs-review"}}
    assert ok({"labelFilter": "needs-review"}, "pull_request", labeled)[0] is True, "방금 붙인 라벨도 본다"
    issue = SAMPLES["issues_opened"]["payload"]
    assert ok({"branchFilter": "main"}, "issues", issue)[0] is True, "브랜치가 없는 이벤트는 브랜치 필터로 거르지 않는다"
    assert ok({}, "ping", {"zen": "z"})[0] is False
    assert ok({}, "", pr)[0] is False


def test_GitHub_트리거의_기본_검증_모드는_HMAC_이고_웹훅_노드는_none_이다():
    assert webhook_verify.settings_from_node({"type": "githubTriggerNode", "data": {}}).mode == "hmac_sha256"
    assert webhook_verify.settings_from_node({"type": "githubTriggerNode", "data": {"verifyMode": "bogus"}}).mode == "hmac_sha256"
    assert webhook_verify.settings_from_node({"type": "githubTriggerNode", "data": {"verifyMode": "none"}}).mode == "none"
    assert webhook_verify.settings_from_node({"type": "webhookNode", "data": {}}).mode == "none"
    assert "githubTriggerNode" in webhook_verify.INBOUND_NODE_TYPES


# ── 5. mock 은 모든 모드를 덮는다 ─────────────────────────────────────────

_MOCK_PARAMS = {"repo": "acme/site", "number": "42", "title": "t", "body": "b", "labels": "bug", "labelAction": "add",
                "tagName": "v2.3.0", "workflowId": "ci.yml", "ref": "main", "path": "README.md"}


@pytest.mark.parametrize("mode", github.MODES)
def test_성공_시나리오가_모든_모드를_재생한다(mode):
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    session = DEFINITION.new_session(transport=transport, sleep=lambda _s: None)
    result = github.run_action(DEFINITION, mode, TOKEN, dict(_MOCK_PARAMS), session=session)
    assert result["mode"] == mode
    if mode == "pr.diff":
        assert result["diff"].startswith("diff --git")
    if mode == "pr.get":
        assert result["number"] == 42 and result["baseBranch"] == "main"
    if mode == "file.get":
        assert "acme/site" in result["content"]
    if mode == "dependabot.list":
        assert result["alerts"][0]["package"] == "lodash"


def test_모드_선언과_시나리오_계약이_맞는다():
    assert set(DEFINITION.connector.modes) == set(github.MODES)
    for mode in github.MODES:
        assert DEFINITION.connector.writes_externally(mode) == (mode not in github.READ_MODES), mode
    assert not mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector, label="githubNode")


@pytest.mark.parametrize("scenario, code", [("auth_failed", "auth_invalid"), ("rate_limited", "rate_limited"),
                                            ("rate_limited_primary", "rate_limited"), ("not_found", "not_found"), ("timeout", "timeout")])
def test_실패_시나리오는_정규화된_코드로_올라온다(scenario, code):
    transport = mock_fixtures.transport_for(DEFINITION.mock, scenario)
    session = DEFINITION.new_session(transport=transport, sleep=lambda _s: None)
    with pytest.raises(ConnectorError) as exc:
        github.run_action(DEFINITION, "pr.get", TOKEN, dict(_MOCK_PARAMS), session=session)
    assert exc.value.code == code


def test_목업_실행_트리거에서_액션까지_저장소와_번호가_이어진다():
    """Mock 탭(ADR-0009): 실제 자격증명 없이 트리거 → 액션이 끝까지 돌고, repo·number 는 트리거 출력에서 채워진다."""
    import mock_service

    graph = {"nodes": [{"id": "t1", "type": "githubTriggerNode", "data": {"events": "pull_request"}},
                       {"id": "g1", "type": "githubNode", "data": {"mode": "pr.comment", "body": "리뷰 완료"}},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "t1", "target": "g1"}, {"id": "e2", "source": "g1", "target": "o1"}]}
    described = mock_service.describe_graph(graph)
    entry = described["entries"][0]
    assert entry["node_type"] == "githubTriggerNode"
    assert [s["id"] for s in entry["samples"]] == ["pull_request_opened", "issues_opened", "release_published", "workflow_run_failed"]
    assert [n["node_id"] for n in described["mockable_nodes"]] == ["g1"]

    result = mock_service.run(graph, db=None, project_id=1, entry_node_id="t1", payload=SAMPLES["pull_request_opened"], scenario="success")
    assert result["success"] is True, result
    assert result["executed_node_count"] == 3
    urls = [r["url"] for r in result["requests"]]
    assert urls == ["https://api.github.com/repos/acme/site/issues/42/comments"], urls
    assert result["requests"][0]["request_headers"]["Authorization"] == mock_runtime.REDACTED_PLACEHOLDER

    failed = mock_service.run(graph, db=None, project_id=1, entry_node_id="t1", payload=SAMPLES["pull_request_opened"], scenario="auth_failed")
    assert failed["success"] is False and failed["failed_request_count"] == 1


# ── 6. 엔드포인트 ─────────────────────────────────────────────────────────

SCENARIO = r'''
import os, sys, json, hmac, hashlib
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
SECRET = "gh-webhook-secret-from-api-center"
owner = models.User(google_id="g-owner", email="owner@example.com", name="Owner", token_balance=1000)
db.add(owner); db.commit()
db.add(models.UserApiKey(user_id=owner.id, provider="webhook_secret", api_key=encrypt_secret(SECRET))); db.commit()
def project(title, **tdata):
    p = models.Project(user_id=owner.id, title=title, graph_data={"is_live": True,
        "nodes": [{"id": "t", "type": "githubTriggerNode", "data": tdata}, {"id": "o", "type": "outputNode", "data": {}}],
        "edges": [{"source": "t", "target": "o"}]})
    db.add(p); db.commit(); return p
strict = project("PR/이슈 열림", events="pull_request, issues", actionFilter="opened, reopened")
branchy = project("main 푸시만", verifyMode="none", events="push, pull_request", branchFilter="main, release/*")
runs = lambda pid: db.query(models.WorkflowRun).filter(models.WorkflowRun.project_id == pid).count()
logs = lambda pid: db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.project_id == pid).count()
samples = {s["id"]: s["payload"] for s in node_definition.get_definition("githubTriggerNode").mock["samples"]}
def body(sample_id):
    return json.dumps(samples[sample_id]["payload"], ensure_ascii=False).encode("utf-8")
sig = lambda raw, secret=SECRET: "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
def post(p, sample_id, event, delivery, *, secret=SECRET, extra=None, raw=None):
    raw = raw if raw is not None else body(sample_id)
    headers = {"Content-Type": "application/json", "X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig(raw, secret)}
    headers.update(extra or {})
    return client.post(f"/webhook/{p.id}", content=raw, headers=headers)

# 정상: 서명이 맞고 필터를 통과한 PR opened → 200 실행, 평탄화된 출력에 저장소·번호가 있다
r = post(strict, "pull_request_opened", "pull_request", "d-1")
assert r.status_code == 200 and r.json()["status"] == "success", r.text
assert '"repo": "acme/site"' in r.json()["result"] and '"number": 42' in r.json()["result"], r.json()["result"][:300]
db.expire_all(); assert runs(strict.id) == 1 and logs(strict.id) == 1

# 기본 검증 모드는 HMAC — 서명이 틀리면 401, 없으면 401. 실행·기록 없음
assert post(strict, "pull_request_opened", "pull_request", "d-2", secret="wrong").status_code == 401
r = client.post(f"/webhook/{strict.id}", content=body("pull_request_opened"), headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request"})
assert r.status_code == 401, r.text
db.expire_all(); assert runs(strict.id) == 1

# 걸러지는 전달은 200 ignored 이고 run 을 만들지 않는다 — ping, 구독하지 않은 이벤트, 필터에 없는 action, 이벤트 헤더 없음
ping = json.dumps({"zen": "Keep it logically awesome.", "hook_id": 1, "hook": {"type": "Repository"}}).encode()
r = post(strict, None, "ping", "d-ping", raw=ping)
assert r.status_code == 200 and r.json()["status"] == "ignored", r.text
r = post(strict, "release_published", "release", "d-3")
assert r.status_code == 200 and r.json()["status"] == "ignored" and r.json()["event"] == "release", r.text
closed = json.dumps({**samples["issues_opened"]["payload"], "action": "closed"}).encode()
r = post(strict, None, "issues", "d-4", raw=closed)
assert r.json()["status"] == "ignored", r.text
r = client.post(f"/webhook/{strict.id}", content=body("issues_opened"), headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig(body("issues_opened")), "X-GitHub-Delivery": "d-5"})
assert r.status_code == 200 and r.json()["status"] == "ignored", r.text
db.expire_all(); assert runs(strict.id) == 1 and logs(strict.id) == 1

# 통과하는 두 번째 이벤트(issues opened) → 실행. 같은 전달 id 재전송 → duplicate(실행 없음)
r = post(strict, "issues_opened", "issues", "d-6")
assert r.status_code == 200 and r.json()["status"] == "success", r.text
again = post(strict, "issues_opened", "issues", "d-6")
assert again.status_code == 200 and again.json()["status"] == "duplicate", again.text
db.expire_all(); assert runs(strict.id) == 2

# verifyMode none + 브랜치 필터: feature 브랜치 push 는 ignored, main push 는 실행, base 가 main 인 PR 은 실행
push = lambda ref: json.dumps({"ref": ref, "after": "a1", "before": "b1", "commits": [], "head_commit": {"id": "a1", "message": "m"},
                               "pusher": {"name": "octocat"}, "repository": {"full_name": "acme/site"}}).encode()
plain = lambda p, raw, event, delivery: client.post(f"/webhook/{p.id}", content=raw, headers={"Content-Type": "application/json", "X-GitHub-Event": event, "X-GitHub-Delivery": delivery})
assert plain(branchy, push("refs/heads/feature/x"), "push", "b-1").json()["status"] == "ignored"
assert plain(branchy, push("refs/heads/main"), "push", "b-2").json()["status"] == "success"
assert plain(branchy, push("refs/heads/release/2.3"), "push", "b-3").json()["status"] == "success"
assert plain(branchy, body("pull_request_opened"), "pull_request", "b-4").json()["status"] == "success"
db.expire_all(); assert runs(branchy.id) == 3

# 웹훅 목록에 GitHub 트리거도 나온다(POST 만)
import datetime as _dt
token = main.jwt.encode({"user_id": owner.id, "email": owner.email, "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1)}, main.JWT_SECRET, algorithm=main.JWT_ALGORITHM)
r = client.get("/api/webhooks", headers={"Authorization": f"Bearer {token}"})
assert r.status_code == 200, r.text
mine = [w for w in r.json() if w["projectId"] == strict.id]
assert mine and mine[0]["nodeType"] == "githubTriggerNode" and mine[0]["methods"] == ["POST"], r.json()
print("GITHUB TRIGGER OK")
'''


def test_github_trigger_endpoint_end_to_end(tmp_path):
    scenario_path = tmp_path / "github_trigger_scenario.py"
    scenario_path.write_text(SCENARIO, encoding="utf-8")
    database_url = f"sqlite:///{tmp_path / 'github.db'}"
    result = subprocess.run(
        [sys.executable, str(scenario_path), database_url, str(BACKEND_DIR)],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout[-3000:]}\n\nstderr:\n{result.stderr[-3000:]}"
    assert "GITHUB TRIGGER OK" in result.stdout
