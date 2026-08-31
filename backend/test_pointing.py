"""AI 시맨틱 포인팅 계약 (백로그 28번 POINT-0).

이 파일이 지키는 문장:

  1. **모델이 범위를 지켰다고 말하는 것을 믿지 않는다.** 서버가 직접 비교하고, 범위 밖이
     하나라도 바뀌었으면 **요청 전체를 거부**한다. 절반만 반영된 그래프가 더 나쁘다.
  2. **클라이언트가 보낸 것 중 믿는 것은 id 와 hash 뿐이다.** label 로는 아무것도 결정하지 않고,
     대상은 서버가 현재 상태에서 다시 찾는다.
  3. **없어진 것과 바뀐 것을 구분한다.** 사용자가 할 일이 다르다.
  4. **비밀 값은 프롬프트에 넣지 않는다.**
  5. **telemetry 에 내용이 남지 않는다** — 지목한 대상의 이름이 곧 워크플로우 내용이다.
"""

from __future__ import annotations

import pytest

import pointing as p

GRAPH = {
    "nodes": [
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "apiKey": "sk-SECRET"}},
        {"id": "n3", "type": "outputNode", "data": {}},
        {"id": "far", "type": "memoNode", "data": {"text": "동떨어진 노드"}},
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
    ],
}

APP = {
    "ui": {"components": [
        {"id": "form", "type": "Container", "props": {}, "children": [
            {"id": "btn", "type": "Button", "props": {"text": "보내기"}, "children": []},
            {"id": "input", "type": "Input", "props": {"placeholder": "이름"}, "children": []},
        ]},
        {"id": "other", "type": "Text", "props": {"text": "관계없음"}, "children": []},
    ], "globalCss": ".a{}", "globalJs": "console.log(1)"},
    "logic": {"nodes": [{"id": "L1", "type": "onClick", "data": {}}], "edges": []},
}


def ctx(scope="target_only", targets=None, **kw):
    return p.parse_context({"scope": scope, "targets": targets or
                            [{"kind": "workflow_node", "id": "n2"}], **kw})


# ── 1. 요청 파싱 ────────────────────────────────────────────────────────

def test_포인팅을_안_쓰는_요청은_None이다():
    for empty in (None, {}, []):
        assert p.parse_context(empty) is None


def test_기본_범위는_선택_항목만이다():
    """기본값이 넓으면 사용자가 모르는 사이 전체가 편집 대상이 된다."""
    assert p.parse_context({"targets": [{"kind": "workflow_node", "id": "n1"}]})["scope"] \
        == p.SCOPE_TARGET_ONLY


def test_모르는_형식은_포인팅_없음으로_강등하지_않는다():
    """지목했는데 전체 캔버스가 편집 대상이 되는 것이 가장 나쁘다."""
    with pytest.raises(p.PointingError) as exc:
        p.parse_context({"version": 99, "targets": [{"kind": "workflow_node", "id": "n1"}]})
    assert exc.value.code == p.POINTING_INVALID_CONTEXT


@pytest.mark.parametrize("bad", [
    {"scope": "everything", "targets": [{"kind": "workflow_node", "id": "n1"}]},
    {"targets": [{"kind": "dom_selector", "id": "#btn"}]},
    {"targets": [{"kind": "workflow_node", "id": ""}]},
    {"targets": []},
    {"targets": "n1"},
])
def test_잘못된_요청을_거부한다(bad):
    with pytest.raises(p.PointingError):
        p.parse_context(bad)


def test_아직_지원하지_않는_종류는_거부한다():
    """계약에는 있지만 resolver 가 없다 — 조용히 무시하면 편집 범위가 넓어진다."""
    with pytest.raises(p.PointingError):
        p.parse_context({"targets": [{"kind": "image_region", "id": "img1"}]})


def test_대상_수에_상한이_있다():
    many = [{"kind": "workflow_node", "id": f"n{i}"} for i in range(p.MAX_TARGETS + 1)]
    with pytest.raises(p.PointingError) as exc:
        p.parse_context({"targets": many})
    assert exc.value.code == p.POINTING_CONTEXT_TOO_LARGE


def test_같은_대상을_두_번_보내면_한_번만_센다():
    parsed = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n1"},
                                          {"kind": "workflow_node", "id": "n1"}]})
    assert len(parsed["targets"]) == 1


def test_label은_길이를_자르고_보관만_한다():
    parsed = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n1",
                                           "label": "가" * 500}]})
    assert len(parsed["targets"][0]["label"]) <= 120


# ── 2. 대상 해석 — 서버가 다시 찾는다 ──────────────────────────────────

def test_현재_상태에서_다시_찾는다():
    resolved = p.resolve(ctx()["targets"], workflow_graph=GRAPH)
    assert resolved[0]["resolved"]["type"] == "llmNode"


def test_클라이언트가_보낸_내용은_쓰지_않는다():
    """label 을 'startNode' 라고 거짓으로 보내도 실제 대상은 n2(llmNode)다."""
    targets = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n2",
                                            "label": "시작 노드"}]})["targets"]
    resolved = p.resolve(targets, workflow_graph=GRAPH)
    assert resolved[0]["resolved"]["type"] == "llmNode"


