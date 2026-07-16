"""
seed_curated_templates.py — 사람이 직접 큐레이션한 "프로덕트급" 템플릿 5개를 Pre-translated DB에 시딩.

배경: translate_and_ingest.py(gpt-4o-mini 자동 번역)의 실측 성공률이 낮았고(20개 중 진짜 표본
기준 약 47%), LLM이 28종 카탈로그 밖 노드 타입을 종종 지어내는 문제가 있었다. 이 스크립트는
그 대신 실제 GitHub의 유명 n8n 템플릿 모음(scraped_templates/, awesome-n8n-templates 계열)에서
분기·병합·반복이 풍부한 진짜 프로덕션급 워크플로우 5개를 골라, 그 로직을 사람이 직접 우리
FlowGraph 스키마로 재구성한 것이다. LLM 번역이 아니므로 카탈로그 위반이 없고, validate_flow()로
전부 검증한 뒤 통과한 것만 DB에 넣는다.

원본 출처(로직 참고, 1:1 이식 아님):
  1. scraped_templates/OpenAI_and_LLMs/AI Data Extraction with Dynamic Prompts and Airtable.json
  2. scraped_templates/Gmail_and_Email_Automation/Auto Categorise Outlook Emails with AI.json
  3. scraped_templates/PDF_and_Document_Processing/Extract data from resume and create PDF with Gotenberg.json
  4. scraped_templates/Airtable/AI Agent to chat with Airtable and analyze data.json
  5. scraped_templates/Slack/Venafi Cloud Slack Cert Bot.json
  6. _archive_n8n_translation_pipeline/scraped_templates/Telegram/Internship Informer.json
  7. _archive_n8n_translation_pipeline/scraped_templates/HR_and_Recruitment/HR & IT Helpdesk Chatbot with Audio Transcription.json
  8. _archive_n8n_translation_pipeline/scraped_templates/Database_and_Storage/Generate SQL queries from schema only - AI-powered.json
  9. _archive_n8n_translation_pipeline/scraped_templates/Notion/Analyse papers from Hugging Face with AI and store them in Notion.json
  10. _archive_n8n_translation_pipeline/scraped_templates/Forms_and_Surveys/Qualifying Appointment Requests with AI & n8n Forms.json
  11. _archive_n8n_translation_pipeline/scraped_templates/Google_Drive_and_Google_Sheets/Automatic Background Removal for Images in Google Drive.json
  12. _archive_n8n_translation_pipeline/scraped_templates/Instagram_Twitter_Social_Media/Reddit AI digest.json
  13. _archive_n8n_translation_pipeline/scraped_templates/Discord/Discord AI-powered bot.json
  14. _archive_n8n_translation_pipeline/scraped_templates/AI_Research_RAG_and_Data_Analysis/Build a Tax Code Assistant with Qdrant, Mistral.ai and OpenAI.json
  15. _archive_n8n_translation_pipeline/scraped_templates/WhatsApp/Building Your First WhatsApp Chatbot.json
  16. _archive_n8n_translation_pipeline/scraped_templates/WordPress/Auto-Tag Blog Posts in WordPress with AI.json
  17. _archive_n8n_translation_pipeline/scraped_templates/devops/docker-compose-controller.json
  18. _archive_n8n_translation_pipeline/scraped_templates/AI_Research_RAG_and_Data_Analysis/Survey Insights with Qdrant, Python and Information Extractor.json

19~38: 같은 원칙으로 n8n-node ↔ 28종 카탈로그 매핑 표를 기준 삼아 나머지 미사용 소스 카테고리
(OpenAI_and_LLMs, Other_Integrations_and_Use_Cases, AI_Research_RAG_and_Data_Analysis,
Gmail_and_Email_Automation, Telegram, PDF_and_Document_Processing, Google_Drive_and_Google_Sheets,
Instagram_Twitter_Social_Media, Notion, Slack, WordPress, Database_and_Storage, Airtable,
WhatsApp, HR_and_Recruitment)에서 골라 추가한 20개. 원본 파일명은 각 템플릿 위 주석 참고.
"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from meta_agent import FlowGraph, FlowNode, FlowEdge, validate_flow, PLACEHOLDER_URL
from rag_utils import get_vector_store, TRANSLATED_COLLECTION

MODEL = "gpt-4o-mini"


def node(id_, type_, data=None):
    return FlowNode(id=id_, type=type_, data=data or {})


def edge(id_, source, target, sourceHandle=None):
    return FlowEdge(id=id_, source=source, target=target, sourceHandle=sourceHandle)


# ── 1. Airtable 레코드/필드 변경 시 AI로 빈 필드 자동 채움 ──────────────────
tpl1 = FlowGraph(
    title="Airtable 레코드 변경 시 AI 필드 자동 채움",
    description="Airtable 레코드/필드가 변경되면 첨부파일을 분석해 빈 필드를 AI로 자동 채운다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "Airtable 웹훅 이벤트 페이로드(row_changed 또는 field_changed)", "testValue": '{"event_type":"row_changed"}'}),
        node("n3", "conditionNode", {"rules": [{"id": "row_changed", "operator": "Contains", "value": "row_changed"}]}),
        node("n4", "distributorNode"),
        node("n5", "httpRequestNode", {"method": "GET", "url": "https://api.airtable.com/v0/{{baseId}}/{{tableId}}/{{recordId}}/attachment"}),
        node("n6", "tokenizerNode", {"method": "extract_text"}),
        node("n7", "promptNode", {"userPrompt": "이 파일 내용을 바탕으로 이 레코드의 빈 필드에 채울 값을 생성해줘"}),
        node("n8", "llmNode", {"model": MODEL, "systemPrompt": "너는 Airtable 레코드의 빈 필드를 채우는 데이터 추출 전문가다"}),
        node("n9", "httpRequestNode", {"method": "PUT", "url": "https://api.airtable.com/v0/{{baseId}}/{{tableId}}/{{recordId}}"}),
        node("n10", "distributorNode"),
        node("n11", "promptNode", {"userPrompt": "변경된 필드 하나에 어울리는 값을 새로 생성해줘"}),
        node("n12", "llmNode", {"model": MODEL, "systemPrompt": "너는 Airtable 필드 값을 동적으로 생성하는 전문가다"}),
        node("n13", "httpRequestNode", {"method": "PUT", "url": "https://api.airtable.com/v0/{{baseId}}/{{tableId}}/{{recordId}}"}),
        node("n14", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n15", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4", "row_changed"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
        edge("e8", "n8", "n9"),
        edge("e9", "n3", "n10", "else"),
        edge("e10", "n10", "n11"),
        edge("e11", "n11", "n12"),
        edge("e12", "n12", "n13"),
        edge("e13", "n4", "n14", "done"),
        edge("e14", "n10", "n14", "done"),
        edge("e15", "n14", "n15"),
    ],
)

# ── 2. 받은 이메일 AI 분류 후 폴더 자동 이동 + 긴급 메일 슬랙 알림 ──────────
tpl2 = FlowGraph(
    title="Outlook 메일 AI 분류 및 폴더 자동 이동",
    description="수신 메일을 AI가 긴급/스팸/일반으로 분류해 해당 폴더로 이동하고 긴급 메일은 슬랙으로 알린다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "distributorNode"),
        node("n3", "promptNode", {"userPrompt": "이 이메일 내용을 보고 카테고리를 판별해줘. 반드시 '긴급', '스팸', '일반' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 이메일 분류 전문가다"}),
        node("n5", "conditionNode", {"rules": [
            {"id": "urgent", "operator": "Contains", "value": "긴급"},
            {"id": "spam", "operator": "Contains", "value": "스팸"},
        ]}),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://graph.microsoft.com/v1.0/me/mailFolders/Urgent/messages/{{id}}/move"}),
        node("n7", "slackNode", {"channel": "#urgent-mail", "message": "긴급 메일이 도착했습니다"}),
        node("n8", "httpRequestNode", {"method": "POST", "url": "https://graph.microsoft.com/v1.0/me/mailFolders/Spam/messages/{{id}}/move"}),
        node("n9", "httpRequestNode", {"method": "POST", "url": "https://graph.microsoft.com/v1.0/me/mailFolders/General/messages/{{id}}/move"}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "urgent"),
        edge("e6", "n6", "n7"),
        edge("e7", "n5", "n8", "spam"),
        edge("e8", "n5", "n9", "else"),
        edge("e9", "n7", "n10"),
        edge("e10", "n8", "n10"),
        edge("e11", "n9", "n10"),
        edge("e12", "n2", "n11", "done"),
    ],
)

# ── 3. 이력서 PDF 파싱(병렬 정리) → HTML 변환 → PDF 재생성 → 텔레그램 발송 ──
tpl3 = FlowGraph(
    title="이력서 PDF 파싱 후 정리된 이력서 PDF 재생성",
    description="이력서 PDF에서 정보를 병렬로 추출/정리한 뒤 깔끔한 HTML/PDF로 재생성해 전송한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "tokenizerNode", {"method": "extract_text"}),
        node("n3", "promptNode", {"userPrompt": "이 이력서에서 인적사항과 보유 기술만 뽑아서 정리해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서를 구조화하는 전문가다"}),
        node("n5", "promptNode", {"userPrompt": "이 이력서에서 경력사항과 학력사항만 뽑아서 정리해줘"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서를 구조화하는 전문가다"}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "promptNode", {"userPrompt": "위 정리된 이력서 정보를 깔끔한 HTML 이력서 형식으로 변환해줘"}),
        node("n9", "llmNode", {"model": MODEL, "systemPrompt": "너는 HTML 이력서를 생성하는 전문가다"}),
        node("n10", "httpRequestNode", {"method": "POST", "url": "https://gotenberg.example.com/forms/chromium/convert/html"}),
        node("n11", "httpRequestNode", {"method": "POST", "url": "https://api.telegram.org/bot{{token}}/sendDocument"}),
        node("n12", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n2", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n4", "n7"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
        edge("e11", "n10", "n11"),
        edge("e12", "n11", "n12"),
    ],
)

# ── 4. Airtable 데이터 비서 챗봇(검색/스키마 조회 분기 + 병합 응답) ─────────
tpl4 = FlowGraph(
    title="Airtable 데이터 비서 챗봇",
    description="질문 의도(레코드 검색/스키마 조회)를 분류해 Airtable 데이터를 조회하고 답변한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "promptNode", {"userPrompt": "사용자 질문을 보고 필요한 작업이 '레코드 검색'인지 '스키마 조회'인지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 Airtable 데이터 비서다. 의도만 짧게 분류한다"}),
        node("n4", "conditionNode", {"rules": [{"id": "search", "operator": "Contains", "value": "레코드 검색"}]}),
        node("n5", "httpRequestNode", {"method": "GET", "url": "https://api.airtable.com/v0/{{baseId}}/{{tableId}}"}),
        node("n6", "jsonParserNode", {"mode": "parse"}),
        node("n7", "httpRequestNode", {"method": "GET", "url": "https://api.airtable.com/v0/meta/bases/{{baseId}}/tables"}),
        node("n8", "jsonParserNode", {"mode": "parse"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "promptNode", {"userPrompt": "위 Airtable 데이터를 바탕으로 사용자 질문에 답해줘"}),
        node("n11", "llmNode", {"model": MODEL, "systemPrompt": "너는 Airtable 데이터 분석 비서다"}),
        node("n12", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "search"),
        edge("e5", "n5", "n6"),
        edge("e6", "n4", "n7", "else"),
        edge("e7", "n7", "n8"),
        edge("e8", "n6", "n9"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
        edge("e11", "n10", "n11"),
        edge("e12", "n11", "n12"),
    ],
)

# ── 5. 인증서 발급 요청: VirusTotal 평판 조회 → 자동발급 / 사람 승인 분기 ──
tpl5 = FlowGraph(
    title="인증서 발급 요청 자동/수동 승인 봇",
    description="도메인 평판을 조회해 안전하면 자동 발급, 위험하면 사람 승인을 거쳐 인증서를 발급한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "인증서 발급 요청 페이로드(도메인 포함)", "testValue": '{"domain":"example.com"}'}),
        node("n3", "httpRequestNode", {"method": "GET", "url": "https://www.virustotal.com/api/v3/domains/{{domain}}"}),
        node("n4", "jsonParserNode", {"mode": "extract", "extractKey": "malicious_count"}),
        node("n5", "conditionNode", {"rules": [{"id": "clean", "operator": "==", "value": "0"}]}),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://api.venafi.cloud/v1/certificaterequests"}),
        node("n7", "slackNode", {"channel": "#cert-bot", "message": "악성 리포트 0건 확인, 인증서가 자동으로 발급되었습니다"}),
        node("n8", "humanApprovalNode", {"message": "악성 리포트가 발견되어 수동 승인이 필요합니다. 인증서를 발급할까요?"}),
        node("n10", "httpRequestNode", {"method": "POST", "url": "https://api.venafi.cloud/v1/certificaterequests"}),
        node("n11", "slackNode", {"channel": "#cert-bot", "message": "수동 승인 후 인증서가 발급되었습니다"}),
        node("n12", "slackNode", {"channel": "#cert-bot", "message": "인증서 발급 요청이 거절되었습니다"}),
        node("n13", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n14", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "clean"),
        edge("e6", "n6", "n7"),
        edge("e7", "n5", "n8", "else"),
        edge("e9", "n8", "n10", "approved"),
        edge("e10", "n10", "n11"),
        edge("e11", "n8", "n12", "rejected"),
        edge("e12", "n7", "n13"),
        edge("e13", "n11", "n13"),
        edge("e14", "n12", "n13"),
        edge("e15", "n13", "n14"),
    ],
)

# ── 6. 채용/공고 링크 모니터링 → AI 유효성 판별 → 카카오톡 알림 ─────────────
tpl6 = FlowGraph(
    title="채용/공고 링크 모니터링 → AI 유효성 판별 → 카카오톡 알림",
    description="여러 공고 페이지를 모니터링해 유효한 채용 공고만 카카오톡으로 알린다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "모니터링할 공고 페이지 링크 목록(JSON 배열 문자열)", "testValue": '["https://example.com/notice/1","https://example.com/notice/2"]'}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "webCrawlerNode", {"url": ""}),
        node("n6", "promptNode", {"userPrompt": "이 페이지가 채용/인턴십 공고인지 확인해줘. 공고라면 '📌 제목: OOO\\n마감일: OOO' 형식으로 정리하고, 공고가 아니거나 이미 마감됐으면 정확히 'SKIP'이라고만 답해."}),
        node("n7", "llmNode", {"model": MODEL, "systemPrompt": "너는 채용 공고 페이지에서 정보를 정확히 추출하고 유효성을 판별하는 전문가다"}),
        node("n8", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n9", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
        edge("e8", "n8", "n9", "else"),
        edge("e9", "n9", "n10"),
        edge("e10", "n8", "n10", "skip"),
        edge("e11", "n4", "n11", "done"),
    ],
)

# ── 7. 사내 정책 헬프데스크 챗봇(카카오톡 답변, 발송 전 사람 승인) ──────────
tpl7 = FlowGraph(
    title="사내 정책 헬프데스크 챗봇(카카오톡 답변, 발송 전 사람 승인)",
    description="사내 정책 문의에 AI가 답변 초안을 작성하고, 사람 승인 후 카카오톡으로 발송한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "dynamicInputNode", {"inputLabel": "직원의 문의 내용", "testValue": "연차는 며칠 남았나요?"}),
        node("n5", "promptNode", {"userPrompt": "위 사내 정책 문서 내용을 참고하여 직원의 질문에 대한 답변을 작성해줘. 정책에 명시되지 않은 내용이면 '정책 문서에서 확인할 수 없습니다. 인사팀에 문의해주세요'라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 회사 인사/IT 정책에 정통한 사내 헬프데스크 상담원이다"}),
        node("n7", "humanApprovalNode", {"message": "아래 답변을 직원에게 카카오톡으로 발송할까요?"}),
        node("n9", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n10", "pythonNode", {"code": "output_data = '답변 발송이 취소되었습니다.'"}),
        node("n11", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n12", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e8", "n7", "n9", "approved"),
        edge("e9", "n9", "n11"),
        edge("e10", "n7", "n10", "rejected"),
        edge("e11", "n10", "n11"),
        edge("e12", "n11", "n12"),
    ],
)

# ── 8. DB 데이터 비서 챗봇(자연어 질의 → 카카오톡 답변) ──────────────────
tpl8 = FlowGraph(
    title="DB 데이터 비서 챗봇(자연어 질의 → 카카오톡 답변)",
    description="DB에서 최근 데이터를 조회해두고, 자연어 질문에 그 데이터를 근거로 답변해 카카오톡으로 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "databaseNode", {"connectionString": PLACEHOLDER_URL, "query": "SELECT id, name, email, created_at FROM users ORDER BY created_at DESC LIMIT 200"}),
        node("n3", "conditionNode", {"rules": [{"id": "error", "operator": "Contains", "value": "Database Error"}]}),
        node("n4", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n5", "dynamicInputNode", {"inputLabel": "위 데이터에 대해 궁금한 점", "testValue": "이번 주에 신규 가입한 사용자 몇 명이야?"}),
        node("n6", "promptNode", {"userPrompt": "위 데이터를 참고해서 질문에 대해 정확하고 간결하게 답변해줘. 데이터에 없는 내용은 추측하지 말고 '데이터에서 확인할 수 없습니다'라고 답해."}),
        node("n7", "llmNode", {"model": MODEL, "systemPrompt": "너는 데이터베이스 조회 결과를 바탕으로 질문에 답하는 데이터 비서다"}),
        node("n8", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4", "error"),
        edge("e4", "n4", "n9"),
        edge("e5", "n3", "n5", "else"),
        edge("e6", "n5", "n6"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
    ],
)

# ── 9. 논문 모니터링 → AI 요약 → Notion 저장 ────────────────────────────
tpl9 = FlowGraph(
    title="논문 모니터링 → AI 요약 → Notion 저장",
    description="매일 새 논문을 모니터링해 AI로 요약하고 Notion에 저장한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 9 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "webCrawlerNode", {"url": ""}),
        node("n6", "promptNode", {"userPrompt": "이 논문 초록을 3문장으로 한국어 요약하고, 관련 분야 키워드 3개를 뽑아줘"}),
        node("n7", "llmNode", {"model": MODEL, "systemPrompt": "너는 AI/ML 논문을 요약하는 리서치 어시스턴트다"}),
        node("n8", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n9", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
        edge("e8", "n4", "n9", "done"),
    ],
)

# ── 10. 예약 신청 접수 → AI 자격 검토 → 사람 승인 → 확정/반려 안내 ─────────
tpl10 = FlowGraph(
    title="예약 신청 접수 → AI 자격 검토 → 사람 승인 → 확정/반려 안내",
    description="예약 신청의 적합성을 AI가 1차 검토하고, 사람이 최종 승인하면 확정/반려 메일을 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "예약 신청 내용(이름/목적/희망일시)", "testValue": "홍길동 / 상담 문의 / 2026-08-01 14:00"}),
        node("n3", "promptNode", {"userPrompt": "이 예약 신청이 우리 서비스 대상에 적합한지 판단해줘. 적합하면 정확히 'QUALIFIED', 아니면 'REJECTED: 사유'라고 답해."}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 예약 신청의 적합성을 판별하는 어시스턴트다"}),
        node("n5", "conditionNode", {"rules": [{"id": "qualified", "operator": "Contains", "value": "QUALIFIED"}]}),
        node("n6", "humanApprovalNode", {"message": "AI가 적합 판정한 예약 신청입니다. 최종 승인하시겠습니까?"}),
        node("n8", "emailNode", {"toEmail": "user@example.com", "subject": "예약이 확정되었습니다"}),
        node("n9", "emailNode", {"toEmail": "user@example.com", "subject": "예약 요청이 반려되었습니다"}),
        node("n10", "emailNode", {"toEmail": "user@example.com", "subject": "예약 신청이 반려되었습니다"}),
        node("n11", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n12", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n13", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "qualified"),
        edge("e7", "n6", "n8", "approved"),
        edge("e8", "n8", "n11"),
        edge("e9", "n6", "n9", "rejected"),
        edge("e10", "n9", "n11"),
        edge("e11", "n11", "n12"),
        edge("e12", "n5", "n10", "else"),
        edge("e13", "n10", "n12"),
        edge("e14", "n12", "n13"),
    ],
)

# ── 11. 구글 드라이브 새 이미지 → 배경 제거 API → 결과 업로드 알림 ─────────
tpl11 = FlowGraph(
    title="이미지 배경 제거 자동화(구글 드라이브 → API → 알림)",
    description="새 이미지가 업로드되면 배경 제거 API를 호출하고 결과를 업로드한 뒤 알린다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/drive-image-uploaded"}),
        node("n2", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n3", "conditionNode", {"rules": [{"id": "fail", "operator": "Contains", "value": "error"}]}),
        node("n4", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4", "fail"),
        edge("e4", "n4", "n7"),
        edge("e5", "n3", "n5", "else"),
        edge("e6", "n5", "n6"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
    ],
)

# ── 12. 레딧 인기글 수집 → AI 관련성 판별/요약 → 카카오톡 다이제스트 ───────
tpl12 = FlowGraph(
    title="레딧 인기글 수집 → AI 관련성 판별/요약 → 카카오톡 다이제스트",
    description="정기적으로 레딧 인기글을 수집해 관련성 있는 글만 요약해 카카오톡으로 보낸다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 8 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 글이 우리 관심 주제(기술/스타트업)와 관련 있는지 판단해줘. 관련 있으면 'RELEVANT: 한줄요약', 아니면 정확히 'SKIP'이라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 레딧 게시물의 관련성을 판별하고 요약하는 큐레이터다"}),
        node("n7", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n8", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8", "else"),
        edge("e8", "n8", "n9"),
        edge("e9", "n7", "n9", "skip"),
        edge("e10", "n4", "n10", "done"),
    ],
)

# ── 13. 디스코드 문의 자동 분류 → 담당 부서 채널로 라우팅 ──────────────────
tpl13 = FlowGraph(
    title="디스코드 문의 자동 분류 → 담당 부서 채널 라우팅",
    description="디스코드로 들어온 문의를 AI가 부서별로 분류해 해당 채널로 라우팅한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/discord-message"}),
        node("n2", "promptNode", {"userPrompt": "이 문의가 '기술지원', '결제문의', '일반문의' 중 어디에 해당하는지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 문의를 부서별로 분류하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [{"id": "tech", "operator": "Contains", "value": "기술지원"}, {"id": "billing", "operator": "Contains", "value": "결제문의"}]}),
        node("n5", "discordNode", {"botToken": "", "channelId": ""}),
        node("n6", "discordNode", {"botToken": "", "channelId": ""}),
        node("n7", "discordNode", {"botToken": "", "channelId": ""}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "tech"),
        edge("e5", "n5", "n8"),
        edge("e6", "n4", "n6", "billing"),
        edge("e7", "n6", "n8"),
        edge("e8", "n4", "n7", "else"),
        edge("e9", "n7", "n8"),
        edge("e10", "n8", "n9"),
    ],
)

# ── 14. 세금/정책 문서 Q&A 어시스턴트 ─────────────────────────────────────
tpl14 = FlowGraph(
    title="세금/정책 문서 Q&A 어시스턴트",
    description="세금/정책 문서를 참고해서 질문에 정확하게 답변하는 어시스턴트.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "dynamicInputNode", {"inputLabel": "세금 관련 질문", "testValue": "1인 사업자 부가세 신고 기한이 언제야?"}),
        node("n5", "promptNode", {"userPrompt": "위 문서 내용을 참고해서 질문에 정확하게 답변해줘. 문서에 없는 내용이면 추측하지 말고 '문서에서 확인할 수 없습니다'라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 세무/법률 문서를 바탕으로 정확하게 답변하는 어시스턴트다"}),
        node("n7", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 15. 제품 카탈로그 문의 챗봇(카카오톡 답변) ─────────────────────────────
tpl15 = FlowGraph(
    title="제품 카탈로그 문의 챗봇(카카오톡 답변)",
    description="제품 카탈로그 문서를 참고해서 고객 문의에 답변하고 카카오톡으로 발송한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "dynamicInputNode", {"inputLabel": "고객 문의 내용", "testValue": "이 제품 가격이 얼마인가요?"}),
        node("n5", "promptNode", {"userPrompt": "위 제품 카탈로그를 참고해서 고객 문의에 친절하게 답변해줘. 카탈로그에 없는 내용이면 '자세한 내용은 상담원에게 문의해주세요'라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 친절한 판매 상담원이다"}),
        node("n7", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
    ],
)

# ── 16. 블로그 포스트 자동 태깅 ───────────────────────────────────────────
tpl16 = FlowGraph(
    title="블로그 포스트 자동 태깅",
    description="새 블로그 글을 주기적으로 확인해서 AI가 태그를 생성하고 자동으로 등록한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 */6 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 블로그 글 내용을 보고 어울리는 태그를 3~5개 쉼표로 구분해서 만들어줘"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 블로그 글에 어울리는 태그를 만드는 편집자다"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n4", "n8", "done"),
    ],
)

# ── 17. 웹훅으로 서버(도커) 시작/중지 제어 ─────────────────────────────────
tpl17 = FlowGraph(
    title="웹훅으로 서버(도커) 시작/중지 제어",
    description="웹훅으로 시작/중지 명령을 받아 서버 제어 API를 호출한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/docker-control"}),
        node("n2", "conditionNode", {"rules": [{"id": "start", "operator": "Contains", "value": "start"}, {"id": "stop", "operator": "Contains", "value": "stop"}]}),
        node("n3", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n4", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n5", "valueNode", {"value": "알 수 없는 명령입니다"}),
        node("n6", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n7", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3", "start"),
        edge("e3", "n2", "n4", "stop"),
        edge("e4", "n2", "n5", "else"),
        edge("e5", "n3", "n6"),
        edge("e6", "n4", "n6"),
        edge("e7", "n5", "n6"),
        edge("e8", "n6", "n7"),
    ],
)

# ── 18. 설문 응답 인사이트 분석 → 카카오톡 알림 ───────────────────────────
tpl18 = FlowGraph(
    title="설문 응답 인사이트 분석 → 카카오톡 알림",
    description="정기적으로 설문 응답 데이터를 분석해 핵심 인사이트를 뽑아 카카오톡으로 알린다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 9 * * 1"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 설문 응답 데이터에서 핵심 인사이트와 패턴을 3가지 뽑아줘"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 설문 데이터를 분석해서 인사이트를 도출하는 리서처다"}),
        node("n7", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n4", "n8", "done"),
    ],
)

# ── 19. 이력서 분석 및 후보자 평가 ─────────────────────────────────────────
tpl19 = FlowGraph(
    title="이력서 분석 및 후보자 평가",
    description="이력서 내용을 AI가 분석해 자격 요건 충족 여부를 평가하고 결과를 이메일로 안내한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 이력서가 채용 공고의 자격 요건(경력 3년 이상, 관련 기술 스택)을 충족하는지 평가해줘. 충족하면 정확히 'PASS', 아니면 'FAIL: 사유'라고 답해."}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서를 평가하는 채용 담당자다"}),
        node("n6", "conditionNode", {"rules": [{"id": "pass", "operator": "Contains", "value": "PASS"}]}),
        node("n7", "emailNode", {"toEmail": "candidate@example.com", "subject": "서류 합격 안내"}),
        node("n8", "emailNode", {"toEmail": "candidate@example.com", "subject": "서류 결과 안내"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7", "pass"),
        edge("e7", "n6", "n8", "else"),
        edge("e8", "n7", "n9"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
    ],
)

# ── 20. 고객 피드백 감성 분석 → 담당자 알림/로그 분기 ───────────────────────
tpl20 = FlowGraph(
    title="고객 피드백 감성 분석 및 라우팅",
    description="고객 피드백의 감성을 분류해 부정적이면 담당자에게 슬랙으로 알리고, 그 외에는 로그만 남긴다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "고객 피드백 내용", "testValue": "배송이 너무 늦어서 화가 납니다"}),
        node("n3", "promptNode", {"userPrompt": "이 피드백의 감성을 판별해줘. 반드시 '긍정', '부정', '중립' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 피드백 감성 분석 전문가다"}),
        node("n5", "conditionNode", {"rules": [
            {"id": "negative", "operator": "Contains", "value": "부정"},
            {"id": "positive", "operator": "Contains", "value": "긍정"},
        ]}),
        node("n6", "slackNode", {"channel": "#customer-feedback", "message": "부정적인 고객 피드백이 접수되었습니다. 확인이 필요합니다"}),
        node("n7", "valueNode", {"value": "긍정 피드백으로 기록되었습니다"}),
        node("n8", "valueNode", {"value": "중립 피드백으로 기록되었습니다"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "negative"),
        edge("e6", "n6", "n9"),
        edge("e7", "n5", "n7", "positive"),
        edge("e8", "n7", "n9"),
        edge("e9", "n5", "n8", "else"),
        edge("e10", "n8", "n9"),
        edge("e11", "n9", "n10"),
    ],
)

# ── 21. GitLab MR AI 코드 리뷰 자동 코멘트 ─────────────────────────────────
tpl21 = FlowGraph(
    title="GitLab MR AI 코드 리뷰 자동 코멘트",
    description="새 MR이 열리면 diff를 AI가 리뷰해 그 결과를 MR에 코멘트로 남긴다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/gitlab-mr-opened"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "promptNode", {"userPrompt": "이 코드 변경사항(diff)을 리뷰해줘. 잠재적 버그, 보안 이슈, 개선 제안을 항목별로 정리해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 꼼꼼한 시니어 개발자로서 코드 리뷰를 하는 전문가다"}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 22. Linear 버그 분류 후 담당 팀으로 라우팅 ─────────────────────────────
tpl22 = FlowGraph(
    title="Linear 버그 분류 후 담당 팀 라우팅",
    description="새로 등록된 버그를 AI가 분류해 프론트엔드/백엔드/인프라 담당 팀으로 이슈를 옮긴다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/linear-new-bug"}),
        node("n2", "promptNode", {"userPrompt": "이 버그 리포트가 '프론트엔드', '백엔드', '인프라' 중 어디에 해당하는지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 버그 리포트를 담당 팀별로 분류하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [
            {"id": "frontend", "operator": "Contains", "value": "프론트엔드"},
            {"id": "backend", "operator": "Contains", "value": "백엔드"},
        ]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "frontend"),
        edge("e5", "n5", "n8"),
        edge("e6", "n4", "n6", "backend"),
        edge("e7", "n6", "n8"),
        edge("e8", "n4", "n7", "else"),
        edge("e9", "n7", "n8"),
        edge("e10", "n8", "n9"),
    ],
)

# ── 23. 매일 신규 논문 목록 수집 → AI 요약/카테고리 분류 → 저장 ────────────
tpl23 = FlowGraph(
    title="신규 논문 자동 요약 및 카테고리 분류",
    description="매일 새로 올라온 논문 목록을 가져와 각각 AI로 요약하고 카테고리를 분류해 저장한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 10 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 논문 초록을 2문장으로 요약하고, 'AI', '데이터', '시스템' 중 가장 잘 맞는 카테고리 하나를 붙여서 'OOO요약 (카테고리: OOO)' 형식으로 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 논문을 요약하고 분류하는 리서치 어시스턴트다"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n4", "n8", "done"),
    ],
)

# ── 24. SEO 시드 키워드 생성기 ─────────────────────────────────────────────
tpl24 = FlowGraph(
    title="SEO 시드 키워드 생성기",
    description="주제나 타겟 키워드를 입력하면 AI가 SEO에 활용할 시드 키워드 목록을 생성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "주제 또는 타겟 키워드", "testValue": "온라인 요가 강의"}),
        node("n3", "promptNode", {"userPrompt": "이 주제와 관련된 SEO 시드 키워드를 검색량이 있을 법한 순서로 20개 뽑아줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 SEO 키워드 리서치 전문가다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 25. Gmail 수신 메일 AI 자동 라벨링 ─────────────────────────────────────
tpl25 = FlowGraph(
    title="Gmail 수신 메일 AI 자동 라벨링",
    description="수신 메일을 AI가 중요/뉴스레터/영업/기타로 분류해 해당 라벨을 붙인다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/gmail-new-message"}),
        node("n2", "promptNode", {"userPrompt": "이 메일이 '중요', '뉴스레터', '영업' 중 어디에 해당하는지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 이메일을 분류하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [
            {"id": "important", "operator": "Contains", "value": "중요"},
            {"id": "newsletter", "operator": "Contains", "value": "뉴스레터"},
            {"id": "sales", "operator": "Contains", "value": "영업"},
        ]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "important"),
        edge("e5", "n5", "n9"),
        edge("e6", "n4", "n6", "newsletter"),
        edge("e7", "n6", "n9"),
        edge("e8", "n4", "n7", "sales"),
        edge("e9", "n7", "n9"),
        edge("e10", "n4", "n8", "else"),
        edge("e11", "n8", "n9"),
        edge("e12", "n9", "n10"),
    ],
)

# ── 26. Gmail 답장 초안 작성 → 사람 승인 후 발송 ───────────────────────────
tpl26 = FlowGraph(
    title="Gmail 답장 초안 작성 및 승인 발송",
    description="받은 메일에 대한 답장 초안을 AI가 작성하고, 사람이 승인하면 그대로 발송한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "받은 메일 내용", "testValue": "환불 절차가 어떻게 되나요?"}),
        node("n3", "promptNode", {"userPrompt": "위 메일에 대한 정중하고 명확한 답장 초안을 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 응대 이메일을 작성하는 담당자다"}),
        node("n5", "humanApprovalNode", {"message": "아래 답장 초안을 이대로 발송할까요?"}),
        node("n6", "emailNode", {"toEmail": "customer@example.com", "subject": "문의 답변 드립니다"}),
        node("n7", "pythonNode", {"code": "output_data = '답장 발송이 취소되었습니다.'"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "approved"),
        edge("e6", "n6", "n8"),
        edge("e7", "n5", "n7", "rejected"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 27. 텔레그램 메시지 유해언어 감지 ──────────────────────────────────────
tpl27 = FlowGraph(
    title="텔레그램 메시지 유해언어 감지",
    description="텔레그램 메시지를 AI가 검사해 유해언어가 감지되면 메시지를 삭제 처리한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/telegram-new-message"}),
        node("n2", "promptNode", {"userPrompt": "이 메시지에 욕설이나 유해 표현이 있는지 판별해줘. 있으면 정확히 'TOXIC', 없으면 정확히 'OK'라고만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 채팅 메시지의 유해성을 판별하는 모더레이터다"}),
        node("n4", "conditionNode", {"rules": [{"id": "toxic", "operator": "Contains", "value": "TOXIC"}]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "valueNode", {"value": "정상 메시지로 확인되었습니다"}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "toxic"),
        edge("e5", "n5", "n7"),
        edge("e6", "n4", "n6", "else"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
    ],
)

# ── 28. 매일 랜덤 레시피 텔레그램 발송 ─────────────────────────────────────
tpl28 = FlowGraph(
    title="매일 랜덤 레시피 텔레그램 발송",
    description="매일 정해진 시간에 AI가 새로운 레시피를 하나 생성해 텔레그램으로 보낸다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 8 * * *"}),
        node("n2", "promptNode", {"userPrompt": "오늘 시도해볼 만한 간단한 요리 레시피를 하나 골라서 재료와 조리 순서를 정리해줘"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 매일 새로운 레시피를 추천하는 요리 어시스턴트다"}),
        node("n4", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n5", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 29. 인보이스 데이터 추출 → 사람 검증 → 저장/반려 ───────────────────────
tpl29 = FlowGraph(
    title="인보이스 데이터 추출 및 사람 검증",
    description="인보이스 PDF에서 AI가 핵심 항목을 추출하고, 사람이 검증한 뒤에만 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 인보이스에서 업체명, 총액, 발행일을 JSON 형식으로 추출해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 인보이스에서 데이터를 정확히 추출하는 전문가다"}),
        node("n6", "humanApprovalNode", {"message": "아래 추출된 인보이스 데이터가 정확한지 확인 후 저장할까요?"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "pythonNode", {"code": "output_data = '검증 실패로 인보이스 저장이 반려되었습니다.'"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7", "approved"),
        edge("e7", "n7", "n9"),
        edge("e8", "n6", "n8", "rejected"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
    ],
)

# ── 30. 구글시트 신규 리드 AI 자격 평가 ────────────────────────────────────
tpl30 = FlowGraph(
    title="구글시트 신규 리드 자격 평가",
    description="정기적으로 시트의 신규 리드를 가져와 AI로 Hot/Warm/Cold 등급을 매기고 상태를 업데이트한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 9 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 리드 정보를 보고 'Hot', 'Warm', 'Cold' 중 하나로 등급을 매겨줘. 등급만 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 영업 리드의 구매 가능성을 평가하는 전문가다"}),
        node("n7", "httpRequestNode", {"method": "PUT", "url": PLACEHOLDER_URL}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n4", "n8", "done"),
    ],
)

# ── 31. AI 트윗 생성 및 게시 ────────────────────────────────────────────────
tpl31 = FlowGraph(
    title="AI 트윗 생성 및 게시",
    description="주제를 입력하면 AI가 트윗 초안을 작성해 바로 게시한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "트윗 주제", "testValue": "신제품 출시 소식"}),
        node("n3", "promptNode", {"userPrompt": "이 주제로 280자 이내의 임팩트 있는 트윗 문구를 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 소셜 미디어 카피라이터다"}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 32. 긍정 피드백만 골라 Notion에 저장 ────────────────────────────────────
tpl32 = FlowGraph(
    title="긍정 피드백 Notion 저장",
    description="들어온 피드백 중 긍정적인 것만 걸러서 Notion 테이블에 저장한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/feedback-received"}),
        node("n2", "promptNode", {"userPrompt": "이 피드백이 긍정적인지 판별해줘. 긍정적이면 정확히 'POSITIVE', 아니면 정확히 'OTHER'라고만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 피드백의 긍정 여부를 판별하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [{"id": "positive", "operator": "Contains", "value": "POSITIVE"}]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "valueNode", {"value": "긍정 피드백이 아니라 저장하지 않았습니다"}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "positive"),
        edge("e5", "n5", "n7"),
        edge("e6", "n4", "n6", "else"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
    ],
)

# ── 33. Slack 고객 문의 감성 추적 및 긴급 알림 ─────────────────────────────
tpl33 = FlowGraph(
    title="Slack 고객 문의 감성 추적",
    description="고객 문의의 감성을 분석해 부정적인 문의는 슬랙으로 긴급 알린다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/support-ticket-new"}),
        node("n2", "promptNode", {"userPrompt": "이 고객 문의의 감성을 판별해줘. 반드시 '부정', '중립', '긍정' 중 하나로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 문의의 감성을 분석하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [{"id": "negative", "operator": "Contains", "value": "부정"}]}),
        node("n5", "slackNode", {"channel": "#support-urgent", "message": "부정적인 고객 문의가 접수되었습니다. 우선 대응이 필요합니다"}),
        node("n6", "valueNode", {"value": "일반 문의로 정상 처리되었습니다"}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "negative"),
        edge("e5", "n5", "n7"),
        edge("e6", "n4", "n6", "else"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
    ],
)

# ── 34. 브랜드 톤앤매너 블로그 포스트 자동 생성 ────────────────────────────
tpl34 = FlowGraph(
    title="브랜드 톤앤매너 블로그 포스트 생성",
    description="키워드를 입력하면 AI가 브랜드 톤앤매너에 맞는 블로그 글을 작성해 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "블로그 주제 키워드", "testValue": "친환경 생활 습관"}),
        node("n3", "promptNode", {"userPrompt": "이 키워드로 친근하고 신뢰감 있는 브랜드 톤으로 블로그 포스트를 작성해줘. 제목과 본문을 포함해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 브랜드의 톤앤매너를 지키는 콘텐츠 작가다"}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 35. 스키마 설명만으로 SQL 쿼리 생성 ────────────────────────────────────
tpl35 = FlowGraph(
    title="스키마 기반 SQL 쿼리 생성 어시스턴트",
    description="테이블 스키마 설명과 자연어 질문을 주면 AI가 SQL 쿼리를 생성해준다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "테이블 스키마와 원하는 조회 내용", "testValue": "users(id, name, email, created_at) / 최근 7일간 신규 가입한 사용자 수를 알고 싶어"}),
        node("n3", "promptNode", {"userPrompt": "위 스키마를 참고해서 요청 내용에 맞는 SQL 쿼리를 작성해줘. 쿼리와 짧은 설명만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 스키마만 보고 정확한 SQL 쿼리를 작성하는 데이터 엔지니어다"}),
        node("n5", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 36. Airtable 지원서 자동 심사 ──────────────────────────────────────────
tpl36 = FlowGraph(
    title="Airtable 지원서 자동 심사",
    description="접수된 지원서를 AI가 자격 요건에 따라 심사해 Airtable의 합격/불합격 상태를 갱신한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "지원서 내용", "testValue": "이름: 홍길동 / 경력: 2년 / 보유기술: Python, SQL"}),
        node("n3", "promptNode", {"userPrompt": "이 지원서가 자격 요건(경력 1년 이상, Python 가능)을 충족하는지 판단해줘. 충족하면 정확히 'QUALIFIED', 아니면 정확히 'REJECTED'라고만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 지원서를 심사하는 채용 담당자다"}),
        node("n5", "conditionNode", {"rules": [{"id": "qualified", "operator": "Contains", "value": "QUALIFIED"}]}),
        node("n6", "httpRequestNode", {"method": "PUT", "url": PLACEHOLDER_URL}),
        node("n7", "httpRequestNode", {"method": "PUT", "url": PLACEHOLDER_URL}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "qualified"),
        edge("e6", "n6", "n8"),
        edge("e7", "n5", "n7", "else"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 37. 영업 미팅 준비 브리핑 → 카카오톡 발송 ──────────────────────────────
tpl37 = FlowGraph(
    title="영업 미팅 준비 브리핑 카카오톡 발송",
    description="미팅 상대 정보를 조회해 AI가 미팅 준비 브리핑을 작성하고 카카오톡으로 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "미팅 상대 회사명 또는 정보 URL", "testValue": "example-company.com"}),
        node("n3", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n4", "promptNode", {"userPrompt": "위 회사 정보를 참고해서 영업 미팅 전 확인하면 좋을 핵심 브리핑을 작성해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 영업 담당자를 위한 미팅 준비를 돕는 어시스턴트다"}),
        node("n6", "kakaoNode", {"accessToken": "", "receiver": ""}),
        node("n7", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 38. 채용 공고 작성 및 사람 승인 후 게시 ────────────────────────────────
tpl38 = FlowGraph(
    title="채용 공고 작성 및 승인 게시",
    description="직무 요건을 주면 AI가 채용 공고 초안을 작성하고, 사람이 승인하면 게시한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "직무 및 요건", "testValue": "백엔드 개발자, Python/FastAPI 경험 2년 이상"}),
        node("n3", "promptNode", {"userPrompt": "이 직무 요건으로 매력적인 채용 공고 초안을 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 채용 공고를 작성하는 HR 담당자다"}),
        node("n5", "humanApprovalNode", {"message": "아래 채용 공고 초안을 이대로 게시할까요?"}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "pythonNode", {"code": "output_data = '채용 공고 게시가 취소되었습니다.'"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "approved"),
        edge("e6", "n6", "n8"),
        edge("e7", "n5", "n7", "rejected"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 39. 문서 템플릿 자동 채움(빈 필드 분석 → AI가 값 생성 → 파일에 채워넣기) ─
tpl39 = FlowGraph(
    title="계약서 템플릿 자동 채움",
    description="템플릿 파일의 빈 필드를 분석하고, 사용자가 준 정보를 바탕으로 AI가 값을 채워 문서를 완성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "templateAnalyzerNode", {"template_path": "uploads/contract_template.hwp"}),
        node("n3", "dynamicInputNode", {"inputLabel": "계약 정보(상대방명/금액/계약일 등)", "testValue": "상대방: 주식회사 예시 / 금액: 5,000,000원 / 계약일: 2026-08-01"}),
        node("n4", "promptNode", {"userPrompt": "위 템플릿의 빈 필드 목록과 사용자가 준 정보를 참고해서, 각 필드에 맞는 값을 JSON으로 채워줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 문서 템플릿의 빈 필드를 정확히 채우는 전문가다"}),
        node("n6", "fileModifierNode", {"template_path": "uploads/contract_template.hwp"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 40. 이력서 이미지/PDF에서 구조화 데이터 추출 후 저장 ────────────────────
tpl40 = FlowGraph(
    title="이력서 구조화 데이터 추출 및 저장",
    description="이력서 파일에서 인적사항/경력/기술스택을 AI가 구조화된 JSON으로 추출해 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 이력서에서 이름, 연락처, 경력, 기술 스택을 JSON 형식으로 추출해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서에서 데이터를 정확히 추출하는 전문가다"}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 41. 표 형태 문서를 CSV로 변환 ───────────────────────────────────────────
tpl41 = FlowGraph(
    title="문서 내 표 데이터 CSV 변환",
    description="문서 안의 표 형태 데이터를 AI가 CSV 텍스트로 변환하고, 빈 줄을 정리해 반환한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 문서 안의 표 형태 데이터를 헤더를 포함한 CSV 형식 텍스트로 변환해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 문서의 표 데이터를 CSV로 변환하는 전문가다"}),
        node("n6", "pythonNode", {"code": "lines = [l for l in str(input_data).split(chr(10)) if l.strip()]\noutput_data = chr(10).join(lines)"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 42. 인보이스 데이터 추출(승인 없이 바로 저장) ──────────────────────────
tpl42 = FlowGraph(
    title="인보이스 자동 추출 및 저장",
    description="인보이스에서 업체명/총액/발행일/품목을 AI가 추출해 파싱한 뒤 바로 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 인보이스에서 업체명, 총액, 발행일, 품목 리스트를 JSON으로 추출해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 인보이스에서 데이터를 정확히 추출하는 전문가다"}),
        node("n6", "jsonParserNode", {"mode": "parse"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
    ],
)

# ── 43. URL 콘텐츠를 마크다운으로 변환하고 링크 목록 추출 ──────────────────
tpl43 = FlowGraph(
    title="웹페이지 마크다운 변환 및 링크 추출",
    description="URL을 주면 페이지를 크롤링해 마크다운으로 정리하고 주요 링크 목록도 함께 뽑는다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "변환할 웹페이지 URL", "testValue": "https://example.com/article"}),
        node("n3", "webCrawlerNode", {"url": ""}),
        node("n4", "promptNode", {"userPrompt": "위 크롤링한 페이지 내용을 마크다운 형식으로 정리하고, 포함된 주요 링크 목록도 별도로 뽑아줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 웹페이지를 깔끔한 마크다운으로 정리하는 전문가다"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 44. CSV 개인정보(PII) 자동 마스킹 ───────────────────────────────────────
tpl44 = FlowGraph(
    title="CSV 개인정보 자동 마스킹",
    description="CSV 데이터에서 이름/이메일/전화번호 등 개인정보를 AI가 찾아 마스킹한 뒤 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 CSV 데이터에서 이름, 이메일, 전화번호 등 개인정보를 찾아 ***로 마스킹한 CSV를 다시 출력해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 개인정보를 정확히 식별해 마스킹하는 전문가다"}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 45. 은행 거래내역서 이미지 → 마크다운 표 변환 ──────────────────────────
tpl45 = FlowGraph(
    title="은행 거래내역서 마크다운 변환",
    description="은행 거래내역서 파일 내용을 AI가 날짜/적요/금액 컬럼의 마크다운 표로 변환한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 은행 거래내역서 내용을 날짜/적요/금액 컬럼이 있는 마크다운 표로 변환해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 거래내역서를 정확한 표로 정리하는 전문가다"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 46. 회의 녹취 파일 → 요약 및 액션 아이템 정리 → 저장 ──────────────────
tpl46 = FlowGraph(
    title="회의 녹취 요약 및 액션 아이템 저장",
    description="회의 녹취/기록 파일을 AI가 핵심 요약과 액션 아이템으로 정리해 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 회의록 내용을 핵심 요약과 액션 아이템(담당자/기한 포함) 목록으로 정리해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 회의록을 요약하고 액션 아이템을 정리하는 비서다"}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 47. GitHub API 문서 기반 Q&A 챗봇 ──────────────────────────────────────
tpl47 = FlowGraph(
    title="API 문서 기반 Q&A 챗봇",
    description="API 문서 내용을 참고해서 개발자의 질문에 답변하는 챗봇.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "dynamicInputNode", {"inputLabel": "API 관련 질문", "testValue": "인증은 어떤 방식으로 하나요?"}),
        node("n5", "promptNode", {"userPrompt": "위 API 문서 내용을 참고해서 질문에 정확하게 답변해줘. 문서에 없으면 '문서에서 확인할 수 없습니다'라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 API 문서를 바탕으로 답변하는 개발자 지원 어시스턴트다"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 48. 영화 추천 데이터 비서 챗봇 ──────────────────────────────────────────
tpl48 = FlowGraph(
    title="영화 추천 데이터 비서 챗봇",
    description="DB에서 평점 높은 영화 목록을 조회해두고, 사용자 취향에 맞는 영화를 추천한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "databaseNode", {"connectionString": PLACEHOLDER_URL, "query": "SELECT title, genre, rating FROM movies ORDER BY rating DESC LIMIT 200"}),
        node("n3", "dynamicInputNode", {"inputLabel": "원하는 영화 취향이나 질문", "testValue": "잔잔한 힐링 영화 추천해줘"}),
        node("n4", "promptNode", {"userPrompt": "위 영화 목록을 참고해서 사용자 취향에 맞는 영화를 2~3개 추천하고 이유를 설명해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 영화 취향에 맞게 추천해주는 큐레이터다"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 49. 사내 복리후생 안내 챗봇 ─────────────────────────────────────────────
tpl49 = FlowGraph(
    title="사내 복리후생 안내 챗봇",
    description="사내 복리후생 문서를 참고해서 직원의 질문에 답변하는 챗봇.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "valueNode", {"file_path": ""}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "dynamicInputNode", {"inputLabel": "복리후생 관련 질문", "testValue": "경조사 휴가는 며칠인가요?"}),
        node("n5", "promptNode", {"userPrompt": "위 복리후생 문서 내용을 참고해서 질문에 답변해줘. 문서에 없으면 '인사팀에 문의해주세요'라고 답해."}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 사내 복리후생에 정통한 HR 상담원이다"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 50. 보안 알림 심각도 판별 → 심각하면 사람 승인 후 차단 조치 ────────────
tpl50 = FlowGraph(
    title="보안 알림 심각도 판별 및 승인 기반 차단",
    description="보안 알림의 심각도를 AI가 판별해, 심각한 경우에만 사람 승인을 거쳐 차단 조치를 실행한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/siem-alert"}),
        node("n2", "promptNode", {"userPrompt": "이 보안 알림의 심각도를 판별해줘. 심각하면 정확히 'CRITICAL', 아니면 정확히 'NORMAL'이라고만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 보안 알림의 심각도를 판별하는 SOC 분석가다"}),
        node("n4", "conditionNode", {"rules": [{"id": "critical", "operator": "Contains", "value": "CRITICAL"}]}),
        node("n5", "humanApprovalNode", {"message": "심각한 보안 알림입니다. 자동 차단 조치를 진행할까요?"}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "valueNode", {"value": "차단은 보류되고 모니터링만 계속됩니다"}),
        node("n8", "valueNode", {"value": "정상 알림으로 기록되었습니다"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "critical"),
        edge("e5", "n5", "n6", "approved"),
        edge("e6", "n6", "n9"),
        edge("e7", "n5", "n7", "rejected"),
        edge("e8", "n7", "n9"),
        edge("e9", "n4", "n8", "else"),
        edge("e10", "n8", "n9"),
        edge("e11", "n9", "n10"),
    ],
)

# ── 51. 신규 고객 온보딩 안내 작성 및 승인 발송 ────────────────────────────
tpl51 = FlowGraph(
    title="신규 고객 온보딩 안내 승인 발송",
    description="신규 고객 정보를 바탕으로 온보딩 안내 초안을 작성하고, 승인 후 이메일로 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "신규 고객 정보", "testValue": "회사명: 예시주식회사 / 담당자: 홍길동 / 이메일: hong@example.com"}),
        node("n3", "promptNode", {"userPrompt": "이 신규 고객을 위한 온보딩 환영 메시지와 필요 서류 안내 초안을 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 온보딩을 담당하는 어시스턴트다"}),
        node("n5", "humanApprovalNode", {"message": "아래 온보딩 안내를 이대로 승인 후 발송할까요?"}),
        node("n6", "emailNode", {"toEmail": "customer@example.com", "subject": "온보딩 안내"}),
        node("n7", "pythonNode", {"code": "output_data = '온보딩 안내 발송이 취소되었습니다.'"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "approved"),
        edge("e6", "n6", "n8"),
        edge("e7", "n5", "n7", "rejected"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 52. 리드 문의 긴급도 분류 후 대응 경로 라우팅 ──────────────────────────
tpl52 = FlowGraph(
    title="리드 문의 긴급도 분류 및 라우팅",
    description="신규 리드 문의의 긴급도를 AI가 분류해 즉시 응대 또는 일반 후속 경로로 나눈다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/lead-new"}),
        node("n2", "promptNode", {"userPrompt": "이 리드 문의가 '즉시 응대 필요'한지 '일반 문의'인지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 영업 리드의 긴급도를 판별하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [{"id": "urgent", "operator": "Contains", "value": "즉시 응대 필요"}]}),
        node("n5", "slackNode", {"channel": "#sales-urgent", "message": "즉시 응대가 필요한 리드 문의가 접수되었습니다"}),
        node("n6", "emailNode", {"toEmail": "sales@example.com", "subject": "신규 리드 후속 안내"}),
        node("n7", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n8", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "urgent"),
        edge("e5", "n5", "n7"),
        edge("e6", "n4", "n6", "else"),
        edge("e7", "n6", "n7"),
        edge("e8", "n7", "n8"),
    ],
)

# ── 53. 이커머스 문의 메일 유형 분류 후 담당 팀 라우팅 ─────────────────────
tpl53 = FlowGraph(
    title="이커머스 문의 메일 유형 분류 라우팅",
    description="이커머스 고객 문의 메일을 주문/배송/환불 문의로 분류해 담당 팀으로 라우팅한다.",
    nodes=[
        node("n1", "webhookNode", {"method": "POST", "path": "/ecommerce-email"}),
        node("n2", "promptNode", {"userPrompt": "이 문의가 '주문문의', '배송문의', '환불문의' 중 어디에 해당하는지 그 단어로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 이커머스 고객 문의를 유형별로 분류하는 어시스턴트다"}),
        node("n4", "conditionNode", {"rules": [
            {"id": "order", "operator": "Contains", "value": "주문문의"},
            {"id": "shipping", "operator": "Contains", "value": "배송문의"},
        ]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "order"),
        edge("e5", "n5", "n8"),
        edge("e6", "n4", "n6", "shipping"),
        edge("e7", "n6", "n8"),
        edge("e8", "n4", "n7", "else"),
        edge("e9", "n7", "n8"),
        edge("e10", "n8", "n9"),
    ],
)

# ── 54. 구독 신청 스팸 여부 판별 후 등록/거부 ──────────────────────────────
tpl54 = FlowGraph(
    title="이메일 구독 신청 스팸 판별 및 등록",
    description="구독 신청자 정보의 스팸 여부를 AI가 판별해 정상일 때만 구독자 명단에 추가한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "구독 신청자 정보", "testValue": "이름: 홍길동 / 이메일: hong@example.com"}),
        node("n3", "promptNode", {"userPrompt": "이 신청 정보가 스팸/봇으로 의심되는지 판별해줘. 정상이면 정확히 'VALID', 스팸이면 정확히 'SPAM'이라고만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 구독 신청의 스팸 여부를 판별하는 어시스턴트다"}),
        node("n5", "conditionNode", {"rules": [{"id": "valid", "operator": "Contains", "value": "VALID"}]}),
        node("n6", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n7", "valueNode", {"value": "스팸으로 판단되어 등록하지 않았습니다"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "valid"),
        edge("e6", "n6", "n8"),
        edge("e7", "n5", "n7", "else"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 55. 해커뉴스 채용 공고 수집 및 정리 ────────────────────────────────────
tpl55 = FlowGraph(
    title="해커뉴스 채용 공고 자동 수집 및 정리",
    description="정기적으로 채용 공고 목록을 가져와 각각 AI로 요약하고 기술 스택을 뽑아 저장한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 9 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 채용 공고를 2문장으로 요약하고, 요구되는 기술 스택을 쉼표로 구분해서 뽑아줘"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 채용 공고를 요약하고 정리하는 어시스턴트다"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": PLACEHOLDER_URL}),
        node("n8", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n4", "n8", "done"),
    ],
)

# ── 56. 경쟁사 모니터링 결과 요약 후 슬랙 전달 ─────────────────────────────
tpl56 = FlowGraph(
    title="경쟁사 언급 모니터링 및 슬랙 다이제스트",
    description="정기적으로 경쟁사 관련 게시물을 가져와 AI로 요약해 슬랙으로 전달한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 8 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode", {}),
        node("n5", "promptNode", {"userPrompt": "이 게시물이 우리 경쟁사와 관련 있는지 판단하고, 관련 있으면 핵심 내용을 한 줄로 요약해줘. 관련 없으면 정확히 'SKIP'이라고만 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 경쟁사 언급을 모니터링하고 요약하는 애널리스트다"}),
        node("n7", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n8", "slackNode", {"channel": "#competitor-watch", "message": "경쟁사 관련 새 게시물이 감지되었습니다"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode", {}),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8", "else"),
        edge("e8", "n8", "n9"),
        edge("e9", "n7", "n9", "skip"),
        edge("e10", "n4", "n10", "done"),
    ],
)

# ── 57. 유튜브 영상 AI 요약 후 디스코드 게시 ───────────────────────────────
tpl57 = FlowGraph(
    title="유튜브 영상 AI 요약 디스코드 게시",
    description="유튜브 영상 URL을 주면 내용을 AI로 요약해 디스코드 채널에 게시한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "유튜브 영상 URL", "testValue": "https://www.youtube.com/watch?v=example"}),
        node("n3", "httpRequestNode", {"method": "GET", "url": PLACEHOLDER_URL}),
        node("n4", "promptNode", {"userPrompt": "이 영상 내용을 핵심 3줄로 요약해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 영상 내용을 간결하게 요약하는 어시스턴트다"}),
        node("n6", "discordNode", {"botToken": "", "channelId": ""}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 58. 채용 포지션 기반 인터뷰 질문지 자동 생성 ───────────────────────────
tpl58 = FlowGraph(
    title="인터뷰 질문지 자동 생성",
    description="채용 포지션 정보를 주면 AI가 그에 맞는 인터뷰 질문 목록을 생성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "채용 포지션 및 요건", "testValue": "프론트엔드 개발자, React 경험 2년 이상"}),
        node("n3", "promptNode", {"userPrompt": "이 포지션에 맞는 기술/인성 인터뷰 질문을 5개 생성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 채용 인터뷰 질문지를 작성하는 HR 담당자다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 59. 환불 요청 자동 검토 및 승인 ─────────────────────────────────────
tpl59 = FlowGraph(
    title="환불 요청 자동 검토 및 승인",
    description="환불 요청 금액을 판단해 고액은 사람 승인을, 소액은 자동 처리를 거쳐 환불을 진행한다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 환불 요청의 금액이 10만원을 초과하는지 판단해서 '고액' 또는 '소액' 중 하나로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 환불 요청 금액 기준을 심사하는 CS 담당자다"}),
        node("n4", "conditionNode", {"rules": [{"id": "high", "operator": "Contains", "value": "고액"}]}),
        node("n5", "humanApprovalNode"),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/refunds/approve"}),
        node("n7", "valueNode", {"value": "환불 요청이 반려되었습니다"}),
        node("n8", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/refunds/auto-approve"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "high"),
        edge("e5", "n5", "n6", "approved"),
        edge("e6", "n5", "n7", "rejected"),
        edge("e7", "n4", "n8", "else"),
        edge("e8", "n6", "n9"),
        edge("e9", "n7", "n9"),
        edge("e10", "n8", "n9"),
        edge("e11", "n9", "n10"),
    ],
)

# ── 60. 휴가 신청 승인 알림 ─────────────────────────────────────────────
tpl60 = FlowGraph(
    title="휴가 신청 승인 알림",
    description="휴가 신청이 잔여 연차를 초과하면 팀장 승인을 거치고, 정상 범위면 바로 승인 안내 메일을 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "휴가 신청 내용(신청자, 기간, 잔여 연차)", "testValue": "홍길동, 8/1~8/3(3일), 잔여 연차 2일"}),
        node("n3", "promptNode", {"userPrompt": "이 휴가 신청이 잔여 연차를 초과하는지 판단해서 '초과' 또는 '정상' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 휴가 신청의 잔여 연차를 검토하는 인사 담당자다"}),
        node("n5", "conditionNode", {"rules": [{"id": "over", "operator": "Contains", "value": "초과"}]}),
        node("n6", "humanApprovalNode"),
        node("n7", "emailNode", {"toEmail": "employee@example.com", "subject": "휴가 신청이 승인되었습니다"}),
        node("n8", "valueNode", {"value": "휴가 신청이 반려되었습니다(연차 초과)"}),
        node("n9", "emailNode", {"toEmail": "employee@example.com", "subject": "휴가 신청이 승인되었습니다(연차 범위 내)"}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "over"),
        edge("e6", "n6", "n7", "approved"),
        edge("e7", "n6", "n8", "rejected"),
        edge("e8", "n5", "n9", "else"),
        edge("e9", "n7", "n10"),
        edge("e10", "n8", "n10"),
        edge("e11", "n9", "n10"),
        edge("e12", "n10", "n11"),
    ],
)

# ── 61. 지출 결의서 금액별 승인 라우팅 ───────────────────────────────────
tpl61 = FlowGraph(
    title="지출 결의서 금액별 승인 라우팅",
    description="지출 결의서 금액이 기준을 넘으면 사람 승인을, 소액이면 자동 승인을 거친 뒤 처리 결과를 알린다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "지출 결의서 내용(항목, 금액)", "testValue": "팀 회식비 350,000원"}),
        node("n3", "promptNode", {"userPrompt": "이 지출 결의서 금액이 30만원을 초과하는지 판단해서 '고액' 또는 '소액' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 지출 결의서 금액 기준을 검토하는 회계 담당자다"}),
        node("n5", "conditionNode", {"rules": [{"id": "high", "operator": "Contains", "value": "고액"}]}),
        node("n6", "humanApprovalNode"),
        node("n7", "valueNode", {"value": "지출 결의서가 자동 승인되었습니다(소액)"}),
        node("n8", "slackNode", {"channel": "#finance", "message": "지출 결의서가 승인 처리되었습니다"}),
        node("n9", "valueNode", {"value": "지출 결의서가 반려되었습니다"}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "high"),
        edge("e6", "n5", "n7", "else"),
        edge("e7", "n6", "n8", "approved"),
        edge("e8", "n6", "n9", "rejected"),
        edge("e9", "n7", "n10"),
        edge("e10", "n8", "n10"),
        edge("e11", "n9", "n10"),
        edge("e12", "n10", "n11"),
    ],
)

# ── 62. 신규 벤더 등록 컴플라이언스 검토 후 승인 ─────────────────────────
tpl62 = FlowGraph(
    title="신규 벤더 등록 컴플라이언스 검토 후 승인",
    description="신규 벤더 정보에 컴플라이언스 위험이 있으면 사람 승인을 거치고, 정상이면 자동으로 등록한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "신규 벤더 정보", "testValue": "ABC상사, 사업자번호 123-45-67890, 해외법인"}),
        node("n3", "promptNode", {"userPrompt": "이 벤더 정보에 컴플라이언스 위험 요소(제재 대상국, 서류 누락 등)가 있는지 판단해서 '위험' 또는 '정상' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 신규 벤더 등록 시 컴플라이언스를 검토하는 담당자다"}),
        node("n5", "conditionNode", {"rules": [{"id": "risk", "operator": "Contains", "value": "위험"}]}),
        node("n6", "humanApprovalNode"),
        node("n7", "databaseNode", {"connectionString": "postgresql://user:pass@localhost/erp", "query": "INSERT INTO vendors (name, status) VALUES ('vendor', 'approved')"}),
        node("n8", "valueNode", {"value": "벤더 등록이 반려되었습니다(컴플라이언스 위험)"}),
        node("n9", "databaseNode", {"connectionString": "postgresql://user:pass@localhost/erp", "query": "INSERT INTO vendors (name, status) VALUES ('vendor', 'approved')"}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "risk"),
        edge("e6", "n6", "n7", "approved"),
        edge("e7", "n6", "n8", "rejected"),
        edge("e8", "n5", "n9", "else"),
        edge("e9", "n7", "n10"),
        edge("e10", "n8", "n10"),
        edge("e11", "n9", "n10"),
        edge("e12", "n10", "n11"),
    ],
)

# ── 63. 소셜 게시물 발행 전 브랜드 검수 승인 ─────────────────────────────
tpl63 = FlowGraph(
    title="소셜 게시물 발행 전 브랜드 검수 승인",
    description="SNS 게시물 초안을 브랜드 가이드라인에 맞춰 다듬고, 사람 승인을 받은 뒤에만 게시한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "게시 예정 SNS 캡션 초안", "testValue": "이번 여름 신제품 런칭! 지금 바로 확인하세요 #신상품"}),
        node("n3", "promptNode", {"userPrompt": "이 캡션이 브랜드 가이드라인(과도한 이모지 금지, 존댓말 사용)에 맞는지 검토하고 필요하면 다듬어서 최종본을 제시해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 SNS 게시물의 브랜드 톤앤매너를 검수하는 마케팅 담당자다"}),
        node("n5", "humanApprovalNode"),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/sns/publish"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 64. 재고 부족 시 발주 승인 워크플로우 ────────────────────────────────
tpl64 = FlowGraph(
    title="재고 부족 시 발주 승인 워크플로우",
    description="매일 재고를 점검해 재주문 기준 미만이면 발주 승인을 요청하고, 승인 시 발주를 진행한다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 7 * * *"}),
        node("n2", "databaseNode", {"connectionString": "postgresql://user:pass@localhost/inventory", "query": "SELECT sku, quantity, reorder_point FROM stock"}),
        node("n3", "promptNode", {"userPrompt": "이 재고 데이터를 보고 재주문 기준(reorder_point) 미만인 품목이 있는지 판단해서, 있으면 '발주 필요'라고만 답하고 없으면 정확히 '정상'이라고만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 재고 데이터를 검토하는 구매 담당자다"}),
        node("n5", "conditionNode", {"rules": [{"id": "need", "operator": "Contains", "value": "발주 필요"}]}),
        node("n6", "humanApprovalNode"),
        node("n7", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/purchase-orders"}),
        node("n8", "valueNode", {"value": "발주가 반려되었습니다"}),
        node("n9", "valueNode", {"value": "재고가 정상 범위입니다"}),
        node("n10", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n11", "slackNode", {"channel": "#purchasing", "message": "재고 점검 결과가 처리되었습니다"}),
        node("n12", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "need"),
        edge("e6", "n6", "n7", "approved"),
        edge("e7", "n6", "n8", "rejected"),
        edge("e8", "n5", "n9", "else"),
        edge("e9", "n7", "n10"),
        edge("e10", "n8", "n10"),
        edge("e11", "n9", "n10"),
        edge("e12", "n10", "n11"),
        edge("e13", "n11", "n12"),
    ],
)

# ── 65. 사내 IT 헬프데스크 챗봇 ──────────────────────────────────────────
tpl65 = FlowGraph(
    title="사내 IT 헬프데스크 챗봇",
    description="사내 IT 문의를 받아 지식베이스를 근거로 해결 방법을 안내한다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 IT 문의에 대해 사내 IT 지식베이스를 참고해서 해결 방법을 안내해줘"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 사내 IT 헬프데스크 상담원이다"}),
        node("n4", "kakaoNode", {"receiver": ""}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 66. 계약서 조항 Q&A 어시스턴트 ───────────────────────────────────────
tpl66 = FlowGraph(
    title="계약서 조항 Q&A 어시스턴트",
    description="계약서 조항에 대한 질문에 근거를 들어 답변한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "계약서 조항 관련 질문", "testValue": "이 계약서에서 중도 해지 위약금 조항이 어떻게 되나요?"}),
        node("n3", "promptNode", {"userPrompt": "이 질문에 대해 계약서 조항을 근거로 답변해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 계약서 조항을 해석해주는 법무 어시스턴트다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 67. 주문 상태 조회 챗봇 ──────────────────────────────────────────────
tpl67 = FlowGraph(
    title="주문 상태 조회 챗봇",
    description="주문번호로 상태를 조회해 고객 질문에 자연스럽게 답변한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "주문번호 및 질문", "testValue": "주문번호 20260716-001 배송 언제 오나요?"}),
        node("n3", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/orders/status"}),
        node("n4", "promptNode", {"userPrompt": "이 주문 상태 데이터를 바탕으로 고객 질문에 자연스럽게 답변해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 주문 상태를 안내하는 고객 상담원이다"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 68. 제품 매뉴얼 트러블슈팅 어시스턴트 ────────────────────────────────
tpl68 = FlowGraph(
    title="제품 매뉴얼 트러블슈팅 어시스턴트",
    description="증상을 입력받아 제품 매뉴얼을 근거로 해결 방법을 단계별로 안내한다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 증상에 대해 제품 매뉴얼을 참고해서 해결 방법을 단계별로 안내해줘"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 제품 매뉴얼 기반 트러블슈팅을 안내하는 지원 엔지니어다"}),
        node("n4", "slackNode", {"channel": "#support-logs", "message": "트러블슈팅 문의가 처리되었습니다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 69. 인사 정책 안내 카카오톡 봇 ───────────────────────────────────────
tpl69 = FlowGraph(
    title="인사 정책 안내 카카오톡 봇",
    description="사내 인사 정책 문의에 대해 정책 문서를 근거로 답변한다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 질문에 대해 사내 인사 정책 문서를 근거로 답변해줘"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 사내 인사 정책을 안내하는 HR 챗봇이다"}),
        node("n4", "kakaoNode", {"receiver": ""}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 70. 코드베이스 아키텍처 Q&A 봇 ───────────────────────────────────────
tpl70 = FlowGraph(
    title="코드베이스 아키텍처 Q&A 봇",
    description="코드베이스 구조에 대한 질문에 아키텍처 문서를 근거로 답변한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "코드베이스 아키텍처 관련 질문", "testValue": "인증 모듈은 어떤 구조로 되어 있나요?"}),
        node("n3", "promptNode", {"userPrompt": "이 질문에 대해 코드베이스 아키텍처 문서를 근거로 답변해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 코드베이스 아키텍처를 설명하는 시니어 개발자다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 71. 제품 출시 보도자료 자동 작성 ─────────────────────────────────────
tpl71 = FlowGraph(
    title="제품 출시 보도자료 자동 작성",
    description="제품 출시 정보를 바탕으로 언론 배포용 보도자료를 작성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "제품 출시 정보(제품명, 핵심 기능, 출시일)", "testValue": "스마트워치 X, 심박수/수면 분석, 2026-08-01 출시"}),
        node("n3", "promptNode", {"userPrompt": "이 정보를 바탕으로 언론 배포용 보도자료를 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 제품 출시 보도자료를 작성하는 PR 담당자다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 72. 이커머스 상품 상세페이지 카피 생성 ───────────────────────────────
tpl72 = FlowGraph(
    title="이커머스 상품 상세페이지 카피 생성",
    description="상품 스펙을 바탕으로 매력적인 상세페이지 카피를 생성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "상품 스펙 및 특징", "testValue": "무선 이어폰, 노이즈캔슬링, 배터리 24시간"}),
        node("n3", "promptNode", {"userPrompt": "이 상품 스펙을 바탕으로 매력적인 상세페이지 카피를 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 이커머스 상세페이지 카피라이터다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 73. 주간 뉴스레터 초안 생성 ──────────────────────────────────────────
tpl73 = FlowGraph(
    title="주간 뉴스레터 초안 생성",
    description="이번 주 발행된 포스트 목록을 바탕으로 뉴스레터 초안을 작성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "이번 주 발행된 포스트 제목과 요약 목록", "testValue": "1. AI 트렌드 정리 2. 신규 기능 안내 3. 팀 인터뷰"}),
        node("n3", "promptNode", {"userPrompt": "이 목록을 바탕으로 인트로와 각 소식 소개가 포함된 뉴스레터 초안을 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 주간 뉴스레터를 작성하는 에디터다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 74. 채용 공고 문구 자동 생성 ─────────────────────────────────────────
tpl74 = FlowGraph(
    title="채용 공고 문구 자동 생성",
    description="채용 직무 요건을 바탕으로 매력적인 채용 공고 문구를 작성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "채용 직무 요건", "testValue": "백엔드 개발자, Python/FastAPI 경험 3년 이상"}),
        node("n3", "promptNode", {"userPrompt": "이 요건을 바탕으로 매력적인 채용 공고 문구를 작성해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 채용 공고를 작성하는 인사 담당자다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 75. 고객 리뷰 기반 FAQ 초안 생성 ─────────────────────────────────────
tpl75 = FlowGraph(
    title="고객 리뷰 기반 FAQ 초안 생성",
    description="고객 리뷰 모음에서 자주 나오는 질문을 뽑아 FAQ 초안으로 정리한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "고객 리뷰 모음", "testValue": "배송이 너무 늦어요 / 사이즈가 작아요 / 교환은 어떻게 하나요"}),
        node("n3", "promptNode", {"userPrompt": "이 리뷰들에서 자주 나오는 질문을 뽑아 FAQ 형식으로 정리해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 리뷰를 분석해 FAQ를 만드는 CS 담당자다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 76. SNS 캡션 다국어 로컬라이징 ───────────────────────────────────────
tpl76 = FlowGraph(
    title="SNS 캡션 다국어 로컬라이징",
    description="한국어 SNS 캡션을 여러 언어로 자연스럽게 로컬라이징한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "원본 SNS 캡션(한국어)", "testValue": "이번 여름, 새로운 컬렉션을 만나보세요!"}),
        node("n3", "promptNode", {"userPrompt": "이 캡션을 영어와 일본어로 각각 자연스럽게 현지화해서 번역해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 SNS 캡션을 다국어로 로컬라이징하는 번역가다"}),
        node("n5", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
    ],
)

# ── 77. PDF 청구서 항목 추출 및 시트 저장 ───────────────────────────────
tpl77 = FlowGraph(
    title="PDF 청구서 항목 추출 및 시트 저장",
    description="청구서 PDF에서 공급자/금액/항목을 추출해 스프레드시트에 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "청구서 PDF 경로", "testValue": "/uploads/invoice_202607.pdf"}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 청구서 내용에서 공급자, 금액, 청구일, 항목을 JSON 형태로 추출해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 청구서에서 정형 데이터를 추출하는 회계 어시스턴트다"}),
        node("n6", "jsonParserNode", {"mode": "parse"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/sheets/invoices"}),
        node("n8", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
    ],
)

# ── 78. 근로계약서 자동 초안 생성 ────────────────────────────────────────
tpl78 = FlowGraph(
    title="근로계약서 자동 초안 생성",
    description="신규 입사자 정보를 근로계약서 템플릿의 빈칸에 채워 초안을 생성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "신규 입사자 정보", "testValue": "이름 김철수, 직무 백엔드 개발자, 입사일 2026-08-01, 연봉 5000만원"}),
        node("n3", "templateAnalyzerNode", {"template_path": "/templates/employment_contract.docx"}),
        node("n4", "promptNode", {"userPrompt": "이 템플릿의 빈칸에 채울 값을 입사자 정보를 바탕으로 JSON으로 만들어줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 근로계약서 초안을 작성하는 인사 담당자다"}),
        node("n6", "fileModifierNode", {"template_path": "/templates/employment_contract.docx"}),
        node("n7", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
    ],
)

# ── 79. 회의록 PDF 결정사항 추출 ─────────────────────────────────────────
tpl79 = FlowGraph(
    title="회의록 PDF 결정사항 추출",
    description="회의록 PDF에서 결정된 사항과 액션 아이템을 추출해 정리한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "회의록 PDF 경로", "testValue": "/uploads/meeting_20260716.pdf"}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 회의록에서 결정된 사항과 액션 아이템을 정리해줘"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 회의록에서 결정사항을 추출하는 어시스턴트다"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 80. 이력서 PDF 표준 포맷 변환 ────────────────────────────────────────
tpl80 = FlowGraph(
    title="이력서 PDF 표준 포맷 변환",
    description="이력서 PDF 내용을 추출해 표준 양식 템플릿의 빈칸에 맞춰 재구성한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "이력서 PDF 경로", "testValue": "/uploads/resume_kim.pdf"}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "templateAnalyzerNode", {"template_path": "/templates/standard_resume.docx"}),
        node("n5", "promptNode", {"userPrompt": "추출된 이력서 내용을 표준 양식의 빈칸에 맞춰 채울 JSON으로 정리해줘"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서를 표준 양식으로 재구성하는 어시스턴트다"}),
        node("n7", "fileModifierNode", {"template_path": "/templates/standard_resume.docx"}),
        node("n8", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8"),
    ],
)

# ── 81. 스캔 영수증 데이터화 및 지출 분류 저장 ───────────────────────────
tpl81 = FlowGraph(
    title="스캔 영수증 데이터화 및 지출 분류 저장",
    description="영수증 내용을 분석해 지출 카테고리를 분류하고 데이터베이스에 저장한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "영수증 이미지 경로 또는 텍스트", "testValue": "스타벅스 강남점, 8,500원, 2026-07-16"}),
        node("n3", "promptNode", {"userPrompt": "이 영수증 내용에서 상호, 금액, 날짜, 지출 카테고리(식비/교통/기타)를 판단해줘"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 영수증을 분석해 지출 카테고리를 분류하는 회계 어시스턴트다"}),
        node("n5", "databaseNode", {"connectionString": "postgresql://user:pass@localhost/expenses", "query": "INSERT INTO expenses (raw_text) VALUES ('receipt')"}),
        node("n6", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
    ],
)

# ── 82. 문서 표준 양식 준수 검사 및 반려 안내 ───────────────────────────
tpl82 = FlowGraph(
    title="문서 표준 양식 준수 검사 및 반려 안내",
    description="제출 문서가 표준 양식을 갖췄는지 검사해 정상 접수 또는 반려 안내 메일을 보낸다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "제출된 문서 경로", "testValue": "/uploads/submitted_form.pdf"}),
        node("n3", "tokenizerNode", {"method": "extract_text"}),
        node("n4", "promptNode", {"userPrompt": "이 문서가 표준 양식(필수 항목: 제목, 작성자, 날짜, 서명)을 모두 갖췄는지 판단해서 '준수' 또는 '미비'로만 답해"}),
        node("n5", "llmNode", {"model": MODEL, "systemPrompt": "너는 제출 문서의 양식 준수 여부를 검토하는 담당자다"}),
        node("n6", "conditionNode", {"rules": [{"id": "ok", "operator": "Contains", "value": "준수"}]}),
        node("n7", "valueNode", {"value": "문서가 정상 접수되었습니다"}),
        node("n8", "valueNode", {"value": "문서 양식이 미비합니다. 필수 항목을 확인해주세요"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "emailNode", {"toEmail": "submitter@example.com", "subject": "문서 접수 결과 안내"}),
        node("n11", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7", "ok"),
        edge("e7", "n6", "n8", "else"),
        edge("e8", "n7", "n9"),
        edge("e9", "n8", "n9"),
        edge("e10", "n9", "n10"),
        edge("e11", "n10", "n11"),
    ],
)

# ── 83. 매일 RSS 피드 관심 주제 다이제스트 ───────────────────────────────
tpl83 = FlowGraph(
    title="매일 RSS 피드 관심 주제 다이제스트",
    description="매일 RSS 피드를 수집해 관심 주제 글만 골라 요약하고 슬랙으로 알린다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 9 * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/rss/recent"}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode"),
        node("n5", "promptNode", {"userPrompt": "이 글이 AI/개발 관련 관심 주제와 관련 있는지 판단하고, 관련 있으면 한 줄로 요약해줘. 관련 없으면 정확히 'SKIP'이라고만 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 RSS 피드에서 관심 주제 글을 골라내는 큐레이터다"}),
        node("n7", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n8", "slackNode", {"channel": "#daily-digest", "message": "오늘의 관심 글이 있습니다"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8", "else"),
        edge("e8", "n8", "n9"),
        edge("e9", "n7", "n9", "skip"),
        edge("e10", "n4", "n10", "done"),
    ],
)

# ── 84. 지원자 이력서 일괄 스크리닝 및 합격자 명단 발송 ─────────────────
tpl84 = FlowGraph(
    title="지원자 이력서 일괄 스크리닝 및 합격자 명단 발송",
    description="매주 신규 지원자 이력서를 일괄 스크리닝해 1차 서류 기준을 충족하면 합격자로 인사팀에 알린다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "0 18 * * 5"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/ats/applicants/recent"}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode"),
        node("n5", "promptNode", {"userPrompt": "이 지원자의 이력서 요약을 보고 서류 기준(3년 이상 경력, 관련 스택 보유)을 충족하는지 판단해서, 충족하면 '합격'이라고만 답하고 아니면 정확히 'SKIP'이라고만 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 이력서를 1차 서류 기준으로 스크리닝하는 채용 담당자다"}),
        node("n7", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n8", "emailNode", {"toEmail": "hr@example.com", "subject": "1차 서류 합격자 알림"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8", "else"),
        edge("e8", "n8", "n9"),
        edge("e9", "n7", "n9", "skip"),
        edge("e10", "n4", "n10", "done"),
    ],
)

# ── 85. 일별 서버 로그 이상탐지 슬랙 알림 ────────────────────────────────
tpl85 = FlowGraph(
    title="일별 서버 로그 이상탐지 슬랙 알림",
    description="주기적으로 서버 로그를 수집해 이상 징후가 있는 항목만 골라 슬랙으로 알린다.",
    nodes=[
        node("n1", "scheduleNode", {"cronExpression": "*/30 * * * *"}),
        node("n2", "httpRequestNode", {"method": "GET", "url": "https://api.example.com/logs/recent"}),
        node("n3", "jsonParserNode", {"mode": "parse"}),
        node("n4", "distributorNode"),
        node("n5", "promptNode", {"userPrompt": "이 로그 라인에 에러나 이상 징후가 있는지 판단해서, 있으면 핵심 내용을 한 줄로 요약해줘. 없으면 정확히 'SKIP'이라고만 답해"}),
        node("n6", "llmNode", {"model": MODEL, "systemPrompt": "너는 서버 로그에서 이상 징후를 탐지하는 SRE 엔지니어다"}),
        node("n7", "conditionNode", {"rules": [{"id": "skip", "operator": "Contains", "value": "SKIP"}]}),
        node("n8", "slackNode", {"channel": "#server-alerts", "message": "이상 징후가 감지되었습니다"}),
        node("n9", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n10", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6"),
        edge("e6", "n6", "n7"),
        edge("e7", "n7", "n8", "else"),
        edge("e8", "n8", "n9"),
        edge("e9", "n7", "n9", "skip"),
        edge("e10", "n4", "n10", "done"),
    ],
)

# ── 86. 고객 문의 채널별 자동 라우팅 ─────────────────────────────────────
tpl86 = FlowGraph(
    title="고객 문의 채널별 자동 라우팅",
    description="고객 문의를 기술/결제/일반으로 분류해 각각 다른 채널로 라우팅한다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 문의 내용을 보고 '기술', '결제', '일반' 중 하나로만 분류해서 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 고객 문의를 담당 부서로 분류하는 라우팅 담당자다"}),
        node("n4", "conditionNode", {"rules": [
            {"id": "tech", "operator": "Contains", "value": "기술"},
            {"id": "billing", "operator": "Contains", "value": "결제"},
        ]}),
        node("n5", "slackNode", {"channel": "#tech-support", "message": "기술 문의가 접수되었습니다"}),
        node("n6", "emailNode", {"toEmail": "billing@example.com", "subject": "결제 문의 접수"}),
        node("n7", "kakaoNode", {"receiver": ""}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "tech"),
        edge("e5", "n4", "n6", "billing"),
        edge("e6", "n4", "n7", "else"),
        edge("e7", "n5", "n8"),
        edge("e8", "n6", "n8"),
        edge("e9", "n7", "n8"),
        edge("e10", "n8", "n9"),
    ],
)

# ── 87. 버그 리포트 심각도 분류 및 이슈 등록 ─────────────────────────────
tpl87 = FlowGraph(
    title="버그 리포트 심각도 분류 및 이슈 등록",
    description="버그 리포트의 심각도를 판별해 우선순위에 맞는 이슈로 등록한다.",
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "버그 리포트 내용", "testValue": "결제 완료 후 주문 내역이 저장되지 않고 500 에러가 발생합니다"}),
        node("n3", "promptNode", {"userPrompt": "이 버그 리포트의 심각도를 판단해서 'critical' 또는 'normal' 중 하나로만 답해"}),
        node("n4", "llmNode", {"model": MODEL, "systemPrompt": "너는 버그 리포트의 심각도를 판별하는 QA 엔지니어다"}),
        node("n5", "conditionNode", {"rules": [{"id": "critical", "operator": "Contains", "value": "critical"}]}),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/issues?priority=urgent"}),
        node("n7", "httpRequestNode", {"method": "POST", "url": "https://api.example.com/issues?priority=normal"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5"),
        edge("e5", "n5", "n6", "critical"),
        edge("e6", "n5", "n7", "else"),
        edge("e7", "n6", "n8"),
        edge("e8", "n7", "n8"),
        edge("e9", "n8", "n9"),
    ],
)

# ── 88. 인바운드 리드 소스별 CRM 라우팅 ──────────────────────────────────
tpl88 = FlowGraph(
    title="인바운드 리드 소스별 CRM 라우팅",
    description="인바운드 리드의 구매 의향을 판별해 hot/cold로 나눠 CRM에 등록하고 영업팀에 알린다.",
    nodes=[
        node("n1", "webhookNode"),
        node("n2", "promptNode", {"userPrompt": "이 리드 정보를 보고 구매 의향이 높은 'hot' 리드인지 낮은 'cold' 리드인지 판단해서 하나로만 답해"}),
        node("n3", "llmNode", {"model": MODEL, "systemPrompt": "너는 인바운드 리드의 품질을 판별하는 영업 담당자다"}),
        node("n4", "conditionNode", {"rules": [{"id": "hot", "operator": "Contains", "value": "hot"}]}),
        node("n5", "httpRequestNode", {"method": "POST", "url": "https://api.crm.example.com/leads/hot"}),
        node("n6", "databaseNode", {"connectionString": "postgresql://user:pass@localhost/crm", "query": "INSERT INTO cold_leads (payload) VALUES ('lead')"}),
        node("n7", "slackNode", {"channel": "#sales", "message": "신규 리드가 등록되었습니다"}),
        node("n8", "mergeNode", {"mergeStrategy": "join_newline"}),
        node("n9", "outputNode"),
    ],
    edges=[
        edge("e1", "n1", "n2"),
        edge("e2", "n2", "n3"),
        edge("e3", "n3", "n4"),
        edge("e4", "n4", "n5", "hot"),
        edge("e5", "n4", "n6", "else"),
        edge("e6", "n5", "n8"),
        edge("e7", "n6", "n8"),
        edge("e8", "n8", "n7"),
        edge("e9", "n7", "n9"),
    ],
)

# 카테고리는 원본 n8n 소스 폴더명(서비스 브랜드 기준)이 아니라, 우리 엔진이 실제로 다르게
# 만드는 축인 "워크플로우 구조 패턴" 기준으로 재편했다(2026-07-16). 예: WhatsApp/Telegram/Discord는
# 우리 엔진에선 다 kakaoNode/discordNode 같은 범용 메시지 노드로 흡수되기 때문에 서비스명으로
# 나누는 게 검색에 도움이 안 됨 — 대신 승인분기/분류라우팅/반복처리/문서파싱/QA챗봇/단발생성
# 6가지로 나눠서 확장 모드 RAG 검색이 "구조가 비슷한" 템플릿을 찾도록 한다.
TEMPLATES = [
    ("Airtable 레코드 변경 시 AI 필드 자동 채움", "Batch_List_Processing_and_Digests", tpl1),
    ("Outlook 메일 AI 분류 및 폴더 자동 이동", "Classification_and_Routing", tpl2),
    ("이력서 PDF 파싱 후 정리된 이력서 PDF 재생성", "Document_Processing", tpl3),
    ("Airtable 데이터 비서 챗봇", "QA_Chatbots_and_Assistants", tpl4),
    ("인증서 발급 요청 자동/수동 승인 봇", "Approval_Workflows", tpl5),
    ("채용/공고 링크 모니터링 → AI 유효성 판별 → 카카오톡 알림", "Batch_List_Processing_and_Digests", tpl6),
    ("사내 정책 헬프데스크 챗봇(카카오톡 답변, 발송 전 사람 승인)", "Approval_Workflows", tpl7),
    ("DB 데이터 비서 챗봇(자연어 질의 → 카카오톡 답변)", "QA_Chatbots_and_Assistants", tpl8),
    ("논문 모니터링 → AI 요약 → Notion 저장", "Batch_List_Processing_and_Digests", tpl9),
    ("예약 신청 접수 → AI 자격 검토 → 사람 승인 → 확정/반려 안내", "Approval_Workflows", tpl10),
    ("이미지 배경 제거 자동화(구글 드라이브 → API → 알림)", "Classification_and_Routing", tpl11),
    ("레딧 인기글 수집 → AI 관련성 판별/요약 → 카카오톡 다이제스트", "Batch_List_Processing_and_Digests", tpl12),
    ("디스코드 문의 자동 분류 → 담당 부서 채널 라우팅", "Classification_and_Routing", tpl13),
    ("세금/정책 문서 Q&A 어시스턴트", "QA_Chatbots_and_Assistants", tpl14),
    ("제품 카탈로그 문의 챗봇(카카오톡 답변)", "QA_Chatbots_and_Assistants", tpl15),
    ("블로그 포스트 자동 태깅", "Batch_List_Processing_and_Digests", tpl16),
    ("웹훅으로 서버(도커) 시작/중지 제어", "Classification_and_Routing", tpl17),
    ("설문 응답 인사이트 분석 → 카카오톡 알림", "Batch_List_Processing_and_Digests", tpl18),
    ("이력서 분석 및 후보자 평가", "Classification_and_Routing", tpl19),
    ("고객 피드백 감성 분석 및 라우팅", "Classification_and_Routing", tpl20),
    ("GitLab MR AI 코드 리뷰 자동 코멘트", "Content_Generation", tpl21),
    ("Linear 버그 분류 후 담당 팀 라우팅", "Classification_and_Routing", tpl22),
    ("신규 논문 자동 요약 및 카테고리 분류", "Batch_List_Processing_and_Digests", tpl23),
    ("SEO 시드 키워드 생성기", "Content_Generation", tpl24),
    ("Gmail 수신 메일 AI 자동 라벨링", "Classification_and_Routing", tpl25),
    ("Gmail 답장 초안 작성 및 승인 발송", "Approval_Workflows", tpl26),
    ("텔레그램 메시지 유해언어 감지", "Classification_and_Routing", tpl27),
    ("매일 랜덤 레시피 텔레그램 발송", "Batch_List_Processing_and_Digests", tpl28),
    ("인보이스 데이터 추출 및 사람 검증", "Approval_Workflows", tpl29),
    ("구글시트 신규 리드 자격 평가", "Batch_List_Processing_and_Digests", tpl30),
    ("AI 트윗 생성 및 게시", "Content_Generation", tpl31),
    ("긍정 피드백 Notion 저장", "Classification_and_Routing", tpl32),
    ("Slack 고객 문의 감성 추적", "Classification_and_Routing", tpl33),
    ("브랜드 톤앤매너 블로그 포스트 생성", "Content_Generation", tpl34),
    ("스키마 기반 SQL 쿼리 생성 어시스턴트", "QA_Chatbots_and_Assistants", tpl35),
    ("Airtable 지원서 자동 심사", "Classification_and_Routing", tpl36),
    ("영업 미팅 준비 브리핑 카카오톡 발송", "Content_Generation", tpl37),
    ("채용 공고 작성 및 승인 게시", "Approval_Workflows", tpl38),
    ("계약서 템플릿 자동 채움", "Document_Processing", tpl39),
    ("이력서 구조화 데이터 추출 및 저장", "Document_Processing", tpl40),
    ("문서 내 표 데이터 CSV 변환", "Document_Processing", tpl41),
    ("인보이스 자동 추출 및 저장", "Document_Processing", tpl42),
    ("웹페이지 마크다운 변환 및 링크 추출", "Document_Processing", tpl43),
    ("CSV 개인정보 자동 마스킹", "Document_Processing", tpl44),
    ("은행 거래내역서 마크다운 변환", "Document_Processing", tpl45),
    ("회의 녹취 요약 및 액션 아이템 저장", "Document_Processing", tpl46),
    ("API 문서 기반 Q&A 챗봇", "QA_Chatbots_and_Assistants", tpl47),
    ("영화 추천 데이터 비서 챗봇", "QA_Chatbots_and_Assistants", tpl48),
    ("사내 복리후생 안내 챗봇", "QA_Chatbots_and_Assistants", tpl49),
    ("보안 알림 심각도 판별 및 승인 기반 차단", "Approval_Workflows", tpl50),
    ("신규 고객 온보딩 안내 승인 발송", "Approval_Workflows", tpl51),
    ("리드 문의 긴급도 분류 및 라우팅", "Classification_and_Routing", tpl52),
    ("이커머스 문의 메일 유형 분류 라우팅", "Classification_and_Routing", tpl53),
    ("이메일 구독 신청 스팸 판별 및 등록", "Classification_and_Routing", tpl54),
    ("해커뉴스 채용 공고 자동 수집 및 정리", "Batch_List_Processing_and_Digests", tpl55),
    ("경쟁사 언급 모니터링 및 슬랙 다이제스트", "Batch_List_Processing_and_Digests", tpl56),
    ("유튜브 영상 AI 요약 디스코드 게시", "Content_Generation", tpl57),
    ("인터뷰 질문지 자동 생성", "Content_Generation", tpl58),
    ("환불 요청 자동 검토 및 승인", "Approval_Workflows", tpl59),
    ("휴가 신청 승인 알림", "Approval_Workflows", tpl60),
    ("지출 결의서 금액별 승인 라우팅", "Approval_Workflows", tpl61),
    ("신규 벤더 등록 컴플라이언스 검토 후 승인", "Approval_Workflows", tpl62),
    ("소셜 게시물 발행 전 브랜드 검수 승인", "Approval_Workflows", tpl63),
    ("재고 부족 시 발주 승인 워크플로우", "Approval_Workflows", tpl64),
    ("사내 IT 헬프데스크 챗봇", "QA_Chatbots_and_Assistants", tpl65),
    ("계약서 조항 Q&A 어시스턴트", "QA_Chatbots_and_Assistants", tpl66),
    ("주문 상태 조회 챗봇", "QA_Chatbots_and_Assistants", tpl67),
    ("제품 매뉴얼 트러블슈팅 어시스턴트", "QA_Chatbots_and_Assistants", tpl68),
    ("인사 정책 안내 카카오톡 봇", "QA_Chatbots_and_Assistants", tpl69),
    ("코드베이스 아키텍처 Q&A 봇", "QA_Chatbots_and_Assistants", tpl70),
    ("제품 출시 보도자료 자동 작성", "Content_Generation", tpl71),
    ("이커머스 상품 상세페이지 카피 생성", "Content_Generation", tpl72),
    ("주간 뉴스레터 초안 생성", "Content_Generation", tpl73),
    ("채용 공고 문구 자동 생성", "Content_Generation", tpl74),
    ("고객 리뷰 기반 FAQ 초안 생성", "Content_Generation", tpl75),
    ("SNS 캡션 다국어 로컬라이징", "Content_Generation", tpl76),
    ("PDF 청구서 항목 추출 및 시트 저장", "Document_Processing", tpl77),
    ("근로계약서 자동 초안 생성", "Document_Processing", tpl78),
    ("회의록 PDF 결정사항 추출", "Document_Processing", tpl79),
    ("이력서 PDF 표준 포맷 변환", "Document_Processing", tpl80),
    ("스캔 영수증 데이터화 및 지출 분류 저장", "Document_Processing", tpl81),
    ("문서 표준 양식 준수 검사 및 반려 안내", "Document_Processing", tpl82),
    ("매일 RSS 피드 관심 주제 다이제스트", "Batch_List_Processing_and_Digests", tpl83),
    ("지원자 이력서 일괄 스크리닝 및 합격자 명단 발송", "Batch_List_Processing_and_Digests", tpl84),
    ("일별 서버 로그 이상탐지 슬랙 알림", "Batch_List_Processing_and_Digests", tpl85),
    ("고객 문의 채널별 자동 라우팅", "Classification_and_Routing", tpl86),
    ("버그 리포트 심각도 분류 및 이슈 등록", "Classification_and_Routing", tpl87),
    ("인바운드 리드 소스별 CRM 라우팅", "Classification_and_Routing", tpl88),
]


def main():
    store = get_vector_store(TRANSLATED_COLLECTION)
    # add_texts()는 그냥 append라 이 스크립트를 다시 돌리면 기존에 이미 들어간 이름도
    # 중복으로 또 쌓인다(실제로 한 번 겪음) — 이미 있는 name은 건너뛴다.
    existing_names = {m.get("name") for m in store.get().get("metadatas", [])}

    docs, metadatas = [], []
    for name, category, g in TEMPLATES:
        if name in existing_names:
            print(f"[SKIP] {name} (이미 DB에 있음)")
            continue
        ok, errs = validate_flow(g)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} (nodes={len(g.nodes)}, edges={len(g.edges)})")
        if not ok:
            for e in errs:
                print(f"   - {e}")
            continue
        docs.append(g.model_dump_json())
        metadatas.append({"name": name, "category": category, "source": "hand_curated"})

    print(f"\n{len(docs)}/{len(TEMPLATES)} templates passed validation and were new.")
    if docs:
        store.add_texts(texts=docs, metadatas=metadatas)
        print(f"Ingested {len(docs)} hand-curated templates into '{TRANSLATED_COLLECTION}'.")


if __name__ == "__main__":
    main()
