from __future__ import annotations

import ast
import re


MAX_WORKFLOW_NODES = 200
MAX_PYTHON_NODE_CODE_BYTES = 8 * 1024
SAFE_NODE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ── 자원 상한: 눈에 보이는 폭탄만 막는 앞단 필터 (§4.15 PYEXEC-0) ──────────
#
# ⚠️ 이것은 방어선이 아니다. 허용 목록은 코드가 **무엇에 닿는지**를 통제하지 **얼마나 쓰는지**를
# 보지 않는다. 여기서는 상수로 적힌 폭탄(`10 ** 10 ** 10`, `'x' * 10**9`)만 잡는다 —
# `n = 10 ** 5` 뒤의 `n ** n` 처럼 계산된 값은 정적으로 알 수 없다.
# **진짜 방어선은 python_runtime.run_isolated 의 프로세스 격리와 rlimit 이다**(PYEXEC-1).
# 이 사실을 모르고 여기 규칙만 늘리면 막았다고 착각하게 된다.
MAX_POW_EXPONENT = 64
MAX_REPEAT_COUNT = 1_000_000
MAX_RANGE_SPAN = 1_000_000
MAX_STATIC_ITERATIONS = 10_000_000

SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "chr", "dict", "enumerate", "filter", "float",
    "int", "len", "list", "map", "max", "min", "range", "reversed", "round",
    "set", "sorted", "str", "sum", "tuple", "zip",
}
SAFE_METHODS = {
    "append", "capitalize", "casefold", "count", "endswith", "extend", "find", "get",
    "index", "insert", "items", "join", "keys", "lower", "lstrip", "pop", "remove",
    "replace", "reverse", "rstrip", "setdefault", "sort", "split", "splitlines",
    "startswith", "strip", "title", "upper", "values",
}
SAFE_AST_NODES = {
    ast.Module, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.If, ast.For,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.Name, ast.Load, ast.Store, ast.Del, ast.Constant, ast.List, ast.Tuple, ast.Set,
    ast.Dict, ast.Subscript, ast.Slice, ast.Attribute, ast.Call, ast.keyword,
    ast.JoinedStr, ast.FormattedValue,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Pass, ast.Break, ast.Continue,
}


class WorkflowSecurityError(ValueError):
    pass


