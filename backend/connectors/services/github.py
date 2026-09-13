"""connectors/services/github.py — GitHub Trigger / Action (백로그 34 DEV-1, ADR-0032).

■ 인증은 fine-grained PAT 하나다
  API 센터 provider `github`(kind api_key). `Authorization: Bearer <token>` + `X-GitHub-Api-Version` 으로 부른다. GitHub App(JWT →
  설치 토큰)은 DEV-4 — check run 작성·조직 전체 웹훅이 필요해질 때. 웹훅 **수신**(githubTriggerNode)에는 토큰이 필요 없다 —
  서명 비밀(`webhook_secret`, DEV-0)만 있으면 된다.

■ 트리거는 인바운드 웹훅 위에 있다
  `/webhook/{endpoint_id}` 핸들러가 githubTriggerNode 도 엔드포인트로 인정하고(webhook_verify.INBOUND_NODE_TYPES), HMAC 검증 뒤
  **실행 전에** 이벤트·action·브랜치·라벨 필터를 건다(`trigger_matches`). 걸러진 이벤트는 run 을 만들지 않고 200 으로 답한다 —
  GitHub 은 2xx 만 보고, 필터에 걸린 push 마다 run 행이 쌓이는 것은 사용자에게 잡음이다. 통과한 이벤트는
  `envelope(event, delivery, payload)` 로 감싸 트리거 노드의 입력이 되고, 노드는 `flatten_envelope` 로 평탄화해 내보낸다.
  평탄화 키(event·action·repo·number·title·body·url·branch·labels …)는 이벤트 종류가 달라도 같다 — 뒤 노드가 "PR 이든 이슈든
  제목과 URL" 을 같은 경로로 읽는다. 원본은 `raw` 로 보존한다.

■ 한도
  1차 한도(사용자 토큰 5,000/h)는 **403 + x-ratelimit-remaining: 0** 으로 온다 — 403 을 권한 오류로 읽으면 사용자에게 "권한을 확인하라"
  고 틀린 안내가 간다. 그 재분류는 GitHub 전용이 아니라 `connectors.errors.from_response` 공통 계층에 있다(같은 관례를 쓰는 API 가
  많다). 2차 한도(콘텐츠 생성 80/분·500/h)는 429 + Retry-After 다. 정의의 rateLimit(분당 60)이 평소 간격을 지킨다.

■ 쓰기 요청은 timeout 에 재시도하지 않는다
  ConnectorSession 의 기본 규칙 그대로 — 이슈가 두 개 생기는 것이 한 번 실패보다 나쁘다. 429 만 재시도된다.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "GitHub"
BASE_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
ACCEPT_JSON = "application/vnd.github+json"
ACCEPT_DIFF = "application/vnd.github.diff"
USER_AGENT = "visual-task-automation"

#: 트리거가 받는 이벤트(X-GitHub-Event). 여기 없는 이벤트도 events 필터를 비우면 통과한다 — 목록은 안내·문서용이다.
EVENTS = (
    "push", "pull_request", "pull_request_review", "issues", "issue_comment", "release",
    "workflow_run", "check_run", "deployment_status", "dependabot_alert",
)
READ_MODES = frozenset({"pr.get", "pr.diff", "release.generate_notes", "dependabot.list", "file.get"})
MAX_DIFF_CHARS = 200_000          # PR diff 상한 — LLM 입력으로도 과하고, 실행 로그·run step 에 그대로 남는 값이다
MAX_FILE_CHARS = 200_000
MAX_LABELS = 100
MAX_WORKFLOW_INPUTS = 25          # GitHub 제한(workflow_dispatch inputs)
MAX_PER_PAGE = 100

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)")


# ── 입력 정리 ──────────────────────────────────────────────────────────────

def parse_list(value: Any) -> List[str]:
    """쉼표·줄바꿈 구분 문자열, JSON 배열 문자열, 리스트 → 공백을 걷어낸 문자열 목록(순서 유지, 중복 제거)."""
    if value is None:
        return []
    items: List[Any]
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


def normalize_repo(raw: Any) -> str:
    """`owner/repo` 로 정규화한다. `https://github.com/owner/repo(.git)` 도 받는다. 형식이 어긋나면 호출 전에 멈춘다 —
    경로 조각을 URL 에 그대로 붙이므로 `..` 나 슬래시가 더 있으면 다른 엔드포인트를 부르게 된다."""
    text = str(raw or "").strip()
    m = _GITHUB_URL_RE.match(text)
    if m:
        text = f"{m.group(1)}/{m.group(2)}"
    if text.endswith(".git"):
        text = text[:-4]
    if not text:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail="저장소(repo)가 비어 있다 — 'owner/repo' 를 적거나 GitHub 트리거 뒤에 연결한다")
    if not _REPO_RE.match(text) or ".." in text.split("/"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"저장소는 'owner/repo' 형식이어야 한다: {text!r}")
    return text


def _number(params: Dict[str, Any], label: str = "이슈/PR 번호") -> int:
    raw = str(params.get("number") or "").strip().lstrip("#")
    try:
        value = int(raw)
    except ValueError:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"{label}가 비어 있거나 숫자가 아니다: {raw!r}") from None
    if value <= 0:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}는 1 이상이어야 한다")
    return value


def _require(params: Dict[str, Any], key: str, label: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"{label}({key})가 비어 있다")
    return value


def _url(repo: str, *segments: Any) -> str:
    parts = [quote(str(s), safe="") for s in segments]
    return f"{BASE_URL}/repos/{repo}" + ("/" + "/".join(parts) if parts else "")


def _headers(token: str, accept: str = ACCEPT_JSON) -> Dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }


def _dict(body: Any) -> Dict[str, Any]:
    return body if isinstance(body, dict) else {}


def _login(obj: Any) -> str:
    return str(_dict(obj).get("login") or "")


def _label_names(labels: Any) -> List[str]:
    out: List[str] = []
    for label in labels or []:
        name = label.get("name") if isinstance(label, dict) else label
        if name:
            out.append(str(name))
    return out


def fill_from_upstream(params: Dict[str, Any], upstream_text: Any) -> Dict[str, Any]:
    """비워 둔 repo·number·tagName 을 직전 노드 출력(GitHub 트리거의 평탄화 JSON)에서 채운다.
    트리거 → 액션이 가장 흔한 배선이라, 사용자가 같은 저장소·번호를 두 번 적지 않게 한다. JSON 이 아니면 아무것도 하지 않는다."""
    try:
        upstream = json.loads(upstream_text) if isinstance(upstream_text, str) else upstream_text
    except ValueError:
        return params
    if not isinstance(upstream, dict):
        return params
    for key, source in (("repo", "repo"), ("number", "number"), ("tagName", "tag")):
        if not str(params.get(key) or "").strip() and upstream.get(source) not in (None, ""):
            params[key] = str(upstream[source])
    return params


# ── 액션 ──────────────────────────────────────────────────────────────────

def _issue_summary(body: Any) -> Dict[str, Any]:
    issue = _dict(body)
    return {
        "number": issue.get("number"),
        "title": issue.get("title") or "",
        "state": issue.get("state") or "",
        "url": issue.get("html_url") or "",
        "labels": _label_names(issue.get("labels")),
    }


def _issue_create(session, token, params):
    repo = normalize_repo(params.get("repo"))
    payload: Dict[str, Any] = {"title": _require(params, "title", "이슈 제목")}
    if str(params.get("body") or "").strip():
        payload["body"] = str(params["body"])
    labels = parse_list(params.get("labels"))[:MAX_LABELS]
    if labels:
        payload["labels"] = labels
    assignees = parse_list(params.get("assignees"))
    if assignees:
        payload["assignees"] = assignees
    response = session.post(_url(repo, "issues"), headers=_headers(token), json=payload)
    return {"repo": repo, **_issue_summary(response.body)}


def _comment(session, token, params):
    """이슈와 PR 의 코멘트는 같은 엔드포인트다(PR 도 이슈 번호를 공유한다)."""
    repo = normalize_repo(params.get("repo"))
    number = _number(params)
    body = _require(params, "body", "코멘트 본문")
    response = session.post(_url(repo, "issues", number, "comments"), headers=_headers(token), json={"body": body})
    comment = _dict(response.body)
    return {"repo": repo, "number": number, "id": comment.get("id"), "url": comment.get("html_url") or "",
            "author": _login(comment.get("user"))}


def _issue_labels(session, token, params):
    repo = normalize_repo(params.get("repo"))
    number = _number(params)
    action = str(params.get("labelAction") or "add").strip().lower()
    labels = parse_list(params.get("labels"))[:MAX_LABELS]
    if action not in ("add", "set", "remove"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"labelAction 은 add|set|remove 여야 한다: {action!r}")
    if action != "set" and not labels:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="라벨(labels)이 비어 있다")
    base = _url(repo, "issues", number, "labels")
    if action == "add":
        response = session.post(base, headers=_headers(token), json={"labels": labels})
        return {"repo": repo, "number": number, "action": action, "labels": _label_names(response.body)}
    if action == "set":
        response = session.request("PUT", base, headers=_headers(token), json={"labels": labels})
        return {"repo": repo, "number": number, "action": action, "labels": _label_names(response.body)}
    remaining: List[str] = []
    removed: List[str] = []
    for name in labels:
        try:
            response = session.request("DELETE", f"{base}/{quote(name, safe='')}", headers=_headers(token))
        except ConnectorError as exc:
            if exc.status == 404:      # 붙어 있지 않던 라벨 — 제거하려던 상태가 이미 그 상태다
                continue
            raise
        removed.append(name)
        remaining = _label_names(response.body)
    return {"repo": repo, "number": number, "action": action, "removed": removed, "labels": remaining}


def _issue_update(session, token, params):
    repo = normalize_repo(params.get("repo"))
    number = _number(params)
    payload: Dict[str, Any] = {}
    if str(params.get("title") or "").strip():
        payload["title"] = str(params["title"])
    if str(params.get("body") or "").strip():
        payload["body"] = str(params["body"])
    state = str(params.get("state") or "").strip().lower()
    if state:
        if state not in ("open", "closed"):
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"state 는 open|closed 여야 한다: {state!r}")
        payload["state"] = state
    labels = parse_list(params.get("labels"))
    if labels:
        payload["labels"] = labels[:MAX_LABELS]
    assignees = parse_list(params.get("assignees"))
    if assignees:
        payload["assignees"] = assignees
    if not payload:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="바꿀 내용이 없다 — 제목·본문·상태·라벨·담당자 중 하나는 있어야 한다")
    response = session.request("PATCH", _url(repo, "issues", number), headers=_headers(token), json=payload)
    return {"repo": repo, **_issue_summary(response.body)}


def _pr_summary(body: Any) -> Dict[str, Any]:
    pr = _dict(body)
    return {
        "number": pr.get("number"),
        "title": pr.get("title") or "",
        "body": pr.get("body") or "",
        "state": pr.get("state") or "",
        "draft": bool(pr.get("draft")),
        "merged": bool(pr.get("merged")),
        "mergeable": pr.get("mergeable"),
        "author": _login(pr.get("user")),
        "branch": str(_dict(pr.get("head")).get("ref") or ""),
        "sha": str(_dict(pr.get("head")).get("sha") or ""),
        "baseBranch": str(_dict(pr.get("base")).get("ref") or ""),
        "url": pr.get("html_url") or "",
        "labels": _label_names(pr.get("labels")),
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changedFiles": pr.get("changed_files"),
    }


def _pr_get(session, token, params):
    repo = normalize_repo(params.get("repo"))
    number = _number(params, "PR 번호")
    response = session.get(_url(repo, "pulls", number), headers=_headers(token))
    return {"repo": repo, **_pr_summary(response.body)}


def _pr_diff(session, token, params):
    repo = normalize_repo(params.get("repo"))
    number = _number(params, "PR 번호")
    response = session.get(_url(repo, "pulls", number), headers=_headers(token, ACCEPT_DIFF))
    diff = response.body if isinstance(response.body, str) else json.dumps(response.body, ensure_ascii=False)
    truncated = len(diff) > MAX_DIFF_CHARS
    return {"repo": repo, "number": number, "diff": diff[:MAX_DIFF_CHARS], "truncated": truncated, "chars": len(diff)}


def _pr_merge(session, token, params):
    repo = normalize_repo(params.get("repo"))
    number = _number(params, "PR 번호")
    method = str(params.get("mergeMethod") or "squash").strip().lower()
    if method not in ("merge", "squash", "rebase"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=f"mergeMethod 는 merge|squash|rebase 여야 한다: {method!r}")
    payload: Dict[str, Any] = {"merge_method": method}
    if str(params.get("commitTitle") or "").strip():
        payload["commit_title"] = str(params["commitTitle"])
    # PUT 이지만 머지는 되돌릴 수 없다 — 멱등 메서드라도 재시도로 두 번 요청되지 않게 닫는다(두 번째는 405 로 실패해 로그가 흐려진다).
    response = session.request("PUT", _url(repo, "pulls", number, "merge"), headers=_headers(token), json=payload, idempotent=False)
    body = _dict(response.body)
    return {"repo": repo, "number": number, "merged": bool(body.get("merged")), "sha": body.get("sha") or "",
            "message": body.get("message") or "", "mergeMethod": method}


def _release_create(session, token, params):
    repo = normalize_repo(params.get("repo"))
    payload: Dict[str, Any] = {
        "tag_name": _require(params, "tagName", "태그"),
        "draft": _bool(params.get("draft")),
        "prerelease": _bool(params.get("prerelease")),
    }
    if str(params.get("targetCommitish") or "").strip():
        payload["target_commitish"] = str(params["targetCommitish"]).strip()
    if str(params.get("title") or "").strip():
        payload["name"] = str(params["title"]).strip()
    body = str(params.get("body") or "")
    if body.strip():
        payload["body"] = body
    elif _bool(params.get("generateNotes", True)):
        payload["generate_release_notes"] = True
    response = session.post(_url(repo, "releases"), headers=_headers(token), json=payload)
    release = _dict(response.body)
    return {"repo": repo, "id": release.get("id"), "tag": release.get("tag_name") or payload["tag_name"],
            "name": release.get("name") or "", "url": release.get("html_url") or "",
            "draft": bool(release.get("draft")), "prerelease": bool(release.get("prerelease"))}


def _release_generate_notes(session, token, params):
    repo = normalize_repo(params.get("repo"))
    payload: Dict[str, Any] = {"tag_name": _require(params, "tagName", "태그")}
    if str(params.get("targetCommitish") or "").strip():
        payload["target_commitish"] = str(params["targetCommitish"]).strip()
    if str(params.get("previousTagName") or "").strip():
        payload["previous_tag_name"] = str(params["previousTagName"]).strip()
    # 저장소에 아무것도 쓰지 않는 POST — 멱등하다. timeout 뒤 다시 시도해도 결과가 같다.
    response = session.post(_url(repo, "releases", "generate-notes"), headers=_headers(token), json=payload, idempotent=True)
    notes = _dict(response.body)
    return {"repo": repo, "tag": payload["tag_name"], "name": notes.get("name") or "", "body": notes.get("body") or ""}


def _workflow_inputs(raw: Any) -> Dict[str, Any]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="inputs 는 JSON 객체여야 한다") from None
    if not isinstance(raw, dict):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="inputs 는 JSON 객체여야 한다")
    if len(raw) > MAX_WORKFLOW_INPUTS:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"workflow_dispatch inputs 는 최대 {MAX_WORKFLOW_INPUTS}개다 (현재 {len(raw)})")
    # GitHub 은 문자열 값만 받는다 — 숫자·불리언을 그대로 보내면 422 다.
    return {str(k): (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)) for k, v in raw.items()}


def _workflow_dispatch(session, token, params):
    repo = normalize_repo(params.get("repo"))
    workflow_id = _require(params, "workflowId", "워크플로우 파일명 또는 id")
    ref = str(params.get("ref") or "").strip() or "main"
    payload: Dict[str, Any] = {"ref": ref}
    inputs = _workflow_inputs(params.get("inputs"))
    if inputs:
        payload["inputs"] = inputs
    session.post(_url(repo, "actions", "workflows", workflow_id, "dispatches"), headers=_headers(token), json=payload)
    return {"repo": repo, "workflowId": workflow_id, "ref": ref, "inputs": inputs, "dispatched": True,
            "url": f"https://github.com/{repo}/actions"}


def _alert_summary(alert: Dict[str, Any]) -> Dict[str, Any]:
    advisory = _dict(alert.get("security_advisory"))
    dependency = _dict(alert.get("dependency"))
    package = _dict(dependency.get("package"))
    vulnerability = _dict(alert.get("security_vulnerability"))
    patched = _dict(vulnerability.get("first_patched_version"))
    return {
        "number": alert.get("number"),
        "state": alert.get("state") or "",
        "severity": advisory.get("severity") or "",
        "summary": advisory.get("summary") or "",
        "ghsaId": advisory.get("ghsa_id") or "",
        "package": package.get("name") or "",
        "ecosystem": package.get("ecosystem") or "",
        "manifest": dependency.get("manifest_path") or "",
        "vulnerableRange": vulnerability.get("vulnerable_version_range") or "",
        "patchedVersion": patched.get("identifier") or "",
        "url": alert.get("html_url") or "",
        "createdAt": alert.get("created_at") or "",
    }


def _dependabot_list(session, token, params):
    repo = normalize_repo(params.get("repo"))
    query: Dict[str, Any] = {}
    state = str(params.get("alertState") or "open").strip().lower()
    if state:
        query["state"] = state
    for key, name in (("severity", "severity"), ("ecosystem", "ecosystem")):
        values = parse_list(params.get(key))
        if values:
            query[name] = ",".join(values)
    try:
        per_page = int(params.get("perPage") or 30)
    except (TypeError, ValueError):
        per_page = 30
    query["per_page"] = max(1, min(per_page, MAX_PER_PAGE))
    response = session.get(_url(repo, "dependabot", "alerts"), headers=_headers(token), params=query)
    alerts = [_alert_summary(a) for a in (response.body or []) if isinstance(a, dict)] if isinstance(response.body, list) else []
    return {"repo": repo, "state": state, "count": len(alerts), "alerts": alerts}


def _file_get(session, token, params):
    repo = normalize_repo(params.get("repo"))
    path = _require(params, "path", "파일 경로").strip("/")
    if ".." in path.split("/"):
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="파일 경로에 '..' 은 쓸 수 없다")
    query: Dict[str, Any] = {}
    if str(params.get("ref") or "").strip():
        query["ref"] = str(params["ref"]).strip()
    url = f"{BASE_URL}/repos/{repo}/contents/{quote(path, safe='/')}"
    response = session.get(url, headers=_headers(token), params=query or None)
    body = response.body
    if isinstance(body, list):        # 디렉터리
        return {"repo": repo, "path": path, "type": "dir",
                "entries": [{"name": e.get("name"), "path": e.get("path"), "type": e.get("type"), "size": e.get("size")}
                            for e in body if isinstance(e, dict)]}
    entry = _dict(body)
    content, binary = "", False
    if entry.get("encoding") == "base64" and entry.get("content"):
        try:
            raw_bytes = base64.b64decode("".join(str(entry["content"]).split()))
        except (ValueError, TypeError):
            raw_bytes = b""
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            binary = True
    truncated = len(content) > MAX_FILE_CHARS
    return {"repo": repo, "path": entry.get("path") or path, "type": entry.get("type") or "file", "sha": entry.get("sha") or "",
            "size": entry.get("size"), "url": entry.get("html_url") or "", "content": content[:MAX_FILE_CHARS],
            "truncated": truncated, "binary": binary}


_ACTIONS = {
    "issue.create": _issue_create,
    "issue.comment": _comment,
    "issue.labels": _issue_labels,
    "issue.update": _issue_update,
    "pr.get": _pr_get,
    "pr.diff": _pr_diff,
    "pr.merge": _pr_merge,
    "pr.comment": _comment,
    "release.create": _release_create,
    "release.generate_notes": _release_generate_notes,
    "workflow.dispatch": _workflow_dispatch,
    "dependabot.list": _dependabot_list,
    "file.get": _file_get,
}
MODES = tuple(_ACTIONS)


def run_action(definition, mode: str, token: str, params: Dict[str, Any], *,
               session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """액션 하나를 실행한다. 실패는 전부 정규화된 ConnectorError 로 올라온다."""
    declared = definition.connector.modes if definition is not None and definition.connector else MODES
    if mode not in declared or mode not in _ACTIONS:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"'{mode}' 는 이 노드가 지원하지 않는 동작이다. 가능: {', '.join(declared)}")
    if not str(token or "").strip():
        from ..errors import AUTH_MISSING
        raise ConnectorError(code=AUTH_MISSING, service=SERVICE, context={"provider": "github"})
    if session is None:
        if definition is None:
            raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="githubNode 정의가 없어 세션을 만들 수 없다")
        session = definition.new_session()
    result = _ACTIONS[mode](session, token, dict(params or {}))
    result["mode"] = mode
    result["telemetry"] = session.telemetry()
    return result


def describe_action(mode: str, params: Dict[str, Any]) -> str:
    repo = str(params.get("repo") or "?")
    number = str(params.get("number") or "")
    target = f"{repo}#{number}" if number else repo
    labels = {
        "issue.create": f"{repo} 에 이슈 생성", "issue.comment": f"{target} 에 코멘트", "issue.labels": f"{target} 라벨 변경",
        "issue.update": f"{target} 수정", "pr.get": f"{target} PR 조회", "pr.diff": f"{target} diff 조회", "pr.merge": f"{target} 머지",
        "pr.comment": f"{target} 에 코멘트", "release.create": f"{repo} 릴리스 {params.get('tagName') or ''}".strip(),
        "release.generate_notes": f"{repo} 릴리스 노트 생성", "workflow.dispatch": f"{repo} 워크플로우 {params.get('workflowId') or ''} 실행".strip(),
        "dependabot.list": f"{repo} Dependabot 알림 조회", "file.get": f"{repo} 파일 {params.get('path') or ''} 읽기".strip(),
    }
    return labels.get(mode, f"{repo} {mode}")


# ── 트리거: 평탄화와 필터 ─────────────────────────────────────────────────

def infer_event(payload: Any) -> str:
    """X-GitHub-Event 헤더가 없을 때(목업 샘플·수동 입력) payload 모양으로 이벤트를 추정한다."""
    p = _dict(payload)
    if "pull_request" in p and "review" in p:
        return "pull_request_review"
    if "pull_request" in p:
        return "pull_request"
    if "issue" in p and "comment" in p:
        return "issue_comment"
    if "issue" in p:
        return "issues"
    if "release" in p:
        return "release"
    if "workflow_run" in p:
        return "workflow_run"
    if "check_run" in p:
        return "check_run"
    if "deployment_status" in p:
        return "deployment_status"
    if "alert" in p:
        return "dependabot_alert"
    if "commits" in p or ("ref" in p and "after" in p):
        return "push"
    if "zen" in p and "hook_id" in p:
        return "ping"
    return ""


def _branch_from_ref(ref: Any) -> str:
    text = str(ref or "")
    for prefix in ("refs/heads/", "refs/tags/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def flatten_event(event: str, payload: Any) -> Dict[str, Any]:
    """이벤트 종류가 달라도 같은 키로 읽을 수 있게 평탄화한다. 없는 값은 빈 문자열/빈 배열 — 바인딩 경로가 null 에 걸리지 않게."""
    p = _dict(payload)
    repo = _dict(p.get("repository"))
    out: Dict[str, Any] = {
        "event": event or infer_event(p),
        "action": str(p.get("action") or ""),
        "repo": str(repo.get("full_name") or ""),
        "repoUrl": str(repo.get("html_url") or ""),
        "defaultBranch": str(repo.get("default_branch") or ""),
        "sender": _login(p.get("sender")),
        "number": None,
        "title": "",
        "body": "",
        "url": "",
        "state": "",
        "branch": "",
        "baseBranch": "",
        "sha": "",
        "labels": [],
        "author": "",
        "tag": "",
        "name": "",
        "status": "",
        "conclusion": "",
        "merged": None,
        "draft": None,
        "commits": [],
    }
    kind = out["event"]
    if kind in ("pull_request", "pull_request_review"):
        pr = _dict(p.get("pull_request"))
        out.update({
            "number": pr.get("number") or p.get("number"), "title": pr.get("title") or "", "body": pr.get("body") or "",
            "url": pr.get("html_url") or "", "state": pr.get("state") or "", "branch": str(_dict(pr.get("head")).get("ref") or ""),
            "baseBranch": str(_dict(pr.get("base")).get("ref") or ""), "sha": str(_dict(pr.get("head")).get("sha") or ""),
            "labels": _label_names(pr.get("labels")), "author": _login(pr.get("user")),
            "merged": pr.get("merged") if pr.get("merged") is not None else None, "draft": pr.get("draft"),
        })
        if kind == "pull_request_review":
            review = _dict(p.get("review"))
            out.update({"reviewState": str(review.get("state") or ""), "reviewBody": review.get("body") or "",
                        "reviewer": _login(review.get("user")), "reviewUrl": review.get("html_url") or ""})
    elif kind in ("issues", "issue_comment"):
        issue = _dict(p.get("issue"))
        out.update({
            "number": issue.get("number"), "title": issue.get("title") or "", "body": issue.get("body") or "",
            "url": issue.get("html_url") or "", "state": issue.get("state") or "", "labels": _label_names(issue.get("labels")),
            "author": _login(issue.get("user")), "isPullRequest": "pull_request" in issue,
        })
        if kind == "issue_comment":
            comment = _dict(p.get("comment"))
            out.update({"comment": comment.get("body") or "", "commenter": _login(comment.get("user")),
                        "commentUrl": comment.get("html_url") or ""})
    elif kind == "release":
        release = _dict(p.get("release"))
        out.update({
            "tag": release.get("tag_name") or "", "name": release.get("name") or "", "title": release.get("name") or release.get("tag_name") or "",
            "body": release.get("body") or "", "url": release.get("html_url") or "", "author": _login(release.get("author")),
            "draft": release.get("draft"), "prerelease": release.get("prerelease"), "branch": str(release.get("target_commitish") or ""),
        })
    elif kind == "push":
        commits = [c for c in (p.get("commits") or []) if isinstance(c, dict)]
        head = _dict(p.get("head_commit"))
        out.update({
            "branch": _branch_from_ref(p.get("ref")), "sha": str(p.get("after") or head.get("id") or ""),
            "title": str(head.get("message") or "").split("\n", 1)[0], "body": head.get("message") or "",
            "url": str(head.get("url") or p.get("compare") or ""), "author": str(_dict(p.get("pusher")).get("name") or ""),
            "commits": [{"id": c.get("id") or "", "message": c.get("message") or "", "author": str(_dict(c.get("author")).get("name") or ""),
                         "url": c.get("url") or ""} for c in commits],
            "commitCount": len(commits), "deleted": bool(p.get("deleted")), "forced": bool(p.get("forced")),
        })
        if str(p.get("ref") or "").startswith("refs/tags/"):
            out["tag"] = _branch_from_ref(p.get("ref"))
            out["branch"] = ""
    elif kind == "workflow_run":
        run = _dict(p.get("workflow_run"))
        out.update({
            "name": run.get("name") or "", "title": run.get("name") or "", "status": run.get("status") or "",
            "conclusion": run.get("conclusion") or "", "url": run.get("html_url") or "", "branch": str(run.get("head_branch") or ""),
            "sha": str(run.get("head_sha") or ""), "number": run.get("run_number"), "runId": run.get("id"),
            "triggerEvent": run.get("event") or "",
        })
    elif kind == "check_run":
        run = _dict(p.get("check_run"))
        out.update({
            "name": run.get("name") or "", "title": run.get("name") or "", "status": run.get("status") or "",
            "conclusion": run.get("conclusion") or "", "url": run.get("html_url") or "", "sha": str(run.get("head_sha") or ""),
            "branch": str(_dict(run.get("check_suite")).get("head_branch") or ""),
        })
    elif kind == "deployment_status":
        status = _dict(p.get("deployment_status"))
        deployment = _dict(p.get("deployment"))
        out.update({
            "status": status.get("state") or "", "state": status.get("state") or "", "environment": str(status.get("environment") or deployment.get("environment") or ""),
            "url": status.get("target_url") or status.get("environment_url") or "", "sha": str(deployment.get("sha") or ""),
            "branch": str(deployment.get("ref") or ""), "body": status.get("description") or "", "name": str(deployment.get("task") or ""),
        })
    elif kind == "dependabot_alert":
        alert = _dict(p.get("alert"))
        summary = _alert_summary(alert)
        out.update({
            "number": alert.get("number"), "title": summary["summary"], "state": summary["state"], "url": summary["url"],
            "severity": summary["severity"], "package": summary["package"], "ecosystem": summary["ecosystem"],
            "patchedVersion": summary["patchedVersion"],
        })
    out["raw"] = p
    return out


def envelope(event: str, delivery: str, payload: Any) -> Dict[str, Any]:
    """핸들러 → 트리거 노드 입력. 헤더에만 있던 이벤트 이름·전달 id 를 payload 와 함께 싣는다."""
    return {"event": str(event or ""), "delivery": str(delivery or ""), "payload": payload}


def flatten_envelope(obj: Any) -> Dict[str, Any]:
    """트리거 노드 입력(envelope 또는 원본 payload, 문자열이면 JSON)을 평탄화한다. 무엇이 와도 예외를 내지 않는다 —
    비어 있거나 JSON 이 아니면 event 가 빈 평탄 구조에 raw 로 남긴다."""
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
    if isinstance(data, dict) and "payload" in data and isinstance(data.get("payload"), dict) and ("event" in data or "delivery" in data):
        flat = flatten_event(str(data.get("event") or ""), data["payload"])
        flat["delivery"] = str(data.get("delivery") or "")
        return flat
    flat = flatten_event("", data if isinstance(data, dict) else {})
    flat["delivery"] = ""
    if not isinstance(data, dict):
        flat["raw"] = data
    return flat


def _glob_any(value: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def trigger_matches(data: Optional[Dict[str, Any]], event: str, payload: Any) -> Tuple[bool, str]:
    """노드 설정(events·actionFilter·branchFilter·labelFilter)으로 이 전달을 실행할지 판정한다. (통과 여부, 사유)."""
    data = data or {}
    event = str(event or "").strip()
    p = _dict(payload)
    if not event:
        return False, "X-GitHub-Event 헤더가 없다"
    if event == "ping":
        return False, "ping — 웹훅 등록 확인. 실행하지 않는다"
    wanted = parse_list(data.get("events"))
    if wanted and event not in wanted:
        return False, f"구독하지 않은 이벤트 {event}"
    actions = parse_list(data.get("actionFilter"))
    action = str(p.get("action") or "")
    if actions and action not in actions:
        return False, f"action {action or '(없음)'} 은 필터에 없다"
    branches = parse_list(data.get("branchFilter"))
    if branches:
        flat = flatten_event(event, p)
        candidates = [b for b in (flat.get("branch"), flat.get("baseBranch")) if b]
        # 브랜치 개념이 없는 이벤트(이슈 등)는 거르지 않는다 — branchFilter=main 때문에 이슈 알림이 조용히 사라지는 쪽이 더 나쁘다.
        if candidates and not any(_glob_any(c, branches) for c in candidates):
            return False, f"브랜치 {', '.join(candidates)} 는 필터에 없다"
    labels = parse_list(data.get("labelFilter"))
    if labels:
        present = _label_names((_dict(p.get("pull_request")) or _dict(p.get("issue"))).get("labels"))
        touched = str(_dict(p.get("label")).get("name") or "")
        if touched:
            present = present + [touched]
        if not any(name in labels for name in present):
            return False, "필터 라벨이 붙어 있지 않다"
    return True, ""
