"""
meta_agent.py — "말로 만드는 Agent 빌더"의 메타 agent (MVP 골격)

자연어 요청 -> Flow JSON(graph_data) 생성/수정.
엔진·프론트(React Flow)는 이미 완성돼 있으므로, 이 모듈은 '올바른 graph_data'만 만들면 된다.

■ 구조 한눈에
  ① NODE_CATALOG    : LLM에게 주는 '노드 사용설명서' (지금은 핵심 18종, 나중에 한 줄씩 추가하면 확장)
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
■ 키:    OPENAI_API_KEY 환경변수(backend/.env) — get_llm()이 gpt-5.4-mini 기본 사용.
"""

from __future__ import annotations
import re
from typing import Literal, List, Dict, Any, Optional, Tuple, Callable
from collections import defaultdict, deque
from pydantic import BaseModel, Field


# httpRequestNode/webCrawlerNode의 url을 실제로 모를 때 쓰는 채움 표시자. validate_flow는
# url이 "비어있지 않은 문자열"이면 통과시키므로 스키마는 만족하면서도, 실행 엔진(node_generators/
# action_nodes.py)이 이 정확한 문자열을 보면 진짜 요청을 시도하지 않고 안내 메시지로 대체한다.
# 두 파일에서 정확히 같은 문자열을 써야 하므로 값을 바꿀 땐 action_nodes.py도 같이 바꿀 것.
PLACEHOLDER_URL = "REPLACE_WITH_ACTUAL_URL"

