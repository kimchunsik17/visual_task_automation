"""pointing.py — AI 시맨틱 포인팅 계약 (백로그 28번 POINT-0, ROADMAP §3.3).

■ 좌표가 아니라 ID 다

"이 노드를 고쳐줘" 를 모델에게 전달하는 방법은 둘이다. 화면 좌표를 주고 무엇을 가리키는지
추측하게 하거나, **제품이 이미 아는 ID** 를 주거나. 후자를 택했다 — 캔버스를 옮기거나 확대해도,
반응형으로 배치가 바뀌어도 대상이 흔들리지 않는다.

DOM selector·임의 JavaScript·모델이 만들어 낸 CSS selector 는 대상 식별자로 받지 않는다.

■ 모델이 "범위 안에서 고쳤다" 고 말하는 것을 믿지 않는다

scope 는 기본이 `target_only` 다. 그런데 그것을 지키게 하는 방법이 프롬프트에 적어 두는 것뿐이면
지켜지지 않는 날이 온다. 그래서 **서버가 변경 전후를 직접 비교**해서, 허용 범위 밖이 하나라도
바뀌었으면 요청 전체를 거부한다(`validate_scope`). 일부만 적용하지 않는 이유는 절반만 반영된
그래프가 사용자에게 더 나쁘기 때문이다.

■ 무엇을 신뢰하는가

클라이언트가 보낸 것 중 **믿는 것은 id 와 hash 뿐**이다. label 은 표시용이고 권한 판정에 쓰지
않으며, 클라이언트가 함께 보낸 데이터 snapshot 도 쓰지 않는다 — 대상은 서버가 현재 상태에서
다시 찾는다(`resolve`). 그 사이에 대상이 바뀌었으면 조용히 다른 것을 고치지 않고 stale 로 되돌린다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

CONTEXT_VERSION = 1

# ── 대상 종류 ───────────────────────────────────────────────────────────
KIND_WORKFLOW_NODE = "workflow_node"
KIND_WORKFLOW_EDGE = "workflow_edge"
KIND_APP_COMPONENT = "app_component"
KIND_APP_LOGIC_NODE = "app_logic_node"
#: POINT-3 이후. 계약에는 두되 resolver 는 아직 없다.
KIND_EXECUTION_STEP = "execution_step"
KIND_MESSAGE_RANGE = "message_range"
KIND_ARTIFACT_CITATION = "artifact_citation"
KIND_IMAGE_REGION = "image_region"

KINDS = (KIND_WORKFLOW_NODE, KIND_WORKFLOW_EDGE, KIND_APP_COMPONENT, KIND_APP_LOGIC_NODE,
         KIND_EXECUTION_STEP, KIND_MESSAGE_RANGE, KIND_ARTIFACT_CITATION, KIND_IMAGE_REGION)
#: POINT-0~2 에서 실제로 해석할 수 있는 것들.
RESOLVABLE_KINDS = (KIND_WORKFLOW_NODE, KIND_WORKFLOW_EDGE,
                    KIND_APP_COMPONENT, KIND_APP_LOGIC_NODE)

# ── 편집 범위 ───────────────────────────────────────────────────────────
SCOPE_REFERENCE_ONLY = "reference_only"
SCOPE_TARGET_ONLY = "target_only"
SCOPE_TARGET_AND_NEIGHBORS = "target_and_neighbors"
SCOPE_WHOLE_CANVAS = "whole_canvas"
SCOPES = (SCOPE_REFERENCE_ONLY, SCOPE_TARGET_ONLY, SCOPE_TARGET_AND_NEIGHBORS, SCOPE_WHOLE_CANVAS)
DEFAULT_SCOPE = SCOPE_TARGET_ONLY

# ── 한도 ────────────────────────────────────────────────────────────────
MAX_TARGETS = 20            # 직접 지목
MAX_RESOLVED_NEIGHBORS = 50  # 1-hop 으로 딸려 오는 것
NEIGHBOR_HOPS = 1

# ── 오류 code (error_catalog.json 에 등록돼 있다) ───────────────────────
POINTING_TARGET_NOT_FOUND = "POINTING_TARGET_NOT_FOUND"
POINTING_TARGET_STALE = "POINTING_TARGET_STALE"
POINTING_SCOPE_VIOLATION = "POINTING_SCOPE_VIOLATION"
POINTING_CONTEXT_TOO_LARGE = "POINTING_CONTEXT_TOO_LARGE"
POINTING_FORBIDDEN = "POINTING_FORBIDDEN"
POINTING_INVALID_CONTEXT = "POINTING_INVALID_CONTEXT"


class PointingError(ValueError):
    """사용자에게 보여도 되는 수준의 실패. `code` 로 클라이언트가 무엇을 할지 정한다."""

    def __init__(self, code: str, message: str, *, targets: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        # 어떤 대상이 문제인지. **label 이 아니라 id 만** 담는다.
        self.targets = list(targets or [])

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "targets": self.targets}


# ── 해시 ────────────────────────────────────────────────────────────────

def snapshot_hash(value: Any) -> str:
    """대상 하나의 내용 해시. 클라이언트와 서버가 같은 방법으로 계산해야 한다.

    `sort_keys` 로 키 순서를 없애고 공백을 고정한다 — 같은 내용인데 직렬화가 달라서 stale 이
    나오면 사용자는 이유를 알 수 없다.
    """
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ── 요청 파싱 ───────────────────────────────────────────────────────────

def parse_context(raw: Any) -> Optional[Dict[str, Any]]:
    """`pointing_context` 를 검증해 정규화한다. 없으면 None(= 포인팅을 쓰지 않는 요청)."""
    if raw in (None, {}, []):
        return None
    if not isinstance(raw, dict):
        raise PointingError(POINTING_INVALID_CONTEXT, "pointing_context 는 객체여야 합니다.")

    version = raw.get("version", CONTEXT_VERSION)
    if version != CONTEXT_VERSION:
        # 모르는 형식을 "포인팅 없음" 으로 강등하지 않는다 — 사용자가 지목했는데 전체 캔버스가
        # 편집 대상이 되는 것이 가장 나쁘다.
        raise PointingError(POINTING_INVALID_CONTEXT,
                            f"모르는 pointing_context 형식입니다: v{version}")

    scope = raw.get("scope") or DEFAULT_SCOPE
    if scope not in SCOPES:
        raise PointingError(POINTING_INVALID_CONTEXT, f"모르는 편집 범위입니다: {scope}")

    raw_targets = raw.get("targets") or []
    if not isinstance(raw_targets, list):
        raise PointingError(POINTING_INVALID_CONTEXT, "targets 는 배열이어야 합니다.")
    if not raw_targets:
        raise PointingError(POINTING_INVALID_CONTEXT, "지목한 대상이 없습니다.")
    if len(raw_targets) > MAX_TARGETS:
        raise PointingError(
            POINTING_CONTEXT_TOO_LARGE,
            f"한 번에 지목할 수 있는 대상은 {MAX_TARGETS}개입니다(지금 {len(raw_targets)}개). "
            "범위를 좁혀주세요.")

    targets, seen = [], set()
    for item in raw_targets:
        if not isinstance(item, dict):
            raise PointingError(POINTING_INVALID_CONTEXT, "target 은 객체여야 합니다.")
        kind = str(item.get("kind") or "").strip()
        target_id = str(item.get("id") or "").strip()
        if kind not in KINDS:
            raise PointingError(POINTING_INVALID_CONTEXT, f"모르는 대상 종류입니다: {kind or '(없음)'}")
        if not target_id:
            raise PointingError(POINTING_INVALID_CONTEXT, "대상 id 가 비어 있습니다.")
        if kind not in RESOLVABLE_KINDS:
            raise PointingError(POINTING_INVALID_CONTEXT,
                                f"'{kind}' 지목은 아직 지원하지 않습니다.")
        key = (kind, target_id)
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            "kind": kind,
            "id": target_id,
            # label 은 **표시용이다.** 권한 판정이나 대상 해석에 쓰지 않는다.
            "label": str(item.get("label") or "")[:120] or None,
            "revision": item.get("revision"),
            "clientStateVersion": item.get("clientStateVersion"),
            "snapshotHash": str(item.get("snapshotHash") or "").strip() or None,
            "path": str(item.get("path") or "").strip() or None,
        })

    return {"version": CONTEXT_VERSION, "scope": scope, "targets": targets}


# ── 대상 해석 ───────────────────────────────────────────────────────────

def _index_workflow(graph: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    nodes = {str(n.get("id")): n for n in (graph or {}).get("nodes") or [] if n.get("id")}
    edges = {str(e.get("id")): e for e in (graph or {}).get("edges") or [] if e.get("id")}
    return nodes, edges


def _walk_components(components: Iterable[Any], out: Dict[str, Any],
                     parent: Optional[str] = None) -> None:
    """컴포넌트는 `children` 으로 중첩된다 — 평평한 목록이 아니다."""
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        comp_id = str(comp.get("id") or "")
        if comp_id:
            out[comp_id] = {"component": comp, "parent": parent}
        _walk_components(comp.get("children") or [], out, comp_id or parent)


def _index_app(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    ui = (state or {}).get("ui") or {}
    logic = (state or {}).get("logic") or {}
    components: Dict[str, Any] = {}
    _walk_components(ui.get("components") or [], components)
    logic_nodes = {str(n.get("id")): n for n in (logic.get("nodes") or []) if n.get("id")}
    logic_edges = {str(e.get("id")): e for e in (logic.get("edges") or []) if e.get("id")}
    return components, logic_nodes, logic_edges


def resolve(targets: List[Dict[str, Any]], *, workflow_graph: Optional[Dict[str, Any]] = None,
            app_state: Optional[Dict[str, Any]] = None,
            revision: Optional[int] = None) -> List[Dict[str, Any]]:
    """지목한 대상을 **현재 상태에서 다시 찾는다.** 클라이언트가 보낸 내용은 쓰지 않는다.

    찾지 못하면 `POINTING_TARGET_NOT_FOUND`, 내용이 달라졌으면 `POINTING_TARGET_STALE`.
    둘을 구분하는 이유는 사용자가 할 일이 다르기 때문이다 — 전자는 지목을 지워야 하고
    후자는 다시 첨부해야 한다.
    """
    nodes, edges = _index_workflow(workflow_graph or {})
    components, logic_nodes, _logic_edges = _index_app(app_state or {})

    resolved, missing, stale = [], [], []
    for target in targets:
        kind, target_id = target["kind"], target["id"]
        if kind == KIND_WORKFLOW_NODE:
            found = nodes.get(target_id)
        elif kind == KIND_WORKFLOW_EDGE:
            found = edges.get(target_id)
        elif kind == KIND_APP_COMPONENT:
            entry = components.get(target_id)
            found = entry["component"] if entry else None
        elif kind == KIND_APP_LOGIC_NODE:
            found = logic_nodes.get(target_id)
        else:
            found = None

        if found is None:
            missing.append(target_id)
            continue

        current_hash = snapshot_hash(found)
        expected = target.get("snapshotHash")
        if expected and expected != current_hash:
            stale.append(target_id)
            continue
        if (target.get("revision") is not None and revision is not None
                and int(target["revision"]) != int(revision)):
            stale.append(target_id)
            continue

        resolved.append({**target, "snapshotHash": current_hash, "resolved": found})

    if missing:
        raise PointingError(
            POINTING_TARGET_NOT_FOUND,
            "지목한 대상을 찾을 수 없습니다. 삭제됐을 수 있으니 다시 선택해주세요.",
            targets=missing)
    if stale:
        raise PointingError(
            POINTING_TARGET_STALE,
            "지목한 뒤 대상이 바뀌었습니다. 다시 첨부해주세요.",
            targets=stale)
    return resolved


# ── 편집 허용 범위 ──────────────────────────────────────────────────────

def _workflow_neighbors(node_ids: Set[str], graph: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """1-hop. 방향을 가리지 않는다 — "이 노드와 연결된 것" 이 사용자의 뜻이다."""
    nodes, edges = _index_workflow(graph)
    neighbor_nodes: Set[str] = set()
    touching_edges: Set[str] = set()
    for edge_id, edge in edges.items():
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in node_ids or target in node_ids:
            touching_edges.add(edge_id)
            if source in nodes:
                neighbor_nodes.add(source)
            if target in nodes:
                neighbor_nodes.add(target)
    return neighbor_nodes - node_ids, touching_edges


def _component_family(comp_ids: Set[str], state: Dict[str, Any]) -> Set[str]:
    """부모와 직계 자식. 컴포넌트는 트리라 "연결" 이 곧 계층이다."""
    components, _ln, _le = _index_app(state)
    family: Set[str] = set()
    for comp_id in comp_ids:
        entry = components.get(comp_id)
        if not entry:
            continue
        if entry["parent"]:
            family.add(entry["parent"])
        for child in entry["component"].get("children") or []:
            child_id = str((child or {}).get("id") or "")
            if child_id:
                family.add(child_id)
    return family - comp_ids


def editable_ids(context: Dict[str, Any], *, workflow_graph: Optional[Dict[str, Any]] = None,
                 app_state: Optional[Dict[str, Any]] = None) -> Dict[str, Set[str]]:
    """이 요청이 바꿔도 되는 id 집합. **결정론적이어야** 한다 — 같은 입력에 같은 결과.

    `whole_canvas` 는 빈 집합이 아니라 `None` 을 돌려준다. 빈 집합("아무것도 못 바꾼다")과
    구분되지 않으면 위험한 쪽으로 잘못 읽힌다.
    """
    scope = context["scope"]
    direct_nodes = {t["id"] for t in context["targets"] if t["kind"] == KIND_WORKFLOW_NODE}
    direct_edges = {t["id"] for t in context["targets"] if t["kind"] == KIND_WORKFLOW_EDGE}
    direct_comps = {t["id"] for t in context["targets"] if t["kind"] == KIND_APP_COMPONENT}
    direct_logic = {t["id"] for t in context["targets"] if t["kind"] == KIND_APP_LOGIC_NODE}

    if scope == SCOPE_WHOLE_CANVAS:
        return {"nodes": None, "edges": None, "components": None, "logicNodes": None}
    if scope == SCOPE_REFERENCE_ONLY:
        return {"nodes": set(), "edges": set(), "components": set(), "logicNodes": set()}

    nodes, edges = set(direct_nodes), set(direct_edges)
    comps, logic = set(direct_comps), set(direct_logic)

    if scope == SCOPE_TARGET_AND_NEIGHBORS:
        if workflow_graph and direct_nodes:
            neighbor_nodes, touching_edges = _workflow_neighbors(direct_nodes, workflow_graph)
            nodes |= neighbor_nodes
            edges |= touching_edges
        if app_state and direct_comps:
            comps |= _component_family(direct_comps, app_state)

    total = len(nodes) + len(edges) + len(comps) + len(logic)
    if total > MAX_TARGETS + MAX_RESOLVED_NEIGHBORS:
        raise PointingError(
            POINTING_CONTEXT_TOO_LARGE,
            f"연결된 항목까지 하면 {total}개가 되어 한 번에 다루기 어렵습니다. "
            "선택을 줄이거나 '선택 항목만' 으로 바꿔주세요.")
    return {"nodes": nodes, "edges": edges, "components": comps, "logicNodes": logic}


# ── 변경 후 검증 ────────────────────────────────────────────────────────

# 무엇을 "바뀌었다" 로 볼 것인가 — **워크플로우가 하는 일**만 본다.
#
# 자리·색·클래스는 편집 범위가 지키려는 대상이 아니다. 게다가 `auto_layout` 이 노드를
# `{id,type,position,data}` 로 재구성하고 엣지를 `FlowEdge.model_dump()` 로 만들기 때문에,
# 통짜로 비교하면 `className`·`style` 이 사라지면서 **AI 가 손대지 않은 항목까지 전부**
# 바뀐 것으로 잡힌다(2026-08-30 실사용에서 6개가 걸렸다).
_SEMANTIC_KEYS = {
    "nodes": ("type", "data"),
    "edges": ("source", "target", "sourceHandle", "targetHandle"),
    "components": ("type", "props"),
    "logicNodes": ("type", "data"),
}


def _semantic(bucket: str, value: Any) -> Any:
    """비교에 쓸 부분만 남긴다. 없는 키는 None 으로 채워 "키가 사라진 것" 과 구분한다."""
    if not isinstance(value, dict):
        return value
    keys = _SEMANTIC_KEYS.get(bucket)
    if not keys:
        return value
    picked = {k: value.get(k) for k in keys}
    if bucket == "components":
        # 자식은 각자 따로 추적하므로 **id 목록**만 본다 — 통째로 넣으면 이중으로 센다.
        picked["childIds"] = [str((c or {}).get("id") or "")
                              for c in (value.get("children") or []) if isinstance(c, dict)]
    return picked


def _changed_ids(before: Dict[str, Any], after: Dict[str, Any], bucket: str = "") -> Set[str]:
    """추가·삭제·수정된 id 전부. 한쪽에만 있는 것도 변경이다."""
    changed = set(before) ^ set(after)
    for key in set(before) & set(after):
        if (snapshot_hash(_semantic(bucket, before[key]))
                != snapshot_hash(_semantic(bucket, after[key]))):
            changed.add(key)
    return changed


def validate_scope(context: Dict[str, Any], *, before: Dict[str, Any], after: Dict[str, Any],
                   allowed: Dict[str, Set[str]], kind: str = "workflow") -> None:
    """모델이 낸 결과가 허용 범위 안에 있는지 **직접 비교해서** 확인한다.

    범위 밖이 하나라도 바뀌었으면 요청 전체를 거부한다 — 절반만 반영된 그래프는 사용자에게
    더 나쁘다.
    """
    if kind == "workflow":
        before_nodes, before_edges = _index_workflow(before)
        after_nodes, after_edges = _index_workflow(after)
        buckets = [("nodes", before_nodes, after_nodes), ("edges", before_edges, after_edges)]
    else:
        b_comps, b_logic, _ = _index_app(before)
        a_comps, a_logic, _ = _index_app(after)
        buckets = [("components", {k: v["component"] for k, v in b_comps.items()},
                    {k: v["component"] for k, v in a_comps.items()}),
                   ("logicNodes", b_logic, a_logic)]

    violations: List[str] = []
    for bucket, old, new in buckets:
        permitted = allowed.get(bucket)
        if permitted is None:      # whole_canvas — 전부 허용
            continue
        outside = _changed_ids(old, new, bucket) - permitted
        violations.extend(sorted(outside))

    if violations:
        raise PointingError(
            POINTING_SCOPE_VIOLATION,
            f"지목하지 않은 항목 {len(violations)}개가 함께 바뀌어 적용하지 않았습니다. "
            "편집 범위를 넓히려면 '연결 항목 포함' 이나 '전체 캔버스' 를 골라주세요.",
            targets=violations[:20])


# ── 프롬프트에 넣을 것 ──────────────────────────────────────────────────

def redact(value: Any) -> Any:
    """secret·자격증명·서버 경로를 지운 사본.

    모델에게 보내기 전에 거른다. `community_sanitize` 가 커뮤니티 공개용 정화를 하는 것과
    목적이 다르다 — 저쪽은 "남에게 보여도 되는가", 이쪽은 "모델 프롬프트에 넣어도 되는가" 다.
    그래서 규칙을 공유하지 않고 필드 이름으로 판단한다.
    """
    if isinstance(value, dict):
        return {k: _redact_field(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


_SECRET_HINTS = ("token", "secret", "apikey", "api_key", "password", "credential",
                 "authorization", "clientsecret", "privatekey")
_PATH_HINTS = ("path", "filepath", "file_path", "output_path", "template_path")


def _redact_field(name: str, value: Any) -> Any:
    lowered = str(name).lower().replace("-", "").replace("_", "")
    if any(hint.replace("_", "") in lowered for hint in _SECRET_HINTS):
        return "[비밀 값 생략]" if value not in (None, "") else value
    if any(hint.replace("_", "") in lowered for hint in _PATH_HINTS) and isinstance(value, str):
        # 서버 경로를 모델에게 보여줄 이유가 없다. 파일 이름까지만 남긴다.
        return value.rsplit("/", 1)[-1] if "/" in value else value
    return redact(value)


def build_prompt_context(resolved: List[Dict[str, Any]], allowed: Dict[str, Set[str]], *,
                         workflow_graph: Optional[Dict[str, Any]] = None,
                         app_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """모델에게 줄 것. **전체 상태가 아니라 지목한 것과 허용된 이웃만** 넣는다.

    전체 상태는 서버가 검증 정본으로 계속 들고 있고, 프롬프트는 예산이라는 것이 이 설계의 요지다.
    """
    nodes, edges = _index_workflow(workflow_graph or {})
    components, logic_nodes, _le = _index_app(app_state or {})

    def pick(bucket: str, source: Dict[str, Any], unwrap=lambda x: x) -> List[Dict[str, Any]]:
        permitted = allowed.get(bucket)
        if permitted is None:
            return []
        return [{"id": key, "value": redact(unwrap(source[key]))}
                for key in sorted(permitted) if key in source]

    return {
        "version": CONTEXT_VERSION,
        "targets": [{"kind": t["kind"], "id": t["id"], "label": t.get("label")}
                    for t in resolved],
        "editable": {
            "nodes": pick("nodes", nodes),
            "edges": pick("edges", edges),
            "components": pick("components", components, unwrap=lambda x: x["component"]),
            "logicNodes": pick("logicNodes", logic_nodes),
        },
    }


# ── 관측 ────────────────────────────────────────────────────────────────

def telemetry(context: Optional[Dict[str, Any]], *, outcome: str,
              violations: int = 0, prompt_tokens: Optional[int] = None) -> Dict[str, Any]:
    """무엇을 남기는가 — **label·본문·문서 내용은 남기지 않는다.** 종류와 수만 센다.

    이 구분이 중요한 이유: 포인팅 telemetry 는 사용자가 지목한 대상의 **이름**을 담기 쉬운데,
    그것이 곧 워크플로우 내용이다.
    """
    if context is None:
        return {"pointing": False}
    kinds: Dict[str, int] = {}
    for target in context["targets"]:
        kinds[target["kind"]] = kinds.get(target["kind"], 0) + 1
    return {
        "pointing": True,
        "scope": context["scope"],
        "targetCount": len(context["targets"]),
        "kinds": kinds,
        "outcome": outcome,          # applied | stale | not_found | scope_violation | too_large
        "scopeViolations": violations,
        "promptTokens": prompt_tokens,
    }


# ── 권한 ────────────────────────────────────────────────────────────────

def check_permission(db, user, project, context: Optional[Dict[str, Any]]) -> None:
    """조회 권한과 편집 권한을 **따로** 본다.

    `reference_only` 는 "답변 근거로만 쓴다" 이므로 조회 권한이면 충분하다. 나머지 scope 는
    실제로 그래프를 바꾸므로 편집 권한이 있어야 한다 — 둘을 하나로 묶으면 viewer 가
    "이 노드 고쳐줘" 로 편집할 수 있게 된다.
    """
    import project_access

    if context is None:
        return
    needed = project_access.VIEW if context["scope"] == SCOPE_REFERENCE_ONLY else project_access.EDIT
    if not project_access.can(db, user, project, needed):
        raise PointingError(
            POINTING_FORBIDDEN,
            "이 워크플로우를 수정할 권한이 없습니다."
            if needed == project_access.EDIT else "이 워크플로우를 볼 권한이 없습니다.")


# ── 모델에게 주는 지시 ──────────────────────────────────────────────────

def instruction_block(context: Dict[str, Any], allowed: Dict[str, Set[str]],
                      resolved: List[Dict[str, Any]]) -> str:
    """지목한 대상과 편집 허용 범위를 모델이 읽을 수 있게 쓴다.

    ■ 왜 프롬프트가 아니라 지시문인가

    계획(§3.3)은 "프롬프트에 선택 subgraph 만 넣는다" 였는데, 실제 구조에서 그래프는
    시스템 프롬프트가 아니라 **tools 를 통해** 모델에 전달된다(`make_tools(graph_data, ...)`).
    프롬프트를 줄여도 토큰이 줄지 않는다는 뜻이다. 그래서 여기서는 **무엇을 고쳐야 하고
    무엇을 건드리면 안 되는지**를 분명히 말하는 데 집중한다.

    ■ 이것을 믿지 않는다

    모델이 이 지시를 지킬 거라고 가정하지 않는다. `validate_scope()` 가 결과를 직접 비교하고
    범위 밖이면 거부한다. 이 문단은 **성공률을 올리는 장치**이지 강제 수단이 아니다.
    """
    lines = ["[지목된 대상]",
             "사용자가 캔버스에서 아래 항목을 직접 골라 이 요청에 첨부했다. 이것이 요청의 대상이다."]
    for target in resolved:
        label = target.get("label")
        kind_name = {"workflow_node": "노드", "workflow_edge": "연결",
                     "app_component": "컴포넌트", "app_logic_node": "로직 노드"}.get(
            target["kind"], target["kind"])
        node_type = ""
        found = target.get("resolved") or {}
        if isinstance(found, dict) and found.get("type"):
            node_type = f", type={found['type']}"
        lines.append(f"- {kind_name} id={target['id']}{node_type}"
                     + (f" ({label})" if label else ""))

    scope = context["scope"]
    if scope == SCOPE_REFERENCE_ONLY:
        lines.append("\n[편집 금지] 위 대상은 **답변의 근거로만** 쓴다. 그래프를 바꾸지 않는다.")
        return "\n".join(lines)
    if scope == SCOPE_WHOLE_CANVAS:
        lines.append("\n[편집 범위] 사용자가 전체 캔버스 수정을 허용했다.")
        return "\n".join(lines)

    editable_nodes = sorted(allowed.get("nodes") or [])
    editable_edges = sorted(allowed.get("edges") or [])
    lines.append("\n[편집 범위] **아래 id 만** 바꾼다. 다른 노드·연결은 추가·삭제·수정하지 않는다.")
    lines.append(f"- 수정 가능한 노드: {', '.join(editable_nodes) or '(없음)'}")
    lines.append(f"- 수정 가능한 연결: {', '.join(editable_edges) or '(없음)'}")
    if scope == SCOPE_TARGET_AND_NEIGHBORS:
        lines.append("  (사용자가 '연결 항목 포함' 을 골라 직접 연결된 1단계까지 열려 있다)")
    lines.append("범위 밖이 하나라도 바뀌면 서버가 요청 전체를 거부한다 — 부분 적용은 없다.")
    # 범위 안에서 **실제로 할 수 있는 방법**을 알려 준다. 이게 없으면 모델이 "못 한다" 고
    # 판단해 아무것도 안 하고 끝낸다(2026-08-30: 노드 종류 변경 요청에 변화가 없었다).
    lines.append(
        "\n[이 범위에서 하는 방법]\n"
        "- 설정 변경: `update_node(node_id, data)` — 넘긴 필드만 병합된다.\n"
        "- **노드 종류 변경: `update_node(node_id, data, node_type=...)`** — id 와 연결이 그대로 남는다.\n"
        "  `delete_node` + `add_node` 를 쓰지 마라. 연결이 끊기고 새 id 가 생겨 범위 밖이 된다.\n"
        "- `generate_flow` 는 그래프 전체를 다시 만들므로 이 범위에서는 쓸 수 없다.\n"
        "- 지목한 것만으로 요청을 처리할 수 없으면, 바꾸지 말고 무엇이 더 필요한지 말해라.")
    return "\n".join(lines)