def _const_int(node: ast.AST) -> int | None:
    """상수만으로 이뤄진 정수 식의 값. 알 수 없으면 None.

    `10 ** 10 ** 10` 을 잡으려면 안쪽 `10 ** 10` 을 계산해야 하는데, 그 계산 자체가 폭탄이면
    안 된다. 그래서 거듭제곱은 **지수를 먼저 보고** 한도를 넘으면 계산하지 않고 포기한다.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, int) and not isinstance(node.value, bool) else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _const_int(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp):
        left, right = _const_int(node.left), _const_int(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                # 계산 전에 크기를 본다 — 곱셈 결과가 상한을 넘으면 값이 필요하지 않다.
                if abs(left) > MAX_STATIC_ITERATIONS or abs(right) > MAX_STATIC_ITERATIONS:
                    return None
                return left * right
            if isinstance(node.op, ast.Pow):
                if right < 0 or right > MAX_POW_EXPONENT or abs(left) > MAX_REPEAT_COUNT:
                    return None
                return left ** right
        except (ArithmeticError, ValueError):
            return None
    return None


def _is_numeric_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _static_iterations(node: ast.For) -> int | None:
    """`for x in range(<상수>)` 의 반복 횟수. 상수가 아니면 None(데이터 크기에 달렸다는 뜻)."""
    call = node.iter
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "range"):
        return None
    args = [_const_int(a) for a in call.args]
    if not args or any(a is None for a in args):
        return None
    if len(args) == 1:
        return max(0, args[0])
    start, stop = args[0], args[1]
    step = args[2] if len(args) > 2 else 1
    if step == 0:
        return None
    return max(0, -(-(stop - start) // step))


def _check_resource_bombs(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # 지수를 상수로 알 수 없으면(_const_int 가 None) 여기서는 막지 못한다 —
            # 그 경우는 실행 격리가 받는다. 상수로 명백히 큰 것만 거른다.
            exponent = _const_int(node.right)
            if exponent is not None and exponent > MAX_POW_EXPONENT:
                raise WorkflowSecurityError(
                    f"pythonNode exponent {exponent} exceeds the {MAX_POW_EXPONENT} limit"
                )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for side, other in ((node.left, node.right), (node.right, node.left)):
                count = _const_int(side)
                # 숫자 × 숫자는 그냥 산술이다. 반복 폭탄은 한쪽이 시퀀스일 때 생긴다.
                if count is not None and count > MAX_REPEAT_COUNT and not _is_numeric_constant(other):
                    raise WorkflowSecurityError(
                        f"pythonNode repeat count {count} exceeds the {MAX_REPEAT_COUNT} limit"
                    )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
            for arg in node.args:
                value = _const_int(arg)
                if value is not None and abs(value) > MAX_RANGE_SPAN:
                    raise WorkflowSecurityError(
                        f"pythonNode range bound {value} exceeds the {MAX_RANGE_SPAN} limit"
                    )

    # 중첩 반복은 깊이가 아니라 **곱**이 문제다. 상수 범위끼리 곱해 상한을 넘으면 거른다.
    def walk_loops(node: ast.AST, product: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.For):
                count = _static_iterations(child)
                nested = product * count if count is not None else product
                if count is not None and nested > MAX_STATIC_ITERATIONS:
                    raise WorkflowSecurityError(
                        f"pythonNode loop runs {nested} times, over the {MAX_STATIC_ITERATIONS} limit"
                    )
                walk_loops(child, nested)
            else:
                walk_loops(child, product)

    walk_loops(tree, 1)


def _assigned_names(tree: ast.AST) -> set[str]:
    names = {"input_data", "output_data"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
    return names


def validate_python_node_code(code: str) -> None:
    if len(code.encode("utf-8")) > MAX_PYTHON_NODE_CODE_BYTES:
        raise WorkflowSecurityError("pythonNode code exceeds the 8 KB limit")
    try:
        tree = ast.parse(code or "", mode="exec")
    except SyntaxError as exc:
        raise WorkflowSecurityError(f"pythonNode contains invalid syntax at line {exc.lineno}") from exc

    local_names = _assigned_names(tree)
    for node in ast.walk(tree):
        if type(node) not in SAFE_AST_NODES:
            raise WorkflowSecurityError(f"pythonNode syntax {type(node).__name__} is not allowed")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise WorkflowSecurityError("pythonNode cannot access private or dunder names")
            if isinstance(node.ctx, ast.Load) and node.id not in local_names | SAFE_BUILTINS:
                raise WorkflowSecurityError(f"pythonNode name {node.id!r} is not allowed")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr not in SAFE_METHODS:
                raise WorkflowSecurityError(f"pythonNode attribute {node.attr!r} is not allowed")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in SAFE_BUILTINS:
                raise WorkflowSecurityError(f"pythonNode call {node.func.id!r} is not allowed")
            if isinstance(node.func, ast.Attribute) and node.func.attr not in SAFE_METHODS:
                raise WorkflowSecurityError(f"pythonNode method {node.func.attr!r} is not allowed")

    _check_resource_bombs(tree)


def validate_workflow_graph(nodes: list, edges: list) -> None:
    if len(nodes) > MAX_WORKFLOW_NODES:
        raise WorkflowSecurityError(f"workflow exceeds the {MAX_WORKFLOW_NODES}-node limit")

    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise WorkflowSecurityError("every workflow node must be an object")
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not SAFE_NODE_ID.fullmatch(node_id):
            raise WorkflowSecurityError(f"unsafe node id: {node_id!r}")
        if node_id in node_ids:
            raise WorkflowSecurityError(f"duplicate node id: {node_id}")
        if not isinstance(node_type, str) or not SAFE_NODE_ID.fullmatch(node_type):
            raise WorkflowSecurityError(f"unsafe node type: {node_type!r}")
        node_ids.add(node_id)
        if node_type == "pythonNode":
            validate_python_node_code(str((node.get("data") or {}).get("code", "")))

    for edge in edges:
        if not isinstance(edge, dict):
            raise WorkflowSecurityError("every workflow edge must be an object")
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise WorkflowSecurityError("workflow edge references an unknown node")


def validate_compiled_workflow(source: str) -> None:
    """Reject high-impact primitives if malformed graph data injects extra source code."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise WorkflowSecurityError(f"generated workflow is invalid at line {exc.lineno}") from exc

    forbidden_names = {"eval", "exec", "compile", "__import__", "globals", "locals", "breakpoint"}
    forbidden_calls = {
        ("os", "system"), ("os", "popen"), ("os", "fork"), ("os", "kill"),
        ("subprocess", "Popen"), ("subprocess", "call"), ("subprocess", "check_call"),
        ("subprocess", "check_output"),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            raise WorkflowSecurityError(f"generated workflow uses forbidden name {node.id!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise WorkflowSecurityError("generated workflow accesses a dunder attribute")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and (owner.id, node.func.attr) in forbidden_calls:
                raise WorkflowSecurityError(f"generated workflow call {owner.id}.{node.func.attr} is forbidden")