def test_없어진_대상과_바뀐_대상을_구분한다():
    """사용자가 할 일이 다르다 — 전자는 지목을 지우고 후자는 다시 첨부한다."""
    gone = p.parse_context({"targets": [{"kind": "workflow_node", "id": "없음"}]})["targets"]
    with pytest.raises(p.PointingError) as exc:
        p.resolve(gone, workflow_graph=GRAPH)
    assert exc.value.code == p.POINTING_TARGET_NOT_FOUND

    changed = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n2",
                                            "snapshotHash": "옛날해시"}]})["targets"]
    with pytest.raises(p.PointingError) as exc:
        p.resolve(changed, workflow_graph=GRAPH)
    assert exc.value.code == p.POINTING_TARGET_STALE


def test_hash가_맞으면_통과한다():
    node = next(n for n in GRAPH["nodes"] if n["id"] == "n2")
    targets = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n2",
                                            "snapshotHash": p.snapshot_hash(node)}]})["targets"]
    assert p.resolve(targets, workflow_graph=GRAPH)


def test_revision이_다르면_stale이다():
    targets = p.parse_context({"targets": [{"kind": "workflow_node", "id": "n2",
                                            "revision": 3}]})["targets"]
    with pytest.raises(p.PointingError) as exc:
        p.resolve(targets, workflow_graph=GRAPH, revision=4)
    assert exc.value.code == p.POINTING_TARGET_STALE


def test_해시는_키_순서에_흔들리지_않는다():
    """같은 내용인데 직렬화가 달라 stale 이 나면 사용자는 이유를 알 수 없다."""
    assert p.snapshot_hash({"a": 1, "b": 2}) == p.snapshot_hash({"b": 2, "a": 1})


def test_중첩된_컴포넌트도_찾는다():
    """컴포넌트는 children 으로 중첩된다 — 평평한 목록이 아니다."""
    targets = p.parse_context({"targets": [{"kind": "app_component", "id": "btn"}]})["targets"]
    assert p.resolve(targets, app_state=APP)[0]["resolved"]["type"] == "Button"


def test_로직_노드도_찾는다():
    targets = p.parse_context({"targets": [{"kind": "app_logic_node", "id": "L1"}]})["targets"]
    assert p.resolve(targets, app_state=APP)[0]["resolved"]["type"] == "onClick"


# ── 3. 편집 허용 범위 ───────────────────────────────────────────────────

def test_선택_항목만이면_그것만_허용된다():
    allowed = p.editable_ids(ctx(), workflow_graph=GRAPH)
    assert allowed["nodes"] == {"n2"} and allowed["edges"] == set()


def test_연결_항목_포함은_1hop까지다():
    allowed = p.editable_ids(ctx(scope="target_and_neighbors"), workflow_graph=GRAPH)
    assert allowed["nodes"] == {"n1", "n2", "n3"}
    assert allowed["edges"] == {"e1", "e2"}
    assert "far" not in allowed["nodes"], "연결되지 않은 노드가 들어왔다"


def test_reference_only는_아무것도_못_바꾼다():
    allowed = p.editable_ids(ctx(scope="reference_only"), workflow_graph=GRAPH)
    assert all(v == set() for v in allowed.values())


def test_whole_canvas는_빈_집합이_아니라_None이다():
    """빈 집합('아무것도 못 바꾼다')과 구분되지 않으면 위험한 쪽으로 잘못 읽힌다."""
    allowed = p.editable_ids(ctx(scope="whole_canvas"), workflow_graph=GRAPH)
    assert all(v is None for v in allowed.values())


def test_컴포넌트_이웃은_부모와_직계_자식이다():
    allowed = p.editable_ids(
        ctx(scope="target_and_neighbors",
            targets=[{"kind": "app_component", "id": "btn"}]), app_state=APP)
    assert allowed["components"] == {"btn", "form"}
    assert "other" not in allowed["components"]


def test_같은_입력에_같은_결과다():
    """결정론적이어야 한다 — 매번 달라지면 검증이 의미가 없다."""
    a = p.editable_ids(ctx(scope="target_and_neighbors"), workflow_graph=GRAPH)
    b = p.editable_ids(ctx(scope="target_and_neighbors"), workflow_graph=GRAPH)
    assert a == b


# ── 4. 변경 후 검증 — 이 파일의 핵심 ───────────────────────────────────

def _with(graph, **changes):
    import copy

    out = copy.deepcopy(graph)
    for node in out["nodes"]:
        if node["id"] in changes:
            node["data"] = {**node.get("data", {}), **changes[node["id"]]}
    return out


def test_허용된_것만_바뀌면_통과한다():
    after = _with(GRAPH, n2={"model": "gpt-5.6"})
    p.validate_scope(ctx(), before=GRAPH, after=after,
                     allowed=p.editable_ids(ctx(), workflow_graph=GRAPH))


