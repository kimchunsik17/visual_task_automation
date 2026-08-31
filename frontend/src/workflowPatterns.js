// 디자인 패턴 접근 헬퍼 (정본: 저장소 루트 workflow_patterns.json — ADR-0005 방식).
//
// 번들은 `python backend/export_node_definitions.py` 가 만든다 — 직접 고치지 마라
// (backend/test_workflow_patterns.py 의 드리프트 테스트가 잡아낸다).
// 같은 정본을 LLM 생성 프롬프트(backend/workflow_patterns.py 의 PATTERN_CATALOG)도
// 읽으므로, 문서에 보이는 패턴과 생성이 따르는 패턴이 항상 같다.

import bundle from './generated/workflowPatterns.json';

export const WORKFLOW_PATTERNS = bundle.patterns;

export const getWorkflowPattern = (patternId) =>
  WORKFLOW_PATTERNS.find((pattern) => pattern.id === patternId) || null;

/** 패턴 그래프에 등장하는 노드 타입 (중복 제거, 등장 순서 유지) */
export const patternNodeTypes = (pattern) => {
  const seen = [];
  (pattern?.graph?.nodes || []).forEach((node) => {
    if (!seen.includes(node.type)) seen.push(node.type);
  });
  return seen;
};

/** 이 노드 타입이 쓰이는 패턴들 — 노드 문서 페이지의 역링크용 */
export const patternsUsingNode = (nodeType) =>
  WORKFLOW_PATTERNS.filter((pattern) => patternNodeTypes(pattern).includes(nodeType));
