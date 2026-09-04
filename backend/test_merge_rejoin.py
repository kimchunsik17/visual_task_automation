"""재합류(fan-out 이 다시 합쳐지는 지점) 방출이 한 번만 되는지 (백로그: mergeNode 중복 방출).

예전에는 갈래마다 generate_block 이 사본 visited 로 내려가면서 재합류 노드와 그 하류가
갈래 수만큼 방출됐다. 증상은 하류에 뭐가 있느냐에 따라 달랐다:

  - 하류가 발송 노드(return 없음)면 **두 번 실행** — 제품이 권하는 mergeNode 해법을
    그대로 따라도 메일이 두 통 갔다(재검증 §2.1 실측).
  - 하류에 outputNode(return)가 있으면 첫 갈래에서 반환해버려 **둘째 갈래가 아예 실행되지
    않고** merge 결과에서 그 값이 조용히 사라졌다.

이제 재합류 노드는 모든 상류 갈래가 방출된 뒤 한 번만 방출된다(graph.generate_block 의
재합류 게이트). 배타 분기(conditionNode)는 분기 구문이 닫힌 자리에서 방출된다.
"""

from graph import compile_workflow, run_workflow


def _executed(logs, node_id):
    return [s for s in logs if s["node_id"] == node_id]


def test_fanout_이_merge_로_합쳐지면_하류는_한_번만_실행된다():
    """발송형(return 없는) 하류의 중복 실행 — '메일 두 통' 사례의 최소 재현."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "f", "type": "valueNode", "data": {"value": "입력"}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
    ]
    edges = [
        {"source": "s", "target": "f"},
        {"source": "f", "target": "b1"},
        {"source": "f", "target": "b2"},
        {"source": "b1", "target": "m"},
        {"source": "b2", "target": "m"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert len(_executed(logs, "m")) == 1, "merge 가 갈래 수만큼 실행됐다(중복 방출)"
    assert result == "왼쪽\n오른쪽"          # 두 갈래 결과가 모두 합쳐진다


def test_merge_하류에_output_이_있어도_둘째_갈래가_실행된다():
    """예전에는 첫 갈래의 merge 사본이 outputNode 의 return 까지 끌고 가서
    둘째 갈래가 통째로 건너뛰어졌다 — 결과에서 '오른쪽' 이 조용히 사라졌다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "f", "type": "valueNode", "data": {"value": "입력"}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "f"},
        {"source": "f", "target": "b1"},
        {"source": "f", "target": "b2"},
        {"source": "b1", "target": "m"},
        {"source": "b2", "target": "m"},
        {"source": "m", "target": "o"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert len(_executed(logs, "b2")) == 1, "둘째 갈래가 실행되지 않았다(첫 갈래에서 조기 return)"
    assert len(_executed(logs, "o")) == 1
    assert result == "왼쪽\n오른쪽"


def test_조건_분기가_merge_로_합쳐지면_분기_뒤에서_한_번만_실행된다():
    """배타 분기 안에 merge 를 방출하면 다른 분기가 실행될 때 못 만난다 — 분기 구문이
    닫힌 자리에서 한 번 방출돼야 하고, 실행된 갈래의 값만 합쳐진다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "v", "type": "valueNode", "data": {"value": "안녕하세요"}},
        {"id": "c", "type": "conditionNode",
         "data": {"rules": [{"id": "r1", "operator": "Contains", "value": "안녕"}]}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "매칭"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "기타"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "v"},
        {"source": "v", "target": "c"},
        {"source": "c", "target": "b1", "sourceHandle": "r1"},
        {"source": "c", "target": "b2", "sourceHandle": "else"},
        {"source": "b1", "target": "m"},
        {"source": "b2", "target": "m"},
        {"source": "m", "target": "o"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert len(_executed(logs, "b1")) == 1      # 매칭된 갈래만 실행
    assert len(_executed(logs, "b2")) == 0
    assert len(_executed(logs, "m")) == 1
    assert len(_executed(logs, "o")) == 1
    assert result == "매칭"                      # 실행 안 된 갈래는 merge 에서 빠진다


def test_merge_없이_같은_노드로_합쳐져도_그_노드는_한_번만_실행된다():
    """mergeNode 가 아닌 재합류(검증 규칙 9가 경고하는 다이아몬드)도 이제 중복 실행되지
    않는다 — 마지막 갈래의 값이 last_result 로 들어간다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "f", "type": "valueNode", "data": {"value": "입력"}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "f"},
        {"source": "f", "target": "b1"},
        {"source": "f", "target": "b2"},
        {"source": "b1", "target": "o"},
        {"source": "b2", "target": "o"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert len(_executed(logs, "o")) == 1
    assert len(_executed(logs, "b1")) == 1 and len(_executed(logs, "b2")) == 1
    assert result == "오른쪽"


def _branch_diamond_flow(condition_value):
    """조건 갈래 '안'에서 fan-out 이 merge 로 합쳐지는 그래프 — 분기 내부 다이아몬드."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "v", "type": "valueNode", "data": {"value": "안녕하세요"}},
        {"id": "c", "type": "conditionNode",
         "data": {"rules": [{"id": "r1", "operator": "Contains", "value": condition_value}]}},
        {"id": "f2", "type": "valueNode", "data": {"varName": "f2", "value": "참입력"}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
        {"id": "e", "type": "valueNode", "data": {"varName": "e", "value": "발송됨"}},
        {"id": "x", "type": "valueNode", "data": {"varName": "x", "value": "기타경로"}},
    ]
    edges = [
        {"source": "s", "target": "v"},
        {"source": "v", "target": "c"},
        {"source": "c", "target": "f2", "sourceHandle": "r1"},
        {"source": "c", "target": "x", "sourceHandle": "else"},
        {"source": "f2", "target": "b1"},
        {"source": "f2", "target": "b2"},
        {"source": "b1", "target": "m"},
        {"source": "b2", "target": "m"},
        {"source": "m", "target": "e"},
    ]
    return run_workflow(nodes, edges, default_input="")


def test_분기_안에서_완결되는_다이아몬드는_분기_안에_남는다():
    """갈래 하나 안에서 fan-out→merge 가 완결되면 merge 와 그 하류(발송 노드)는 그 갈래
    안에 방출돼야 한다 — 분기 바깥으로 끌어내면 갈래가 실행되지 않아도 발송이 나간다."""
    # 조건이 참인 실행: 다이아몬드 갈래가 타고, merge·하류가 한 번씩 실행된다.
    _, _, logs = _branch_diamond_flow("안녕")
    assert len(_executed(logs, "m")) == 1
    assert len(_executed(logs, "e")) == 1
    assert len(_executed(logs, "x")) == 0
    assert _executed(logs, "m")[0]["result_data"] == "왼쪽\n오른쪽"

    # 조건이 거짓인 실행: 갈래가 타지 않으므로 merge 도 하류 발송도 실행되면 안 된다.
    _, _, logs = _branch_diamond_flow("전혀다른말")
    assert len(_executed(logs, "m")) == 0, "분기가 실행되지 않았는데 merge 가 실행됐다(분기 밖 방출)"
    assert len(_executed(logs, "e")) == 0, "분기가 실행되지 않았는데 하류 발송이 실행됐다"
    assert len(_executed(logs, "x")) == 1


def test_갈래가_merge_로_직행해도_컴파일된다():
    """갈래 본문이 재합류 노드뿐이면 방출이 분기 뒤로 미뤄져 if/else 블록이 비는데,
    빈 블록은 문법 오류다 — pass 채움 회귀 테스트 (공식 템플릿 dry-run 에서 실제로 깨졌다)."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "v", "type": "valueNode", "data": {"value": "안녕하세요"}},
        {"id": "c", "type": "conditionNode",
         "data": {"rules": [{"id": "r1", "operator": "Contains", "value": "안녕"}]}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "기타"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "v"},
        {"source": "v", "target": "c"},
        {"source": "c", "target": "m", "sourceHandle": "r1"},   # 갈래 본문이 merge 뿐
        {"source": "c", "target": "b2", "sourceHandle": "else"},
        {"source": "b2", "target": "m"},
        {"source": "m", "target": "o"},
    ]
    result, _, logs = run_workflow(nodes, edges, default_input="")
    assert len(_executed(logs, "m")) == 1
    assert len(_executed(logs, "o")) == 1
    assert "안녕하세요" in result                # 조건 통과 갈래: 판정 입력이 merge 로 흐른다