# ── ① 노드 카탈로그 (핵심 11종) ────────────────────────────────────────────
# 여기에 노드를 한 줄씩 추가하면 챗봇이 다룰 수 있는 노드가 늘어난다(P2 확장).
NODE_CATALOG = """\
[사용 가능한 노드 — 이 28종만 사용한다]
- startNode      : 플로우 시작점. data 없음. 모든 플로우는 이 노드에서 시작한다.
- scheduleNode   : 주기적으로 자동 실행되는 플로우의 시작점. data.cronExpression(문자열, 예: "0 7 * * *"). startNode 대신 사용한다.
- promptNode     : 사용자 프롬프트. data.userPrompt(문자열).
- llmNode        : LLM 호출. data.model(gemini-3.5-flash | gpt-4o-mini | claude-3-5-sonnet-20240620),
                   data.systemPrompt(문자열). 사용자가 모델을 특정하지 않으면 gpt-4o-mini를 기본값으로 쓴다.
- tokenizerNode  : 업로드 문서(PDF/PPTX/Excel/HWP)에서 텍스트 추출. data.method(extract_text | chunk_pages).
                   '문서/PDF/회의록 기반' 작업이면 llmNode 앞에 둔다. 직전 노드의 출력이 파일 경로여야 한다.
- templateAnalyzerNode: 서식 파일(.hwp/.hwpx/.xlsx/.pptx/텍스트) 안의 빈칸을 스캔해서 채워야 할 항목을
                   JSON으로 뽑아낸다(값은 안 채움, 빈칸 목록만). data.template_path(문자열, 파일 경로).
                   "{{이름}}" 같은 표시나 HWP 양식 필드를 자동으로 찾는다.
- fileModifierNode: templateAnalyzerNode가 찾아낸 빈칸을 실제 값으로 채워서 파일을 완성한다.
                   data.template_path(문자열, 원본 서식 파일 경로 — templateAnalyzerNode와 동일),
                   data.output_path(문자열, 선택 — 비우면 자동 생성). 채울 값은 자기 data가 아니라
                   직전 노드의 출력(JSON)에서 가져오므로, 반드시 그 JSON을 만들어주는 노드
                   (templateAnalyzerNode → llmNode/promptNode 조합이 일반적) 바로 뒤에 연결해야 한다 —
                   그렇지 않으면 에러 없이 빈칸이 하나도 안 채워진 원본이 그대로 저장된다.
- conditionNode  : 조건 분기. data.rules=[{"id":"r1", "operator":"=="|"Contains"|">"|"<"|">="|"<=", "value":"문자열"}].
                   분기 엣지는 sourceHandle에 해당 rule의 id(조건 통과) 또는 "else"(다 안 맞을 때)를 넣는다.
- distributorNode: 직전 노드의 출력을 리스트로 보고 하나씩 꺼내 뒤에 연결된 노드들을 항목 개수만큼
                   반복 실행시킨다(리스트가 아니면 1개짜리로 취급). data 없음. "각각에 대해",
                   "하나씩" 같은 요청에 쓴다.
- breakNode      : 반복을 즉시 멈춘다. data 없음. 반드시 distributorNode 하류(반복 구조 안)에서만
                   쓴다 — 반복 구조 밖에 두면 실행 자체가 SyntaxError로 깨진다. 보통 conditionNode와
                   짝을 이뤄 "특정 조건을 만나면 반복을 멈춘다"는 용도로 쓴다.
- webhookNode    : 외부 시스템의 Webhook 요청을 수신하는 진입점. data.method(GET|POST|PUT|DELETE 등), data.path(문자열, 엔드포인트 경로). startNode 대신 진입점으로 사용할 수 있다.
- httpRequestNode: 외부 API 호출. data.method(GET|POST|PUT|DELETE), data.url(문자열),
                   data.headers(JSON 문자열, 생략 가능), data.body(JSON 문자열, 생략 가능).
- jsonParserNode : JSON 파싱/변환. data.mode(parse|stringify|extract). extract일 때만 data.extractKey(문자열) 필요.
                   parse=문자열→JSON, stringify=JSON→문자열, extract=특정 키 값 꺼내기.
- databaseNode   : SQL 데이터베이스 조회/실행. data.connectionString(문자열, DB 접속정보 — 사용자가
                   실제로 준 값만 쓰고 없으면 지어내지 말고 물어본다), data.query(문자열, 실행할 SQL).
                   connectionString이나 query가 없으면 실행 시 에러가 난다.
- delayNode      : 지정한 시간만큼 대기 후 다음 노드로 진행. data.seconds(숫자).
- dynamicInputNode: 실행할 때마다 외부(호출자·디스코드 봇 메시지 등)에서 값을 받는 자리.
                   data.inputLabel(문자열, 이 입력이 뭔지 설명 — 요청 맥락에서 유추해 채운다),
                   data.testValue(문자열, 선택 — 에디터에서 미리보기/테스트 실행할 때만 쓰이는 예시값.
                   실제 배포 실행에서는 호출자가 넘긴 값으로 항상 대체되므로 "진짜 기본 메시지"가 아니다).
                   userPrompt처럼 flow에 고정 박히는 값이 필요하면 promptNode를 쓰고, "매번 다른 값을
                   입력받고 싶다"는 요청일 때만 이 노드를 쓴다.
- valueNode      : 실행할 때마다 항상 같은 고정값을 흐름에 넣는다(dynamicInputNode의 반대 — 매번
                   바뀌는 값이 아니라 고정값). data.file_path(문자열, 선택 — 고정 파일 경로) 또는
                   data.value(문자열, 선택 — 고정 텍스트) 중 하나를 쓴다. 파일 경로가 필요한 노드
                   (tokenizerNode 등) 앞에 "항상 이 파일" 식으로 붙이거나, 프롬프트에 고정 문구를
                   미리 넣어둘 때 쓴다.
- webCrawlerNode : URL의 웹페이지를 크롤링해 텍스트만 추출한다(5000자 제한). data.url(문자열, 선택 —
                   비워두면 직전 노드의 출력을 URL로 그대로 쓴다). 크롤링에 실패해도 워크플로우가
                   멈추지 않고 "Crawling failed: ..." 같은 에러 문자열이 다음 노드로 그냥 전달된다.
- emailNode      : 이메일 전송. data.toEmail(문자열, 받는사람), data.subject(문자열, 선택 — 기본값은
                   "Auto Flow 알림"). 본문은 직전 노드의 출력을 그대로 쓴다. SMTP 크리덴셜은 서버
                   배포 시점 .env 설정이 필요하다(챗봇이 채울 필드 아님) — 없으면 실행 시 실패한다.
- loopNode       : 반복을 제어한다. data.maxIterations(숫자, 기본 5). 하류 엣지는 sourceHandle을 쓴다:
                   'loop_start' (매 반복마다 실행할 흐름 시작), 'done' (반복이 모두 끝난 뒤 실행).
- multiAgentNode : 여러 에이전트를 조율한다. data.mode("supervisor" | "group_chat"). 
                   연결될 서브 에이전트(llmNode)는 엣지의 targetHandle을 "tools"로 설정하여 들어와야 한다.
- pythonNode     : 파이썬 코드를 실행한다. data.code(문자열, 파이썬 코드). 직전 노드의 출력이 'input_data' 변수에 담기며, 처리 결과를 'output_data' 변수에 할당해야 한다.
- discordNode    : 디스코드 메시지 발송. data.botToken(문자열), data.channelId(문자열, 선택). 직전 노드의 출력을 본문으로 발송한다.
- kakaoNode      : 카카오톡 알림톡/메시지 발송. data.accessToken(문자열, 사용자 제공), data.receiver(문자열, 선택 — 수신자 정보, 비우면 나에게 보내기). 직전 노드의 출력을 내용으로 발송한다.
- tossNode       : 토스페이먼츠 API 연동. data.secretKey(문자열), data.searchType(문자열, 'paymentKey' 또는 'orderId'), data.searchValue(문자열). 직전 노드의 결과를 검색 값으로 쓰거나 입력받아 결제 정보를 조회한다.
- slackNode      : 슬랙 메시지 발송. data.channel(문자열, 예: "#general"), data.message(문자열, 선택 — 직전 노드 출력과 함께 전송할 추가 메시지).
- humanApprovalNode : 사람의 승인 대기. data.message(문자열, 승인 요청 메시지). 워크플로우 진행을 일시 정지하고 사용자 승인을 기다린다.
- mergeNode      : 여러 흐름의 결과를 하나로 병합한다. data.mergeStrategy("join_newline" | "join_comma" | "array"). 여러 갈래의 엣지가 이 노드로 모일 수 있다.
- outputNode     : 결과 출력(종료). data 없음. 모든 플로우는 이 노드에서 끝난다.

[생성 원칙]
- discordNode를 생성할 때 사용자가 프롬프트에서 봇 토큰이나 Webhook URL을 명시적으로 알려주지 않았다면, 절대 임의의 가짜 값(예: "your-token", "1234")을 지어내서 채우지 말고 botToken과 channelId를 빈 문자열("")로 둔다. 그리고 반드시 답변에서 "디스코드 발송 노드를 구성했습니다. 실제 발송을 위해서는 화면에서 디스코드 노드를 클릭한 뒤, 본인의 봇 토큰(또는 웹훅 주소)을 직접 입력해 주세요."라고 친절하게 안내한다.
- httpRequestNode/webCrawlerNode를 새로 만들거나 기존 템플릿을 참고할 때, 실제로 호출 가능한 URL을
  모른다면(사용자가 안 줬고, 참고한 템플릿에도 url이 정확히 "REPLACE_WITH_ACTUAL_URL"로 남아있다면)
  절대 그럴듯해 보이는 가짜 URL을 지어내지 말고 url을 정확히 "REPLACE_WITH_ACTUAL_URL" 문자열
  그대로 둔다(빈 문자열 금지 — httpRequestNode는 빈 url이면 검증에서 막힌다). 그리고 반드시
  답변에서 "⚠️ OOO 노드에 실제 API 주소를 입력해 주셔야 이 부분이 정상 작동합니다."처럼 어떤
  노드에 뭘 채워야 하는지 구체적으로 안내한다 — 이 워크플로우를 실행하면 그 노드에서 "채워넣어야
  하는 필드가 있습니다. AI와 대화하는 창을 참고해주세요"라는 안내가 뜨는데, 사용자가 이 채팅
  창의 설명과 그 실행 결과 안내를 서로 연결할 수 있어야 하기 때문이다.
- dynamicInputNode의 testValue를 사용자가 명시적으로 주지 않았다면: 문맥에 맞는 그럴듯한 예시값을 채우거나
  (마땅치 않으면 비워둬도 된다), 반드시 답변에서 "사용자가 값을 안 줘서 예시로 OOO를 채웠다" 또는
  "예시가 마땅치 않아 비워뒀다"는 사실을 알려준다 — 실제 값이 아니라 미리보기용 임시값이라는 걸
  사용자가 착각하지 않게 하기 위함이다.
- webCrawlerNode의 url은 요청에 크롤링할 대상이 고정 문자열로 나와 있으면(예: "example.com 크롤링해줘")
  채우고, URL 자체가 이전 단계의 결과물(예: API 응답으로 받은 링크)이면 비워서 직전 노드 출력을
  그대로 쓰게 한다. 단, url을 비울 거면 반드시 URL을 실제로 만들어낼 노드를 바로 앞에 연결해야 한다 —
  url도 없고 직전 노드도 없거나 직전이 startNode뿐이면 실행 시 크롤링할 URL이 없어서 에러가 난다
  (Validator가 이 경우를 막는다).
- 반드시 startNode 또는 scheduleNode 중 정확히 1개로 시작하고, outputNode로 끝난다.
- 모든 노드는 start→output 경로 위에 있어야 한다. 어디에도 연결 안 된 고아 노드를 만들지 않는다.
- 사용자가 원하는 바를 충족하되, 불필요한 중복 노드를 만들지 않는다 — 필요한 만큼만 최소로 구성한다.
  단, "최소"를 이유로 요청에 필요한 단계(예: PDF 입력이면 tokenizerNode)를 빠뜨리면 안 된다.
- tokenizerNode는 직전 노드의 출력이 파일 경로일 때만 사용한다.
- distributorNode 뒤에 연결된 노드들은 리스트 항목 개수만큼 반복 실행된다는 걸 감안해서 구성한다.
- breakNode는 반드시 distributorNode 하류에서만 쓴다 — 반복 구조 밖에서 쓰면 실행이 깨진다.
- fileModifierNode는 반드시 JSON을 만들어주는 노드(templateAnalyzerNode → llmNode/promptNode 조합이
  일반적) 뒤에 연결한다 — 그렇지 않으면 빈칸이 하나도 안 채워진 채로 조용히 저장된다.
- promptNode는 항상 인접한 llmNode와 짝으로 사용한다.
- llmNode의 model은 사용자가 특정 모델을 요청하지 않는 한 기본값 gpt-4o-mini를 쓴다.
- 사용자의 요청이 짧거나 모호하더라도 가급적 되묻지 말고, 실무에서 흔히 쓰이는 자동화 패턴(예: 실패 시 알림, 조건에 따른 분기, 중요 작업 전 승인 등)을 유추하여 알아서 똑똑하게 비선형(분기, 반복, 병합 등) 워크플로우 초안을 구성한다. 사용자는 생성된 초안을 보고 나중에 수정하면 되므로, 챗봇이 주도적으로 풍부한 형태의 초안을 제시해야 한다.
- (미세수정 시) 기존 노드로 이미 처리 가능하면 새 노드를 추가하지 말고 update_node로 기존 노드를 고친다.
- **불필요한 중복 엣지(Edge) 연결 금지.** 목적지가 같은데 불필요하게 직행 경로와 우회 경로를 동시에 만들지 않는다(예: llm→output과 llm→delay→output을 동시에 연결하지 마라 — delay를 거치는 하나만 남긴다).
- **적극적인 비선형 구조 활용.** 조건 분기(conditionNode), 병렬 처리(하나의 노드에서 여러 노드로 동시에 분기), 반복 분배(distributorNode, loopNode) 등을 적극 활용하여 프로덕트급 파이프라인을 구축한다. 
- 여러 갈래로 병렬 처리된 흐름이 나중에 다시 합쳐져야 할 때는 반드시 `mergeNode`를 사용하여 안전하게 병합한다. (conditionNode의 조건 분기도 추후 합류 시 mergeNode 사용)

[연결 규칙]
- 순환(cycle) 금지. 노드는 앞에서 뒤로만 연결한다.
- 각 노드 id는 n1, n2 ... 처럼 유일하게. 엣지 id는 e1, e2 ...
- conditionNode에서 나가는 엣지만 sourceHandle이 필요(rule.id 또는 "else"). 나머지는 비워둔다.
- 노드마다 엣지 여러 개 허용 여부가 다르다(실행 엔진 동작 기준):
  · conditionNode는 같은 핸들(rule id 또는 else)에 엣지를 1개까지만 — 2개 이상이면 엔진이
    첫 번째만 쓰고 나머지는 조용히 버린다.
  · promptNode는 들어오는 llmNode 엣지를 1개까지만 — 2개 이상이면 어떤 모델이 쓰일지
    비결정적이 된다(엔진이 마지막 걸로 덮어씀).
  · 그 외 노드가 나가는 엣지를 여러 개 갖는 것(팬아웃) 자체는 문법적으로 가능하지만, 갈라진 경로가
    나중에 다시 모일 때는 반드시 mergeNode를 통해 합쳐야 한다. mergeNode 없이 임의의 노드(예: llmNode)로
    여러 갈래가 바로 합류하게 만들면 그 노드가 중복 실행되므로 절대 금지한다.
"""


