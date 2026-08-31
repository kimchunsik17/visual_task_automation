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
  ⑧ make_tools      : (Phase 2) 요청별 그릇 + 도구 7종(show/add/connect/update/delete/generate/web_search)
  ⑨ run_agent_turn  : (Phase 3) create_agent 조립 + 한 턴 실행 + 최종 완결성 게이트

■ 실행:  python meta_agent.py        (아래 __main__의 데모가 돈다)
■ 설치:  backend/requirements.txt에 필요한 패키지 이미 포함(langgraph·langchain-openai 등).
         create_agent를 쓰려면 core langchain 패키지도 필요 — 없으면 `pip install langchain>=0.3`.
■ 키:    OPENAI_API_KEY 환경변수(backend/.env) — get_llm()이 gpt-4o-mini 기본 사용.
"""

from __future__ import annotations
import asyncio
import json
import re
import time
import uuid
from typing import Literal, List, Dict, Any, Optional, Tuple, Callable
from collections import defaultdict, deque
from pydantic import BaseModel, Field, model_validator
from rag_utils import retrieve_chat_context
from llm.task_spec import (
    TaskSpec,
    build_task_spec_context,
    normalize_task_spec,
    should_normalize_task_spec,
    task_coverage_issues,
)
import generation_plan
import node_bindings
import workflow_patterns
import node_definition
import node_knowledge
from flow_validation import ValidationIssue, issue_signature, validation_issues
from generation_trace import build_generation_trace


# httpRequestNode/webCrawlerNode의 url을 실제로 모를 때 쓰는 채움 표시자. validate_flow는
# url이 "비어있지 않은 문자열"이면 통과시키므로 스키마는 만족하면서도, 실행 엔진(node_generators/
# action_nodes.py)이 이 정확한 문자열을 보면 진짜 요청을 시도하지 않고 안내 메시지로 대체한다.
# 두 파일에서 정확히 같은 문자열을 써야 하므로 값을 바꿀 땐 action_nodes.py도 같이 바꿀 것.
PLACEHOLDER_URL = "REPLACE_WITH_ACTUAL_URL"

# ── ① 노드 카탈로그 (핵심 11종) ────────────────────────────────────────────
# 여기에 노드를 한 줄씩 추가하면 챗봇이 다룰 수 있는 노드가 늘어난다(P2 확장).
_NODE_CATALOG_TEMPLATE = """\
[사용 가능한 노드 — 이 51종만 사용한다]
- startNode      : 플로우 시작점. data 없음. 모든 플로우는 이 노드에서 시작한다.
- scheduleNode   : {{NODE_DEFINITION}}
- promptNode     : 사용자 프롬프트. data.userPrompt(문자열).
- llmNode        : {{NODE_DEFINITION}}
- tokenizerNode  : 업로드 문서(PDF/PPTX/Excel/HWP)에서 텍스트 추출. data.method(extract_text | chunk_pages).
                   '문서/PDF/회의록 기반' 작업이면 llmNode 앞에 둔다. 직전 노드의 출력이 파일 경로여야 한다.
- templateAnalyzerNode: {{NODE_DEFINITION}}
- fileModifierNode: {{NODE_DEFINITION}}
- hwpxDocumentNode: {{NODE_DEFINITION}}
- formatNode: {{NODE_DEFINITION}}
- naverSearchNode: {{NODE_DEFINITION}}
- jusoNode: {{NODE_DEFINITION}}
- dataGoKrNode: {{NODE_DEFINITION}}
- naverSearchTriggerNode: {{NODE_DEFINITION}}
- naverCafeNode: {{NODE_DEFINITION}}
- posterGeneratorNode: {{NODE_DEFINITION}}
- imageGenerationNode: {{NODE_DEFINITION}}
- conditionNode  : {{NODE_DEFINITION}}
- distributorNode: 직전 노드의 출력을 리스트로 보고 하나씩 꺼내 뒤에 연결된 노드들을 항목 개수만큼
                   반복 실행시킨다(리스트가 아니면 1개짜리로 취급). data 없음. "각각에 대해",
                   "하나씩" 같은 요청에 쓴다. sourceHandle이 없는(기본) 엣지는 반복 "안"에서
                   항목마다 실행된다 — 이 경로는 절대 outputNode로 이어지면 안 된다(반복 중
                   outputNode에 닿으면 그 즉시 return돼서 첫 항목만 처리하고 전체 워크플로우가
                   끝나버린다). 반복이 다 끝난 뒤 딱 한 번 실행할 것(최종 요약·종료 등)은
                   sourceHandle을 "done"으로 지정해 연결한다(loopNode의 done과 동일한 개념) —
                   outputNode로 끝내려면 반드시 이 done 경로를 거쳐야 한다.
- breakNode      : 반복을 즉시 멈춘다. data 없음. 반드시 distributorNode 하류(반복 구조 안)에서만
                   쓴다 — 반복 구조 밖에 두면 실행 자체가 SyntaxError로 깨진다. 보통 conditionNode와
                   짝을 이뤄 "특정 조건을 만나면 반복을 멈춘다"는 용도로 쓴다.
- webhookNode    : 외부 시스템의 Webhook 요청을 수신하는 진입점. data.method(GET|POST|PUT|DELETE 등), data.path(문자열, 엔드포인트 경로). startNode 대신 진입점으로 사용할 수 있다.
- discordTriggerNode: 디스코드에서 봇에게 DM을 보내거나 멘션하면 그 메시지로 워크플로우가 시작된다.
                   startNode 대신 진입점으로 쓴다("디스코드로 대화하는 봇 만들어줘" 같은 요청에 적합
                   — 배포 절차 없이 이 노드 하나로 끝난다). data.botToken(문자열) — 사용자가 토큰을
                   프롬프트에서 직접 주지 않았다면 절대 지어내지 말고 빈 문자열로 두거나
                   "{{API_CENTER:discord}}"로 채워라(사용자가 API 센터에 등록해뒀다면 자동으로
                   연결된다). 캔버스에 저장하고 "라이브 시작"을 켜면(에디터 상단 토글) 그 순간부터
                   실제 디스코드 봇이 메시지를 기다린다 — 별도의 "배포" 절차가 필요 없다. 메시지를
                   보낸 사람에게 다시 답장을 보내고 싶으면 흐름 끝에 outputNode만 두면 되고(봇이
                   자동으로 그 결과를 답장으로 보낸다), discordNode(발송)를 굳이 또 연결할 필요는
                   없다 — discordNode는 "다른" 채널/사람에게 별도로 보내고 싶을 때만 추가로 쓴다.
- telegramTriggerNode: 텔레그램에서 봇에게 메시지를 보내면 그 메시지로 워크플로우가 시작된다.
                   discordTriggerNode와 완전히 같은 방식(진입점, "라이브 시작"으로 켜짐, 흐름 끝은
                   outputNode 하나면 충분하고 봇이 자동으로 답장한다)이고, "텔레그램으로 대화하는
                   봇 만들어줘" 같은 요청에 쓴다. data.botToken(문자열) — 사용자가 토큰을 직접
                   주지 않았다면 지어내지 말고 빈 문자열로 두거나 "{{API_CENTER:telegram}}"으로
                   채워라. 텔레그램 봇 토큰은 @BotFather에서 한 번 발급받으면 만료되지 않는다(카카오
                   access_token과 달리 자동 갱신이 필요 없다).
- youtubeTriggerNode: {{NODE_DEFINITION}}
- telegramNode   : 텔레그램 메시지 발송. data.botToken(문자열, telegramTriggerNode와 동일한 값 —
                   "{{API_CENTER:telegram}}"), data.chatId(문자열, 받을 사람/채널의 chat_id — 사용자가
                   실제 값을 안 줬으면 지어내지 말고 빈 문자열로 둔다. 숫자(음수 가능, 그룹/채널은
                   보통 음수) 또는 "@channel_username" 형식만 유효하다). 직전 노드의 출력을 그대로
                   발송한다. telegramTriggerNode로 시작한 흐름에서 받은 사람에게 그대로 답장하는
                   용도라면 이 노드 없이 outputNode로 끝내면 된다(discordNode와 동일한 이유) —
                   "다른" 특정 채팅방에 보내고 싶을 때만 추가로 쓴다.
- httpRequestNode: {{NODE_DEFINITION}}
- jsonParserNode : {{NODE_DEFINITION}}
- databaseNode   : {{NODE_DEFINITION}}
- googleSheetsNode: 구글 시트 읽기/쓰기. databaseNode처럼 별도 접속 정보가 필요 없다 — 서버가
                   서비스 계정으로 접근하므로, 사용자는 그 시트를 서비스 계정과 "공유"만 해두면
                   된다(이 노드의 data에 인증 정보를 채울 필요 없음). data.mode("read"|"append"|"write",
                   기본 read — read는 조회, append는 맨 끝에 한 행 추가, write는 지정한 범위를
                   덮어쓴다), data.spreadsheetId(문자열, 시트 URL의 .../d/⟨이 부분⟩/edit에 있는 ID —
                   사용자가 실제로 URL이나 ID를 안 줬으면 지어내지 말고 빈 문자열로 둔다),
                   data.range(문자열, 예: "Sheet1" 또는 "Sheet1!A1:D10" — 비우면 첫 번째 시트 전체를
                   대상으로 한다), data.values(문자열, 선택 — append/write일 때 기록할 값을 JSON
                   배열로 직접 써도 되고, 비워두면 직전 노드의 출력(JSON)을 그대로 값으로 쓴다.
                   read일 때는 안 쓴다). read의 출력은 행(list of list) JSON 문자열이므로, 그 내용을
                   활용하려면 뒤에 llmNode/jsonParserNode를 연결해라.
- googleCalendarNode: 구글 캘린더 일정 등록/조회. googleSheetsNode와 동일한 서비스 계정을 쓰므로
                   별도 인증 정보가 필요 없다(사용자가 캘린더를 서비스 계정과 공유해두면 됨).
                   data.mode("create"|"list", 기본 create — create는 일정 등록, list는 다가오는
                   일정 조회), data.calendarId(문자열, 캘린더 설정의 "캘린더 ID" — 보통 본인 gmail
                   주소이거나 ...@group.calendar.google.com 형식. 사용자가 실제로 안 줬으면 지어내지
                   말고 빈 문자열로 둔다), data.eventData(문자열, 선택 — create일 때 등록할 일정을
                   JSON으로 직접 써도 되고(예: {"summary":"팀 회의","start":"2026-08-01T10:00:00+09:00",
                   "end":"2026-08-01T11:00:00+09:00","description":"...","location":"..."}), 비워두면
                   직전 노드의 출력(JSON)을 그대로 쓴다. start/end는 타임존 포함 ISO 8601 문자열이어야
                   한다), data.timeMin/data.timeMax(문자열, 선택 — list일 때 조회 범위, ISO 8601.
                   비우면 timeMin은 지금부터), data.maxResults(숫자, 선택 — list일 때 최대 개수,
                   기본 10). list의 출력은 일정 목록(JSON 배열) 문자열이므로 활용하려면 뒤에
                   llmNode/jsonParserNode를 연결해라.
