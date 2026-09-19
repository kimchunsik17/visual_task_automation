"""connectors/services/gitlab.py — GitLab Trigger / Action (백로그 34 DEV-3 2차, ADR-0036).

GitHub 연동(github.py, ADR-0032)과 같은 모양으로 만들되 GitLab 이 다른 세 가지를 반영한다.

  1. **자체 호스팅.** 인스턴스 주소(`baseUrl`, 기본 https://gitlab.com)가 노드 필드다. 사용자가 준 주소로 서버가 요청하므로 url_guard 를
     거친다 — 사설망 인스턴스는 SSRF 정책상 막힌다(운영자가 url_guard 허용 목록을 열어야 한다).
  2. **인증은 PRIVATE-TOKEN.** 개인 액세스 토큰(provider `gitlab`, api_key)을 `PRIVATE-TOKEN` 헤더로 싣는다. 프로젝트는 숫자 id 또는
     `group/project` 경로(URL 인코딩)로 가리킨다.
  3. **웹훅 서명은 평문 토큰.** `X-Gitlab-Token` 을 그대로 비교한다 — DEV-0 의 `static_token` 모드가 그것이다(webhook_verify). 이벤트 이름은
     `X-Gitlab-Event`("Merge Request Hook" 등)와 payload `object_kind`(merge_request 등) 둘로 온다 — object_kind 를 정본으로 쓴다.

트리거 평탄화 키는 GitHub 과 같다(event·action·repo·number·title·body·url·branch·baseBranch·sha·labels·author·tag·status·…) —
"PR 이든 MR 이든 뒤 노드는 같은 경로로 읽는다" 가 두 연동을 나란히 두는 이유다. MR 은 number = iid.
"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "GitLab"
DEFAULT_BASE_URL = "https://gitlab.com"
API_PREFIX = "/api/v4"
USER_AGENT = "visual-task-automation"

#: object_kind 값. X-Gitlab-Event 헤더("Push Hook")는 이 이름으로 정규화한다.
EVENTS = ("push", "tag_push", "merge_request", "issue", "note", "pipeline", "job", "release", "deployment", "wiki_page")
EVENT_HEADER_TO_KIND = {
    "push hook": "push", "tag push hook": "tag_push", "merge request hook": "merge_request", "issue hook": "issue",
    "confidential issue hook": "issue", "note hook": "note", "confidential note hook": "note", "pipeline hook": "pipeline",
    "job hook": "job", "release hook": "release", "deployment hook": "deployment", "wiki page hook": "wiki_page",
}
READ_MODES = frozenset({"mr.get", "mr.diff", "pipeline.get", "file.get"})
MAX_DIFF_CHARS = 200_000
MAX_FILE_CHARS = 200_000
MAX_LABELS = 100
MAX_PIPELINE_VARIABLES = 30

_PROJECT_PATH_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*(/[A-Za-z0-9_.][A-Za-z0-9_.-]*)+$")


# ── 입력 정리 ──────────────────────────────────────────────────────────────

def parse_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                loaded = json.loads(text)
                items = list(loaded) if isinstance(loaded, list) else [text]
            except ValueError:
                items = re.split(r"[,\n]", text)
        else:
            items = re.split(r"[,\n]", text)
    out: List[str] = []
    for item in items:
        name = str(item).strip()
        if name and name not in out:
            out.append(name)
    return out


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "yes"}
    return bool(value)


def normalize_base_url(raw: Any) -> str:
    """인스턴스 주소. 비우면 gitlab.com. https 만, 경로는 잘라낸다(https://gitlab.example.com/group/x → https://gitlab.example.com)."""
    text = str(raw or "").strip() or DEFAULT_BASE_URL
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"GitLab 인스턴스 주소가 잘못됐다: {text!r}")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="GitLab 인스턴스 주소는 https 여야 한다")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def guard_base_url(base_url: str) -> str:
    """사용자가 준 인스턴스 주소로 서버가 요청한다 — SSRF 검사. 목업은 건너뛴다."""
    from .. import mock_runtime

    if mock_runtime.current() is not None:
        return base_url
    import url_guard

    try:
        url_guard.check_url(base_url + "/")
    except url_guard.UrlBlocked as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"{exc} — 사설망 GitLab 은 운영자가 url_guard 허용 목록을 열어야 한다") from exc
    return base_url


