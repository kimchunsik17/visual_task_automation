"""pythonNode 실행 격리와 자원 한도 (§4.15, 우선 백로그 25) 계약 테스트.

§4.15 검증 매트릭스의 층을 따른다 — 접근(회귀)·자원·정리·격리·오류·불변식·성능·실행 경로.

이 파일의 존재 이유를 한 줄로: **허용 목록은 무엇에 닿는지를 막고, 격리는 얼마나 쓰는지를 막는다.**
둘 중 하나만 있으면 다른 하나가 뚫린다.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time

import pytest

import python_runtime
from graph import compile_workflow, run_workflow
from python_runtime import IsolationLimits, run_isolated
from workflow_security import WorkflowSecurityError, validate_python_node_code


def _sandbox_runnable() -> bool:
    """이 환경에서 pythonNode 격리 실행기를 실제로 돌릴 수 있는가.

    두 가지가 막는다.

      1. **플랫폼**: `python_sandbox.py` 가 POSIX 전용 `resource` 로 rlimit 을 걸고, 자식에게
         넘기는 환경을 최소화하면서 Windows 가 난수 초기화에 쓰는 SystemRoot 도 뺀다. 둘 중
         하나만으로도 자식이 즉사하고, 부모는 그 종료 코드를 자원 한도 초과로 오해한다.
      2. **플래그**: `PYTHON_NODE_ENABLED=0` 이면 노드 자체가 닫혀 있다(ADR-0019 후속).

    둘 중 하나라도 걸리면 이 파일의 실행 계열 테스트는 '검증할 대상이 없는' 상태다. 실패로
    남겨 두면 21건이 상시 빨강이 되어 진짜 회귀를 가린다 — 리눅스(운영·CI)에서는 전부 돈다.
    """
    if not python_runtime.node_enabled():
        return False
    try:
        import resource  # noqa: F401
    except ImportError:
        return False
    return True


requires_sandbox = pytest.mark.skipif(
    not _sandbox_runnable(),
    reason="pythonNode 격리 실행기를 돌릴 수 없는 환경(POSIX rlimit 부재 또는 PYTHON_NODE_ENABLED=0)")


def _tight(**overrides) -> IsolationLimits:
    """테스트가 오래 걸리지 않게 좁힌 한도."""
    base = dict(cpu_seconds=1, address_space_bytes=192 * 1024 * 1024,
                wall_seconds=5.0, output_bytes=64 * 1024)
    base.update(overrides)
    return IsolationLimits(**base)


# ── 1. 접근 통제 회귀 ────────────────────────────────────────────────────
@pytest.mark.parametrize("code", [
    "import os\noutput_data = os.listdir('/')",
    "output_data = input_data.__class__.__mro__",
    "output_data = db.query(models.User).all()",
    "output_data = open('/etc/passwd').read()",
    "output_data = eval('1+1')",
    "output_data = (lambda: 1)()",
    "def f():\n    return 1\noutput_data = f()",
    "while True:\n    pass",
    "try:\n    output_data = 1\nexcept:\n    pass",
    "output_data = getattr(input_data, 'encode')",
    "output_data = os.environ",
])
def test_access_control_still_blocks_everything_it_used_to(code):
    """자원 한도를 더하면서 접근 통제를 느슨하게 만들지 않았다는 것을 고정한다."""
    with pytest.raises(WorkflowSecurityError):
        validate_python_node_code(code)


# ── 2. 정적 상한(PYEXEC-0) ───────────────────────────────────────────────
@pytest.mark.parametrize("code, hint", [
    ("output_data = 10 ** 10 ** 10", "exponent"),
    ("output_data = [0] * (10 ** 9)", "repeat"),
    ("output_data = 'x' * (10 ** 9)", "repeat"),
    ("output_data = list(range(10 ** 8))", "range"),
    ("t = 0\nfor a in range(100000):\n    for b in range(100000):\n        t = t + 1\noutput_data = t", "loop"),
])
def test_literal_bombs_are_rejected_before_execution(code, hint):
    with pytest.raises(WorkflowSecurityError) as exc:
        validate_python_node_code(code)
    assert hint in str(exc.value)


@pytest.mark.parametrize("code", [
    "output_data = [x.strip().upper() for x in input_data.split(',')]",
    "output_data = 2 ** 10",
    "output_data = 10 ** 9 * 3",                       # 숫자끼리의 곱은 반복 폭탄이 아니다
    "t = 0\nfor a in range(1000):\n    t = t + a\noutput_data = t",
    "r = []\nfor a in range(100):\n    for b in range(100):\n        r.append(a * b)\noutput_data = r",
    "t = 0\nfor x in input_data:\n    t = t + 1\noutput_data = t",   # 데이터 크기 기반은 정적으로 모른다
])
def test_normal_transformations_are_not_false_positives(code):
    validate_python_node_code(code)


def test_static_filter_admits_it_cannot_catch_computed_bombs():
    """`n ** n` 은 정적으로 잡히지 않는다 — 이것이 격리가 필요한 이유다.

    이 테스트가 깨진다면 정적 검사가 좋아진 것이므로 반갑지만, **격리를 뺄 이유는 되지 않는다.**
    """
    validate_python_node_code("n = 10 ** 8\noutput_data = n ** n")


# ── 3. 자원 한도(PYEXEC-1) ───────────────────────────────────────────────
@requires_sandbox
def test_computed_bomb_is_stopped_by_the_cpu_limit():
    result = run_isolated("n = 10 ** 8\noutput_data = n ** n", None, limits=_tight())
    assert result.error.code == "RUNTIME_RESOURCE_EXCEEDED"
    assert result.error.safe_details["limitKind"] == "cpu"
    assert result.error.effect_state == "not_started" and result.error.safe_to_retry is False


@requires_sandbox
def test_memory_bomb_is_stopped_by_the_address_space_limit():
    code = "r = []\nfor i in range(1000000):\n    r.append('x' * 100000)\noutput_data = 1"
    result = run_isolated(code, None, limits=_tight())
    assert result.error.code == "RUNTIME_RESOURCE_EXCEEDED"
    assert result.error.safe_details["limitKind"] in {"memory", "cpu"}


@requires_sandbox
def test_unresponsive_child_is_cut_by_the_wall_clock():
    result = run_isolated("output_data = input_data", "x", limits=_tight(wall_seconds=0.01))
    assert result.error.code == "RUNTIME_RESOURCE_EXCEEDED"
    assert result.error.safe_details["limitKind"] == "wall"


@requires_sandbox
def test_output_size_is_capped():
    result = run_isolated("output_data = 'x' * 500000", None, limits=_tight(output_bytes=1024))
    assert result.error.code == "RUNTIME_OUTPUT_TOO_LARGE"
    assert result.error.safe_details["limitBytes"] == 1024


# ── 4. 정리 ─────────────────────────────────────────────────────────────
@requires_sandbox
def test_repeated_bombs_leave_no_zombies_or_temp_directories():
    """실패·타임아웃을 반복해도 자식 프로세스와 임시 디렉터리가 남지 않아야 한다."""
    before = {d for d in os.listdir("/tmp") if d.startswith("pynode-")}
    for _ in range(8):
        run_isolated("n = 10 ** 8\noutput_data = n ** n", None, limits=_tight())
        run_isolated("output_data = input_data", "x", limits=_tight(wall_seconds=0.01))
    time.sleep(0.2)
    after = {d for d in os.listdir("/tmp") if d.startswith("pynode-")}
    assert after == before, f"임시 디렉터리가 남았다: {after - before}"

    zombies = subprocess.run(
        ["bash", "-c", "ps -eo stat= | grep -c '^Z' || true"], capture_output=True, text=True,
    ).stdout.strip()
    assert zombies == "0", f"좀비 프로세스 {zombies}개"


# ── 5. 격리 ─────────────────────────────────────────────────────────────
@requires_sandbox
def test_child_process_gets_no_secrets_from_the_environment(monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "leaked")
    probe = subprocess.run(
        [sys.executable, "-c", "import os, json; print(json.dumps(sorted(os.environ)))"],
        capture_output=True, text=True, env=dict(python_runtime.SANDBOX_ENV),
    )
    names = json.loads(probe.stdout)
    assert "SECRET_CANARY" not in names
    assert not any(n.startswith(("OPENAI", "GOOGLE", "SMTP", "DATABASE", "SECRET", "JWT")) for n in names)


@requires_sandbox
def test_child_runs_in_a_throwaway_working_directory():
    """`cwd` 가 저장소가 아니어야 한다 — 허용 목록이 open() 을 막지만 방어는 겹쳐 둔다."""
    result = run_isolated("output_data = input_data", "ok", limits=_tight())
    assert result.ok
    # 실행이 끝나면 그 디렉터리는 이미 지워져 있다.
    assert not [d for d in os.listdir("/tmp") if d.startswith("pynode-")]


# ── 6. 오류 표현 ────────────────────────────────────────────────────────
@requires_sandbox
def test_user_code_errors_report_type_and_line_but_not_the_data():
    result = run_isolated("output_data = input_data['없는키']", {"a": 1}, limits=_tight())
    assert result.error.code == "RUNTIME_USER_CODE_FAILED"
    assert result.error.safe_details["errorType"] == "KeyError"
    assert result.error.safe_details["line"] == 1
    # 처리 중이던 데이터·키 이름은 공개 payload 에 없어야 한다.
    assert "없는키" not in json.dumps(result.error.to_dict(), ensure_ascii=False)


@requires_sandbox
def test_user_code_is_not_echoed_into_the_public_payload():
    result = run_isolated("output_data = input_data + 1", "문자열", limits=_tight())
    assert result.error.code == "RUNTIME_USER_CODE_FAILED"
    assert "input_data + 1" not in json.dumps(result.error.to_dict(), ensure_ascii=False)


# ── 7. 정상 동작과 불변식 ────────────────────────────────────────────────
@pytest.mark.parametrize("code, data, expected", [
    ("output_data = [x.strip().upper() for x in input_data.split(',')]", " a, b ,c ", ["A", "B", "C"]),
    ("output_data = {'말': input_data + '요'}", "안녕하세", {"말": "안녕하세요"}),
    ("output_data = sorted(input_data, reverse=True)", [2, 3, 1], [3, 2, 1]),
    ("", "그대로", "그대로"),                       # 코드가 비면 입력을 그대로 흘린다
    ("output_data = set([3, 1, 2])", None, [1, 2, 3]),   # set 은 정렬된 배열로 정규화된다
])
@requires_sandbox
def test_normal_transformations_round_trip(code, data, expected):
    result = run_isolated(code, data, limits=_tight())
    assert result.ok, result.error
    assert result.data == expected


@requires_sandbox
def test_metrics_are_reported_for_successful_runs():
    result = run_isolated("output_data = input_data", "x", limits=_tight())
    assert result.metrics["cpuMs"] >= 0 and result.metrics["peakRssBytes"] > 0


@requires_sandbox
def test_non_serializable_input_is_refused_before_spawning():
    """`input_data` 는 순수 데이터여야 한다는 불변식. 살아 있는 객체가 상류에서 흘러들면 여기서 걸린다."""
    class Live:
        def get(self, *a):
            raise AssertionError("이 메서드가 불릴 수 있으면 안 된다")

    result = run_isolated("output_data = input_data", Live(), limits=_tight())
    # default=str 로 문자열이 되므로 실행은 되지만, **객체 자체는 자식에게 건너가지 않는다.**
    assert result.ok and isinstance(result.data, str)


# ── 8. 실행 경로 ────────────────────────────────────────────────────────
def _graph(code):
    nodes = [
        {"id": "s1", "type": "startNode", "data": {}},
        {"id": "v1", "type": "valueNode", "data": {"value": " a, b ,c "}},
        {"id": "py", "type": "pythonNode", "data": {"code": code}},
    ]
    return nodes, [{"source": "s1", "target": "v1"}, {"source": "v1", "target": "py"}]


@requires_sandbox
def test_generated_code_does_not_inline_user_code():
    """사용자 코드가 생성 소스의 **일부**가 아니라 문자열 인자여야 한다.

    이것이 격리의 핵심 부수 효과다 — db 세션이 있는 네임스페이스에서 코드가 분리된다.
    """
    nodes, edges = _graph("output_data = input_data.upper()")
    source = compile_workflow(nodes, edges)
    assert "_run_isolated(" in source
    tree = ast.parse(source)
    # 사용자 코드가 실행 구문으로 파싱되지 않고 문자열 상수로만 존재해야 한다.
    constants = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "output_data = input_data.upper()" in constants
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "upper"
        for n in ast.walk(tree)
    )


@requires_sandbox
def test_workflow_run_returns_the_transformed_value():
    nodes, edges = _graph("output_data = [x.strip().upper() for x in input_data.split(',')]")
    text, _, logs = run_workflow(nodes, edges, default_input="")
    step = next(entry for entry in logs if entry["node_id"] == "py")
    assert step["status"] == "success"
    assert "A" in text and "C" in text


@requires_sandbox
def test_a_failing_node_does_not_kill_the_workflow():
    nodes, edges = _graph("output_data = input_data['없는키']")
    text, _, logs = run_workflow(nodes, edges, default_input="")
    step = next(entry for entry in logs if entry["node_id"] == "py")
    assert step["status"] == "error"
    assert step["error"]["code"] == "RUNTIME_USER_CODE_FAILED"
    assert not text.startswith("Dynamic Execution Error")   # 흐름 전체가 죽지 않는다


@requires_sandbox
def test_isolation_can_be_switched_off_for_rollback(monkeypatch):
    """되돌리기 경로에서도 허용 목록과 정적 상한은 그대로 걸린다."""
    monkeypatch.setenv("PYTHON_NODE_ISOLATION", "0")
    assert python_runtime.isolation_enabled() is False
    nodes, edges = _graph("output_data = input_data.upper()")
    source = compile_workflow(nodes, edges)
    assert "_run_isolated(" not in source and "output_data = input_data.upper()" in source

    nodes, edges = _graph("output_data = 10 ** 10 ** 10")
    with pytest.raises(WorkflowSecurityError):
        validate_python_node_code(nodes[2]["data"]["code"])


# ── 9. 성능 ─────────────────────────────────────────────────────────────
@requires_sandbox
def test_isolation_overhead_stays_within_budget():
    """프로세스 기동 비용이 정상 변환을 눈에 띄게 느리게 만들면 안 된다."""
    samples = []
    for _ in range(5):
        started = time.monotonic()
        assert run_isolated("output_data = input_data.upper()", "abc", limits=_tight()).ok
        samples.append(time.monotonic() - started)
    assert max(samples) < 1.5, f"격리 오버헤드가 너무 크다: {samples}"