# ── ② 출력 스키마 (형식 강제) ────────────────────────────────────────────
# type을 Literal로 묶어 11종 밖의 노드를 아예 못 만들게 한다. position(x,y)은
# LLM이 추측하면 안 되므로 항상 None으로 초기화하고, auto_layout에서 채운다.
NodeType = Literal[
    "startNode", "promptNode", "llmNode", "tokenizerNode", "conditionNode",
    "httpRequestNode", "jsonParserNode", "delayNode", "dynamicInputNode",
    "webCrawlerNode", "outputNode", "valueNode", "distributorNode", "breakNode",
    "templateAnalyzerNode", "fileModifierNode", "emailNode", "databaseNode",
    "loopNode", "multiAgentNode", "scheduleNode", "pythonNode", "discordNode",
    "kakaoNode", "slackNode", "humanApprovalNode", "mergeNode", "tossNode", "webhookNode"
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
    sourceHandle: Optional[str] = Field(default=None, description="조건 분기 rule 순번/'else', 또는 loopNode의 'loop_start'/'done'")
    targetHandle: Optional[str] = Field(default=None, description="multiAgentNode에 서브에이전트 연결 시 'tools'로 지정")


class FlowGraph(BaseModel):
    nodes: List[FlowNode]
    edges: List[FlowEdge]


# ── LLM 준비 (제공자 교체 지점) ──────────────────────────────────────────
def get_llm():
    """메타 agent가 쓸 LLM. 현재 OpenAI. 제공자 교체는 여기만 바꾸면 된다.
    gpt-5 계열 reasoning 모델은 temperature 파라미터를 거부/무시하므로 넘기지 않는다."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-5.4-mini")
    # Gemini로 되돌리려면 위 두 줄 대신:
    # from langchain_google_genai import ChatGoogleGenerativeAI
    # return ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)


SYSTEM = (
    "너는 노코드 agent 빌더의 설계 도우미다. 사용자의 요청을 읽고, "
    "아래 노드만으로 실행 가능한 워크플로우(graph_data)를 만든다.\n\n" + NODE_CATALOG
)

# Medium 모드 전용 시스템 프롬프트 — 템플릿 구조를 유지하면서 파라미터만 수정
MEDIUM_SYSTEM = (
    "너는 노코드 agent 빌더의 설계 도우미다. 아래에 주어진 **기존 워크플로우 템플릿**의 "
    "구조(노드 배치, 엣지 연결, 분기/병합/반복 패턴)를 골격으로 삼아, "
    "노드의 data(프롬프트, URL, 이메일, 시스템 프롬프트 등 파라미터)만 "
    "사용자의 요청에 맞게 수정해서 새 워크플로우를 만든다.\n\n"
    "**반드시 지켜야 할 원칙:**\n"
    "1. 템플릿의 비선형 구조(conditionNode 분기, mergeNode 병합, distributorNode/loopNode 반복, "
    "humanApprovalNode 승인 등)를 최대한 유지하라. 단순 선형으로 축소하지 마라.\n"
    "2. 노드의 type과 엣지 연결은 가급적 그대로 유지하되, data 필드의 값(userPrompt, systemPrompt, "
    "url, toEmail, channel, rules의 value 등)을 사용자 요청의 맥락에 맞게 바꿔라.\n"
    "3. 사용자가 짧게 말해도, 이 템플릿의 풍부한 구조가 프로덕트급 워크플로우의 뼈대이다. "
    "절대 단순화하지 마라.\n"
    "4. 단, 사용자 요청에 반드시 필요하지만 템플릿에 없는 노드는 추가해도 되고, "
    "요청과 완전히 무관한 노드는 제거해도 된다.\n"
    "5. 노드 id(n1, n2...), 엣지 id(e1, e2...)는 다시 매길 수 있다.\n\n"
    + NODE_CATALOG
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

[예시3] 요청: "매번 다른 문장을 입력받아 한국어로 번역하고, 3초 후에 결과를 보여주는 봇 만들어줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"번역할 문장","testValue":"Hello, how are you?"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 문장을 한국어로 번역해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 번역 전문가다"}},
  {"id":"n5","type":"delayNode","data":{"seconds":3}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
# ↑ n4에서 n6(output)으로 가는 직행 엣지를 따로 만들지 않는다 — delayNode를 거치는 경로 하나만 남긴다
# (기본은 단일 경로 원칙). testValue는 사용자가 안 준 예시이므로 답변에서 그 사실을 알려준다.

[예시4] 요청: "https://example.com/news 내용 요약해줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://example.com/news"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 웹페이지 내용을 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n5","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ url이 요청에 고정으로 나와 있으므로 data.url을 채운다. 만약 URL이 이전 단계 결과물(예:
# httpRequestNode의 응답에서 뽑아낸 링크)이라면 url은 비우고, 그 노드를 webCrawlerNode 바로
# 앞에 연결한다(비우면서 앞에 아무 노드도 없거나 startNode뿐이면 Validator가 막는다).

[예시5] 요청: "https://api.example.com/articles 에서 글 목록을 받아와서 각각 한국어로 요약해줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"https://api.example.com/articles"}},
  {"id":"n3","type":"jsonParserNode","data":{"mode":"parse"}},
  {"id":"n4","type":"distributorNode","data":{}},
  {"id":"n5","type":"promptNode","data":{"userPrompt":"다음 글을 한국어로 요약해줘"}},
  {"id":"n6","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n7","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"},
  {"id":"e6","source":"n6","target":"n7"}
]}
# ↑ distributorNode(n4) 뒤에 연결된 n5~n7은 글 목록 개수만큼 반복 실행된다.

[예시6] 요청: "계약서_템플릿.hwp 파일의 빈칸을 채워서 완성해줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"templateAnalyzerNode","data":{"template_path":"계약서_템플릿.hwp"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 JSON의 각 키에 대해 문맥에 맞는 값을 채워서 같은 형식의 JSON으로만 답해"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 문서 양식을 채우는 도우미다. 반드시 JSON 형식으로만 답한다"}},
  {"id":"n5","type":"fileModifierNode","data":{"template_path":"계약서_템플릿.hwp"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
# ↑ fileModifierNode(n5)가 채울 값은 자기 data가 아니라 직전 노드(n4, llmNode가 만든 JSON)에서 온다.
# templateAnalyzerNode(n2) 없이 fileModifierNode를 바로 쓰면 채울 JSON이 없어 원본이 그대로 저장된다.

[예시7] 요청: "https://example.com/news 내용을 요약해서 team@company.com으로 메일 보내줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://example.com/news"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 뉴스를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"team@company.com","subject":"뉴스 요약"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}

[예시8] 요청: "customers 테이블에서 이메일만 뽑아서 보여줘 (DB 접속정보: postgresql://user:pass@localhost:5432/shop)"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"databaseNode","data":{"connectionString":"postgresql://user:pass@localhost:5432/shop","query":"SELECT email FROM customers"}},
  {"id":"n3","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"}
]}
# ↑ connectionString은 요청에 실제로 준 값을 그대로 쓴다 — 안 주면 지어내지 말고 물어본다.

[예시9] 요청: "사용자 요청을 번역, 요약, 감성 분석 에이전트에게 보내서 알아서 처리하게 해주는 매니저 봇을 만들어줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"promptNode","data":{"userPrompt":"사용자의 요청을 처리할 에이전트를 선택해"}},
  {"id":"n3","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"번역을 담당합니다."}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"요약을 담당합니다."}},
  {"id":"n5","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"감성 분석을 담당합니다."}},
  {"id":"n6","type":"multiAgentNode","data":{"mode":"supervisor"}},
  {"id":"n7","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n6"},
  {"id":"e3","source":"n3","target":"n6","targetHandle":"tools"},
  {"id":"e4","source":"n4","target":"n6","targetHandle":"tools"},
  {"id":"e5","source":"n5","target":"n6","targetHandle":"tools"},
  {"id":"e6","source":"n6","target":"n7"}
]}
# ↑ multiAgentNode(n6)로 들어오는 llmNode 서브 에이전트들(n3,n4,n5)의 엣지에는 반드시 targetHandle:"tools"를 지정해야 한다.

[예시10] 요청: "다음 문장을 3번 반복해서 요약해줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"loopNode","data":{"maxIterations":3}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 문장을 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"요약 전문가"}},
  {"id":"n5","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3","sourceHandle":"loop_start"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n2"},
  {"id":"e5","source":"n2","target":"n5","sourceHandle":"done"}
]}
# ↑ loopNode에서 반복할 흐름의 시작은 sourceHandle:"loop_start", 반복 종료 후 나가는 흐름은 sourceHandle:"done"을 쓴다.

[예시11] 요청: "매일 아침 9시에 날씨를 요약해서 이메일로 보내줘"
{"nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"https://api.example.com/weather"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 날씨 정보를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"날씨 전문가"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"me@example.com","subject":"오늘의 날씨"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
# ↑ 정기적으로 실행해야 하므로 startNode 대신 scheduleNode(cronExpression 포함)로 시작한다.

[예시12] 요청: "매일 아침에 해커뉴스 크롤링해서 좋은 글 있으면 요약해서 카카오톡으로 보내줘"
{"nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://news.ycombinator.com"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 뉴스들 중에서 IT 업계 트렌드에 맞는 '좋은 글'이 있는지 판별하고 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"뉴스 큐레이터"}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"r1","operator":"Contains","value":"좋은 글 있음"}]}},
  {"id":"n6","type":"humanApprovalNode","data":{"message":"카카오톡으로 발송할까요?"}},
  {"id":"n7","type":"kakaoNode","data":{"receiver":""}},
  {"id":"n8","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n9","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"r1"},
  {"id":"e6","source":"n6","target":"n7"},
  {"id":"e7","source":"n7","target":"n8"},
  {"id":"e8","source":"n5","target":"n8","sourceHandle":"else"},
  {"id":"e9","source":"n8","target":"n9"}
]}
# ↑ 짧은 요청이지만 조건 분기(conditionNode), 사람 승인(humanApprovalNode), 카카오톡 발송(kakaoNode), 병합(mergeNode)을 알아서 적절히 구성했다.

[예시13] 요청: "메일 들어오면 감성 분석해서 악플이면 슬랙으로 알림 보내고, 아니면 디스코드로 보내줘"
{"nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"수신된 이메일 내용","testValue":"이 서비스 정말 최악이네요. 환불해주세요."}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 내용이 악플(부정적)인지 판단해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"감성 분석가"}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"r1","operator":"Contains","value":"부정적"}]}},
  {"id":"n6","type":"slackNode","data":{"channel":"#alerts","message":"악플이 접수되었습니다!"}},
  {"id":"n7","type":"discordNode","data":{"botToken":"","channelId":""}},
  {"id":"n8","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n9","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"r1"},
  {"id":"e6","source":"n5","target":"n7","sourceHandle":"else"},
  {"id":"e7","source":"n6","target":"n8"},
  {"id":"e8","source":"n7","target":"n8"},
  {"id":"e9","source":"n8","target":"n9"}
]}
# ↑ 갈라졌던 엣지들(n6->n8, n7->n8)이 mergeNode로 정상적으로 합류했다.
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


def generate_flow_from_template(user_request: str, template: FlowGraph) -> FlowGraph:
    """Medium 모드 전용: Pre-translated DB에서 가져온 템플릿의 구조를 골격으로 유지하면서
    파라미터만 사용자 요청에 맞게 수정한다.

    템플릿이 비선형(분기/병합/반복)이면 결과도 자연스럽게 비선형 구조를 유지한다.
    사용자가 짧게 말해도 프로덕트급 워크플로우가 나오는 핵심 메커니즘."""
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o", temperature=0).with_structured_output(FlowGraph, method="function_calling")
    messages = [
        ("system", MEDIUM_SYSTEM),
        ("user",
         f"아래는 참고할 워크플로우 템플릿이다:\n{template.model_dump_json()}\n\n"
         f'이 템플릿의 구조(노드 타입 배치, 엣지 연결, 분기/병합/반복 패턴)를 **절대 단순화하지 말고 최대한 유지**하면서, '
         f'노드의 data 필드(프롬프트, URL, 이메일 등)만 다음 사용자 요청에 맞게 수정해줘: "{user_request}"\n'
         f'(주의: 기존 템플릿의 노드들을 함부로 삭제하지 말고 구조를 보존하라)'),
    ]
    return _strip_positions(llm.invoke(messages))


# 정밀 모드 전용 시스템 프롬프트 — 템플릿 없이, 요청을 더 꼼꼼히 해석해서 살을 붙여 만든다
PRECISE_SYSTEM = (
    "너는 노코드 agent 빌더의 설계 전문가다. 사용자의 요청을 읽고, "
    "아래 노드만으로 실행 가능한 프로덕트급 워크플로우(graph_data)를 만든다.\n\n"
    "**반드시 지켜야 할 원칙:**\n"
    "1. 사용자가 짧게 말해도 뼈대만 만들지 마라. 요청의 의도를 꼼꼼히 해석해서, "
    "실제 서비스로 바로 쓸 수 있는 수준까지 살을 붙여라 — 필요하다면 데이터 가공, "
    "조건 분기, 에러/예외 상황 처리, 결과 알림 같은 보조 노드도 스스로 판단해서 추가하라.\n"
    "2. 단, 카탈로그에 없는 노드 타입을 상상해서 만들지 말고, 항상 아래 노드 목록 안에서만 조합하라.\n"
    "3. 단순 선형 구조로 뭉뚱그리지 말고, 요청 성격에 맞으면 분기/병합/반복 구조를 적극 활용하라.\n\n"
    + NODE_CATALOG
)


def generate_flow_precise(user_request: str) -> FlowGraph:
    """정밀 모드 전용: 템플릿 검색 없이, 사용자 요청을 더 꼼꼼히 해석해서
    프로덕트급 수준으로 살을 붙여 생성한다."""
    llm = get_llm().with_structured_output(FlowGraph, method="function_calling")
    messages = [
        ("system", PRECISE_SYSTEM + "\n\n" + FEWSHOT),
        ("user", f'요청: "{user_request}"\n위 규칙에 맞는, 실제 서비스 수준으로 구체화된 graph_data를 만들어줘.'),
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
LOOP_PRODUCING_NODE_TYPES = {"distributorNode"}  # breakNode가 유효하려면 상류에 이 중 하나가 있어야 한다(추후 loopNode 등 추가 시 여기에 더한다)


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
      9) conditionNode가 아닌 노드에서 갈라진 경로 여러 개가 같은 하류 노드에서 다시 합쳐지면 안 됨
         (예: llm→output 직행 + llm→delay→output 경유가 동시에 존재 — merge 기능이 없어 그 노드가
         중복 실행된다). 기본은 단일 경로이고, 이 재합류만 예외적으로 허용된다.
      10) webCrawlerNode의 data.url이 비어있으면, 실행 시 직전 노드의 출력을 URL로 대신 쓴다
          (실행 엔진 확인 결과). 그런데 연결된 이전 노드가 아예 없거나, 직전 노드가 아무 값도
          만들지 않는 startNode뿐이면 URL을 얻을 방법이 없어 "No URL provided" 에러로 빠진다 —
          이 경우를 막는다.
      11) breakNode는 상류(backward)에 distributorNode가 없으면 에러 — 파이썬 break는 반복문 밖에
          있으면 SyntaxError로 실행 자체가 깨진다(조용한 버그가 아니라 즉시 크래시).
      12) fileModifierNode는 채울 값을 항상 직전 노드의 출력(JSON)에서 가져온다(자기 data엔 값이
          없음). 연결된 이전 노드가 없거나 직전 노드가 startNode뿐이면 채울 JSON이 없어 에러 없이
          빈칸이 하나도 안 채워진 원본이 그대로 저장된다(webCrawlerNode의 10)과 달리 우회 필드가
          없어 항상 검사한다).
      13) outputNode에서 나가는 엣지가 있으면 안 됨 — outputNode는 실행 엔진에서 즉시 return하는
          노드라(generate_output_node 확인 결과) 그 뒤에 연결된 노드는 절대 실행되지 않는다(죽은 코드).
          템플릿 기반 생성 시 원본 템플릿의 무관한 잔여 노드가 지워지지 않고 outputNode 뒤에 그대로
          매달리는 사례가 실제로 발견됨 — 그래프 편집기에는 "연결"된 것처럼 보여서 눈치채기 어렵다.
      14) 고아 노드 — 시작 노드(startNode/scheduleNode/webhookNode)가 아닌데 들어오는 엣지가 하나도
          없으면 영원히 실행될 방법이 없다. multiAgentNode/fileModifierNode에 targetHandle이
          'tools'/'template'인 엣지의 소스는 예외(그래프 컴파일러도 이 핸들은 제어 흐름이 아닌
          배선으로 취급해 별도로 다룬다).                    ← require_complete=True일 때만

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
        start_count = types.count("startNode") + types.count("scheduleNode") + types.count("webhookNode")
        if start_count != 1:
            errors.append(f"시작 노드(startNode, scheduleNode 또는 webhookNode)는 정확히 1개여야 한다 (현재 {start_count}개)")
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
                
        elif source_node.type == "loopNode":
            if e.sourceHandle not in ("loop_start", "done"):
                errors.append(f"엣지 {e.id}: loopNode {source_node.id}에서 나가는 엣지는 sourceHandle이 'loop_start' 또는 'done'이어야 한다 (현재: {e.sourceHandle})")
            else:
                handle_edge_count[(source_node.id, e.sourceHandle)] += 1

        target_node = nodes_by_id.get(e.target)
        if target_node and target_node.type == "multiAgentNode":
            if source_node.type == "llmNode":
                if e.targetHandle != "tools":
                    errors.append(f"엣지 {e.id}: multiAgentNode {target_node.id}로 연결되는 서브 에이전트(llmNode {source_node.id})는 targetHandle이 'tools'여야 한다")

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

    # 9) 재합류(diamond) 감지 — conditionNode가 아닌 노드에서 갈라진 경로 여러 개가
    # 같은 하류 노드에서 다시 합쳐지는지 검사. (실행 엔진에 merge 기능이 없어서, 이런 구조가 있으면
    # 그 하류 노드가 여러 번 실행/출력된다. conditionNode의 분기는 런타임에 하나만 타므로 예외.)
    forward: Dict[str, List[str]] = defaultdict(list)
    for e in g.edges:
        forward[e.source].append(e.target)

    def _reachable_from(start: str) -> set:
        seen: set = set()
        stack = [start]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            u_node = nodes_by_id.get(u)
            if u_node and u_node.type == "mergeNode":
                continue  # mergeNode 이후로는 병합된 단일 경로로 취급하므로 탐색 중지
            stack.extend(forward.get(u, []))
        return seen

    reported_diamonds: set = set()
    for n in g.nodes:
        if n.type == "conditionNode":
            continue
        children = forward.get(n.id, [])
        if len(children) < 2:
            continue
        reach = {c: _reachable_from(c) for c in children}
        for i in range(len(children)):
            for j in range(i + 1, len(children)):
                c1, c2 = children[i], children[j]
                shared = reach[c1] & reach[c2]
                shared = {s for s in shared if nodes_by_id.get(s) and nodes_by_id[s].type != "mergeNode"}
                if shared:
                    key = (n.id, c1, c2)
                    if key in reported_diamonds:
                        continue
                    reported_diamonds.add(key)
                    errors.append(
                        f"{n.id}에서 나간 경로 여러 개({c1}, {c2} 방향)가 {', '.join(sorted(shared))}에서 "
                        "다시 합쳐진다 — merge 기능이 없어 해당 노드가 중복 실행된다. 여러 갈래를 합치려면 "
                        "반드시 mergeNode를 사이에 두어 병합해라."
                    )

    # 10) webCrawlerNode: url이 비어있으면 직전 노드가 실제로 URL을 줄 수 있어야 한다
    # (실행 엔진 확인 결과: url이 없으면 prev_res_var를 URL로 쓰는데, startNode 바로 다음이거나
    # incoming 엣지가 아예 없으면 prev_res_var가 없어서 "No URL provided" 에러로 빠진다)
    for n in g.nodes:
        if n.type != "webCrawlerNode" or (n.data or {}).get("url"):
            continue
        incoming_sources = [nodes_by_id[e.source] for e in g.edges if e.target == n.id and e.source in nodes_by_id]
        if not incoming_sources:
            errors.append(
                f"{n.id}(webCrawlerNode)에 url이 없고 연결된 이전 노드도 없다 — "
                "url을 채우거나 URL을 출력하는 노드를 앞에 연결하라"
            )
        elif all(s.type == "startNode" for s in incoming_sources):
            errors.append(
                f"{n.id}(webCrawlerNode)에 url이 없고 직전 노드가 startNode뿐이라 실행 시 URL을 얻을 수 없다 — "
                "url을 채우거나 URL을 출력하는 노드를 startNode와 사이에 연결하라"
            )

    # 11) breakNode: 상류(backward)에 distributorNode(반복을 만드는 노드)가 있어야 한다
    # (파이썬 break는 반복문 밖에 있으면 SyntaxError로 실행 자체가 깨진다 — 조용한 버그가 아니라 즉시 크래시)
    for n in g.nodes:
        if n.type != "breakNode":
            continue
        if not _has_upstream_type(n.id, g, LOOP_PRODUCING_NODE_TYPES):
            errors.append(
                f"{n.id}(breakNode)의 상류에 distributorNode(반복을 만드는 노드)가 없다 — "
                "반복 구조 밖에서 break를 쓰면 실행이 SyntaxError로 깨진다. distributorNode 하류에 연결하라"
            )

    # 12) fileModifierNode: 채울 값을 항상 직전 노드의 출력(JSON)에서 가져온다(자기 data엔 값이 없음).
    # webCrawlerNode의 10)과 달리 우회 필드가 없어 url이 비었는지 여부와 상관없이 항상 검사한다.
    for n in g.nodes:
        if n.type != "fileModifierNode":
            continue
        incoming_sources = [nodes_by_id[e.source] for e in g.edges if e.target == n.id and e.source in nodes_by_id]
        if not incoming_sources:
            errors.append(
                f"{n.id}(fileModifierNode)에 연결된 이전 노드가 없다 — 채울 값(JSON)을 만들어주는 노드"
                "(templateAnalyzerNode → llmNode/promptNode 조합 등)를 앞에 연결하라"
            )
        elif all(s.type == "startNode" for s in incoming_sources):
            errors.append(
                f"{n.id}(fileModifierNode)의 직전 노드가 startNode뿐이라 채울 JSON을 얻을 수 없다 — "
                "templateAnalyzerNode 등 JSON을 만들어주는 노드를 사이에 연결하라"
            )

    # 3) 순환(cycle)
    has_cycle, stuck = _has_cycle(ids, g.edges)
    if has_cycle:
        errors.append(f"순환(cycle)이 있다 — 관련 노드: {', '.join(stuck)} (노드는 앞으로만 연결해야 한다)")

    # 13) outputNode에서 나가는 엣지 금지 — 뒤에 뭘 연결해도 실행 엔진이 절대 안 탄다(죽은 코드)
    for e in g.edges:
        source_node = nodes_by_id.get(e.source)
        if source_node and source_node.type == "outputNode":
            errors.append(
                f"엣지 {e.id}: outputNode {source_node.id}에서 나가는 엣지가 있다 — "
                "outputNode는 결과를 즉시 반환하고 끝나서 그 뒤에 연결된 노드는 절대 실행되지 않는다. "
                "필요 없는 노드면 삭제하고, 필요하면 outputNode보다 앞으로 연결을 옮겨라"
            )

    # 14) 고아 노드 — 시작 노드가 아닌데 들어오는 엣지가 하나도 없음(require_complete일 때만:
    # add_node 등으로 그리는 중에는 아직 안 이어진 노드가 정상적으로 있을 수 있다)
    if require_complete:
        start_types = {"startNode", "scheduleNode", "webhookNode"}
        targets_with_incoming = {e.target for e in g.edges}
        tool_or_template_sources = {e.source for e in g.edges if e.targetHandle in ("tools", "template")}
        for n in g.nodes:
            if n.type in start_types or n.id in tool_or_template_sources:
                continue
            if n.id not in targets_with_incoming:
                errors.append(
                    f"{n.id}({n.type})는 시작 노드가 아닌데 들어오는 엣지가 없다 — "
                    "고아 노드라 절대 실행되지 않는다. 앞 노드에 연결하거나 필요 없으면 삭제하라"
                )

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

    elif n.type == "pythonNode":
        if "code" not in d:
            errors.append(f"{n.id}(pythonNode)에 code가 없다")
            
    elif n.type == "discordNode":
        if "botToken" not in d:
            errors.append(f"{n.id}(discordNode)에 botToken이 없다")
        elif d.get("botToken") and not d.get("botToken", "").startswith("http"):
            if not d.get("channelId"):
                errors.append(f"{n.id}(discordNode)가 Webhook이 아닌 봇 토큰 방식일 때는 channelId가 필수다")

    elif n.type == "slackNode":
        if "channel" not in d:
            errors.append(f"{n.id}(slackNode)에 channel이 없다")
            
    elif n.type == "mergeNode":
        strategy = d.get("mergeStrategy")
        if strategy and strategy not in ["join_newline", "join_comma", "array"]:
            errors.append(f"{n.id}(mergeNode)의 mergeStrategy '{strategy}'는 허용되지 않는다")

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

    elif n.type == "templateAnalyzerNode":
        if not d.get("template_path"):
            errors.append(f"{n.id}(templateAnalyzerNode)에 template_path가 없다")

    elif n.type == "fileModifierNode":
        if not d.get("template_path"):
            errors.append(f"{n.id}(fileModifierNode)에 template_path가 없다")

    elif n.type == "emailNode":
        if not d.get("toEmail"):
            errors.append(f"{n.id}(emailNode)에 toEmail이 없다")

    elif n.type == "loopNode":
        max_iter = d.get("maxIterations", 5)
        try:
            int(max_iter)
        except (TypeError, ValueError):
            errors.append(f"{n.id}(loopNode)의 maxIterations는 숫자여야 한다 (현재: {max_iter!r})")

    elif n.type == "scheduleNode":
        if not d.get("cronExpression"):
            errors.append(f"{n.id}(scheduleNode)에 cronExpression이 없다")

    elif n.type == "multiAgentNode":
        mode = d.get("mode")
        if mode not in ("supervisor", "group_chat"):
            errors.append(f"{n.id}(multiAgentNode)의 mode는 'supervisor' 또는 'group_chat'이어야 한다 (현재: {mode!r})")

    # TODO(가드레일 미구현 — 2026-07-15 예나 결정: 리스크 알고 지금은 제약 없이 추가함, 나중에 추가할 것):
    #   1) query가 SELECT로 시작하지 않으면 에러 처리(INSERT/UPDATE/DELETE/DROP/ALTER 등 차단)
    #   2) AGENT_SYSTEM_PROMPT에 "파괴적 쿼리는 실행 전 사용자 확인" 지시 추가
    #      (generate_flow는 구조화 출력 강제라 되묻기 불가 — ReAct 에이전트 도구 호출 레이어에서만 가능)
    #   3) show_flow/_summarize_node_data에서 connectionString 마스킹(현재는 평문 노출)
    elif n.type == "databaseNode":
        if not d.get("connectionString"):
            errors.append(f"{n.id}(databaseNode)에 connectionString이 없다")
        if not d.get("query"):
            errors.append(f"{n.id}(databaseNode)에 query가 없다")

    # startNode·outputNode·valueNode·distributorNode·breakNode는 data가 없어도(또는 비어있어도)
    # 실행이 깨지지 않으므로 필수 필드 에러로 보진 않는다.
    return errors


def _condition_handles(n: FlowNode) -> set:
    """conditionNode가 가질 수 있는 sourceHandle 전체 집합 = rule id들 + 'else'."""
    rules = (n.data or {}).get("rules") or []
    return {r.get("id") for r in rules if r.get("id")} | {"else"}


def _has_upstream_type(target_id: str, g: FlowGraph, wanted_types: set) -> bool:
    """target_id로 들어오는 엣지를 거꾸로(backward) 타고 올라가며, wanted_types에 속하는 타입의
    노드를 만나면 True. breakNode가 distributorNode 하류(반복 구조 안)에 있는지 확인하는 용도."""
    backward: Dict[str, List[str]] = defaultdict(list)
    for e in g.edges:
        backward[e.target].append(e.source)
    nodes_by_id = {n.id: n for n in g.nodes}
    seen: set = set()
    stack = list(backward.get(target_id, []))
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        node = nodes_by_id.get(u)
        if node and node.type in wanted_types:
            return True
        stack.extend(backward.get(u, []))
    return False


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
    if node_type == "dynamicInputNode":
        test_val = data.get("testValue", "")
        return f"inputLabel={data.get('inputLabel', '')!r}, testValue={test_val!r}" + (
            " (비어있음 — 예시값 없음)" if not test_val else " (예시/미리보기용, 실제 실행 값 아님)"
        )
    if node_type == "webCrawlerNode":
        url = data.get("url", "")
        return f"url={url!r}" + (" (비어있음 — 직전 노드 출력을 URL로 사용)" if not url else "")
    if node_type == "valueNode":
        file_path = data.get("file_path", "")
        return f"file_path={file_path!r}" if file_path else f"value={data.get('value', '')!r}"
    if node_type == "templateAnalyzerNode":
        return f"template_path={data.get('template_path', '')!r}"
    if node_type == "fileModifierNode":
        return f"template_path={data.get('template_path', '')!r}, output_path={data.get('output_path', '')!r}"
    if node_type == "emailNode":
        return f"toEmail={data.get('toEmail', '')!r}, subject={data.get('subject', '')!r}"
    if node_type == "databaseNode":
        return f"connectionString={data.get('connectionString', '')!r}, query={data.get('query', '')!r}"
    if node_type == "pythonNode":
        code_preview = data.get("code", "")[:30].replace("\n", " ") + "..."
        return f"code={code_preview!r}"
    if node_type == "discordNode":
        return f"botToken={'Webhook' if data.get('botToken', '').startswith('http') else 'BotToken'}, channelId={data.get('channelId', '')!r}"
    if node_type == "kakaoNode":
        return f"receiver={data.get('receiver', '')!r}"
    if node_type == "slackNode":
        return f"channel={data.get('channel', '')!r}, message={data.get('message', '')!r}"
    if node_type == "humanApprovalNode":
        return f"message={data.get('message', '')!r}"
    if node_type == "mergeNode":
        return f"mergeStrategy={data.get('mergeStrategy', 'join_newline')!r}"
    if node_type == "loopNode":
        return f"maxIterations={data.get('maxIterations', 5)}"
    if node_type == "multiAgentNode":
        return f"mode={data.get('mode', '')!r}"
    if node_type == "scheduleNode":
        return f"cronExpression={data.get('cronExpression', '')!r}"
    return ""


def _dynamic_input_note(n: FlowNode) -> Optional[str]:
    """dynamicInputNode 하나에 대해 testValue 상태를 있는 그대로 알려주는 문장을 만든다.
    도구(add_node/update_node/generate_flow)의 반환 문자열에 붙여서, 에이전트가 답변에서
    '예시값을 채웠다/못 채워서 비워뒀다'는 사실을 실제 데이터 그대로(추측 없이) 전달하게 한다."""
    if n.type != "dynamicInputNode":
        return None
    test_val = (n.data or {}).get("testValue", "")
    if test_val:
        return f"{n.id}(dynamicInputNode)의 testValue를 예시로 {test_val!r}로 채웠다 — 실제 실행 값이 아니라 미리보기용 예시임을 답변에서 알려줄 것"
    return f"{n.id}(dynamicInputNode)에 마땅한 예시가 없어 testValue를 비워뒀다 — 실제 실행 시 호출자가 넘긴 값으로 채워짐을 답변에서 알려줄 것"


def make_tools(initial_graph: FlowGraph, complexity_level: str = "low") -> Tuple[List, Callable[[], FlowGraph]]:
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
        jsonParserNode→mode(parse|stringify|extract)(+extract면 extractKey), delayNode→seconds(숫자),
        dynamicInputNode→inputLabel(문자열)+testValue(문자열, 선택 — 미리보기용 예시일 뿐 실제 실행값 아님),
        webCrawlerNode→url(문자열, 선택 — 비우면 직전 노드 출력을 URL로 사용하는데, 그러려면 반드시
        URL을 실제로 만들어내는 노드가 바로 앞에 연결돼 있어야 한다).
        valueNode→file_path 또는 value(둘 다 문자열, 선택 — 실행마다 항상 같은 고정값),
        distributorNode/breakNode→data 없음(breakNode는 반드시 distributorNode 하류에 연결해야 함,
        아니면 실행이 SyntaxError로 깨짐), templateAnalyzerNode→template_path(문자열),
        fileModifierNode→template_path(문자열)+output_path(문자열, 선택) — 반드시 JSON을 만들어주는
        노드(templateAnalyzerNode→llmNode 조합 등) 바로 뒤에 연결해야 한다(직전 노드 의존).
        emailNode→toEmail(문자열)+subject(문자열, 선택), databaseNode→connectionString(문자열,
        사용자가 준 값만 사용)+query(문자열, SQL — 아직 SELECT 강제 등 가드레일 없음, 주의해서 사용).
        startNode·outputNode는 data가 필요 없다.
        실패하면 사유가 반환되니 data를 고쳐서 이 도구를 다시 호출한다."""
        before = _snapshot()
        new_id = _next_id("n", [n.id for n in state["graph"].nodes])
        new_node = FlowNode(id=new_id, type=node_type, data=data or {})
        state["graph"].nodes.append(new_node)
        msg = f"노드 {new_id}({node_type}) 추가됨"
        note = _dynamic_input_note(new_node)
        if note:
            msg += f"\n{note}"
        return _commit_or_rollback(before, msg)

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
        msg = f"노드 {node_id} 갱신됨: {list(data.keys())}"
        if "testValue" in data:
            note = _dynamic_input_note(node)
            if note:
                msg += f"\n{note}"
        return _commit_or_rollback(before, msg)

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
        
        g = None
        template = None
        mode_label = "few-shot"
        
        if complexity_level == "high":
            # ── 정밀 모드: 템플릿 검색 없이, 요청을 더 꼼꼼히 해석해서 살을 붙여 생성 ──
            g = generate_flow_precise(request)
            mode_label = "정밀 생성"

        elif complexity_level == "medium":
            # ── 확장 모드: Pre-translated DB에서 템플릿 검색 → 구조 유지 + 파라미터 수정 ──
            try:
                from rag_utils import search_and_parse_template
                template_data = search_and_parse_template(request)
                if template_data:
                    template = FlowGraph(
                        nodes=template_data.get("nodes", []),
                        edges=template_data.get("edges", []),
                    )
                    mode_label = "사전 번역 템플릿 기반"
            except Exception as e:
                print(f"Medium mode template search failed: {e}")

        # 확장 모드에서 템플릿을 못 찾았을 때
        if not g:
            if template:
                g = generate_flow_from_template(request, template)
            else:
                g = generate_flow(request)  # low 모드 또는 fallback

        # ── Validation + 재시도 ──
        ok, errs = validate_flow(g)
        if not ok:
            retry = f'{request}\n\n(직전 생성이 아래 이유로 잘못됐다. 고쳐서 다시: {"; ".join(errs)})'
            if mode_label == "정밀 생성":
                g = generate_flow_precise(retry)
            elif template:
                g = generate_flow_from_template(retry, template)
            else:
                g = generate_flow(retry)
            ok, errs = validate_flow(g)
            
        if not ok:
            return _fail(f"생성 실패(기존 flow 유지): {errs}")
        state["graph"] = g
        msg = f"새 플로우 생성됨 ({mode_label}): 노드 {len(g.nodes)}개, 엣지 {len(g.edges)}개"
        notes = [n for n in (_dynamic_input_note(node) for node in g.nodes) if n]
        if notes:
            msg += "\n" + "\n".join(notes)
        return _succeed(msg)

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
    '- 완전히 새로 만드는 요청("~봇 만들어줘")에는 반드시 `generate_flow` 하나만 호출한다. 절대 여러 번의 `add_node`를 병렬로 호출해서 직접 조립하지 마라.\n'
    '- 기존 flow에 붙이거나 일부만 고치는 요청에는 add_node/connect_nodes/update_node/delete_node를 쓴다.\n'
    '- 노드 id가 뭔지 확실하지 않으면 먼저 show_flow로 현재 상태를 확인하고 나서 편집한다.\n'
    '- 그래프 편집과 무관한 잡담(인사, 이 앱이 뭔지 설명 등)에는 도구를 부르지 말고 그냥 대화로 답한다.\n'
    '- 요청이 너무 모호해서 어떤 노드가 필요한지 판단할 수 없으면, 임의로 짐작해서 도구를 부르지 말고 '
    '먼저 무엇을 원하는지 구체적으로 되묻는다. 특히 대화가 길어져서 이전 요청들과 섞여 헷갈릴 수 있는 '
    '상황일수록(예: 여러 flow를 이미 만들어본 뒤) 짐작하지 말고 먼저 확인한다.\n'
    '- 도구 응답에 \'⚠️ 연속 N회 실패\' 경고가 붙으면, 같은 방식을 반복하지 말고 사용자에게 무엇이 '
    '막혔는지 설명하고 어떻게 할지 물어본다.\n'
    '- 도구 응답에 \'dynamicInputNode의 testValue를...\' 같은 안내 문장이 붙어 있으면, 그 내용을 반드시 '
    '최종 답변에 그대로(추측해서 다른 값을 지어내지 말고) 포함시켜 사용자에게 알려준다 — 예시값인지, '
    '비워뒀는지를 사용자가 알아야 실제 실행 때 뭐가 들어가는지 헷갈리지 않는다.\n'
    '\n[예시]\n'
    '- 사용자: "PDF 요약봇 만들어줘" → generate_flow("PDF 요약봇 만들어줘") 호출\n'
    '- 사용자: "요약 뒤에 번역 추가해줘" → show_flow로 현재 노드 확인 → add_node로 promptNode·llmNode 추가 → connect_nodes로 연결\n'
    '- 사용자: "모델을 gpt-4o로 바꿔줘" → show_flow로 llmNode id 확인 → update_node(그 id, {"model": "gpt-4o"})\n'
    '- 사용자: "매번 다른 문장을 입력받아서 번역해주는 봇 만들어줘" → generate_flow 호출 → 도구 응답에 '
    '"n2(dynamicInputNode)의 testValue를 예시로 \'Hello, how are you?\'로 채웠다..." 같은 note가 붙으면, '
    '답변에서 "테스트용으로 \'Hello, how are you?\'라는 예시 문장을 넣어뒀어요. 실제로 실행할 때는 그때 '
    '입력하는 문장이 대신 들어갑니다." 처럼 그대로 안내한다\n'
    '- 사용자: "안녕" → 도구 호출 없이 그냥 인사만 한다 (예: "안녕하세요! 어떤 워크플로우를 만들어드릴까요?")\n'
    '- 사용자: "채용 자동화 봇 만들어줘" (단순한 요청) → 사용자가 구체적으로 말하지 않아도 RAG로 제공된 템플릿들을 참고하여 예외 처리, 실패 알림, 분기 등을 포함한 [크고 복잡한 비선형적 워크플로우]를 상상한 뒤, 이 복잡한 내용을 구체적인 문자열로 만들어서 `generate_flow("입력: ... 조건분기: ... 알림: ...")` 도구 하나에 인자로 넘겨 한 번에 완성한다.\n'
    '- ⚠️ 단, 유추한 로직이 사용자의 원래 목적 자체를 완전히 벗어나는 경우(예: 채용을 물어봤는데 마케팅 봇을 만드는 경우)에만 채팅창에서 2~3가지 선택지를 제안하여 묻고, 그 외에는 사용자가 묻지 않은 디테일까지 전부 살을 붙여서 최대한 복잡하고 멋진 노드 그래프를 바로 생성한다.\n'
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


def build_agent(graph_data: FlowGraph, complexity_level: str = "low", checkpointer=None):
    """이번 요청 전용 에이전트 + get_current_graph 접근자를 만든다. (tools, agent 둘 다 요청마다 새로 만듦.)"""
    from langchain.agents import create_agent

    tools, get_current_graph = make_tools(graph_data, complexity_level=complexity_level)
    agent = create_agent(
        get_llm(),
        tools=tools,
        system_prompt=AGENT_SYSTEM_PROMPT,
        checkpointer=checkpointer or _get_default_checkpointer(),
    )
    return agent, get_current_graph


def run_agent_turn(graph_data: dict, message: str, thread_id: str, complexity_level: str = "low", checkpointer=None) -> Tuple[str, dict]:
    """대화 한 턴을 실행한다. /api/chat은 이 함수를 그대로 감싸기만 하면 된다.

    흐름: graph_data(raw dict, 프론트가 보낸 것) → FlowGraph로 파싱 → 이번 요청 전용 에이전트 조립
    → agent.invoke → 끝나면 최종 완결성 게이트(validate_flow, require_complete=True 기본값) →
    통과하면 auto_layout한 graph_data, 실패하면 원본 graph_data 그대로 반환.

    반환: (reply: str, graph_data: dict) — API 응답 {reply, graph_data}에 그대로 매핑된다.
    """
    g = FlowGraph(nodes=graph_data.get("nodes", []), edges=graph_data.get("edges", []))
    agent, get_current_graph = build_agent(g, complexity_level=complexity_level, checkpointer=checkpointer)

    # 확장, 정밀 모드 모두 내부 도구(_generate_flow_tool)에서 RAG/생성을 처리하므로
    # 추가적인 프롬프트 조작(rag_context 첨부)은 하지 않습니다.
    final_message = message

    result = agent.invoke(
        {"messages": [{"role": "user", "content": final_message}]},
        {"configurable": {"thread_id": thread_id}},
    )
    reply = result["messages"][-1].content

    final_graph = get_current_graph()

    # If the AI did not modify the graph in this turn, just return as is without warnings.
    if g.nodes == final_graph.nodes and g.edges == final_graph.edges:
        return reply, graph_data

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