def project_ref(raw: Any) -> str:
    """프로젝트 id(숫자) 또는 `group/project` 경로 → API 경로 조각(경로는 URL 인코딩)."""
    text = str(raw or "").strip()
    m = re.match(r"^https?://[^/]+/(.+?)(?:\.git)?/?$", text)
    if m:
        text = re.sub(r"/-/.*$", "", m.group(1))
    if not text:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="프로젝트(project)가 비어 있다 — 숫자 id 또는 'group/project'")
    if text.isdigit():
        return text
    if not _PROJECT_PATH_RE.match(text) or ".." in text.split("/"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"프로젝트는 숫자 id 또는 'group/project' 형식이어야 한다: {text!r}")
    return quote(text, safe="")


def _iid(params: Dict[str, Any], label: str = "이슈/MR 번호(iid)") -> int:
    raw = str(params.get("number") or "").strip().lstrip("#!")
    try:
        value = int(raw)
    except ValueError:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}가 비어 있거나 숫자가 아니다: {raw!r}") from None
    if value <= 0:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}는 1 이상이어야 한다")
    return value


def _require(params: Dict[str, Any], key: str, label: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}({key})가 비어 있다")
    return value


def _headers(token: str) -> Dict[str, str]:
    return {"PRIVATE-TOKEN": token, "Accept": "application/json", "User-Agent": USER_AGENT}


def _dict(body: Any) -> Dict[str, Any]:
    return body if isinstance(body, dict) else {}


def _url(base: str, project: str, *segments: Any) -> str:
    parts = [quote(str(s), safe="") for s in segments]
    return f"{base}{API_PREFIX}/projects/{project}" + ("/" + "/".join(parts) if parts else "")


def fill_from_upstream(params: Dict[str, Any], upstream_text: Any) -> Dict[str, Any]:
    """비워 둔 project·number·tagName·baseUrl 을 직전 노드 출력(GitLab 트리거의 평탄화 JSON)에서 채운다."""
    try:
        upstream = json.loads(upstream_text) if isinstance(upstream_text, str) else upstream_text
    except ValueError:
        return params
    if not isinstance(upstream, dict):
        return params
    for key, source in (("project", "repo"), ("number", "number"), ("tagName", "tag"), ("baseUrl", "instance")):
        if not str(params.get(key) or "").strip() and upstream.get(source) not in (None, ""):
            params[key] = str(upstream[source])
    return params


# ── 액션 ──────────────────────────────────────────────────────────────────

def _issue_summary(body: Any) -> Dict[str, Any]:
    issue = _dict(body)
    return {"number": issue.get("iid"), "id": issue.get("id"), "title": issue.get("title") or "", "state": issue.get("state") or "",
            "url": issue.get("web_url") or "", "labels": [str(l) for l in (issue.get("labels") or [])]}


def _issue_create(session, token, base, project, params):
    payload: Dict[str, Any] = {"title": _require(params, "title", "이슈 제목")}
    if str(params.get("body") or "").strip():
        payload["description"] = str(params["body"])
    labels = parse_list(params.get("labels"))[:MAX_LABELS]
    if labels:
        payload["labels"] = ",".join(labels)
    response = session.post(_url(base, project, "issues"), headers=_headers(token), json=payload)
    return _issue_summary(response.body)


def _note(kind: str):
    def _send(session, token, base, project, params):
        iid = _iid(params)
        body = _require(params, "body", "코멘트 본문")
        response = session.post(_url(base, project, kind, iid, "notes"), headers=_headers(token), json={"body": body})
        note = _dict(response.body)
        return {"number": iid, "id": note.get("id"), "author": str(_dict(note.get("author")).get("username") or ""),
                "createdAt": note.get("created_at") or ""}
    return _send


def _issue_update(session, token, base, project, params):
    iid = _iid(params)
    payload: Dict[str, Any] = {}
    if str(params.get("title") or "").strip():
        payload["title"] = str(params["title"])
    if str(params.get("body") or "").strip():
        payload["description"] = str(params["body"])
    state = str(params.get("state") or "").strip().lower()
    if state:
        if state not in ("close", "reopen", "closed", "open"):
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"state 는 close|reopen 이어야 한다: {state!r}")
        payload["state_event"] = "close" if state in ("close", "closed") else "reopen"
    labels = parse_list(params.get("labels"))
    if labels:
        payload["labels"] = ",".join(labels[:MAX_LABELS])
    if not payload:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="바꿀 내용이 없다 — 제목·본문·상태·라벨 중 하나는 있어야 한다")
    response = session.request("PUT", _url(base, project, "issues", iid), headers=_headers(token), json=payload)
    return _issue_summary(response.body)