def test_범위_밖이_바뀌면_요청_전체를_거부한다():
    """모델이 '지목한 것만 고쳤다' 고 말해도 서버가 직접 본다."""
    after = _with(GRAPH, n2={"model": "gpt-5.6"}, far={"text": "몰래 바꿈"})
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(ctx(), before=GRAPH, after=after,
                         allowed=p.editable_ids(ctx(), workflow_graph=GRAPH))
    assert exc.value.code == p.POINTING_SCOPE_VIOLATION
    assert "far" in exc.value.targets


def test_노드를_몰래_추가해도_잡는다():
    import copy

    after = copy.deepcopy(GRAPH)
    after["nodes"].append({"id": "새노드", "type": "emailNode", "data": {}})
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(ctx(), before=GRAPH, after=after,
                         allowed=p.editable_ids(ctx(), workflow_graph=GRAPH))
    assert "새노드" in exc.value.targets


def test_노드를_몰래_지워도_잡는다():
    import copy

    after = copy.deepcopy(GRAPH)
    after["nodes"] = [n for n in after["nodes"] if n["id"] != "far"]
    with pytest.raises(p.PointingError):
        p.validate_scope(ctx(), before=GRAPH, after=after,
                         allowed=p.editable_ids(ctx(), workflow_graph=GRAPH))


def test_엣지를_몰래_바꿔도_잡는다():
    import copy

    after = copy.deepcopy(GRAPH)
    after["edges"][0]["target"] = "far"
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(ctx(), before=GRAPH, after=after,
                         allowed=p.editable_ids(ctx(), workflow_graph=GRAPH))
    assert "e1" in exc.value.targets


def test_whole_canvas면_무엇이든_통과한다():
    after = _with(GRAPH, far={"text": "바꿈"})
    scope = ctx(scope="whole_canvas")
    p.validate_scope(scope, before=GRAPH, after=after,
                     allowed=p.editable_ids(scope, workflow_graph=GRAPH))


def test_reference_only에서는_어떤_변경도_거부한다():
    after = _with(GRAPH, n2={"model": "gpt-5.6"})
    scope = ctx(scope="reference_only")
    with pytest.raises(p.PointingError):
        p.validate_scope(scope, before=GRAPH, after=after,
                         allowed=p.editable_ids(scope, workflow_graph=GRAPH))


def test_앱_전역_CSS_변경도_범위_밖이면_잡는다():
    import copy

    after = copy.deepcopy(APP)
    after["ui"]["components"][1]["props"]["text"] = "몰래 바꿈"   # other
    scope = ctx(targets=[{"kind": "app_component", "id": "btn"}])
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(scope, before=APP, after=after,
                         allowed=p.editable_ids(scope, app_state=APP), kind="app")
    assert "other" in exc.value.targets


# ── 5. 프롬프트에 들어가는 것 ───────────────────────────────────────────

def test_비밀_값은_프롬프트에_안_들어간다():
    resolved = p.resolve(ctx()["targets"], workflow_graph=GRAPH)
    built = p.build_prompt_context(resolved, p.editable_ids(ctx(), workflow_graph=GRAPH),
                                   workflow_graph=GRAPH)
    import json as _json

    assert "sk-SECRET" not in _json.dumps(built, ensure_ascii=False)


def test_전체_그래프가_아니라_허용된_것만_넣는다():
    """전체 상태는 서버의 검증 정본이고, 프롬프트는 예산이다."""
    built = p.build_prompt_context(
        p.resolve(ctx()["targets"], workflow_graph=GRAPH),
        p.editable_ids(ctx(), workflow_graph=GRAPH), workflow_graph=GRAPH)
    ids = [n["id"] for n in built["editable"]["nodes"]]
    assert ids == ["n2"], f"허용되지 않은 노드가 들어갔다: {ids}"


def test_연결_항목_포함이면_이웃도_들어간다():
    scope = ctx(scope="target_and_neighbors")
    built = p.build_prompt_context(
        p.resolve(scope["targets"], workflow_graph=GRAPH),
        p.editable_ids(scope, workflow_graph=GRAPH), workflow_graph=GRAPH)
    assert {n["id"] for n in built["editable"]["nodes"]} == {"n1", "n2", "n3"}


def test_서버_경로를_모델에게_보여주지_않는다():
    graph = {"nodes": [{"id": "h1", "type": "hwpxDocumentNode",
                        "data": {"output_path": "/srv/app/uploads/보고서.hwpx"}}], "edges": []}
    scope = ctx(targets=[{"kind": "workflow_node", "id": "h1"}])
    built = p.build_prompt_context(
        p.resolve(scope["targets"], workflow_graph=graph),
        p.editable_ids(scope, workflow_graph=graph), workflow_graph=graph)
    value = built["editable"]["nodes"][0]["value"]["data"]["output_path"]
    assert value == "보고서.hwpx" and "/srv/" not in value


# ── 6. 관측 — 내용을 남기지 않는다 ─────────────────────────────────────

