// NodeError v1 접근 헬퍼 (ADR-0016).
//
// 정본은 저장소 루트 error_catalog.json 이고, 아래 번들은 `python backend/export_node_definitions.py`
// 가 만든다 — 번들 파일을 직접 고치지 마라(backend/test_node_errors.py 의 드리프트 테스트가 잡아낸다).
//
// 서버가 보내는 error 객체(wire contract)는 code·category·userMessage·retryable·effectState·field·
// retryAfterMs·requestId·safeDetails 다. 이 파일은 그 위에 catalog 가 아는 표시 정보(category 아이콘,
// 해결 동작)를 얹는다. 클라이언트가 모르는 code 가 오면 category 로만 그린다 — 서버가 catalog 를
// 먼저 늘려도 화면이 깨지지 않는다.

import catalog from './generated/errorCatalog.json';

export const ErrorCatalog = catalog;

// 이 상태에서는 "다시 보내면 두 번 갈 수 있다" — 재시도 버튼을 켜지 않는다(서버 규칙과 동일).
const UNSAFE_EFFECT_STATES = new Set(['unknown', 'applied']);

export const getErrorCodeMeta = (code) => (code && catalog.codes[code]) || null;

export const getCategoryMeta = (category) =>
  catalog.categories[category] || catalog.categories.runtime || { label: '오류', icon: 'bug' };

export const getResolution = (error) => {
  if (!error) return catalog.resolutions.none;
  const meta = getErrorCodeMeta(error.code);
  const key = meta?.resolution || 'none';
  return { key, ...(catalog.resolutions[key] || catalog.resolutions.none) };
};

/** 자동/수동 재시도 버튼을 활성화해도 되는가 — retryable 이면서 부수효과 상태가 안전할 때만. */
export const canRetry = (error) =>
  Boolean(error?.retryable) && !UNSAFE_EFFECT_STATES.has(error?.effectState);

export const effectStateLabel = (state) => ({
  not_applicable: '외부 변경 없음',
  not_started: '외부 반영 전 실패',
  unknown: '외부 반영 여부 알 수 없음',
  applied: '외부 반영 뒤 실패',
}[state] || state || '');

export const isLegacyError = (error) => error?.code === 'LEGACY_NODE_ERROR';
