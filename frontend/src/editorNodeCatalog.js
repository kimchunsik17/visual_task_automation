import { NodeRegistry } from './nodeRegistry';
import { NodeDefinitions } from './nodeDefinitions';
import { getHiddenNodeTypes } from './features';

const STATIC_EDITOR_NODES = [
  ['startNode', '시작', 'core', '#10b981', 'node-start', 'trigger'],
  ['scheduleNode', '스케줄 (시작)', 'core', '#8b5cf6', 'node-schedule', 'trigger'],
  ['outputNode', '결과 출력', 'core', '#f97316', 'node-output'],
  ['dynamicInputNode', '동적 입력', 'input', '#d946ef', 'node-dynamic-input'],
  ['webhookNode', '웹훅 수신', 'input', '#0ea5e9', 'node-webhook', 'trigger'],
  ['discordTriggerNode', '디스코드 봇 (시작)', 'input', '#5865f2', 'node-discord-trigger', 'trigger'],
  ['telegramTriggerNode', '텔레그램 봇 (시작)', 'input', '#26a5e4', 'node-telegram-trigger', 'trigger'],
  ['youtubeTriggerNode', 'YouTube 새 영상 (시작)', 'input', '#ff0033', 'node-youtube', 'trigger'],
  ['valueNode', '변수 (값)', 'input', '#ec4899', 'node-value'],
  ['promptNode', '프롬프트', 'ai', '#3b82f6', 'node-prompt'],
  ['llmNode', 'LLM', 'ai', '#8b5cf6', 'node-llm'],
  ['multiAgentNode', 'Multi-Agent', 'ai', '#6366f1', 'node-multi-agent'],
  ['conditionNode', '조건 분기', 'logic', '#0ea5e9', 'node-condition'],
  ['loopNode', '반복 (Loop)', 'logic', '#ca8a04', 'node-loop', 'container'],
  ['breakNode', '반복 종료', 'logic', '#dc2626', 'node-break'],
  ['delayNode', 'Delay (대기)', 'logic', '#3b82f6', 'node-delay'],
  ['mergeNode', 'Merge (병합)', 'logic', '#ec4899', 'node-merge'],
  ['pythonNode', '파이썬', 'code', '#eab308', 'node-python'],
  ['jsonParserNode', 'JSON 파서', 'code', '#eab308', 'node-json-parser'],
  ['tokenizerNode', '토크나이저', 'code', '#14b8a6', 'node-tokenizer'],
  ['distributorNode', '분배기', 'code', '#6366f1', 'node-distributor'],
  ['databaseNode', '데이터베이스', 'code', '#059669', 'node-database'],
  ['webCrawlerNode', '웹 크롤러', 'integration', '#0ea5e9', 'node-web-crawler'],
  ['emailNode', '이메일 전송', 'integration', '#f43f5e', 'node-email'],
  ['kakaoNode', '카카오 알림톡', 'integration', '#facc15', 'node-kakao-alimtalk'],
  ['discordNode', '디스코드 발송', 'integration', '#5865f2', 'node-discord-send'],
  ['telegramNode', '텔레그램 발송', 'integration', '#26a5e4', 'node-telegram-send'],
  ['notionNode', 'Notion', 'integration', '#9b9b9b', 'node-notion'],
  ['youtubeNode', 'YouTube', 'integration', '#ff0033', 'node-youtube'],
  ['rssTriggerNode', 'RSS 새 글 (시작)', 'input', '#f97316', 'node-webhook', 'trigger'],
  ['gmailTriggerNode', 'Gmail 새 메일 (시작)', 'input', '#ea4335', 'node-email', 'trigger'],
  ['gmailNode', 'Gmail 발송/답장', 'integration', '#ea4335', 'node-email'],
  ['googleDriveNode', 'Google Drive', 'integration', '#34a853', 'node-file-modifier'],
  ['httpRequestNode', 'HTTP Request', 'integration', '#0ea5e9', 'node-http-request'],
  ['naverSearchTriggerNode', '네이버 새 검색결과 (시작)', 'input', '#03c75a', 'provider-naver-api-hub', 'trigger'],
  ['naverSearchNode', '네이버 검색', 'integration', '#03c75a', 'provider-naver-api-hub'],
  ['jusoNode', '도로명주소', 'integration', '#0b6bcb', 'provider-juso'],
  ['dataGoKrNode', '공공데이터포털', 'integration', '#1e5eb8', 'provider-data-go-kr'],
  ['naverCafeNode', '네이버 카페', 'integration', '#03c75a', 'provider-naver-user-oauth'],
  // 문서 카테고리(포맷 스튜디오 계획 §4.3) — 새 문서·포스터는 formatNode, 기존 서식 파일
  // 채우기는 templateAnalyzer→fileModifier, 코드 없는 .hwpx 생성은 hwpxDocumentNode.
  ['formatNode', '문서 포맷', 'document', '#0d9488', 'node-file-modifier'],
  ['fileModifierNode', '자동 완성', 'document', '#f43f5e', 'node-file-modifier'],
  ['templateAnalyzerNode', '템플릿 분석', 'document', '#8b5cf6', 'node-template-analyzer'],
  ['hwpxDocumentNode', 'HWPX 문서', 'document', '#0ea5e9', 'node-template-analyzer'],
  ['humanApprovalNode', '사용자 승인', 'advanced', '#f43f5e', 'node-human-approval'],
  // 캔버스 주석 — 실행 그래프가 아니므로 kind를 분리해 연결/삽입/교체 후보에서 제외된다.
  ['memoNode', '메모 (주석)', 'advanced', '#eab308', 'ui-text', 'annotation'],
];