def test_재합류가_있어도_생성_소스는_한_번씩만_방출된다():
    """실행이 아니라 소스 수준의 단정 — merge 하류 노드의 본문이 소스에 두 번 있으면
    (실행 경로에 따라) 두 번 실행될 수 있는 상태다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "f", "type": "valueNode", "data": {"value": "입력"}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
        {"id": "m", "type": "mergeNode", "data": {}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "f"},
        {"source": "f", "target": "b1"},
        {"source": "f", "target": "b2"},
        {"source": "b1", "target": "m"},
        {"source": "b2", "target": "m"},
        {"source": "m", "target": "o"},
    ]
    src = compile_workflow(nodes, edges)
    assert src.count("# --- Merge Node (m) ---") == 1
    assert src.count("# --- Output Node (o) ---") == 1


def test_병렬_갈래의_둘째_갈래는_형제_출력이_아니라_자기_상류의_출력을_받는다():
    """분기 형제 오염(2026-09-04) — 생성 코드는 갈래를 순차 방출하므로 둘째 갈래가 시작할 때
    last_result 에 첫 갈래의 마지막 출력이 남아 있었다. 시연 포스터 그래프에서 실제로 배경
    프롬프트 LLM 이 공고문 대신 형제 갈래의 문안 JSON 을 입력으로 받았다. 이제 갈래 진입
    시점에 자기 상류의 기록(__node_results__)으로 복원된다.

    dynamicInputNode 는 '직전 출력 + [라벨]: 값' 을 만들므로 갈래 입력 탐침으로 쓴다 —
    둘째 갈래 출력에 첫 갈래의 라벨이 섞여 있으면 오염이다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "src", "type": "valueNode", "data": {"value": "원본"}},
        {"id": "t1", "type": "dynamicInputNode", "data": {"inputLabel": "갈래1"}},
        {"id": "t2", "type": "dynamicInputNode", "data": {"inputLabel": "갈래2"}},
        {"id": "m", "type": "mergeNode", "data": {"mergeStrategy": "join_newline"}},
        {"id": "o", "type": "outputNode", "data": {}},
    ]
    edges = [
        {"source": "s", "target": "src"},
        {"source": "src", "target": "t1"},
        {"source": "src", "target": "t2"},
        {"source": "t1", "target": "m"},
        {"source": "t2", "target": "m"},
        {"source": "m", "target": "o"},
    ]
    result, _, logs = run_workflow(nodes, edges, t1="하나", t2="둘")
    t2_out = _executed(logs, "t2")[0]["result_data"]
    assert "[갈래2]" in t2_out and "원본" in t2_out
    assert "[갈래1]" not in t2_out and "하나" not in t2_out, (
        "둘째 갈래가 형제 갈래의 출력을 입력으로 받았다(분기 형제 오염): " + t2_out)
    # merge 에는 두 갈래가 각각 '원본'에서 출발한 결과가 모두 들어간다
    assert "하나" in result and "둘" in result


