"""공식 템플릿에 **소개 글과 캔버스 메모**를 붙인다 (1회성 도구).

가져가는 사람이 캔버스만 보고는 알 수 없는 세 가지를 채운다.

  1. **출력 노드가 흐름의 끝에 보이지 않는다.** 배선은 맞다 — 반복(distributorNode) 안에
     출력 노드를 두면 첫 항목만 처리하고 끝나므로, 출력은 `done` 가지로 빠지는 게 정상이다.
     그런데 자동 배치가 그 노드를 `distributorNode` 바로 오른쪽 칸에 놓아서, 화면에서는
     반복 본체가 훨씬 오른쪽까지 이어지고 출력 노드만 가운데 덩그러니 남는다.
     **배선은 그대로 두고 자리만 맨 오른쪽으로 옮긴다.**
  2. **캔버스에 설명이 없다.** 채워야 하는 칸, 반복이 도는 구간, 승인이 필요한 지점을
     `memoNode`(실행되지 않는 주석)로 그 자리 위에 붙인다.
  3. **소개 글이 비어 있다.** 무엇을 하는지, 무엇을 미리 준비해야 하는지, 가져온 뒤 어떤
     칸을 채워야 하는지를 스냅샷에서 그대로 만들어 넣는다.

메모는 그래프 **위쪽 전용 줄**에 놓는다. 노드 사이에 끼워 넣으면 자동 배치가 만든 행 간격
(280px)을 침범해 다른 노드와 겹친다. 위 줄에 두고 x 를 대상 노드와 맞추면 어느 노드에 대한
말인지 바로 읽힌다.

    python -m enrich_curated_templates            # 미리보기
    python -m enrich_curated_templates --apply
"""

from __future__ import annotations

import argparse
import collections
import copy
import math
import re
from typing import Any, Dict, List, Optional, Tuple

MEMO_WIDTH = 320
# 클라이언트의 MEMO_MIN_NODE_HEIGHT 와 같은 값. 이보다 작게 주면 어차피 이 크기로 늘어난다.
MEMO_MIN_HEIGHT = 168
# 메모 상자 안에서 본문이 아닌 것들 — 'MEMO' 머리줄과 서식 도구모음, 안쪽 여백.
MEMO_CHROME = 96
MEMO_LINE_HEIGHT = 23
# 320px 상자에서 14px 한글이 한 줄에 들어가는 대략의 글자 수.
MEMO_CHARS_PER_LINE = 19
MEMO_LANE_GAP = 300          # 그래프 맨 윗줄에서 메모 줄까지
MEMO_STACK_GAP = 250         # 같은 x 에 메모가 겹칠 때 위로 더 올리는 간격
LAYOUT_X_GAP = 470           # community_sanitize 와 같은 값

PLACEHOLDER_RE = re.compile(r"REPLACE_WITH|YOUR_[A-Z_]+|<[A-Z_]{4,}>|PLACEHOLDER")

CREDENTIAL_LABEL = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google_gemini": "Google Gemini",
    "gmail_user_oauth": "Gmail", "google_drive_user_oauth": "Google Drive",
    "google_sheets_user_oauth": "Google Sheets", "google_calendar_user_oauth": "Google 캘린더",
    "naver_user_oauth": "네이버", "naver_search": "네이버 검색 API",
    "slack_bot": "Slack 봇", "discord_bot": "Discord 봇", "telegram_bot": "Telegram 봇",
    "kakao_user_oauth": "카카오", "notion": "Notion", "youtube": "YouTube API",
    "data_go_kr": "공공데이터포털 인증키", "juso": "도로명주소 승인키",
}

TRIGGER_SENTENCE = {
    "startNode": "직접 **실행** 버튼을 눌러 시작합니다.",
    "scheduleNode": "정해 둔 시각마다 자동으로 시작합니다.",
    "webhookNode": "외부에서 웹훅 요청이 들어오면 시작합니다.",
    "gmailTriggerNode": "새 메일이 도착하면 시작합니다.",
    "rssTriggerNode": "구독한 RSS 에 새 글이 올라오면 시작합니다.",
    "naverSearchTriggerNode": "네이버 검색 결과가 바뀌면 시작합니다.",
    "youtubeTriggerNode": "지정한 채널에 새 영상이 올라오면 시작합니다.",
    "telegramTriggerNode": "텔레그램 메시지가 오면 시작합니다.",
    "discordTriggerNode": "디스코드 메시지가 오면 시작합니다.",
}

