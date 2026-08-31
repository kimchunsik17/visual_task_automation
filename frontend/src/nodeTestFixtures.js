// 노드 테스트 데이터 저장소 (EDITOR_SHORTCUTS §7.1·§7.3, Slice 4).
//
// 두 가지를 브라우저에만 저장한다. 서버로 보내는 것은 실행 요청 순간뿐이고, 그래프에는 남지 않는다.
//
//   샘플 입력 (§7.1)  진입점 실행에서 "직전 노드 출력" 자리에 넣을 값
//   고정 출력 (§7.3)  어떤 노드의 결과를 fixture 로 굳혀, 하류를 반복 테스트할 때 그 노드(그리고
//                     그 상류 전체)를 실행하지 않게 한다 — 외부 API 를 다시 부르지 않는 핵심 장치
//
// 고정 출력에는 두 가지 안전장치가 붙는다.
//   1. 저장 전 redaction — 실행 결과에 토큰·비밀번호 같은 값이 섞여 있어도 localStorage 에 그대로
//      남기지 않는다(클립보드 마스킹과 같은 규칙).
//   2. stale 감지 — 노드 설정이 바뀌면 고정해 둔 결과는 더 이상 그 설정의 출력이 아니므로 경고한다.

const SAMPLE_PREFIX = 'wfai:sampleInput';
const PINNED_PREFIX = 'wfai:pinnedOutput';
const MAX_FIXTURE_LENGTH = 200_000;   // localStorage 를 한 노드가 독차지하지 않게 한다

