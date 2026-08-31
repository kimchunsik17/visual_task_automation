// NodeDefinition v1 접근 헬퍼 (ADR-0005).
//
// 정본은 저장소 루트 node_definitions/<type>.json 이고, 아래 번들은
// `python backend/export_node_definitions.py` 가 만든다 — 번들 파일을 직접 고치지 마라
// (backend/test_node_definitions.py 의 드리프트 테스트가 잡아낸다).
//
// 같은 정의를 서버 validator(backend/node_definition.py)와 LLM 노드 카탈로그
// (backend/meta_agent.py 의 NODE_CATALOG)도 읽는다. 그래서 예전처럼 허용값 하나를
// 바꾸려고 세 파일을 따로 고칠 필요가 없다.

import definitions from './generated/nodeDefinitions.json';

export const NodeDefinitions = definitions;

export const getNodeDefinition = (nodeType) => definitions[nodeType] || null;

export const getNodeDisplay = (nodeType) => getNodeDefinition(nodeType)?.display || {};

const findField = (nodeType, fieldPath) => {
  const [head, tail] = String(fieldPath).split('.');
  const field = getNodeDefinition(nodeType)?.fields?.find((f) => f.name === head);
  if (!field) return null;
  if (!tail) return field;
  return (field.itemFields || []).find((f) => f.name === tail) || null;
};

/** 'model' 또는 'rules.operator'(repeatable 항목 필드) 경로의 select 선택지 */
export const getFieldOptions = (nodeType, fieldPath) => findField(nodeType, fieldPath)?.options || [];

/** 같은 경로의 선언된 기본값 */
export const getFieldDefault = (nodeType, fieldPath) => findField(nodeType, fieldPath)?.default;

/** showWhen 조건에 따라 이 필드를 지금 보여줘야 하는지 */
export const isFieldVisible = (field, data) => {
  const condition = field.showWhen;
  if (!condition) return true;
  const current = data ? data[condition.field] : undefined;
  if (Array.isArray(condition.oneOf)) return condition.oneOf.includes(current);
  if (condition.equals !== undefined) return current === condition.equals;
  return Boolean(current) === (condition.truthy !== false);
};

/**
 * 어떤 필드를 켰을 때 비로소 드러나는 필드들 가운데, 아직 비어 있고 기본값이 선언된 것.
 * 예: useStructuredOutput 을 체크하면 jsonSchema 에 예시 스키마를 미리 채워준다.
 */
export const dependentDefaults = (nodeType, fieldName, data) => {
  const filled = {};
  (getNodeDefinition(nodeType)?.fields || []).forEach((field) => {
    if (field.showWhen?.field !== fieldName) return;
    if (field.default === undefined || field.default === null) return;
    if (data && data[field.name]) return;
    filled[field.name] = field.default;
  });
  return filled;
};
