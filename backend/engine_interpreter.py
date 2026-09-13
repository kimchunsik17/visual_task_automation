"""engine_interpreter.py — 그래프 인터프리터 (백로그 32 실행 엔진 v2, ENGINE-0 4단계, ADR-0027).

무엇을 하나
  compile_workflow 가 파이썬 소스를 만들어 exec 하는 대신, 같은 순회 규칙(graph_traversal)으로 **정적 계획**을
  세우고 그 계획을 따라 노드 본문(node_bodies — 생성기가 찍는 줄 그대로)을 프렐류드 네임스페이스 위에서 직접
  실행한다. 흐름 노드 6종(node_bodies.NATIVE_FLOW_TYPES)만 여기서 파이썬 제어문으로 구현한다 — 구조 앞뒤의
  곧은 줄은 생성기와 같은 함수(flow_nodes.emit_*, ui_nodes.emit_*)가 만든다.

왜 계획을 먼저 세우나
  재합류(merge) 자리는 실행 시점 도착 수로 정할 수 없다 — 배타 분기의 한 갈래만 실행돼도 merge 는 분기 뒤에서
  한 번 실행돼야 한다(옛 엔진은 방출 위치가 그렇게 정해져 있다). 그래서 옛 엔진의 generate_block 과 같은 순서로
  걷되 코드 대신 계획을 만들고, 같은 JoinGate 로 재합류 자리를 정한다.

옛 엔진과 같아야 하는 것 / 다른 것
  - 같은 것: 노드 실행 순서, 각 노드가 보는 직전 값(prev_res_var 변수 이름), log_step 기록, __node_results__,
    토큰 집계, 루트 단위 예외 처리('► Flow N Error'), 승인 대기 신호, 결과 문자열 형식.
  - 다른 것: 노드 본문을 모듈 수준에서 exec 하므로 루트 사이 지역 변수가 격리되지 않는다(옛 엔진은 run_root_N
    함수 지역). 옛 엔진에서 NameError 였을 참조가 여기서는 통과할 수 있다 — 섀도 대조에서 드러나면 루트마다
    네임스페이스를 나눈다.

이 모듈이 하지 않는 것
  - 자격증명 치환·승인 스냅샷·durable 대기 전환 — graph.run_workflow 가 두 엔진 공통으로 한다.
  - 보안 검증 — run_workflow 가 먼저 compile_workflow 를 불러 생성 소스 검증(validate_compiled_workflow)을 통과한
    그래프만 여기로 온다. 여기서 exec 하는 본문은 그 소스의 부분집합이다.
  - 노드별 재시도·타임아웃·단계 기록 — 개입 지점은 _Executor.run_item 하나로 모였고, ENGINE-1·3 이 거기에 얹는다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import graph_traversal as gt
import node_bodies
import node_retry
from node_generators import flow_nodes as _flow
from node_generators import ui_nodes as _ui

REJECTED_MESSAGE = 'Workflow execution halted by Human Approval Node (Rejected).'


class ReturnSignal(Exception):
    """outputNode 의 `return last_result` — 루트 하나를 끝낸다."""

    def __init__(self, value: Any):
        super().__init__()
        self.value = value


class BreakSignal(Exception):
    """breakNode 의 `break` — 가장 안쪽 반복(loopNode·distributorNode)을 끊는다."""


class PlanError(Exception):
    """계획을 세울 수 없다 — 흐름 노드가 아닌데 본문만 떼어 낼 수 없는 노드(생성기가 제어 구문을 냄)."""


# ── 계획 ───────────────────────────────────────────────────────────────────
@dataclass
class Exec:
    """곧은 줄 묶음 — 네임스페이스에서 그대로 exec. 노드 본문·고정 출력·형제 복원·흐름 노드 머리/꼬리.
    kind 는 진행 이벤트(ENGINE-1)가 "노드가 시작됐다" 를 어느 항목에서 낼지 고르는 데 쓴다 — body·pinned·header 가
    시작점이고 restore·tail 은 아니다."""
    node_id: str
    source: str
    kind: str = "body"                # body | pinned | restore | header | tail
    node_type: Optional[str] = None
    # 노드 설정 retries/backoffSec (ENGINE-3, node_retry). body 에만 — 재시도 가능한 오류로 끝나면 본문만 다시 exec 한다.
    retry: Optional[node_retry.RetrySettings] = None
    _code: Any = field(default=None, repr=False, compare=False)

    def code(self):
        if self._code is None:
            self._code = compile(self.source, f"<node {self.node_id}>", "exec")
        return self._code


@dataclass
class Cond:
    node_id: str
    header: Exec
    cases: List[Tuple[str, List]]     # (판정식, 갈래 계획) — 규칙 순서대로 처음 참인 갈래 하나만
    otherwise: List
    _compiled: List[Any] = field(default_factory=list, repr=False, compare=False)

    def compiled_cases(self):
        if len(self._compiled) != len(self.cases):
            self._compiled = [compile(expr, f"<condition {self.node_id}>", "eval") for expr, _ in self.cases]
        return self._compiled


@dataclass
class Loop:
    node_id: str
    header: Exec
    count_expr: str                   # 옛 엔진의 range(int(<raw>)) 와 같은 식을 같은 이름공간에서 평가
    acc_var: str
    body: Optional[List]              # None 이면 본문이 pass — 누적 대입도 없다
    tail: Exec
    done: List


@dataclass
class Distribute:
    node_id: str
    header: Exec
    list_var: str
    item_var: str
    acc_var: str
    body: List
    tail: Exec
    done: List


@dataclass
class Approval:
    node_id: str
    header: Exec                      # 결정 읽기(없으면 __ApprovalPendingSignal__) · 통과 · 기록
    decision_var: str
    has_handles: bool                 # approved/rejected 핸들이 있으면 분기, 없으면 옛 단순 연결(거절=중단)
    approved: List
    rejected: Optional[List]          # None 이면 거절 갈래가 없다 → 예외로 중단
    plain: List


@dataclass
class Output:
    node_id: str
    body: Exec
    node_type: str = "outputNode"


@dataclass
class Break:
    node_id: str
    body: Exec
    node_type: str = "breakNode"


@dataclass
class ErrorSplit:
    """error 출력 핸들이 있는 노드(ENGINE-3 2단계) — 본문을 돌린 뒤 실패면 on_error, 성공이면 normal. 옛 엔진의
    graph.emit_error_split(if/else)과 같은 배타 분기."""
    node_id: str
    body: Exec
    on_error: List
    normal: List


@dataclass
class Root:
    items: List


@dataclass
class Plan:
    roots: List[Root]
    nodes: list
    project_id: Any
    entry_node_id: Any
    error_branches: bool = False      # error 간선이 있어 프렐류드 헬퍼(_node_failed·_node_error_payload)가 필요한가


def build_plan(nodes: list, edges: list, *, project_id=None, entry_node_id=None, stop_node_id=None,
               scope_node_ids=None, pinned_outputs=None) -> Plan:
    """그래프를 걷되 코드 대신 계획을 만든다. 실패는 graph_traversal.GraphPreparationError(사용자 문구) 또는
    PlanError 로 올라간다."""
    prepared = gt.prepare_graph(nodes, edges, stop_node_id=stop_node_id, scope_node_ids=scope_node_ids,
                                pinned_outputs=pinned_outputs)
    index = gt.classify_edges(prepared.edges)
    roots = gt.select_roots(prepared, index, entry_node_id)
    return _PlanBuilder(prepared, index).build(roots, project_id=project_id, entry_node_id=entry_node_id)


class _PlanBuilder:
    """graph.compile_workflow 의 generate_block 과 같은 순서로 걷는다 — 재합류 게이트·형제 복원·고정 출력·
    배타 분기 뒤 방출·마지막 루트의 미아 방출까지 같은 지점에서 같은 판정을 한다."""

    def __init__(self, prepared: gt.PreparedGraph, index: gt.EdgeIndex):
        self.prepared = prepared
        self.index = index
        self.node_dict = prepared.node_dict
        self.forward = index.forward_edges
        self.incoming = index.incoming_edges
        self.pinned = prepared.pinned_outputs
        self.gate = gt.JoinGate(gt.join_expectations(index))

    def build(self, roots: list, *, project_id, entry_node_id) -> Plan:
        plan_roots: List[Root] = []
        for idx, root in enumerate(roots):
            items = self.block(root['id'], None, None, set())
            if idx == len(roots) - 1:
                # 루트 여러 개에 걸친 재합류는 마지막 루트에서야 상류가 모두 방출되므로 여기서 정리한다.
                self.gate.flush_stranded(
                    lambda join_id, visited: items.extend(self.block(join_id, None, None, visited, _as_join=True)))
            plan_roots.append(Root(items))
        return Plan(plan_roots, self.prepared.nodes, project_id, entry_node_id,
                    error_branches=gt.has_error_branches(self.prepared.edges, self.node_dict))

    def block(self, node_id: str, active_llm_id: Optional[str], prev_res_var: Optional[str],
              visited: set, _as_join: bool = False) -> List:
        import graph  # 방출 조각(emit_pinned_output·sibling_restore_line) 공유 — 지연 import(무거운 모듈)

        items: List = []
        if node_id in visited:
            return items

        # 재합류 게이트: 도착만 기록하고 자리는 나중에 잡는다(graph_traversal.JoinGate).
        if not _as_join and self.gate.is_join(node_id):
            merged_visited = self.gate.arrive(node_id, visited)
            if merged_visited is None:
                return items
            visited = merged_visited
            prev_res_var = None

        visited = visited | {node_id}
        node = self.node_dict.get(node_id)
        if not node:
            return items
        self.gate.mark_emitted(node_id)

        # 0. 고정 출력(§7.3)
        if node_id in self.pinned:
            lines: List[str] = []
            out_var = graph.emit_pinned_output(lines, node_id, node, "", self.pinned[node_id])
            items.append(Exec(node_id, "\n".join(lines), kind="pinned", node_type=node['type']))
            for target_id, _handle in self.forward.get(node_id, []):
                items.extend(self.block(target_id, active_llm_id, out_var, visited))
            return items

        # 0.5 병렬 분기 형제 오염 복원(PR #69)
        restore_src = gt.sibling_restore_source(node_id, prev_res_var, node_dict=self.node_dict, index=self.index)
        if restore_src is not None:
            items.append(Exec(node_id, graph.sibling_restore_line("", restore_src), kind="restore", node_type=node['type']))

        node_type = node['type']
        if node_type in node_bodies.NATIVE_FLOW_TYPES:
            items.append(self._flow(node_type, node_id, node, active_llm_id, prev_res_var, visited))
            if node_type in gt.EXCLUSIVE_BRANCH_TYPES:
                # 배타 분기가 닫힌 자리 — 형제 갈래에 걸친 재합류를 여기서 한 번 방출한다.
                self.gate.flush_ready(
                    lambda join_id, vis: items.extend(self.block(join_id, None, None, vis, _as_join=True)))
            return items

        # 1. 나머지는 생성기 본문 그대로(하이브리드 래퍼)
        body = node_bodies.render_node_body(node_id, node_dict=self.node_dict, forward_edges=self.forward,
                                            incoming_edges=self.incoming, active_llm_id=active_llm_id,
                                            prev_res_var=prev_res_var, visited=visited)
        if not body.wrappable:
            raise PlanError(f"{node_type}({node_id}) 는 NATIVE_FLOW_TYPES 가 아닌데 본문만 떼어 낼 수 없다 "
                            f"(nests={body.nests_downstream}, terminal={body.terminal_statement}, branches={body.branches})")
        body_item = Exec(node_id, body.source, kind="body", node_type=node_type, retry=node_retry.retry_settings(node))
        error_targets = gt.error_branch_targets(node_id, self.forward)
        if error_targets:
            # 에러 출력 핸들(ENGINE-3 2단계) — 옛 엔진의 emit_error_split 과 같은 배타 분기, 같은 순서(error 갈래 → 보통 하류).
            # 갈래 경로를 표시해 두 갈래에서 만나는 재합류를 분기 뒤에 한 번 놓는다.
            normal_targets = gt.normal_branch_targets(node_id, self.forward)
            payload_var = gt.error_payload_var(node_id)
            on_error = self._branch(node_id, gt.ERROR_HANDLE, lambda: [
                it for t in error_targets for it in self.block(t, active_llm_id, payload_var, visited)])
            normal = self._branch(node_id, gt.OK_BRANCH_KEY, lambda: [
                it for call in body.downstream if call.target_id in normal_targets
                for it in self.block(call.target_id, call.active_llm_id, call.prev_res_var, visited)])
            items.append(ErrorSplit(node_id, body_item, on_error, normal))
            self.gate.flush_ready(
                lambda join_id, vis: items.extend(self.block(join_id, None, None, vis, _as_join=True)))
            return items
        items.append(body_item)
        for call in body.downstream:
            items.extend(self.block(call.target_id, call.active_llm_id, call.prev_res_var, visited))
        return items

    def _branch(self, owner_id: str, key: str, build):
        self.gate.begin_branch(owner_id, key)
        try:
            return build()
        finally:
            self.gate.end_branch()

    # ── 흐름 노드 6종 — 생성기와 같은 구조, 같은 곧은 줄 ───────────────────
    def _flow(self, node_type, node_id, node, active_llm_id, prev_res_var, visited):
        if node_type == 'conditionNode':
            return self._condition(node_id, node, active_llm_id, prev_res_var, visited)
        if node_type == 'humanApprovalNode':
            return self._approval(node_id, node, active_llm_id, prev_res_var, visited)
        if node_type == 'loopNode':
            return self._loop(node_id, node, active_llm_id, prev_res_var, visited)
        if node_type == 'distributorNode':
            return self._distributor(node_id, node, active_llm_id, prev_res_var, visited)
        if node_type == 'outputNode':
            lines: List[str] = []
            _ui.emit_output_body(lines, node_id, node, "", prev_res_var)
            return Output(node_id, Exec(node_id, "\n".join(lines)))
        if node_type == 'breakNode':
            lines = []
            _flow.emit_break_body(lines, node_id, node, "")
            return Break(node_id, Exec(node_id, "\n".join(lines)))
        raise PlanError(f"흐름 노드 구현이 없다: {node_type}")  # pragma: no cover — NATIVE_FLOW_TYPES 와 어긋난 경우

    def _condition(self, node_id, node, active_llm_id, prev_res_var, visited) -> Cond:
        rules = node.get('data', {}).get('rules', [])
        var = prev_res_var if prev_res_var else 'last_result'
        header: List[str] = []
        _flow.emit_condition_header(header, node_id, node, "", var)
        edge_by_handle = _flow.condition_branch_targets(node_id, self.forward)

        def branch(handle):
            target_id = edge_by_handle.get(handle)
            if target_id is None:
                return []
            self.gate.begin_branch(node_id, handle)
            try:
                return self.block(target_id, active_llm_id, prev_res_var, visited)
            finally:
                self.gate.end_branch()

        cases: List[Tuple[str, List]] = []
        for rule in rules:
            expr = _flow.condition_expr(var, rule.get('operator', 'Contains'), rule.get('value', ''))
            cases.append((expr, branch(rule.get("id"))))
        otherwise = branch("else")
        return Cond(node_id, Exec(node_id, "\n".join(header), kind="header", node_type=node['type']), cases, otherwise)

    def _loop(self, node_id, node, active_llm_id, prev_res_var, visited) -> Loop:
        max_iter = node.get('data', {}).get('maxIterations', 5)
        acc_var = f"loop_acc_{node_id}"
        header: List[str] = []
        _flow.emit_loop_header(header, node_id, "", acc_var, prev_res_var)
        entry = _flow.loop_body_entry(node_id, self.node_dict, self.forward)
        body = self.block(entry, active_llm_id, acc_var, visited) if entry is not None else None
        tail: List[str] = []
        _flow.emit_loop_tail(tail, node_id, node, "", acc_var)
        done = _flow.done_target(node_id, self.forward)
        done_items = self.block(done, active_llm_id, acc_var, visited) if done is not None else []
        return Loop(node_id, Exec(node_id, "\n".join(header), kind="header", node_type=node['type']), f"int({max_iter})",
                    acc_var, body, Exec(node_id, "\n".join(tail), kind="tail", node_type=node['type']), done_items)

    def _distributor(self, node_id, node, active_llm_id, prev_res_var, visited) -> Distribute:
        acc_var = f"dist_acc_{node_id}"
        joined_var = f"dist_joined_{node_id}"
        item_var = f"dist_item_{node_id}"
        header: List[str] = []
        _flow.emit_distributor_header(header, node_id, "", prev_res_var, acc_var)
        body_items: List = []
        for target_id, _handle in _flow.distributor_body_targets(node_id, self.forward):
            body_items.extend(self.block(target_id, active_llm_id, item_var, visited))
        tail: List[str] = []
        _flow.emit_distributor_tail(tail, node_id, node, "", acc_var, joined_var)
        done = _flow.done_target(node_id, self.forward)
        done_items = self.block(done, active_llm_id, joined_var, visited) if done is not None else []
        return Distribute(node_id, Exec(node_id, "\n".join(header), kind="header", node_type=node['type']),
                          f"dist_list_{node_id}", item_var, acc_var, body_items,
                          Exec(node_id, "\n".join(tail), kind="tail", node_type=node['type']), done_items)

    def _approval(self, node_id, node, active_llm_id, prev_res_var, visited) -> Approval:
        header: List[str] = []
        _ui.emit_approval_header(header, node_id, node, "", prev_res_var)
        approved_edges, rejected_edges, plain_edges = _ui.approval_targets(node_id, self.forward)
        has_handles = bool(approved_edges or rejected_edges)
        approved_items: List = []
        rejected_items: Optional[List] = None
        plain_items: List = []
        if has_handles:
            approve_targets = approved_edges + plain_edges
            if approve_targets:
                self.gate.begin_branch(node_id, 'approved')
                try:
                    for target_id in approve_targets:
                        approved_items.extend(self.block(target_id, active_llm_id, 'last_result', visited))
                finally:
                    self.gate.end_branch()
            if rejected_edges:
                rejected_items = []
                self.gate.begin_branch(node_id, 'rejected')
                try:
                    for target_id in rejected_edges:
                        rejected_items.extend(self.block(target_id, active_llm_id, 'last_result', visited))
                finally:
                    self.gate.end_branch()
        else:
            for target_id in plain_edges:
                plain_items.extend(self.block(target_id, active_llm_id, 'last_result', visited))
        return Approval(node_id, Exec(node_id, "\n".join(header), kind="header", node_type=node['type']),
                        f"approval_{node_id}", has_handles, approved_items, rejected_items, plain_items)


# ── 실행 ───────────────────────────────────────────────────────────────────
# exec/eval 에 대해: 여기서 실행·평가하는 문자열은 옛 엔진이 생성 소스에 그대로 박아 exec 하던 것과 **같은
# 텍스트**다(노드 본문·판정식·range(int(...)) 식). run_workflow 는 그 생성 소스 전체를 validate_compiled_workflow
# (AST 금지 이름·호출 검사)에 통과시킨 뒤에만 어느 엔진이든 실행한다 — 인터프리터가 새 실행 표면을 여는 것이
# 아니라 같은 표면을 노드 단위로 나눠 실행하는 것이다. 사용자 코드(pythonNode)는 여전히 자식 프로세스 격리다.
class _Executor:
    """계획을 네임스페이스 위에서 실행한다. run_item 이 유일한 개입 지점이다 — 노드별 재시도·타임아웃·
    단계 기록(ENGINE-1·3)은 여기에 얹는다."""

    STARTING_KINDS = ("body", "pinned", "header")

    def __init__(self, namespace: Dict[str, Any], observer=None):
        self.ns = namespace
        # run_events.RunObserver 또는 None — node_started 만 여기서 낸다(node_finished 는 log_step 래퍼가 낸다).
        self.observer = observer

    def run_items(self, items: List) -> None:
        for item in items:
            self.run_item(item)

    def _started(self, node_id: str, node_type: Optional[str]) -> None:
        if self.observer is not None:
            try:
                self.observer.node_started(node_id, node_type)
            except Exception:  # 이벤트는 부수 기능 — 실행을 막지 않는다
                pass

    def _run_header(self, item) -> None:
        # 흐름 노드의 머리(Exec kind=header)는 run_item 을 거치지 않으므로 여기서 시작 이벤트를 낸다.
        self._started(item.node_id, item.header.node_type)
        exec(item.header.code(), self.ns)

    def run_item(self, item) -> None:
        if isinstance(item, Exec):
            if item.kind in self.STARTING_KINDS:
                self._started(item.node_id, item.node_type)
            if item.retry is not None and item.kind == "body":
                self._run_with_retry(item)
            else:
                exec(item.code(), self.ns)
        elif isinstance(item, Cond):
            self._condition(item)
        elif isinstance(item, Loop):
            self._loop(item)
        elif isinstance(item, Distribute):
            self._distribute(item)
        elif isinstance(item, Approval):
            self._approval(item)
        elif isinstance(item, Output):
            self._started(item.node_id, item.node_type)
            exec(item.body.code(), self.ns)
            raise ReturnSignal(self.ns['last_result'])
        elif isinstance(item, Break):
            self._started(item.node_id, item.node_type)
            exec(item.body.code(), self.ns)
            raise BreakSignal()
        elif isinstance(item, ErrorSplit):
            self._error_split(item)
        else:  # pragma: no cover
            raise PlanError(f"모르는 계획 항목: {type(item).__name__}")

    def _run_with_retry(self, item: Exec) -> None:
        """노드 본문을 최대 max_attempts 번 exec 한다 — 이것이 ENGINE-3 재시도의 전부다(ADR-0030).

        재시도 여부는 본문이 남긴 log_step 기록의 오류(retryable·effectState)에서 읽는다(node_retry.retryable_failure). 실패한
        시도의 기록은 접고 최종 기록에 attempts·retried 를 붙인다. 시도 사이에 __node_meta__ 의 이 노드 항목을 지운다 — 남겨 두면
        log_step 이 성공한 재시도를 이전 시도의 error 메타로 다시 error 로 적는다.
        """
        logs = self.ns['__execution_logs__']
        retried: List[Dict[str, Any]] = []
        since = len(logs)
        for attempt in range(item.retry.max_attempts):
            exec(item.code(), self.ns)
            failure = node_retry.retryable_failure(logs, since, item.node_id)
            if failure is None or attempt + 1 >= item.retry.max_attempts:
                node_retry.annotate_final(logs, since, item.node_id, attempt + 1, retried)
                return
            node_retry.fold_attempt(logs, since, attempt, failure, retried)
            meta = self.ns.get('__node_meta__')
            if isinstance(meta, dict):
                meta.pop(item.node_id, None)
            delay = node_retry.backoff_delay(item.retry, attempt, failure)
            self._retry_event(item, attempt + 1, failure.get('code'), delay)
            node_retry.sleep(delay)

    def _retry_event(self, item: Exec, attempt: int, error_code: Optional[str], delay: float) -> None:
        observer = self.observer
        if observer is None or not hasattr(observer, 'node_retry'):
            return
        try:
            observer.node_retry(item.node_id, item.node_type, attempt=attempt, max_attempts=item.retry.max_attempts,
                                error_code=error_code, delay_sec=delay)
        except Exception:  # 이벤트는 부수 기능 — 재시도를 막지 않는다
            pass

    def _error_split(self, item: ErrorSplit) -> None:
        """본문(재시도 포함)을 돌린 뒤 log_step 메타로 실패를 판정한다 — 옛 엔진의 `if _node_failed(...)` 와 같은 헬퍼를 쓴다."""
        self.run_item(item.body)
        if self.ns['_node_failed'](item.node_id):
            payload = self.ns['_node_error_payload'](item.node_id)
            self.ns[gt.error_payload_var(item.node_id)] = payload   # 옛 엔진의 방출과 같은 변수 — 형제 복원이 덮지 못한다
            self.ns['last_result'] = payload
            self.run_items(item.on_error)
        else:
            self.run_items(item.normal)

    def _condition(self, item: Cond) -> None:
        self._run_header(item)
        for (expr, branch), code in zip(item.cases, item.compiled_cases()):
            if eval(code, self.ns):
                self.run_items(branch)
                return
        self.run_items(item.otherwise)

    def _loop(self, item: Loop) -> None:
        self._run_header(item)
        count = eval(item.count_expr, self.ns)
        for idx in range(count):
            self.ns[f"_loop_idx_{item.node_id}"] = idx
            if item.body is None:
                continue
            try:
                self.run_items(item.body)
            except BreakSignal:
                break
            self.ns[item.acc_var] = self.ns['last_result']
        exec(item.tail.code(), self.ns)
        self.run_items(item.done)

    def _distribute(self, item: Distribute) -> None:
        self._run_header(item)
        acc = self.ns[item.acc_var]
        for value in self.ns[item.list_var]:
            self.ns[item.item_var] = value
            self.ns['last_result'] = value
            try:
                self.run_items(item.body)
            except BreakSignal:
                break
            acc.append(self.ns['last_result'])
        exec(item.tail.code(), self.ns)
        self.run_items(item.done)

    def _approval(self, item: Approval) -> None:
        self._run_header(item)  # 결정이 없으면 여기서 __ApprovalPendingSignal__ 이 올라간다
        approved = _ui.is_approved(self.ns[item.decision_var])
        if item.has_handles:
            if approved:
                self.run_items(item.approved)
            elif item.rejected is not None:
                self.run_items(item.rejected)
            else:
                raise Exception(REJECTED_MESSAGE)
        else:
            if not approved:
                raise Exception(REJECTED_MESSAGE)
            self.run_items(item.plain)


def _compile_all(items: List) -> None:
    """본문을 실행 전에 전부 컴파일한다 — 문법 오류가 있으면 루트 안 'Flow Error' 가 아니라 옛 엔진처럼
    실행 바깥(Dynamic Execution Error)으로 드러나야 한다."""
    for item in items:
        if isinstance(item, Exec):
            item.code()
        elif isinstance(item, Cond):
            item.header.code()
            item.compiled_cases()
            for _expr, branch in item.cases:
                _compile_all(branch)
            _compile_all(item.otherwise)
        elif isinstance(item, Loop):
            item.header.code()
            item.tail.code()
            _compile_all(item.body or [])
            _compile_all(item.done)
        elif isinstance(item, Distribute):
            item.header.code()
            item.tail.code()
            _compile_all(item.body)
            _compile_all(item.done)
        elif isinstance(item, Approval):
            item.header.code()
            _compile_all(item.approved)
            _compile_all(item.rejected or [])
            _compile_all(item.plain)
        elif isinstance(item, (Output, Break)):
            item.body.code()
        elif isinstance(item, ErrorSplit):
            item.body.code()
            _compile_all(item.on_error)
            _compile_all(item.normal)


def execute(plan: Plan, namespace: Dict[str, Any], runtime_inputs: Dict[str, Any], observer=None) -> Any:
    """계획을 실행하고 결과 값을 돌려준다. 토큰·로그는 옛 엔진과 같은 이름으로 namespace 에 남는다
    (__token_usage__·__execution_logs__) — 호출자(graph.run_workflow)가 거기서 읽는다.
    observer(run_events.RunObserver)가 있으면 프렐류드의 log_step 을 감싸 node_finished 를, 실행기가 node_started 를 낸다."""
    import graph

    lines: List[str] = []
    graph.emit_module_prelude(lines, plan.nodes, plan.project_id, error_branches=plan.error_branches)
    exec(compile("\n".join(lines), "<workflow prelude>", "exec"), namespace)
    llm_lines: List[str] = []
    graph.emit_llm_setup(llm_lines, plan.nodes, plan.project_id, indent="")
    if llm_lines:
        exec(compile("\n".join(llm_lines), "<workflow llm setup>", "exec"), namespace)
    namespace['kwargs'] = runtime_inputs
    if observer is not None:
        import run_events
        run_events.attach_step_observer(namespace, observer)
    for root in plan.roots:
        _compile_all(root.items)

    executor = _Executor(namespace, observer)
    signal_cls = namespace.get('__ApprovalPendingSignal__')
    global_results: List[str] = []
    many = len(plan.roots) > 1
    for idx, root in enumerate(plan.roots):
        if plan.entry_node_id is not None:
            # 승인 재개: 중단 시점에 승인자가 본 payload 가 직전 노드 출력 자리에 들어간다.
            namespace['last_result'] = runtime_inputs.get('__approval_payload__', '')
        else:
            namespace['last_result'] = 'No execution occurred.'
        flow_start = datetime.datetime.utcnow().isoformat()
        try:
            try:
                executor.run_items(root.items)
                res = namespace['last_result']
            except ReturnSignal as ret:
                res = ret.value
            global_results.append(f'► Flow {idx + 1} Result:\n{str(res)}' if many else str(res))
        except Exception as e:
            if signal_cls is not None and isinstance(e, signal_cls):
                raise
            # 노드가 잡지 못한 예외 — 실행 엔진 수준 실패로 구조화해 남긴다(node_type='workflow', ADR-0016).
            global_results.append(f'► Flow {idx + 1} Error: {str(e)}')
            namespace['log_step'](f'flow-{idx}', 'workflow', flow_start,
                                  error=namespace['_node_error_from_exception'](e, node_type='workflow', node_id=f'flow-{idx}'))

    handler = namespace.get('langfuse_handler')
    if handler and hasattr(handler, '_langfuse_client'):
        handler._langfuse_client.flush()
    if many:
        return '\n\n' + ('=' * 40) + '\n\n'.join(global_results)
    return global_results[0] if global_results else 'No result'


def run(nodes: list, edges: list, *, namespace: Dict[str, Any], runtime_inputs: Dict[str, Any], project_id=None,
        entry_node_id=None, stop_node_id=None, scope_node_ids=None, pinned_outputs=None, observer=None) -> Any:
    """graph.run_workflow 가 exec 대신 부르는 진입점. 인자 의미는 compile_workflow 와 같다."""
    plan = build_plan(nodes, edges, project_id=project_id, entry_node_id=entry_node_id, stop_node_id=stop_node_id,
                      scope_node_ids=scope_node_ids, pinned_outputs=pinned_outputs)
    return execute(plan, namespace, runtime_inputs, observer=observer)