- youtubeNode    : {{NODE_DEFINITION}}
- rssTriggerNode : {{NODE_DEFINITION}}
- gmailTriggerNode : {{NODE_DEFINITION}}
- gmailNode      : {{NODE_DEFINITION}}
- googleDriveNode: {{NODE_DEFINITION}}
- notionNode     : Notion 페이지 생성/데이터베이스 조회. data.token(문자열) — 사용자가 토큰을
                   직접 주지 않았다면 지어내지 말고 빈 문자열로 두거나 "{{API_CENTER:notion}}"으로
                   채워라(사용자가 API 센터에 Notion Integration Token을 등록해뒀다면 자동으로
                   연결된다 — discordNode/kakaoNode와 동일한 방식). data.mode("create"|"query", 기본
                   create — create는 데이터베이스에 새 페이지(행) 추가, query는 데이터베이스의
                   페이지들을 조회), data.databaseId(문자열, Notion 데이터베이스 URL에 있는 ID —
                   사용자가 실제로 안 줬으면 지어내지 말고 빈 문자열로 둔다), data.properties(문자열,
                   선택 — create일 때 채울 속성을 Notion 속성 형식의 JSON으로 직접 써도 되고(예:
                   {"이름":{"title":[{"text":{"content":"..."}}]}, "완료":{"checkbox":true}}), 비워두면
                   직전 노드의 출력(JSON, 이미 Notion 속성 형식이어야 함)을 그대로 쓴다. ⚠️ Notion은
                   속성 타입마다 JSON 형식이 다르다(title/rich_text/number/select/checkbox/date 등) —
                   정확한 속성 이름과 타입을 모르면 llmNode에 "다음 Notion 속성 형식에 맞는 JSON을
                   만들어라: {실제 속성 스키마}"처럼 구체적으로 지시해야 한다). query의 출력은 페이지
                   목록(JSON 배열) 문자열이므로 활용하려면 뒤에 llmNode/jsonParserNode를 연결해라.
- delayNode      : {{NODE_DEFINITION}}
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
- webCrawlerNode : URL의 웹페이지를 읽어 제목·발행일·본문·링크로 갈라서 넘긴다. 메뉴·광고·푸터는
                   빼고 본문만 남긴다. data.url(문자열, 선택 — 비워두면 직전 노드의 출력을 URL로
                   그대로 쓴다), data.output("text" 기본 — 제목/발행/본문을 사람이 읽는 글로 |
                   "structured" — 전체를 JSON으로 | "links" — 페이지의 링크 목록만 JSON으로),
                   data.maxChars(숫자, 기본 5000). 목록 페이지에서 링크를 모아 상세로 넘어갈 때는
                   output="links"를 쓴다. robots.txt를 지키고 호스트당 하루 요청 수에 상한이 있어서
                   같은 사이트를 대량으로 훑는 워크플로우는 도중에 막힌다. 실패해도 워크플로우가
                   멈추지 않고 "수집하지 않았습니다: ..." 같은 문자열이 다음 노드로 그냥 전달된다.
- emailNode      : {{NODE_DEFINITION}}
- loopNode       : 반복을 제어한다. data.maxIterations(숫자, 기본 5). 하류 엣지는 sourceHandle을 쓴다:
                   'loop_start' (매 반복마다 실행할 흐름 시작), 'done' (반복이 모두 끝난 뒤 실행).
- multiAgentNode : 여러 에이전트를 조율한다. data.mode("supervisor" | "group_chat"). 
                   연결될 서브 에이전트(llmNode)는 엣지의 targetHandle을 "tools"로 설정하여 들어와야 한다.
- pythonNode     : 제한된 파이썬으로 데이터를 변환한다. data.code(문자열). 직전 노드의 출력이 'input_data'
                   변수에 담기며, 처리 결과를 'output_data' 변수에 할당해야 한다. ⚠️ 격리된 환경에서 돌아서
                   **쓸 수 있는 것이 매우 제한적이다** — import·def·lambda·while·try·open·eval 은 전부 금지이고,
                   파일·네트워크·환경변수·DB 에 접근할 수 없다. 쓸 수 있는 것은 변수 대입, if, for, 컴프리헨션,
                   사칙연산, f-string, 그리고 len/str/int/float/list/dict/set/sorted/sum/min/max/range/enumerate/
                   zip/map/filter/any/all/abs/round 같은 기본 함수와 문자열·리스트·딕셔너리의 흔한 메서드
                   (split/join/strip/replace/upper/lower/get/keys/items/values/append/sort 등)뿐이다.
                   실행 시간 1초·메모리 256MB 제한이 있으니 큰 반복을 만들지 마라. 파일을 읽거나 외부를
                   호출해야 하면 pythonNode 가 아니라 전용 노드(fileModifierNode/httpRequestNode 등)를 써라.
- discordNode    : {{NODE_DEFINITION}}
- kakaoNode      : 카카오톡 메시지 발송. data.accessToken(문자열) — 사용자가 프롬프트에서 직접 토큰 값을
                   알려주지 않는 한 항상 리터럴 문자열 "{{API_CENTER:kakao_token}}"으로 채운다(API 센터에
                   등록해둔 카카오 access_token을 실행 시점에 자동으로 대입하며, 6시간마다 만료되어도
                   refresh_token으로 자동 갱신되므로 사용자가 재입력할 필요가 없다). data.receiver(문자열,
                   선택 — 수신자 정보, 비우면 나에게 보내기). 직전 노드의 출력을 내용으로 발송한다.
- tossNode       : 토스페이먼츠 API 연동. data.secretKey(문자열), data.searchType(문자열, 'paymentKey' 또는 'orderId'), data.searchValue(문자열). 직전 노드의 결과를 검색 값으로 쓰거나 입력받아 결제 정보를 조회한다.
- paymentLinkNode: 주문 정보를 받아 결제 링크를 생성한다(결제 "조회"인 tossNode와 반대로 "생성"). data.provider(문자열,
                   기본 'toss'), data.orderData(문자열, 선택 — 채울 주문 정보를 JSON 문자열로 직접
                   써도 되고, 비워두면 직전 노드의 출력을 그대로 주문 데이터로 쓴다). "주문/결제 링크
                   만들어줘" 같은 요청에 쓴다. 직전 노드의 출력을 그대로 쓸 거면 orderData는 비워둔다.
- slackNode      : {{NODE_DEFINITION}}
- humanApprovalNode : {{NODE_DEFINITION}}
- mergeNode      : 여러 흐름의 결과를 하나로 병합한다. data.mergeStrategy("join_newline" | "join_comma" | "array"). 여러 갈래의 엣지가 이 노드로 모일 수 있다.
- outputNode     : 결과 출력(종료). data 없음. 흐름의 최종 결과를 사용자/호출자에게 텍스트로 돌려줘야
  할 때 이 노드로 끝난다. 단, emailNode/discordNode/kakaoNode/slackNode처럼 그 자체로 외부에 결과를
  발송/전달하는 노드로 흐름이 끝나는 경우(예: 디스코드로 메시지만 보내고 끝나는 봇)나, fileModifierNode/
  posterGeneratorNode처럼 파일(서식 문서, 포스터 이미지/PDF)을 완성해서 저장하는 것 자체로 흐름이
  끝나는 경우에는 그 노드가 이미 최종 결과 전달을 완료한 것이므로 outputNode를 추가로 붙이지 않는다.
  (databaseNode는 SELECT 조회만 가능하므로 항상 조회 결과를 사용자에게 보여줘야 한다 — outputNode를
  생략하지 않는다.) googleSheetsNode/googleCalendarNode/notionNode는 databaseNode와 달리 읽기와
  쓰기를 모두 할 수 있는 노드다 — data.mode가 "append"/"write"(googleSheetsNode),
  "create"(googleCalendarNode/notionNode)처럼 실제로 뭔가를 기록/생성하는 모드로 흐름이 끝나면
  discordNode와 동일하게 outputNode 없이 끝나도 된다. 반대로 mode가 "read"/"list"/"query"(조회)면
  databaseNode와 동일하게 반드시 outputNode로 결과를 보여줘야 한다.

[생성 원칙]
- discordNode를 생성할 때 사용자가 프롬프트에서 봇 토큰이나 Webhook URL을 명시적으로 알려주지 않았다면, 절대 임의의 가짜 값(예: "your-token", "1234")을 지어내서 채우지 말고 botToken과 channelId를 빈 문자열("")로 둔다. 그리고 반드시 답변에서 "디스코드 발송 노드를 구성했습니다. 실제 발송을 위해서는 화면에서 디스코드 노드를 클릭한 뒤, 본인의 봇 토큰(또는 웹훅 주소)을 직접 입력해 주세요."라고 친절하게 안내한다.
- discordTriggerNode로 시작하는 "디스코드로 대화하는 챗봇" 흐름은 "outputNode(종료)가 없으면 안
  된다"는 규칙을 만족시키려고 끝에 discordNode를 억지로 붙이면 절대 안 된다 — 사용자가 실제
  channelId를 알려주지 않은 채로 discordNode를 끝에 붙이면 채울 값이 없어 앞선 규칙과 충돌하고,
  그렇다고 channelId를 지어내면(실제로 이런 실수가 있었다 — 존재하지 않는 채널로 보내려다 실패)
  발송이 조용히 실패한다. discordTriggerNode로 시작할 때는 그냥 outputNode로 끝내라(봇이 답장을
  받은 채널/DM으로 자동으로 돌려보낸다 — discordTriggerNode 항목 설명 참고). discordNode는 사용자가
  "다른 특정 채널"의 실제 channelId를 프롬프트에서 명시적으로 알려준 경우에만 추가로 쓴다.
- telegramTriggerNode로 시작하는 흐름도 위 discordTriggerNode와 완전히 같은 이유로, 끝에 telegramNode를
  억지로 붙이지 마라 — chatId를 모르면 채울 값이 없다. outputNode로 끝내면 봇이 받은 채팅방으로
  자동으로 답장한다. telegramNode는 사용자가 "다른" 특정 채팅방의 실제 chatId를 알려준 경우에만 쓴다.
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
- 반드시 startNode, scheduleNode, webhookNode, discordTriggerNode, telegramTriggerNode 중 정확히 1개로
  시작한다. "디스코드 봇/디스코드로 대화" 같은 요청이면 startNode 대신 discordTriggerNode로, "텔레그램
  봇/텔레그램으로 대화" 같은 요청이면 telegramTriggerNode로 시작한다. 끝은 outputNode가 기본이지만,
  emailNode/discordNode/telegramNode/kakaoNode/slackNode 같은 발송형 액션 노드나, 파일을 완성해서 저장하고
  끝나는 fileModifierNode/posterGeneratorNode로 흐름이 끝나면 그걸로 충분하다(그 뒤에 굳이
  outputNode를 덧붙이지 않는다).
  단, databaseNode는 SELECT 조회만 가능해서 항상 결과를 보여줘야 하므로 예외에 포함하지 않는다 —
  databaseNode로 끝나는 흐름에는 outputNode를 반드시 붙인다. googleSheetsNode/googleCalendarNode/
  notionNode는 mode가 기록/생성(append, write, create)이면 위 예외에 포함되고, 조회(read, list,
  query)면 databaseNode와 동일하게 outputNode를 반드시 붙인다.
- 모든 노드는 start→output 경로 위에 있어야 한다. 어디에도 연결 안 된 고아 노드를 만들지 않는다.
- 사용자가 원하는 바를 충족하되, 불필요한 중복 노드를 만들지 않는다 — 필요한 만큼만 최소로 구성한다.
  단, "최소"를 이유로 요청에 필요한 단계(예: PDF 입력이면 tokenizerNode)를 빠뜨리면 안 된다.
- tokenizerNode는 직전 노드의 출력이 파일 경로일 때만 사용한다. startNode/scheduleNode 등 파일
  경로를 만들어내지 않는 노드 바로 뒤에 tokenizerNode를 두면 실행할 때마다 실패한다 — 반드시
  그 사이에 valueNode(data.file_path, 초기값은 빈 문자열 "")를 두고, 답변에서 "이 노드를 클릭해서
  실제 파일을 업로드해야 한다"고 안내한다.
- distributorNode 뒤에 연결된 노드들(sourceHandle 없는 기본 엣지)은 리스트 항목 개수만큼 반복
  실행된다는 걸 감안해서 구성한다. **outputNode는 절대 이 반복 경로 안에 두지 마라** — 첫 항목만
  처리하고 즉시 끝나버린다. 반복이 다 끝난 뒤 종료하려면 반드시 distributorNode에서 sourceHandle을
  "done"으로 지정한 별도 엣지로 outputNode(또는 그 앞 단계)를 연결한다.
- breakNode는 반드시 distributorNode 하류에서만 쓴다 — 반복 구조 밖에서 쓰면 실행이 깨진다.
- fileModifierNode는 반드시 JSON을 만들어주는 노드(templateAnalyzerNode → llmNode/promptNode 조합이
  일반적) 뒤에 연결한다 — 그렇지 않으면 빈칸이 하나도 안 채워진 채로 조용히 저장된다. 이때 그 llmNode는
  systemPrompt로만 "JSON으로 답해"라고 지시하지 말고 useStructuredOutput+jsonSchema를 반드시 함께
  설정해라 — 프롬프트 지시만으로는 모델이 가끔 JSON이 아닌 답을 내놓아 fileModifierNode가 조용히
  실패할 수 있다.
- llmNode의 출력을 jsonParserNode가 바로 이어받거나, conditionNode가 그 출력에서 특정 키/값을 검사하는
  구조라면 마찬가지로 그 llmNode에 useStructuredOutput+jsonSchema를 설정해서 출력 형식을 구조적으로
  보장해라.
- promptNode는 항상 인접한 llmNode와 짝으로 사용한다.
- llmNode의 model은 사용자가 특정 모델을 요청하지 않는 한 기본값 gpt-4o-mini를 쓴다.
- (미세수정 시) 기존 노드로 이미 처리 가능하면 새 노드를 추가하지 말고 update_node로 기존 노드를 고친다.
- **노드 종류를 바꿀 때도 update_node(node_id, data, node_type=...)를 쓴다.** delete_node + add_node 를 쓰면 그 노드에 붙어 있던 연결이 전부 끊기고 id 도 새로 생긴다 — 사용자가 잡아 둔 배선을 잃는다.
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

# 위 템플릿의 {{NODE_DEFINITION}} 자리는 저장소 루트 node_definitions/<type>.json 에서 채운다
# (ADR-0005). 노드 설명·허용값·필수 필드가 카탈로그와 validator와 프론트 UI 세 곳에 따로 적혀
# 있어 서로 어긋나던 문제를 없애기 위한 것이다. 조립 결과는 이전 원문과 완전히 같다 —
# backend/test_node_definitions.py 가 testdata/node_catalog_snapshot.txt 와 대조한다.
NODE_CATALOG = node_definition.inject_catalog_entries(_NODE_CATALOG_TEMPLATE)


# ── ①-b 카탈로그 트리밍 (생성 품질 개선) ────────────────────────────────────
# NODE_CATALOG는 32종 노드 설명을 전부 담아 항상 통째로 프롬프트에 들어갔다 — 요청과 무관한
# 노드 설명이 대부분을 차지하면 정작 관련 있는 규칙에 대한 준수도가 흐려지는 경향이 있다(길고
# 노이즈 섞인 지시일수록 개별 규칙 하나하나에 쏠리는 주의가 옅어짐). 그래서 요청과 관련 있을
# 법한 노드 타입만 골라 카탈로그를 줄여서 넣는다. NODE_CATALOG 원문은 절대 손대지 않고(문구를
# 다시 입력하면 오타/누락 위험이 있다) 거기서 노드별 항목을 그대로 잘라내는 방식이라, 항목
# 하나를 고치면 트리밍된 버전에도 자동으로 반영된다.
def _extract_section(catalog_text: str, header: str, next_header: Optional[str]) -> str:
    start = catalog_text.index(header)
    if next_header:
        end = catalog_text.index(next_header, start)
        return catalog_text[start:end]
    return catalog_text[start:]


def _parse_node_catalog_entries(catalog_text: str) -> Dict[str, str]:
    """'[사용 가능한 노드...]' 섹션을 노드 타입별 텍스트 블록으로 쪼갠다. 각 항목은
    '- nodeType : ...'로 시작해서 다음 '- nodeType :' 줄 전까지(줄바꿈된 설명 포함) 이어진다."""
    section = _extract_section(catalog_text, "[사용 가능한 노드", "\n[생성 원칙]")
    entries: Dict[str, str] = {}
    current_type = None
    current_lines: List[str] = []
    for line in section.split("\n")[1:]:  # 첫 줄(헤더)은 건너뜀
        m = re.match(r"^- (\w+)\s*:", line)
        if m:
            if current_type:
                entries[current_type] = "\n".join(current_lines).rstrip("\n") + "\n"
            current_type = m.group(1)
            current_lines = [line]
        elif current_type:
            current_lines.append(line)
    if current_type:
        entries[current_type] = "\n".join(current_lines).rstrip("\n") + "\n"
    return entries


NODE_CATALOG_ENTRIES: Dict[str, str] = _parse_node_catalog_entries(NODE_CATALOG)
NODE_CATALOG_PRINCIPLES = _extract_section(NODE_CATALOG, "[생성 원칙]", "[연결 규칙]")
NODE_CATALOG_CONNECTION_RULES = _extract_section(NODE_CATALOG, "[연결 규칙]", None)

# 노드가 뭐가 됐든 거의 모든 흐름에 등장하는 기본형이라 선별과 무관하게 항상 포함한다.
_ALWAYS_INCLUDE_NODE_TYPES = ["startNode", "outputNode", "promptNode", "llmNode"]

# 문서 요청이면 formatNode 를 **함께** 보여준다.
#
# 선별 LLM 은 문서 요청에서 구형 경로(templateAnalyzer→llm→fileModifier, hwpxDocumentNode,
# posterGeneratorNode)만 고르는 일이 잦다 — 2026-08-31 측정에서 "시말서를 작성해서 한글 파일로
# 만들고 이메일로" 요청 3회 모두 formatNode 가 선별에서 빠졌다. 카탈로그에 항목이 아예 없으면
# 노드 설명을 어떻게 고쳐도 생성이 그 노드를 쓸 방법이 없다(설명은 프롬프트에 들어가지도 않는다).
# 그래서 이 넷 중 하나라도 골랐으면 formatNode 를 결정론적으로 끼워 넣고, 선택은 생성 LLM 이
# 두 설명을 나란히 보고 하게 한다. 문서와 무관한 요청에는 발동하지 않는다.
_DOCUMENT_COSELECT_TRIGGERS = {
    "templateAnalyzerNode", "fileModifierNode", "hwpxDocumentNode", "posterGeneratorNode",
}
_DOCUMENT_COSELECT_ADDITIONS = ["formatNode"]


def apply_selection_augmentation(selected_types: List[str]) -> List[str]:
    """선별 결과에 결정론적 보강을 적용한다(순서 유지, 중복 없음)."""
    result = list(selected_types)
    if set(result) & _DOCUMENT_COSELECT_TRIGGERS:
        for node_type in _DOCUMENT_COSELECT_ADDITIONS:
            if node_type not in result:
                result.append(node_type)
    return result


class NodeTypeSelection(BaseModel):
    node_types: List[str] = Field(description="이 요청을 구현하는 워크플로우에 실제로 쓰일 가능성이 있는 노드 타입 이름들")


def _llm_select_node_types(user_request: str) -> Tuple[List[str], Optional[str], Optional[dict], int]:
    """LLM 선별 한 번을 실행하고 (선별 타입, 오류, 토큰 사용량, 지연 ms)를 돌려준다.

    include_raw=True로 같은 호출에서 토큰 사용량까지 회수한다 — 이 selector 호출 자체가
    hybrid retrieval(node_knowledge)로 없애려는 비용이라, 전환 판단을 위해 크기를 재둔다
    (ADR-0013, RAG Phase A 계측)."""
    started = time.perf_counter()
    token_usage: Optional[dict] = None
    try:
        llm = get_llm(complexity_level="low").with_structured_output(
            NodeTypeSelection, method="function_calling", include_raw=True,
        )
        type_list = ", ".join(NODE_CATALOG_ENTRIES.keys())
        messages = [
            ("system",
             "너는 노코드 워크플로우 빌더의 '노드 선별' 도우미다. 아래는 지원하는 전체 노드 타입 "
             f"목록이다:\n{type_list}\n\n"
             "사용자 요청을 구현하는 워크플로우를 만들 때 실제로 쓰일 가능성이 있는 노드 타입만 "
             "골라라. 확실하지 않으면 너그럽게 포함해라 — 빠뜨리는 것보다 여분으로 포함하는 게 "
             "훨씬 안전하다. startNode/outputNode/promptNode/llmNode는 이미 항상 따로 포함되니 "
             "고르지 않아도 된다. 목록에 없는 이름은 절대 만들어내지 마라."),
            ("user", f'요청: "{user_request}"'),
        ]
        result = llm.invoke(messages)
        usage = getattr(result.get("raw"), "usage_metadata", None)
        if usage:
            token_usage = {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            }
        if result.get("parsed") is None:
            raise ValueError(f"구조화 출력 파싱 실패: {result.get('parsing_error')}")
        latency_ms = round((time.perf_counter() - started) * 1000)
        selected = [t for t in result["parsed"].node_types if t in NODE_CATALOG_ENTRIES]
        return selected, None, token_usage, latency_ms
    except Exception as e:
        print(f"[select_relevant_node_types] 선별 실패, 전체 카탈로그로 폴백: {e}")
        return [], f"{type(e).__name__}: {e}", token_usage, round((time.perf_counter() - started) * 1000)


def select_relevant_node_types(user_request: str, complexity_level: str = "low") -> List[str]:
    """가벼운 1차 선별 — 실패하거나 결과가 부실하면 빈 리스트를 돌려주고, 호출부(build_trimmed_catalog)가
    그걸 보고 전체 카탈로그로 안전하게 폴백한다(즉, 이 단계가 잘못돼도 트리밍 이전과 동일하게만
    동작할 뿐 더 나빠지지는 않는다)."""
    return _llm_select_node_types(user_request)[0]


def build_trimmed_catalog(selected_types: Optional[List[str]]) -> str:
    """selected_types가 비었거나 너무 적으면(선별이 사실상 실패했다고 판단) 원본 NODE_CATALOG를
    그대로 돌려준다 — 트리밍이 실패해도 절대 원래보다 못한 결과를 내지 않는다."""
    if not selected_types or len(set(selected_types) & set(NODE_CATALOG_ENTRIES)) < 3:
        return NODE_CATALOG
    want = set(apply_selection_augmentation(selected_types)) | set(_ALWAYS_INCLUDE_NODE_TYPES)
    header = (
        "[사용 가능한 노드 — 이번 요청과 관련 있을 법한 노드만 추려서 아래에 나열했다. "
        "이 목록에 없는 노드 타입이 정말 필요하다고 판단되면 이름을 지어내지 말고, "
        "목록에 있는 노드 조합으로 최대한 대체할 방법을 먼저 찾아라]\n"
    )
    body = "".join(NODE_CATALOG_ENTRIES[t] for t in NODE_CATALOG_ENTRIES if t in want)
    return header + body + "\n" + NODE_CATALOG_PRINCIPLES + "\n" + NODE_CATALOG_CONNECTION_RULES


def _select_and_trim_catalog(user_request: str, complexity_level: str, stage: str) -> str:
    """LLM 선별 → 카탈로그 트리밍을 실행하고, 같은 요청으로 hybrid retrieval(node_knowledge)을
    shadow로 함께 돌려 두 선별 결과와 실제 제공된 카탈로그 구성을 선별 트레이스에 기록한다
    (ADR-0013). 생성 프롬프트에 쓰이는 것은 변함없이 LLM 선별 결과다 — shadow 결과는 기록만
    되고, Recall 기준을 데이터로 통과하기 전에는 기본 경로를 바꾸지 않는다."""
    selected_types, llm_error, llm_usage, llm_latency = _llm_select_node_types(user_request)
    trimmed_catalog = build_trimmed_catalog(selected_types)
    fallback = trimmed_catalog == NODE_CATALOG
    offered_types = (
        sorted(NODE_CATALOG_ENTRIES) if fallback
        else sorted((set(selected_types) | set(_ALWAYS_INCLUDE_NODE_TYPES)) & set(NODE_CATALOG_ENTRIES))
    )
    event: Dict[str, Any] = {
        "stage": stage,
        "complexity_level": complexity_level,
        "llm": {
            "selected_types": selected_types,
            "error": llm_error,
            "token_usage": llm_usage,
            "latency_ms": llm_latency,
        },
        "catalog": {
            "fallback_full_catalog": fallback,
            "offered_types": offered_types,
            # 프롬프트에 들어간 카탈로그 크기(문자 수). 토큰 절감 지표("전체 대비 50% 감소")의
            # 근사 proxy다 — 정확한 토큰 수는 provider마다 달라 문자 수로 비교한다.
            "trimmed_chars": len(trimmed_catalog),
            "full_chars": len(NODE_CATALOG),
        },
    }
    if node_knowledge.shadow_mode_enabled():
        try:
            event["shadow"] = node_knowledge.hybrid_select_node_types(user_request)
        except Exception as e:
            event["shadow"] = {"selected_types": [], "source": "error", "error": f"{type(e).__name__}: {e}"}
    node_knowledge.record_selection_event(event)
    return trimmed_catalog


# ── ② 출력 스키마 (형식 강제) ────────────────────────────────────────────
# type을 Literal로 묶어 11종 밖의 노드를 아예 못 만들게 한다. position(x,y)은
# LLM이 추측하면 안 되므로 항상 None으로 초기화하고, auto_layout에서 채운다.
NodeType = Literal[
    "startNode", "promptNode", "llmNode", "tokenizerNode", "conditionNode",
    "httpRequestNode", "jsonParserNode", "delayNode", "dynamicInputNode", "webCrawlerNode",
    "outputNode", "valueNode", "distributorNode", "breakNode", "templateAnalyzerNode", "fileModifierNode",
    "emailNode", "databaseNode", "loopNode", "multiAgentNode", "scheduleNode", "pythonNode", "discordNode",
    "kakaoNode", "slackNode", "humanApprovalNode", "mergeNode", "tossNode", "webhookNode", "paymentLinkNode",
    "posterGeneratorNode", "imageGenerationNode", "discordTriggerNode", "telegramTriggerNode", "telegramNode", "googleSheetsNode",
    "googleCalendarNode", "notionNode", "youtubeNode", "youtubeTriggerNode",
    "rssTriggerNode", "gmailTriggerNode", "gmailNode", "googleDriveNode",
    # 한국형 노드 계획 Phase 1~3.
    #
    # ⚠️ 2026-08-30 에 이 다섯이 **빠져 있었다.** 카탈로그는 LLM 에게 쓰라고 알려주는데
    # 출력 스키마가 거부해서, 이 노드를 쓴 그래프는 생성·dry-run·커뮤니티 게시가 전부
    # 깨졌다(발견 경위: 새 노드로 템플릿을 만들다가 구조 검사에서 걸렸다).
    # 같은 일이 반복되지 않도록 `test_node_definitions.py` 가 이 목록과 카탈로그를 대조한다.
    "naverSearchNode", "naverSearchTriggerNode", "naverCafeNode", "hwpxDocumentNode",
    "jusoNode", "dataGoKrNode",
    # 문서 포맷(포맷 스튜디오 계획 Phase 1) — 빈칸 선언된 포맷에 값을 채워 파일 생성.
    "formatNode",
    # memoNode는 캔버스 주석(스티키 노트)이다 — 실행/검증에서 제외되지만, 사용자가 그래프에
    # 남긴 메모가 저장된 graph_data를 FlowGraph로 파싱할 때 깨지지 않도록 스키마에는 포함한다.
    "memoNode",
]


# 워크플로우를 **시작할 수 있는** 노드. 하드코딩하지 않고 정의에서 파생시킨다(ADR-0008,
# `dry_run.TRIGGER_NODE_TYPES` 와 같은 방식).
#
# ⚠️ 2026-08-30 까지 손으로 적은 5종이었고, 그 사이에 늘어난 rssTriggerNode·youtubeTriggerNode·
# gmailTriggerNode·naverSearchTriggerNode 가 빠져 있었다. 그래서 이 트리거로 시작하는 그래프가
# 전부 "시작 노드는 정확히 1개여야 한다 (현재 0개)" 로 거부됐다. 목록에 넣는 걸 잊는 실수를
# 구조적으로 막는다.
_LEGACY_START_NODE_TYPES = frozenset({
    "startNode", "scheduleNode", "webhookNode", "discordTriggerNode", "telegramTriggerNode",
})
START_NODE_TYPES = _LEGACY_START_NODE_TYPES | frozenset(node_definition.trigger_types())


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
    title: str = Field(default="", description="워크플로우의 짧고 명확한 제목 (예: '새 뉴스레터 자동 발송')")
    description: str = Field(default="", description="워크플로우가 수행하는 작업에 대한 상세 설명 (예: '매일 아침 뉴스를 요약해 이메일로 전송합니다.')")
    nodes: List[FlowNode]
    edges: List[FlowEdge]

    @model_validator(mode="before")
    @classmethod
    def _fill_missing_edge_ids(cls, values):
        """엣지 id 누락 보충. 프론트가 실행 계열 API로 그래프를 보낼 때 엣지를
        {source, target, sourceHandle, targetHandle}로만 직렬화해 왔다 — 실행기
        (compile_workflow)는 id를 안 읽어서 문제가 없었지만, 이 그래프를 FlowGraph로
        재파싱하는 경로(dry_run 문제 검사, evaluation)에서는 id 필수 검증에 걸렸다.
        mode="before" 검증기는 LLM structured output 의 JSON 스키마에는 나타나지 않으므로
        생성 계약(id 필수)은 그대로 유지되고, 파싱 관용만 넓어진다."""
        if isinstance(values, dict) and isinstance(values.get("edges"), list):
            edges = values["edges"]
            taken = {str(e.get("id")) for e in edges if isinstance(e, dict) and e.get("id")}
            counter = 1
            filled = []
            for e in edges:
                if isinstance(e, dict) and not e.get("id"):
                    while f"e{counter}" in taken:
                        counter += 1
                    e = {**e, "id": f"e{counter}"}
                    taken.add(f"e{counter}")
                filled.append(e)
            values = {**values, "edges": filled}
        return values


class FlowNodePatch(BaseModel):
    id: str
    type: Optional[NodeType] = None
    data: Optional[Dict[str, Any]] = None


class FlowRepairPlan(BaseModel):
    reason: str = ""
    update_nodes: List[FlowNodePatch] = Field(default_factory=list)
    add_nodes: List[FlowNode] = Field(default_factory=list)
    remove_node_ids: List[str] = Field(default_factory=list)
    add_edges: List[FlowEdge] = Field(default_factory=list)
    remove_edge_ids: List[str] = Field(default_factory=list)


FLOW_REPAIR_PROMPT_VERSION = "flow-repair-v1"


import os
has_langfuse = bool(os.getenv('LANGFUSE_PUBLIC_KEY')) and bool(os.getenv('LANGFUSE_SECRET_KEY'))
if has_langfuse:
    from langfuse.langchain import CallbackHandler

# ── LLM 준비 (제공자 교체 지점) ──────────────────────────────────────────
def get_llm(
    session_id=None,
    tags=None,
    complexity_level="low",
    langfuse_handler=None,
    generation_trace_id=None,
):
    """메타 agent용 모델을 공통 provider 설정에서 생성한다."""
    from llm.providers import create_chat_model

    llm = create_chat_model(
        profile=complexity_level,
        temperature=0,
        required_capabilities={"structured_output", "tool_calling"},
    )
    if has_langfuse and langfuse_handler:
        if tags is None:
            tags = ["agent_generation"]
        metadata = {}
        if session_id:
            metadata["langfuse_session_id"] = f"generation-{session_id}"
        if generation_trace_id:
            metadata["generation_trace_id"] = generation_trace_id
        llm = llm.with_config(callbacks=[langfuse_handler], metadata=metadata, tags=tags)
    return llm


SYSTEM = (
    "너는 노코드 agent 빌더의 설계 도우미다. 사용자의 요청을 읽고, "
    "아래 노드만으로 실행 가능한 워크플로우(graph_data)를 만든다.\n\n"
    "**반드시 지켜야 할 원칙:**\n"
    "1. 사용자가 명시적으로 말한 내용만 정확히 구현하라. 요청에 없는 보조 노드(실패 알림, "
    "승인 절차, 재시도 로직 등)를 임의로 추가하지 마라 — 이런 건 사용자가 결과를 보고 "
    "에디터에서 직접 add_node/connect_nodes로 붙이는 몫이다.\n"
    "2. 요청이 짧거나 모호해도 되묻지 말고 가장 직접적이고 단순한 해석으로 채우되, "
    "과도하게 확장하거나 풍부하게 만들려고 하지 마라. 최소한의 노드로 요청을 그대로 구현하는 "
    "것이 목표다.\n\n"
    + NODE_CATALOG
    + workflow_patterns.PATTERN_CATALOG
    + node_bindings.BINDING_CATALOG
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
    + workflow_patterns.PATTERN_CATALOG
    + node_bindings.BINDING_CATALOG
)

# few-shot 예시 — 생성 품질을 좌우하는 핵심. 실패 사례를 여기에 계속 보강한다(팀원 C).
# 빠름/정밀이 서로 다른 예시 세트를 쓴다(2026-07-16) — 두 티어의 "생성 철학"이 정반대라서
# (빠름=요청한 것만 리터럴 구현, 정밀=요청에 없어도 필요해 보이면 보조 노드를 알아서 추가) 같은
# 예시를 공유하면 한쪽 원칙과 충돌한다. 실제로 구 FEWSHOT의 예시12(해커뉴스→카톡)가 요청에
# 없는 humanApprovalNode(승인 절차)를 추가하는 정밀 스타일 예시였는데, 이게 빠름에도 공유되면서
# 빠름의 원칙 1번("요청에 없는 승인 절차 등을 임의로 추가하지 마라")과 정면으로 충돌하고 있었다.
FEWSHOT_FAST = """\
[예시1] 요청: "PDF 요약봇 만들어줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"valueNode","data":{"file_path":""}},
  {"id":"n3","type":"tokenizerNode","data":{"method":"extract_text"}},
  {"id":"n4","type":"promptNode","data":{"userPrompt":"다음 문서를 요약해줘"}},
  {"id":"n5","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
# ↑ tokenizerNode는 "직전 노드의 출력이 파일 경로"여야 동작한다. startNode 바로 뒤에 tokenizerNode를
# 놓으면 파일을 받을 방법이 없어 매번 실패한다 — 반드시 valueNode(file_path, 초기값은 빈 문자열)를
# 사이에 두고, 답변에서 "n2(valueNode)를 클릭해서 PDF/문서 파일을 업로드해야 실제로 동작한다"고 안내한다.

[예시2] 요청: "날씨 API 호출해서 결과를 한국어로 요약해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
  {"id":"e6","source":"n4","target":"n7","sourceHandle":"done"}
]}
# ↑ distributorNode(n4)의 기본 엣지(n4→n5→n6)는 글 목록 개수만큼 반복 실행되고,
# sourceHandle="done" 엣지(n4→n7)는 반복이 다 끝난 뒤 딱 한 번만 실행된다. outputNode(n7)를
# 반복 안에 두면(예: n6→n7로 직접 연결) 첫 번째 글만 처리하고 그 즉시 끝나버리므로 반드시
# done 경로로 연결해야 한다.

[예시6] 요청: "계약서_템플릿.docx 파일의 빈칸을 채워서 완성해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"templateAnalyzerNode","data":{"template_path":"계약서_템플릿.docx"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 JSON의 각 키에 대해 문맥에 맞는 값을 채워서 같은 형식의 JSON으로만 답해"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 문서 양식을 채우는 도우미다. 반드시 JSON 형식으로만 답한다","useStructuredOutput":true,"jsonSchema":"{\\"title\\":\\"FilledFields\\",\\"type\\":\\"object\\",\\"additionalProperties\\":{\\"type\\":\\"string\\"}}"}},
  {"id":"n5","type":"fileModifierNode","data":{"template_path":"계약서_템플릿.docx"}},
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://example.com/news"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 뉴스를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"team@company.com","subject":"뉴스 요약"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ emailNode로 메일을 보내는 게 이 요청의 최종 목적이라, 그 뒤에 outputNode를 더 붙이지 않는다
# (emailNode 자체가 최종 결과 전달이다 — discordNode/kakaoNode/slackNode도 마찬가지).

[예시8] 요청: "customers 테이블에서 이메일만 뽑아서 보여줘 (DB 접속정보: postgresql://user:pass@localhost:5432/shop)"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"databaseNode","data":{"connectionString":"{{API_CENTER:database}}","query":"SELECT email FROM customers"}},
  {"id":"n3","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"}
]}
# ↑ 사용자가 접속 정보를 대화에 적어줬어도 connectionString에는 절대 원문을 넣지 않는다 —
#   항상 "{{API_CENTER:database}}"로 두고, 답변에서 "API 센터에 등록해달라"고 안내한다
#   (그래프는 저장·공유·이력이 남는 곳이라 비밀번호가 들어가면 안 된다).

[예시9] 요청: "사용자 요청을 번역, 요약, 감성 분석 에이전트에게 보내서 알아서 처리하게 해주는 매니저 봇을 만들어줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 날씨 정보를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"날씨 전문가"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"me@example.com","subject":"오늘의 날씨"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ 정기적으로 실행해야 하므로 startNode 대신 scheduleNode(cronExpression 포함)로 시작한다.
# emailNode 발송으로 끝나므로 outputNode는 붙이지 않는다.

[예시12] 요청: "매일 아침에 해커뉴스 크롤링해서 좋은 글 있으면 요약해서 카카오톡으로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://news.ycombinator.com"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 뉴스들 중에서 IT 업계 트렌드에 맞는 '좋은 글'이 있는지 판별하고 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"뉴스 큐레이터"}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"r1","operator":"Contains","value":"좋은 글 있음"}]}},
  {"id":"n6","type":"kakaoNode","data":{"accessToken":"{{API_CENTER:kakao_token}}","receiver":""}},
  {"id":"n7","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"r1"},
  {"id":"e6","source":"n6","target":"n7"},
  {"id":"e7","source":"n5","target":"n7","sourceHandle":"else"}
]}
# ↑ 요청에 승인 절차를 언급하지 않았으므로 humanApprovalNode를 임의로 넣지 않는다(원칙 1).
# conditionNode의 두 분기(r1, else)가 다른 노드를 거치지 않고 각각 outputNode로 바로 이어져도
# 된다 — conditionNode에서 갈라진 경로는 런타임에 하나만 타므로 mergeNode 없이 합쳐도 안전하다.

[예시13] 요청: "메일 들어오면 감성 분석해서 악플이면 슬랙으로 알림 보내고, 아니면 디스코드로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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

[예시14] 요청: "결제 요청 내용을 보여주고 제가 직접 승인하면 결제 진행 메일 보내고, 제가 거절하면 거절 메일 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"결제 요청 내용","testValue":"10만원 결제 요청"}},
  {"id":"n3","type":"humanApprovalNode","data":{"message":"이 결제 요청을 승인하시겠습니까?"}},
  {"id":"n4","type":"httpRequestNode","data":{"method":"POST","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n5","type":"valueNode","data":{"value":"결제 요청이 승인되어 후속 처리가 완료되었습니다. 고객에게 처리 완료 메일을 보냅니다."}},
  {"id":"n6","type":"emailNode","data":{"toEmail":"me@example.com","subject":"결제가 진행되었습니다"}},
  {"id":"n7","type":"valueNode","data":{"value":"결제 요청이 거절되어 진행되지 않았습니다. 필요하면 거절 사유를 함께 안내합니다."}},
  {"id":"n8","type":"emailNode","data":{"toEmail":"me@example.com","subject":"결제 요청이 거절되었습니다"}},
  {"id":"n9","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n10","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4","sourceHandle":"approved"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"},
  {"id":"e6","source":"n3","target":"n7","sourceHandle":"rejected"},
  {"id":"e7","source":"n7","target":"n8"},
  {"id":"e8","source":"n6","target":"n9"},
  {"id":"e9","source":"n8","target":"n9"},
  {"id":"e10","source":"n9","target":"n10"}
]}
# ↑ 승인 분기에서는 실제 처리(httpRequestNode)를 먼저 수행하고, 그 결과를 그대로 고객에게 보내지 말고
# valueNode 등으로 고객용 안내 문구를 만든 뒤 emailNode로 넘긴다. 거절 분기도 마찬가지로 고객용 문구를
# 따로 만든 뒤 메일을 보내는 구조가 더 안정적이다.

[예시15] 요청: "30분마다 외부 API 상태를 점검해서 장애면 슬랙으로 알려줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"*/30 * * * *"}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 응답을 보고 첫 줄은 정확히 'STATUS: DOWN' 또는 'STATUS: UP' 중 하나로, 둘째 줄은 점검 결과 요약 한 줄로만 답해"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 외부 API 상태를 판별하는 모니터링 담당자다. 출력 첫 줄은 반드시 STATUS: DOWN 또는 STATUS: UP 이어야 한다."}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"down","operator":"Contains","value":"STATUS: DOWN"}]}},
  {"id":"n6","type":"slackNode","data":{"channel":"#alerts","message":"외부 API 장애 감지"}},
  {"id":"n7","type":"valueNode","data":{"value":"STATUS: UP\\n정기 점검 결과 정상입니다."}},
  {"id":"n8","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n9","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"down"},
  {"id":"e6","source":"n5","target":"n7","sourceHandle":"else"},
  {"id":"e7","source":"n6","target":"n8"},
  {"id":"e8","source":"n7","target":"n8"},
  {"id":"e9","source":"n8","target":"n9"}
]}
# ↑ 모니터링 예시는 LLM 출력 형식을 먼저 표준화한 뒤(conditionNode가 읽기 쉬운 STATUS 라인),
# 그 문자열을 기준으로 분기하는 편이 느슨한 자연어 판정보다 훨씬 안정적이다.

[예시17] 요청: "동아리 여름 축제 홍보 포스터를 만들어서 PNG로 저장해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"포스터에 들어갈 행사 정보","testValue":"2026 여름 축제, 7월 25일 오후 6시, 대운동장, 밴드공연과 푸드트럭"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 행사 정보를 바탕으로 세로형 홍보 포스터를 디자인해줘. 크기는 900x1200 픽셀 기준이다."}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 전문 그래픽 디자이너다. 반드시 완성된 HTML 문서 하나만 답한다(설명 텍스트나 ```코드펜스 없이 <html>로 시작해서 </html>로 끝나야 한다). <style> 태그 안에 모든 CSS를 인라인으로 작성하고, body 바로 아래 900x1200px 크기의 컨테이너를 만든다. 절대 단순한 흰 배경에 텍스트만 나열하지 말고 반드시 다음을 모두 포함한다: (1) 선명한 그라데이션 배경(예: #6a11cb→#2575fc 보라-파랑, #f857a6→#ff5858 핑크-빨강, #11998e→#38ef7d 청록-라임, #ee0979→#ff6a00 마젠타-주황처럼 채도 높은 두 색 조합 중 내용에 어울리는 걸 고르거나 비슷한 톤으로 직접 만든다) 또는 선명한 색상 블록/도형으로 900x1200 전체를 채운다. 흰색이나 #f5f5f5, #fdfcf9처럼 흰색에 가까운 옅은 파스텔만으로는 배경을 채우지 마라(사실상 흰 화면처럼 보인다) — 반드시 눈에 띄게 채도 있는 색을 쓴다 — 이 배경은 가장 바깥 컨테이너 자체에 직접 입히고, 그 안에 같은 크기의 불투명한 흰색 카드를 겹쳐서 배경을 가리지 않는다(카드를 쓰려면 캔버스보다 작게 만들거나 반투명하게 한다). (2) 크고 굵은 제목(48~72px, font-weight:800 이상)과 톤을 낮춘 부제(20~28px)의 타이포그래피 위계, (3) 둥근 배지나 구분선, 아이콘/이모지, 그림자 중 최소 하나의 시각적 강조 요소, (4) 40px 이상의 넉넉한 안쪽 여백, (5) 배경과 대비되는 확실한 글자색, (6) 내용을 위쪽에만 몰아넣지 말고 가장 바깥 컨테이너에 display:flex; flex-direction:column; justify-content:space-between을 써서 제목·본문·하단 정보가 세로 전체에 고르게 분산되게 하고 캔버스 아래를 비워두지 않는다. 외부 이미지 URL이나 웹폰트 링크는 절대 쓰지 않는다(네트워크 접근이 없어 깨진다) — 시스템 기본 폰트만 사용한다."}},
  {"id":"n5","type":"posterGeneratorNode","data":{"outputFormat":"png","width":900,"height":1200}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ posterGeneratorNode(n5)는 디자인을 스스로 하지 않는다 — 바로 앞 llmNode(n4)가 만든 HTML 문자열을
# 그대로 받아 실제 Chromium으로 렌더링해서 저장할 뿐이다. 포스터 생성 자체로 흐름이 끝나는 저장형
# 결과이므로 outputNode를 붙이지 않는다.

[예시18] 요청: "직원 지각 사건 시말서를 작성해서 한글 파일로 만들고 팀장 이메일로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"사건 경위 메모","testValue":"2026-08-30 14:20, 김워크 사원이 30분 지각. 알람 미작동이 원인."}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 메모를 근거로 시말서 빈칸을 채워라. 메모에 없는 값은 지어내지 말고 빈 문자열로 둔다."}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 문서 빈칸 채우기 도우미다. 시말서 포맷의 빈칸을 채운 JSON만 답한다.","useStructuredOutput":true,"jsonSchema":"{\\"title\\": \\"IncidentReportValues\\", \\"type\\": \\"object\\", \\"properties\\": {\\"department\\": {\\"type\\": \\"string\\"}, \\"authorName\\": {\\"type\\": \\"string\\"}, \\"incidentAt\\": {\\"type\\": \\"string\\"}, \\"summary\\": {\\"type\\": \\"string\\"}, \\"cause\\": {\\"type\\": \\"string\\"}, \\"prevention\\": {\\"type\\": \\"string\\"}}, \\"required\\": [\\"department\\", \\"authorName\\", \\"incidentAt\\", \\"summary\\", \\"cause\\", \\"prevention\\"]}"}},
  {"id":"n5","type":"formatNode","data":{"formatId":"incident-report","output":"hwpx"}},
  {"id":"n6","type":"emailNode","data":{"toEmail":"","subject":"시말서 제출"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
(포맷의 빈칸을 채우는 흐름이다. formatNode 는 LLM 을 부르지 않으므로 값은 앞 llmNode 가
 useStructuredOutput 으로 만들고, 스키마의 키 이름은 포맷의 빈칸 이름과 같아야 한다.
 jsonSchema 의 title 은 영문·숫자·밑줄만 쓴다(한글 제목은 OpenAI 가 거부한다).
 완성 파일은 자동으로 첨부되므로 emailNode 뒤에 outputNode 를 붙이지 않는다.
 toEmail 은 사용자가 실제 주소를 주지 않았으므로 빈 문자열로 두고 답변에서 안내한다.)

[예시19] 요청: "웹훅으로 문의가 들어오면 문의한 사람 이메일로 접수 확인 메일 보내줘. 본문에 email, name 키가 들어와"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"webhookNode","data":{"method":"POST","path":"/inquiry"}},
  {"id":"n2","type":"emailNode","data":{"toEmail":"","subject":"문의 접수 확인","bindings":{"toEmail":{"source":"n1","path":"email"}}}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"}
]}
(값을 옮기기만 하는 자리다 — jsonParserNode 나 llmNode 를 두지 않는다. 요청이 키 이름(email)을
 알려줬으므로 path 에 그대로 쓰고, 키 이름을 모르는 요청이면 path 를 빈 문자열로 둔다.
 bindings 의 source 는 실행 경로상 앞선 노드여야 한다.)
"""

# 정밀 모드용 — 빠름과 달리 "요청에 없어도 필요해 보이면 보조 노드를 알아서 추가"하는 게
# 원칙이므로, 예시12는 사람 승인 절차를 (요청에 없어도) 스스로 판단해서 추가한 버전을 그대로 쓴다.
FEWSHOT_PRECISE = """\
[예시1] 요청: "PDF 요약봇 만들어줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"valueNode","data":{"file_path":""}},
  {"id":"n3","type":"tokenizerNode","data":{"method":"extract_text"}},
  {"id":"n4","type":"promptNode","data":{"userPrompt":"다음 문서를 요약해줘"}},
  {"id":"n5","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
# ↑ tokenizerNode는 "직전 노드의 출력이 파일 경로"여야 동작한다. startNode 바로 뒤에 tokenizerNode를
# 놓으면 파일을 받을 방법이 없어 매번 실패한다 — 반드시 valueNode(file_path, 초기값은 빈 문자열)를
# 사이에 두고, 답변에서 "n2(valueNode)를 클릭해서 PDF/문서 파일을 업로드해야 실제로 동작한다"고 안내한다.

[예시2] 요청: "날씨 API 호출해서 결과를 한국어로 요약해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
  {"id":"e6","source":"n4","target":"n7","sourceHandle":"done"}
]}
# ↑ distributorNode(n4)의 기본 엣지(n4→n5→n6)는 글 목록 개수만큼 반복 실행되고,
# sourceHandle="done" 엣지(n4→n7)는 반복이 다 끝난 뒤 딱 한 번만 실행된다. outputNode(n7)를
# 반복 안에 두면(예: n6→n7로 직접 연결) 첫 번째 글만 처리하고 그 즉시 끝나버리므로 반드시
# done 경로로 연결해야 한다.

[예시6] 요청: "계약서_템플릿.docx 파일의 빈칸을 채워서 완성해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"templateAnalyzerNode","data":{"template_path":"계약서_템플릿.docx"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 JSON의 각 키에 대해 문맥에 맞는 값을 채워서 같은 형식의 JSON으로만 답해"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 문서 양식을 채우는 도우미다. 반드시 JSON 형식으로만 답한다","useStructuredOutput":true,"jsonSchema":"{\\"title\\":\\"FilledFields\\",\\"type\\":\\"object\\",\\"additionalProperties\\":{\\"type\\":\\"string\\"}}"}},
  {"id":"n5","type":"fileModifierNode","data":{"template_path":"계약서_템플릿.docx"}},
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://example.com/news"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"다음 뉴스를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"team@company.com","subject":"뉴스 요약"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ emailNode로 메일을 보내는 게 이 요청의 최종 목적이라, 그 뒤에 outputNode를 더 붙이지 않는다
# (emailNode 자체가 최종 결과 전달이다 — discordNode/kakaoNode/slackNode도 마찬가지).

[예시8] 요청: "customers 테이블에서 이메일만 뽑아서 보여줘 (DB 접속정보: postgresql://user:pass@localhost:5432/shop)"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"databaseNode","data":{"connectionString":"{{API_CENTER:database}}","query":"SELECT email FROM customers"}},
  {"id":"n3","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"}
]}
# ↑ 사용자가 접속 정보를 대화에 적어줬어도 connectionString에는 절대 원문을 넣지 않는다 —
#   항상 "{{API_CENTER:database}}"로 두고, 답변에서 "API 센터에 등록해달라"고 안내한다
#   (그래프는 저장·공유·이력이 남는 곳이라 비밀번호가 들어가면 안 된다).

[예시9] 요청: "사용자 요청을 번역, 요약, 감성 분석 에이전트에게 보내서 알아서 처리하게 해주는 매니저 봇을 만들어줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 날씨 정보를 한국어로 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"날씨 전문가"}},
  {"id":"n5","type":"emailNode","data":{"toEmail":"me@example.com","subject":"오늘의 날씨"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ 정기적으로 실행해야 하므로 startNode 대신 scheduleNode(cronExpression 포함)로 시작한다.
# emailNode 발송으로 끝나므로 outputNode는 붙이지 않는다.

[예시12] 요청: "매일 아침에 해커뉴스 크롤링해서 좋은 글 있으면 요약해서 카카오톡으로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"0 9 * * *"}},
  {"id":"n2","type":"webCrawlerNode","data":{"url":"https://news.ycombinator.com"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 뉴스들 중에서 IT 업계 트렌드에 맞는 '좋은 글'이 있는지 판별하고 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"뉴스 큐레이터"}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"r1","operator":"Contains","value":"좋은 글 있음"}]}},
  {"id":"n6","type":"humanApprovalNode","data":{"message":"카카오톡으로 발송할까요?"}},
  {"id":"n7","type":"kakaoNode","data":{"accessToken":"{{API_CENTER:kakao_token}}","receiver":""}},
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
# ↑ 짧은 요청이지만 조건 분기(conditionNode), 사람 승인(humanApprovalNode), 카카오톡 발송(kakaoNode), 병합(mergeNode)을
# 요청에 명시되지 않았어도 실제 서비스 수준에 맞게 스스로 판단해서 추가했다 — 이게 정밀 모드의 핵심이다.

[예시13] 요청: "메일 들어오면 감성 분석해서 악플이면 슬랙으로 알림 보내고, 아니면 디스코드로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
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

[예시14] 요청: "결제 요청 내용을 보여주고 제가 직접 승인하면 결제 진행 메일 보내고, 제가 거절하면 거절 메일 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"결제 요청 내용","testValue":"10만원 결제 요청"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 결제 요청을 검토할 사람이 빠르게 판단할 수 있도록 금액, 요청 사유, 위험 포인트를 짧게 요약해줘"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 결제 승인 요청을 검토하는 운영 담당자다. 승인 판단에 필요한 핵심 정보만 짧고 정확하게 요약한다."}},
  {"id":"n5","type":"humanApprovalNode","data":{"message":"이 결제 요청을 승인하시겠습니까?"}},
  {"id":"n6","type":"httpRequestNode","data":{"method":"POST","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n7","type":"valueNode","data":{"value":"결제 요청이 승인되어 후속 처리가 완료되었습니다. 고객에게 처리 완료 메일을 발송합니다."}},
  {"id":"n8","type":"emailNode","data":{"toEmail":"me@example.com","subject":"결제가 진행되었습니다"}},
  {"id":"n9","type":"valueNode","data":{"value":"결제 요청이 거절되어 진행되지 않았습니다. 필요하면 거절 사유를 고객 안내에 포함합니다."}},
  {"id":"n10","type":"emailNode","data":{"toEmail":"me@example.com","subject":"결제 요청이 거절되었습니다"}},
  {"id":"n11","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n12","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"approved"},
  {"id":"e6","source":"n6","target":"n7"},
  {"id":"e7","source":"n7","target":"n8"},
  {"id":"e8","source":"n5","target":"n9","sourceHandle":"rejected"},
  {"id":"e9","source":"n9","target":"n10"},
  {"id":"e10","source":"n8","target":"n11"},
  {"id":"e11","source":"n10","target":"n11"},
  {"id":"e12","source":"n11","target":"n12"}
]}
# ↑ 정밀 모드에서는 승인 전에 사람이 읽기 좋은 요약(promptNode→llmNode)을 먼저 만들고,
# 승인 뒤 실제 처리와 고객용 안내를 분리해 구성하는 식으로 살을 붙인다.

[예시15] 요청: "보안 알림 들어오면 심각도 확인해서, 심각하면 승인받고 차단하고 아니면 그냥 기록만 해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"webhookNode","data":{"method":"POST","path":"/siem-alert"}},
  {"id":"n2","type":"promptNode","data":{"userPrompt":"이 보안 알림의 심각도를 판별해줘. 심각하면 정확히 'CRITICAL', 아니면 정확히 'NORMAL'이라고만 답해"}},
  {"id":"n3","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 보안 알림의 심각도를 판별하는 SOC 분석가다"}},
  {"id":"n4","type":"conditionNode","data":{"rules":[{"id":"critical","operator":"Contains","value":"CRITICAL"}]}},
  {"id":"n5","type":"humanApprovalNode","data":{"message":"심각한 보안 알림입니다. 자동 차단 조치를 진행할까요?"}},
  {"id":"n6","type":"httpRequestNode","data":{"method":"POST","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n7","type":"valueNode","data":{"value":"차단은 보류되고 모니터링만 계속됩니다"}},
  {"id":"n8","type":"valueNode","data":{"value":"정상 알림으로 기록되었습니다"}},
  {"id":"n9","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n10","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5","sourceHandle":"critical"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"approved"},
  {"id":"e6","source":"n6","target":"n9"},
  {"id":"e7","source":"n5","target":"n7","sourceHandle":"rejected"},
  {"id":"e8","source":"n7","target":"n9"},
  {"id":"e9","source":"n4","target":"n8","sourceHandle":"else"},
  {"id":"e10","source":"n8","target":"n9"},
  {"id":"e11","source":"n9","target":"n10"}
]}
# ↑ conditionNode로 먼저 분류하고, 그 중 한 분기에서만(심각한 경우만) humanApprovalNode를
# 거치도록 중첩할 수 있다 — 조건 분기와 사람 승인은 서로 독립적인 노드라 이렇게 조합 가능하다.
# 심각하지 않은 else 분기는 승인 없이 바로 기록으로 끝난다.

[예시16] 요청: "30분마다 외부 API 상태를 점검해서 장애면 슬랙으로 알리고, 정상이면 결과만 남겨줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"scheduleNode","data":{"cronExpression":"*/30 * * * *"}},
  {"id":"n2","type":"httpRequestNode","data":{"method":"GET","url":"REPLACE_WITH_ACTUAL_URL"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"이 응답 또는 오류를 보고 첫 줄은 정확히 'STATUS: DOWN' 또는 'STATUS: UP' 중 하나로, 둘째 줄은 원인 추정 또는 정상 점검 요약 한 줄로만 답해"}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 외부 API 상태를 모니터링하는 SRE다. 첫 줄은 반드시 STATUS: DOWN 또는 STATUS: UP 이어야 하고, 둘째 줄에는 점검 요약만 쓴다."}},
  {"id":"n5","type":"conditionNode","data":{"rules":[{"id":"down","operator":"Contains","value":"STATUS: DOWN"}]}},
  {"id":"n6","type":"slackNode","data":{"channel":"#ops-alerts","message":"외부 API 장애가 감지되었습니다"}},
  {"id":"n7","type":"valueNode","data":{"value":"STATUS: UP\\n정기 점검 결과 정상입니다."}},
  {"id":"n8","type":"mergeNode","data":{"mergeStrategy":"join_newline"}},
  {"id":"n9","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6","sourceHandle":"down"},
  {"id":"e6","source":"n5","target":"n7","sourceHandle":"else"},
  {"id":"e7","source":"n6","target":"n8"},
  {"id":"e8","source":"n7","target":"n8"},
  {"id":"e9","source":"n8","target":"n9"}
]}
# ↑ 정밀 모드의 모니터링 예시는 LLM 출력 포맷을 강하게 고정해서 분기 정확도를 높이고,
# 장애 알림과 정상 기록 경로를 명확히 나눈다.

[예시17] 요청: "동아리 여름 축제 홍보 포스터를 만들어서 PNG로 저장해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"포스터에 들어갈 행사 정보","testValue":"2026 여름 축제, 7월 25일 오후 6시, 대운동장, 밴드공연과 푸드트럭"}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 행사 정보를 바탕으로 세로형 홍보 포스터를 디자인해줘. 크기는 900x1200 픽셀 기준이다."}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 전문 그래픽 디자이너다. 반드시 완성된 HTML 문서 하나만 답한다(설명 텍스트나 ```코드펜스 없이 <html>로 시작해서 </html>로 끝나야 한다). <style> 태그 안에 모든 CSS를 인라인으로 작성하고, body 바로 아래 900x1200px 크기의 컨테이너를 만든다. 절대 단순한 흰 배경에 텍스트만 나열하지 말고 반드시 다음을 모두 포함한다: (1) 선명한 그라데이션 배경(예: #6a11cb→#2575fc 보라-파랑, #f857a6→#ff5858 핑크-빨강, #11998e→#38ef7d 청록-라임, #ee0979→#ff6a00 마젠타-주황처럼 채도 높은 두 색 조합 중 내용에 어울리는 걸 고르거나 비슷한 톤으로 직접 만든다) 또는 선명한 색상 블록/도형으로 900x1200 전체를 채운다. 흰색이나 #f5f5f5, #fdfcf9처럼 흰색에 가까운 옅은 파스텔만으로는 배경을 채우지 마라(사실상 흰 화면처럼 보인다) — 반드시 눈에 띄게 채도 있는 색을 쓴다 — 이 배경은 가장 바깥 컨테이너 자체에 직접 입히고, 그 안에 같은 크기의 불투명한 흰색 카드를 겹쳐서 배경을 가리지 않는다(카드를 쓰려면 캔버스보다 작게 만들거나 반투명하게 한다). (2) 크고 굵은 제목(48~72px, font-weight:800 이상)과 톤을 낮춘 부제(20~28px)의 타이포그래피 위계, (3) 둥근 배지나 구분선, 아이콘/이모지, 그림자 중 최소 하나의 시각적 강조 요소, (4) 40px 이상의 넉넉한 안쪽 여백, (5) 배경과 대비되는 확실한 글자색, (6) 내용을 위쪽에만 몰아넣지 말고 가장 바깥 컨테이너에 display:flex; flex-direction:column; justify-content:space-between을 써서 제목·본문·하단 정보가 세로 전체에 고르게 분산되게 하고 캔버스 아래를 비워두지 않는다. 외부 이미지 URL이나 웹폰트 링크는 절대 쓰지 않는다(네트워크 접근이 없어 깨진다) — 시스템 기본 폰트만 사용한다."}},
  {"id":"n5","type":"posterGeneratorNode","data":{"outputFormat":"png","width":900,"height":1200}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"}
]}
# ↑ posterGeneratorNode(n5)는 디자인을 스스로 하지 않는다 — 바로 앞 llmNode(n4)가 만든 HTML 문자열을
# 그대로 받아 실제 Chromium으로 렌더링해서 저장할 뿐이다. 그래서 HTML을 실제로 "잘 만들게" 하는 책임은
# n4의 systemPrompt에 있다. 포스터 생성 자체로 흐름이 끝나는 저장형 결과이므로 outputNode를 붙이지 않는다.
[예시18] 요청: "직원 지각 사건 시말서를 작성해서 한글 파일로 만들고 팀장 이메일로 보내줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"dynamicInputNode","data":{"inputLabel":"사건 경위 메모","testValue":"2026-08-30 14:20, 김워크 사원이 30분 지각. 알람 미작동이 원인."}},
  {"id":"n3","type":"promptNode","data":{"userPrompt":"위 메모를 근거로 시말서 빈칸을 채워라. 메모에 없는 값은 지어내지 말고 빈 문자열로 둔다."}},
  {"id":"n4","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 문서 빈칸 채우기 도우미다. 시말서 포맷의 빈칸을 채운 JSON만 답한다.","useStructuredOutput":true,"jsonSchema":"{\\"title\\": \\"IncidentReportValues\\", \\"type\\": \\"object\\", \\"properties\\": {\\"department\\": {\\"type\\": \\"string\\"}, \\"authorName\\": {\\"type\\": \\"string\\"}, \\"incidentAt\\": {\\"type\\": \\"string\\"}, \\"summary\\": {\\"type\\": \\"string\\"}, \\"cause\\": {\\"type\\": \\"string\\"}, \\"prevention\\": {\\"type\\": \\"string\\"}}, \\"required\\": [\\"department\\", \\"authorName\\", \\"incidentAt\\", \\"summary\\", \\"cause\\", \\"prevention\\"]}"}},
  {"id":"n5","type":"formatNode","data":{"formatId":"incident-report","output":"hwpx"}},
  {"id":"n6","type":"emailNode","data":{"toEmail":"","subject":"시말서 제출"}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
(포맷의 빈칸을 채우는 흐름이다. formatNode 는 LLM 을 부르지 않으므로 값은 앞 llmNode 가
 useStructuredOutput 으로 만들고, 스키마의 키 이름은 포맷의 빈칸 이름과 같아야 한다.
 jsonSchema 의 title 은 영문·숫자·밑줄만 쓴다(한글 제목은 OpenAI 가 거부한다).
 완성 파일은 자동으로 첨부되므로 emailNode 뒤에 outputNode 를 붙이지 않는다.
 toEmail 은 사용자가 실제 주소를 주지 않았으므로 빈 문자열로 두고 답변에서 안내한다.)

[예시19] 요청: "네이버 블로그에서 '전기차 보조금' 검색해서 첫 글 본문을 크롤링해 요약해줘"
{"title": "예시 워크플로우", "description": "이 워크플로우는 사용자의 요청에 따라 생성되었습니다.", "nodes":[
  {"id":"n1","type":"startNode","data":{}},
  {"id":"n2","type":"naverSearchNode","data":{"mode":"blog","query":"전기차 보조금","display":5}},
  {"id":"n3","type":"webCrawlerNode","data":{"url":"","output":"text","bindings":{"url":{"source":"n2","path":"items[0].link"}}}},
  {"id":"n4","type":"promptNode","data":{"userPrompt":"다음 글을 한국어로 요약해줘"}},
  {"id":"n5","type":"llmNode","data":{"model":"gpt-4o-mini","systemPrompt":"너는 요약 전문가다"}},
  {"id":"n6","type":"outputNode","data":{}}
],"edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"},
  {"id":"e3","source":"n3","target":"n4"},
  {"id":"e4","source":"n4","target":"n5"},
  {"id":"e5","source":"n5","target":"n6"}
]}
(검색 결과에서 URL 하나를 꺼내 다음 노드의 필드에 넣는 자리다 — jsonParserNode 를 두지 않고
 bindings 로 직접 꽂는다. naverSearchNode 는 출력 형식이 카탈로그에 적혀 있어서 path
 (items[0].link)를 쓸 수 있다. 출력 형식이 적혀 있지 않은 노드라면 path 를 비워 둔다.
 요약은 실제로 생각이 필요한 일이므로 llmNode 를 그대로 둔다.)

"""


# ── ③ 생성 ───────────────────────────────────────────────────────────────
def _strip_positions(g: FlowGraph) -> FlowGraph:
    """LLM이 혹시 position을 채워서 냈어도 무시한다 — generate_flow/modify_flow는 항상
    '전체를 새로 만든다'는 뜻이므로, 좌표는 auto_layout이 새로 배치해야 한다(기존 캔버스
    배치를 사용자가 손으로 잡아놨어도 이 경로에서는 의도적으로 전체 재배치가 맞다)."""
    for n in g.nodes:
        n.position = None
    return g


def generate_flow(user_request: str, complexity_level: str = "low") -> FlowGraph:
    llm = get_llm(complexity_level=complexity_level).with_structured_output(FlowGraph, method="function_calling")   # 출력을 FlowGraph 형식으로 강제
    # 요청과 관련 있을 법한 노드만 추려서 카탈로그를 줄인다(선별 실패 시 build_trimmed_catalog가
    # 알아서 전체 NODE_CATALOG로 폴백하므로 최악의 경우도 트리밍 이전과 동일하다).
    trimmed_catalog = _select_and_trim_catalog(user_request, complexity_level, stage="generate_flow")
    system_prompt = SYSTEM.replace(NODE_CATALOG, trimmed_catalog, 1)
    messages = [
        ("system", system_prompt + "\n\n" + FEWSHOT_FAST),
        ("user", f'요청: "{user_request}"\n위 규칙에 맞는 graph_data를 만들어줘.'),
    ]
    return _strip_positions(llm.invoke(messages))


def generate_flow_from_template(user_request: str, template: FlowGraph, session_id=None, complexity_level: str = "low") -> FlowGraph:
    """Medium 모드 전용: Pre-translated DB에서 가져온 템플릿의 구조를 골격으로 유지하면서
    파라미터만 사용자 요청에 맞게 수정한다.

    템플릿이 비선형(분기/병합/반복)이면 결과도 자연스럽게 비선형 구조를 유지한다.
    사용자가 짧게 말해도 프로덕트급 워크플로우가 나오는 핵심 메커니즘."""
    llm = get_llm(session_id=session_id, tags=["template_application"], complexity_level=complexity_level).with_structured_output(FlowGraph, method="function_calling")
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
    + workflow_patterns.PATTERN_CATALOG
    + node_bindings.BINDING_CATALOG
)


