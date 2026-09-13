"""engine_interpreter — 그래프 인터프리터 (백로그 32 ENGINE-0 4단계, ADR-0027) 테스트.

계약: (1) EXECUTION_ENGINE=interpreter 로 돌린 run_workflow 는 legacy 와 **같은 결과·같은 실행 로그·같은 토큰
집계**를 낸다 — 흐름 노드 6종·재합류·형제 복원·고정 출력·부분 실행·승인 대기·루트 예외·다중 루트 전부 ·
(2) 옛 엔진의 기존 테스트(merge_rejoin·editor_execution·approval_flow …)가 인터프리터에서 그대로 통과한다 ·
(3) shadow 는 legacy 결과를 바꾸지 않고 계획 실패만 기록한다 · (4) 계획은 정적이다 — 재합류가 분기 밖에 놓인다.
"""

from __future__ import annotations

import copy
import os
import pathlib
import subprocess
import sys

import pytest

import engine_interpreter
import execution
import graph
from conftest import minimal_subprocess_env

BACKEND = pathlib.Path(__file__).resolve().parent


def N(id_, type_, **data):
    return {"id": id_, "type": type_, "data": data}


def E(source, target, source_handle=None, target_handle=None):
    e = {"source": source, "target": target}
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    if target_handle is not None:
        e["targetHandle"] = target_handle
    return e


def _norm_logs(logs):
    out = []
    for s in logs:
        err = s.get("error")
        out.append((s["node_id"], s["node_type"], s["status"], s.get("result_data"), bool(s.get("pinned")),
                    (err["code"], err["userMessage"]) if err else None))
    return out


def run_both(monkeypatch, nodes, edges, **kwargs):
    """같은 그래프를 두 엔진으로 돌려 (legacy, interpreter) 를 돌려준다. 그래프는 엔진마다 깊은 복사로 준다."""
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    legacy = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), **copy.deepcopy(kwargs))
    monkeypatch.setenv("EXECUTION_ENGINE", "interpreter")
    interp = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), **copy.deepcopy(kwargs))
    return legacy, interp


def assert_equivalent(legacy, interp):
    l_result, l_tokens, l_logs = legacy
    i_result, i_tokens, i_logs = interp
    assert i_result == l_result
    assert _norm_logs(i_logs) == _norm_logs(l_logs)
    assert i_tokens == l_tokens


# ── 1. 흐름 노드와 순회 규칙 ───────────────────────────────────────────────

