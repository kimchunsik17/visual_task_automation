"""
meta_agent.py — "말로 만드는 Agent 빌더"의 메타 agent (MVP 골격)

자연어 요청 -> Flow JSON(graph_data) 생성/수정.
엔진·프론트(React Flow)는 이미 완성돼 있으므로, 이 모듈은 '올바른 graph_data'만 만들면 된다.

■ 구조 한눈에
  ① NODE_CATALOG    : LLM에게 주는 '노드 사용설명서' (지금은 핵심 9종, 나중에 한 줄씩 추가하면 확장)
  ② Pydantic 스키마 : 출력 형식을 강제(with_structured_output) → 엉뚱한 노드/필드 방지
  ③ generate_flow   : 요청 -> graph_data
  ④ modify_flow     : 기존 graph_data + 요청 -> 수정된 graph_data
  ⑤ validate_flow   : 시작/종료·순환(DAG)·연결 검증 (Validator = 품질 게이트)
  ⑥ auto_layout     : LLM이 모르는 노드 좌표(x,y)를 자동 배치 → 실제 React Flow 형식으로 변환
  ⑦ generate_safely : 생성 → 검증 실패 시 사유를 붙여 1회 재시도
  ⑧ make_tools      : (Phase 2) 요청별 그릇 + 도구 6종(show/add/connect/update/delete/generate)
  ⑨ run_agent_turn  : (Phase 3) create_agent 조립 + 한 턴 실행 + 최종 완결성 게이트

■ 실행:  python meta_agent.py        (아래 __main__의 데모가 돈다)
■ 설치:  backend/requirements.txt에 필요한 패키지 이미 포함(langgraph·langchain-openai 등).
         create_agent를 쓰려면 core langchain 패키지도 필요 — 없으면 `pip install langchain>=0.3`.
■ 키:    OPENAI_API_KEY 환경변수(backend/.env) — get_llm()이 gpt-4o-mini 기본 사용.
"""

from __future__ import annotations
import re
from typing import Literal, List, Dict, Any, Optional, Tuple, Callable
from collections import defaultdict, deque
from pydantic import BaseModel, Field


# ── ① 노드 카탈로그 (핵심 9종) ────────────────────────────────────────────
# 여기에 노드를 한 줄씩 추가하면 챗봇이 다룰 수 있는 노드가 늘어난다(P2 확장).
NODE_CATALOG = """\
[사용 가능한 노드 — 이 9종만 사용한다]
- startNode      : 플로우 시작점. data 없음. 모든 플로우는 이 노드에서 시작한다.
- promptNode     : 사용자 프롬프트. data.userPrompt(문자열).
- llmNode        : LLM 호출. data.model(gemini-3.5-flash | gpt-4o-mini | claude-3-5-sonnet-20240620),
                   data.systemPrompt(문자열). 사용자가 모델을 특정하지 않으면 gpt-4o-mini를 기본값으로 쓴다.
- tokenizerNode  : 업로드 문서(PDF/PPTX/Excel/HWP)에서 텍스트 추출. data.method(extract_text | chunk_pages).
                   '문서/PDF/회의록 기반' 작업이면 llmNode 앞에 둔다. 직전 노드의 출력이 파일 경로여야 한다.
- conditionNode  : 조건 분기. data.rules=[{"id":"r1", "operator":"=="|"Contains"|">"|"<"|">="|"<=", "value":"문자열"}].
                   분기 엣지는 sourceHandle에 해당 rule의 id(조건 통과) 또는 "else"(다 안 맞을 때)를 넣는다.
- httpRequestNode: 외부 API 호출. data.method(GET|POST|PUT|DELETE), data.url(문자열),
                   data.headers(JSON 문자열, 생략 가능), data.body(JSON 문자열, 생략 가능).
- jsonParserNode : JSON 파싱/변환. data.mode(parse|stringify|extract). extract일 때만 data.extractKey(문자열) 필요.
                   parse=문자열→JSON, stringify=JSON→문자열, extract=특정 키 값 꺼내기.
- delayNode      : 지정한 시간만큼 대기 후 다음 노드로 진행. data.seconds(숫자).
- outputNode     : 결과 출력(종료). data 없음. 모든 플로우는 이 노드에서 끝난다.

[생성 원칙]
- 반드시 startNode 1개로 시작하고, outputNode로 끝난다.
- 모든 노드는 start→output 경로 위에 있어야 한다. 어디에도 연결 안 된 고아 노드를 만들지 않는다.
- 사용자가 원하는 바를 충족하되, 불필요한 중복 노드를 만들지 않는다 — 필요한 만큼만 최소로 구성한다.
  단, "최소"를 이유로 요청에 필요한 단계(예: PDF 입력이면 tokenizerNode)를 빠뜨리면 안 된다.
- tokenizerNode는 직전 노드의 출력이 파일 경로일 때만 사용한다.
- promptNode는 항상 인접한 llmNode와 짝으로 사용한다.
- llmNode의 model은 사용자가 특정 모델을 요청하지 않는 한 기본값 gpt-4o-mini를 쓴다.
- 요청이 모호하면 임의로 복잡하게 확대 해석하지 말고, 가장 단순한 구조로 만들거나 먼저 사용자에게 되물어본다.
- (미세수정 시) 기존 노드로 이미 처리 가능하면 새 노드를 추가하지 말고 update_node로 기존 노드를 고친다.

[연결 규칙]
- 순환(cycle) 금지. 노드는 앞에서 뒤로만 연결한다.
- 각 노드 id는 n1, n2 ... 처럼 유일하게. 엣지 id는 e1, e2 ...
- conditionNode에서 나가는 엣지만 sourceHandle이 필요(rule.id 또는 "else"). 나머지는 비워둔다.
- 노드마다 엣지 여러 개 허용 여부가 다르다(실행 엔진 동작 기준):
  · conditionNode는 같은 핸들(rule id 또는 else)에 엣지를 1개까지만 — 2개 이상이면 엔진이
    첫 번째만 쓰고 나머지는 조용히 버린다.
  · promptNode는 들어오는 llmNode 엣지를 1개까지만 — 2개 이상이면 어떤 모델이 쓰일지
    비결정적이 된다(엔진이 마지막 걸로 덮어씀).
  · 그 외 노드가 나가는 엣지를 여러 개 갖는 것(팬아웃)은 괜찮다 — 각 분기가 독립적으로 실행된다.
    단, 여러 입력을 하나로 합치는 기능은 없다.
"""