def _mr_summary(body: Any) -> Dict[str, Any]:
    mr = _dict(body)
    return {
        "number": mr.get("iid"), "id": mr.get("id"), "title": mr.get("title") or "", "body": mr.get("description") or "",
        "state": mr.get("state") or "", "draft": bool(mr.get("draft") or mr.get("work_in_progress")),
        "merged": mr.get("state") == "merged", "mergeStatus": mr.get("detailed_merge_status") or mr.get("merge_status") or "",
        "author": str(_dict(mr.get("author")).get("username") or ""), "branch": mr.get("source_branch") or "",
        "baseBranch": mr.get("target_branch") or "", "sha": mr.get("sha") or "", "url": mr.get("web_url") or "",
        "labels": [str(l) for l in (mr.get("labels") or [])], "changesCount": mr.get("changes_count"),
    }


def _mr_get(session, token, base, project, params):
    iid = _iid(params, "MR 번호(iid)")
    response = session.get(_url(base, project, "merge_requests", iid), headers=_headers(token))
    return _mr_summary(response.body)


def _mr_diff(session, token, base, project, params):
    iid = _iid(params, "MR 번호(iid)")
    response = session.get(_url(base, project, "merge_requests", iid, "changes"), headers=_headers(token))
    body = _dict(response.body)
    parts = []
    for change in body.get("changes") or []:
        if not isinstance(change, dict):
            continue
        header = f"diff --git a/{change.get('old_path')} b/{change.get('new_path')}\n"
        parts.append(header + str(change.get("diff") or ""))
    diff = "\n".join(parts)
    return {"number": iid, "diff": diff[:MAX_DIFF_CHARS], "truncated": len(diff) > MAX_DIFF_CHARS, "chars": len(diff),
            "files": len(parts)}


def _mr_merge(session, token, base, project, params):
    iid = _iid(params, "MR 번호(iid)")
    payload: Dict[str, Any] = {}
    if _bool(params.get("squash")):
        payload["squash"] = True
    if str(params.get("commitTitle") or "").strip():
        payload["merge_commit_message"] = str(params["commitTitle"])
    if _bool(params.get("removeSourceBranch")):
        payload["should_remove_source_branch"] = True
    response = session.request("PUT", _url(base, project, "merge_requests", iid, "merge"), headers=_headers(token), json=payload or None,
                               idempotent=False)
    mr = _dict(response.body)
    return {"number": iid, "merged": mr.get("state") == "merged", "state": mr.get("state") or "", "sha": mr.get("merge_commit_sha") or mr.get("sha") or "",
            "url": mr.get("web_url") or ""}


def _pipeline_variables(raw: Any) -> List[Dict[str, str]]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="variables 는 JSON 객체여야 한다") from None
    if not isinstance(raw, dict):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="variables 는 JSON 객체여야 한다")
    if len(raw) > MAX_PIPELINE_VARIABLES:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"variables 는 최대 {MAX_PIPELINE_VARIABLES}개다")
    return [{"key": str(k), "value": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)} for k, v in raw.items()]


def _pipeline_trigger(session, token, base, project, params):
    ref = str(params.get("ref") or "").strip() or "main"
    payload: Dict[str, Any] = {"ref": ref}
    variables = _pipeline_variables(params.get("variables"))
    if variables:
        payload["variables"] = variables
    response = session.post(_url(base, project, "pipeline"), headers=_headers(token), json=payload)
    pipe = _dict(response.body)
    return {"pipelineId": pipe.get("id"), "ref": ref, "status": pipe.get("status") or "", "url": pipe.get("web_url") or "", "sha": pipe.get("sha") or ""}