def test_telemetry에_대상_이름이_남지_않는다():
    """지목한 대상의 이름이 곧 워크플로우 내용이다."""
    scope = ctx(targets=[{"kind": "workflow_node", "id": "n2", "label": "고객 개인정보 조회"}])
    record = p.telemetry(scope, outcome="applied")
    import json as _json

    dumped = _json.dumps(record, ensure_ascii=False)
    assert "고객" not in dumped and "n2" not in dumped


def test_telemetry가_세는_것():
    scope = ctx(scope="target_and_neighbors",
                targets=[{"kind": "workflow_node", "id": "n1"},
                         {"kind": "workflow_edge", "id": "e1"}])
    record = p.telemetry(scope, outcome="scope_violation", violations=3)
    assert record["scope"] == "target_and_neighbors"
    assert record["targetCount"] == 2
    assert record["kinds"] == {"workflow_node": 1, "workflow_edge": 1}
    assert record["scopeViolations"] == 3


def test_포인팅을_안_쓴_요청도_기록한다():
    assert p.telemetry(None, outcome="applied") == {"pointing": False}


# ── 7. 오류 code 가 카탈로그에 있다 ────────────────────────────────────

def test_모든_포인팅_오류가_카탈로그에_등록돼_있다():
    """code 를 새로 만들면 `error_catalog.json` 에 먼저 넣는다(ADR-0016)."""
    import io
    import json as _json
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    catalog = _json.load(io.open(root / "error_catalog.json", encoding="utf-8"))
    registered = {c["code"] for c in catalog["codes"]}
    for code in (p.POINTING_TARGET_NOT_FOUND, p.POINTING_TARGET_STALE,
                 p.POINTING_SCOPE_VIOLATION, p.POINTING_CONTEXT_TOO_LARGE,
                 p.POINTING_FORBIDDEN, p.POINTING_INVALID_CONTEXT):
        assert code in registered, f"{code} 가 error_catalog.json 에 없다"


def test_오류가_대상_id만_담는다():
    with pytest.raises(p.PointingError) as exc:
        p.resolve(p.parse_context({"targets": [{"kind": "workflow_node", "id": "없음",
                                                "label": "비밀 노드"}]})["targets"],
                  workflow_graph=GRAPH)
    assert exc.value.to_dict()["targets"] == ["없음"]
    assert "비밀" not in str(exc.value.to_dict())


# ── 8. 권한 — 조회와 편집을 따로 본다 ──────────────────────────────────
#
# 둘을 하나로 묶으면 viewer 가 "이 노드 고쳐줘" 로 편집할 수 있게 된다.

class _FakeUser:
    def __init__(self, uid):
        self.id = uid


class _FakeProject:
    def __init__(self, owner_id, visibility="private", workspace_id=None):
        self.user_id = owner_id
        self.visibility = visibility
        self.workspace_id = workspace_id


def test_소유자는_편집할_수_있다():
    p.check_permission(None, _FakeUser(1), _FakeProject(1), ctx())


def test_남의_비공개_프로젝트는_거부한다():
    with pytest.raises(p.PointingError) as exc:
        p.check_permission(None, _FakeUser(2), _FakeProject(1), ctx())
    assert exc.value.code == p.POINTING_FORBIDDEN


def test_공개_프로젝트라도_편집은_거부한다():
    """공개 범위는 조회만 준다 — 포인팅으로 그 선을 넘으면 안 된다."""
    with pytest.raises(p.PointingError):
        p.check_permission(None, _FakeUser(2), _FakeProject(1, visibility="public"), ctx())


def test_공개_프로젝트의_참조는_허용한다():
    """`reference_only` 는 그래프를 바꾸지 않으므로 조회 권한이면 충분하다."""
    p.check_permission(None, _FakeUser(2), _FakeProject(1, visibility="public"),
                       ctx(scope="reference_only"))


def test_포인팅을_안_쓰면_검사하지_않는다():
    p.check_permission(None, _FakeUser(2), _FakeProject(1), None)


# ── 9. 엔드포인트 연결 (POINT-0) ───────────────────────────────────────
#
# 계약이 있어도 호출부가 안 쓰면 소용없다 — 실제로 `/api/chat` 이 이 경로를 타는지 본다.

def _main_source():
    import io
    import pathlib

    return io.open(pathlib.Path(__file__).resolve().parent / "main.py",
                   encoding="utf-8").read()


def test_chat이_pointing_context를_받는다():
    """optional 이라 예전 클라이언트는 그대로 동작한다."""
    from main import ChatPayload

    assert "pointing_context" in ChatPayload.model_fields
    payload = ChatPayload(project_id="1", message="안녕")
    assert payload.pointing_context is None


def test_chat이_모델_호출_전에_해석하고_권한을_본다():
    source = _main_source()
    parse_at = source.index("_pointing.parse_context(payload.pointing_context)")
    permission_at = source.index("_pointing.check_permission(db, user, _point_project")
    call_at = source.index("await run_agent_turn(")
    assert parse_at < call_at, "모델을 부른 뒤에 해석하면 이미 늦다"
    assert permission_at < call_at, "권한을 보기 전에 모델을 불렀다"


