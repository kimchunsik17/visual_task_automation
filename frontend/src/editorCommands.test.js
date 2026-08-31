import test from 'node:test';
import assert from 'node:assert/strict';
import {
  absorbDetachedText,
  arrangeSelectedNodes,
  createClipboardFragment,
  SAFE_ENTITY_ID,
  makeEntityId,
  normalizeGraphIds,
  createEditorCommandRegistry,
  createEditorSnapshot,
  findCommandForKeyboardEvent,
  formatEditorShortcut,
  materializeClipboardFragment,
  parseClipboardFragment,
  serializeClipboardFragment,
} from './editorCommands.js';

const sampleGraph = () => ({
  nodes: [
    {
      id: 'parent',
      type: 'loopNode',
      position: { x: 100, y: 200 },
      selected: true,
      data: { label: '반복' },
    },
    {
      id: 'child',
      type: 'httpRequestNode',
      parentNode: 'parent',
      extent: 'parent',
      position: { x: 10, y: 20 },
      selected: true,
      data: {
        apiKey: 'raw-secret',
        nested: { accessToken: 'nested-secret' },
        onChange: () => {},
      },
    },
  ],
  edges: [{ id: 'edge', source: 'parent', target: 'child', selected: true }],
});

test('history snapshots omit transient React Flow and UI callback state', () => {
  const { nodes, edges } = sampleGraph();
  const snapshot = createEditorSnapshot(nodes, edges);
  assert.equal('selected' in snapshot.nodes[0], false);
  assert.equal('onChange' in snapshot.nodes[1].data, false);
  assert.equal('selected' in snapshot.edges[0], false);
});

test('clipboard fragments redact credentials and round-trip through JSON', () => {
  const { nodes, edges } = sampleGraph();
  const fragment = createClipboardFragment(nodes, edges);
  const parsed = parseClipboardFragment(serializeClipboardFragment(fragment));
  assert.equal(parsed.nodes[1].data.apiKey, '');
  assert.equal(parsed.nodes[1].data.apiKeyNeedsConnection, true);
  assert.equal(parsed.nodes[1].data.nested.accessToken, '');
  assert.equal(parsed.nodes[1].data.nested.accessTokenNeedsConnection, true);
});

test('clipboard redaction covers every credential key the node UIs actually use', () => {
  const nodes = [{
    id: 'n1', type: 'databaseNode', position: { x: 0, y: 0 }, selected: true,
    data: {
      connectionString: 'postgresql://u:pw@h/db', botToken: 'bot-secret',
      webhookUrl: 'https://hooks.example/x', smtp_credentials: 'me@x.com:app-pw',
      secretKey: 'toss-secret', query: 'SELECT 1',
    },
  }];
  const fragment = createClipboardFragment(nodes, []);
  const text = serializeClipboardFragment(fragment);
  for (const leaked of ['pw@h', 'bot-secret', 'hooks.example', 'app-pw', 'toss-secret']) {
    assert.equal(text.includes(leaked), false, `clipboard leaked: ${leaked}`);
  }
  assert.equal(fragment.nodes[0].data.query, 'SELECT 1');
});

test('clipboard redaction keeps API Center references (they are not secrets)', () => {
  const nodes = [{
    id: 'n1', type: 'databaseNode', position: { x: 0, y: 0 }, selected: true,
    data: { connectionString: '{{API_CENTER:database}}' },
  }];
  const fragment = createClipboardFragment(nodes, []);
  assert.equal(fragment.nodes[0].data.connectionString, '{{API_CENTER:database}}');
  assert.equal('connectionStringNeedsConnection' in fragment.nodes[0].data, false);
});

test('pasting remaps node and edge IDs while preserving child coordinates', () => {
  const { nodes, edges } = sampleGraph();
  const fragment = createClipboardFragment(nodes, edges);
  const pasted = materializeClipboardFragment(fragment, { x: 40, y: 40 });
  assert.notEqual(pasted.nodes[0].id, 'parent');
  assert.equal(pasted.nodes[1].parentNode, pasted.nodes[0].id);
  assert.deepEqual(pasted.nodes[1].position, { x: 10, y: 20 });
  assert.equal(pasted.edges[0].source, pasted.nodes[0].id);
  assert.equal(pasted.edges[0].target, pasted.nodes[1].id);
});

test('generated ids are safe python identifiers (the server rejects hyphenated UUIDs)', () => {
  for (let i = 0; i < 20; i += 1) {
    assert.match(makeEntityId('node'), SAFE_ENTITY_ID);
  }
  const { nodes, edges } = sampleGraph();
  const pasted = materializeClipboardFragment(createClipboardFragment(nodes, edges), { x: 0, y: 0 });
  pasted.nodes.forEach((node) => assert.match(node.id, SAFE_ENTITY_ID));
});

test('loading a graph normalizes legacy hyphenated ids and keeps edges/parents consistent', () => {
  const nodes = [
    { id: 'node_4359b546-55aa-4c6f-944f-1711774e5269', type: 'startNode', position: { x: 0, y: 0 }, data: {} },
    { id: 'safe_child', type: 'valueNode', parentNode: 'node_4359b546-55aa-4c6f-944f-1711774e5269', position: { x: 1, y: 1 }, data: {} },
  ];
  const edges = [{ id: 'e_x', source: 'node_4359b546-55aa-4c6f-944f-1711774e5269', target: 'safe_child' }];
  const result = normalizeGraphIds(nodes, edges);
  assert.equal(result.changed, true);
  result.nodes.forEach((node) => assert.match(node.id, SAFE_ENTITY_ID));
  assert.equal(result.nodes[1].parentNode, result.nodes[0].id);
  assert.equal(result.edges[0].source, result.nodes[0].id);
  assert.equal(result.edges[0].target, 'safe_child');
  const untouched = normalizeGraphIds([{ id: 'ok_1' }], []);
  assert.equal(untouched.changed, false);
});