STEP_SENTENCE = {
    "llmNode": "AI 가 내용을 읽고 처리합니다",
    "promptNode": "AI 에게 줄 지시문을 만듭니다",
    "httpRequestNode": "외부 API 를 호출합니다",
    "jsonParserNode": "받아 온 데이터를 항목별로 분해합니다",
    "distributorNode": "목록을 하나씩 꺼내 아래 단계를 반복합니다",
    "loopNode": "정해진 횟수만큼 반복합니다",
    "conditionNode": "조건에 따라 갈래를 나눕니다",
    "mergeNode": "갈래별 결과를 합칩니다",
    "humanApprovalNode": "사람이 승인해야 다음으로 넘어갑니다",
    "outputNode": "결과를 화면에 보여줍니다",
    "slackNode": "Slack 으로 보냅니다",
    "kakaoNode": "카카오톡으로 보냅니다",
    "emailNode": "메일로 보냅니다",
    "gmailNode": "Gmail 로 보냅니다",
    "discordNode": "Discord 로 보냅니다",
    "telegramNode": "Telegram 으로 보냅니다",
    "databaseNode": "데이터베이스에 읽고 씁니다",
    "hwpxDocumentNode": "한글(HWPX) 문서를 만듭니다",
    "imageGenerationNode": "이미지를 생성합니다",
    "fileModifierNode": "서식 파일의 빈칸을 채웁니다",
    "dynamicInputNode": "실행할 때 값을 입력받습니다",
    "valueNode": "고정값을 넣습니다",
    "googleDriveNode": "Google Drive 에 올립니다",
    "youtubeNode": "YouTube 정보를 가져옵니다",
    "naverSearchNode": "네이버에서 검색합니다",
    "naverCafeNode": "네이버 카페에 글을 올립니다",
    "jusoNode": "도로명주소를 조회합니다",
    "dataGoKrNode": "공공데이터포털에서 자료를 받아옵니다",
    "webCrawlerNode": "웹 페이지 내용을 읽어옵니다",
    "delayNode": "잠시 기다립니다",
}

RISK_SENTENCE = {
    "arbitrary_code": "직접 작성한 코드를 실행합니다 — 가져온 뒤 코드 내용을 꼭 확인하세요.",
    "arbitrary_url": "지정한 주소로 요청을 보냅니다 — 주소를 확인하고 채워 넣으세요.",
    "database": "데이터베이스를 읽고 씁니다 — 연결 정보와 대상 테이블을 확인하세요.",
    "writes_files": "파일을 만듭니다 — 저장 위치를 확인하세요.",
    "payment": "결제와 관련된 동작이 있습니다 — 실행 전에 반드시 확인하세요.",
}


def _memo_height(text: str) -> int:
    """본문이 상자 밖으로 새지 않을 높이. `.memo-node` 는 overflow: visible 이라 넘치면
    글자가 점선 밖으로 흘러나온다 — 잘리지는 않지만 지저분하다."""
    lines = 0
    for paragraph in str(text or "").split("\n"):
        lines += max(1, math.ceil(len(paragraph) / MEMO_CHARS_PER_LINE))
    return max(MEMO_MIN_HEIGHT, MEMO_CHROME + lines * MEMO_LINE_HEIGHT)


def _memo(node_id: str, text: str, x: float, y: float) -> Dict[str, Any]:
    """메모 노드 하나. 크기는 `data.memoSize` 에 넣는다 —

    정화(`sanitize_graph`)가 노드에서 `id/type/position/data` 만 남기고 width·height·style 은
    버린다. 클라이언트의 `ensureMemoNodeDefaults` 가 `data.memoSize` 를 대체 값으로 읽으므로
    거기 넣어야 크기가 살아남는다.
    """
    return {
        "id": node_id,
        "type": "memoNode",
        "position": {"x": float(x), "y": float(y)},
        "data": {
            "text": text,
            "memoContent": {"version": 1, "segments": [{"text": text, "bold": False,
                                                        "highlight": False}]},
            "memoFontSize": 14,
            "memoSize": {"width": MEMO_WIDTH, "height": _memo_height(text)},
        },
    }


