// 필드 데이터 바인딩 — 에디터 쪽 헬퍼 (계획 DATA_FLOW_SEPARATION_PLAN §5).
//
// 정본은 백엔드 node_bindings.BINDABLE_FIELDS 이고, 여기서는 그 번들을 읽어
// "이 필드에 ⚡ 를 붙일 수 있는지"와 "무엇을 가리킬 수 있는지"만 판단한다.
// 바인딩 자체는 노드 data.bindings 에 저장된다 — 캔버스에 선을 그리지 않는다.

import bundle from './generated/bindableFields.json';

const BINDABLE = bundle.fields || {};

export const bindableFields = (nodeType) => BINDABLE[nodeType] || [];
export const isBindableField = (nodeType, field) => bindableFields(nodeType).includes(field);

export const bindingOf = (data, field) => {
  const spec = (data?.bindings || {})[field];
  if (!spec || typeof spec !== 'object' || !spec.source) return null;
  return { source: spec.source, path: spec.path || '', required: spec.required !== false };
};

/** 실행 경로상 node 로 오는 모든 상류 노드 id (역방향 BFS — 백엔드 _upstream_ids 와 같은 규칙) */
export const upstreamIds = (nodeId, edges) => {
  const incoming = new Map();
  (edges || []).forEach((edge) => {
    const target = String(edge.target);
    if (!incoming.has(target)) incoming.set(target, []);
    incoming.get(target).push(String(edge.source));
  });
  const seen = new Set();
  const queue = [...(incoming.get(String(nodeId)) || [])];
  while (queue.length) {
    const current = queue.pop();
    if (seen.has(current)) continue;
    seen.add(current);
    queue.push(...(incoming.get(current) || []));
  }
  return seen;
};

/**
 * 실행 결과(JSON 문자열)에서 선택 가능한 경로 후보를 뽑는다.
 * 실행 이력이 있으면 실제 값을 함께 보여줘서 "어떤 경로가 무엇인지"를 짐작하지 않게 한다.
 */
const MAX_CANDIDATES = 60;

export const pathCandidates = (rawResult) => {
  if (rawResult == null) return [];
  let value = rawResult;
  if (typeof value === 'string') {
    const text = value.trim().replace(/^```(?:json)?\s*/i, '').replace(/```$/, '').trim();
    if (!text.startsWith('{') && !text.startsWith('[')) return [];
    try { value = JSON.parse(text); } catch { return []; }
  }
  const out = [];
  const walk = (node, prefix) => {
    if (out.length >= MAX_CANDIDATES) return;
    if (Array.isArray(node)) {
      node.slice(0, 3).forEach((item, index) => walk(item, `${prefix}[${index}]`));
      return;
    }
    if (node && typeof node === 'object') {
      Object.entries(node).forEach(([key, child]) => {
        const path = prefix ? `${prefix}.${key}` : key;
        if (child && typeof child === 'object') {
          out.push({ path, preview: Array.isArray(child) ? `배열 ${child.length}개` : '객체' });
          walk(child, path);
        } else {
          out.push({ path, preview: String(child).slice(0, 40) });
        }
      });
    }
  };
  walk(value, '');
  return out;
};

/** 바인딩 개수 — 접힌 노드 배지용 */
export const bindingCount = (data) => Object.keys(data?.bindings || {}).length;

/** 필드 하나의 바인딩을 넣거나(spec) 지운다(null). data.bindings 만 바꾼 새 객체를 돌려준다. */
export const withBinding = (data, field, spec) => {
  const next = { ...(data?.bindings || {}) };
  if (spec) next[field] = spec;
  else delete next[field];
  if (Object.keys(next).length === 0) {
    const { bindings, ...rest } = data || {};
    return rest;
  }
  return { ...(data || {}), bindings: next };
};

/**
 * 캔버스 오버레이가 그릴 데이터 링크 목록 (계획 §5-2).
 * 정본은 노드 data.bindings 이므로 엣지 배열과 무관하게 여기서 파생한다.
 */
export const bindingLinks = (nodes) => {
  const links = [];
  (nodes || []).forEach((node) => {
    const bindings = node?.data?.bindings;
    if (!bindings) return;
    Object.entries(bindings).forEach(([field, spec]) => {
      if (!spec || !spec.source) return;
      links.push({
        id: `${node.id}:${field}`,
        source: String(spec.source),
        target: String(node.id),
        field,
        path: spec.path || '',
      });
    });
  });
  return links;
};

/** 변수 허브(§5-5)로 쓰이는 valueNode 의 이름. 없으면 null. */
export const variableName = (node) => {
  if (!node || node.type !== 'valueNode') return null;
  const name = (node.varName ?? node.data?.varName ?? '').toString().trim();
  return name || null;
};