def test_chat이_모델_결과를_직접_검증한다():
    source = _main_source()
    call_at = source.index("await run_agent_turn(")
    validate_at = source.index("_pointing.validate_scope(_point_ctx")
    assert validate_at > call_at, "검증이 모델 호출 앞에 있다"


def test_stale은_409로_돌려준다():
    """400 과 구분해야 클라이언트가 '다시 첨부' UI 를 띄울 수 있다."""
    assert "409 if _pe.code == _pointing.POINTING_TARGET_STALE else 400" in _main_source()


def test_지목이_있으면_앱_생성_분기를_타지_않는다():
    """캔버스에서 무언가를 지목했다면 "이걸 고쳐줘" 지 "앱을 만들어줘" 가 아니다.

    앱 분기가 먼저 있어서, 순서를 잘못 두면 **지목이 조용히 무시된다.**
    """
    source = _main_source()
    parse_at = source.index("_pointing.parse_context(payload.pointing_context)")
    app_branch_at = source.index("is_app_creation_intent(payload.message, target_type)")
    assert parse_at < app_branch_at, "앱 분기 뒤에 해석하면 지목이 무시된다"
    assert "_point_ctx is None and is_app_creation_intent" in source


def test_앱_컴포넌트_지목은_이_엔드포인트에서_거부한다():
    """`/api/chat` 은 워크플로우 그래프를 다룬다 — 앱 지목을 받으면 '대상 없음' 으로만 보인다.
    POINT-2 에서 `/api/builder/generate_app` 에 붙는다."""
    assert "앱 컴포넌트 지목은 아직 지원하지 않습니다" in _main_source()


# ── 10. POINT-1: 모델 지시문과 에디터 연결 ─────────────────────────────

def _instruction(scope="target_only", targets=None, graph=None):
    graph = graph or GRAPH
    context = ctx(scope=scope, targets=targets)
    allowed = p.editable_ids(context, workflow_graph=graph)
    resolved = p.resolve(context["targets"], workflow_graph=graph)
    return p.instruction_block(context, allowed, resolved)


def test_지시문이_대상을_id와_type으로_말한다():
    text = _instruction()
    assert "id=n2" in text and "type=llmNode" in text


def test_지시문이_수정_가능한_id를_열거한다():
    text = _instruction()
    assert "수정 가능한 노드: n2" in text


def test_연결_항목_포함이면_이웃도_열거한다():
    text = _instruction(scope="target_and_neighbors")
    assert "n1, n2, n3" in text
    assert "e1, e2" in text
    assert "1단계" in text


def test_지시문이_거부를_예고한다():
    """모델이 범위를 넘으면 어떻게 되는지 미리 말해 준다 — 성공률을 올리는 장치다."""
    assert "요청 전체를 거부" in _instruction()


def test_reference_only는_편집_금지를_말한다():
    text = _instruction(scope="reference_only")
    assert "편집 금지" in text and "근거로만" in text


def test_whole_canvas는_id를_열거하지_않는다():
    text = _instruction(scope="whole_canvas")
    assert "수정 가능한 노드" not in text
    assert "전체 캔버스" in text


def test_지시문이_사용자_요청보다_앞에_온다():
    """뒤에 붙이면 앞쪽 문맥에 묻힌다."""
    import io
    import pathlib

    source = io.open(pathlib.Path(__file__).resolve().parent / "meta_agent.py",
                     encoding="utf-8").read()
    assert 'f"{pointing_instruction}\\n\\n[사용자 요청]\\n{message}"' in source


def test_chat이_지시문을_에이전트에_넘긴다():
    source = _main_source()
    assert "pointing_instruction=_point_instruction" in source


def test_클라이언트_해시가_서버와_같은_방식이다():
    """다르면 멀쩡한 대상이 전부 stale 로 튕긴다 — 기능이 통째로 죽는다."""
    import io
    import pathlib

    editor = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/pages/EditorPage.jsx", encoding="utf-8").read()
    assert "SHA-256" in editor
    assert ".slice(0, 32)" in editor, "서버는 hex 앞 32자를 쓴다"
    assert "Object.keys(v).sort()" in editor, "키 순서를 없애야 서버와 같아진다"


def test_에디터가_선택만으로_자동_첨부하지_않는다():
    """속성을 보려고 클릭한 것이 AI 편집 권한으로 이어지면 안 된다."""
    import io
    import pathlib

    editor = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/pages/EditorPage.jsx", encoding="utf-8").read()
    assert "attachSelectionToAI" in editor
    # 첨부는 버튼 클릭으로만 일어난다 — 선택 상태 변화에 붙어 있으면 안 된다.
    assert "onClick={attachSelectionToAI}" in editor
    assert "useEffect(() => { attachSelectionToAI" not in editor


