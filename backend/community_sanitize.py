"""community_sanitize.py — 공개 게시용 워크플로우 정화 (ADR-0021, 우선 백로그 23 COMMUNITY-2).

워크플로우를 글에 붙이려면 그 안의 비밀을 지워야 한다. 문제는 **어떻게 지울지 결정하는 방식**이다.

  ❌ 차단 목록 — "botToken 과 smtp_credentials 를 지워라". 다음에 추가되는 노드를 **반드시** 놓친다.
  ✅ 허용 목록 — 모든 노드 타입이 정화 규칙을 **먼저 등록**해야 하고, 등록되지 않은 타입이 그래프에
     있으면 게시 자체를 거부한다.

규칙의 출처는 둘이다.

  1. **노드 정의**(ADR-0005) — `kind == "secret"`, `credential` 블록, `kind == "attachments"` 에서
     자동으로 파생된다. 정의에 secret 필드를 추가하면 정화도 자동으로 따라온다.
  2. **`LEGACY_RULES`** — 아직 정의가 없는 노드 타입(startNode·pythonNode·kakaoNode 등)을 위한 표.
     정의로 이전되면 여기서 지운다.

§4.12 는 "정의가 없는 노드 타입이면 게시를 거부한다"고 썼지만, 조사해 보니 실제 워크플로우가 쓰는
13개 타입 중 8개가 정의 없는 기본 노드였다(`startNode`·`outputNode`·`valueNode`…). 그대로 적용하면
**모든 워크플로우가 거부된다.** 그래서 판정 기준을 "정의가 있는가"에서 **"정화 규칙이 등록됐는가"**로
바꿨다. 안전 성질은 그대로다 — 규칙 없는 노드는 공개될 수 없고, `test_community_qna` 가 **모든 등록
생성기 타입이 규칙을 갖는지** 확인하므로 새 노드를 규칙 없이 추가하면 테스트가 깨진다.
"""

from __future__ import annotations

import copy
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ── 모든 노드에 공통으로 적용되는 문자열 정화 ────────────────────────────
# 자격증명 reference 는 남긴다(그게 요점이다 — 가져간 사람이 자기 것을 채운다). 다만 ADR-0017 의
# `#<id>` 는 **작성자의 자격증명 id** 라서 뗀다. 남기면 작성자 구성이 새고, 가져간 쪽에서는
# 존재하지 않는 id 를 가리켜 조용히 실패한다.
CREDENTIAL_REF_RE = re.compile(r"\{\{API_CENTER:([\w-]+)(?:#\d+)?\}\}")
UPLOAD_PATH_RE = re.compile(r"uploads/[^\s\"'<>]+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\b01[016789][-. ]?\d{3,4}[-. ]?\d{4}\b")
# 그래프 최상위에 남아 있는 배포 비밀들.
GRAPH_SECRET_KEYS = {"discord_bot_token", "telegram_bot_token", "share_token", "webhook_secret"}

REDACTED = ""
NEEDS_INPUT = "__NEEDS_INPUT__"

# React Flow 노드의 보통 크기(약 320x200)와 에디터 dagre 설정을 기준으로 한 간격이다.
# 공개 스냅샷은 measured 크기를 싣지 않으므로, 가져오기 전에 겹치지 않는 안전한 기본 간격을 둔다.
LAYOUT_X_GAP = 470
LAYOUT_Y_GAP = 280
LAYOUT_ORIGIN_X = 80
LAYOUT_ORIGIN_Y = 80


def _valid_position(position: Any) -> bool:
    if not isinstance(position, dict):
        return False
    x, y = position.get("x"), position.get("y")
    return (
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
        and isinstance(y, (int, float)) and not isinstance(y, bool) and math.isfinite(float(y))
    )


def _positions_are_stacked(positions: List[Dict[str, Any]]) -> bool:
    """같은 지점에 저장된 노드를 찾는다.

    몇 px 차이는 직렬화·마이그레이션 과정에서 생길 수 있으므로 사실상 같은 위치로 본다. 반면
    사용자가 의도적으로 촘촘하게 둔 레이아웃은 건드리지 않도록 판정 범위는 작게 잡는다.
    """
    for index, first in enumerate(positions):
        for second in positions[index + 1:]:
            if abs(float(first["x"]) - float(second["x"])) < 16 \
                    and abs(float(first["y"]) - float(second["y"])) < 16:
                return True
    return False