# ── ② 출력 스키마 (형식 강제) ────────────────────────────────────────────
# type을 Literal로 묶어 9종 밖의 노드를 아예 못 만들게 한다. position(x,y)은
# LLM이 추측하면 안 되므로 항상 None으로 초기화하고, auto_layout에서 채운다.
NodeType = Literal[
    "startNode", "promptNode", "llmNode", "tokenizerNode", "conditionNode",
    "httpRequestNode", "jsonParserNode", "delayNode", "outputNode"
]


class FlowNode(BaseModel):
    id: str = Field(description="노드 고유 id, 예: n1")
    type: NodeType
    data: Dict[str, Any] = Field(default_factory=dict, description="노드 설정(promptNode의 userPrompt 등)")
    position: Optional[Dict[str, float]] = Field(
        default=None,
        description="화면 좌표 {x,y}. LLM은 절대 채우지 않는다(항상 비워둠) — 기존 노드는 프론트가 보낸 "
                     "좌표를 그대로 보존하고, 새 노드만 auto_layout이 배치한다.",
    )


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = Field(default=None, description="조건 분기 시 rule 순번 또는 'else'")


class FlowGraph(BaseModel):
    nodes: List[FlowNode]
    edges: List[FlowEdge]


# ── LLM 준비 (제공자 교체 지점) ──────────────────────────────────────────
def get_llm():
    """메타 agent가 쓸 LLM. 현재 OpenAI. 제공자 교체는 여기만 바꾸면 된다."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)
    # Gemini로 되돌리려면 위 두 줄 대신:
    # from langchain_google_genai import ChatGoogleGenerativeAI
    # return ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)


SYSTEM = (
    "너는 노코드 agent 빌더의 설계 도우미다. 사용자의 요청을 읽고, "
    "아래 노드만으로 실행 가능한 워크플로우(graph_data)를 만든다.\n\n" + NODE_CATALOG
)

# few-shot 예시 — 생성 품질을 좌우하는 핵심. 실패 사례를 여기에 계속 보강한다(팀원 C).
FEWSHOT = """\
[예시1] 요청: "PDF 요약봇 만들어줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"tokenizerNode","data":{"method":"extract_text"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 문서를 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n5","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}