def test_조건_분기_뒤_재합류는_한_번_실행되고_실행된_갈래만_합쳐진다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="안녕하세요"),
             N("c", "conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": "안녕"}]),
             N("b1", "valueNode", varName="b1", value="매칭"), N("b2", "valueNode", varName="b2", value="기타"),
             N("m", "mergeNode", mergeStrategy="join_newline"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "c"), E("c", "b1", "r1"), E("c", "b2", "else"), E("b1", "m"), E("b2", "m"), E("m", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert interp[0] == "매칭"
    assert [n for n, *_ in _norm_logs(interp[2])] == ["s", "v", "c", "b1", "m", "o"]


@pytest.mark.parametrize("condition_value, expect_merge_runs", [("안녕", 1), ("전혀다른말", 0)])
def test_분기_안에서_완결되는_다이아몬드는_분기_안에_남는다(monkeypatch, condition_value, expect_merge_runs):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="안녕하세요"),
             N("c", "conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": condition_value}]),
             N("f2", "valueNode", varName="f2", value="참입력"), N("b1", "valueNode", varName="b1", value="왼쪽"),
             N("b2", "valueNode", varName="b2", value="오른쌍"), N("m", "mergeNode", mergeStrategy="join_newline"),
             N("e", "valueNode", varName="e", value="발송됨"), N("x", "valueNode", varName="x", value="기타경로")]
    edges = [E("s", "v"), E("v", "c"), E("c", "f2", "r1"), E("c", "x", "else"), E("f2", "b1"), E("f2", "b2"),
             E("b1", "m"), E("b2", "m"), E("m", "e")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert sum(1 for n, *_ in _norm_logs(interp[2]) if n == "m") == expect_merge_runs


def test_병렬_갈래의_둘째_갈래는_자기_상류의_출력을_받는다(monkeypatch):
    nodes = [N("s", "startNode"), N("src", "valueNode", value="원본"), N("t1", "dynamicInputNode", inputLabel="갈래1"),
             N("t2", "dynamicInputNode", inputLabel="갈래2"), N("m", "mergeNode", mergeStrategy="join_newline"),
             N("o", "outputNode")]
    edges = [E("s", "src"), E("src", "t1"), E("src", "t2"), E("t1", "m"), E("t2", "m"), E("m", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, t1="하나", t2="둘")
    assert_equivalent(legacy, interp)
    t2_out = next(r for n, _t, _s, r, *_ in _norm_logs(interp[2]) if n == "t2")
    assert "[갈래1]" not in t2_out and "원본" in t2_out


def test_분배는_항목마다_본문을_돌리고_done_은_합본으로_한_번_이어간다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value='["가", "나", "다"]'), N("p", "jsonParserNode", mode="parse"),
             N("d", "distributorNode"), N("u", "dynamicInputNode", inputLabel="항목"),
             N("c", "conditionNode", rules=[{"id": "r1", "operator": "==", "value": "나"}]),
             N("skip", "valueNode", varName="skip", value=""), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "p"), E("p", "d"), E("d", "u"), E("u", "c"), E("c", "skip", "r1"), E("d", "o", "done")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert [n for n, *_ in _norm_logs(interp[2])].count("u") == 3
    assert interp[0].count("[항목]") == 3


def test_반복은_누적값을_다음_회차에_넘기고_done_으로_한_번_이어간다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="x"), N("l", "loopNode", maxIterations=3),
             N("body", "dynamicInputNode", inputLabel="회차"), N("done", "valueNode", varName="done", value="끝"),
             N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "l"), E("l", "body", "loop_start"), E("l", "done", "done"), E("done", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, body="+")
    assert_equivalent(legacy, interp)
    steps = _norm_logs(interp[2])
    ids = [n for n, *_ in steps]
    assert ids.count("body") == 3 and ids[-3:] == ["l", "done", "o"]
    # 누적: 3회차 body 출력에는 앞 회차의 라벨이 두 번 들어 있다(직전 결과를 다음 회차 입력으로 넘긴다).
    third = [r for n, _t, _s, r, *_ in steps if n == "body"][2]
    assert third.count("[회차]") == 3


def test_break_는_가장_안쪽_반복만_끊고_누적_대입을_건너뛴다(monkeypatch):
    # 바깥 loop(2회) 안에 distributor(항목 1개) — 그 본문에서 break. 안쪽 반복만 끊기므로 loop 는 2회 다 돈다.
    nodes = [N("s", "startNode"), N("v", "valueNode", value="x"), N("l", "loopNode", maxIterations=2),
             N("d", "distributorNode"), N("u", "dynamicInputNode", inputLabel="항목"), N("brk", "breakNode"),
             N("done", "valueNode", varName="done", value="끝"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "l"), E("l", "d", "loop_start"), E("d", "u"), E("u", "brk"),
             E("l", "done", "done"), E("done", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, u="+")
    assert_equivalent(legacy, interp)
    ids = [n for n, *_ in _norm_logs(interp[2])]
    assert ids.count("u") == 2 and ids.count("brk") == 2 and ids.count("d") == 2
    assert ids[-3:] == ["l", "done", "o"]
    # 조건 뒤의 break 도 같다 — 첫 회차에 끊기고 done 으로 이어간다.
    nodes2 = [N("s", "startNode"), N("v", "valueNode", value="x"), N("l", "loopNode", maxIterations=4),
              N("body", "dynamicInputNode", inputLabel="회차"),
              N("c", "conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": "회차"}]),
              N("brk", "breakNode"), N("done", "valueNode", varName="done", value="끝"), N("o", "outputNode")]
    edges2 = [E("s", "v"), E("v", "l"), E("l", "body", "loop_start"), E("body", "c"), E("c", "brk", "r1"),
              E("l", "done", "done"), E("done", "o")]
    legacy, interp = run_both(monkeypatch, nodes2, edges2, body="+")
    assert_equivalent(legacy, interp)
    ids = [n for n, *_ in _norm_logs(interp[2])]
    assert ids.count("body") == 1 and ids.count("brk") == 1 and ids[-2:] == ["done", "o"]