def _next_id(used: set, prefix: str = "memo") -> str:
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    used.add(f"{prefix}{index}")
    return f"{prefix}{index}"


def _loop_interior(edges, types) -> set:
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


def plan_memos(nodes, edges, types) -> List[Tuple[str, str]]:
    """(대상 노드 id, 메모 본문) 목록. **정말 알아야 하는 것만** 넣는다 —
    노드마다 메모를 달면 캔버스가 메모로 덮여 오히려 아무것도 안 읽힌다."""
    import community_sanitize

    memos: List[Tuple[str, str]] = []
    by_id = {n["id"]: n for n in nodes}

    # 1) 채워야 실행되는 칸 — 가장 먼저 걸리는 문제다.
    for node in nodes:
        data = node.get("data") or {}
        if node.get("type") == "httpRequestNode" and PLACEHOLDER_RE.search(str(data.get("url") or "")):
            method = str(data.get("method") or "GET").upper()
            memos.append((node["id"],
                          f"⚠ 여기를 먼저 채우세요\n이 노드의 주소가 비어 있습니다. "
                          f"{method} 요청을 보낼 실제 API 주소를 넣어야 실행됩니다."))

    needs = collections.defaultdict(list)
    for entry in community_sanitize.needs_input_for({"nodes": nodes}):
        needs[entry["nodeId"]].append(entry["field"])
    for node_id, fields in needs.items():
        node = by_id.get(node_id)
        if node is None or node_id in {m[0] for m in memos}:
            continue
        memos.append((node_id,
                      f"⚠ 가져온 뒤 채우세요\n비어 있는 칸: {', '.join(sorted(set(fields)))}\n"
                      "자격증명은 API 센터에 등록하면 목록에서 고를 수 있습니다."))

    # 2) 반복 구간 — "출력 노드가 왜 저기 붙어 있나" 의 답이다.
    for node in nodes:
        if node.get("type") != "distributorNode":
            continue
        memos.append((node["id"],
                      "🔁 여기서부터 반복입니다\n앞 단계가 넘긴 목록을 하나씩 꺼내 오른쪽 노드들을 "
                      "항목 수만큼 실행합니다. 결과는 반복이 모두 끝난 뒤 '완료' 선을 타고 "
                      "출력 노드로 갑니다."))

    # 3) 사람이 개입해야 멈추지 않는 지점.
    for node in nodes:
        if node.get("type") == "humanApprovalNode":
            memos.append((node["id"],
                          "✋ 사람이 승인해야 넘어갑니다\n승인 대기함에서 승인하기 전에는 "
                          "다음 단계가 실행되지 않습니다."))
        elif node.get("type") == "dynamicInputNode":
            label = str((node.get("data") or {}).get("inputLabel") or "").strip()
            memos.append((node["id"],
                          "⌨ 실행할 때 값을 넣는 자리입니다"
                          + (f"\n입력 항목: {label}" if label else "")))

    return memos