export const NODE_CATEGORY_LABELS = {
  core: '기본',
  input: '입력',
  ai: 'AI',
  logic: '로직',
  code: '코드·데이터',
  integration: '외부 연동',
  document: '문서',
  advanced: '고급',
};

const knownCategories = new Set(Object.keys(NODE_CATEGORY_LABELS));

const toCatalogEntry = ([type, label, category, color, icon, kind = 'node']) => ({
  type,
  label,
  category,
  categoryLabel: NODE_CATEGORY_LABELS[category],
  color,
  icon,
  kind,
  fieldNames: (NodeDefinitions[type]?.fields || []).map((field) => field.name),
});

const catalogByType = new Map(STATIC_EDITOR_NODES.map(toCatalogEntry).map((entry) => [entry.type, entry]));

Object.values(NodeRegistry).forEach((meta) => {
  const category = knownCategories.has(meta.category) ? meta.category : 'integration';
  const definitionFields = (NodeDefinitions[meta.type]?.fields || []).map((field) => field.name);
  catalogByType.set(meta.type, {
    type: meta.type,
    label: meta.label || meta.type,
    category,
    categoryLabel: NODE_CATEGORY_LABELS[category],
    color: meta.color || '#64748b',
    icon: meta.icon || null,
    kind: meta.kind || 'node',
    fieldNames: [...new Set([...(meta.fields || []).map((field) => field.name), ...definitionFields])],
  });
});

export const EDITOR_NODE_CATALOG = [...catalogByType.values()];

// 시연 노드 비가시화(features.hidden_nodes) — 팔레트·교체 후보 같은 "고르는" 표면은
// 이 함수를 쓴다. 캔버스에 이미 놓인 숨김 노드는 정상 렌더·정상 실행된다(시연 플래그 계획).
export const visibleEditorNodes = () => {
  const hidden = getHiddenNodeTypes();
  return hidden.size === 0 ? EDITOR_NODE_CATALOG : EDITOR_NODE_CATALOG.filter((n) => !hidden.has(n.type));
};

export const getEditorNodeMeta = (type) => catalogByType.get(type) || {
  type,
  label: type,
  category: 'advanced',
  categoryLabel: NODE_CATEGORY_LABELS.advanced,
  color: '#64748b',
  icon: null,
  kind: 'node',
  fieldNames: [],
};

export const getReplacementCandidates = (sourceType) => {
  const source = getEditorNodeMeta(sourceType);
  return visibleEditorNodes().filter((candidate) => candidate.type !== sourceType && candidate.kind === source.kind);
};

