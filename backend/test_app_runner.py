"""앱 빌더 실행 경로 회귀 테스트.

두 결함을 고정한다.
  1. 앱 입력 키 이름을 사용자가 정하는데, 그 값을 run_workflow 의 **kwargs 로 펼치면
     'db'/'session_id'/'project_id'/'nodes' 같은 이름일 때 TypeError 로 실행이 통째로 죽었다.
  2. 실행 문맥(session_id/project_id)이 생성된 코드까지 전달되지 않아, llmNode 의 대화 기억이
     모든 프로젝트·세션에서 같은 행을 공유했다.
"""

from __future__ import annotations

import pytest

from graph import run_workflow

# webhookNode 는 생성된 코드에서 kwargs.get('<node_id>') 를 읽는다. 노드 id 를 관찰하고 싶은
# 키 이름으로 두면, 그 값이 실제로 실행 함수까지 왔는지 결과 문자열로 확인할 수 있다.
def echo_workflow(node_id: str):
    nodes = [
        {"id": node_id, "type": "webhookNode", "data": {}},
        {"id": "out", "type": "outputNode", "data": {}},
    ]
    edges = [{"id": "e1", "source": node_id, "target": "out"}]
    return nodes, edges


def run(node_id: str, **call_kwargs):
    nodes, edges = echo_workflow(node_id)
    result, _tokens, _logs = run_workflow(nodes, edges, **call_kwargs)
    return result


# ── 1. 입력 키 충돌 ────────────────────────────────────────────────────
@pytest.mark.parametrize("reserved", ["db", "session_id", "project_id", "nodes", "edges"])
def test_user_input_named_like_a_runtime_parameter_does_not_break_the_run(reserved):
    """앱 제작자가 입력 키를 'db' 나 'project_id' 로 지으면 예전에는 실행이 500 으로 죽었다."""
    result = run("echo", db=None, session_id="app_runner", project_id=1,
                 user_inputs={reserved: "사용자가 넣은 값"})
    assert "Dynamic Execution Error" not in str(result)


def test_user_input_value_still_reaches_the_node():
    result = run("my_input", db=None, session_id="app_runner", project_id=1,
                 user_inputs={"my_input": "안녕하세요"})
    assert "안녕하세요" in str(result)


def test_legacy_kwargs_callers_keep_working():
    """스케줄러·웹훅 등 기존 호출부는 **kwargs 를 그대로 쓴다 — 깨지면 안 된다."""
    result = run("my_input", db=None, session_id="webhook", project_id=1, my_input="레거시 경로")
    assert "레거시 경로" in str(result)


def test_user_inputs_win_over_legacy_kwargs_for_the_same_key():
    result = run("my_input", db=None, project_id=1,
                 my_input="레거시", user_inputs={"my_input": "명시적 입력"})
    assert "명시적 입력" in str(result)


# ── 2. 실행 문맥 전달 ──────────────────────────────────────────────────
def test_session_id_reaches_the_generated_code():
    """llmNode 의 대화 기억은 이 값으로 행을 나눈다. 안 넘어가면 모든 세션이 한 행을 공유한다."""
    assert "chat-session-42" in str(run("session_id", db=None, session_id="chat-session-42", project_id=7))


def test_project_id_reaches_the_generated_code():
    """트리거 cursor 도 이 값으로 프로젝트를 나눈다."""
    assert "7" in str(run("project_id", db=None, session_id="s", project_id=7))


def test_a_user_input_cannot_impersonate_the_execution_context():
    """실행 문맥은 호출부가 정하는 값이다 — 앱 입력으로 덮어쓸 수 있으면 다른 프로젝트의
    대화 기억을 읽어낼 수 있게 된다."""
    result = run("project_id", db=None, session_id="s", project_id=7,
                 user_inputs={"project_id": "999"})
    assert "999" not in str(result)
    assert "7" in str(result)


def test_missing_context_falls_back_to_the_generated_defaults():
    """session_id 를 안 주는 호출부도 있다 — None 을 억지로 넣어 기본값을 깨뜨리면 안 된다."""
    result = run("session_id", db=None, project_id=1)
    assert "Dynamic Execution Error" not in str(result)