def test_삭제된_대상을_표시한다():
    """없어진 대상을 다른 id 에 조용히 재연결하지 않고 눈에 보이게 남긴다.

    핸들은 2026-08-30 에 캔버스 위 칩에서 **입력란 안의 토큰**으로 옮겼다(사용자 요청 —
    하나씩 지우기 어려웠다). 그래서 문구는 공용 Drawer 에 있다.
    """
    import io
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    drawer = io.open(root / "frontend/src/components/AIAssistantDrawer.jsx",
                     encoding="utf-8").read()
    editor = io.open(root / "frontend/src/pages/EditorPage.jsx", encoding="utf-8").read()

    assert "삭제된 대상" in drawer
    assert "is-missing" in drawer
    # 에디터는 판정만 하고 표시는 Drawer 에 맡긴다.
    assert "missing:" in editor


def test_핸들이_입력란_안에_있다():
    """칩이 입력창 밖에 있으면 "이 요청이 무엇에 대한 것인지" 가 멀어진다."""
    import io
    import pathlib
    import re

    drawer = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/components/AIAssistantDrawer.jsx",
                     encoding="utf-8").read()
    shell = re.search(r'<div className="work-assistant-input-shell">(.*?)</div>\s*</footer>',
                      drawer, re.S)
    assert shell, "input-shell 을 찾지 못했다"
    assert "work-assistant-mentions" in shell.group(1), "핸들이 입력란 밖에 있다"


def test_한글_조합_중에는_핸들을_지우지_않는다():
    """조합 중 Backspace 는 자모를 지우는 동작이다. 가로채면 글자 대신 핸들이 사라진다.

    이 저장소는 한글 IME 문제가 재발한 이력이 있다.
    """
    import io
    import pathlib

    drawer = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/components/AIAssistantDrawer.jsx",
                     encoding="utf-8").read()
    assert "isComposing" in drawer
    # Backspace 분기와 Enter 분기 **둘 다** 조합 상태를 본다.
    assert drawer.count("isComposing") >= 2


def test_클라이언트가_서버와_같은_출처에서_해시한다():
    """2026-08-30: 클라이언트가 React Flow **원본** 노드를 해싱해서 모든 대상이
    "지목한 뒤 바뀌었습니다" 로 튕겼다.

    서버는 `payload.graph_data`(= `getCurrentFlowData()`) 안의 항목을 해싱한다. 그 값은
    `createEditorSnapshot` 을 거쳐 함수·캔버스 전용 필드가 걸러진 것이라 원본과 모양이 다르다.
    클라이언트도 **같은 출처**에서 꺼내야 한다.
    """
    import io
    import pathlib
    import re

    editor = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/pages/EditorPage.jsx", encoding="utf-8").read()
    body = re.search(r"const targetSnapshot = \([^)]*\) => \{(.*?)\n  \};", editor, re.S)
    assert body, "targetSnapshot 을 찾지 못했다"
    assert "getCurrentFlowData()" in body.group(1), (
        "targetSnapshot 이 graph_data 와 다른 출처를 본다 — 해시가 어긋나 전부 stale 이 된다")
    # 원본 상태에서 직접 고르면 안 된다.
    assert "nodes.find(" not in body.group(1) and "edges.find(" not in body.group(1)


def test_정제된_노드의_해시가_서버와_같다():
    """실제 모양으로 확인한 값. 직렬화 방식이 바뀌면 여기서 깨진다."""
    node = {"id": "n2", "type": "llmNode", "position": {"x": 120.5, "y": 40},
            "width": 240, "height": 180,
            "data": {"model": "gpt-4o-mini", "systemPrompt": "요약해줘"}}
    assert p.snapshot_hash(node) == "6f153a105ec708c7baf13157e3bd8381"


def test_전송되지_않는_키는_해시에_넣지_않는다():
    """2026-08-30 두 번째 stale 원인.

    JS 객체에 `sourceHandle: undefined` 가 있으면 `JSON.stringify` 는 **그 키를 빼고** 보낸다.
    그런데 클라이언트가 손으로 만든 직렬화는 `"sourceHandle":undefined` 를 넣어 버려서,
    서버가 보는 것(키 없음)과 항상 어긋났다. 그래서 클라이언트는 `JSON.parse(JSON.stringify())`
    로 **전송될 모양**을 먼저 만든 뒤 해싱한다.
    """
    import io
    import pathlib
    import re

    editor = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "frontend/src/pages/EditorPage.jsx", encoding="utf-8").read()
    body = re.search(r"const stableStringify = useCallback\((.*?)\n  \}, \[\]\);", editor, re.S)
    assert body, "stableStringify 를 찾지 못했다"
    assert "JSON.parse(JSON.stringify(" in body.group(1), (
        "전송 모양으로 정규화하지 않으면 undefined 키 때문에 해시가 어긋난다")


def test_실제_그래프_모양으로_해시가_맞는다():
    """합성 데이터로만 맞춰 보다가 두 번 놓쳤다 — 저장된 그래프에 실제로 있는 키 조합으로 굳힌다."""
    node = {"id": "n1", "type": "startNode", "className": "",
            "position": {"x": 0, "y": 0}, "data": {}}
    edge = {"id": "e1", "source": "n1", "target": "n2", "type": "smoothstep",
            "style": {"stroke": "#94a3b8"}}
    import json as _json

    # 값은 JS 구현으로 같은 입력을 돌려 얻은 것이다. 직렬화가 바뀌면 여기서 깨진다.
    assert p.snapshot_hash(node) == "8f7ad81116170f73e99f44b0d197ea3c"
    assert p.snapshot_hash(edge) == "7268f68e10bf6524fafa2ee1b06f0f57"