def test_반복_밖의_break_는_두_엔진이_같은_실행_오류로_끝난다(monkeypatch):
    """옛 엔진은 생성 소스 compile 에서 'break' outside loop 로 죽는다(ast.parse 는 통과한다) — 인터프리터도
    같은 자리에서 같은 문구를 내야 한다."""
    nodes = [N("s", "startNode"), N("brk", "breakNode"), N("o", "outputNode")]
    edges = [E("s", "brk"), E("brk", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert interp[0].startswith("Dynamic Execution Error: 'break' outside loop")


def test_반복_본문이_없으면_pass_이고_횟수_식은_옛_엔진과_같은_이름공간에서_평가된다(monkeypatch):
    nodes = [N("s", "startNode"), N("l", "loopNode", maxIterations="2"), N("o", "outputNode")]
    edges = [E("s", "l"), E("l", "o", "done")]
    assert_equivalent(*run_both(monkeypatch, nodes, edges, default_input=""))
    # maxIterations 가 이상한 값이면 옛 엔진은 range(int(abc)) 의 NameError 로 루트가 실패한다 — 같아야 한다.
    bad = [N("s", "startNode"), N("l", "loopNode", maxIterations="abc"), N("o", "outputNode")]
    legacy, interp = run_both(monkeypatch, bad, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert interp[0].startswith("► Flow 1 Error: name 'abc' is not defined")


@pytest.mark.parametrize("decision, with_reject_branch", [("Y", True), ("N", True), ("Y", False), ("N", False)])
def test_승인_노드는_결정에_따라_갈래를_고르고_거절_갈래가_없으면_중단한다(monkeypatch, decision, with_reject_branch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="초안"), N("h", "humanApprovalNode"),
             N("ok", "valueNode", varName="ok", value="승인됨"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "h")]
    if with_reject_branch:
        nodes += [N("no", "valueNode", varName="no", value="반려"), N("o2", "outputNode")]
        edges += [E("h", "ok", "approved"), E("h", "no", "rejected"), E("ok", "o"), E("no", "o2")]
    else:
        edges += [E("h", "ok"), E("ok", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, approval_decisions={"h": decision})
    assert_equivalent(legacy, interp)
    if decision == "N" and not with_reject_branch:
        assert "halted by Human Approval Node" in interp[0]
    elif decision == "N":
        assert interp[0] == "반려"
    else:
        assert interp[0] == "승인됨"


def test_결정이_없으면_두_엔진_모두_fail_closed_문구로_멈춘다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="초안"), N("h", "humanApprovalNode"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "h"), E("h", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges)
    assert_equivalent(legacy, interp)
    assert interp[0].startswith("[HUMAN_APPROVAL_REQUIRED]")


def test_다중_루트는_같은_형식으로_합쳐진다(monkeypatch):
    nodes = [N("s1", "startNode"), N("a", "valueNode", value="첫째"), N("s2", "startNode"), N("b", "valueNode", value="둘째"),
             N("o", "outputNode")]
    edges = [E("s1", "a"), E("s2", "b"), E("b", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert "► Flow 1 Result:" in interp[0] and "► Flow 2 Result:" in interp[0]


def test_고정_출력과_부분_실행_인자는_그대로_승계된다(monkeypatch):
    nodes = [N("s", "startNode"), N("a", "valueNode", value="A"), N("b", "dynamicInputNode", inputLabel="B"),
             N("c", "valueNode", varName="c", value="C"), N("o", "outputNode")]
    edges = [E("s", "a"), E("a", "b"), E("b", "c"), E("c", "o")]
    assert_equivalent(*run_both(monkeypatch, nodes, edges, pinned_outputs={"b": "고정B"}, default_input=""))
    assert_equivalent(*run_both(monkeypatch, nodes, edges, entry_node_id="b", approval_payload="샘플", b="입력"))
    assert_equivalent(*run_both(monkeypatch, nodes, edges, stop_node_id="b", default_input=""))
    assert_equivalent(*run_both(monkeypatch, nodes, edges, scope_node_ids=["a", "b"], default_input=""))
    _, interp = run_both(monkeypatch, nodes, edges, pinned_outputs={"b": "고정B"}, default_input="")
    assert any(n == "b" and pinned for n, _t, _s, _r, pinned, _e in _norm_logs(interp[2]))


def test_등록되지_않은_노드와_제어_간선으로_도달한_tool_노드도_같다(monkeypatch):
    nodes = [N("s", "startNode"), N("x", "noSuchNode"), N("o", "outputNode")]
    edges = [E("s", "x"), E("x", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert interp[0] == "Unsupported node type: noSuchNode"


def test_llm_노드의_토큰_집계와_active_llm_배선이_같다(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from llm.providers.adapters import MockChatModel

    class _CountingModel(MockChatModel):
        """결정적 답변 + 토큰 사용량 — 두 엔진의 add_tracking 집계가 같은지 보기 위해 usage_metadata 를 싣는다."""

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            text = "답변:" + str(messages[-1].content)[-12:]
            message = AIMessage(content=text, usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
            return ChatResult(generations=[ChatGeneration(message=message)])

    import llm.providers as providers
    monkeypatch.setattr(providers, "create_runtime_chat_model", lambda **kw: _CountingModel())

    nodes = [N("s", "startNode"), N("v", "valueNode", value="자료"), N("p", "promptNode", userPrompt="요약해"),
             N("l", "llmNode", systemPrompt="너는 요약가"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "p"), E("p", "l"), E("l", "o")]
    legacy, interp = run_both(monkeypatch, nodes, edges, default_input="")
    assert_equivalent(legacy, interp)
    assert interp[1]["total_tokens"] > 0
    assert interp[0].startswith("답변:")


# ── 2. 옛 엔진의 기존 테스트가 인터프리터에서 그대로 통과한다 ─────────────

INTERPRETER_REPLAY_FILES = [
    "test_merge_rejoin.py", "test_editor_execution.py", "test_approval_flow.py", "test_pipeline_channels.py",
    "test_node_bindings.py", "test_artifact_delivery.py", "test_python_isolation.py",
]


def test_옛_엔진의_실행_테스트가_인터프리터에서_그대로_통과한다():
    """가장 강한 등가성 오라클 — 같은 단정이 두 엔진에서 모두 참이어야 한다. 서브프로세스로 돌려 환경변수를
    격리한다(EXECUTION_ENGINE 은 프로세스 전역이다)."""
    # 홈 디렉토리 변수는 남긴다 — langchain 계열이 import 시점에 Path.home() 을 부른다(없으면 수집 단계에서 죽는다).
    home_vars = {k: os.environ[k] for k in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA")
                 if os.environ.get(k)}
    env = minimal_subprocess_env(EXECUTION_ENGINE="interpreter", PYTHONPATH=str(BACKEND), PYTHONIOENCODING="utf-8",
                                 **home_vars)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *INTERPRETER_REPLAY_FILES],
        cwd=str(BACKEND), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    tail = "\n".join(proc.stdout.strip().splitlines()[-15:])
    assert proc.returncode == 0, f"인터프리터에서 깨진 기존 테스트가 있다:\n{tail}\n{proc.stderr[-2000:]}"
    assert "passed" in tail and "failed" not in tail


# ── 3. shadow — legacy 결과 그대로, 계획 실패만 기록 ───────────────────────

def test_shadow_는_legacy_결과를_바꾸지_않고_계획을_한_번_세운다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="값"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "o")]
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    legacy = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), default_input="")

    planned = []
    real_build = engine_interpreter.build_plan
    monkeypatch.setattr(engine_interpreter, "build_plan", lambda *a, **k: planned.append(1) or real_build(*a, **k))
    monkeypatch.setattr(execution, "shadow_plan_failures", [])
    monkeypatch.setenv("EXECUTION_ENGINE", "shadow")
    shadow = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), default_input="")

    assert_equivalent(legacy, shadow)
    assert planned == [1]
    assert execution.shadow_plan_failures == []


def test_shadow_의_계획_실패는_기록만_남기고_실행_결과는_legacy_다(monkeypatch):
    nodes = [N("s", "startNode"), N("v", "valueNode", value="값"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "o")]
    monkeypatch.setenv("EXECUTION_ENGINE", "legacy")
    legacy = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), default_input="")

    def boom(*a, **k):
        raise engine_interpreter.PlanError("계획 불가")

    monkeypatch.setattr(engine_interpreter, "build_plan", boom)
    monkeypatch.setattr(execution, "shadow_plan_failures", [])
    monkeypatch.setenv("EXECUTION_ENGINE", "shadow")
    shadow = graph.run_workflow(copy.deepcopy(nodes), copy.deepcopy(edges), default_input="", project_id=None)
    assert_equivalent(legacy, shadow)
    assert execution.shadow_plan_failures == [{"project_id": None, "error": "PlanError: 계획 불가"}]


