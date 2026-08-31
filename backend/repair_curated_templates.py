"""공식 템플릿 품질 보수 (1회성 도구).

n8n 로직을 옮겨 오면서 남은 세 가지를 고친다.

  1. **지시 프롬프트가 한 줄뿐이다.** 244개 중 221개가 80자 미만이고 중앙값이 31자였다.
     "너는 이메일 분류 전문가다" 처럼 역할만 있고 *무엇을 어떤 형식으로 내놓아야 하는지*가 없다.
     모델이 매번 다른 모양으로 답하므로 뒤 노드가 조용히 깨진다.
  2. **반복 밖에서 출력 노드 없이 끝나는 가지**가 있다. 실행해도 결과가 아무 데도 안 남는다.
  3. **httpRequestNode 주소가 자리표시자**인 채로 라벨도 없다. 캔버스만 봐서는 무엇을 채워야
     하는지 알 수 없다.

고칠 때 **기존 버전을 덮어쓰지 않는다** — `revise_curated` 로 새 버전을 낸다. 가져간 사람의
"v1.0.0 을 설치했다" 는 기록이 거짓이 되면 안 된다(ADR-0023).

    python -m repair_curated_templates --dry-run     # 무엇이 바뀌는지만 본다
    python -m repair_curated_templates --apply
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import re
from typing import Any, Dict, List, Optional, Tuple

MIN_PROMPT_LEN = 80
PLACEHOLDER_RE = re.compile(r"REPLACE_WITH|YOUR_[A-Z_]+|<[A-Z_]{4,}>|PLACEHOLDER")

# 뒤에 오는 노드가 기대하는 모양. 프롬프트의 [출력 형식] 문단이 여기서 나온다.
# 이걸 안 맞추면 모델이 설명문을 붙여 내놓고 파서가 깨진다.
_JSON_CONSUMERS = {"jsonParserNode", "conditionNode", "fileModifierNode", "databaseNode",
                   "hwpxDocumentNode", "templateAnalyzerNode"}
_MESSAGE_CONSUMERS = {"slackNode", "kakaoNode", "emailNode", "gmailNode", "discordNode",
                      "telegramNode", "naverCafeNode"}

_OUTPUT_RULES = {
    "json": (
        "[출력 형식]\n"
        "JSON 객체 하나만 출력한다. 앞뒤에 설명, 인사말, ```json 같은 코드블록 표시를 붙이지 않는다.\n"
        "값을 정할 수 없는 항목은 빈 문자열로 두고 임의로 지어내지 않는다."
    ),
    "message": (
        "[출력 형식]\n"
        "메신저/메일에 그대로 붙일 본문만 출력한다. 제목·머리말·꼬리말을 따로 붙이지 않는다.\n"
        "3~6줄 이내로 쓰고, 핵심을 첫 줄에 둔다. 표나 복잡한 서식은 쓰지 않는다."
    ),
    "text": (
        "[출력 형식]\n"
        "사람이 그대로 읽을 수 있는 본문만 출력한다. \"다음은 결과입니다\" 같은 서두를 붙이지 않는다."
    ),
}

_COMMON_RULES = (
    "[지켜야 할 것]\n"
    "- 입력에 없는 사실을 지어내지 않는다. 근거가 없으면 없다고 적는다.\n"
    "- 판단이 애매하면 가장 보수적인 쪽을 고르고 그 이유를 함께 남긴다.\n"
    "- 한국어로 답한다."
)


def _clean_role(text: str) -> str:
    """한 줄짜리 역할 문장을 다듬는다. 마침표가 없으면 붙인다."""
    role = " ".join(str(text or "").split()).strip()
    if not role:
        return ""
    if not role.endswith((".", "!", "?", "다", "요")):
        role += "."
    elif role.endswith("다"):
        role += "."
    return role


def _output_kind(downstream: List[str]) -> str:
    if any(t in _JSON_CONSUMERS for t in downstream):
        return "json"
    if any(t in _MESSAGE_CONSUMERS for t in downstream):
        return "message"
    return "text"


def build_prompt(*, role: str, title: str, description: str, upstream: List[str],
                 downstream: List[str], has_prompt_node: bool) -> str:
    """짧은 역할 한 줄을 실제로 쓸 수 있는 지시문으로 넓힌다.

    지어내지 않는다 — 재료는 전부 그래프 안에 이미 있는 것들이다. 역할 문장, 템플릿의 제목과
    소개, 앞뒤에 붙은 노드 종류. 그래서 템플릿마다 다른 문장이 나온다.
    """
    role = _clean_role(role) or "너는 이 워크플로우의 처리 단계를 맡은 어시스턴트다."
    goal = " ".join(str(description or title or "").split()).strip()

    task = ["[하는 일]"]
    if goal:
        task.append(f"이 워크플로우의 목적은 다음과 같다 — {goal}")
    task.append("그중 이 단계에서는 위 역할에 해당하는 처리만 수행하고, 다음 단계가 바로 쓸 수 있는"
                " 결과를 만든다.")

    if has_prompt_node:
        source = "앞 단계의 프롬프트 노드가 이번에 처리할 내용을 함께 넘겨준다."
    elif upstream:
        source = f"앞 단계({', '.join(sorted(set(upstream)))})의 출력이 입력으로 들어온다."
    else:
        source = "사용자가 넣은 값이 입력으로 들어온다."
    inputs = f"[입력]\n{source} 입력이 비어 있으면 비어 있다고 답하고 임의의 예시를 만들지 않는다."

    return "\n\n".join([role, "\n".join(task), inputs,
                        _OUTPUT_RULES[_output_kind(downstream)], _COMMON_RULES])


def _neighbours(edges, node_id) -> Tuple[List[str], List[str]]:
    up = [e["source"] for e in edges if e.get("target") == node_id]
    down = [e["target"] for e in edges if e.get("source") == node_id]
    return up, down


def _loop_interior(edges, types) -> set:
    """distributorNode 에서 done 이 아닌 엣지로 닿는 노드들.

    여기에 outputNode 를 넣으면 **첫 항목만 처리하고 끝난다**(meta_agent 지침). 그래서 반복
    안에서 끝나는 가지는 고장이 아니라 정상이다 — 손대면 안 된다.
    """
    out = collections.defaultdict(list)
    for e in edges:
        out[e.get("source")].append(e)
    inside = set()
    for nid, ty in types.items():
        if ty != "distributorNode":
            continue
        stack = [e["target"] for e in out[nid] if (e.get("sourceHandle") or "") != "done"]
        while stack:
            cur = stack.pop()
            if cur in inside:
                continue
            inside.add(cur)
            stack.extend(e["target"] for e in out[cur])
    return inside


def _next_node_id(nodes) -> str:
    used = {n.get("id") for n in nodes}
    index = len(nodes) + 1
    while f"n{index}" in used:
        index += 1
    return f"n{index}"


_URL_HINT = {
    "GET": "조회할 API 주소를 넣어주세요",
    "POST": "보낼 API 주소를 넣어주세요",
    "PUT": "수정할 API 주소를 넣어주세요",
    "PATCH": "수정할 API 주소를 넣어주세요",
    "DELETE": "삭제할 API 주소를 넣어주세요",
}


def repair(graph: Dict[str, Any], *, title: str, description: str) -> Tuple[Dict[str, Any], List[str]]:
    """고친 그래프와 무엇을 고쳤는지 목록을 돌려준다. 원본은 건드리지 않는다."""
    fixed = copy.deepcopy(graph)
    nodes: List[Dict[str, Any]] = fixed.get("nodes") or []
    edges: List[Dict[str, Any]] = fixed.get("edges") or []
    types = {n.get("id"): n.get("type") for n in nodes}
    changes: List[str] = []

    # ── 1. 프롬프트 ──
    prompt_nodes = {n.get("id") for n in nodes if n.get("type") == "promptNode"}
    for node in nodes:
        if node.get("type") != "llmNode":
            continue
        data = node.setdefault("data", {})
        current = str(data.get("systemPrompt") or "")
        if len(current) >= MIN_PROMPT_LEN:
            continue
        up, down = _neighbours(edges, node.get("id"))
        data["systemPrompt"] = build_prompt(
            role=current, title=title, description=description,
            upstream=[types.get(i) for i in up if types.get(i)],
            downstream=[types.get(i) for i in down if types.get(i)],
            has_prompt_node=any(i in prompt_nodes for i in up),
        )
        changes.append(f"프롬프트 보강: {node.get('id')}")

    # ── 2. 반복 **밖**에서 출력 노드 없이 끝나는 가지 ──
    inside = _loop_interior(edges, types)
    has_outgoing = {e.get("source") for e in edges}
    dead = [n.get("id") for n in nodes
            if n.get("id") not in has_outgoing
            and n.get("type") != "outputNode"
            and n.get("id") not in inside]
    for node_id in dead:
        new_id = _next_node_id(nodes)
        anchor = next((n for n in nodes if n.get("id") == node_id), None)
        position = dict((anchor or {}).get("position") or {"x": 0, "y": 0})
        nodes.append({"id": new_id, "type": "outputNode",
                      "position": {"x": position.get("x", 0) + 320, "y": position.get("y", 0)},
                      "data": {}})
        edges.append({"id": f"e-{node_id}-{new_id}", "source": node_id, "target": new_id})
        types[new_id] = "outputNode"
        changes.append(f"출력 노드 연결: {node_id} → {new_id}")

    # ── 3. 자리표시자 주소에 라벨을 붙인다 ──
    # 주소 자체를 지어내지 않는다. 어떤 API 인지 모르는 채로 그럴듯한 주소를 넣으면 조용히
    # 엉뚱한 곳으로 요청이 나간다. 대신 **채워야 한다는 사실**을 캔버스에서 보이게 한다.
    for node in nodes:
        if node.get("type") != "httpRequestNode":
            continue
        data = node.setdefault("data", {})
        if not PLACEHOLDER_RE.search(str(data.get("url") or "")):
            continue
        method = str(data.get("method") or "GET").upper()
        hint = _URL_HINT.get(method, "API 주소를 넣어주세요")
        if not str(data.get("label") or "").strip():
            data["label"] = f"⚠ {hint}"
            changes.append(f"자리표시자 안내: {node.get('id')}")

    return fixed, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 새 버전을 낸다")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N개만 처리(시험용)")
    parser.add_argument("--version", default="1.1.0", help="새 버전 번호")
    args = parser.parse_args()

    import community_templates
    import models
    from database import SessionLocal

    db = SessionLocal()
    # 각 템플릿의 **소유자**로 고친다. 운영자 계정이 있으면 그쪽을 쓰지만, 소유자는 언제나
    # 자기 템플릿을 고칠 수 있으므로 운영 권한이 아직 없는 환경에서도 돌아간다.
    staff = db.query(models.User).filter(models.User.role.in_(("admin", "moderator"))).first()

    rows = db.query(models.Template).filter(
        models.Template.is_curated.is_(True),
        models.Template.status.in_(("published", "in_review")),
    ).order_by(models.Template.id.asc()).all()
    if args.limit:
        rows = rows[: args.limit]

    totals = collections.Counter()
    failures = []
    touched = 0
    for template in rows:
        version = db.query(models.TemplateVersion).filter_by(id=template.latest_version_id).first()
        share = (db.query(models.WorkflowShare).filter_by(id=version.workflow_share_id).first()
                 if version else None)
        if share is None:
            continue
        # 이미 이 버전까지 올린 템플릿은 건너뛴다 — 다시 돌려도 안전해야 한다.
        if version is not None and str(version.version) == str(args.version):
            continue
        fixed, changes = repair(share.graph_snapshot or {}, title=template.title,
                                description=template.description or "")
        if not changes:
            continue
        touched += 1
        for change in changes:
            totals[change.split(":")[0]] += 1
        if not args.apply:
            continue
        actor = staff or db.query(models.User).filter(
            models.User.id == template.owner_id).first()
        if actor is None:
            failures.append((template.slug, "고칠 권한이 있는 계정을 찾을 수 없습니다."))
            continue
        try:
            community_templates.revise_curated(
                db, actor, template, graph=fixed, version=args.version,
                changelog="; ".join(sorted({c.split(":")[0] for c in changes})),
                reviewer="품질 보수 일괄 적용")
        except Exception as exc:      # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
            db.rollback()
            failures.append((template.slug, str(exc)[:160]))

    print(f"대상 {len(rows)}개 중 고칠 것이 있는 템플릿: {touched}개")
    for kind, count in totals.most_common():
        print(f"   {kind}: {count}건")
    if failures:
        print(f"\n실패 {len(failures)}건:")
        for slug, err in failures[:10]:
            print(f"   {slug}: {err}")
    if not args.apply:
        print("\n(--apply 를 붙이면 새 버전으로 반영합니다)")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