[예시2] 요청: "날씨 API 호출해서 결과를 한국어로 요약해줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"https://api.example.com/weather"}},
  {"id":"n3","type":"jsonParserNode","data":{"mode":"extract","extractKey":"summary"}},
  {"id":"n4","type":"promptNode","data":{"userPrompt":"다음 날씨 정보를 한국어로 요약해줘"}},
  {"id":"n5","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 날씨 캐스터다"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
"""


# ── ③ 생성 ───────────────────────────────────────────────────────────────
def _strip_positions(g: FlowGraph) -> FlowGraph:
    """LLM이 혹시 position을 채워서 냈어도 무시한다 — generate_flow/modify_flow는 항상
    '전체를 새로 만든다'는 뜻이므로, 좌표는 auto_layout이 새로 배치해야 한다(기존 캔버스
    배치를 사용자가 손으로 잡아놨어도 이 경로에서는 의도적으로 전체 재배치가 맞다)."""
    for n in g.nodes:
        n.position = None
    return g


def generate_flow(user_request: str) -> FlowGraph:
    llm = get_llm().with_structured_output(FlowGraph, method="function_calling")   # 출력을 FlowGraph 형식으로 강제
    messages = [
        ("system", SYSTEM + "\n\n" + FEWSHOT),
        ("user", f'요청: "{user_request}"\n위 규칙에 맞는 graph_data를 만들어줘.'),
    ]
    return _strip_positions(llm.invoke(messages))


# ── ④ 수정 ───────────────────────────────────────────────────────────────
def modify_flow(existing: FlowGraph, user_request: str) -> FlowGraph:
    llm = get_llm().with_structured_output(FlowGraph, method="function_calling")
    messages = [
        ("system", SYSTEM),
        ("user",
         f"아래는 현재 플로우다:\n{existing.model_dump_json()}\n\n"
         f'이 플로우를 다음 요청대로 수정해서 "전체"를 다시 반환해줘: "{user_request}"'),
    ]
    return _strip_positions(llm.invoke(messages))


# ── ⑤ Validator (품질 게이트) ────────────────────────────────────────────
# 계약(§3, 계약_Flow_JSON.md)에서 고정된 허용값. 여기 값이 바뀌면 계약 문서도 같이 고친다.
ALLOWED_MODELS = {
    "gemini-3.5-flash", "gemini-1.5-pro", "gpt-4o-mini", "gpt-4o",
    "claude-3-haiku-20240307", "claude-3-5-sonnet-20240620",
}
ALLOWED_OPERATORS = {"==", "Contains", ">", "<", ">=", "<="}
ALLOWED_METHODS = {"extract_text", "chunk_pages"}
ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE"}
ALLOWED_JSON_PARSER_MODES = {"parse", "stringify", "extract"}


def validate_flow(g: FlowGraph, require_complete: bool = True) -> Tuple[bool, List[str]]:
    """유효하면 (True, []), 아니면 (False, [사람이 읽을 사유들]). 사유는 재시도 프롬프트에 재사용.

    검사 항목(계약 §3 기준):
      1) startNode 정확히 1개로 시작        ← require_complete=True일 때만
      2) outputNode로 종료(1개 이상)        ← require_complete=True일 때만
      3) 순환 금지(DAG)
      4) 모든 엣지의 source·target가 실재 노드
      5) 노드 id 유일(엣지 id도 유일)
      6) 노드별 data 필수 필드 존재 + 값 검증(model enum, operator enum 등)
      7) conditionNode 분기 엣지의 sourceHandle이 그 노드의 rules[].id 또는 "else" 중 하나,
         그리고 같은 핸들에 엣지가 2개 이상 몰리지 않는지(실행 엔진이 첫 번째만 쓰고 나머지는 무시함)
      8) promptNode에 llmNode발 incoming 엣지가 2개 이상이면 안 됨(실행 엔진이 마지막 것으로 덮어써서
         모델 선택이 비결정적이 됨)

    require_complete=False면 1)·2)(시작/종료 완결성)를 건너뛴다. add_node 등으로 그래프를
    한 노드씩 쌓는 도중에는 당연히 startNode나 outputNode가 아직 없는 "미완성" 상태를 거치므로,
    그 자체를 실패로 보면 노드를 단 하나도 못 쌓는다(직접 테스트로 확인된 버그).
    그래서 미세 수정 도구(add/connect/update/delete_node)는 require_complete=False로 "즉시 막아야
    할 것"만 검사하고, 완성 여부는 generate_flow나 최종 응답 직전(Phase 4)에 기본값(True)으로 확인한다.
    """
    errors: List[str] = []
    ids = [n.id for n in g.nodes]
    types = [n.type for n in g.nodes]
    idset = set(ids)

    # 1~2) 시작/종료 — 완성본 검사일 때만
    if require_complete:
        if types.count("startNode") != 1:
            errors.append(f"startNode(시작)는 정확히 1개여야 한다 (현재 {types.count('startNode')}개)")
        if "outputNode" not in types:
            errors.append("outputNode(종료)가 없다")

    # 5) 노드/엣지 id 유일성
    dup_node_ids = {i for i in ids if ids.count(i) > 1}
    if dup_node_ids:
        errors.append(f"중복된 노드 id가 있다: {', '.join(sorted(dup_node_ids))}")

    edge_ids = [e.id for e in g.edges]
    dup_edge_ids = {i for i in edge_ids if edge_ids.count(i) > 1}
    if dup_edge_ids:
        errors.append(f"중복된 엣지 id가 있다: {', '.join(sorted(dup_edge_ids))}")

    # 4) 엣지 양끝 노드 존재 (고아 엣지)
    for e in g.edges:
        missing = [x for x in (e.source, e.target) if x not in idset]
        if missing:
            errors.append(f"엣지 {e.id}가 존재하지 않는 노드를 가리킨다: {', '.join(missing)}")

    # 6) 노드별 data 필수 필드
    nodes_by_id = {n.id: n for n in g.nodes}
    for n in g.nodes:
        errors.extend(_validate_node_data(n))

    # 7) conditionNode 분기 엣지의 sourceHandle 검사 + 핸들당 엣지 개수 제한
    # (실행 엔진 확인 결과: 같은 핸들에 엣지가 2개 이상이면 첫 번째만 쓰고 나머지는 조용히 버림 — 침묵 버그라서 여기서 막는다)
    handle_edge_count: Dict[Tuple[str, str], int] = defaultdict(int)
    for e in g.edges:
        source_node = nodes_by_id.get(e.source)
        if source_node is None:
            continue  # 이미 위에서 고아 엣지로 보고됨
        if source_node.type == "conditionNode":
            handles = _condition_handles(source_node)
            if e.sourceHandle is None:
                errors.append(f"엣지 {e.id}: conditionNode {source_node.id}에서 나가는 엣지는 sourceHandle(rule id 또는 'else')이 필요하다")
            elif e.sourceHandle not in handles:
                errors.append(
                    f"엣지 {e.id}: sourceHandle '{e.sourceHandle}'가 {source_node.id}의 rules id/else와 일치하지 않는다 "
                    f"(허용: {', '.join(sorted(handles))})"
                )
            else:
                handle_edge_count[(source_node.id, e.sourceHandle)] += 1

    for (cond_id, handle), count in handle_edge_count.items():
        if count > 1:
            errors.append(
                f"{cond_id}(conditionNode)의 handle '{handle}'에 엣지가 {count}개 연결됐다 — "
                "실행 엔진은 핸들당 엣지를 1개만 처리하고 나머지는 조용히 무시한다. 핸들당 1개만 연결하라"
            )

    # 8) promptNode에 llmNode에서 들어오는 엣지가 2개 이상이면 안 됨
    # (실행 엔진 확인 결과: 마지막 것으로 조용히 덮어써서 어떤 모델이 쓰일지 비결정적이 됨)
    llm_incoming_count: Dict[str, int] = defaultdict(int)
    for e in g.edges:
        source_node = nodes_by_id.get(e.source)
        target_node = nodes_by_id.get(e.target)
        if source_node and target_node and source_node.type == "llmNode" and target_node.type == "promptNode":
            llm_incoming_count[target_node.id] += 1

    for prompt_id, count in llm_incoming_count.items():
        if count > 1:
            errors.append(
                f"{prompt_id}(promptNode)에 llmNode에서 들어오는 엣지가 {count}개 있다 — "
                "실행 엔진이 마지막 것으로 조용히 덮어써서 어떤 모델이 쓰일지 비결정적이 된다. 1개만 연결하라"
            )

    # 3) 순환(cycle)
    has_cycle, stuck = _has_cycle(ids, g.edges)
    if has_cycle:
        errors.append(f"순환(cycle)이 있다 — 관련 노드: {', '.join(stuck)} (노드는 앞으로만 연결해야 한다)")

    return (len(errors) == 0, errors)


def _validate_node_data(n: FlowNode) -> List[str]:
    """노드 type별 data 필수 필드 존재 여부 + 허용값 검사. 계약 §3 표 기준."""
    errors: List[str] = []
    d = n.data or {}

    if n.type == "promptNode":
        if not d.get("userPrompt"):
            errors.append(f"{n.id}(promptNode)에 userPrompt가 없다")

    elif n.type == "llmNode":
        model = d.get("model")
        if not model:
            errors.append(f"{n.id}(llmNode)에 model이 없다")
        elif model not in ALLOWED_MODELS:
            errors.append(f"{n.id}(llmNode)의 model '{model}'은 허용되지 않는다 (허용: {', '.join(sorted(ALLOWED_MODELS))})")
        if not d.get("systemPrompt"):
            errors.append(f"{n.id}(llmNode)에 systemPrompt가 없다")

    elif n.type == "tokenizerNode":
        method = d.get("method")
        if method not in ALLOWED_METHODS:
            errors.append(f"{n.id}(tokenizerNode)의 method는 extract_text 또는 chunk_pages여야 한다 (현재: {method!r})")

    elif n.type == "conditionNode":
        rules = d.get("rules")
        if not rules:
            errors.append(f"{n.id}(conditionNode)에 rules가 없다")
        else:
            seen_rule_ids = set()
            for i, r in enumerate(rules):
                rid = r.get("id")
                op = r.get("operator")
                val = r.get("value")
                label = rid or f"#{i}"
                if not rid:
                    errors.append(f"{n.id}(conditionNode)의 rule {label}에 id가 없다")
                elif rid in seen_rule_ids:
                    errors.append(f"{n.id}(conditionNode)의 rule id '{rid}'가 중복된다")
                else:
                    seen_rule_ids.add(rid)
                if op not in ALLOWED_OPERATORS:
                    errors.append(f"{n.id}(conditionNode)의 rule {label} operator '{op}'는 허용되지 않는다 (허용: {', '.join(sorted(ALLOWED_OPERATORS))})")
                if val is None or val == "":
                    errors.append(f"{n.id}(conditionNode)의 rule {label}에 value가 없다")

    elif n.type == "httpRequestNode":
        method = d.get("method")
        if method not in ALLOWED_HTTP_METHODS:
            errors.append(f"{n.id}(httpRequestNode)의 method는 GET/POST/PUT/DELETE 중 하나여야 한다 (현재: {method!r})")
        if not d.get("url"):
            errors.append(f"{n.id}(httpRequestNode)에 url이 없다")

    elif n.type == "jsonParserNode":
        mode = d.get("mode")
        if mode not in ALLOWED_JSON_PARSER_MODES:
            errors.append(f"{n.id}(jsonParserNode)의 mode는 parse/stringify/extract 중 하나여야 한다 (현재: {mode!r})")
        if mode == "extract" and not d.get("extractKey"):
            errors.append(f"{n.id}(jsonParserNode)는 mode가 extract일 때 extractKey가 필요하다")

    elif n.type == "delayNode":
        seconds = d.get("seconds")
        if seconds is None:
            errors.append(f"{n.id}(delayNode)에 seconds가 없다")
        else:
            try:
                if float(seconds) < 0:
                    errors.append(f"{n.id}(delayNode)의 seconds는 0 이상이어야 한다 (현재: {seconds!r})")
            except (TypeError, ValueError):
                errors.append(f"{n.id}(delayNode)의 seconds는 숫자여야 한다 (현재: {seconds!r})")

    # startNode·outputNode는 data가 없어야 정상이지만, 있다고 해서 실행이 깨지진 않으므로 에러로 보진 않는다.
    return errors


def _condition_handles(n: FlowNode) -> set:
    """conditionNode가 가질 수 있는 sourceHandle 전체 집합 = rule id들 + 'else'."""
    rules = (n.data or {}).get("rules") or []
    return {r.get("id") for r in rules if r.get("id")} | {"else"}


def _has_cycle(ids: List[str], edges: List[FlowEdge]) -> Tuple[bool, List[str]]:
    """위상정렬로 순환 감지. (순환 여부, 순환에 걸려 못 빠진 노드 id 목록)."""
    adj = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for e in edges:
        if e.source in indeg and e.target in indeg:
            adj[e.source].append(e.target)
            indeg[e.target] += 1
    q = deque([i for i in ids if indeg[i] == 0])
    seen = set()
    while q:
        u = q.popleft()
        seen.add(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    stuck = [i for i in ids if i not in seen]
    return (len(stuck) > 0, stuck)


# ── ⑥ 자동 배치 → 실제 graph_data(dict) ──────────────────────────────────
def auto_layout(g: FlowGraph) -> dict:
    """position(x,y)이 없는 노드(새로 추가됐거나 generate_flow가 방금 만든 노드)만 위상순서로
    새로 배치하고, 이미 position이 있는 노드(프론트에서 넘어온 기존 노드)는 그대로 보존한다.

    이게 없으면 사용자가 캔버스에서 손으로 배치를 잡아놔도 챗봇에게 한 마디만 시키면 매번
    전체가 위상순서로 다시 정렬돼버린다(실제로 통합 전 리뷰에서 지적된 문제) — 그래서
    "이미 위치가 있으면 건드리지 않는다"를 기본 원칙으로 삼는다."""
    order = _topo_order([n.id for n in g.nodes], g.edges)
    existing_positions = {n.id: n.position for n in g.nodes if n.position}
    existing_xs = [p.get("x", 0) for p in existing_positions.values()]
    base_x = (max(existing_xs) + 220) if existing_xs else 0
    new_ids_in_order = [nid for nid in order if nid not in existing_positions]
    fresh_positions = {nid: {"x": base_x + i * 220, "y": 120} for i, nid in enumerate(new_ids_in_order)}

    nodes = [{
        "id": n.id,
        "type": n.type,
        "position": existing_positions.get(n.id) or fresh_positions.get(n.id, {"x": 0, "y": 120}),
        "data": n.data,
    } for n in g.nodes]
    edges = [e.model_dump() for e in g.edges]
    return {"nodes": nodes, "edges": edges}


def _topo_order(ids: List[str], edges: List[FlowEdge]) -> List[str]:
    adj = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for e in edges:
        if e.source in indeg and e.target in indeg:
            adj[e.source].append(e.target)
            indeg[e.target] += 1
    q = deque([i for i in ids if indeg[i] == 0])
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return out + [i for i in ids if i not in out]   # 순환 노드는 뒤에 붙임(안전)


# ── ⑦ 생성 + 검증 + 재시도 ───────────────────────────────────────────────
def generate_safely(user_request: str) -> dict:
    """생성 → Validator 통과분만 반환. 실패하면 사유를 붙여 1회 재시도."""
    g = generate_flow(user_request)
    ok, errs = validate_flow(g)
    if not ok:
        retry = f'{user_request}\n\n(직전 생성이 아래 이유로 잘못됐다. 고쳐서 다시: {"; ".join(errs)})'
        g = generate_flow(retry)
        ok, errs = validate_flow(g)
    if not ok:
        raise ValueError(f"유효한 플로우 생성 실패: {errs}")
    return auto_layout(g)


# ── ⑧ Phase 2: 도구 6종 (요청별 그릇 + 자기수정 루프) ──────────────────────
# 설계 요약 (예나와 논의 확정):
#   - 요청마다 make_tools(graph)를 새로 호출 → 그 안에서만 사는 "그릇"(state["graph"])을
#     클로저로 감싼 6개 @tool을 반환. 동시 요청끼리 절대 안 섞인다.
#   - 변경형 도구(add/connect/update/delete/generate) 공통 흐름:
#     스냅샷 → 변경 적용 → validate_flow → 실패하면 스냅샷으로 자동 롤백 + 에러 문자열 반환,
#     성공하면 그대로 커밋. 반환 문자열은 항상 사람이 읽는 한국어 → 에이전트의 자기수정 재료.
#   - update_node는 data를 "병합"(merge)한다 — 넘긴 필드만 덮어쓰고 나머지는 유지.
#     type은 여기서 못 바꾼다(구조상 data만 받으므로) — 바꾸려면 delete_node 후 add_node.
#   - position(x,y)은 그릇 안에서는 안 다룬다. 에이전트가 끝난 뒤 auto_layout()에서 한 번만 채운다.

def _next_id(prefix: str, existing_ids: List[str]) -> str:
    """prefix(n 또는 e) + 숫자 id 중 가장 큰 번호 다음 값을 돌려준다. 없으면 1부터."""
    nums = []
    for i in existing_ids:
        m = re.fullmatch(rf"{re.escape(prefix)}(\d+)", i)
        if m:
            nums.append(int(m.group(1)))
    return f"{prefix}{(max(nums) + 1) if nums else 1}"


def _summarize_node_data(node_type: str, data: Dict[str, Any]) -> str:
    """show_flow용 한 줄 요약. 노드 타입별 핵심 필드만 보여준다."""
    if node_type == "promptNode":
        return f"userPrompt={data.get('userPrompt', '')!r}"
    if node_type == "llmNode":
        return f"model={data.get('model')}, systemPrompt={data.get('systemPrompt', '')!r}"
    if node_type == "tokenizerNode":
        return f"method={data.get('method')}"
    if node_type == "conditionNode":
        rule_ids = [r.get("id") for r in (data.get("rules") or [])]
        return f"rules={rule_ids}"
    if node_type == "httpRequestNode":
        return f"method={data.get('method')}, url={data.get('url', '')!r}"
    if node_type == "jsonParserNode":
        mode = data.get("mode")
        return f"mode={mode}" + (f", extractKey={data.get('extractKey', '')!r}" if mode == "extract" else "")
    if node_type == "delayNode":
        return f"seconds={data.get('seconds')}"
    return ""


def make_tools(initial_graph: FlowGraph) -> Tuple[List, Callable[[], FlowGraph]]:
    """요청 하나(=대화 한 턴)마다 호출. (도구 6개 리스트, 현재 그래프를 꺼내는 함수) 튜플을 반환한다.

    두 번째 값 get_current_graph()가 필요한 이유: 도구들이 참조하는 그릇(state)은 클로저 안에
    갇혀 있어서 바깥에서 직접 못 꺼낸다. 롤백이 일어나면 state["graph"]가 통째로 새 객체로
    바뀌기도 해서, 맨 처음 넘긴 initial_graph 참조를 계속 들고 있어도 최신 상태를 못 본다
    (테스트하다 실제로 걸린 문제). 그래서 Phase 3/4가 에이전트 실행이 끝난 뒤
    "최종적으로 뭐가 만들어졌는지" 읽을 방법이 반드시 있어야 한다.

    사용 예 (Phase 3/4에서):
        tools, get_current_graph = make_tools(graph_data_from_request)
        agent = create_agent(model, tools=tools, checkpointer=...)
        agent.invoke(...)
        final_graph = get_current_graph()          # 에이전트가 도구로 바꾼 최종 결과
        ok, errs = validate_flow(final_graph)       # require_complete=True(기본값) — 완결성 최종 게이트
        if ok:
            response_graph_data = auto_layout(final_graph)
        else:
            response_graph_data = 원래_받은_graph_data   # 미완성이면 캔버스에 반영하지 않고 원본 유지
    """
    from langchain_core.tools import tool

    state: Dict[str, Any] = {"graph": initial_graph, "fail_streak": 0, "last_errors": []}

    def _snapshot() -> FlowGraph:
        return state["graph"].model_copy(deep=True)

    def _fail(msg: str) -> str:
        """실패 처리 공통: 연속 실패 횟수를 세고, 3회 이상이면 '그만 시도하라'는 경고를 덧붙인다.
        (예나 결정: 구조 미완결 문제는 require_complete=False로 이미 해결했으니, 이 카운터는
        정말로 반복해서 이상한 시도를 하는 경우—잘못된 id 참조, 계속 틀린 값 고집 등—를 잡는 안전망.)"""
        state["fail_streak"] += 1
        if state["fail_streak"] >= 3:
            msg += (
                f"\n⚠️ 연속 {state['fail_streak']}회 실패했습니다. 같은 방식으로 더 시도하지 말고, "
                "사용자에게 무엇이 막혔는지 설명하고 어떻게 할지 물어보세요."
            )
        return msg

    def _succeed(msg: str) -> str:
        state["fail_streak"] = 0
        return msg

    def _commit_or_rollback(before: FlowGraph, success_msg: str) -> str:
        # require_complete=False: 도구 하나 단위로는 startNode/outputNode가 아직 없어도 정상
        # (짓는 중이니까). 그 완결성 확인은 generate_flow나 Phase 4 최종 응답 때만 한다.
        ok, errs = validate_flow(state["graph"], require_complete=False)
        if not ok:
            state["graph"] = before  # 자동 롤백
            state["last_errors"] = errs
            return _fail(f"실패(변경 취소됨): {'; '.join(errs)}")
        return _succeed(success_msg)

    def _render_flow() -> str:
        g = state["graph"]
        if not g.nodes:
            return "(빈 플로우 — 아직 노드 없음)"
        lines = []
        for n in g.nodes:
            summary = _summarize_node_data(n.type, n.data)
            lines.append(f"- {n.id}({n.type})" + (f": {summary}" if summary else ""))
        lines.append("엣지:")
        if not g.edges:
            lines.append("  (없음)")
        for e in g.edges:
            handle = f" [{e.sourceHandle}]" if e.sourceHandle else ""
            lines.append(f"  {e.source} → {e.target}{handle}  ({e.id})")
        return "\n".join(lines)

    @tool
    def show_flow() -> str:
        """현재 flow(graph_data)를 사람이 읽는 텍스트로 보여준다.
        다른 도구를 쓰기 전에 노드 id·현재 구조를 확인할 때 사용한다."""
        return _render_flow()

    @tool
    def add_node(node_type: NodeType, data: Optional[Dict[str, Any]] = None) -> str:
        """새 노드를 flow에 추가한다. id는 자동 생성된다(n1, n2 ...).
        node_type별 data 필수 필드: promptNode→userPrompt, llmNode→model+systemPrompt,
        tokenizerNode→method(extract_text|chunk_pages), conditionNode→rules(id·operator·value 목록),
        httpRequestNode→method(GET|POST|PUT|DELETE)+url(headers/body는 선택),
        jsonParserNode→mode(parse|stringify|extract)(+extract면 extractKey), delayNode→seconds(숫자).
        startNode·outputNode는 data가 필요 없다.
        실패하면 사유가 반환되니 data를 고쳐서 이 도구를 다시 호출한다."""
        before = _snapshot()
        new_id = _next_id("n", [n.id for n in state["graph"].nodes])
        state["graph"].nodes.append(FlowNode(id=new_id, type=node_type, data=data or {}))
        return _commit_or_rollback(before, f"노드 {new_id}({node_type}) 추가됨")

    @tool
    def connect_nodes(source: str, target: str, sourceHandle: Optional[str] = None) -> str:
        """두 노드를 엣지로 연결한다(source→target). id는 자동 생성된다(e1, e2 ...).
        conditionNode에서 나가는 엣지만 sourceHandle에 해당 rule의 id 또는 "else"를 지정한다.
        그 외 노드에서 나가는 엣지는 sourceHandle을 비워둔다.
        주의(엔진 제약): conditionNode는 같은 핸들에 엣지를 1개까지만 연결 가능하고,
        promptNode는 llmNode에서 들어오는 엣지를 1개까지만 연결 가능하다 — 이미 있으면 실패한다."""
        before = _snapshot()
        new_id = _next_id("e", [e.id for e in state["graph"].edges])
        state["graph"].edges.append(FlowEdge(id=new_id, source=source, target=target, sourceHandle=sourceHandle))
        handle_note = f" [{sourceHandle}]" if sourceHandle else ""
        return _commit_or_rollback(before, f"엣지 {new_id}: {source} → {target}{handle_note}")

    @tool
    def update_node(node_id: str, data: Dict[str, Any]) -> str:
        """기존 노드의 data를 수정한다. 넘긴 필드만 기존 값 위에 병합되고 나머지 필드는 그대로 유지된다.
        노드의 type은 여기서 바꿀 수 없다 — type을 바꾸려면 delete_node 후 add_node를 쓴다."""
        g = state["graph"]
        node = next((n for n in g.nodes if n.id == node_id), None)
        if node is None:
            return _fail(f"실패: 노드 {node_id}를 찾을 수 없다")
        before = _snapshot()
        node.data = {**node.data, **data}
        return _commit_or_rollback(before, f"노드 {node_id} 갱신됨: {list(data.keys())}")

    @tool
    def delete_node(node_id: str) -> str:
        """노드 하나와 그 노드에 연결된 모든 엣지를 함께 삭제한다."""
        g = state["graph"]
        if not any(n.id == node_id for n in g.nodes):
            return _fail(f"실패: 노드 {node_id}를 찾을 수 없다")
        before = _snapshot()
        g.nodes = [n for n in g.nodes if n.id != node_id]
        g.edges = [e for e in g.edges if e.source != node_id and e.target != node_id]
        return _commit_or_rollback(before, f"노드 {node_id} 및 연결된 엣지 삭제됨")

    @tool("generate_flow")
    def _generate_flow_tool(request: str) -> str:
        """완전히 새로운 flow를 통째로 생성해서 기존 flow를 전부 대체한다.
        "~봇 만들어줘"처럼 처음부터 새로 만드는 요청에만 쓴다.
        기존 flow에 노드를 붙이거나 일부만 고치는 요청에는 add_node/connect_nodes/update_node를 쓴다."""
        g = generate_flow(request)  # 모듈 최상단의 ③ 생성 함수(LLM 호출) 재사용
        ok, errs = validate_flow(g)  # 완전한 그래프를 한 번에 만드므로 require_complete=True(기본값) 그대로
        if not ok:
            retry = f'{request}\n\n(직전 생성이 아래 이유로 잘못됐다. 고쳐서 다시: {"; ".join(errs)})'
            g = generate_flow(retry)
            ok, errs = validate_flow(g)
        if not ok:
            return _fail(f"생성 실패(기존 flow 유지): {errs}")
        state["graph"] = g
        return _succeed(f"새 플로우 생성됨: 노드 {len(g.nodes)}개, 엣지 {len(g.edges)}개")

    def get_current_graph() -> FlowGraph:
        """컨테이너의 최신 그래프를 반환. Phase 3/4가 에이전트 실행 후 최종 결과를 읽을 때 쓴다."""
        return state["graph"]

    tools = [show_flow, add_node, connect_nodes, update_node, delete_node, _generate_flow_tool]
    return tools, get_current_graph


# ── ⑨ Phase 3: create_agent 조립 + 한 턴 실행 ───────────────────────────────
# 설계 요약 (예나와 논의 확정, day1.md §7 create_agent 패턴 그대로):
#   - 에이전트 객체는 요청(대화 한 턴)마다 새로 만든다. Phase 2의 "요청별 그릇" 방식을
#     에이전트 조립까지 그대로 밀고 나간 것 — tools가 그 요청의 graph_data를 감싼 클로저라서,
#     에이전트도 그 tools에 맞춰 매번 새로 만들어야 한다.
#   - 대화 기억은 에이전트를 새로 만들어도 안 끊긴다. checkpointer(=InMemorySaver)가
#     thread_id로 메시지 히스토리를 별도 보관하기 때문 — **단, checkpointer 객체 자체는
#     매 요청마다 새로 만들면 안 되고 프로세스 전체에서 하나를 공유해야 한다**(안 그러면
#     매번 새 메모리가 생겨서 기억이 매번 리셋된다).
#   - 최종 완결성 게이트(require_complete=True)는 여기(Phase 3)에서 확인한다: 에이전트가
#     끝난 뒤 get_current_graph()로 그래프를 꺼내 validate_flow 통과분만 auto_layout해서 돌려주고,
#     실패하면 원래 받은 graph_data를 그대로 돌려줘서 캔버스가 미완성 상태로 안 넘어가게 한다.

AGENT_SYSTEM_PROMPT = (
    "너는 노코드 agent 빌더의 대화형 편집 도우미다. 사용자가 말로 flow(워크플로우)를 만들거나 "
    "고쳐달라고 하면 아래 도구를 써서 실제로 graph_data를 편집한다.\n\n"
    + NODE_CATALOG +
    "\n[도구 사용 지침]\n"
    "- 완전히 새로 만드는 요청(\"~봇 만들어줘\")에는 generate_flow를 쓴다.\n"
    "- 기존 flow에 붙이거나 일부만 고치는 요청에는 add_node/connect_nodes/update_node/delete_node를 쓴다.\n"
    "- 노드 id가 뭔지 확실하지 않으면 먼저 show_flow로 현재 상태를 확인하고 나서 편집한다.\n"
    "- 그래프 편집과 무관한 잡담(인사, 이 앱이 뭔지 설명 등)에는 도구를 부르지 말고 그냥 대화로 답한다.\n"
    "- 요청이 너무 모호해서 어떤 노드가 필요한지 판단할 수 없으면, 임의로 짐작해서 도구를 부르지 말고 "
    "먼저 무엇을 원하는지 구체적으로 되묻는다. 특히 대화가 길어져서 이전 요청들과 섞여 헷갈릴 수 있는 "
    "상황일수록(예: 여러 flow를 이미 만들어본 뒤) 짐작하지 말고 먼저 확인한다.\n"
    "- 도구 응답에 '⚠️ 연속 N회 실패' 경고가 붙으면, 같은 방식을 반복하지 말고 사용자에게 무엇이 "
    "막혔는지 설명하고 어떻게 할지 물어본다.\n"
    "\n[예시]\n"
    '- 사용자: "PDF 요약봇 만들어줘" → generate_flow("PDF 요약봇 만들어줘") 호출\n'
    '- 사용자: "요약 뒤에 번역 추가해줘" → show_flow로 현재 노드 확인 → add_node로 promptNode·llmNode 추가 → connect_nodes로 연결\n'
    '- 사용자: "모델을 gpt-4o로 바꿔줘" → show_flow로 llmNode id 확인 → update_node(그 id, {"model": "gpt-4o"})\n'
    '- 사용자: "안녕" → 도구 호출 없이 그냥 인사만 한다\n'
    '- 사용자: "뭔가 자동화해줘" (구체적인 목적·입력·출력이 없는 모호한 요청) → 도구를 부르지 않고 '
    '"어떤 작업을 자동화하고 싶으신가요? 예를 들어 문서 요약, 외부 API 연동, 정해진 시간마다 알림 보내기 '
    '등 목적을 알려주시면 그에 맞는 flow를 만들어드릴게요." 처럼 구체적으로 되묻는다. '
    "(실패 사례: 이 요청에 임의로 노드를 추가해서 기존 flow와 뒤섞인 적 있음 — 절대 짐작해서 만들지 말 것)\n"
    "# ↑ 초안 5개. 실패 사례 생기는 대로 팀원 C가 계속 보강할 자리."
)

# 프로세스 전체에서 공유해야 하는 checkpointer. 요청마다 새로 만들면 대화 기억이 매번 리셋되므로
# 지연 생성 후 재사용한다(모듈 전역 싱글턴). FastAPI 앱이라면 앱 시작 시 한 번만 만들어 주입해도 된다.
_default_checkpointer = None


def _get_default_checkpointer():
    global _default_checkpointer
    if _default_checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver
        _default_checkpointer = InMemorySaver()
    return _default_checkpointer


def build_agent(graph_data: FlowGraph, checkpointer=None):
    """이번 요청 전용 에이전트 + get_current_graph 접근자를 만든다. (tools, agent 둘 다 요청마다 새로 만듦.)"""
    from langchain.agents import create_agent

    tools, get_current_graph = make_tools(graph_data)
    agent = create_agent(
        get_llm(),
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer or _get_default_checkpointer(),
    )
    return agent, get_current_graph


def run_agent_turn(graph_data: dict, message: str, thread_id: str, checkpointer=None) -> Tuple[str, dict]:
    """대화 한 턴을 실행한다. /api/chat은 이 함수를 그대로 감싸기만 하면 된다.

    흐름: graph_data(raw dict, 프론트가 보낸 것) → FlowGraph로 파싱 → 이번 요청 전용 에이전트 조립
    → agent.invoke → 끝나면 최종 완결성 게이트(validate_flow, require_complete=True 기본값) →
    통과하면 auto_layout한 graph_data, 실패하면 원본 graph_data 그대로 반환.

    반환: (reply: str, graph_data: dict) — API 응답 {reply, graph_data}에 그대로 매핑된다.
    """
    g = FlowGraph(nodes=graph_data.get("nodes", []), edges=graph_data.get("edges", []))
    agent, get_current_graph = build_agent(g, checkpointer=checkpointer)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        {"configurable": {"thread_id": thread_id}},
    )
    reply = result["messages"][-1].content

    final_graph = get_current_graph()
    ok, errs = validate_flow(final_graph)  # require_complete=True(기본값) — 최종 완결성 게이트
    if ok:
        response_graph_data = auto_layout(final_graph)
    else:
        response_graph_data = graph_data  # 미완성이면 캔버스에 반영하지 않고 원본 그대로 유지
        reply += f"\n\n(⚠️ 아직 실행 가능한 상태가 아니라 캔버스에는 반영하지 않았습니다: {'; '.join(errs)})"

    return reply, response_graph_data


# ── 데모 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    req = "회의록 PDF를 올리면 할 일 목록을 뽑아주는 봇 만들어줘"
    print("요청:", req, "\n")
    graph = generate_safely(req)
    print(json.dumps(graph, ensure_ascii=False, indent=2))
