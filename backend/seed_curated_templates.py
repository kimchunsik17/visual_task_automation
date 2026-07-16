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
"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from meta_agent import FlowGraph, FlowNode, FlowEdge, validate_flow
from rag_utils import get_vector_store, TRANSLATED_COLLECTION

MODEL = "gpt-4o-mini"


def node(id_, type_, data=None):
    return FlowNode(id=id_, type=type_, data=data or {})


def edge(id_, source, target, sourceHandle=None):
    return FlowEdge(id=id_, source=source, target=target, sourceHandle=sourceHandle)


# ── 1. Airtable 레코드/필드 변경 시 AI로 빈 필드 자동 채움 ──────────────────
tpl1 = FlowGraph(
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
        edge("e13", "n9", "n14"),
        edge("e14", "n13", "n14"),
        edge("e15", "n14", "n15"),
    ],
)

# ── 2. 받은 이메일 AI 분류 후 폴더 자동 이동 + 긴급 메일 슬랙 알림 ──────────
tpl2 = FlowGraph(
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
        edge("e12", "n10", "n11"),
    ],
)

# ── 3. 이력서 PDF 파싱(병렬 정리) → HTML 변환 → PDF 재생성 → 텔레그램 발송 ──
tpl3 = FlowGraph(
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
    nodes=[
        node("n1", "startNode"),
        node("n2", "dynamicInputNode", {"inputLabel": "인증서 발급 요청 페이로드(도메인 포함)", "testValue": '{"domain":"example.com"}'}),
        node("n3", "httpRequestNode", {"method": "GET", "url": "https://www.virustotal.com/api/v3/domains/{{domain}}"}),
        node("n4", "jsonParserNode", {"mode": "extract", "extractKey": "malicious_count"}),
        node("n5", "conditionNode", {"rules": [{"id": "clean", "operator": "==", "value": "0"}]}),
        node("n6", "httpRequestNode", {"method": "POST", "url": "https://api.venafi.cloud/v1/certificaterequests"}),
        node("n7", "slackNode", {"channel": "#cert-bot", "message": "악성 리포트 0건 확인, 인증서가 자동으로 발급되었습니다"}),
        node("n8", "humanApprovalNode", {"message": "악성 리포트가 발견되어 수동 승인이 필요합니다. 인증서를 발급할까요?"}),
        node("n9", "conditionNode", {"rules": [{"id": "approved", "operator": "==", "value": "승인"}]}),
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
        edge("e8", "n8", "n9"),
        edge("e9", "n9", "n10", "approved"),
        edge("e10", "n10", "n11"),
        edge("e11", "n9", "n12", "else"),
        edge("e12", "n7", "n13"),
        edge("e13", "n11", "n13"),
        edge("e14", "n12", "n13"),
        edge("e15", "n13", "n14"),
    ],
)

TEMPLATES = [
    ("Airtable 레코드 변경 시 AI 필드 자동 채움", "OpenAI_and_LLMs", tpl1),
    ("Outlook 메일 AI 분류 및 폴더 자동 이동", "Gmail_and_Email_Automation", tpl2),
    ("이력서 PDF 파싱 후 정리된 이력서 PDF 재생성", "PDF_and_Document_Processing", tpl3),
    ("Airtable 데이터 비서 챗봇", "Airtable", tpl4),
    ("인증서 발급 요청 자동/수동 승인 봇", "Slack", tpl5),
]


def main():
    docs, metadatas = [], []
    for name, category, g in TEMPLATES:
        ok, errs = validate_flow(g)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} (nodes={len(g.nodes)}, edges={len(g.edges)})")
        if not ok:
            for e in errs:
                print(f"   - {e}")
            continue
        docs.append(g.model_dump_json())
        metadatas.append({"name": name, "category": category, "source": "hand_curated"})

    print(f"\n{len(docs)}/{len(TEMPLATES)} templates passed validation.")
    if docs:
        store = get_vector_store(TRANSLATED_COLLECTION)
        store.add_texts(texts=docs, metadatas=metadatas)
        print(f"Ingested {len(docs)} hand-curated templates into '{TRANSLATED_COLLECTION}'.")


if __name__ == "__main__":
    main()