def build_intro(*, title: str, description: str, nodes, edges, types,
                required_credentials, risk_flags) -> str:
    """소개 글. **그래프에서 읽어낸 사실만** 쓴다 — 지어내면 실제와 어긋난다."""
    import community_sanitize

    incoming = {e.get("target") for e in edges}
    starts = [n for n in nodes if n["id"] not in incoming and n.get("type") != "memoNode"]
    trigger = starts[0].get("type") if starts else None

    lines = ["## 무엇을 하나요", (description or title).strip(), ""]

    lines.append("## 어떻게 동작하나요")
    lines.append(TRIGGER_SENTENCE.get(trigger, "워크플로우가 시작되면 아래 순서로 처리합니다."))
    lines.append("")
    order, seen = [], set()
    for node in nodes:
        kind = node.get("type")
        if kind in ("memoNode", "outputNode") or kind == trigger or kind in seen:
            continue
        sentence = STEP_SENTENCE.get(kind)
        if sentence:
            seen.add(kind)
            order.append(sentence)
    for index, sentence in enumerate(order[:8], start=1):
        lines.append(f"{index}. {sentence}")
    lines.append(f"{min(len(order), 8) + 1}. 결과를 출력 노드에 보여줍니다.")
    lines.append("")

    blanks = community_sanitize.needs_input_for({"nodes": nodes})
    # 비어 있는 칸 중 **자격증명 칸**은 "미리 준비할 것" 이다. required_credentials 만 보면
    # llmNode.apiKey 처럼 참조가 아니라 값으로 지워진 칸이 빠져서, 준비할 게 없다고 적어 놓고
    # 정작 실행하면 키가 없어 실패한다.
    credential_blanks = []
    for entry in blanks:
        node = next((n for n in nodes if n["id"] == entry["nodeId"]), None)
        rule = community_sanitize.rule_for(str((node or {}).get("type")))
        if rule and entry["field"] in rule.credential_fields:
            credential_blanks.append((entry["nodeId"], entry["field"]))

    lines.append("## 미리 준비할 것")
    if required_credentials or credential_blanks:
        lines.append("**API 센터**에서 먼저 등록해 두면 노드에서 골라 쓸 수 있습니다.")
        lines.append("")
        for provider in required_credentials:
            lines.append(f"- {CREDENTIAL_LABEL.get(provider, provider)}")
        for node_id, field in credential_blanks:
            lines.append(f"- `{node_id}` 의 {field} — 사용할 서비스의 키")
    else:
        lines.append("따로 연결해 둘 것이 없습니다.")
    lines.append("")

    placeholders = [n["id"] for n in nodes
                    if n.get("type") == "httpRequestNode"
                    and PLACEHOLDER_RE.search(str((n.get("data") or {}).get("url") or ""))]
    lines.append("## 가져온 뒤 채워야 하는 값")
    if blanks or placeholders:
        lines.append("캔버스에 노란 메모로 표시해 두었습니다.")
        lines.append("")
        for node_id in placeholders:
            lines.append(f"- `{node_id}` — 호출할 API 주소")
        for entry in blanks:
            lines.append(f"- `{entry['nodeId']}` — {entry['field']}")
    else:
        lines.append("바로 실행할 수 있습니다. 값을 바꾸고 싶으면 각 노드를 눌러 수정하세요.")
    lines.append("")

    lines.append("## 알아두세요")
    lines.append("- 가져오면 **내 계정에 사본**이 생깁니다. 자동으로 실행되지 않습니다.")
    if any(n.get("type") == "distributorNode" for n in nodes):
        lines.append("- 목록을 하나씩 처리하는 반복 구간이 있습니다. 항목이 많으면 그만큼 오래 걸립니다.")
    for flag in risk_flags:
        sentence = RISK_SENTENCE.get(flag)
        if sentence:
            lines.append(f"- {sentence}")
    return "\n".join(lines).strip() + "\n"


def rearrange_output(nodes, edges, types) -> List[str]:
    """출력 노드를 흐름의 **맨 오른쪽**으로 옮긴다. 배선은 건드리지 않는다."""
    changed = []
    xs = [float((n.get("position") or {}).get("x", 0)) for n in nodes
          if n.get("type") not in ("outputNode", "memoNode")]
    if not xs:
        return changed
    right = max(xs) + LAYOUT_X_GAP
    # 흐름의 마지막 노드와 같은 줄에 둔다 — 오른쪽 끝으로만 옮기고 y 를 그대로 두면
    # 혼자 아래쪽 줄에 떨어져 여전히 "따로 노는" 것처럼 보인다.
    tail = max((n for n in nodes if n.get("type") not in ("outputNode", "memoNode")),
               key=lambda n: float((n.get("position") or {}).get("x", 0)), default=None)
    row_y = float((tail or {}).get("position", {}).get("y", 80))
    for node in nodes:
        if node.get("type") != "outputNode":
            continue
        position = dict(node.get("position") or {"x": 0, "y": 0})
        # 딱 한 칸 뒤에 붙인다. 예전에는 `>= right` 면 건너뛰어서, 중간 노드가 빠져 **너무 멀리**
        # 떨어진 경우(빈 칸 두 개)를 못 고쳤다.
        if abs(float(position.get("x", 0)) - right) < 1 and float(position.get("y", 0)) == row_y:
            continue
        node["position"] = {"x": right, "y": row_y}
        changed.append(node["id"])
    return changed


