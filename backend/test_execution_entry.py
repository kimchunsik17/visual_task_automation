"""execution.start — 실행 단일 진입점 (백로그 32 ENGINE-0 1단계) 테스트.

계약: (1) graph.run_workflow 를 직접 부르는 곳은 graph.py 와 execution.py 뿐이다 · (2) start 는
run_workflow 와 인자·반환·예외가 같고 trigger_source 만 떼어 contextvar 에 둔다 · (3) 모르는
trigger_source 는 거부한다 · (4) 아직 없는 엔진 모드는 legacy 로 가되 경고를 남긴다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import execution

BACKEND = pathlib.Path(__file__).resolve().parent
ALLOWED_DIRECT_CALLERS = {"graph.py", "execution.py"}
SKIP_PARTS = {"venv", ".venv", "node_modules", "__pycache__", ".git", "chroma_db"}


def _backend_sources():
    for path in BACKEND.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        yield path


def _called_name(call: ast.Call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_run_workflow_is_only_called_through_execution_start():
    """호출부가 run_workflow 를 직접 부르면 ENGINE-2 에서 큐로 보낼 자리를 놓친다. 문자열(배포용 생성
    코드) 안의 run_workflow 는 AST 호출이 아니라서 걸리지 않는다 — 의도된 것."""
    offenders = []
    for path in _backend_sources():
        if path.name in ALLOWED_DIRECT_CALLERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) == "run_workflow":
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert offenders == [], "run_workflow 직접 호출 — execution.start 를 써라: " + ", ".join(offenders)


def test_every_start_call_declares_a_known_trigger_source():
    """trigger_source 는 닫힌 목록이다 — 호출부마다 다른 표기가 생기면 ENGINE-1 의 집계가 갈라진다."""
    seen = set()
    problems = []
    for path in _backend_sources():
        if path.name == "execution.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "start" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "execution"):
                continue
            where = f"{path.relative_to(BACKEND)}:{node.lineno}"
            kw = next((k for k in node.keywords if k.arg == "trigger_source"), None)
            if kw is None or not isinstance(kw.value, ast.Constant):
                problems.append(f"{where}: trigger_source 리터럴이 없다")
                continue
            if kw.value.value not in execution.TRIGGER_SOURCES:
                problems.append(f"{where}: {kw.value.value!r} 는 허용 목록 밖")
            seen.add(kw.value.value)
    assert problems == [], "\n".join(problems)
    # 실제 호출부가 이 출처들을 전부 쓰고 있어야 한다 — 하나가 빠지면 호출부를 잃어버린 것이다.
    assert {"manual", "schedule", "webhook", "bot", "app", "api", "approval", "evaluation", "mock"} <= seen


def test_start_forwards_arguments_and_exposes_trigger_source(monkeypatch):
    import graph

    captured = {}

    def fake_run_workflow(nodes, edges, **kwargs):
        captured["nodes"] = nodes
        captured["edges"] = edges
        captured["kwargs"] = kwargs
        captured["trigger_inside"] = execution.current_trigger_source()
        return "결과", {"total_tokens": 3}, [{"node_id": "x"}]

    monkeypatch.setattr(graph, "run_workflow", fake_run_workflow)
    assert execution.current_trigger_source() is None

    out = execution.start([{"id": "a"}], [{"source": "a"}], trigger_source="webhook",
                          db="DB", session_id="s", project_id=7, default_input="hi")

    assert out == ("결과", {"total_tokens": 3}, [{"node_id": "x"}])
    assert captured["nodes"] == [{"id": "a"}] and captured["edges"] == [{"source": "a"}]
    # trigger_source 는 run_workflow 로 새지 않는다 — 생성 코드의 runtime_inputs 와 섞이면 안 된다.
    assert captured["kwargs"] == {"db": "DB", "session_id": "s", "project_id": 7, "default_input": "hi"}
    assert captured["trigger_inside"] == "webhook"
    assert execution.current_trigger_source() is None  # 끝나면 원복


def test_start_propagates_exceptions_and_resets_context(monkeypatch):
    import graph

    def boom(nodes, edges, **kwargs):
        raise RuntimeError("엔진 폭발")

    monkeypatch.setattr(graph, "run_workflow", boom)
    with pytest.raises(RuntimeError, match="엔진 폭발"):
        execution.start([], [], trigger_source="manual")
    assert execution.current_trigger_source() is None


def test_unknown_trigger_source_is_rejected_before_running(monkeypatch):
    import graph

    monkeypatch.setattr(graph, "run_workflow", lambda *a, **k: pytest.fail("실행되면 안 된다"))
    with pytest.raises(ValueError, match="trigger_source"):
        execution.start([], [], trigger_source="scheduler")  # 'schedule' 의 오타


@pytest.mark.parametrize("raw, expect_warning", [
    ("", False), ("legacy", False), ("LEGACY", False),
    ("shadow", True), ("interpreter", True), ("turbo", True),
])
def test_engine_mode_falls_back_to_legacy_loudly(monkeypatch, raw, expect_warning):
    # caplog 대신 로거를 직접 바꿔 끼운다 — 다른 테스트 파일이 로깅 설정을 갈아엎으면(dictConfig 등)
    # "execution" 로거의 레코드가 caplog 에 닿지 않아 전체 회귀에서만 이 테스트가 깨졌다(2026-09-06).
    warnings = []

    class _Recorder:
        def warning(self, msg, *args, **kwargs):
            warnings.append(msg % args if args else msg)

    monkeypatch.setattr(execution, "logger", _Recorder())
    monkeypatch.setenv("EXECUTION_ENGINE", raw)
    execution._warned_engine_values.clear()
    assert execution.engine_mode() == execution.ENGINE_LEGACY
    warned = any("legacy 로 실행" in w for w in warnings)
    assert warned == expect_warning
