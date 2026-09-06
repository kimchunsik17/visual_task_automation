"""node_bodies.py — 노드 하나의 생성 코드 본문만 떼어 내는 렌더러 (백로그 32 ENGINE-0 2단계, 하이브리드 이관의 재료).

왜 이 모듈이 있나
  생성기(node_generators, 49종)는 "자기 본문을 lines 에 쌓고 → 하류로 재귀(generate_block_fn)" 한다.
  인터프리터로 옮길 때 49종을 한 번에 다시 쓰지 않는다(빅뱅 금지, 로드맵 §3.1). 대신 생성기를 그대로
  부르되 **재귀를 기록만 하는 함수**로 바꿔 끼워, 그 노드의 본문 줄만 얻는다. 인터프리터는 이 본문을
  프렐류드(graph.emit_module_prelude) 네임스페이스 위에서 exec 한다 — 본문은 옛 엔진이 찍는 줄과 바이트
  단위로 같으므로 노드 의미론의 등가성은 구성상 보장된다. 재구현해야 하는 것은 순회(graph_traversal)와
  흐름 노드뿐이다.

무엇을 알려 주나 (RenderedBody)
  - lines            그 노드의 본문 줄 (indent 기준)
  - downstream       생성기가 하류로 넘기려던 호출 — 대상·들여쓰기·active_llm_id·prev_res_var.
                     인터프리터가 "다음 노드에 어떤 변수 이름을 직전 값으로 주는가"를 여기서 읽는다.
  - nests_downstream 하류 호출이 본문보다 깊은 들여쓰기에서 일어난다 = 생성기가 제어 구문(if/for)을
                     방출한다. 이런 노드는 본문만 떼어 낼 수 없어 인터프리터가 직접 구현한다.
  - terminal_statement 본문 첫 들여쓰기의 return/break — 루트 함수를 끝내거나 반복을 끊는 노드.
  - wrappable        위 둘이 없고 분기 표시(begin_branch)도 없는 노드. 래퍼 executor 로 감쌀 수 있다.

하지 않는 것
  - 실행하지 않는다. 네임스페이스·exec 는 인터프리터의 몫이다.
  - 재합류·형제 복원 같은 순회 규칙을 모른다 — graph_traversal 이 판정하고 인터프리터가 적용한다.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from node_registry import node_registry
import node_generators  # noqa: F401  (등록 부작용 — 생성기 49종)

# 본문만 떼어 낼 수 없어 인터프리터가 **직접 구현**하는 타입. 인스턴스가 아니라 타입으로 고른다 —
# 규칙·핸들이 없는 conditionNode 는 본문만 보면 선형처럼 보이지만(if False/else pass) 그래도 흐름 노드다.
#   conditionNode·humanApprovalNode  배타 분기(if/elif/else) 안에서 하류를 부른다
#   loopNode·distributorNode         for 구문 안에서 하류를 부른다
#   breakNode·outputNode             본문이 break / return 으로 제어를 끊는다
# 나머지(51종 중 45종)는 최소 그래프에서 wrappable 이다 — test_node_bodies.py 가 양쪽을 못 박는다.
NATIVE_FLOW_TYPES: Tuple[str, ...] = (
    'conditionNode', 'humanApprovalNode', 'loopNode', 'distributorNode', 'breakNode', 'outputNode')


@dataclass
class DownstreamCall:
    target_id: str
    indent: str
    active_llm_id: Optional[str]
    prev_res_var: Optional[str]


@dataclass
class RenderedBody:
    node_id: str
    node_type: str
    indent: str
    lines: List[str] = field(default_factory=list)
    downstream: List[DownstreamCall] = field(default_factory=list)
    branches: List[Tuple[str, str]] = field(default_factory=list)   # begin_branch(owner, key) 기록

    @property
    def source(self) -> str:
        return "\n".join(self.lines)

    @property
    def nests_downstream(self) -> bool:
        """하류 호출이 본문 들여쓰기보다 깊다 — 생성기가 if/for 구문 안에서 하류를 부른다."""
        return any(call.indent != self.indent for call in self.downstream)

    @property
    def terminal_statement(self) -> Optional[str]:
        """본문 들여쓰기에서 실행 흐름을 끊는 문장: 'return' | 'break' | None."""
        for line in self.lines:
            if not line.startswith(self.indent):
                continue
            rest = line[len(self.indent):]
            if rest.startswith(" ") or rest.startswith("\t"):
                continue  # 더 깊은 줄
            head = rest.split(" ", 1)[0]
            if head in ("return", "break"):
                return head
        return None

    @property
    def wrappable(self) -> bool:
        """본문을 그대로 exec 하고 downstream 으로 이어가면 옛 엔진과 같은 노드인가."""
        return not self.nests_downstream and self.terminal_statement is None and not self.branches


def render_node_body(node_id: str, *, node_dict: Dict[str, dict], forward_edges: Dict[str, list],
                     incoming_edges: Dict[str, list], active_llm_id: Optional[str] = None,
                     prev_res_var: Optional[str] = None, indent: str = "",
                     visited: Optional[Set[str]] = None) -> RenderedBody:
    """생성기를 부르되 하류 재귀는 기록만 한다. forward_edges/incoming_edges/node_dict 는 옛 엔진이 쓰는
    것과 **같은 객체**를 넘겨야 한다 — promptNode 가 하류 llmNode 를 찾거나 mergeNode 가 상류 목록을
    읽는 등, 생성기가 그래프를 직접 본다.

    등록되지 않은 타입은 compile_workflow 의 'Unsupported Node' 블록과 같은 줄을 낸다.
    """
    node = node_dict[node_id]
    node_type = node['type']
    rendered = RenderedBody(node_id=node_id, node_type=node_type, indent=indent)
    lines = rendered.lines
    recorder = _Recorder(rendered)

    generator = node_registry.get_generator(node_type)
    if generator is None:
        lines.append(f"{indent}# --- Unsupported Node ({node_id}) ---")
        lines.append(f"{indent}print('Unsupported node type: {node_type}')")
        lines.append(f"{indent}last_result = 'Unsupported node type: {node_type}'")
        for target_id, _handle in forward_edges.get(node_id, []):
            recorder(target_id, indent, active_llm_id=active_llm_id, prev_res_var='last_result')
        return rendered

    generator(
        node_id=node_id,
        node=node,
        indent=indent,
        active_llm_id=active_llm_id,
        prev_res_var=prev_res_var,
        visited=set(visited or ()),
        node_dict=node_dict,
        forward_edges=forward_edges,
        incoming_edges=incoming_edges,
        lines=lines,
        generate_block_fn=recorder,
    )
    return rendered


class _Recorder:
    """generate_block_fn 자리에 끼우는 기록기 — 생성기의 하류 재귀를 실행하지 않고 적어 둔다.
    compile_workflow 의 generate_block 과 같은 호출 규약(위치 인자 target_id·indent, 키워드
    active_llm_id·prev_res_var·visited, 함수 속성 begin_branch/end_branch)을 따른다."""

    def __init__(self, rendered: RenderedBody):
        self._rendered = rendered

    def __call__(self, target_id, call_indent, active_llm_id=None, prev_res_var=None, visited=None,
                 _as_join=False):
        self._rendered.downstream.append(DownstreamCall(
            target_id=target_id, indent=call_indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var))

    def begin_branch(self, owner_id, branch_key) -> None:
        self._rendered.branches.append((owner_id, str(branch_key)))

    def end_branch(self) -> None:
        pass


def parses_standalone(rendered: RenderedBody) -> bool:
    """본문이 (indent='' 기준) 모듈 수준 파이썬으로 파싱되는가 — 래퍼 executor 의 전제."""
    try:
        ast.parse(rendered.source)
        return True
    except SyntaxError:
        return False