def _pipeline_get(session, token, base, project, params):
    pid = str(params.get("pipelineId") or "").strip()
    if not pid.isdigit():
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"파이프라인 id(pipelineId)가 비어 있거나 숫자가 아니다: {pid!r}")
    response = session.get(_url(base, project, "pipelines", pid), headers=_headers(token))
    pipe = _dict(response.body)
    return {"pipelineId": pipe.get("id"), "status": pipe.get("status") or "", "ref": pipe.get("ref") or "", "sha": pipe.get("sha") or "",
            "url": pipe.get("web_url") or "", "duration": pipe.get("duration"), "startedAt": pipe.get("started_at") or "",
            "finishedAt": pipe.get("finished_at") or ""}


def _release_create(session, token, base, project, params):
    payload: Dict[str, Any] = {"tag_name": _require(params, "tagName", "태그")}
    if str(params.get("title") or "").strip():
        payload["name"] = str(params["title"]).strip()
    if str(params.get("body") or "").strip():
        payload["description"] = str(params["body"])
    if str(params.get("ref") or "").strip():
        payload["ref"] = str(params["ref"]).strip()
    response = session.post(_url(base, project, "releases"), headers=_headers(token), json=payload)
    rel = _dict(response.body)
    return {"tag": rel.get("tag_name") or payload["tag_name"], "name": rel.get("name") or "",
            "url": str(_dict(rel.get("_links")).get("self") or ""), "createdAt": rel.get("created_at") or ""}


def _file_get(session, token, base, project, params):
    path = _require(params, "path", "파일 경로").strip("/")
    if ".." in path.split("/"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="파일 경로에 '..' 은 쓸 수 없다")
    ref = str(params.get("ref") or "").strip() or "main"
    url = f"{base}{API_PREFIX}/projects/{project}/repository/files/{quote(path, safe='')}/raw"
    response = session.get(url, headers=_headers(token), params={"ref": ref})
    content = response.body if isinstance(response.body, str) else json.dumps(response.body, ensure_ascii=False)
    return {"path": path, "ref": ref, "content": content[:MAX_FILE_CHARS], "truncated": len(content) > MAX_FILE_CHARS, "size": len(content)}


_ACTIONS = {
    "issue.create": _issue_create,
    "issue.comment": _note("issues"),
    "issue.update": _issue_update,
    "mr.get": _mr_get,
    "mr.diff": _mr_diff,
    "mr.merge": _mr_merge,
    "mr.comment": _note("merge_requests"),
    "pipeline.trigger": _pipeline_trigger,
    "pipeline.get": _pipeline_get,
    "release.create": _release_create,
    "file.get": _file_get,
}
MODES = tuple(_ACTIONS)


def run_action(definition, mode: str, token: str, params: Dict[str, Any], *, session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    declared = definition.connector.modes if definition is not None and definition.connector else MODES
    if mode not in declared or mode not in _ACTIONS:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"'{mode}' 는 이 노드가 지원하지 않는 동작이다. 가능: {', '.join(declared)}")
    if not str(token or "").strip():
        from ..errors import AUTH_MISSING
        raise ConnectorError(code=AUTH_MISSING, service=SERVICE, context={"provider": "gitlab"})
    params = dict(params or {})
    base = guard_base_url(normalize_base_url(params.get("baseUrl")))
    project = project_ref(params.get("project"))
    if session is None:
        if definition is None:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="gitlabNode 정의가 없어 세션을 만들 수 없다")
        session = definition.new_session()
    result = _ACTIONS[mode](session, token, base, project, params)
    result["mode"] = mode
    result["project"] = str(params.get("project") or "")
    result["instance"] = base
    result["telemetry"] = session.telemetry()
    return result


def describe_action(mode: str, params: Dict[str, Any]) -> str:
    project = str(params.get("project") or "?")
    number = str(params.get("number") or "")
    target = f"{project}!{number}" if number else project
    labels = {
        "issue.create": f"{project} 에 이슈 생성", "issue.comment": f"{project}#{number} 에 코멘트", "issue.update": f"{project}#{number} 수정",
        "mr.get": f"{target} MR 조회", "mr.diff": f"{target} diff 조회", "mr.merge": f"{target} 머지", "mr.comment": f"{target} 에 코멘트",
        "pipeline.trigger": f"{project} 파이프라인 실행", "pipeline.get": f"{project} 파이프라인 조회", "release.create": f"{project} 릴리스 {params.get('tagName') or ''}".strip(),
        "file.get": f"{project} 파일 {params.get('path') or ''} 읽기".strip(),
    }
    return labels.get(mode, f"{project} {mode}")