// 값 자체가 시크릿인 흔한 형태들. 키-값 문자열과 Authorization 헤더, URI userinfo 를 가린다
// (백엔드 node_errors.redaction 과 같은 의도이며, 여기서는 저장 직전에 적용한다).
// lookbehind 없이 키를 그대로 두고 값만 바꾼다(구형 Safari 호환).
const SECRET_ASSIGNMENT_RE = /("?\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|authorization)\b"?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)/gi;
const BEARER_RE = /\b(Bearer|Bot|Basic|Token)\s+[A-Za-z0-9\-._~+/=]{8,}/gi;
const URI_USERINFO_RE = /(:\/\/)([^/\s@'"]+)@/g;

export const REDACTED = '"[REDACTED]"';

/** 고정 출력으로 저장하기 전에 값 안의 시크릿을 가린다. */
export const redactFixture = (text) => {
  if (typeof text !== 'string') return '';
  return text
    .replace(URI_USERINFO_RE, '$1[REDACTED]@')
    .replace(BEARER_RE, (_match, scheme) => `${scheme} [REDACTED]`)
    .replace(SECRET_ASSIGNMENT_RE, (_match, key) => `${key}${REDACTED}`)
    .slice(0, MAX_FIXTURE_LENGTH);
};

/** 노드 설정의 지문. 값이 달라지면 고정해 둔 출력은 오래된 것이다. */
export const nodeSignature = (node) => {
  const data = node?.data || {};
  const stable = Object.keys(data)
    .filter((key) => typeof data[key] !== 'function' && !key.startsWith('on') && !key.startsWith('is'))
    .sort()
    .map((key) => `${key}=${typeof data[key] === 'object' ? JSON.stringify(data[key]) : String(data[key])}`)
    .join('');
  let hash = 0;
  for (let i = 0; i < stable.length; i += 1) {
    hash = (hash * 31 + stable.charCodeAt(i)) | 0;
  }
  return `${node?.type || '?'}:${hash}`;
};

const read = (key) => {
  try { return localStorage.getItem(key); } catch { return null; }
};
const write = (key, value) => {
  try {
    if (value === null || value === '') localStorage.removeItem(key);
    else localStorage.setItem(key, value);
    return true;
  } catch { return false; }
};

// ── 샘플 입력 ───────────────────────────────────────────────────────────
const sampleKey = (projectId, nodeId) => `${SAMPLE_PREFIX}:${projectId || 'new'}:${nodeId}`;

export const readSampleInput = (projectId, nodeId) => read(sampleKey(projectId, nodeId)) || '';
export const writeSampleInput = (projectId, nodeId, value) => write(sampleKey(projectId, nodeId), value || '');

// ── 고정 출력 ───────────────────────────────────────────────────────────
const pinnedKey = (projectId, nodeId) => `${PINNED_PREFIX}:${projectId || 'new'}:${nodeId}`;

/** { value, signature, savedAt } 또는 null. */
export const readPinnedOutput = (projectId, nodeId) => {
  const raw = read(pinnedKey(projectId, nodeId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.value !== 'string') return null;
    return parsed;
  } catch { return null; }
};

export const writePinnedOutput = (projectId, node, value) => {
  const fixture = {
    value: redactFixture(value),
    signature: nodeSignature(node),
    savedAt: new Date().toISOString(),
  };
  return write(pinnedKey(projectId, node.id), JSON.stringify(fixture)) ? fixture : null;
};

export const clearPinnedOutput = (projectId, nodeId) => write(pinnedKey(projectId, nodeId), null);

/** 노드 설정이 고정 시점 이후로 바뀌었는가 — UI 가 "오래된 고정 데이터" 로 경고한다. */
export const isPinnedOutputStale = (fixture, node) =>
  Boolean(fixture) && Boolean(node) && fixture.signature !== nodeSignature(node);

/**
 * 실행 요청에 실을 `{node_id: value}`. 고정된 노드만 담는다.
 * stale 한 fixture 도 보낸다 — 사용자가 명시적으로 고정한 값이고, 경고는 UI 가 한다.
 */
export const collectPinnedOutputs = (projectId, nodes = []) => {
  const pinned = {};
  nodes.forEach((node) => {
    const fixture = readPinnedOutput(projectId, node.id);
    if (fixture) pinned[String(node.id)] = fixture.value;
  });
  return pinned;
};

export const pinnedNodeIds = (projectId, nodes = []) => Object.keys(collectPinnedOutputs(projectId, nodes));

// ── 외부 전송 판정 ──────────────────────────────────────────────────────
// "이 노드를 실제로 돌리면 바깥으로 무언가 나가는가" — 실제 실행 전에 확인을 받을지 정한다
// (§7.1 "실제 외부 쓰기는 별도 확인"). 백엔드 dry_run.SIDE_EFFECT_NODE_TYPES 와 같은 근거를 쓴다:
// 정의가 있는 노드는 정의의 sideEffect 에서, 아직 정의로 옮기지 않은 노드는 아래 목록에서.
const LEGACY_SIDE_EFFECT_TYPES = new Set([
  'databaseNode', 'discordNode', 'emailNode', 'fileModifierNode', 'googleCalendarNode',
  'googleSheetsNode', 'httpRequestNode', 'kakaoNode', 'notionNode', 'paymentLinkNode',
  'posterGeneratorNode', 'slackNode', 'telegramNode', 'tossNode', 'webCrawlerNode',
]);

export const nodeWritesExternally = (node, definition) => {
  if (!node) return false;
  const modes = definition?.connector?.sideEffectByMode;
  if (modes) {
    const mode = node.data?.mode || node.data?.method;
    // 모르는 모드는 쓰기로 본다 — 백엔드 ConnectorSpec.writes_externally 와 같은 규칙.
    if (mode) return modes[mode] !== 'external-read' && modes[mode] !== 'none';
    return Object.values(modes).some((grade) => grade === 'external-write');
  }
  if (definition?.sideEffect) return definition.sideEffect === 'external-write';
  return LEGACY_SIDE_EFFECT_TYPES.has(node.type);
};

/** 이 노드부터 하류로 실제 실행할 때 외부로 나갈 수 있는 노드들(확인 문구에 이름을 싣는다). */
export const downstreamExternalNodes = (nodes = [], edges = [], startId, getDefinition = () => null) => {
  const byId = new Map(nodes.map((node) => [String(node.id), node]));
  const forward = new Map();
  edges.forEach((edge) => {
    const source = String(edge.source);
    if (!forward.has(source)) forward.set(source, []);
    forward.get(source).push(String(edge.target));
  });
  const seen = new Set();
  const queue = [String(startId)];
  const found = [];
  while (queue.length) {
    const current = queue.shift();
    if (seen.has(current)) continue;
    seen.add(current);
    const node = byId.get(current);
    if (node && nodeWritesExternally(node, getDefinition(node.type))) found.push(node);
    (forward.get(current) || []).forEach((next) => queue.push(next));
  }
  return found;
};