# ── 11. 표현과 의미를 가른다 (2026-08-30 실사용에서 나온 결함) ─────────
#
# `auto_layout` 은 노드를 `{id,type,position,data}` 로 재구성하고 엣지를
# `FlowEdge.model_dump()` 로 만든다. 그래서 `className`·`style` 이 사라지는데,
# 통짜로 비교하면 **AI 가 손대지 않은 항목까지 전부** 바뀐 것으로 잡혔다(6개 위반).
#
# 편집 범위가 지키려는 것은 **워크플로우가 하는 일**이지 자리·색이 아니다.

LAID_OUT_BEFORE = {
    "nodes": [
        {"id": "a", "type": "llmNode", "className": "custom-node llm",
         "data": {"model": "gpt-4o-mini"}, "position": {"x": 1, "y": 2},
         "width": 240, "height": 180},
        {"id": "b", "type": "outputNode", "className": "custom-node",
         "data": {}, "position": {"x": 3, "y": 4}},
    ],
    "edges": [{"id": "e", "source": "a", "target": "b",
               "type": "smoothstep", "style": {"stroke": "#94a3b8"}}],
}
# auto_layout 을 거친 모양 — 표현 키가 전부 사라졌다.
LAID_OUT_AFTER = {
    "nodes": [
        {"id": "a", "type": "llmNode", "data": {"model": "gpt-4o-mini"},
         "position": {"x": 1, "y": 2}},
        {"id": "b", "type": "outputNode", "data": {}, "position": {"x": 3, "y": 4}},
    ],
    "edges": [{"id": "e", "source": "a", "target": "b",
               "sourceHandle": None, "targetHandle": None}],
}


def _target_a():
    return ctx(targets=[{"kind": "workflow_node", "id": "a"}])


def test_표현만_달라진_것은_변경이_아니다():
    """className·style·width 가 사라져도 워크플로우가 하는 일은 같다."""
    context = _target_a()
    p.validate_scope(context, before=LAID_OUT_BEFORE, after=LAID_OUT_AFTER,
                     allowed=p.editable_ids(context, workflow_graph=LAID_OUT_BEFORE))


def test_자리가_바뀌어도_변경이_아니다():
    import copy

    after = copy.deepcopy(LAID_OUT_AFTER)
    after["nodes"][1]["position"] = {"x": 999, "y": 999}
    context = _target_a()
    p.validate_scope(context, before=LAID_OUT_BEFORE, after=after,
                     allowed=p.editable_ids(context, workflow_graph=LAID_OUT_BEFORE))


def test_data가_바뀌면_여전히_잡는다():
    """느슨해진 만큼 진짜 변경을 놓치면 안 된다."""
    import copy

    after = copy.deepcopy(LAID_OUT_AFTER)
    after["nodes"][1]["data"] = {"몰래": "바꿈"}
    context = _target_a()
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(context, before=LAID_OUT_BEFORE, after=after,
                         allowed=p.editable_ids(context, workflow_graph=LAID_OUT_BEFORE))
    assert exc.value.targets == ["b"]


def test_노드_종류가_바뀌면_잡는다():
    import copy

    after = copy.deepcopy(LAID_OUT_AFTER)
    after["nodes"][1]["type"] = "emailNode"
    context = _target_a()
    with pytest.raises(p.PointingError):
        p.validate_scope(context, before=LAID_OUT_BEFORE, after=after,
                         allowed=p.editable_ids(context, workflow_graph=LAID_OUT_BEFORE))


def test_연결이_바뀌면_잡는다():
    """엣지의 style 은 표현이지만 source/target 은 의미다."""
    import copy

    after = copy.deepcopy(LAID_OUT_AFTER)
    after["edges"][0]["target"] = "a"
    context = _target_a()
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(context, before=LAID_OUT_BEFORE, after=after,
                         allowed=p.editable_ids(context, workflow_graph=LAID_OUT_BEFORE))
    assert "e" in exc.value.targets


def test_앱_컴포넌트도_props만_본다():
    import copy

    before = {"ui": {"components": [
        {"id": "btn", "type": "Button", "props": {"text": "보내기"}, "children": [],
         "style": {"top": 10}},
        {"id": "txt", "type": "Text", "props": {"text": "안내"}, "children": [],
         "style": {"top": 20}}]}, "logic": {"nodes": [], "edges": []}}
    after = copy.deepcopy(before)
    for comp in after["ui"]["components"]:
        comp.pop("style")                     # 표현만 사라짐
    context = ctx(targets=[{"kind": "app_component", "id": "btn"}])
    p.validate_scope(context, before=before, after=after,
                     allowed=p.editable_ids(context, app_state=before), kind="app")

    after["ui"]["components"][1]["props"]["text"] = "몰래 바꿈"
    with pytest.raises(p.PointingError) as exc:
        p.validate_scope(context, before=before, after=after,
                         allowed=p.editable_ids(context, app_state=before), kind="app")
    assert "txt" in exc.value.targets