# ── 트리거: 평탄화와 필터 ─────────────────────────────────────────────────

def normalize_event(header: Any, payload: Any) -> str:
    """payload.object_kind 가 정본, 없으면 X-Gitlab-Event 헤더를 object_kind 이름으로."""
    kind = str(_dict(payload).get("object_kind") or "").strip().lower()
    if kind:
        return kind
    text = str(header or "").strip().lower()
    return EVENT_HEADER_TO_KIND.get(text, text.replace(" hook", "").replace(" ", "_"))


def _branch_from_ref(ref: Any) -> str:
    text = str(ref or "")
    for prefix in ("refs/heads/", "refs/tags/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def flatten_event(event: str, payload: Any) -> Dict[str, Any]:
    p = _dict(payload)
    project = _dict(p.get("project"))
    user = _dict(p.get("user"))
    attrs = _dict(p.get("object_attributes"))
    kind = event or normalize_event("", p)
    repo_url = str(project.get("web_url") or "")
    instance = ""
    if repo_url:
        parsed = urlparse(repo_url)
        instance = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    out: Dict[str, Any] = {
        "event": kind, "action": str(attrs.get("action") or ""), "repo": str(project.get("path_with_namespace") or ""),
        "repoUrl": repo_url, "instance": instance, "projectId": project.get("id"), "defaultBranch": str(project.get("default_branch") or ""),
        "sender": str(user.get("username") or p.get("user_username") or ""), "number": None, "title": "", "body": "", "url": "", "state": "",
        "branch": "", "baseBranch": "", "sha": "", "labels": [], "author": "", "tag": "", "name": "", "status": "", "conclusion": "",
        "merged": None, "draft": None, "commits": [],
    }
    if kind == "merge_request":
        out.update({
            "number": attrs.get("iid"), "title": attrs.get("title") or "", "body": attrs.get("description") or "", "url": attrs.get("url") or "",
            "state": attrs.get("state") or "", "branch": str(attrs.get("source_branch") or ""), "baseBranch": str(attrs.get("target_branch") or ""),
            "sha": str(_dict(attrs.get("last_commit")).get("id") or ""), "labels": [str(_dict(l).get("title") or l) for l in (p.get("labels") or attrs.get("labels") or [])],
            "author": str(user.get("username") or ""), "merged": attrs.get("state") == "merged", "draft": bool(attrs.get("draft") or attrs.get("work_in_progress")),
            "mergeStatus": attrs.get("detailed_merge_status") or attrs.get("merge_status") or "",
        })
    elif kind == "issue":
        out.update({
            "number": attrs.get("iid"), "title": attrs.get("title") or "", "body": attrs.get("description") or "", "url": attrs.get("url") or "",
            "state": attrs.get("state") or "", "labels": [str(_dict(l).get("title") or l) for l in (p.get("labels") or attrs.get("labels") or [])],
            "author": str(user.get("username") or ""),
        })
    elif kind == "note":
        target = _dict(p.get("merge_request") or p.get("issue") or p.get("snippet") or p.get("commit"))
        out.update({
            "number": target.get("iid"), "title": target.get("title") or "", "body": attrs.get("note") or "", "url": attrs.get("url") or "",
            "author": str(user.get("username") or ""), "noteableType": str(attrs.get("noteable_type") or ""), "comment": attrs.get("note") or "",
            "branch": str(target.get("source_branch") or ""), "baseBranch": str(target.get("target_branch") or ""),
        })
    elif kind in ("push", "tag_push"):
        commits = [c for c in (p.get("commits") or []) if isinstance(c, dict)]
        head = commits[-1] if commits else {}
        ref = str(p.get("ref") or "")
        out.update({
            "branch": "" if kind == "tag_push" else _branch_from_ref(ref), "tag": _branch_from_ref(ref) if kind == "tag_push" else "",
            "sha": str(p.get("after") or p.get("checkout_sha") or ""), "title": str(head.get("title") or head.get("message") or "").split("\n", 1)[0],
            "body": head.get("message") or "", "url": str(head.get("url") or repo_url), "author": str(p.get("user_username") or user.get("username") or ""),
            "commits": [{"id": c.get("id") or "", "message": c.get("message") or "", "author": str(_dict(c.get("author")).get("name") or ""), "url": c.get("url") or ""}
                        for c in commits],
            "commitCount": int(p.get("total_commits_count") or len(commits)),
        })
    elif kind == "pipeline":
        out.update({
            "number": attrs.get("id"), "pipelineId": attrs.get("id"), "status": attrs.get("status") or "", "conclusion": attrs.get("status") or "",
            "branch": str(attrs.get("ref") or ""), "sha": str(attrs.get("sha") or ""), "url": str(attrs.get("url") or ""), "name": str(attrs.get("source") or ""),
            "tag": str(attrs.get("ref") or "") if attrs.get("tag") else "", "duration": attrs.get("duration"),
            "mergeRequest": (_dict(p.get("merge_request")).get("iid")),
        })
    elif kind == "job":
        out.update({
            "number": p.get("build_id"), "name": str(p.get("build_name") or ""), "status": str(p.get("build_status") or ""), "conclusion": str(p.get("build_status") or ""),
            "branch": str(p.get("ref") or ""), "sha": str(p.get("sha") or ""), "pipelineId": p.get("pipeline_id"), "stage": str(p.get("build_stage") or ""),
        })
    elif kind == "release":
        out.update({
            "tag": str(p.get("tag") or ""), "name": str(p.get("name") or ""), "title": str(p.get("name") or p.get("tag") or ""),
            "body": p.get("description") or "", "url": str(p.get("url") or ""), "action": str(p.get("action") or ""),
        })
    elif kind == "deployment":
        out.update({
            "status": str(p.get("status") or ""), "state": str(p.get("status") or ""), "environment": str(p.get("environment") or ""),
            "url": str(p.get("deployable_url") or ""), "sha": str(p.get("commit_url") or "").rsplit("/", 1)[-1], "branch": str(p.get("ref") or ""),
        })
    out["raw"] = p
    return out


def envelope(event: str, delivery: str, payload: Any) -> Dict[str, Any]:
    return {"event": str(event or ""), "delivery": str(delivery or ""), "payload": payload}


def flatten_envelope(obj: Any) -> Dict[str, Any]:
    data: Any = obj
    if isinstance(obj, (bytes, bytearray)):
        obj = obj.decode("utf-8", "replace")
    if isinstance(obj, str):
        text = obj.strip()
        if not text or text == "<<No input provided>>":
            return {**flatten_event("", {}), "delivery": "", "raw": text}
        try:
            data = json.loads(text)
        except ValueError:
            return {**flatten_event("", {}), "delivery": "", "raw": text}
    if isinstance(data, dict) and isinstance(data.get("payload"), dict) and ("event" in data or "delivery" in data):
        flat = flatten_event(normalize_event(data.get("event"), data["payload"]), data["payload"])
        flat["delivery"] = str(data.get("delivery") or "")
        return flat
    flat = flatten_event("", data if isinstance(data, dict) else {})
    flat["delivery"] = ""
    if not isinstance(data, dict):
        flat["raw"] = data
    return flat


def _glob_any(value: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def trigger_matches(data: Optional[Dict[str, Any]], event_header: str, payload: Any) -> Tuple[bool, str]:
    data = data or {}
    p = _dict(payload)
    event = normalize_event(event_header, p)
    if not event:
        return False, "X-Gitlab-Event 헤더도 object_kind 도 없다"
    wanted = parse_list(data.get("events"))
    if wanted and event not in wanted:
        return False, f"구독하지 않은 이벤트 {event}"
    actions = parse_list(data.get("actionFilter"))
    action = str(_dict(p.get("object_attributes")).get("action") or p.get("action") or "")
    if actions and action not in actions:
        return False, f"action {action or '(없음)'} 은 필터에 없다"
    branches = parse_list(data.get("branchFilter"))
    if branches:
        flat = flatten_event(event, p)
        candidates = [b for b in (flat.get("branch"), flat.get("baseBranch")) if b]
        if candidates and not any(_glob_any(c, branches) for c in candidates):
            return False, f"브랜치 {', '.join(candidates)} 는 필터에 없다"
    labels = parse_list(data.get("labelFilter"))
    if labels:
        present = flatten_event(event, p).get("labels") or []
        if not any(name in labels for name in present):
            return False, "필터 라벨이 붙어 있지 않다"
    return True, ""