# ── 4. 계획은 정적이다 ────────────────────────────────────────────────────

def test_형제_갈래에_걸친_재합류는_계획에서_분기_밖에_놓인다():
    nodes = [N("s", "startNode"), N("v", "valueNode", value="안녕"),
             N("c", "conditionNode", rules=[{"id": "r1", "operator": "Contains", "value": "안녕"}]),
             N("b1", "valueNode", varName="b1", value="왼쪽"), N("b2", "valueNode", varName="b2", value="오른쌍"),
             N("m", "mergeNode"), N("o", "outputNode")]
    edges = [E("s", "v"), E("v", "c"), E("c", "b1", "r1"), E("c", "b2", "else"), E("b1", "m"), E("b2", "m"), E("m", "o")]
    plan = engine_interpreter.build_plan(nodes, edges)
    root = plan.roots[0].items
    kinds = [(type(i).__name__, i.node_id) for i in root]
    assert kinds == [("Exec", "s"), ("Exec", "v"), ("Cond", "c"), ("Exec", "m"), ("Output", "o")], kinds
    cond = root[2]
    assert [i.node_id for i in cond.cases[0][1]] == ["b1"] and [i.node_id for i in cond.otherwise] == ["b2"]


def test_감쌀_수_없는_비흐름_노드는_계획_단계에서_거부된다(monkeypatch):
    """NATIVE_FLOW_TYPES 밖의 생성기가 제어 구문을 내기 시작하면 조용히 틀린 실행이 아니라 계획 실패여야 한다."""
    import node_bodies

    class _Fake:
        wrappable = False
        nests_downstream = True
        terminal_statement = None
        branches = []
        source = ""
        downstream = []

    monkeypatch.setattr(node_bodies, "render_node_body", lambda *a, **k: _Fake())
    with pytest.raises(engine_interpreter.PlanError, match="본문만 떼어 낼 수 없다"):
        engine_interpreter.build_plan([N("s", "startNode"), N("v", "valueNode")], [E("s", "v")])