def _topological_positions(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) \
        -> Dict[str, Dict[str, float]]:
    """연결 방향을 유지하는 안정적인 좌→우 레이아웃을 계산한다."""
    node_ids = [str(node.get("id")) for node in nodes]
    node_id_set = set(node_ids)
    order = {node_id: index for index, node_id in enumerate(node_ids)}
    successors: Dict[str, List[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}

    for edge in edges:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source not in node_id_set or target not in node_id_set or source == target:
            continue
        if target not in successors[source]:
            successors[source].append(target)
            indegree[target] += 1

    queue = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
    depth = {node_id: 0 for node_id in queue}
    visited: Set[str] = set()
    while queue:
        source = queue.popleft()
        visited.add(source)
        for target in sorted(successors[source], key=lambda item: order[item]):
            depth[target] = max(depth.get(target, 0), depth[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    # 순환 그래프는 완전한 위상 정렬이 불가능하다. 남은 노드는 마지막 열에 안정적으로 놓아도
    # 겹침은 사라지고, 사용자는 에디터의 자동 정렬로 더 다듬을 수 있다.
    cycle_depth = max(depth.values(), default=-1) + 1
    for node_id in node_ids:
        if node_id not in visited:
            depth[node_id] = cycle_depth

    levels: Dict[int, List[str]] = defaultdict(list)
    for node_id in node_ids:
        levels[depth[node_id]].append(node_id)
    widest_level = max((len(level) for level in levels.values()), default=1)

    positions: Dict[str, Dict[str, float]] = {}
    for level in sorted(levels):
        level_nodes = levels[level]
        y_offset = (widest_level - len(level_nodes)) * LAYOUT_Y_GAP / 2
        for row, node_id in enumerate(level_nodes):
            positions[node_id] = {
                "x": LAYOUT_ORIGIN_X + level * LAYOUT_X_GAP,
                "y": LAYOUT_ORIGIN_Y + y_offset + row * LAYOUT_Y_GAP,
            }
    return positions


def ensure_readable_layout(graph: Dict[str, Any]) -> Dict[str, Any]:
    """공개/가져오기 그래프의 겹친 위치를 복구하되 정상적인 수동 배치는 보존한다.

    과거 공개 스냅샷은 위치가 없던 모든 노드를 ``(0, 0)``으로 저장했다. 새 게시물뿐 아니라 이미
    저장된 템플릿도 설치할 때 복구할 수 있도록 별도의 순수 함수로 두고 항상 깊은 사본을 반환한다.
    """
    result = copy.deepcopy(graph or {})
    nodes = [node for node in (result.get("nodes") or []) if isinstance(node, dict)]
    edges = [edge for edge in (result.get("edges") or []) if isinstance(edge, dict)]
    if not nodes:
        result["nodes"] = nodes
        result["edges"] = edges
        return result

    valid_positions = [node["position"] for node in nodes if _valid_position(node.get("position"))]
    missing_count = len(nodes) - len(valid_positions)
    needs_full_layout = (
        _positions_are_stacked(valid_positions)
        or missing_count >= 2
        or missing_count == len(nodes)
    )

    if needs_full_layout:
        positions = _topological_positions(nodes, edges)
        for node in nodes:
            node["position"] = positions[str(node.get("id"))]
    elif missing_count == 1:
        # 하나만 위치가 없다면 사용자가 만든 나머지 레이아웃은 그대로 두고 오른쪽 빈 공간에 둔다.
        max_x = max(float(position["x"]) for position in valid_positions)
        min_y = min(float(position["y"]) for position in valid_positions)
        for node in nodes:
            if not _valid_position(node.get("position")):
                node["position"] = {"x": max_x + LAYOUT_X_GAP, "y": min_y}

    result["nodes"] = nodes
    result["edges"] = edges
    return result


@dataclass(frozen=True)
class NodeRule:
    """한 노드 타입의 정화 규칙."""

    secret_fields: Tuple[str, ...] = ()          # 값을 지운다
    credential_fields: Tuple[str, ...] = ()      # reference 로 정규화하고 아니면 지운다
    path_fields: Tuple[str, ...] = ()            # 서버 경로 — 지우고 needs_input 표시
    attachment_fields: Tuple[str, ...] = ()      # artifactId 목록 — 비운다
    risk_flags: Tuple[str, ...] = ()             # 가져가기 전에 보여줄 위험 표시


# 정의가 없는 노드 타입의 규칙. **정의로 이전되면 여기서 지운다.**
# 비어 있는 규칙도 "확인했고 비밀이 없다"는 명시적 선언이다 — 빠뜨린 것과 구분된다.
LEGACY_RULES: Dict[str, NodeRule] = {
    # 흐름 제어·표시 — 비밀 없음
    "startNode": NodeRule(),
    "outputNode": NodeRule(),
    # 캔버스 주석. 실행 그래프가 아니지만 **정화는 그대로 받는다** — 메모 본문에 메일 주소나
    # 토큰을 적어 둔 채로 공개될 수 있어서다(_scrub_value 가 남은 문자열을 훑는다).
    "memoNode": NodeRule(),
    "promptNode": NodeRule(),
    "mergeNode": NodeRule(),
    "loopNode": NodeRule(),
    "breakNode": NodeRule(),
    "distributorNode": NodeRule(),
    "multiAgentNode": NodeRule(),
    "tokenizerNode": NodeRule(),
    "dynamicInputNode": NodeRule(),
    "webhookNode": NodeRule(),
    "webCrawlerNode": NodeRule(),
    # 값 노드는 업로드한 파일을 가리킬 수 있다 — 남의 파일이므로 비운다.
    "valueNode": NodeRule(path_fields=("file_path",)),
    # 임의 코드는 아니지만(허용 목록이 import·속성 접근을 막는다, ADR-0019) 가져가기 전에
    # 코드 전문을 보여줘야 한다 — 보안이 아니라 고지 목적이다(§4.12).
    "pythonNode": NodeRule(risk_flags=("arbitrary_code",)),
    # 발송·연동 노드의 채널 자격증명
    "kakaoNode": NodeRule(credential_fields=("accessToken",)),
    "telegramNode": NodeRule(credential_fields=("botToken",)),
    "telegramTriggerNode": NodeRule(credential_fields=("botToken",)),
    "discordTriggerNode": NodeRule(credential_fields=("botToken",)),
    "notionNode": NodeRule(credential_fields=("token",)),
    "tossNode": NodeRule(secret_fields=("secretKey",), risk_flags=("payment",)),
    "paymentLinkNode": NodeRule(risk_flags=("payment",)),
    "googleSheetsNode": NodeRule(),
    "googleCalendarNode": NodeRule(),
}

# 정의에서 파생되지 않는 추가 위험 표시.
DEFINITION_RISK_FLAGS = {
    "databaseNode": ("database",),
    "httpRequestNode": ("arbitrary_url",),
    "fileModifierNode": ("writes_files",),
    "posterGeneratorNode": ("writes_files",),
}


class SanitizeRefused(ValueError):
    """정화 규칙이 없는 노드가 있어 게시할 수 없다. 새 노드는 규칙을 먼저 등록해야 한다."""

    def __init__(self, unknown_types: List[str]):
        self.unknown_types = sorted(set(unknown_types))
        super().__init__(
            "정화 규칙이 등록되지 않은 노드가 있어 공유할 수 없습니다: "
            + ", ".join(self.unknown_types)
        )


def rule_for(node_type: str) -> Optional[NodeRule]:
    """이 노드 타입의 정화 규칙. **None 이면 게시할 수 없다.**"""
    import node_definition

    definition = node_definition.get_definition(node_type)
    if definition is not None:
        return NodeRule(
            secret_fields=tuple(f.name for f in definition.fields if f.kind == "secret"),
            credential_fields=tuple(f.name for f in definition.fields if f.credential),
            attachment_fields=tuple(f.name for f in definition.fields if f.kind == "attachments"),
            risk_flags=DEFINITION_RISK_FLAGS.get(node_type, ()),
        )
    return LEGACY_RULES.get(node_type)


def covered_types() -> Set[str]:
    import node_definition

    return set(node_definition.defined_types()) | set(LEGACY_RULES)


# ── 문자열 정화 ─────────────────────────────────────────────────────────
def scrub_text(value: str) -> str:
    """모든 문자열 값에 적용된다. 서버 경로·이메일·전화번호를 지우고 자격증명 id 를 뗀다."""
    text = CREDENTIAL_REF_RE.sub(lambda m: "{{API_CENTER:%s}}" % m.group(1), str(value))
    text = UPLOAD_PATH_RE.sub("[파일: 가져온 뒤 다시 선택하세요]", text)
    text = EMAIL_RE.sub("[이메일 제거됨]", text)
    text = PHONE_RE.sub("[전화번호 제거됨]", text)
    return text


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    return value


def _referenced_providers(value: Any) -> Set[str]:
    """이 노드가 참조하는 API 센터 provider 들. 중첩된 dict·list 안까지 본다."""
    found: Set[str] = set()
    if isinstance(value, str):
        found.update(CREDENTIAL_REF_RE.findall(value))
    elif isinstance(value, list):
        for item in value:
            found |= _referenced_providers(item)
    elif isinstance(value, dict):
        for item in value.values():
            found |= _referenced_providers(item)
    return found


@dataclass
class SanitizeReport:
    node_types: List[str] = field(default_factory=list)
    required_credentials: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    # 게시 전에 "무엇이 지워지는지" 보여주기 위한 목록 — 사용자가 모른 채 누르게 하지 않는다.
    cleared: List[Dict[str, str]] = field(default_factory=list)
    needs_input: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodeTypes": self.node_types,
            "requiredCredentials": self.required_credentials,
            "riskFlags": self.risk_flags,
            "cleared": self.cleared,
            "needsInput": self.needs_input,
        }


def sanitize_graph(graph: Dict[str, Any]) -> Tuple[Dict[str, Any], SanitizeReport]:
    """게시용 스냅샷을 만든다. **되돌릴 수 없는 단방향 변환이다.**

    규칙이 없는 노드 타입이 하나라도 있으면 `SanitizeRefused` — 새 노드가 정화 규칙 없이 공개되는
    경로를 원천 차단한다.
    """
    source = copy.deepcopy(graph or {})
    nodes = [n for n in (source.get("nodes") or []) if isinstance(n, dict)]
    edges = [e for e in (source.get("edges") or []) if isinstance(e, dict)]

    unknown = [str(n.get("type")) for n in nodes if rule_for(str(n.get("type"))) is None]
    if unknown:
        raise SanitizeRefused(unknown)

    report = SanitizeReport()
    clean_nodes = []
    for node in nodes:
        node_type = str(node.get("type"))
        rule = rule_for(node_type)
        data = dict(node.get("data") or {})
        node_id = str(node.get("id"))

        # 자격증명 필드를 **먼저** 본다. 많은 필드가 secret 이면서 동시에 credential 이라
        # (`llmNode.apiKey`, `discordNode.botToken` …), secret 을 먼저 지우면 reference 까지
        # 함께 사라져 가져간 사람이 "여기에 자기 것을 넣으면 된다"는 자리를 잃는다.
        for name in rule.credential_fields:
            raw = data.get(name)
            if isinstance(raw, str) and CREDENTIAL_REF_RE.fullmatch(raw.strip()):
                # reference 는 남긴다 — 가져간 사람이 자기 자격증명을 채우는 자리다. id 만 뗀다.
                data[name] = CREDENTIAL_REF_RE.sub(lambda m: "{{API_CENTER:%s}}" % m.group(1), raw.strip())
            elif raw:
                report.cleared.append({"nodeId": node_id, "field": name, "reason": "credential"})
                data[name] = REDACTED
                report.needs_input.append({"nodeId": node_id, "field": name})

        for name in rule.secret_fields:
            if name in rule.credential_fields:
                continue   # 위에서 reference 유지 또는 제거를 이미 결정했다
            if data.get(name):
                report.cleared.append({"nodeId": node_id, "field": name, "reason": "secret"})
            data[name] = REDACTED

        for name in rule.path_fields:
            if data.get(name):
                report.cleared.append({"nodeId": node_id, "field": name, "reason": "server_path"})
                report.needs_input.append({"nodeId": node_id, "field": name})
            data[name] = REDACTED

        for name in rule.attachment_fields:
            # 남의 파일을 가리킬 수 없다(ADR-0018). 자동 모드로 되돌린다.
            if (data.get(name) or {}) not in ({}, {"mode": "auto", "artifactIds": []}):
                report.needs_input.append({"nodeId": node_id, "field": name})
            data[name] = {"mode": "auto", "artifactIds": []}

        # 남은 모든 문자열에 공통 정화를 건다 — 규칙이 놓친 자리(프롬프트 본문의 이메일 등)를 덮는다.
        data = {k: _scrub_value(v) for k, v in data.items()}

        # 필요한 자격증명은 **값에서** 모은다. 필드 선언(credential 블록)에만 의존하면 선언이 없는
        # 노드(databaseNode.connectionString 이 그렇다)의 요구사항이 목록에서 빠지고, 가져간 사람은
        # 무엇을 준비해야 하는지 모른 채 실행에서 실패한다.
        for provider in _referenced_providers(data):
            if provider not in report.required_credentials:
                report.required_credentials.append(provider)

        for flag in rule.risk_flags:
            if flag not in report.risk_flags:
                report.risk_flags.append(flag)
        if node_type not in report.node_types:
            report.node_types.append(node_type)

        clean_nodes.append({
            "id": node_id, "type": node_type,
            # 위치가 없는 노드를 모두 (0, 0)에 넣으면 템플릿 설치 시 완전히 포개진다.
            # 아래 ensure_readable_layout()이 연결 구조를 기준으로 안전하게 배치한다.
            "position": node.get("position"),
            "data": data,
        })

    clean_edges = [{
        "id": str(e.get("id") or f"{e.get('source')}-{e.get('target')}"),
        "source": str(e.get("source")), "target": str(e.get("target")),
        **({"sourceHandle": e["sourceHandle"]} if e.get("sourceHandle") else {}),
        **({"targetHandle": e["targetHandle"]} if e.get("targetHandle") else {}),
    } for e in edges]

    report.node_types.sort()
    report.required_credentials.sort()
    report.risk_flags.sort()
    return ensure_readable_layout({"nodes": clean_nodes, "edges": clean_edges}), report


def needs_input_for(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    """**이미 정화된** 스냅샷에서 "가져간 사람이 채워야 하는 칸"을 찾는다.

    게시 시점의 `SanitizeReport.needs_input` 을 저장해 두는 대신 스냅샷 상태에서 파생한다 —
    정화를 다시 돌리면 이미 비어 있어서 아무것도 나오지 않고, 저장해 두면 정화 규칙이 바뀔 때
    옛 기록과 실제 스냅샷이 어긋난다. 비어 있는 자격증명·비밀·경로 칸이 곧 "채워야 하는 칸"이다.
    """
    result: List[Dict[str, str]] = []
    for node in (snapshot or {}).get("nodes") or []:
        rule = rule_for(str(node.get("type")))
        if rule is None:
            continue
        data = node.get("data") or {}
        for name in (*rule.credential_fields, *rule.secret_fields, *rule.path_fields):
            value = data.get(name)
            # reference 가 들어 있으면 채울 필요가 없다 — 자격증명 등록만 하면 된다.
            if isinstance(value, str) and CREDENTIAL_REF_RE.fullmatch(value.strip()):
                continue
            if not value:
                entry = {"nodeId": str(node.get("id")), "field": name}
                if entry not in result:
                    result.append(entry)
    return result


def preview(graph: Dict[str, Any]) -> Dict[str, Any]:
    """게시 전 미리보기. 무엇이 지워지는지 **누르기 전에** 보여준다."""
    try:
        _, report = sanitize_graph(graph)
    except SanitizeRefused as exc:
        return {"ok": False, "unknownNodeTypes": exc.unknown_types, "message": str(exc)}
    return {"ok": True, **report.to_dict()}