def generate_flow_precise(user_request: str, complexity_level: str = "high") -> FlowGraph:
    """정밀 모드 전용: 템플릿 검색 없이, 사용자 요청을 더 꼼꼼히 해석해서
    프로덕트급 수준으로 살을 붙여 생성한다."""
    llm = get_llm(complexity_level=complexity_level).with_structured_output(FlowGraph, method="function_calling")
    trimmed_catalog = _select_and_trim_catalog(user_request, complexity_level, stage="generate_flow_precise")
    system_prompt = PRECISE_SYSTEM.replace(NODE_CATALOG, trimmed_catalog, 1)
    messages = [
        ("system", system_prompt + "\n\n" + FEWSHOT_PRECISE),
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
# NodeDefinition으로 이전한 노드의 허용값은 정의 파일의 select options에서 파생시킨다 —
# 에디터 드롭다운에 뜨는 선택지와 검증기가 통과시키는 값이 구조적으로 같아진다(ADR-0005).
ALLOWED_MODELS = node_definition.option_values("llmNode", "model")
ALLOWED_OPERATORS = node_definition.option_values("conditionNode", "rules.operator")
ALLOWED_HTTP_METHODS = node_definition.option_values("httpRequestNode", "method")
# 아직 이전하지 않은 노드의 허용값은 여기 그대로 둔다.
ALLOWED_METHODS = {"extract_text", "chunk_pages"}
ALLOWED_JSON_PARSER_MODES = node_definition.option_values("jsonParserNode", "mode")
LOOP_PRODUCING_NODE_TYPES = {"distributorNode"}  # breakNode가 유효하려면 상류에 이 중 하나가 있어야 한다(추후 loopNode 등 추가 시 여기에 더한다)
# 그 자체로 외부에 결과를 발송/전달하거나 영구 반영(저장)하는 노드 — 이걸로 흐름이 끝나면
# outputNode 없이도 완결로 인정한다. databaseNode는 검증기가 SELECT/WITH만 허용하고
# INSERT/UPDATE/DELETE는 전부 차단하므로(_validate_node_data 참고) 항상 "조회" 결과가 나오고,
# 그 결과는 반드시 사용자에게 보여줘야 하므로 여기 포함하지 않는다(포함하면 조회 결과가
# outputNode 없이 조용히 버려지는 흐름을 허용하게 된다).
TERMINAL_ACTION_NODE_TYPES = {"emailNode", "discordNode", "telegramNode", "kakaoNode", "slackNode", "fileModifierNode", "posterGeneratorNode", "imageGenerationNode"}
# googleSheetsNode/googleCalendarNode/notionNode는 databaseNode와 달리 "쓰기"도 할 수 있는
# 노드라, 위 TERMINAL_ACTION_NODE_TYPES처럼 타입만으로 무조건 통과시키면 read/list/query
# 모드로 흐름이 끝날 때도 결과가 조용히 버려지는 걸 허용하게 된다(원래 outputNode를 강제한
# 이유와 동일). 그렇다고 이 세 노드가 항상 outputNode를 요구하면, discordNode/kakaoNode와
# 똑같이 "쓰기 자체가 최종 결과 전달"인 create/append/write 모드까지 불필요하게 막혀버린다
# — 실제로 이 제약 때문에 사용자가 불편을 겪었다. 그래서 모드별로 판단한다: 이 모드일 때만
# "그 자체로 끝나도 되는" 발송/저장형 액션으로 본다.
MODE_AWARE_TERMINAL_NODE_TYPES = {
    "googleSheetsNode": {"append", "write"},
    "googleCalendarNode": {"create"},
    "notionNode": {"create"},
}


def validate_flow(g: FlowGraph, require_complete: bool = True) -> Tuple[bool, List[str]]:
    """유효하면 (True, []), 아니면 (False, [사람이 읽을 사유들]). 사유는 재시도 프롬프트에 재사용.

    검사 항목(계약 §3 기준):
      1) startNode 정확히 1개로 시작        ← require_complete=True일 때만
      2) outputNode로 종료(1개 이상), 단 emailNode/discordNode/kakaoNode/slackNode 같은 발송형
         액션 노드나 fileModifierNode 같은 저장형 액션 노드가 더 이상 나가는 엣지 없이 끝나면
         outputNode 없이도 통과(그 자체가 최종 결과 전달/반영이므로) ← require_complete=True일 때만
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
      14) 고아 노드 — 시작 노드(startNode/scheduleNode/webhookNode/discordTriggerNode/telegramTriggerNode)가 아닌데 들어오는 엣지가 하나도
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
        start_count = sum(types.count(t) for t in START_NODE_TYPES)
        if start_count != 1:
            names = ", ".join(sorted(START_NODE_TYPES))
            errors.append(f"시작 노드({names} 중 하나)는 정확히 1개여야 한다 (현재 {start_count}개)")

        has_output_node = "outputNode" in types
        # tools/template 핸들은 실제 제어 흐름이 아니라 배선(서브에이전트/템플릿 연결)이므로 제외
        sources_with_real_outgoing = {e.source for e in g.edges if e.targetHandle not in ("tools", "template")}

        def _is_terminal_leaf(n) -> bool:
            if n.id in sources_with_real_outgoing:
                return False
            if n.type in TERMINAL_ACTION_NODE_TYPES:
                return True
            allowed_modes = MODE_AWARE_TERMINAL_NODE_TYPES.get(n.type)
            if allowed_modes is not None:
                return (n.data or {}).get("mode") in allowed_modes
            return False

        ends_with_terminal_action = any(_is_terminal_leaf(n) for n in g.nodes)
        if not has_output_node and not ends_with_terminal_action:
            errors.append(
                "outputNode(종료)가 없다 — 또는 emailNode/discordNode/kakaoNode/slackNode 같은 "
                "발송형 액션 노드나 fileModifierNode 같은 저장형 액션 노드로 흐름이 끝나야 한다 "
                "(googleSheetsNode/googleCalendarNode/notionNode는 mode가 create/append/write일 때만 해당)"
            )

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
        if n.type in ("conditionNode", "loopNode"):
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

    # 13) posterGeneratorNode: fileModifierNode의 12)와 동일한 이유 — 렌더링할 HTML을 항상 직전
    # 노드의 출력에서 가져오므로(자기 data엔 디자인 내용이 없다), llmNode 등 실제 HTML을 만들어주는
    # 노드가 앞에 있어야 한다.
    for n in g.nodes:
        if n.type != "posterGeneratorNode":
            continue
        incoming_sources = [nodes_by_id[e.source] for e in g.edges if e.target == n.id and e.source in nodes_by_id]
        if not incoming_sources:
            errors.append(
                f"{n.id}(posterGeneratorNode)에 연결된 이전 노드가 없다 — HTML을 만들어주는 노드"
                "(promptNode → llmNode 조합 등)를 앞에 연결하라"
            )
        elif all(s.type == "startNode" for s in incoming_sources):
            errors.append(
                f"{n.id}(posterGeneratorNode)의 직전 노드가 startNode뿐이라 렌더링할 HTML을 얻을 수 없다 — "
                "llmNode 등 HTML을 만들어주는 노드를 사이에 연결하라"
            )

    # 3) 순환(cycle)
    # loopNode로 돌아오는 엣지는 반복 제어의 정상적인 back-edge다. 컴파일러가
    # maxIterations로 종료를 보장하므로 일반 DAG 순환 검사에서는 제외한다.
    loop_ids = {node.id for node in g.nodes if node.type == "loopNode"}
    cycle_edges = [edge for edge in g.edges if edge.target not in loop_ids]
    has_cycle, stuck = _has_cycle(ids, cycle_edges)
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
        start_types = {"startNode", "scheduleNode", "webhookNode", "discordTriggerNode", "telegramTriggerNode"} | node_definition.trigger_types()
        targets_with_incoming = {e.target for e in g.edges}
        tool_or_template_sources = {e.source for e in g.edges if e.targetHandle in ("tools", "template")}
        for n in g.nodes:
            # memoNode는 실행 그래프의 일부가 아닌 캔버스 주석 — 연결이 없는 게 정상이다.
            if n.type in start_types or n.id in tool_or_template_sources or n.type == "memoNode":
                continue
            if n.id not in targets_with_incoming:
                errors.append(
                    f"{n.id}({n.type})는 시작 노드가 아닌데 들어오는 엣지가 없다 — "
                    "고아 노드라 절대 실행되지 않는다. 앞 노드에 연결하거나 필요 없으면 삭제하라"
                )

    # 15) distributorNode의 반복 "안"(done이 아닌 기본 경로)에서 outputNode에 닿으면 안 됨
    # (실행 엔진 확인 결과: 반복 중 outputNode에 닿으면 그 즉시 return돼서 첫 항목만 처리하고
    # 전체 워크플로우가 끝나버린다 — 조용한 버그. 반복이 다 끝난 뒤 종료하려면 done 핸들을 거쳐야 한다)
    all_forward: Dict[str, List[str]] = defaultdict(list)
    for e in g.edges:
        all_forward[e.source].append(e.target)

    def _reaches_output(start: str) -> bool:
        seen: set = set()
        stack = [start]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            u_node = nodes_by_id.get(u)
            if u_node and u_node.type == "outputNode":
                return True
            stack.extend(all_forward.get(u, []))
        return False

    for n in g.nodes:
        if n.type != "distributorNode":
            continue
        body_targets = [e.target for e in g.edges if e.source == n.id and e.sourceHandle != "done"]
        for t in body_targets:
            if _reaches_output(t):
                errors.append(
                    f"{n.id}(distributorNode)의 반복 안(기본 경로)이 outputNode까지 이어진다 — "
                    "반복 중 outputNode에 닿으면 첫 항목만 처리하고 즉시 종료된다. 반복이 끝난 뒤 "
                    "종료하려면 sourceHandle을 'done'으로 지정한 엣지를 통해 outputNode로 이어라"
                )
                break

    # 12) 필드 데이터 바인딩(계획 DATA_FLOW_SEPARATION_PLAN §3) — 지원하지 않는 필드,
    #     없는/상류가 아닌 소스, 잘못된 경로를 실행 전에 거부한다. 조용히 무시하면 사용자는
    #     "연결했는데 값이 안 온다"만 겪는다.
    import node_bindings
    errors.extend(node_bindings.validate_bindings(
        [n.model_dump() for n in g.nodes],
        [e.model_dump() for e in g.edges],
    ))

    return (len(errors) == 0, errors)


def validate_flow_detailed(g: FlowGraph, require_complete: bool = True) -> Tuple[bool, List[ValidationIssue]]:
    ok, messages = validate_flow(g, require_complete=require_complete)
    return ok, validation_issues(messages)


def repair_disconnected_flow(g: FlowGraph) -> Tuple[FlowGraph, List[str]]:
    """Remove only graph elements that cannot be reached or executed.

    This repair is deliberately conservative. It does not invent nodes, fields, or
    business logic; semantic repair remains the model's job.
    """
    repaired = g.model_copy(deep=True)
    repairs: List[str] = []
    node_ids = {node.id for node in repaired.nodes}

    def next_unique_id(prefix: str, existing: set[str]) -> str:
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        value = f"{prefix}{index}"
        existing.add(value)
        return value

    valid_edges = []
    seen_connections = set()
    for edge in repaired.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            repairs.append(f"고아 엣지 {edge.id} 제거")
            continue
        connection = (edge.source, edge.target, edge.sourceHandle, edge.targetHandle)
        if connection in seen_connections:
            repairs.append(f"중복 연결 엣지 {edge.id} 제거")
            continue
        seen_connections.add(connection)
        valid_edges.append(edge)
    repaired.edges = valid_edges

    output_ids = {node.id for node in repaired.nodes if node.type == "outputNode"}
    without_dead_edges = []
    for edge in repaired.edges:
        if edge.source in output_ids:
            repairs.append(f"outputNode 뒤의 죽은 엣지 {edge.id} 제거")
            continue
        without_dead_edges.append(edge)
    repaired.edges = without_dead_edges

    edge_ids = {edge.id for edge in repaired.edges}
    start_types = {"startNode", "scheduleNode", "webhookNode", "discordTriggerNode", "telegramTriggerNode"} | node_definition.trigger_types()
    if repaired.nodes and not any(node.type in start_types for node in repaired.nodes):
        incoming_ids = {
            edge.target for edge in repaired.edges if edge.targetHandle not in ("tools", "template")
        }
        roots = [node for node in repaired.nodes if node.id not in incoming_ids]
        if roots:
            if len(roots) > 1:
                existing_forward: Dict[str, List[str]] = defaultdict(list)
                for edge in repaired.edges:
                    if edge.targetHandle not in ("tools", "template"):
                        existing_forward[edge.source].append(edge.target)

                def distances_from(root_id: str) -> Dict[str, int]:
                    distances = {root_id: 0}
                    queue = [root_id]
                    while queue:
                        current = queue.pop(0)
                        for target in existing_forward.get(current, []):
                            if target not in distances:
                                distances[target] = distances[current] + 1
                                queue.append(target)
                    return distances

                root_distances = [distances_from(root.id) for root in roots]
                common = set.intersection(*(set(values) for values in root_distances))
                if common:
                    convergence_id = min(
                        common,
                        key=lambda node_id: (max(values[node_id] for values in root_distances), node_id),
                    )
                    convergence = next(node for node in repaired.nodes if node.id == convergence_id)
                    if convergence.type != "mergeNode":
                        merge_id = next_unique_id("n", node_ids)
                        repaired.nodes.append(FlowNode(
                            id=merge_id, type="mergeNode", data={"mergeStrategy": "join_newline"},
                        ))
                        branch_nodes = set().union(*(set(values) for values in root_distances))
                        for edge in repaired.edges:
                            if edge.target == convergence_id and edge.source in branch_nodes:
                                edge.target = merge_id
                        repaired.edges.append(FlowEdge(
                            id=next_unique_id("e", edge_ids), source=merge_id, target=convergence_id,
                        ))
                        repairs.append(f"다중 입력 합류 노드 {merge_id} 추가")
            start_id = next_unique_id("n", node_ids)
            repaired.nodes.append(FlowNode(id=start_id, type="startNode", data={}))
            for root in roots:
                repaired.edges.append(FlowEdge(
                    id=next_unique_id("e", edge_ids), source=start_id, target=root.id,
                ))
            repairs.append(f"누락된 시작 노드 {start_id} 추가")

    real_sources = {
        edge.source for edge in repaired.edges if edge.targetHandle not in ("tools", "template")
    }
    has_output = any(node.type == "outputNode" for node in repaired.nodes)
    has_terminal_action = any(
        node.id not in real_sources and (
            node.type in TERMINAL_ACTION_NODE_TYPES
            or (node.type in MODE_AWARE_TERMINAL_NODE_TYPES
                and (node.data or {}).get("mode") in MODE_AWARE_TERMINAL_NODE_TYPES[node.type])
        )
        for node in repaired.nodes
    )
    if repaired.nodes and not has_output and not has_terminal_action:
        leaves = [
            node for node in repaired.nodes
            if node.id not in real_sources and node.type not in start_types
        ]
        if leaves:
            output_id = next_unique_id("n", node_ids)
            repaired.nodes.append(FlowNode(id=output_id, type="outputNode", data={}))
            if len(leaves) == 1:
                terminal_source = leaves[0].id
            else:
                merge_id = next_unique_id("n", node_ids)
                repaired.nodes.append(FlowNode(
                    id=merge_id, type="mergeNode", data={"mergeStrategy": "join_newline"},
                ))
                for leaf in leaves:
                    repaired.edges.append(FlowEdge(
                        id=next_unique_id("e", edge_ids), source=leaf.id, target=merge_id,
                    ))
                terminal_source = merge_id
            repaired.edges.append(FlowEdge(
                id=next_unique_id("e", edge_ids), source=terminal_source, target=output_id,
            ))
            repairs.append(f"누락된 종료 노드 {output_id} 추가")

    # distributor 본문에서 output으로 가면 첫 항목에서 전체 실행이 끝난다. 해당 연결은
    # 끊고 같은 output을 done 경로에서 한 번만 실행하도록 옮긴다.
    forward: Dict[str, List[str]] = defaultdict(list)
    for edge in repaired.edges:
        if edge.targetHandle not in ("tools", "template"):
            forward[edge.source].append(edge.target)
    output_ids = {node.id for node in repaired.nodes if node.type == "outputNode"}
    for distributor in [node for node in repaired.nodes if node.type == "distributorNode"]:
        body_starts = [
            edge.target for edge in repaired.edges
            if edge.source == distributor.id and edge.sourceHandle != "done"
        ]
        body_reachable = set()
        stack = list(body_starts)
        while stack:
            current = stack.pop()
            if current in body_reachable:
                continue
            body_reachable.add(current)
            stack.extend(forward.get(current, []))
        reached_outputs = body_reachable & output_ids
        for output_id in reached_outputs:
            removed = [
                edge for edge in repaired.edges
                if edge.target == output_id and edge.source in body_reachable
            ]
            if not removed:
                continue
            repaired.edges = [edge for edge in repaired.edges if edge not in removed]
            done_edges = [
                edge for edge in repaired.edges
                if edge.source == distributor.id and edge.sourceHandle == "done"
            ]
            if done_edges:
                done_edges[0].target = output_id
                repaired.edges = [edge for edge in repaired.edges if edge not in done_edges[1:]]
            else:
                repaired.edges.append(FlowEdge(
                    id=next_unique_id("e", edge_ids),
                    source=distributor.id,
                    target=output_id,
                    sourceHandle="done",
                ))
            repairs.append(f"{distributor.id} 반복 출력을 done 경로로 이동")

    roots = [node.id for node in repaired.nodes if node.type in start_types]
    forward = defaultdict(list)
    for edge in repaired.edges:
        if edge.targetHandle not in ("tools", "template"):
            forward[edge.source].append(edge.target)

    reachable = set()
    stack = list(roots)
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(forward.get(current, []))

    # Tool and template source nodes are executable wiring even though control flow
    # intentionally does not reach them.
    wired_sources = {
        edge.source for edge in repaired.edges
        if edge.targetHandle in ("tools", "template") and edge.target in reachable
    }
    keep_ids = reachable | wired_sources
    if roots and keep_ids:
        removed_ids = [node.id for node in repaired.nodes if node.id not in keep_ids]
        if removed_ids:
            repairs.append(f"시작점에서 도달 불가능한 노드 제거: {', '.join(removed_ids)}")
            repaired.nodes = [node for node in repaired.nodes if node.id in keep_ids]
            repaired.edges = [
                edge for edge in repaired.edges if edge.source in keep_ids and edge.target in keep_ids
            ]

    # 실행될 수 없는 데이터 바인딩 정리(계획 §6). 생성 모델이 다른 노드의 필드 이름을 옮겨 적거나
    # (예: formatNode 에 toEmail) 없는 노드를 소스로 쓰면, 그 바인딩은 생성 코드가 읽지 않으므로
    # 실행에 아무 영향이 없는데 검증만 실패시킨다 — 도달 불가능한 엣지와 같은 부류다.
    # 사용자가 에디터에서 직접 만든 바인딩은 이 경로를 타지 않는다(그쪽은 validate_bindings 가 거부한다).
    live_ids = {node.id for node in repaired.nodes}
    for node in repaired.nodes:
        bindings = (node.data or {}).get("bindings")
        if not isinstance(bindings, dict):
            continue
        allowed = node_bindings.bindable_fields(str(node.type))
        kept = {}
        for field, spec in bindings.items():
            if field not in allowed:
                repairs.append(f"{node.id}({node.type})가 지원하지 않는 '{field}' 바인딩 제거")
                continue
            if not isinstance(spec, dict) or spec.get("source") not in live_ids:
                repairs.append(f"{node.id}({node.type})의 '{field}' 바인딩 소스가 없어 제거")
                continue
            kept[field] = spec
        if kept != bindings:
            node.data = {**node.data, "bindings": kept}
            if not kept:
                node.data.pop("bindings")

    return repaired, repairs


def apply_flow_repair_plan(g: FlowGraph, plan: FlowRepairPlan) -> Tuple[FlowGraph, List[str]]:
    operation_count = (
        len(plan.update_nodes) + len(plan.add_nodes) + len(plan.remove_node_ids)
        + len(plan.add_edges) + len(plan.remove_edge_ids)
    )
    max_operations = int(os.getenv("LLM_REPAIR_MAX_OPERATIONS", "12"))
    if operation_count == 0:
        raise ValueError("repair plan에 적용할 작업이 없습니다.")
    if operation_count > max_operations:
        raise ValueError(f"repair plan 작업 수가 제한을 초과했습니다: {operation_count}/{max_operations}")

    repaired = g.model_copy(deep=True)
    notes: List[str] = []
    remove_nodes = set(plan.remove_node_ids)
    remove_edges = set(plan.remove_edge_ids)

    if remove_nodes:
        known = {node.id for node in repaired.nodes}
        unknown = remove_nodes - known
        if unknown:
            raise ValueError(f"존재하지 않는 노드 제거 요청: {', '.join(sorted(unknown))}")
        repaired.nodes = [node for node in repaired.nodes if node.id not in remove_nodes]
        repaired.edges = [
            edge for edge in repaired.edges
            if edge.source not in remove_nodes and edge.target not in remove_nodes
        ]
        notes.append(f"노드 제거: {', '.join(sorted(remove_nodes))}")

    if remove_edges:
        known = {edge.id for edge in repaired.edges}
        unknown = remove_edges - known
        if unknown:
            raise ValueError(f"존재하지 않는 엣지 제거 요청: {', '.join(sorted(unknown))}")
        repaired.edges = [edge for edge in repaired.edges if edge.id not in remove_edges]
        notes.append(f"엣지 제거: {', '.join(sorted(remove_edges))}")

    nodes_by_id = {node.id: node for node in repaired.nodes}
    for patch in plan.update_nodes:
        node = nodes_by_id.get(patch.id)
        if node is None:
            raise ValueError(f"존재하지 않는 노드 수정 요청: {patch.id}")
        if patch.type is not None:
            node.type = patch.type
        if patch.data is not None:
            node.data = {**(node.data or {}), **patch.data}
        notes.append(f"노드 수정: {patch.id}")

    for node in plan.add_nodes:
        if node.id in nodes_by_id:
            raise ValueError(f"이미 존재하는 노드 추가 요청: {node.id}")
        repaired.nodes.append(node)
        nodes_by_id[node.id] = node
        notes.append(f"노드 추가: {node.id}")

    edges_by_id = {edge.id: edge for edge in repaired.edges}
    for edge in plan.add_edges:
        if edge.id in edges_by_id:
            raise ValueError(f"이미 존재하는 엣지 추가 요청: {edge.id}")
        if edge.source not in nodes_by_id or edge.target not in nodes_by_id:
            raise ValueError(f"새 엣지 {edge.id}의 source/target 노드가 존재하지 않습니다.")
        repaired.edges.append(edge)
        edges_by_id[edge.id] = edge
        notes.append(f"엣지 추가: {edge.id}")

    return repaired, notes


def repair_flow_partially(
    g: FlowGraph,
    user_request: str,
    issues: List[ValidationIssue],
    complexity_level: str = "low",
) -> Tuple[FlowGraph, FlowRepairPlan, List[str]]:
    llm = get_llm(complexity_level=complexity_level).with_structured_output(
        FlowRepairPlan, method="function_calling",
    )
    repairable_ids = sorted({issue.node_id for issue in issues if issue.node_id})
    repairable_edge_ids = sorted({issue.edge_id for issue in issues if issue.edge_id})
    messages = [
        ("system", (
            "너는 워크플로우 그래프의 부분 수정기다. 전체 그래프를 새로 만들지 말고 validator issue를 "
            "해결하는 최소 작업만 FlowRepairPlan으로 반환한다. 요청에 없던 기능을 추가하지 않는다. "
            "update_nodes.data는 기존 data와 병합되므로 바꿀 필드만 넣는다. add_nodes/add_edges에는 "
            "기존과 겹치지 않는 id를 쓴다. 오류와 무관한 노드나 엣지는 절대 제거하거나 수정하지 않는다. "
            "필수 설정값을 모르면 빈 문자열 대신 REPLACE_WITH_ACTUAL_URL, REPLACE_WITH_RECIPIENT_EMAIL처럼 "
            "용도를 알 수 있는 placeholder를 넣는다. "
            f"수정 대상으로 우선 고려할 node id: {repairable_ids or '(없음)'}, edge id: {repairable_edge_ids or '(없음)'}."
        )),
        ("user", (
            f"원래 사용자 요청:\n{user_request}\n\n"
            f"현재 그래프:\n{g.model_dump_json()}\n\n"
            f"validator issues:\n{json.dumps([issue.model_dump() for issue in issues], ensure_ascii=False)}\n\n"
            "이 issue들만 해결하는 최소 repair plan을 반환해라."
        )),
    ]
    plan = llm.invoke(messages)
    repaired, notes = apply_flow_repair_plan(g, plan)
    return repaired, plan, notes


def repair_task_coverage_deterministically(
    g: FlowGraph,
    spec: TaskSpec,
    issues: List[ValidationIssue],
) -> Tuple[FlowGraph, List[str]]:
    repaired = g.model_copy(deep=True)
    notes: List[str] = []
    codes = {issue.code for issue in issues}

    def next_id(prefix: str, existing: set[str]) -> str:
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        return f"{prefix}{index}"

    node_ids = {node.id for node in repaired.nodes}
    edge_ids = {edge.id for edge in repaired.edges}

    def insert_before(node_type: str, data: Dict[str, Any], target_types: set[str]) -> Optional[str]:
        targets = [node for node in repaired.nodes if node.type in target_types]
        if not targets:
            return None
        target = targets[0]
        incoming = [
            edge for edge in repaired.edges
            if edge.target == target.id and edge.targetHandle not in ("tools", "template")
        ]
        if not incoming:
            return None
        inserted_id = next_id("n", node_ids)
        for edge in incoming:
            edge.target = inserted_id
        final_edge_id = next_id("e", edge_ids)
        repaired.nodes.append(FlowNode(id=inserted_id, type=node_type, data=data))
        repaired.edges.append(FlowEdge(id=final_edge_id, source=inserted_id, target=target.id))
        node_ids.add(inserted_id)
        edge_ids.add(final_edge_id)
        return inserted_id

    def insert_after_approval(node_type: str, data: Dict[str, Any]) -> Optional[str]:
        approvals = [node for node in repaired.nodes if node.type == "humanApprovalNode"]
        if not approvals:
            return None
        outgoing = [
            edge for edge in repaired.edges
            if edge.source == approvals[0].id and edge.sourceHandle in ("approved", "approve")
        ]
        if not outgoing:
            return None
        original = outgoing[0]
        inserted_id = next_id("n", node_ids)
        bridge_id = next_id("e", edge_ids)
        original.source = inserted_id
        original.sourceHandle = None
        repaired.nodes.append(FlowNode(id=inserted_id, type=node_type, data=data))
        repaired.edges.append(FlowEdge(
            id=bridge_id,
            source=approvals[0].id,
            target=inserted_id,
            sourceHandle="approved",
        ))
        node_ids.add(inserted_id)
        edge_ids.add(bridge_id)
        return inserted_id

    trigger_issues = [issue for issue in issues if issue.code == "INTENT_TRIGGER_MISSING"]
    for issue in trigger_issues:
        expected = set(issue.details.get("expected_node_types") or [])
        starts = [node for node in repaired.nodes if node.type == "startNode"]
        if len(starts) != 1:
            continue
        start = starts[0]
        if "webhookNode" in expected:
            start.type = "webhookNode"
            start.data = {"method": "POST", "path": "/webhook"}
            notes.append(f"TaskSpec webhook 트리거로 {start.id} 교체")
        elif "scheduleNode" in expected:
            trigger_text = spec.trigger or spec.goal
            minute_match = re.search(r"(\d+)\s*분마다", trigger_text)
            hour_match = re.search(r"(?:매일\s*)?(\d{1,2})\s*시", trigger_text)
            cron = (
                f"*/{minute_match.group(1)} * * * *" if minute_match
                else f"0 {hour_match.group(1)} * * *" if hour_match
                else "0 9 * * *"
            )
            start.type = "scheduleNode"
            start.data = {"cronExpression": cron}
            notes.append(f"TaskSpec 정기 트리거로 {start.id} 교체")

    if "INTENT_RUNTIME_INPUT_MISSING" in codes:
        starts = [node for node in repaired.nodes if node.type == "startNode"]
        if len(starts) == 1:
            start = starts[0]
            input_id = next_id("n", node_ids)
            labels = spec.inputs or [
                item.description for item in spec.missing_information if item.category == "runtime_input"
            ]
            input_node = FlowNode(
                id=input_id,
                type="dynamicInputNode",
                data={"inputLabel": ", ".join(labels) or "실행 입력", "testValue": ""},
            )
            outgoing = [
                edge for edge in repaired.edges
                if edge.source == start.id and edge.targetHandle not in ("tools", "template")
            ]
            for edge in outgoing:
                edge.source = input_id
            bridge_id = next_id("e", edge_ids)
            repaired.nodes.append(input_node)
            repaired.edges.append(FlowEdge(id=bridge_id, source=start.id, target=input_id))
            node_ids.add(input_id)
            edge_ids.add(bridge_id)
            notes.append(f"TaskSpec 실행 입력 노드 {input_id} 삽입")

    integration_issues = [issue for issue in issues if issue.code == "INTENT_INTEGRATION_MISSING"]
    integration_defaults = {
        "emailNode": {"toEmail": "REPLACE_WITH_RECIPIENT_EMAIL", "subject": "자동화 알림"},
        "slackNode": {"channel": "REPLACE_WITH_SLACK_CHANNEL", "message": "자동화 결과"},
        "discordNode": {"botToken": "", "channelId": ""},
        "kakaoNode": {"accessToken": "{{API_CENTER:kakao_token}}", "receiver": ""},
        "telegramNode": {"botToken": "", "chatId": ""},
        "googleCalendarNode": {"mode": "create"},
        "googleSheetsNode": {"mode": "append"},
        "notionNode": {"mode": "create"},
    }
    existing_types = {node.type for node in repaired.nodes}
    for issue in integration_issues:
        expected = issue.details.get("expected_node_types") or []
        node_type = next((value for value in expected if value not in existing_types), None)
        outputs = [node for node in repaired.nodes if node.type == "outputNode"]
        if not node_type or not outputs:
            continue
        output = outputs[0]
        incoming = [edge for edge in repaired.edges if edge.target == output.id]
        if not incoming:
            continue
        action_id = next_id("n", node_ids)
        action = FlowNode(id=action_id, type=node_type, data=integration_defaults.get(node_type, {}))
        for edge in incoming:
            edge.target = action_id
        final_edge_id = next_id("e", edge_ids)
        repaired.nodes.append(action)
        repaired.edges.append(FlowEdge(id=final_edge_id, source=action_id, target=output.id))
        node_ids.add(action_id)
        edge_ids.add(final_edge_id)
        existing_types.add(node_type)
        notes.append(f"TaskSpec 연동 노드 {action_id}({node_type}) 삽입")

    semantic_insertions = {
        "INTENT_HTTP_REQUEST_MISSING": (
            "httpRequestNode", {"method": "POST", "url": "REPLACE_WITH_ACTUAL_URL"}, {"outputNode"},
        ),
        "INTENT_JSON_PARSER_MISSING": ("jsonParserNode", {"mode": "parse"}, {"outputNode"}),
        "INTENT_TEMPLATE_ANALYZER_MISSING": (
            "templateAnalyzerNode", {"template_path": "REPLACE_WITH_TEMPLATE_FILE"}, {"llmNode"},
        ),
        "INTENT_FILE_MODIFIER_MISSING": (
            "fileModifierNode", {"template_path": "REPLACE_WITH_TEMPLATE_FILE"}, {"outputNode"},
        ),
        "INTENT_MERGE_MISSING": (
            "mergeNode", {"mergeStrategy": "join_newline"}, {"outputNode"},
        ),
    }
    existing_types = {node.type for node in repaired.nodes}
    for issue in issues:
        insertion = semantic_insertions.get(issue.code)
        if not insertion:
            continue
        node_type, data, target_types = insertion
        if node_type in existing_types:
            continue
        inserted_id = (
            insert_after_approval(node_type, data)
            if issue.code == "INTENT_HTTP_REQUEST_MISSING"
            else None
        )
        inserted_id = inserted_id or insert_before(node_type, data, target_types)
        if inserted_id:
            existing_types.add(node_type)
            notes.append(f"TaskSpec 의미 노드 {inserted_id}({node_type}) 삽입")

    issue_codes = {issue.code for issue in issues}
    document_pipeline_missing = (
        "INTENT_TEMPLATE_ANALYZER_MISSING" in issue_codes
        and "INTENT_ACTION_MISSING" in issue_codes
        and "templateAnalyzerNode" not in existing_types
        and "llmNode" not in existing_types
    )
    if document_pipeline_missing:
        targets = [node for node in repaired.nodes if node.type == "fileModifierNode"]
        if targets:
            target = targets[0]
            incoming = [
                edge for edge in repaired.edges
                if edge.target == target.id and edge.targetHandle not in ("tools", "template")
            ]
            if incoming:
                analyzer_id = next_id("n", node_ids)
                node_ids.add(analyzer_id)
                prompt_id = next_id("n", node_ids)
                node_ids.add(prompt_id)
                llm_id = next_id("n", node_ids)
                node_ids.add(llm_id)
                for edge in incoming:
                    edge.target = analyzer_id
                repaired.nodes.extend([
                    FlowNode(
                        id=analyzer_id,
                        type="templateAnalyzerNode",
                        data={"template_path": "REPLACE_WITH_TEMPLATE_FILE"},
                    ),
                    FlowNode(
                        id=prompt_id,
                        type="promptNode",
                        data={"userPrompt": "서식 필드에 맞춰 지원자 정보를 JSON 값으로 작성해줘"},
                    ),
                    FlowNode(
                        id=llm_id,
                        type="llmNode",
                        data={
                            "model": "gpt-4o-mini",
                            "systemPrompt": "문서 서식의 필드를 채우는 JSON만 생성한다.",
                            "useStructuredOutput": True,
                            "jsonSchema": json.dumps({
                                "title": "FilledTemplateFields",
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            }),
                        },
                    ),
                ])
                for source, destination in (
                    (analyzer_id, prompt_id),
                    (prompt_id, llm_id),
                    (llm_id, target.id),
                ):
                    repaired.edges.append(FlowEdge(
                        id=next_id("e", edge_ids), source=source, target=destination,
                    ))
                    edge_ids.add(repaired.edges[-1].id)
                notes.append(
                    f"TaskSpec 문서 파이프라인 {analyzer_id}->{prompt_id}->{llm_id}->{target.id} 삽입"
                )

    return repaired, notes


async def repair_flow_after_agent(
    g: FlowGraph,
    user_request: str,
    complexity_level: str = "low",
    task_spec: Optional[TaskSpec] = None,
) -> Tuple[FlowGraph, List[str], List[ValidationIssue]]:
    def combined_issues(graph: FlowGraph) -> Tuple[bool, List[ValidationIssue]]:
        structural_ok, current_issues = validate_flow_detailed(graph)
        if structural_ok and task_spec is not None:
            current_issues.extend(task_coverage_issues(task_spec, graph.model_dump()))
        return not current_issues, current_issues

    candidate, notes = repair_disconnected_flow(g)
    ok, issues = combined_issues(candidate)
    if ok:
        return candidate, notes, []

    if task_spec is not None:
        semantic_candidate, semantic_notes = repair_task_coverage_deterministically(candidate, task_spec, issues)
        semantic_candidate, cleanup_notes = repair_disconnected_flow(semantic_candidate)
        semantic_ok, semantic_issues = combined_issues(semantic_candidate)
        if semantic_notes and (semantic_ok or len(semantic_issues) < len(issues)):
            candidate, issues, ok = semantic_candidate, semantic_issues, semantic_ok
            notes.extend(semantic_notes)
            notes.extend(cleanup_notes)
            if ok:
                return candidate, notes, []

    max_attempts = max(0, min(int(os.getenv("LLM_FINAL_REPAIR_MAX_ATTEMPTS", "2")), 2))
    timeout_seconds = float(os.getenv("LLM_FINAL_REPAIR_TIMEOUT_SECONDS", "30"))
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    seen_signatures = set()

    for _ in range(max_attempts):
        signature = issue_signature(issues)
        if signature in seen_signatures:
            notes.append("최종 repair에서 동일 validator 오류가 반복되어 중단")
            break
        seen_signatures.add(signature)
        if not any(issue.repairable for issue in issues):
            break
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            notes.append(f"최종 repair 시간 제한({timeout_seconds:g}초) 도달")
            break
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    repair_flow_partially, candidate, user_request, issues,
                    complexity_level=complexity_level,
                ),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            notes.append(f"최종 repair 시간 제한({timeout_seconds:g}초) 도달")
            break
        except Exception as exc:
            notes.append(f"최종 부분 수정 실패: {exc}")
            break

        repaired, _plan, applied_notes = result
        repaired, cleanup_notes = repair_disconnected_flow(repaired)
        applied_notes.extend(cleanup_notes)
        repaired_ok, repaired_issues = combined_issues(repaired)
        if not repaired_ok and task_spec is not None:
            semantic_repaired, semantic_notes = repair_task_coverage_deterministically(
                repaired, task_spec, repaired_issues,
            )
            semantic_repaired, semantic_cleanup = repair_disconnected_flow(semantic_repaired)
            semantic_ok, semantic_issues = combined_issues(semantic_repaired)
            if semantic_notes and (semantic_ok or len(semantic_issues) < len(repaired_issues)):
                repaired, repaired_ok, repaired_issues = semantic_repaired, semantic_ok, semantic_issues
                applied_notes.extend(semantic_notes)
                applied_notes.extend(semantic_cleanup)
        notes.extend(applied_notes)
        if repaired_ok:
            return repaired, notes, []
        if issue_signature(repaired_issues) == signature:
            notes.append("최종 부분 수정 후 동일 validator 오류가 반복되어 중단")
            break
        if len(repaired_issues) <= len(issues):
            candidate, issues = repaired, repaired_issues
        else:
            notes.append("최종 부분 수정이 오류를 늘려 후보를 폐기")
            break

    return candidate, notes, issues


def _validate_node_data(n: FlowNode) -> List[str]:
    """노드 type별 data 필수 필드 존재 여부 + 허용값 검사. 계약 §3 표 기준."""
    errors: List[str] = []
    d = n.data or {}

    # NodeDefinition으로 이전한 노드는 정의 파일에 선언된 규칙으로 검증한다(ADR-0005).
    # 메시지 문구는 이전 하드코딩 구현과 한 글자도 다르지 않게 옮겼다 — flow_validation.py의
    # 정규식 분류와 repair 로직이 문구에 의존하기 때문이다. 규칙 DSL로 표현할 수 없는
    # 잔여 검사(databaseNode의 SQL 가드 등)는 아래 분기에서 이어서 수행한다(하이브리드).
    if node_definition.get_definition(n.type) is not None:
        errors.extend(node_definition.validate_node_data(n.type, n.id, d))

    if n.type == "promptNode":
        if not d.get("userPrompt"):
            errors.append(f"{n.id}(promptNode)에 userPrompt가 없다")

    elif n.type == "tokenizerNode":
        method = d.get("method")
        if method not in ALLOWED_METHODS:
            errors.append(f"{n.id}(tokenizerNode)의 method는 extract_text 또는 chunk_pages여야 한다 (현재: {method!r})")

    elif n.type == "pythonNode":
        if "code" not in d:
            errors.append(f"{n.id}(pythonNode)에 code가 없다")
            
    elif n.type == "telegramNode":
        # 텔레그램 chat_id는 디스코드 channelId와 달리 형식이 여러 개다 — 개인 채팅은 양수,
        # 그룹/슈퍼그룹은 보통 음수(예: "-1001234567890"), 공개 채널은 "@channel_username"도
        # 유효하다. 그래서 숫자 하나만 허용하면 정상 케이스까지 막힌다 — 세 형식 중 하나인지만
        # 검사해서, 디스코드 channelId 검증과 같은 이유(지어낸 값 방지)로 형식이 완전히
        # 이상한 경우만 걸러낸다.
        chat_id = d.get("chatId", "")
        if chat_id and not re.match(r"^-?\d+$|^@\w+$", chat_id):
            errors.append(
                f"{n.id}(telegramNode)의 chatId({chat_id!r})가 유효한 텔레그램 chat_id 형식(숫자, 음수 "
                "가능, 또는 \"@채널명\")이 아니다 — 사용자가 채팅방을 알려주지 않았다면 지어내지 말고 "
                "빈 문자열로 둬라"
            )

    elif n.type == "kakaoNode":
        # API 센터에는 카카오 관련 provider가 두 개 있다 — "kakao"(REST API 키=client_id, 토큰
        # 자동 갱신에만 쓰임)와 "kakao_token"(실제 발송용 access_token). 실제로 LLM이 지침을
        # 놓치고 accessToken을 "{{API_CENTER:kakao}}"(잘못된 쪽)로 채운 사례가 있었다 — REST
        # 키는 Bearer 토큰으로 못 써서 카카오 서버가 401로 거부한다. 여기서 미리 걸러낸다
        # (실행 엔진에도 동일한 값을 자동 교정하는 안전장치가 있지만,애초에 맞게 생성되는 게 낫다).
        access_token = d.get("accessToken", "")
        if access_token.strip() == "{{API_CENTER:kakao}}":
            errors.append(
                f"{n.id}(kakaoNode)의 accessToken이 '{{{{API_CENTER:kakao}}}}'로 되어 있는데, 이건 "
                "REST API 키(client_id)라 실제 메시지 발송에는 쓸 수 없다 — 반드시 "
                "'{{API_CENTER:kakao_token}}'으로 바꿔라"
            )

    elif n.type == "mergeNode":
        strategy = d.get("mergeStrategy")
        if strategy and strategy not in ["join_newline", "join_comma", "array"]:
            errors.append(f"{n.id}(mergeNode)의 mergeStrategy '{strategy}'는 허용되지 않는다")

    elif n.type == "googleSheetsNode":
        mode = d.get("mode", "read")
        if mode not in ("read", "append", "write"):
            errors.append(f"{n.id}(googleSheetsNode)의 mode는 read/append/write 중 하나여야 한다 (현재: {mode!r})")

    elif n.type == "googleCalendarNode":
        mode = d.get("mode", "create")
        if mode not in ("create", "list"):
            errors.append(f"{n.id}(googleCalendarNode)의 mode는 create/list 중 하나여야 한다 (현재: {mode!r})")

    elif n.type == "notionNode":
        mode = d.get("mode", "create")
        if mode not in ("create", "query"):
            errors.append(f"{n.id}(notionNode)의 mode는 create/query 중 하나여야 한다 (현재: {mode!r})")

    elif n.type == "loopNode":
        max_iter = d.get("maxIterations", 5)
        try:
            int(max_iter)
        except (TypeError, ValueError):
            errors.append(f"{n.id}(loopNode)의 maxIterations는 숫자여야 한다 (현재: {max_iter!r})")

    elif n.type == "multiAgentNode":
        mode = d.get("mode")
        if mode not in ("supervisor", "group_chat"):
            errors.append(f"{n.id}(multiAgentNode)의 mode는 'supervisor' 또는 'group_chat'이어야 한다 (현재: {mode!r})")

    elif n.type == "databaseNode":
        # query 존재 검사는 정의 파일이 담당한다. SQL 가드(세미콜론 분해 + SELECT/WITH 강제)는
        # 규칙 DSL로 표현할 수 없어 잔여 하드코딩으로 남긴다(하이브리드 검증).
        query = d.get("query", "")
        if query:
            # 가드레일: 실행기와 같은 판별기(sql_guard, ADR-0017)를 쓴다 — AST 허용 목록으로 단일
            # SELECT/WITH 만 통과시키고 DML/DDL/락/파일 함수/허용되지 않은 schema 를 막는다. 생성 시점과
            # 실행 시점의 판정이 같아야 "에디터에선 통과인데 실행에서 막히는" 일이 없다.
            try:
                from db_query_runtime import parse_allowed_schemas
                from sql_guard import QueryRejected, analyze_read_query
                analysis = analyze_read_query(query, allowed_schemas=parse_allowed_schemas(d.get("allowedSchemas")))
            except QueryRejected as exc:
                errors.append(
                    f"{n.id}(databaseNode)의 query: {exc.message} "
                    "보안 및 무결성을 위해 이 노드에서는 오직 SELECT 쿼리만 실행할 수 있습니다."
                )
            else:
                declared = {str((p or {}).get("name") or "").strip() for p in (d.get("parameters") or []) if isinstance(p, dict)}
                for placeholder in analysis.placeholders:
                    if placeholder not in declared:
                        errors.append(
                            f"{n.id}(databaseNode)의 query가 파라미터 :{placeholder} 를 쓰는데 data.parameters 에 정의가 없다 "
                            "— {\"name\": \"" + placeholder + "\", \"source\": \"value\"|\"input\", \"value\"|\"path\": ..., \"type\": ...} 를 추가하라"
                        )

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
    return {
        "title": getattr(g, "title", ""),
        "description": getattr(g, "description", ""),
        "nodes": nodes,
        "edges": edges
    }


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
def generate_safely(user_request: str, complexity_level: str = "low") -> dict:
    """생성 → Validator 통과분만 반환. 실패하면 사유를 붙여 1회 재시도."""
    g = generate_flow(user_request, complexity_level=complexity_level)
    ok, errs = validate_flow(g)
    if not ok:
        retry = f'{user_request}\n\n(직전 생성이 아래 이유로 잘못됐다. 고쳐서 다시: {"; ".join(errs)})'
        g = generate_flow(retry, complexity_level=complexity_level)
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
#     node_type 을 함께 주면 **종류를 그 자리에서 바꾼다**(2026-08-30 추가). 이때는 병합하지 않고
#     data 를 통째로 교체한다 — 이전 종류의 설정은 새 종류에서 의미가 없다.
#     예전에는 delete_node + add_node 로만 가능했는데, 그러면 연결이 전부 끊기고 id 도 바뀐다.
#     시맨틱 포인팅(백로그 28)에서는 그 둘이 편집 범위 밖이라 종류 변경 자체가 불가능했다.
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
        out = data.get("output") or "text"
        return (f"url={url!r}, output={out!r}"
                + (" (url 비어있음 — 직전 노드 출력을 URL로 사용)" if not url else ""))
    if node_type == "valueNode":
        file_path = data.get("file_path", "")
        return f"file_path={file_path!r}" if file_path else f"value={data.get('value', '')!r}"
    if node_type == "templateAnalyzerNode":
        return f"template_path={data.get('template_path', '')!r}"
    if node_type == "fileModifierNode":
        return f"template_path={data.get('template_path', '')!r}, output_path={data.get('output_path', '')!r}"
    if node_type == "posterGeneratorNode":
        return f"outputFormat={data.get('outputFormat', 'png')!r}, width={data.get('width', 900)!r}, height={data.get('height', 1200)!r}, backgroundPreset={data.get('backgroundPreset', 'none')!r}"
    if node_type == "imageGenerationNode":
        return f"action={data.get('action', 'auto')!r}, model={data.get('model', 'gpt-5.6')!r}, size={data.get('size', 'auto')!r}, quality={data.get('quality', 'auto')!r}"
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


def _web_search_duckduckgo(query: str, max_results: int = 5) -> str:
    """API 키 없이 DuckDuckGo HTML 결과 페이지를 스크래핑해서 검색한다.
    워크플로우 생성 챗봇이 최신 정보(사용법, 시세, 뉴스 등)를 참고할 때 쓰는 보조 도구."""
    import requests
    from bs4 import BeautifulSoup
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for result in soup.select(".result__body")[:max_results]:
            title_tag = result.select_one(".result__title")
            snippet_tag = result.select_one(".result__snippet")
            link_tag = result.select_one(".result__url")
            title = title_tag.get_text(strip=True) if title_tag else ""
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            url = link_tag.get_text(strip=True) if link_tag else ""
            if title:
                results.append(f"- {title}\n  {url}\n  {snippet}")
        return "\n\n".join(results) if results else "검색 결과가 없습니다."
    except Exception as e:
        return f"웹 검색 실패: {e}"


def _verify_url(url: str) -> str:
    """webCrawlerNode/httpRequestNode에 채워 넣을 URL이 실제로 존재/접속 가능한지 확인한다.
    web_search는 검색 결과만 줄 뿐 그 링크가 지금도 살아있는지는 보장하지 않으므로(오래된 문서,
    깨진 링크 등), 채팅 챗봇이 URL을 자동으로 채워 넣기 전에 실제 HTTP 요청으로 한 번 더
    검증하는 용도. 사용자가 직접 타이핑할 필요 없이 챗봇이 사이트 주소를 검증→자동 입력하게
    해달라는 요청으로 추가됨."""
    import requests
    try:
        resp = requests.get(
            url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True
        )
        status = resp.status_code
        title = ""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text[:20000], "html.parser")
            if soup.title and soup.title.get_text(strip=True):
                title = soup.title.get_text(strip=True)
        except Exception:
            pass
        if 200 <= status < 400:
            return (
                f"접속 성공 (상태 코드 {status}). 최종 URL: {resp.url}. "
                f"페이지 제목: {title or '(확인 안 됨)'}"
            )
        return f"접속 실패 (상태 코드 {status}) — 이 URL은 유효하지 않을 수 있으니 다른 후보를 확인해라."
    except Exception as e:
        return f"접속 실패: {e} — 이 URL은 유효하지 않을 수 있으니 다른 후보를 확인해라."


def make_tools(initial_graph: FlowGraph, complexity_level: str = "low", db=None):
    """요청 하나(=대화 한 턴)마다 호출. (도구 리스트, 현재 그래프를 꺼내는 함수, 확인 질문을 꺼내는 함수) 튜플을 반환한다.

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

    initial_ok, _ = validate_flow(initial_graph)
    state: Dict[str, Any] = {
        "graph": initial_graph,
        "last_valid_graph": initial_graph.model_copy(deep=True) if initial_ok else None,
        "fail_streak": 0,
        "last_errors": [],
        "clarification": None,
    }

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
        _, before_errs = validate_flow(before, require_complete=False)
        _, errs = validate_flow(state["graph"], require_complete=False)
        
        # 편집 중인 그래프는 이미 유효하지 않은 상태일 수 있으므로(필수 값 누락 등)
        # 이전 상태에 없던 '새로 추가된 에러'만 롤백의 기준으로 삼는다.
        new_errs = [e for e in errs if e not in before_errs]
        
        if new_errs:
            state["graph"] = before  # 자동 롤백
            state["last_errors"] = new_errs
            return _fail(f"실패(변경 취소됨 - 새 오류 발생): {'; '.join(new_errs)}")
        complete_ok, _ = validate_flow(state["graph"])
        if complete_ok:
            state["last_valid_graph"] = state["graph"].model_copy(deep=True)
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
        emailNode→toEmail(문자열)+subject(문자열, 선택), databaseNode→connectionString(항상
        "{{API_CENTER:database}}" — 접속 정보 원문 금지)+query(문자열, SQL — DROP/TRUNCATE/ALTER 등은 검증기가 막고,
        DELETE/UPDATE는 WHERE 없이 쓰면 막힌다. 그 안에서만 자유롭게 사용).
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
    def update_node(node_id: str, data: Dict[str, Any],
                    node_type: Optional[NodeType] = None) -> str:
        """기존 노드를 수정한다. data는 넘긴 필드만 기존 값 위에 병합된다.

        node_type을 함께 주면 **노드 종류를 그 자리에서 바꾼다.** 이때 data는 병합하지 않고
        통째로 교체한다 — 이전 종류의 설정은 새 종류에서 의미가 없기 때문이다. 그러므로
        새 종류의 필수 필드를 data에 모두 담아 보내야 한다(add_node와 같은 요구사항).

        ⚠️ 종류를 바꿀 때 delete_node + add_node를 쓰지 마라. 그러면 **연결이 전부 끊기고**
        id도 새로 생긴다. 이 도구는 id와 연결을 그대로 두고 종류만 바꾼다.
        """
        g = state["graph"]
        node = next((n for n in g.nodes if n.id == node_id), None)
        if node is None:
            return _fail(f"실패: 노드 {node_id}를 찾을 수 없다")
        before = _snapshot()
        if node_type and node_type != node.type:
            old_type = node.type
            node.type = node_type
            node.data = dict(data)          # 이전 종류의 설정을 끌고 가지 않는다
            msg = f"노드 {node_id} 종류 변경됨: {old_type} → {node_type}"
            return _commit_or_rollback(before, msg)
        node.data = {**node.data, **data}
        msg = f"노드 {node_id} 갱신됨: {list(data.keys())}"
        if "testValue" in data:
            note = _dynamic_input_note(node)
            if note:
                msg += f"\n{note}"
        return _commit_or_rollback(before, msg)

    @tool
    def bind_field(node_id: str, field: str, source_node_id: str, path: str = "") -> str:
        """노드의 입력 필드를 **앞 노드의 출력값에 직접 연결**한다(데이터 바인딩).

        "웹훅으로 온 이메일을 수신자로 써줘", "검색 결과 첫 링크를 크롤링해줘" 처럼 값을
        옮기기만 하는 요청에 쓴다 — 그런 일에 llmNode 나 jsonParserNode 를 새로 넣지 마라.

        path 는 JSON 경로(a.b[0].c)이고, 비우면 그 노드의 출력 전체다. 출력 형식이
        카탈로그에 적혀 있지 않은 노드(webhookNode 요청 본문 등)는 사용자가 키 이름을
        직접 말한 경우에만 경로를 쓰고, 아니면 비워 둔다.

        source_node_id 를 빈 문자열로 주면 그 필드의 연결을 **해제**한다.
        지원하지 않는 필드나 실행 경로상 앞이 아닌 소스는 실패 사유가 돌아온다."""
        g = state["graph"]
        node = next((n for n in g.nodes if n.id == node_id), None)
        if node is None:
            return _fail(f"실패: 노드 {node_id}를 찾을 수 없다")
        allowed = node_bindings.bindable_fields(str(node.type))
        if field not in allowed:
            return _fail(
                f"실패: {node.type}의 '{field}' 필드는 데이터 바인딩을 지원하지 않는다"
                f" (지원: {', '.join(allowed) if allowed else '없음'})")
        before = _snapshot()
        bindings = dict(node.data.get("bindings") or {})
        if not source_node_id:
            if field not in bindings:
                return _fail(f"실패: {node_id}의 '{field}' 에는 연결된 값이 없다")
            bindings.pop(field)
            msg = f"노드 {node_id}의 '{field}' 값 연결 해제됨"
        else:
            bindings[field] = {"source": source_node_id, "path": path}
            where = f" -> {path}" if path else " (출력 전체)"
            msg = f"노드 {node_id}의 '{field}' <- {source_node_id}{where}"
        new_data = {**node.data, "bindings": bindings}
        if not bindings:
            new_data.pop("bindings")
        node.data = new_data
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

    QUALITY_GATE_THRESHOLD = 70
    # 재시도 1회당 평가 사이클(테스트케이스 생성+실행+채점) 전체가 다시 도는 데다, 매 시도마다
    # generate_flow_precise까지 새로 호출돼서 비용이 크다 — 원래 3이었는데, 체감 생성 시간이
    # 너무 길다는 피드백으로 2로 낮췄다(사용자 확인 완료).
    QUALITY_GATE_MAX_ATTEMPTS = 2
    # 품질 게이트는 "대충 괜찮은지" 빠르게 감만 보면 되는 용도라, 정식 /api/evaluate(3개)보다
    # 적은 1개 테스트케이스만 돌려서 속도를 우선한다(사용자 확인 완료).
    QUALITY_GATE_NUM_TEST_CASES = 1

    @tool("generate_flow")
    async def _generate_flow_tool(request: str) -> str:
        """완전히 새로운 flow를 통째로 생성해서 기존 flow를 전부 대체한다.
        "~봇 만들어줘"처럼 처음부터 새로 만드는 요청에만 쓴다.
        기존 flow에 노드를 붙이거나 일부만 고치는 요청에는 add_node/connect_nodes/update_node를 쓴다."""

        generation_timeout = float(os.getenv("LLM_GENERATION_TIMEOUT_SECONDS", "75"))
        generation_deadline = asyncio.get_running_loop().time() + generation_timeout
        generation_timed_out = False

        async def _call_generation(fn, *args, **kwargs):
            nonlocal generation_timed_out
            remaining = generation_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                generation_timed_out = True
                return None
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(fn, *args, **kwargs), timeout=remaining,
                )
            except asyncio.TimeoutError:
                generation_timed_out = True
                return None

        g = None
        template = None
        mode_label = "빠름 생성"

        # generate_flow*/search_and_parse_template은 내부적으로 LLM·임베딩 API를 동기(blocking)로
        # 호출한다. uvicorn이 --workers 1(단일 워커)로 떠 있어서, 이 도구 함수가 async라고 해도 그
        # 안에서 동기 호출을 await 없이 그냥 부르면 그 호출이 끝날 때까지 이벤트 루프 전체가 멈춰서
        # 다른 모든 사용자의 요청까지 같이 멈춘다("서버가 멈춘 것 같다"는 증상의 실제 원인 — AI로
        # 워크플로우를 생성/재생성할 때마다(특히 재시도 루프가 도는 정밀 모드) 이 경로를 타므로 흔하게
        # 재발할 수 있었다). asyncio.to_thread로 스레드에 넘겨서 이벤트 루프를 막지 않게 한다.
        if complexity_level == "high":
            # ── 정밀 모드: 템플릿 검색 없이, 요청을 더 꼼꼼히 해석해서 살을 붙여 생성 ──
            g = await _call_generation(generate_flow_precise, request, complexity_level=complexity_level)
            mode_label = "정밀 생성"

        elif complexity_level == "medium":
            # ── 확장 모드: Pre-translated DB에서 템플릿 검색 → 구조 유지 + 파라미터 수정 ──
            try:
                from rag_utils import search_and_parse_template
                template_data = await asyncio.to_thread(search_and_parse_template, request)
                if template_data:
                    template = FlowGraph(
                        title=template_data.get("title") or "참고 템플릿",
                        description=template_data.get("description") or "",
                        nodes=template_data.get("nodes", []),
                        edges=template_data.get("edges", []),
                    )
                    mode_label = "사전 번역 템플릿 기반"
            except Exception as e:
                print(f"Medium mode template search failed: {e}")

        # 확장 모드에서 템플릿을 못 찾았을 때
        if not g:
            if template:
                g = await _call_generation(generate_flow_from_template, request, template, complexity_level=complexity_level)
            else:
                if complexity_level == "medium":
                    # 템플릿 검색이 빗나가도 low few-shot으로 급락시키지 않고,
                    # 구조를 적극 활용하는 확장 생성 경로를 유지한다.
                    g = await _call_generation(generate_flow_precise, request, complexity_level=complexity_level)
                    mode_label = "확장 생성"
                else:
                    _plan = generation_plan.current_plan()
                    if (
                        _plan is not None and _plan.adaptive and _plan.candidate_count >= 2
                        and generation_plan.adaptive_candidates_enabled()
                    ):
                        # adaptive fan-out(§4.4): 같은 요청을 빠름/정밀 두 관점으로 생성해
                        # LLM judge 없이 결정론 기준(구조→커버리지→dry-run→복잡도)으로 고른다.
                        candidates = await asyncio.gather(
                            _call_generation(generate_flow, request, complexity_level=complexity_level),
                            _call_generation(generate_flow_precise, request, complexity_level=complexity_level),
                        )
                        labels = ["fast", "precise"]
                        alive = [(index, candidate) for index, candidate in enumerate(candidates) if candidate is not None]
                        if alive:
                            # 랭킹은 결정론 리페어를 거친 상태에서 한다 — 리페어 전 상태로 고르면
                            # 최종 그래프와 어긋난다(1차 게이트 비교의 악화 사례 ②). LLM 리페어는
                            # 비용이 있어 선택된 후보만 기존 경로에서 받는다.
                            repaired = [repair_disconnected_flow(candidate)[0] for _, candidate in alive]
                            best, scores = generation_plan.rank_candidates(
                                repaired,
                                getattr(_plan, "_task_spec", None),
                                labels=[labels[index] for index, _ in alive],
                                user_request=request,
                            )
                            generation_plan.record_candidates(_plan, scores, best)
                            g = repaired[best]
                            mode_label = f"적응형 생성 ({scores[best]['label']} 후보 선택)"
                    else:
                        g = await _call_generation(generate_flow, request, complexity_level=complexity_level)

        if generation_timed_out or g is None:
            return _fail(f"생성 시간 제한({generation_timeout:g}초)을 초과했습니다. 기존 flow를 유지합니다.")

        # 검증 실패 시 전체 재생성보다 오류가 난 노드/엣지만 먼저 고친다. 같은 오류 signature가
        # 반복되면 즉시 중단하고, 부분 수정으로 다룰 수 없는 오류만 전체 재생성으로 폴백한다.
        MAX_ATTEMPTS = max(1, min(int(os.getenv("LLM_GENERATION_MAX_ATTEMPTS", "3")), 3))
        ok, issues = validate_flow_detailed(g)
        attempt = 1
        partial_repair_count = 0
        repair_notes: List[str] = []
        seen_signatures = set()

        if not ok:
            deterministic_graph, deterministic_notes = repair_disconnected_flow(g)
            deterministic_ok, deterministic_issues = validate_flow_detailed(deterministic_graph)
            if deterministic_ok or len(deterministic_issues) < len(issues):
                g, issues = deterministic_graph, deterministic_issues
                ok = deterministic_ok
                repair_notes.extend(deterministic_notes)

        while not ok and attempt < MAX_ATTEMPTS:
            signature = issue_signature(issues)
            if signature in seen_signatures:
                repair_notes.append("동일 validator 오류 반복으로 수정 중단")
                break
            seen_signatures.add(signature)
            attempt += 1

            candidate_graph = None
            if any(issue.repairable for issue in issues):
                try:
                    repair_result = await _call_generation(
                        repair_flow_partially, g, request, issues, complexity_level=complexity_level,
                    )
                    if repair_result is not None:
                        candidate_graph, _repair_plan, applied_notes = repair_result
                        partial_repair_count += 1
                        repair_notes.extend(applied_notes)
                except Exception as exc:
                    repair_notes.append(f"부분 수정 계획 적용 실패: {exc}")
                    break
            else:
                issue_text = "; ".join(f"[{issue.code}] {issue.message}" for issue in issues)
                retry = f"{request}\n\n직전 생성 오류를 고쳐 전체 그래프를 다시 생성해라: {issue_text}"
                if mode_label == "정밀 생성":
                    candidate_graph = await _call_generation(generate_flow_precise, retry, complexity_level=complexity_level)
                elif template:
                    candidate_graph = await _call_generation(generate_flow_from_template, retry, template, complexity_level=complexity_level)
                elif mode_label == "확장 생성":
                    candidate_graph = await _call_generation(generate_flow_precise, retry, complexity_level=complexity_level)
                else:
                    candidate_graph = await _call_generation(generate_flow, retry, complexity_level=complexity_level)

            if candidate_graph is None:
                break
            candidate_ok, candidate_issues = validate_flow_detailed(candidate_graph)
            candidate_signature = issue_signature(candidate_issues)
            if candidate_ok:
                g, issues, ok = candidate_graph, [], True
                break
            if candidate_signature == signature:
                repair_notes.append("부분 수정 후 동일 validator 오류가 반복되어 중단")
                break
            if len(candidate_issues) <= len(issues):
                g, issues = candidate_graph, candidate_issues
            else:
                repair_notes.append("부분 수정이 오류를 늘려 후보를 폐기")
                break

        if not ok:
            timeout_note = f", {generation_timeout:g}초 시간 제한 도달" if generation_timed_out else ""
            issue_text = "; ".join(f"[{issue.code}] {issue.message}" for issue in issues)
            return _fail(f"생성 실패(기존 flow 유지, {attempt}회 시도{timeout_note}): {issue_text}")

        # ── 정밀 모드 전용 품질 게이트: 구조 검증을 통과해도 실제 품질이 낮을 수 있으므로,
        # 평가 기능(evaluator)으로 채점해서 기준 점수 미달이면 개선 제안을 반영해 재생성한다.
        # (db 세션이 있어야 실제 워크플로우를 실행해볼 수 있어서, db 없으면 조용히 건너뛴다.)
        quality_score = None
        quality_attempts = 0
        if complexity_level in ("medium", "high") and db is not None:
            from evaluator import run_evaluation_pipeline
            while quality_attempts < QUALITY_GATE_MAX_ATTEMPTS:
                quality_attempts += 1
                try:
                    eval_report = await run_evaluation_pipeline(
                        project_id=None,
                        title=g.title or "워크플로우",
                        description=g.description or "",
                        nodes=[n.model_dump() for n in g.nodes],
                        edges=[e.model_dump() for e in g.edges],
                        db=db,
                        num_test_cases=QUALITY_GATE_NUM_TEST_CASES,
                    )
                except Exception as ex:
                    print(f"[정밀 생성 품질 게이트] 평가 실패, 건너뜀: {ex}")
                    break
                if not isinstance(eval_report, dict) or "error" in eval_report:
                    break
                quality_score = eval_report.get("score", 0)
                if quality_score >= QUALITY_GATE_THRESHOLD or quality_attempts >= QUALITY_GATE_MAX_ATTEMPTS:
                    break
                suggestions = eval_report.get("suggestions", [])
                retry_request = (
                    f'{request}\n\n(방금 생성한 워크플로우가 자동 평가에서 {quality_score}/100점을 받아 '
                    f'기준({QUALITY_GATE_THRESHOLD}점)에 못 미쳤다. 아래 개선 제안을 반영해서 다시 생성해줘:\n'
                    + "\n".join(f"- {s}" for s in suggestions)
                )
                if template:
                    candidate = await _call_generation(generate_flow_from_template, retry_request, template, complexity_level=complexity_level)
                else:
                    candidate = await _call_generation(generate_flow_precise, retry_request, complexity_level=complexity_level)
                if candidate is None:
                    break
                cand_ok, _ = validate_flow(candidate)
                if cand_ok:
                    g = candidate
                else:
                    # 재생성이 구조 검증에 실패하면 직전까지의 g(구조는 유효함)를 유지하고 품질 루프 종료
                    break

        state["graph"] = g
        state["last_valid_graph"] = g.model_copy(deep=True)
        msg = f"새 플로우 생성됨 ({mode_label}): 노드 {len(g.nodes)}개, 엣지 {len(g.edges)}개"
        if partial_repair_count or repair_notes:
            msg += f"\n부분 수정 {partial_repair_count}회: {'; '.join(repair_notes)}"
        if quality_score is not None:
            msg += f"\n자동 품질 평가: {quality_score}/100점 ({quality_attempts}회 시도)"
        notes = [n for n in (_dynamic_input_note(node) for node in g.nodes) if n]
        if notes:
            msg += "\n" + "\n".join(notes)
        return _succeed(msg)

    @tool
    def ask_clarification(question: str, options: List[str]) -> str:
        """새 워크플로우를 생성하기 전에 결과물에 꼭 필요한 정보(목적지 URL, 알림 받을 대상,
        처리할 파일 종류, 실행 주기·시간 등)가 요청에 빠져 있을 때, 추측해서 바로 만들지 말고
        사용자에게 되물어야 할 때 쓴다. options는 사용자가 클릭 한 번으로 고를 수 있는 2~4개의
        구체적인 답변 후보 — "기타"/"모름" 같은 항목은 넣지 않는다(사용자는 언제든 직접 타이핑해서
        답할 수 있다). 이 도구를 호출하면 이번 턴에는 generate_flow를 호출하지 않고 질문만 보여준다.
        사용자가 이미 필요한 정보를 줬거나, "몰라도 돼"/"그냥 만들어줘"처럼 건너뛰겠다는 의사를
        밝혔으면 이 도구를 쓰지 말고 바로 generate_flow로 진행한다(그때는 지금처럼 빈 값/placeholder로
        채워서 만든다)."""
        state["clarification"] = {"question": question, "options": options}
        return f"[사용자에게 확인 질문을 표시함: {question}]"

    @tool
    def web_search(query: str) -> str:
        """인터넷에서 최신 정보를 검색한다. 워크플로우를 만들거나 노드 값을 채울 때 필요한
        실시간/최신 정보(특정 API 사용법, 최근 뉴스, 가격·시세, 최신 모델명 등)를 참고하고 싶을 때 사용한다.
        검색 결과(제목/URL/요약)를 텍스트로 반환할 뿐, 워크플로우 자체를 수정하지는 않는다."""
        return _web_search_duckduckgo(query)

    @tool
    def verify_url(url: str) -> str:
        """webCrawlerNode/httpRequestNode에 채워 넣으려는 URL이 실제로 접속되는지 확인한다.
        web_search로 찾은 후보 URL이 지금도 살아있는지, 오타는 없는지 마지막으로 확인할 때 쓴다.
        접속 성공 시 페이지 제목도 같이 알려주므로, 찾으려던 사이트가 맞는지 대조할 수 있다."""
        return _verify_url(url)

    def get_current_graph() -> FlowGraph:
        """컨테이너의 최신 그래프를 반환. Phase 3/4가 에이전트 실행 후 최종 결과를 읽을 때 쓴다."""
        return state["graph"]

    def get_last_valid_graph() -> Optional[FlowGraph]:
        graph = state.get("last_valid_graph")
        return graph.model_copy(deep=True) if graph is not None else None

    def get_clarification() -> Optional[Dict[str, Any]]:
        """ask_clarification이 이번 턴에 호출됐으면 {question, options}를, 아니면 None을 반환한다."""
        return state["clarification"]

    tools = [show_flow, add_node, connect_nodes, update_node, bind_field, delete_node, _generate_flow_tool, ask_clarification, web_search, verify_url]
    return tools, get_current_graph, get_clarification, get_last_valid_graph


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
    + NODE_CATALOG
    + workflow_patterns.PATTERN_CATALOG
    + node_bindings.BINDING_CATALOG +
    "\n[도구 사용 지침]\n"
    '- 완전히 새로 만드는 요청("~봇 만들어줘")에는 반드시 `generate_flow` 하나만 호출한다. 절대 여러 번의 `add_node`를 병렬로 호출해서 직접 조립하지 마라.\n'
    '- ⚠️ `generate_flow`는 캔버스의 노드를 통째로 지우고 완전히 새로 대체한다 — 캔버스에 이미 노드가 있는데 '
    '함부로 호출하면 사용자가 공들여 만든 기존 워크플로우가 전부 사라진다. 캔버스에 노드가 하나라도 있으면, '
    'show_flow로 먼저 현재 구조를 확인하고, 요청이 "이 워크플로우를 참고/수정/보완"하는 성격이면 '
    '(예: "여기에 ~ 추가해줘", "이 노드를 ~로 바꿔줘", "~도 되게 해줘" 등 기존 구조를 전제로 하는 표현) '
    'add_node/connect_nodes/update_node/delete_node로 그 구조를 유지한 채 편집한다. `generate_flow`는 캔버스가 '
    '비어있거나, 사용자가 "처음부터 다시/완전히 새로" 만들어달라고 명시적으로 요청했을 때만 쓴다. '
    '애매하면 지우지 말고 먼저 "기존 워크플로우를 그대로 두고 일부만 고칠까요, 아니면 처음부터 새로 만들까요?"라고 되묻는다.\n'
    '- 기존 flow에 붙이거나 일부만 고치는 요청에는 add_node/connect_nodes/update_node/delete_node를 쓴다.\n'
    '- "앞 노드의 ~을 이 필드에 써줘" 처럼 값을 옮기기만 하는 요청에는 bind_field를 쓴다. 값을 옮기려고 llmNode/jsonParserNode를 추가하지 마라 — 노드도 토큰도 쓰지 않는 쪽이 맞다.\n'
    '- 노드 id가 뭔지 확실하지 않으면 먼저 show_flow로 현재 상태를 확인하고 나서 편집한다.\n'
    '- 그래프 편집과 무관한 잡담(인사, 이 앱이 뭔지 설명 등)에는 도구를 부르지 말고 그냥 대화로 답한다.\n'
    '- 요청이 너무 모호해서 어떤 노드가 필요한지 판단할 수 없으면, 임의로 짐작해서 도구를 부르지 말고 '
    '먼저 무엇을 원하는지 구체적으로 되묻는다. 특히 대화가 길어져서 이전 요청들과 섞여 헷갈릴 수 있는 '
    '상황일수록(예: 여러 flow를 이미 만들어본 뒤) 짐작하지 말고 먼저 확인한다.\n'
    '- ⚠️ [필수 정보 확인 — ask_clarification] 캔버스가 비어있어 `generate_flow`로 완전히 새 워크플로우를 '
    '만들어야 하는 상황에서, 그 워크플로우가 실제로 쓸모 있으려면 반드시 있어야 하는 핵심 정보가 요청에 '
    '없으면(예: 알림을 어느 메신저/채널로 보낼지, 몇 시/무슨 주기로 실행할지, 어떤 형식의 파일을 만들지, '
    '크롤링할 대상이 여러 후보 중 무엇인지) 짐작해서 바로 `generate_flow`를 부르지 말고 먼저 '
    '`ask_clarification`으로 되묻는다. 한 턴에 하나의 질문만, 답변 후보 2~4개를 구체적인 문구로 만들어서 '
    '넘긴다(예: question="알림을 어디로 보낼까요?", options=["카카오톡", "디스코드", "이메일"]). '
    '단, 있으면 더 좋지만 없어도 그럴듯하게 채울 수 있는 부수적인 디테일(정확한 문구, 색상, 세부 조건 등)'
    '까지 전부 물어보지는 마라 — 결과물의 핵심 목적 자체를 좌우하는 정보만 대상이다. '
    '⚠️ 한 대화당 ask_clarification은 원칙적으로 딱 한 번만 쓴다 — 사용자가 답하면(칩을 고르든 직접 '
    '타이핑하든) 그 답변을 대화 맨 처음의 원래 요청과 반드시 결합해서 곧바로 `generate_flow`를 호출한다. '
    '예를 들어 원래 요청이 "매일 아침 뉴스 요약해서 알려줘"였고 질문에 사용자가 "디스코드"라고만 답했어도, '
    '"어떤 워크플로우를 원하냐"고 또 되묻지 말고 두 정보를 합쳐 즉시 '
    'generate_flow("매일 아침 뉴스 요약해서 디스코드로 알려줘")를 호출한다 — 짧은 답 하나만으로 부족해 '
    '보여도 이미 원래 요청에 있던 목적·조건은 그대로 유효하니 다시 물을 필요가 없다. 그리고 사용자가 이미 '
    '"몰라도 돼"/"그냥 만들어줘"/"아무거나"처럼 건너뛰겠다는 의사를 밝혔거나, 직전에 이미 질문을 한 번 '
    '했다면(같은 종류든 아니든) 다시 묻지 말고 지금까지 받은 정보 + 합리적인 기본값으로 바로 `generate_flow`를 호출한다 '
    '(URL처럼 자동으로 못 찾는 값은 기존 안내대로 REPLACE_WITH_ACTUAL_URL로 남기면 된다 — ask_clarification은 '
    '"카카오톡 vs 디스코드"처럼 후보가 몇 개로 정해지는 선택에 특히 적합하고, 정확한 URL·이메일 주소처럼 '
    '순수 자유입력값에는 억지로 쓰지 않아도 된다).\n'
    '- 도구 응답에 \'⚠️ 연속 N회 실패\' 경고가 붙으면, 같은 방식을 반복하지 말고 사용자에게 무엇이 '
    '막혔는지 설명하고 어떻게 할지 물어본다.\n'
    '- 도구 응답에 \'dynamicInputNode의 testValue를...\' 같은 안내 문장이 붙어 있으면, 그 내용을 반드시 '
    '최종 답변에 그대로(추측해서 다른 값을 지어내지 말고) 포함시켜 사용자에게 알려준다 — 예시값인지, '
    '비워뒀는지를 사용자가 알아야 실제 실행 때 뭐가 들어가는지 헷갈리지 않는다.\n'
    '- ⚠️ webCrawlerNode/httpRequestNode를 만들거나 채울 때, 사용자가 사이트를 이름으로만 말하고'
    '(예: "네이버 뉴스", "잡코리아 채용공고", "한국거래소 공시") 정확한 URL을 안 줬다면, url을 '
    'REPLACE_WITH_ACTUAL_URL로 비워두고 사용자에게 입력해달라고 안내하는 게 기본값이었지만, 이제는 '
    '누구나 아는 공개 서비스/기관 이름일 때만(고유명사로 특정 가능한 경우) 그전에 먼저 `web_search`로 '
    '그 사이트의 실제 주소 후보를 찾고, `verify_url`로 후보가 지금도 접속되는지, 그리고 검색으로 찾은 '
    '사이트 이름/페이지 제목이 사용자가 말한 대상과 정확히 일치하는지(비슷하게 들리는 다른 사이트가 '
    '아닌지) 확인해라. 확인되면 그 URL을 그대로 generate_flow에 넘기는 요청 문자열에 명시하거나'
    '(예: `generate_flow("네이버 뉴스 크롤링해줘. url은 https://news.naver.com 으로 설정")`) '
    'update_node의 data.url로 채워서, 사용자가 URL을 직접 타이핑할 필요가 없게 만든다. '
    '⚠️ "우리 회사", "우리 학교", "저희 사내 시스템/인트라넷", "내 블로그"처럼 사용자 개인이나 소속'
    '조직만 아는 비공개 대상은 애초에 web_search로 찾을 수 있는 게 아니다 — 이런 경우는 검색을 '
    '시도하지도 말고 곧바로 REPLACE_WITH_ACTUAL_URL로 남기고 "이건 비공개 사이트라 자동으로 찾을 수 '
    '없으니 직접 주소를 입력해달라"고 안내한다(검색 결과에 그럴듯해 보이는 사이트가 걸려도 그건 다른 '
    '사이트일 뿐이니 무시한다). web_search/verify_url을 썼는데도 실패하거나 애매하면(이름이 정확히 '
    '일치하지 않거나, 동명이인 사이트가 여럿이거나, 접속이 계속 실패하면) 절대 불확실한 URL을 지어내서 '
    '채우지 말고, 기존처럼 REPLACE_WITH_ACTUAL_URL로 '
    '남기고 어떤 후보를 찾았는지/왜 확신 못했는지 사용자에게 알려준다.\n'
    '\n[예시]\n'
    '- 사용자: "PDF 요약봇 만들어줘" → generate_flow("PDF 요약봇 만들어줘") 호출\n'
    '- 사용자: "매일 아침 뉴스 요약해서 알려줘" (캔버스 비어있음) → 어느 메신저로 받을지가 워크플로우의 '
    '핵심 노드(카카오/디스코드/텔레그램/이메일 중 무엇을 쓸지)를 결정하는 필수 정보인데 빠져 있음 → '
    'ask_clarification(question="어디로 알려드릴까요?", options=["카카오톡", "디스코드", "이메일"]) 호출 → '
    '사용자가 "디스코드"라고 답하면(또는 칩을 클릭하면) 그 답을 반영해서 '
    'generate_flow("매일 아침 뉴스 요약해서 디스코드로 알려줘") 호출\n'
    '- 사용자: "요약 뒤에 번역 추가해줘" → show_flow로 현재 노드 확인 → add_node로 promptNode·llmNode 추가 → connect_nodes로 연결\n'
    '- 사용자: "모델을 gpt-5.4-mini로 바꿔줘" → show_flow로 llmNode id 확인 → update_node(그 id, {"model": "gpt-5.4-mini"})\n'
    '- 사용자: "매번 다른 문장을 입력받아서 번역해주는 봇 만들어줘" → generate_flow 호출 → 도구 응답에 '
    '"n2(dynamicInputNode)의 testValue를 예시로 \'Hello, how are you?\'로 채웠다..." 같은 note가 붙으면, '
    '답변에서 "테스트용으로 \'Hello, how are you?\'라는 예시 문장을 넣어뒀어요. 실제로 실행할 때는 그때 '
    '입력하는 문장이 대신 들어갑니다." 처럼 그대로 안내한다\n'
    '- 사용자: "잡코리아에서 채용공고 크롤링해서 요약해줘" → web_search("잡코리아 공식 사이트 URL") → '
    '후보로 "https://www.jobkorea.co.kr" 발견 → verify_url("https://www.jobkorea.co.kr")로 접속 성공 + '
    '페이지 제목이 "잡코리아"인 것 확인 → generate_flow("잡코리아(https://www.jobkorea.co.kr)에서 채용공고를 '
    '크롤링해서 요약해줘") 호출 → 최종 답변에서 "잡코리아 실제 주소(https://www.jobkorea.co.kr)를 확인해서 '
    '자동으로 채워뒀어요"라고 안내한다\n'
    '- 사용자: "우리 회사 사내 인트라넷에서 공지사항 크롤링해줘" → "사내 인트라넷"은 특정 공개 서비스명이 '
    '아니라 이 사용자만 아는 비공개 시스템이므로 web_search를 시도하지 않는다 → url은 '
    'REPLACE_WITH_ACTUAL_URL로 둔 채 generate_flow 호출 → 최종 답변에서 "사내 인트라넷은 외부에서 검색해 '
    '찾을 수 없는 비공개 사이트라 주소를 비워뒀어요. 웹크롤러 노드를 클릭해서 실제 인트라넷 주소를 직접 '
    '입력해 주세요"라고 안내한다\n'
    '- 사용자: "안녕" → 도구 호출 없이 그냥 인사만 한다 (예: "안녕하세요! 어떤 워크플로우를 만들어드릴까요?")\n'
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