def test_배타_분기와_loop_는_복원_대상이_아니다():
    """복원은 '병렬 fan-out' 에만 걸려야 한다 — 배타 분기(conditionNode)는 한 갈래만
    실행돼 오염이 없고, loopNode 갈래(본문/탈출)에 복원을 걸면 반복 값이 덮인다.
    소스 수준으로 복원 라인이 붙지 않았음을 단정한다."""
    nodes = [
        {"id": "s", "type": "startNode", "data": {}},
        {"id": "v", "type": "valueNode", "data": {"value": "안녕"}},
        {"id": "c", "type": "conditionNode",
         "data": {"rules": [{"id": "r1", "operator": "Contains", "value": "안녕"}]}},
        {"id": "b1", "type": "valueNode", "data": {"varName": "b1", "value": "왼쪽"}},
        {"id": "b2", "type": "valueNode", "data": {"varName": "b2", "value": "오른쪽"}},
    ]
    edges = [
        {"source": "s", "target": "v"},
        {"source": "v", "target": "c"},
        {"source": "c", "target": "b1", "sourceHandle": "r1"},
        {"source": "c", "target": "b2", "sourceHandle": "else"},
    ]
    src = compile_workflow(nodes, edges)
    assert "__node_results__['c']" not in src, "배타 분기 갈래에 복원 라인이 붙었다"