test('copying a child without its parent converts its position to canvas coordinates', () => {
  const { nodes, edges } = sampleGraph();
  nodes[0].selected = false;
  const fragment = createClipboardFragment(nodes, edges);
  assert.equal(fragment.nodes[0].parentNode, undefined);
  assert.deepEqual(fragment.nodes[0].position, { x: 110, y: 220 });
  assert.equal(fragment.edges.length, 0);
});

test('alignment respects node dimensions and separate parent coordinate systems', () => {
  const nodes = [
    { id: 'a', position: { x: 20, y: 10 }, width: 100, selected: true },
    { id: 'b', position: { x: 80, y: 90 }, width: 200, selected: true },
    { id: 'c', parentNode: 'group', position: { x: 15, y: 30 }, width: 50, selected: true },
    { id: 'd', parentNode: 'group', position: { x: 45, y: 70 }, width: 50, selected: true },
  ];
  const aligned = arrangeSelectedNodes(nodes, 'align-right');
  assert.equal(aligned[0].position.x, 180);
  assert.equal(aligned[1].position.x, 80);
  assert.equal(aligned[2].position.x, 45);
  assert.equal(aligned[3].position.x, 45);
});

test('horizontal distribution produces equal gaps while keeping outer bounds', () => {
  const nodes = [
    { id: 'a', position: { x: 0, y: 0 }, width: 40, selected: true },
    { id: 'b', position: { x: 90, y: 0 }, width: 20, selected: true },
    { id: 'c', position: { x: 180, y: 0 }, width: 40, selected: true },
  ];
  const distributed = arrangeSelectedNodes(nodes, 'distribute-horizontal');
  const firstGap = distributed[1].position.x - (distributed[0].position.x + 40);
  const secondGap = distributed[2].position.x - (distributed[1].position.x + 20);
  assert.equal(firstGap, secondGap);
  assert.equal(distributed[0].position.x, 0);
  assert.equal(distributed[2].position.x, 180);
});

test('shift-number viewport shortcuts use physical digit codes', () => {
  const actions = new Proxy({}, { get: () => () => {} });
  const commands = createEditorCommandRegistry(actions);
  const context = {
    canUndo: false,
    canRedo: false,
    hasSelection: true,
    hasNodes: true,
    selectedNodeCount: 1,
    isOwner: true,
    isTextEditing: false,
  };
  const command = findCommandForKeyboardEvent(commands, {
    key: '@',
    code: 'Digit2',
    ctrlKey: false,
    metaKey: false,
    shiftKey: true,
    altKey: false,
  }, context);
  assert.equal(command.id, 'viewport.fit-selection');
});

test('shortcut labels adapt modifier keys to the current platform', () => {
  assert.equal(formatEditorShortcut({ mod: true, shift: true, key: 'z' }, 'Win32'), 'Ctrl+Shift+Z');
  assert.equal(formatEditorShortcut({ mod: true, alt: true, key: 'k' }, 'MacIntel'), '⌘+Option+K');
  assert.equal(formatEditorShortcut({ key: 'escape' }, 'Linux'), 'Esc');
});

// ── 분리 텍스트(popout) 흡수 — 데이터 흐름 분리 계획 §5-7 ──────────────────
test('absorbDetachedText 는 분리된 값을 원래 필드로 되돌리고 노드를 없앤다', () => {
  const nodes = [
    { id: 'n1', type: 'llmNode', data: { systemPrompt: '옛 값', isDetached_systemPrompt: true } },
    { id: 'popout_n1_systemPrompt', type: 'detachedText',
      data: { sourceId: 'n1', fieldKey: 'systemPrompt', value: '분리창에서 고친 값' } },
    { id: 'n2', type: 'outputNode', data: {} },
  ];
  const edges = [
    { id: 'e1', source: 'n1', target: 'n2' },
    { id: 'e2', source: 'popout_n1_systemPrompt', target: 'n1' },
  ];
  const result = absorbDetachedText(nodes, edges);
  assert.equal(result.changed, true);
  assert.deepEqual(result.nodes.map((n) => n.id), ['n1', 'n2']);
  // 값은 분리창 쪽이 정본이다 — 분리된 동안 사용자가 편집한 곳이다
  assert.equal(result.nodes[0].data.systemPrompt, '분리창에서 고친 값');
  assert.ok(!('isDetached_systemPrompt' in result.nodes[0].data));
  assert.deepEqual(result.edges.map((e) => e.id), ['e1']);
});

test('absorbDetachedText 는 분리 노드 없이 남은 플래그만 있어도 정리한다', () => {
  const result = absorbDetachedText([
    { id: 'n1', type: 'llmNode', data: { systemPrompt: '값', isDetached_systemPrompt: true } },
  ], []);
  assert.equal(result.changed, true);
  assert.equal(result.nodes[0].data.systemPrompt, '값');
  assert.ok(!('isDetached_systemPrompt' in result.nodes[0].data));
});

test('absorbDetachedText 는 손댈 게 없으면 입력을 그대로 돌려준다', () => {
  const nodes = [{ id: 'n1', type: 'llmNode', data: { systemPrompt: '값' } }];
  const edges = [];
  const result = absorbDetachedText(nodes, edges);
  assert.equal(result.changed, false);
  assert.equal(result.nodes, nodes);
  assert.equal(result.edges, edges);
});