# ── 12. 범위 안에서 실제로 할 수 있어야 한다 (2026-08-30) ──────────────
#
# 검증만 엄격하고 방법이 없으면 모델은 아무것도 안 하고 끝낸다 — 사용자에게는
# "오류도 없는데 변화도 없는" 상태로 보인다. 실제로 노드 종류 변경에서 그랬다.

def test_지시문이_종류_변경_방법을_알려준다():
    text = _instruction()
    assert "node_type" in text
    assert "delete_node" in text and "쓰지 마라" in text


def test_지시문이_못_할_때_어떻게_할지_말한다():
    """모델이 조용히 포기하지 않게 한다."""
    assert "무엇이 더 필요한지 말해라" in _instruction()


def test_update_node가_종류를_바꿀_수_있다():
    """예전에는 delete_node + add_node 뿐이었다 — 연결이 끊기고 id 가 바뀌어
    `target_only` 범위에서는 종류 변경 자체가 불가능했다."""
    import meta_agent
    from meta_agent import FlowGraph

    graph = FlowGraph(title="", description="", nodes=[
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "요약"}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ], edges=[{"id": "e1", "source": "n1", "target": "n2"},
              {"id": "e2", "source": "n2", "target": "n3"}])
    tools, get_graph, _c, _l = meta_agent.make_tools(graph)
    update = next(t for t in tools if t.name == "update_node")

    result = update.invoke({"node_id": "n2", "data": {"value": "고정 문구"},
                            "node_type": "valueNode"})
    assert "실패" not in result
    after = get_graph()
    assert {n.id: n.type for n in after.nodes}["n2"] == "valueNode"
    # **연결이 살아 있어야 한다** — 이게 delete+add 와의 차이다.
    assert {(e.source, e.target) for e in after.edges} == {("n1", "n2"), ("n2", "n3")}


def test_종류를_바꾸면_옛_설정을_끌고_가지_않는다():
    """이전 종류의 data 가 남으면 새 종류에서 의미 없는 필드가 붙는다."""
    import meta_agent
    from meta_agent import FlowGraph

    graph = FlowGraph(title="", description="", nodes=[
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "요약"}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ], edges=[{"id": "e1", "source": "n1", "target": "n2"},
              {"id": "e2", "source": "n2", "target": "n3"}])
    tools, get_graph, _c, _l = meta_agent.make_tools(graph)
    update = next(t for t in tools if t.name == "update_node")
    update.invoke({"node_id": "n2", "data": {"value": "고정 문구"}, "node_type": "valueNode"})

    data = {n.id: n.data for n in get_graph().nodes}["n2"]
    assert data == {"value": "고정 문구"}
    assert "systemPrompt" not in data and "model" not in data


def test_종류를_안_주면_예전처럼_병합한다():
    """기존 호출부가 그대로 동작해야 한다."""
    import meta_agent
    from meta_agent import FlowGraph

    graph = FlowGraph(title="", description="", nodes=[
        {"id": "n1", "type": "startNode", "data": {}},
        {"id": "n2", "type": "llmNode", "data": {"model": "gpt-4o-mini", "systemPrompt": "요약"}},
        {"id": "n3", "type": "outputNode", "data": {}},
    ], edges=[{"id": "e1", "source": "n1", "target": "n2"},
              {"id": "e2", "source": "n2", "target": "n3"}])
    tools, get_graph, _c, _l = meta_agent.make_tools(graph)
    update = next(t for t in tools if t.name == "update_node")
    update.invoke({"node_id": "n2", "data": {"model": "gpt-5.6"}})

    data = {n.id: n.data for n in get_graph().nodes}["n2"]
    assert data["model"] == "gpt-5.6"
    assert data["systemPrompt"] == "요약", "병합이 아니라 교체가 됐다"


def test_종류_변경이_편집_범위를_넘지_않는다():
    """id 와 연결이 그대로이므로 `target_only` 안에서 끝난다."""
    before = {"nodes": [{"id": "n1", "type": "startNode", "data": {}},
                        {"id": "n2", "type": "llmNode", "data": {"model": "a"}},
                        {"id": "n3", "type": "outputNode", "data": {}}],
              "edges": [{"id": "e1", "source": "n1", "target": "n2"},
                        {"id": "e2", "source": "n2", "target": "n3"}]}
    after = {"nodes": [{"id": "n1", "type": "startNode", "data": {}},
                       {"id": "n2", "type": "valueNode", "data": {"value": "고정"}},
                       {"id": "n3", "type": "outputNode", "data": {}}],
             "edges": before["edges"]}
    context = ctx(targets=[{"kind": "workflow_node", "id": "n2"}])
    p.validate_scope(context, before=before, after=after,
                     allowed=p.editable_ids(context, workflow_graph=before))
