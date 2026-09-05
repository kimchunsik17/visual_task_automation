"""NodeDefinition v1 (ADR-0005) 회귀 테스트.

정의 파일을 세 소비자(프론트 UI, 서버 validator, LLM 카탈로그)가 함께 쓰기 시작했으므로,
정의 하나를 고쳤을 때 어디가 조용히 어긋나는지를 여기서 잡는다.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

import node_definition
from export_node_definitions import BUNDLE_PATH, render_bundle

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
META_AGENT_PATH = REPO_ROOT / "backend" / "meta_agent.py"
CATALOG_SNAPSHOT_PATH = REPO_ROOT / "backend" / "testdata" / "node_catalog_snapshot.txt"

MIGRATED_TYPES = [
    "conditionNode", "httpRequestNode", "llmNode",
    # 우선 백로그 9번(2026-08-28): 주요 10종 이전 — 검증 문구·카탈로그 문구는 바이트 동일.
    "databaseNode", "delayNode", "emailNode", "fileModifierNode", "humanApprovalNode",
    "imageGenerationNode", "jsonParserNode", "posterGeneratorNode", "scheduleNode", "slackNode", "templateAnalyzerNode",
    # 우선 백로그 20번 잔여(2026-08-29): 첨부 포트가 생기면서 정의로 이전 — 문구는 역시 바이트 동일.
    "discordNode",
    # 한국형 노드 계획 Phase 1(2026-08-30): 서식 없이 .hwpx 를 만드는 노드.
    "hwpxDocumentNode",
    # 포맷 스튜디오 계획 Phase 1(2026-08-31): 포맷+빈칸 값 → 완성 파일.
    "formatNode",
]
# ADR-0008 에서 추가된 공식 연동 노드. 정의만으로 UI·validator·카탈로그가 만들어진다.
CONNECTOR_TYPES = [
    "youtubeNode", "youtubeTriggerNode",
    # Wave 1 (우선 백로그 8번, 2026-08-28): ADR-0007/0008 계약의 반복 적용.
    "rssTriggerNode", "gmailTriggerNode", "gmailNode", "googleDriveNode",
    # 한국형 노드 계획 Phase 2(2026-08-30): NAVER API HUB 검색.
    "naverSearchNode", "naverSearchTriggerNode", "naverCafeNode", "jusoNode", "dataGoKrNode",
]


def _catalog_template() -> str:
    """meta_agent.py 에서 NODE_CATALOG 템플릿 리터럴만 꺼낸다. langchain 등 무거운 의존성
    없이도 카탈로그 조립 결과를 검사하려는 것이다."""
    source = META_AGENT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^_NODE_CATALOG_TEMPLATE = ("""\\\n.*?""")\n', source, re.S | re.M)
    assert match, "meta_agent.py 에서 _NODE_CATALOG_TEMPLATE 리터럴을 찾지 못했다"
    return ast.literal_eval(match.group(1))


# ── 정의 파일 자체 ──────────────────────────────────────────────────────
def test_definitions_load():
    assert node_definition.defined_types() == sorted(MIGRATED_TYPES + CONNECTOR_TYPES)


@pytest.mark.parametrize("node_type", MIGRATED_TYPES + CONNECTOR_TYPES)
def test_definition_is_self_consistent(node_type):
    definition = node_definition.get_definition(node_type)
    # 정의 스키마 버전은 노드 계약이 바뀔 때 올라간다(databaseNode v2 = ADR-0017). 1 로 고정하지
    # 않되, 빠뜨리거나 0 이 되는 것은 막는다.
    assert isinstance(definition.version, int) and definition.version >= 1
    assert definition.executor == node_type
    assert definition.display.label

    # enum 규칙은 허용값을 같은 필드의 options 에서 읽는다 — options 없는 필드에 enum
    # 규칙을 달면 "무엇을 넣어도 실패"하는 검증기가 조용히 만들어진다.
    def walk(fields):
        for field in fields:
            for rule in field.validation:
                if rule.rule == "enum":
                    assert field.options, f"{node_type}.{field.name}: enum 규칙인데 options가 없다"
            if field.kind == "repeatable":
                assert field.itemFields, f"{node_type}.{field.name}: repeatable인데 itemFields가 없다"
                walk(field.itemFields)

    walk(definition.fields)


@pytest.mark.parametrize("node_type", MIGRATED_TYPES + CONNECTOR_TYPES)
def test_catalog_description_only_mentions_declared_fields(node_type):
    """카탈로그 설명이 'data.xxx' 로 안내하는 필드는 반드시 정의에 선언돼 있어야 한다.
    필드 이름을 바꾸면서 프롬프트 문구를 안 고치면 LLM이 존재하지 않는 필드를 채운다."""
    definition = node_definition.get_definition(node_type)
    declared = {field.name for field in definition.fields}
    # \w는 유니코드 모드에서 한글 조사까지 붙여 잡는다("connectionString은") — ASCII 식별자만.
    mentioned = set(re.findall(r"\bdata\.([A-Za-z_][A-Za-z0-9_]*)", definition.llm.description))
    assert mentioned <= declared, f"{node_type}: 정의에 없는 필드를 설명이 언급한다 — {mentioned - declared}"


# ── 소비자 ①: LLM 카탈로그 ─────────────────────────────────────────────
def _catalog_entries(catalog: str) -> dict:
    """'- nodeType : ...' 블록을 타입별로 쪼갠다(meta_agent 의 파서와 같은 규칙)."""
    section = catalog[catalog.index("[사용 가능한 노드") : catalog.index("\n[생성 원칙]")]
    entries, current, lines = {}, None, []
    for line in section.split("\n")[1:]:
        match = re.match(r"^- (\w+)\s*:", line)
        if match:
            if current:
                entries[current] = "\n".join(lines)
            current, lines = match.group(1), [line]
        elif current:
            lines.append(line)
    if current:
        entries[current] = "\n".join(lines)
    return entries


def test_existing_catalog_entries_never_drift():
    """노드를 새로 추가하는 것은 괜찮지만, 이미 있던 항목의 문구는 한 글자도 달라지면 안 된다 —
    생성 품질이 이 프롬프트 문구에 맞춰 조정돼 있기 때문이다."""
    assembled = node_definition.inject_catalog_entries(_catalog_template())
    snapshot = CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8")

    before, after = _catalog_entries(snapshot), _catalog_entries(assembled)
    missing = set(before) - set(after)
    assert not missing, f"카탈로그에서 사라진 노드 — {missing}"
    for node_type, text in before.items():
        assert after[node_type] == text, f"{node_type} 의 카탈로그 문구가 달라졌다"


def test_catalog_guidance_sections_never_drift():
    """[생성 원칙]과 [연결 규칙]은 노드 하나가 아니라 전체 생성 규칙이라 더 민감하다."""
    assembled = node_definition.inject_catalog_entries(_catalog_template())
    snapshot = CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert assembled[assembled.index("[생성 원칙]"):] == snapshot[snapshot.index("[생성 원칙]"):]


def test_catalog_header_count_matches_the_actual_entry_count():
    """'이 N종만 사용한다' 는 실제 항목 수와 맞아야 한다 — 어긋나면 LLM 에게 거짓을 말하게 된다."""
    assembled = node_definition.inject_catalog_entries(_catalog_template())
    declared = int(re.search(r"이 (\d+)종만 사용한다", assembled).group(1))
    assert declared == len(_catalog_entries(assembled))


def test_meta_agent_assembles_catalog_from_definitions():
    source = META_AGENT_PATH.read_text(encoding="utf-8")
    assert "NODE_CATALOG = node_definition.inject_catalog_entries(_NODE_CATALOG_TEMPLATE)" in source
    for node_type in MIGRATED_TYPES + CONNECTOR_TYPES:
        # 접두사는 카탈로그 원문의 패딩을 그대로 보존한다(바이트 동등성) — 폭을 재조립하지 않는다.
        assert re.search(
            rf"^- {node_type}\s*: {re.escape(node_definition.CATALOG_PLACEHOLDER)}$", source, re.M,
        ), node_type


def test_missing_definition_for_placeholder_fails_loudly():
    with pytest.raises(KeyError):
        node_definition.inject_catalog_entries(
            f"- neverExistsNode : {node_definition.CATALOG_PLACEHOLDER}\n"
        )


# ── 소비자 ②: 서버 validator ───────────────────────────────────────────
def test_migrated_types_have_no_hardcoded_validation_branch():
    """정의와 하드코딩 분기가 동시에 존재하면 둘이 갈라진다. 이전한 타입은 분기가 없어야 한다.

    databaseNode는 예외 — SQL 가드(세미콜론 분해 + SELECT/WITH 강제)는 규칙 DSL로 표현할 수
    없어 잔여 분기를 유지한다(하이브리드 검증, 정의가 query 존재 검사를 담당)."""
    source = META_AGENT_PATH.read_text(encoding="utf-8")
    hybrid_types = {"databaseNode"}
    for node_type in MIGRATED_TYPES:
        if node_type in hybrid_types:
            continue
        assert f'elif n.type == "{node_type}":' not in source


def test_unknown_type_is_left_to_legacy_validation():
    assert node_definition.validate_node_data("kakaoNode", "n1", {}) == []


@pytest.mark.parametrize(
    "node_type, data, expected",
    [
        # ── httpRequestNode ──
        ("httpRequestNode", {"method": "GET", "url": "https://x.dev"}, []),
        (
            "httpRequestNode",
            {},
            [
                "n1(httpRequestNode)의 method는 GET/POST/PUT/DELETE 중 하나여야 한다 (현재: None)",
                "n1(httpRequestNode)에 url이 없다",
            ],
        ),
        (
            "httpRequestNode",
            {"method": "PATCH", "url": "https://x.dev"},
            ["n1(httpRequestNode)의 method는 GET/POST/PUT/DELETE 중 하나여야 한다 (현재: 'PATCH')"],
        ),
        # ── llmNode ──
        ("llmNode", {"model": "gpt-4o-mini", "systemPrompt": "s"}, []),
        (
            "llmNode",
            {},
            ["n1(llmNode)에 model이 없다", "n1(llmNode)에 systemPrompt가 없다"],
        ),
        (
            "llmNode",
            {"model": "gpt-4", "systemPrompt": "s"},
            ["n1(llmNode)의 model 'gpt-4'은 허용되지 않는다 (허용: gpt-4o-mini, gpt-5.4-mini, gpt-5.6-terra)"],
        ),
        (
            "llmNode",
            {"model": "gpt-5.6-terra", "systemPrompt": "s", "useStructuredOutput": True},
            ["n1(llmNode)는 useStructuredOutput이 true인데 jsonSchema가 없다"],
        ),
        (
            "llmNode",
            {"model": "gpt-5.6-terra", "systemPrompt": "s", "useStructuredOutput": True, "jsonSchema": "{oops"},
            ["n1(llmNode)의 jsonSchema가 유효한 JSON이 아니다 — 실행 시 파싱에서 그대로 실패한다"],
        ),
        (
            "llmNode",
            {"model": "gpt-5.6-terra", "systemPrompt": "s", "useStructuredOutput": True, "jsonSchema": '{"type":"object"}'},
            [
                "n1(llmNode)의 jsonSchema에 최상위 'title' 키가 없다 — OpenAI 구조적 출력이 title을 "
                "함수 이름으로 쓰기 때문에 없으면 'Unsupported function' 오류로 실행이 즉시 실패한다. "
                '예: "title":"Result"를 추가하라'
            ],
        ),
        # useStructuredOutput이 꺼져 있으면 jsonSchema가 깨져 있어도 실행에 영향이 없다.
        (
            "llmNode",
            {"model": "gpt-5.6-terra", "systemPrompt": "s", "useStructuredOutput": False, "jsonSchema": "{oops"},
            [],
        ),
        # ── conditionNode ──
        ("conditionNode", {"rules": [{"id": "r1", "operator": "==", "value": "a"}]}, []),
        ("conditionNode", {}, ["n1(conditionNode)에 rules가 없다"]),
        ("conditionNode", {"rules": []}, ["n1(conditionNode)에 rules가 없다"]),
        (
            "conditionNode",
            {"rules": [{"operator": "bogus"}]},
            [
                "n1(conditionNode)의 rule #0에 id가 없다",
                "n1(conditionNode)의 rule #0 operator 'bogus'는 허용되지 않는다 (허용: <, <=, ==, >, >=, Contains)",
                "n1(conditionNode)의 rule #0에 value가 없다",
            ],
        ),
        (
            "conditionNode",
            {"rules": [{"id": "r1", "operator": "==", "value": "a"}, {"id": "r1", "operator": "==", "value": "b"}]},
            ["n1(conditionNode)의 rule id 'r1'가 중복된다"],
        ),
        # value=""는 "비어있는지 검사"하는 정상 규칙이라 통과시킨다.
        ("conditionNode", {"rules": [{"id": "r1", "operator": "Contains", "value": ""}]}, []),
        (
            "conditionNode",
            {"rules": [{"id": "r1", "operator": "==", "value": None}]},
            ["n1(conditionNode)의 rule r1에 value가 없다"],
        ),
        # ── discordNode (백로그 20번 잔여 이전) ──
        # botToken 키 자체가 없을 때는 channelId 요구로 넘어가지 않는다(예전 if/elif 사슬과 동일).
        ("discordNode", {}, ["n1(discordNode)에 botToken이 없다"]),
        # 봇 토큰 방식은 channelId 가 필수다.
        (
            "discordNode",
            {"botToken": "bot-token", "channelId": ""},
            ["n1(discordNode)가 Webhook이 아닌 봇 토큰 방식일 때는 channelId가 필수다"],
        ),
        ("discordNode", {"botToken": "bot-token", "channelId": "1234567890123456789"}, []),
        # Webhook URL 이면 채널이 URL 안에 있으므로 요구하지 않는다.
        ("discordNode", {"botToken": "https://discord.com/api/webhooks/1/a"}, []),
        ("discordNode", {"botToken": "https://discord.com/api/webhooks/1/a", "channelId": ""}, []),
        # 아직 모른다는 뜻의 빈 값은 통과하지만, 지어낸 형식은 걸러 재시도하게 만든다.
        ("discordNode", {"botToken": ""}, []),
        (
            "discordNode",
            {"botToken": "bot-token", "channelId": "guild/channel"},
            ["n1(discordNode)의 channelId('guild/channel')가 실제 디스코드 채널 ID 형식(숫자로만 된 스노우플레이크)이 아니다 — 사용자가 채널을 알려주지 않았다면 지어내지 말고 빈 문자열로 둬라"],
        ),
    ],
)
def test_validation_messages_match_pre_migration_behaviour(node_type, data, expected):
    assert node_definition.validate_node_data(node_type, "n1", data) == expected


def test_allowed_values_are_derived_from_select_options():
    assert node_definition.option_values("llmNode", "model") == {"gpt-4o-mini", "gpt-5.4-mini", "gpt-5.6-terra"}
    assert node_definition.option_values("httpRequestNode", "method") == {"GET", "POST", "PUT", "DELETE"}
    assert node_definition.option_values("conditionNode", "rules.operator") == {
        "==", "Contains", ">", "<", ">=", "<=",
    }
    assert node_definition.option_values("llmNode", "nopeField") == set()


# ── 소비자 ③: 프론트엔드 번들 ──────────────────────────────────────────
def test_frontend_bundle_is_up_to_date():
    assert BUNDLE_PATH.exists(), f"{BUNDLE_PATH} 가 없다 — python backend/export_node_definitions.py 실행"
    assert BUNDLE_PATH.read_text(encoding="utf-8") == render_bundle(), (
        "프론트엔드 번들이 정의 파일과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    )


def test_frontend_bundle_carries_ui_metadata():
    """에디터가 필드를 그리는 데 필요한 정보가 번들에 실제로 담겨 있는지."""
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    model_field = next(f for f in bundle["llmNode"]["fields"] if f["name"] == "model")
    assert [option["value"] for option in model_field["options"]] == [
        "gpt-4o-mini", "gpt-5.4-mini", "gpt-5.6-terra",
    ]
    json_schema_field = next(f for f in bundle["llmNode"]["fields"] if f["name"] == "jsonSchema")
    assert json_schema_field["showWhen"] == {"field": "useStructuredOutput", "truthy": True}
    assert bundle["conditionNode"]["display"]["collapsedLabel"] == "Switch\nBranch"


# ── 화면 등록 ───────────────────────────────────────────────────────────
# 정의를 추가해도 캔버스에 컴포넌트를 등록하지 않으면 노드가 팔레트에는 보이는데 **놓으면
# 디자인이 없고 펼칠 수도 없다**(2026-08-30 실제로 겪었다 — naverSearchNode·hwpxDocumentNode).
#
# 등록 경로는 둘이다. 정적 목록(EditorPage 의 nodeTypes + editorNodeCatalog 의 STATIC_EDITOR_NODES)
# 과, nodeRegistry.js 에 선언하면 DynamicNode 로 자동 등록되는 경로다. 둘 중 하나면 된다.

FRONTEND_DIR = REPO_ROOT / "frontend" / "src"
EDITOR_PAGE_PATH = FRONTEND_DIR / "pages" / "EditorPage.jsx"
EDITOR_CATALOG_PATH = FRONTEND_DIR / "editorNodeCatalog.js"
NODE_REGISTRY_PATH = FRONTEND_DIR / "nodeRegistry.js"
CUSTOM_NODES_PATH = FRONTEND_DIR / "customNodes.jsx"


def _explicit_node_types() -> set:
    source = EDITOR_PAGE_PATH.read_text(encoding="utf-8")
    block = re.search(r"const nodeTypes = \{(.*?)\n\};", source, re.S)
    assert block, "EditorPage.jsx 에서 nodeTypes 맵을 찾지 못했다"
    return set(re.findall(r"^\s*(\w+):", block.group(1), re.M))


def _dynamic_node_types() -> set:
    """nodeRegistry.js 에 선언된 타입 — DynamicNode 로 자동 등록된다."""
    source = NODE_REGISTRY_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"type:\s*'(\w+)'", source)) | set(re.findall(r'^\s*(\w+):\s*\{', source, re.M))


def _generic_field_node_types() -> set:
    """`ConnectorNode` 로 그리는 타입 — 필드 UI 를 정의에서 자동 생성한다."""
    source = CUSTOM_NODES_PATH.read_text(encoding="utf-8")
    return set(re.findall(r'<ConnectorNode[^>]*nodeType="(\w+)"', source))


@pytest.mark.parametrize("node_type", MIGRATED_TYPES + CONNECTOR_TYPES)
def test_정의된_노드는_캔버스에_그려질_수_있다(node_type):
    assert node_type in (_explicit_node_types() | _dynamic_node_types()), (
        f"{node_type}: EditorPage 의 nodeTypes 에도 nodeRegistry 에도 없다 — 캔버스에 놓으면 "
        "디자인이 적용되지 않고 펼칠 수도 없다"
    )


@pytest.mark.parametrize("node_type", MIGRATED_TYPES + CONNECTOR_TYPES)
def test_정의된_노드는_팔레트에서_고를_수_있다(node_type):
    """등록만 하고 팔레트에 없으면 사용자가 캔버스에 놓을 방법이 없다."""
    catalog = EDITOR_CATALOG_PATH.read_text(encoding="utf-8")
    assert f"'{node_type}'" in catalog or node_type in _dynamic_node_types(), (
        f"{node_type}: editorNodeCatalog 의 정적 목록에도 nodeRegistry 에도 없다")


@pytest.mark.parametrize("node_type", sorted(_generic_field_node_types()))
def test_정의로_필드를_그리는_노드는_보이는_필드가_있다(node_type):
    """`ConnectorNode` 는 정의의 필드를 그대로 그린다 — 전부 `ui.hidden` 이면 펼쳐도 빈 상자다.

    전용 컴포넌트를 가진 노드(fileModifierNode 등)는 자체 UI 를 그리므로 일부러 숨긴다."""
    definition = node_definition.get_definition(node_type)
    assert definition is not None, f"{node_type}: 정의가 없다"
    visible = [f for f in definition.fields if not f.ui.get("hidden")]
    assert visible, f"{node_type}: 보이는 필드가 하나도 없어 펼쳐도 값을 넣을 수 없다"


# 흐름이 여기서 끝나는 게 **정상인** 노드들. 나머지는 전부 뒤로 이을 수 있어야 한다.
TERMINAL_NODE_TYPES = {
    "outputNode",       # 결과 표시 — 마지막
    "breakNode",        # 반복 중단 — 뒤가 없다
    "memoNode",         # 캔버스 주석 — 실행 그래프가 아니다
}


def _component_source(component: str) -> str:
    source = CUSTOM_NODES_PATH.read_text(encoding="utf-8")
    start = source.find(f"export const {component} = ")
    if start < 0:
        return ""
    following = [m.start() for m in re.finditer(r"export const \w+ = ", source[start + 1:])]
    end = start + 1 + following[0] if following else len(source)
    return source[start:end]


def _node_type_components() -> dict:
    source = EDITOR_PAGE_PATH.read_text(encoding="utf-8")
    block = re.search(r"const nodeTypes = \{(.*?)\n\};", source, re.S)
    assert block, "EditorPage.jsx 에서 nodeTypes 맵을 찾지 못했다"
    return dict(re.findall(r"^\s*(\w+):\s*(\w+)", block.group(1), re.M))


@pytest.mark.parametrize("node_type,component", sorted(_node_type_components().items()))
def test_노드는_뒤로_이을_수_있는_핸들이_있다(node_type, component):
    """나가는 핸들이 없으면 **엣지가 데이터에 있어도 화면에 선이 그려지지 않는다.**

    2026-08-31 실제로 겪음 — notionNode/telegramNode/discordNode 가 target 핸들만 그려서,
    `notionNode → outputNode` 엣지가 멀쩡히 저장돼 있는데도 캔버스에서는 출력 노드가
    연결되지 않은 것처럼 보였다. 사용자가 "출력 노드 연결이 없다" 고 두 번 지적한 원인이다.
    """
    if node_type in TERMINAL_NODE_TYPES:
        return
    body = _component_source(component)
    assert body, f"{component}: customNodes.jsx 에서 컴포넌트를 찾지 못했다"
    has_source = ('type="source"' in body) or ("<ConnectorNode" in body)
    assert has_source, (
        f"{node_type}({component}): 나가는 핸들이 없다 — 이 노드 뒤로 잇는 선이 "
        "화면에 그려지지 않는다. <Handle type=\"source\" position={Position.Right} id=\"out\" /> 를 넣어라"
    )


# 실행기가 **이름으로 읽는** 갈래 핸들. 컴포넌트에 같은 id 의 핸들이 없으면 그 엣지는
# React Flow 가 붙일 자리를 못 찾아 **선을 그리지 않는다** — 실행은 되는데 화면만 끊겨 보인다.
# 오른쪽은 그 이름을 읽는 코드 위치다.
REQUIRED_SOURCE_HANDLES = {
    # node_generators/flow_nodes.py — 반복이 끝난 뒤 한 번만 나가는 경로
    "distributorNode": {"out", "done"},
    "loopNode": {"loop_start", "done"},
    # node_generators/ui_nodes.py — 승인/반려 분기
    "humanApprovalNode": {"approved", "rejected"},
    # conditionNode 는 규칙 id 로 핸들을 만든다(id={rule.id}) — 고정 이름은 else 뿐이다.
    "conditionNode": {"else"},
}


def _source_handle_ids(component: str) -> set:
    body = _component_source(component)
    if "<ConnectorNode" in body:
        return {"out"}          # ConnectorNode 가 정의를 보고 그린다
    ids = set()
    for match in re.finditer(r"<Handle\b(.*?)/>", body, re.S):
        attrs = match.group(1)
        if 'type="source"' not in attrs:
            continue
        named = re.search(r'id="(\w+)"', attrs)
        if named:
            ids.add(named.group(1))
        elif "id={rule.id}" in attrs:
            ids.add("*dynamic*")
    return ids


@pytest.mark.parametrize("node_type,required", sorted(REQUIRED_SOURCE_HANDLES.items()))
def test_갈래_핸들이_컴포넌트에_있다(node_type, required):
    """2026-08-31 실제로 겪음 — distributorNode 에 `done` 핸들이 없어서, 반복이 끝난 뒤
    출력 노드로 가는 선이 템플릿 29개에서 통째로 안 보였다. 데이터·실행은 멀쩡했다."""
    component = _node_type_components().get(node_type)
    assert component, f"{node_type}: EditorPage 의 nodeTypes 에 없다"
    missing = required - _source_handle_ids(component)
    assert not missing, (
        f"{node_type}({component}): 갈래 핸들 {sorted(missing)} 이(가) 없다 — 실행기는 이 이름을 "
        "읽는데 캔버스에는 붙일 자리가 없어 그 선이 그려지지 않는다"
    )


def test_showWhen_은_필드_최상위에_둔다():
    """`ui.showWhen` 에 두면 아무 효과가 없다 — 조건부 필드가 늘 보이거나 늘 숨는다."""
    for node_type in node_definition.defined_types():
        for field in node_definition.get_definition(node_type).fields:
            assert "showWhen" not in field.ui, (
                f"{node_type}.{field.name}: showWhen 은 ui 안이 아니라 필드 최상위 속성이다")


def test_출력_스키마가_카탈로그와_같은_노드를_받는다():
    """**카탈로그가 알려준 노드를 스키마가 거부하면 안 된다.**

    2026-08-30 에 실제로 어긋나 있었다 — 카탈로그는 49종을 알리는데 `NodeType` 은 45종만
    받아서, 한국형 노드 5종을 쓴 그래프가 생성·dry-run·커뮤니티 게시에서 전부 깨졌다.
    LLM 에게 "써도 된다" 고 말한 것과 우리가 받아주는 것이 같아야 한다.
    """
    from typing import get_args

    import meta_agent

    schema_types = set(get_args(meta_agent.NodeType))
    catalog_types = set(_catalog_entries(
        node_definition.inject_catalog_entries(_catalog_template())))

    rejected = catalog_types - schema_types
    assert not rejected, (
        f"카탈로그가 알리는데 출력 스키마가 거부하는 노드: {sorted(rejected)} — "
        "이 노드를 쓴 그래프는 검증에서 깨진다")

    # 반대 방향은 memoNode 하나만 허용한다(캔버스 주석이라 카탈로그에 없다).
    extra = schema_types - catalog_types
    assert extra == {"memoNode"}, f"카탈로그에 없는 스키마 타입: {sorted(extra - {'memoNode'})}"


def test_시작_노드_판정이_dry_run과_같다():
    """`validate_flow` 와 `dry_run` 이 서로 다른 트리거 목록을 들고 있으면 안 된다.

    2026-08-30 에 실제로 갈라져 있었다 — `meta_agent` 는 손으로 적은 5종이었고 그 사이 늘어난
    트리거 4종이 빠져서, RSS·YouTube·Gmail·네이버 트리거로 시작하는 그래프가 전부
    "시작 노드는 정확히 1개여야 한다 (현재 0개)" 로 거부됐다.
    """
    import dry_run
    import meta_agent

    assert set(meta_agent.START_NODE_TYPES) == set(dry_run.TRIGGER_NODE_TYPES)


def test_정의가_선언한_트리거가_시작_노드로_인정된다():
    import meta_agent

    for node_type in node_definition.trigger_types():
        assert node_type in meta_agent.START_NODE_TYPES, (
            f"{node_type} 는 트리거로 선언됐는데 시작 노드로 인정되지 않는다")
