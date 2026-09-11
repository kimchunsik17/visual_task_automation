"""graph_traversal.py — 두 실행 엔진이 공유하는 순회 규칙 (백로그 32 실행 엔진 v2, ENGINE-0 3단계).

왜 이 모듈이 있나
  `graph.compile_workflow` 는 그래프를 파이썬 소스로 만든다. 그 안에는 "코드를 어떻게 찍는가"와
  "그래프를 어떤 순서·규칙으로 걷는가"가 한 함수에 섞여 있었다. 인터프리터(생성 없이 노드를
  직접 실행하는 엔진)가 옛 엔진과 **정확히 같은** 순서로 걷지 않으면 코퍼스 대조(섀도 실행)가
  의미를 잃는다 — 그래서 걷는 규칙만 여기로 뽑아 두 엔진이 같은 함수를 부르게 한다.

여기 있는 것 (전부 정적 규칙 — 실행 시점 값에 의존하지 않는다)
  - prepare_graph        memoNode 제거 · 범위(scope) · 정지(stop) · 고정 출력(pinned) 정규화 · 보안 검증
  - classify_edges       제어 흐름 간선과 배선 간선(template/tools/attachments)의 구분, 첨부 전용 예외
  - select_roots         트리거 루트 판정(정의 파생 + 내장 5종), 폴백 휴리스틱, 연결된 루트 우선
  - join_expectations    재합류 노드가 기다려야 하는 상류 수 (루프 되돌림 간선 제외)
  - JoinGate             재합류 게이트의 상태 기계 — 도착 기록 · 자리 판정 · 분기 닫힘 뒤 방출 · 미아 방출
  - sibling_restore_source  병렬 분기 형제 오염 복원 규칙 (2026-09-04, PR #69)

여기 없는 것
  - 코드 방출(lines.append)·exec — graph.py 의 몫이다.
  - 노드 실행 의미론(conditionNode 가 어느 갈래를 고르는가 등) — 생성기와 (앞으로의) executor 의 몫이다.

바꿀 때의 규칙
  이 모듈을 바꾸면 `compile_workflow` 의 출력도 바뀐다. 의도한 변경이 아니면 코퍼스 해시 대조
  (공식 템플릿·큐레이션 시드·스모크 그래프)가 바이트 단위로 같아야 한다 — PR 본문에 대조 결과를 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from workflow_security import WorkflowSecurityError, validate_workflow_graph

# ── 상수 ───────────────────────────────────────────────────────────────────
# 값이 아니라 배선을 잇는 targetHandle — 실행 순서로 세지 않는다(세면 같은 노드가 두 번 실행된다).
NON_CONTROL_HANDLES: Tuple[str, ...] = ('template', 'tools', 'attachments')

# 배타 분기(if/elif/else)를 방출하는 노드. 형제 갈래에 걸친 재합류는 분기 안에 자리 잡지 못하고
# 분기 구문이 닫힌 자리에서 방출된다(JoinGate.flush_ready).
EXCLUSIVE_BRANCH_TYPES: Tuple[str, ...] = ('conditionNode', 'humanApprovalNode')

# 형제 오염 복원(sibling_restore_source)을 걸지 않는 상류 — 배타 분기는 한 갈래만 실행돼 오염이
# 없고, loopNode 는 반복 값을 last_result 로 넘기므로 복원하면 반복 값이 덮인다.
SIBLING_RESTORE_EXEMPT_TYPES: Tuple[str, ...] = ('conditionNode', 'humanApprovalNode', 'loopNode')

# node_definition 이 없던 시절의 내장 트리거. 정의 기반 트리거(youtube/rss/gmail …)는
# node_definition.trigger_types() 에서 파생한다 — 손으로 적은 목록에 새 트리거를 잊는 사고(N1·N2)를 막는다.
BUILTIN_TRIGGER_TYPES: Tuple[str, ...] = (
    'startNode', 'scheduleNode', 'webhookNode', 'discordTriggerNode', 'telegramTriggerNode')

ERROR_EMPTY_GRAPH = "Error: Graph is empty. Please drag and drop nodes from the sidebar."
ERROR_EMPTY_SCOPE = "Error: 선택한 실행 범위에 실행할 노드가 없습니다."
ERROR_NO_ROOT = "Error: No valid starting node found."


class GraphPreparationError(Exception):
    """그래프를 걸을 수 없다. str(exc) 가 사용자에게 보이는 'Error: …' 문구 그대로다 —
    compile_workflow 는 이 문구를 결과 문자열로 돌려주고, 인터프리터도 같은 문구를 쓴다."""


# ── 1. 그래프 준비 ─────────────────────────────────────────────────────────
@dataclass
class PreparedGraph:
    nodes: list
    edges: list
    pinned_outputs: Dict[str, Any]
    node_dict: Dict[str, dict]


def prepare_graph(nodes: list, edges: list, *, stop_node_id=None, scope_node_ids=None,
                  pinned_outputs=None) -> PreparedGraph:
    """실행 대상 노드·간선을 확정한다.

    범위 실행(EDITOR_SHORTCUTS §7.4)은 그래프를 잘라내는 방식이다 — 노드 생성기는 자기 하류를
    스스로 순회하므로, 생성기마다 조건을 넣는 대신 순회할 간선 자체를 줄인다.
      stop_node_id    이 노드까지만(하류로 나가는 간선을 지운다). entry 와 같으면 "이 노드만".
      scope_node_ids  이 노드들만(선택 영역 실행). 그 밖의 노드와 간선은 없는 것으로 본다.
      pinned_outputs  {node_id: 출력} — 그 노드는 실행하지 않고 고정 값을 흘린다(§7.3). None 값은 버린다.
    """
    if not nodes:
        raise GraphPreparationError(ERROR_EMPTY_GRAPH)

    # 캔버스 주석(memoNode)은 실행 대상이 아니다 — 남겨두면 "들어오는 엣지가 없는 노드"라서
    # 폴백 루트로 잡혀 'Unsupported node type' 결과를 만들 수 있다.
    nodes = [n for n in nodes if n.get('type') != 'memoNode']
    if not nodes:
        raise GraphPreparationError(ERROR_EMPTY_GRAPH)

    pinned = {str(k): v for k, v in (pinned_outputs or {}).items() if v is not None}

    if scope_node_ids:
        keep = {str(n) for n in scope_node_ids}
        nodes = [n for n in nodes if str(n.get('id')) in keep]
        edges = [e for e in edges if str(e.get('source')) in keep and str(e.get('target')) in keep]
        if not nodes:
            raise GraphPreparationError(ERROR_EMPTY_SCOPE)
    if stop_node_id is not None:
        # 여기까지 실행 — 이 노드의 결과는 만들되 하류로는 넘기지 않는다.
        edges = [e for e in edges if str(e.get('source')) != str(stop_node_id)]

    try:
        validate_workflow_graph(nodes, edges)
    except WorkflowSecurityError as exc:
        raise GraphPreparationError(f"Error: Security validation failed: {exc}") from exc

    return PreparedGraph(nodes=nodes, edges=edges, pinned_outputs=pinned,
                         node_dict={n['id']: n for n in nodes})


# ── 2. 간선 분류 ───────────────────────────────────────────────────────────
@dataclass
class EdgeIndex:
    tool_node_ids: Set[str]                                   # targetHandle='tools' 로 들어가는 source — 루트가 될 수 없다
    forward_edges: Dict[str, List[Tuple[str, Optional[str]]]]  # source -> [(target, sourceHandle)] — 제어 흐름만, 간선 순서 유지
    incoming_edges: Dict[str, List[dict]]                     # target -> [{'source', 'targetHandle'}] — 배선 간선 포함 전부
    control_flow_edges: List[dict]                            # 실행 순서로 세는 간선 원본
    has_incoming: Set[str]                                    # 제어 간선이 들어오는 노드


def classify_edges(edges: list) -> EdgeIndex:
    """제어 흐름 간선과 배선 간선을 가른다.

    첨부 포트(ADR-0018)는 값이 아니라 파일을 잇는 자리라 실행 순서로 세지 않는다 — 세면 같은
    노드가 두 번 실행된다. 다만 발송 노드에 **첨부 간선만** 연결된 경우(편집기에서 본문 포트를
    빼먹은 그래프)까지 제외하면 그 노드는 아예 실행되지 않는다. 그건 사용자가 의도한 바가
    아니므로, 본문 간선이 하나도 없을 때만 첨부 간선을 제어 흐름으로도 인정한다.
    """
    tool_node_ids: Set[str] = set()
    for e in edges:
        if e.get('targetHandle') == 'tools':
            tool_node_ids.add(e['source'])

    forward_edges: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    incoming_edges: Dict[str, List[dict]] = {}
    control_flow_edges: List[dict] = []

    body_fed = {e['target'] for e in edges if e.get('targetHandle') not in NON_CONTROL_HANDLES}

    for e in edges:
        source = e['source']
        target = e['target']
        target_handle = e.get('targetHandle')

        incoming_edges.setdefault(target, []).append({'source': source, 'targetHandle': target_handle})

        is_attachment_only = target_handle == 'attachments' and target not in body_fed
        if target_handle not in NON_CONTROL_HANDLES or is_attachment_only:
            control_flow_edges.append(e)
            forward_edges.setdefault(source, []).append((target, e.get('sourceHandle')))

    return EdgeIndex(
        tool_node_ids=tool_node_ids,
        forward_edges=forward_edges,
        incoming_edges=incoming_edges,
        control_flow_edges=control_flow_edges,
        has_incoming={e['target'] for e in control_flow_edges},
    )


def control_incoming(node_id: str, index: EdgeIndex) -> List[dict]:
    """이 노드로 들어오는 제어 간선(배선 간선 제외). 배선 간선은 incoming_edges 에 남아 있어
    발송 노드가 첨부 출처를 찾는 데 쓰인다 — 그것과 제어 판정을 섞지 않기 위한 조회."""
    return [inc for inc in index.incoming_edges.get(node_id, [])
            if inc.get('targetHandle') not in NON_CONTROL_HANDLES]


# ── 3. 루트 판정 ───────────────────────────────────────────────────────────
def trigger_node_types() -> Set[str]:
    """루트로 인정하는 노드 타입 — 내장 5종 + 정의 파생 트리거."""
    import node_definition as _node_definition
    return set(BUILTIN_TRIGGER_TYPES) | set(_node_definition.trigger_types())


def select_roots(prepared: PreparedGraph, index: EdgeIndex, entry_node_id=None) -> List[dict]:
    """순회를 시작할 노드들. 순서가 곧 실행 순서다.

    1. entry_node_id(승인 재개·범위 실행)가 있으면 그 노드 하나.
    2. 트리거 노드 전부(tool 노드 제외).
    3. 없으면 폴백 — 제어 간선이 들어오지 않고, 컨테이너 안이 아니고, llmNode 도 tool 도 아닌 노드.
    4. 그것도 없으면(시작 노드 없는 순환 그래프) 최상위 첫 노드.
    루트가 여럿이면 하류가 있는 것만 남긴다(하나도 없을 때만 전부 유지).
    """
    nodes, node_dict = prepared.nodes, prepared.node_dict

    if entry_node_id is not None:
        if entry_node_id not in node_dict:
            raise GraphPreparationError(f"Error: 재개 지점 노드({entry_node_id})를 그래프에서 찾을 수 없다.")
        roots = [node_dict[entry_node_id]]
    else:
        trigger_types = trigger_node_types()
        roots = [n for n in nodes if n['type'] in trigger_types and n['id'] not in index.tool_node_ids]

    if not roots and entry_node_id is None:
        roots = [n for n in nodes
                 if n['id'] not in index.has_incoming and not n.get('parentNode')
                 and n['type'] != 'llmNode' and n['id'] not in index.tool_node_ids]
        if not roots:
            top_level = [n for n in nodes if not n.get('parentNode')]
            roots = [top_level[0]] if top_level else []

    if not roots:
        raise GraphPreparationError(ERROR_NO_ROOT)

    if len(roots) > 1:
        connected_roots = [r for r in roots if r['id'] in index.forward_edges]
        if connected_roots:
            roots = connected_roots
    return roots


# ── 4. 재합류 ──────────────────────────────────────────────────────────────
def forward_reachable(index: EdgeIndex, start_id: str) -> Set[str]:
    """start_id 에서 제어 간선을 따라 도달할 수 있는 노드(자기 자신은 되돌아올 때만 포함)."""
    seen: Set[str] = set()
    stack = [start_id]
    while stack:
        for nxt, _h in index.forward_edges.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


JoinExpectations = Dict[str, Tuple[int, Set[str]]]


def join_expectations(index: EdgeIndex) -> JoinExpectations:
    """재합류 노드 -> (기대 도착 수, back-edge 를 뺀 상류 집합).

    제어 간선이 2개 이상 들어오는 노드가 재합류다. 갈래마다 따로 방출하면 재합류 노드와 그 하류
    전체가 갈래 수만큼 실행된다(메일 두 통, 재검증 §2.1) — 모든 갈래가 방출된 뒤 한 번만 방출한다.
    루프 되돌림(back-edge) 상류는 기다리면 영원히 못 만나므로 기대 목록에서 뺀다.
    간선 단위로 센다 — 같은 source 에서 다른 핸들로 두 번 들어와도(조건의 r1/else 가 같은
    노드로) 각각이 갈래 하나씩이라 도착을 따로 기다려야 한다.
    """
    join_edges: Dict[str, List[str]] = {}
    for e in index.control_flow_edges:
        join_edges.setdefault(e['target'], []).append(e['source'])

    expected: JoinExpectations = {}
    for target, sources in join_edges.items():
        if len(sources) >= 2:
            fwd = forward_reachable(index, target)
            live = [s for s in sources if s not in fwd]
            if len(live) >= 2:
                expected[target] = (len(live), set(live))
    return expected


@dataclass
class _PendingJoin:
    visited: Set[str] = field(default_factory=set)
    arrivals: int = 0
    paths: Set[tuple] = field(default_factory=set)


class JoinGate:
    """재합류 게이트 — "재합류 노드를 어디에 한 번 방출하는가"의 상태 기계.

    두 엔진이 같은 인스턴스 규칙을 쓴다: 옛 엔진은 방출 위치를, 인터프리터는 정적 계획의 실행
    위치를 이것으로 정한다. 실행 시점의 도착 수로 판정하면 안 된다 — 배타 분기의 한 갈래만
    실행돼도 재합류는 분기 뒤에서 실행돼야 하므로(merge 는 없는 상류를 빈 값으로 건너뛴다),
    판정은 **정적(그래프 위 방출 여부)** 이어야 한다.

    분기 경로(branch_path)는 배타 분기의 "어느 갈래 안인가" 스택이다. 재합류를 어디에 둘지 이 경로로
    판정한다:
      - 상류 전부가 현재 경로의 계보 안(같은 갈래·바깥 스코프·이미 닫힌 내부 구문)이면 지금 이
        자리(분기 안 포함)에 방출해도 안전하다 — 분기 내부 다이아몬드는 분기 안에 남아야, 그 갈래가
        실행되지 않을 때 하류(발송 노드)도 실행되지 않는다.
      - 상류가 형제 갈래에 걸쳐 있으면 분기 안에 방출할 수 없다(다른 갈래가 타면 영영 못 만난다) —
        분기 구문이 닫힌 자리에서 flush_ready 가 방출한다.
    """

    def __init__(self, expected: JoinExpectations):
        self.expected = expected
        self.emitted_nodes: Set[str] = set()          # 본문이 이미 방출된 노드
        self.emitted_paths: Dict[str, tuple] = {}     # 노드 -> 방출 당시의 분기 경로
        self.pending: Dict[str, _PendingJoin] = {}    # 자리를 기다리는 재합류 노드
        self.branch_path: List[Tuple[str, str]] = []  # (배타 분기 노드 id, 갈래 식별자) 스택

    # 분기 경로
    def begin_branch(self, owner_id: str, branch_key) -> None:
        self.branch_path.append((owner_id, str(branch_key)))

    def end_branch(self) -> None:
        self.branch_path.pop()

    # 방출 기록 — 생성기 본문은 자기 코드를 먼저 쌓고 나서 하류로 재귀하므로 시작 시점에 기록한다.
    def mark_emitted(self, node_id: str) -> None:
        self.emitted_nodes.add(node_id)
        self.emitted_paths[node_id] = tuple(self.branch_path)

    def is_join(self, node_id: str) -> bool:
        return node_id in self.expected

    @staticmethod
    def path_compatible(source_path, current_path) -> bool:
        # 한쪽이 다른 쪽의 접두사면 같은 계보다(바깥 스코프 또는 같은 갈래 안).
        shorter = min(len(source_path), len(current_path))
        return tuple(source_path[:shorter]) == tuple(current_path[:shorter])

    def placeable_here(self, join_id: str) -> bool:
        """지금 이 자리에 방출해도 되는가: (a) 기대한 갈래가 전부 도착했고 (b) 상류가 전부 방출됐고
        (c) 상류·도착 지점이 모두 현재 분기 경로의 계보 안이어야 한다. (c)가 없으면 형제 갈래에
        걸친 재합류가 마지막 갈래 "안"에 방출돼, 다른 갈래가 실행될 때 그 노드를 영영 못 만난다."""
        count, sources = self.expected[join_id]
        st = self.pending.get(join_id)
        if st is None or st.arrivals < count:
            return False
        if not sources <= self.emitted_nodes:
            return False
        return (all(self.path_compatible(self.emitted_paths.get(s, ()), self.branch_path) for s in sources)
                and all(self.path_compatible(p, self.branch_path) for p in st.paths))

    def arrive(self, join_id: str, visited: Set[str]) -> Optional[Set[str]]:
        """한 갈래가 재합류 노드에 도착했다. 도착만 기록하고 자리는 나중에 잡는다.

        지금 이 자리에 방출할 수 있으면(마지막 상류 갈래가 방출을 마친 같은 들여쓰기의 fan-out)
        pending 에서 빼고 **합쳐진 visited** 를 돌려준다 — 호출자는 이 노드를 방출하되
        prev_res_var 를 넘기지 말아야 한다(특정 갈래의 지역 변수를 물려주면 다른 갈래가 실행됐을
        때 NameError). 아직이면(또는 이미 방출됐으면) None — 호출자는 여기서 멈춘다.
        """
        if join_id in self.emitted_nodes:
            return None
        st = self.pending.setdefault(join_id, _PendingJoin())
        st.visited |= visited
        st.arrivals += 1
        st.paths.add(tuple(self.branch_path))
        if not self.placeable_here(join_id):
            return None
        self.pending.pop(join_id, None)
        return visited | st.visited

    def flush_ready(self, emit: Callable[[str, Set[str]], None]) -> None:
        """분기 구문이 닫힌 자리에서, 상류가 전부 방출됐고 계보가 맞는 재합류 노드를 방출한다.
        emit(join_id, visited) 는 그 노드를 방출한다(방출이 다른 재합류의 상류를 채울 수 있어
        진전이 있는 동안 반복한다). 순회 순서는 옛 엔진과 같다 — 스냅샷을 훑고, 진전이 있으면 다시."""
        progress = True
        while progress:
            progress = False
            for join_id in list(self.pending):
                if self.placeable_here(join_id):
                    st = self.pending.pop(join_id)
                    progress = True
                    emit(join_id, st.visited)

    def flush_stranded(self, emit: Callable[[str, Set[str]], None]) -> None:
        """상류 일부가 아예 방출되지 않아(도달 불가 갈래, 부분 실행 진입) 자리 잡지 못한 재합류 —
        마지막 루트 끝에서 한 번은 방출한다. 예전에는 도달한 갈래마다 방출됐으므로 한 번 방출이
        하위 호환이다(merge 는 없는 상류를 빈 값으로 건너뛴다)."""
        while self.pending:
            join_id, st = self.pending.popitem()
            emit(join_id, st.visited)


# ── 5. 형제 오염 복원 ─────────────────────────────────────────────────────
def sibling_restore_source(node_id: str, prev_res_var: Optional[str], *, node_dict: Dict[str, dict],
                           index: EdgeIndex) -> Optional[str]:
    """병렬 분기 형제 오염 복원(2026-09-04, PR #69) — 복원해야 하면 상류 노드 id, 아니면 None.

    한 노드에서 두 갈래 이상이 나뉘면(병렬 분기) 갈래는 **순차** 실행되므로, 두 번째 갈래가 시작할 때
    last_result 에는 첫 갈래의 마지막 출력이 남아 있다(시연 포스터 그래프에서 실제 발견 — 배경 프롬프트
    LLM 이 공고문 대신 앞 갈래의 문안 JSON 을 받았다). 갈래 진입 시점에 자기 상류의 기록
    (__node_results__, log_step 이 항상 남긴다)으로 되돌린다.
    조건: 직전 값이 공유 변수 last_result 로 넘어왔고(노드 전용 변수 val_x·res_text_x 는 형제가 덮을 수
    없어 안전), 제어 간선이 정확히 하나 들어오며, 그 상류가 배타 분기·loop 가 아니고 갈래를 둘 이상 낸다.
    """
    if prev_res_var != 'last_result':
        return None
    ctl_incoming = control_incoming(node_id, index)
    if len(ctl_incoming) != 1:
        return None
    src_id = ctl_incoming[0]['source']
    src_node = node_dict.get(src_id)
    if src_node is None or src_node.get('type') in SIBLING_RESTORE_EXEMPT_TYPES:
        return None
    if len(index.forward_edges.get(src_id, [])) < 2:
        return None
    return src_id
