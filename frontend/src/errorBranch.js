// 에러 출력 핸들·재시도·중복 제거 설정 — 백엔드 규칙의 프론트 쪽 거울 (백로그 32 ENGINE-3, ADR-0030).
//
//   backend/graph_traversal.py   ERROR_HANDLE='error', 흐름 노드(NATIVE_FLOW_TYPES)의 'error' 핸들은 에러 핸들이 아니다
//   backend/node_retry.py        data.retries(0~5) · data.backoffSec(첫 대기, 상한 60초)
//   backend/idempotency.py       webhookNode data.dedupeByPayload
//   backend/error_trigger.py     graph_data.errorWorkflowId
//
// 값의 상한·키 이름은 백엔드가 정본이다 — 여기서는 편집기가 같은 범위로 잘라 저장할 뿐이다.

export const ERROR_HANDLE = 'error';
export const ERROR_EDGE_LABEL = '실패 시';

/** 인터프리터가 직접 구현하는 흐름 노드 6종 — 생성기가 제어 구문을 내므로 error 포트를 둘 자리가 없다. */
export const FLOW_NODE_TYPES = ['conditionNode', 'humanApprovalNode', 'loopNode', 'distributorNode', 'breakNode', 'outputNode'];

// 시작·메모는 "실패" 의 뜻이 없다.
const NO_ERROR_PORT = new Set([...FLOW_NODE_TYPES, 'startNode', 'memoNode']);

export const supportsErrorPort = (type) => typeof type === 'string' && type !== '' && !NO_ERROR_PORT.has(type);

export const isErrorEdge = (edge) => Boolean(edge) && edge.sourceHandle === ERROR_HANDLE;

/** 캔버스에 그릴 때만 입힌다(저장하지 않는다) — 빨간 점선과 "실패 시" 라벨. 실행 강조 색은 호출자가 그 위에 얹는다. */
export function decorateErrorEdge(edge) {
  if (!isErrorEdge(edge)) return edge;
  return {
    ...edge,
    className: [edge.className, 'edge-error'].filter(Boolean).join(' '),
    label: edge.label ?? ERROR_EDGE_LABEL,
    style: {
      ...edge.style,
      stroke: edge.style?.stroke ?? 'var(--ts-danger, #ef4444)',
      strokeDasharray: edge.style?.strokeDasharray ?? '6 4',
    },
  };
}

export const RETRIES_MAX = 5;
export const BACKOFF_MAX_SEC = 60;
export const BACKOFF_DEFAULT_SEC = 1;

/** 빈 값·0·음수·숫자 아님 → undefined(키를 지운다). 상한 5. */
export function normalizeRetries(raw) {
  if (raw === '' || raw === null || raw === undefined) return undefined;
  const n = Math.trunc(Number(raw));
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.min(RETRIES_MAX, n);
}

/** 빈 값·음수·숫자 아님 → undefined(백엔드 기본 1초). 상한 60. 0 은 "대기 없음" 으로 유효하다. */
export function normalizeBackoffSec(raw) {
  if (raw === '' || raw === null || raw === undefined) return undefined;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return Math.min(BACKOFF_MAX_SEC, n);
}

export const supportsPayloadDedupe = (type) => type === 'webhookNode';

/** graph_data.errorWorkflowId → 양의 정수 또는 null. */
export function errorWorkflowIdFrom(graphData) {
  const raw = graphData && typeof graphData === 'object' ? graphData.errorWorkflowId : null;
  if (raw === null || raw === undefined || raw === '') return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}