def enrich(graph: Dict[str, Any], *, title: str, description: str,
           required_credentials, risk_flags) -> Tuple[Dict[str, Any], str, List[str]]:
    fixed = copy.deepcopy(graph)
    nodes: List[Dict[str, Any]] = fixed.get("nodes") or []
    edges: List[Dict[str, Any]] = fixed.get("edges") or []
    types = {n.get("id"): n.get("type") for n in nodes}
    changes: List[str] = []

    # 이미 붙어 있던 메모는 걷어낸다 — 다시 돌릴 때 같은 말이 겹겹이 쌓이면 안 된다.
    before = len(nodes)
    nodes[:] = [n for n in nodes if n.get("type") != "memoNode"]
    if len(nodes) != before:
        changes.append("이전 메모 정리")

    moved = rearrange_output(nodes, edges, types)
    if moved:
        changes.append(f"출력 노드 자리 이동: {', '.join(moved)}")

    plans = plan_memos(nodes, edges, types)
    if plans:
        by_id = {n["id"]: n for n in nodes}
        top = min(float((n.get("position") or {}).get("y", 80)) for n in nodes)
        used = {n["id"] for n in nodes}
        stacked: Dict[float, int] = collections.defaultdict(int)
        for target_id, text in plans:
            anchor = by_id.get(target_id)
            if anchor is None:
                continue
            x = float((anchor.get("position") or {}).get("x", 80))
            level = stacked[x]
            stacked[x] += 1
            nodes.append(_memo(_next_id(used), text,
                               x=x, y=top - MEMO_LANE_GAP - level * MEMO_STACK_GAP))
        changes.append(f"메모 {len(plans)}개")

    intro = build_intro(title=title, description=description, nodes=nodes, edges=edges,
                        types=types, required_credentials=required_credentials,
                        risk_flags=risk_flags)
    return fixed, intro, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="", help="쉼표로 구분한 slug 목록만 처리")
    parser.add_argument("--version", default="1.2.0")
    args = parser.parse_args()

    import community_templates
    import models
    from database import SessionLocal

    db = SessionLocal()
    rows = db.query(models.Template).filter(
        models.Template.is_curated.is_(True),
        models.Template.status.in_(("published", "in_review")),
    ).order_by(models.Template.id.asc()).all()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        rows = [r for r in rows if r.slug in only]
    if args.limit:
        rows = rows[: args.limit]

    totals = collections.Counter()
    failures = []
    for template in rows:
        version = db.query(models.TemplateVersion).filter_by(id=template.latest_version_id).first()
        share = (db.query(models.WorkflowShare).filter_by(id=version.workflow_share_id).first()
                 if version else None)
        if share is None or (version and str(version.version) == str(args.version)):
            continue
        fixed, intro, changes = enrich(
            share.graph_snapshot or {}, title=template.title,
            description=template.description or "",
            required_credentials=list(share.required_credentials or []),
            risk_flags=list(share.risk_flags or []))
        for change in changes:
            totals[change.split(":")[0].split(" ")[0]] += 1
        totals["소개"] += 1
        if not args.apply:
            continue
        actor = db.query(models.User).filter(models.User.id == template.owner_id).first()
        if actor is None:
            failures.append((template.slug, "고칠 권한이 있는 계정이 없습니다."))
            continue
        try:
            community_templates.revise_curated(
                db, actor, template, graph=fixed, version=args.version,
                changelog="캔버스 메모와 출력 노드 자리 정리", reviewer="소개·메모 일괄 적용")
            community_templates.edit_template(db, actor, template, intro_body=intro)
        except Exception as exc:      # noqa: BLE001
            db.rollback()
            failures.append((template.slug, str(exc)[:160]))

    print(f"대상 {len(rows)}개")
    for kind, count in totals.most_common():
        print(f"   {kind}: {count}건")
    if failures:
        print(f"\n실패 {len(failures)}건:")
        for slug, err in failures[:10]:
            print(f"   {slug}: {err}")
    if not args.apply:
        print("\n(--apply 를 붙이면 반영합니다)")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
