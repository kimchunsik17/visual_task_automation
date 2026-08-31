import test from 'node:test';
import assert from 'node:assert/strict';
import {
  collectPinnedOutputs,
  downstreamExternalNodes,
  isPinnedOutputStale,
  nodeSignature,
  nodeWritesExternally,
  readPinnedOutput,
  readSampleInput,
  redactFixture,
  writePinnedOutput,
  writeSampleInput,
} from './nodeTestFixtures.js';

// localStorage 는 브라우저 API 라 node:test 에서는 최소 구현으로 대신한다.
const installStorage = () => {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
    clear: () => store.clear(),
  };
  return store;
};

test('고정 출력은 저장 전에 시크릿을 가린다', () => {
  const raw = [
    '{"api_key": "sk-live-1234567890", "user": "kim"}',
    'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload',
    'postgresql://dbuser:supersecret@db.example.com:5432/app',
    'password=hunter2',
  ].join('\n');
  const masked = redactFixture(raw);
  for (const secret of ['sk-live-1234567890', 'eyJhbGciOiJIUzI1NiJ9', 'supersecret', 'hunter2', 'dbuser']) {
    assert.ok(!masked.includes(secret), `${secret} 가 남아 있다`);
  }
  assert.ok(masked.includes('"user": "kim"'));   // 시크릿이 아닌 값은 보존
  assert.ok(masked.includes('[REDACTED]'));
});

test('노드 설정이 바뀌면 고정 출력이 오래된 것으로 표시된다', () => {
  installStorage();
  const node = { id: 'n1', type: 'httpRequestNode', data: { url: 'https://a.dev', method: 'GET' } };
  const fixture = writePinnedOutput(7, node, '{"ok": true}');
  assert.equal(isPinnedOutputStale(fixture, node), false);
  const edited = { ...node, data: { ...node.data, url: 'https://b.dev' } };
  assert.equal(isPinnedOutputStale(fixture, edited), true);
  // UI 콜백·표시 상태가 바뀐 것만으로는 stale 이 아니다.
  const rerendered = { ...node, data: { ...node.data, onChange: () => {}, isExecuting: true } };
  assert.equal(nodeSignature(rerendered), nodeSignature(node));
});

test('고정 출력과 샘플 입력은 프로젝트·노드별로 분리 저장된다', () => {
  installStorage();
  const node = { id: 'n1', type: 'valueNode', data: {} };
  writePinnedOutput(1, node, '프로젝트1 결과');
  writePinnedOutput(2, node, '프로젝트2 결과');
  assert.equal(readPinnedOutput(1, 'n1').value, '프로젝트1 결과');
  assert.equal(readPinnedOutput(2, 'n1').value, '프로젝트2 결과');
  assert.equal(readPinnedOutput(1, 'other'), null);

  writeSampleInput(1, 'n1', '샘플');
  assert.equal(readSampleInput(1, 'n1'), '샘플');
  writeSampleInput(1, 'n1', '');
  assert.equal(readSampleInput(1, 'n1'), '');
});

test('실행 요청에는 고정된 노드만 실린다', () => {
  installStorage();
  const nodes = [
    { id: 'a', type: 'valueNode', data: {} },
    { id: 'b', type: 'valueNode', data: {} },
  ];
  writePinnedOutput(1, nodes[0], '고정값');
  assert.deepEqual(collectPinnedOutputs(1, nodes), { a: '고정값' });
});

test('외부 전송 판정은 정의의 sideEffect 와 모드를 따른다', () => {
  const definitions = {
    httpRequestNode: { sideEffect: 'external-write', connector: { sideEffectByMode: { GET: 'external-read', POST: 'external-write' } } },
    gmailTriggerNode: { sideEffect: 'external-read' },
    llmNode: { sideEffect: 'none' },
  };
  const get = (type) => definitions[type] || null;
  assert.equal(nodeWritesExternally({ type: 'httpRequestNode', data: { method: 'GET' } }, get('httpRequestNode')), false);
  assert.equal(nodeWritesExternally({ type: 'httpRequestNode', data: { method: 'POST' } }, get('httpRequestNode')), true);
  // 모르는 모드는 쓰기로 본다(백엔드와 같은 안전한 쪽 가정).
  assert.equal(nodeWritesExternally({ type: 'httpRequestNode', data: { method: 'PATCH' } }, get('httpRequestNode')), true);
  assert.equal(nodeWritesExternally({ type: 'gmailTriggerNode', data: {} }, get('gmailTriggerNode')), false);
  assert.equal(nodeWritesExternally({ type: 'llmNode', data: {} }, get('llmNode')), false);
  // 아직 정의로 옮기지 않은 노드는 목록으로 판정한다.
  assert.equal(nodeWritesExternally({ type: 'kakaoNode', data: {} }, null), true);
  assert.equal(nodeWritesExternally({ type: 'valueNode', data: {} }, null), false);
});

test('실제 실행 확인 문구는 하류의 외부 전송 노드를 모은다', () => {
  const nodes = [
    { id: 'a', type: 'llmNode', data: {} },
    { id: 'b', type: 'discordNode', data: {} },
    { id: 'c', type: 'emailNode', data: {} },
    { id: 'z', type: 'kakaoNode', data: {} },   // 다른 갈래 — 하류가 아니다
  ];
  const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }];
  const found = downstreamExternalNodes(nodes, edges, 'a', () => null).map((node) => node.id);
  assert.deepEqual(found, ['b', 'c']);
  assert.deepEqual(downstreamExternalNodes(nodes, edges, 'c', () => null).map((n) => n.id), ['c']);
});

test('순환 그래프에서도 하류 탐색이 끝난다', () => {
  const nodes = [{ id: 'a', type: 'llmNode', data: {} }, { id: 'b', type: 'discordNode', data: {} }];
  const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'a' }];
  assert.deepEqual(downstreamExternalNodes(nodes, edges, 'a', () => null).map((n) => n.id), ['b']);
});