def build_agent(
    graph_data: FlowGraph,
    complexity_level: str = "low",
    checkpointer=None,
    thread_id: str = "",
    langfuse_handler=None,
    db=None,
    generation_trace_id: Optional[str] = None,
):
    """이번 요청 전용 에이전트 + get_current_graph 접근자를 만든다. (tools, agent 둘 다 요청마다 새로 만듦.)"""
    from langchain.agents import create_agent

    tools, get_current_graph, get_clarification, get_last_valid_graph = make_tools(
        graph_data, complexity_level=complexity_level, db=db,
    )
    
    prompt = AGENT_SYSTEM_PROMPT
    if complexity_level == "high":
        prompt += (
            '\n- 사용자: "채용 자동화 봇 만들어줘" (단순한 요청) → 사용자가 구체적으로 말하지 않아도 예외 처리, '
            '실패 알림, 분기 등을 포함한 [크고 복잡한 비선형적 워크플로우]를 상상한 뒤, 이 복잡한 내용을 '
            '구체적인 문자열로 만들어서 `generate_flow("입력: ... 조건분기: ... 알림: ...")` 도구 하나에 인자로 '
            '넘겨 한 번에 완성한다.\n'
            '- ⚠️ 단, 유추한 로직이 원래 목적을 벗어나는 경우에만 묻고, 그 외에는 사용자가 묻지 않은 디테일까지 '
            '전부 살을 붙여서 최대한 복잡하고 멋진 노드 그래프를 바로 생성한다.\n'
        )
    elif complexity_level == "low":
        prompt += (
            '\n- ⚠️ [빠름 모드 주의] 사용자가 짧게 요청하면, 상상해서 살을 붙이지 말고 최대한 단순하고 직관적으로 '
            '요청된 필수 기능만 포함하여 `generate_flow`에 넘겨라. 복잡한 예외 처리나 알림 노드를 임의로 추가하지 마라.\n'
            '- 사용자 메시지에 `[정규화된 TaskSpec]`과 `[결정론적 실행 정책]`이 있으면 그 정책을 최우선으로 '
            '따른다. `즉시 생성`이면 URL, API key, channel ID, database ID, 이메일, 파일 경로, 실행 시 입력값이 '
            '빠져 있어도 절대 되묻지 말고 placeholder 또는 dynamicInputNode를 사용해 generate_flow를 호출한다. '
            '`질문 필요`일 때만 TaskSpec의 질문으로 ask_clarification을 한 번 호출한다.\n'
        )

    agent = create_agent(
        get_llm(
            session_id=thread_id,
            complexity_level=complexity_level,
            langfuse_handler=langfuse_handler,
            generation_trace_id=generation_trace_id,
        ),
        tools=tools,
        system_prompt=prompt,
        checkpointer=checkpointer or _get_default_checkpointer(),
    )
    return agent, get_current_graph, get_clarification, get_last_valid_graph


async def run_agent_turn(
    graph_data: dict,
    message: str,
    thread_id: str,
    complexity_level: str = "low",
    checkpointer=None,
    db=None,
    trace_id: Optional[str] = None,
    training_consent: bool = False,
    pointing_instruction: Optional[str] = None,
) -> Tuple[str, dict, dict, Optional[Dict[str, Any]]]:
    """대화 한 턴을 실행한다. /api/chat은 이 함수를 그대로 감싸기만 하면 된다.

    흐름: graph_data(raw dict, 프론트가 보낸 것) → FlowGraph로 파싱 → 이번 요청 전용 에이전트 조립
    → agent.ainvoke → 끝나면 최종 완결성 게이트(validate_flow, require_complete=True 기본값) →
    통과하면 auto_layout한 graph_data, 실패하면 원본 graph_data 그대로 반환.

    db: 정밀(high) 모드의 생성 품질 게이트(생성 → 평가 → 기준 미달 시 재생성)가 실제로 워크플로우를
    실행해봐야 해서 필요하다 — 없으면(None) 품질 게이트는 조용히 건너뛰고 구조 검증까지만 한다.

    반환: (reply: str, graph_data: dict, token_usage: dict, clarification: dict|None) — 마지막 값은
    ask_clarification 도구가 이번 턴에 호출됐을 때만 {question, options}로 채워진다(그 외엔 None).
    API 응답 {reply, graph_data, token_usage, clarification}에 그대로 매핑된다.
    """
    trace_started = time.perf_counter()
    trace_id = trace_id or str(uuid.uuid4())
    # 이번 턴의 노드 선별 이벤트(LLM 선별 + hybrid shadow)를 모을 수집기. 생성 함수는
    # asyncio.to_thread로 돌아도 같은 컨텍스트 사본을 받아 같은 수집기 객체에 기록한다.
    node_knowledge.begin_selection_trace()
    g = FlowGraph(
        title=graph_data.get("title", ""),
        description=graph_data.get("description", ""),
        nodes=graph_data.get("nodes", []),
        edges=graph_data.get("edges", [])
    )
    initial_dump = g.model_dump()

    handler = None
    if has_langfuse:
        handler = CallbackHandler()

    # 사용자 문서 기반 RAG 컨텍스트 주입 — retrieve_chat_context는 임베딩 API 호출을 포함한
    # 동기(blocking) 함수라, 대화할 때마다(생성 요청이 아니어도) 이벤트 루프를 막을 수 있었다.
    # generate_flow* 계열과 동일한 이유로 asyncio.to_thread로 넘긴다.
    project_id = thread_id.replace("project-", "") if thread_id.startswith("project-") else ""
    context_task = (
        asyncio.to_thread(retrieve_chat_context, project_id, message) if project_id
        else asyncio.sleep(0, result="")
    )
    task_spec_task = (
        normalize_task_spec(message)
        if should_normalize_task_spec(message, has_existing_graph=bool(g.nodes))
        else asyncio.sleep(0, result=None)
    )
    context, task_spec_result = await asyncio.gather(context_task, task_spec_task)

    # GenerationPlan(백로그 10번, §4.4): 요청·TaskSpec에서 결정론적으로 후보 수/평가 정책을
    # 정한다. adaptive 경로가 꺼져 있어도 계획은 만들어 trace에 남긴다 — 전환 판단의 데이터.
    generation_plan.begin_plan(
        message, complexity_level,
        task_spec=task_spec_result.spec if task_spec_result else None,
        has_existing_graph=bool(g.nodes),
    )

    agent, get_current_graph, get_clarification, get_last_valid_graph = build_agent(
        g, complexity_level=complexity_level, checkpointer=checkpointer, thread_id=thread_id,
        langfuse_handler=handler, db=db, generation_trace_id=trace_id,
    )
    
    final_message = message
    # 지목한 대상은 **맨 앞**에 둔다(백로그 28 POINT-1). 뒤에 붙이면 앞쪽 문맥에 묻힌다.
    # 이 지시가 지켜질 거라고 믿지는 않는다 — 서버가 결과를 직접 비교해 거부한다.
    if pointing_instruction:
        final_message = f"{pointing_instruction}\n\n[사용자 요청]\n{message}"
    if context:
        final_message = f"{final_message}\n\n{context}"
    if task_spec_result and task_spec_result.spec:
        final_message = f"{final_message}\n\n{build_task_spec_context(task_spec_result.spec)}"
    elif task_spec_result and task_spec_result.error:
        print(f"[task_spec] 정규화 실패, 기존 agent 판단으로 폴백: {task_spec_result.error}")

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": final_message}]},
        {"configurable": {"thread_id": thread_id}},
    )
    reply = result["messages"][-1].content

    # LangChain AIMessage 응답에서 토큰 사용량 추출
    task_spec_usage = task_spec_result.token_usage if task_spec_result else {}
    token_usage = {
        "input_tokens": int(task_spec_usage.get("input_tokens", 0) or 0),
        "output_tokens": int(task_spec_usage.get("output_tokens", 0) or 0),
        "total_tokens": int(task_spec_usage.get("total_tokens", 0) or 0),
    }
    for msg in reversed(result["messages"]):
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            token_usage["input_tokens"] += usage.get("input_tokens", 0)
            token_usage["output_tokens"] += usage.get("output_tokens", 0)
            token_usage["total_tokens"] += usage.get("total_tokens", 0)
            break  # 마지막 AI 메시지 한 번만 집계
    if task_spec_result:
        token_usage["task_spec"] = {
            "prompt_version": task_spec_result.prompt_version,
            "latency_ms": task_spec_result.latency_ms,
            "error": task_spec_result.error,
            **task_spec_usage,
        }

    final_graph = get_current_graph()
    clarification = get_clarification()
    active_task_spec = task_spec_result.spec if task_spec_result and task_spec_result.spec else None
    fallback_notes: List[str] = []

    def attach_trace(
        output_graph: dict,
        *,
        outcome: str,
        status: str,
        issues: Optional[List[Any]] = None,
        notes: Optional[List[str]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        issue_payload = []
        for issue in issues or []:
            if hasattr(issue, "model_dump"):
                issue_payload.append(issue.model_dump())
            elif isinstance(issue, dict):
                issue_payload.append(issue)
            else:
                issue_payload.append({"code": "UNKNOWN", "message": str(issue)})
        from dry_run import dry_run_workflow

        dry_run = dry_run_workflow(output_graph).model_dump() if outcome == "graph" else None
        # 이번 턴의 선별 이벤트를 회수해 최종 그래프에 실제로 쓰인 노드와 비교한다(ADR-0013).
        selection_trace = node_knowledge.collect_selection_trace()
        node_selection = None
        if selection_trace:
            final_types = [str(node.get("type") or "") for node in (output_graph.get("nodes") or [])]
            node_selection = node_knowledge.summarize_selection(selection_trace["events"], final_types)
        plan_record = generation_plan.collect_plan()
        trace = build_generation_trace(
            trace_id=trace_id,
            thread_id=thread_id,
            message=message,
            complexity_level=complexity_level,
            graph_data=output_graph,
            token_usage=token_usage,
            task_spec=active_task_spec.model_dump() if active_task_spec else None,
            validation_issues=issue_payload,
            repair_notes=notes,
            outcome=outcome,
            status=status,
            latency_ms=round((time.perf_counter() - trace_started) * 1000),
            error_message=error_message,
            repair_prompt_version=FLOW_REPAIR_PROMPT_VERSION,
            dry_run_result=dry_run,
            training_consent=training_consent,
            node_selection=node_selection,
            generation_plan=plan_record,
        )
        token_usage["trace_id"] = trace_id
        token_usage["_generation_trace"] = trace

    # TaskSpec이 즉시 생성을 결정했는데 상위 agent가 도구 호출을 놓치거나 잘못 질문한 경우,
    # 같은 결정을 다시 LLM 라우팅에 맡기지 않고 생성기를 한 번 직접 호출한다.
    if initial_dump == final_graph.model_dump():
        should_fallback_generate = (
            not initial_dump.get("nodes")
            and active_task_spec is not None
            and active_task_spec.request_kind == "create"
            and not active_task_spec.clarification_required
        )
        if should_fallback_generate:
            fallback_timeout = float(os.getenv("LLM_GENERATION_FALLBACK_TIMEOUT_SECONDS", "75"))
            fallback_request = f"{message}\n\n{build_task_spec_context(active_task_spec)}"
            try:
                generated = await asyncio.wait_for(
                    asyncio.to_thread(
                        generate_flow, fallback_request, complexity_level=complexity_level,
                    ),
                    timeout=fallback_timeout,
                )
                final_graph, fallback_notes, fallback_issues = await repair_flow_after_agent(
                    generated,
                    message,
                    complexity_level=complexity_level,
                    task_spec=active_task_spec,
                )
                clarification = None
                if not fallback_issues:
                    reply = "워크플로우를 생성했습니다."
                    if not fallback_notes:
                        fallback_notes.append("TaskSpec에 따라 직접 생성")
                else:
                    reply += (
                        "\n\n(자동 생성 폴백 후 남은 문제: "
                        + "; ".join(issue.message for issue in fallback_issues)
                        + ")"
                    )
            except asyncio.TimeoutError:
                clarification = None
                reply += f"\n\n(자동 생성 폴백이 {fallback_timeout:g}초 시간 제한에 도달했습니다.)"
            except Exception as exc:
                clarification = None
                reply += f"\n\n(자동 생성 폴백 실패: {exc})"

    # 대화이거나 폴백 생성도 그래프를 만들지 못했다면 원본을 유지한다.
    if initial_dump == final_graph.model_dump():
        if handler and hasattr(handler, 'flush'):
            handler.flush()
        if clarification:
            outcome, trace_status, trace_issues = "clarification", "completed", []
        elif active_task_spec is not None and active_task_spec.request_kind == "create":
            outcome, trace_status = "no_graph", "failed"
            trace_issues = [{
                "code": "NO_GRAPH",
                "message": "생성 요청이 그래프를 반환하지 않았다.",
                "repairable": True,
            }]
        else:
            outcome, trace_status, trace_issues = "chat", "completed", []
        attach_trace(
            graph_data,
            outcome=outcome,
            status=trace_status,
            issues=trace_issues,
            notes=fallback_notes,
        )
        return reply, graph_data, token_usage, clarification

    is_new_generation = not initial_dump.get("nodes") and bool(final_graph.nodes)
    ok, errs = validate_flow(final_graph, require_complete=is_new_generation)
    trace_issue_models: List[Any] = validation_issues(errs)
    coverage_issues = (
        task_coverage_issues(active_task_spec, final_graph.model_dump())
        if ok and is_new_generation and active_task_spec is not None else []
    )
    if coverage_issues:
        ok = False
        errs = [issue.message for issue in coverage_issues]
        trace_issue_models = coverage_issues

    repair_notes = list(fallback_notes)
    if not ok and is_new_generation:
        repaired_graph, repair_notes, repaired_issues = await repair_flow_after_agent(
            final_graph, message, complexity_level=complexity_level, task_spec=active_task_spec,
        )
        if not repaired_issues:
            final_graph = repaired_graph
            ok, errs = True, []
            trace_issue_models = []
        else:
            final_graph = repaired_graph
            trace_issue_models = repaired_issues
            last_valid_graph = get_last_valid_graph()
            has_intent_issues = any(issue.code.startswith("INTENT_") for issue in repaired_issues)
            if last_valid_graph is not None and not has_intent_issues:
                final_graph = last_valid_graph
                ok, errs = True, []
                trace_issue_models = []
                repair_notes.append("마지막 검증 통과 그래프로 복원")
            else:
                errs = [issue.message for issue in repaired_issues]
    
    # 캔버스에는 항상 반영 (에러가 있어도 사용자가 눈으로 보고 수정할 수 있도록)
    response_graph_data = auto_layout(final_graph)

    if repair_notes and ok:
        reply += f"\n\n(자동 구조 수정: {'; '.join(repair_notes)})"
    
    if not ok:
        reply += f"\n\n(⚠️ 일부 구조적 문제가 있어 확인이 필요합니다: {'; '.join(errs)})"

    if handler and hasattr(handler, 'flush'):
        handler.flush()

    attach_trace(
        response_graph_data,
        outcome="graph",
        status="completed" if ok else "failed",
        issues=[] if ok else trace_issue_models,
        notes=repair_notes,
    )

    return reply, response_graph_data, token_usage, clarification


# ── 데모 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    req = "회의록 PDF를 올리면 할 일 목록을 뽑아주는 봇 만들어줘"
    print("요청:", req, "\n")
    graph = generate_safely(req)
    print(json.dumps(graph, ensure_ascii=False, indent=2))
