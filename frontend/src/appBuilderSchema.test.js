import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyWorkflowMappings,
  buildSubmitChain,
  fitContainersToChildren,
  inferButtonActionMode,
  isValidLogicConnection,
  makeGeneratedLayoutEditable,
  normalizeComponents,
  normalizeWorkflowMappings,
  requiredCanvasHeight,
  resolveCanvas,
  scaleDescendantGeometry,
} from './appBuilderSchema.js';

test('normalizes legacy and object workflow mappings', () => {
  assert.deepEqual(normalizeWorkflowMappings({
    save: 12,
    search: { id: '34', resultTarget: { componentId: 'result' } },
    empty: '',
  }), {
    save: { projectId: '12' },
    search: { id: '34', projectId: '34', resultTarget: { componentId: 'result' } },
  });
});

test('applies workflow mappings recursively without mutating components', () => {
  const components = [{
    id: 'panel',
    type: 'container',
    props: {},
    children: [{ id: 'save', type: 'button', props: { text: 'Save' } }],
  }];
  const result = applyWorkflowMappings(components, { save: '7' });

  assert.equal(result[0].children[0].props.workflowId, '7');
  assert.equal(components[0].children[0].props.workflowId, undefined);
});

test('keeps valid positions and assigns safe pixel dimensions', () => {
  const result = normalizeComponents([
    { id: 'placed', type: 'button', props: { position: { x: 40, y: 50 }, style: { width: '160px' } } },
    { id: 'auto', type: 'input', props: { style: { width: '100%' } } },
  ], { width: 1024, height: 768 });

  assert.deepEqual(result[0].props.position, { x: 40, y: 50 });
  assert.equal(result[0].props.style.width, '160px');
  assert.equal(result[1].props.style.width, '300px');
  assert.ok(result[1].props.position.y >= 30);
});

test('prefers an actual blueprint trigger over a legacy workflow fallback', () => {
  assert.equal(inferButtonActionMode({ workflowId: '5' }, true), 'blueprint');
  assert.equal(inferButtonActionMode({ workflowId: '5' }, false), 'workflow');
  assert.equal(inferButtonActionMode({ actionMode: 'workflow', onClickHandler: 'save' }, true), 'workflow');
});

test('expands canvas height for components below the initial canvas', () => {
  const height = requiredCanvasHeight([
    { id: 'result', type: 'terminal', props: { position: { x: 0, y: 740 }, style: { height: '200px' } } },
  ], 768);
  assert.equal(height, 970);
});

test('respects automatic and fixed playground heights', () => {
  const components = [
    { id: 'result', type: 'text', props: { position: { x: 0, y: 900 }, style: { height: '40px' } } },
  ];

  assert.equal(resolveCanvas(components, { width: 1024, height: 768, autoHeight: true }).height, 970);
  assert.equal(resolveCanvas(components, { width: 1024, height: 768, autoHeight: false }).height, 768);
});

test('only accepts compatible Blueprint handles', () => {
  assert.equal(isValidLogicConnection({ sourceHandle: 'trigger', targetHandle: 'triggerIn' }), true);
  assert.equal(isValidLogicConnection({ sourceHandle: 'dataOut', targetHandle: 'payloadIn' }), true);
  assert.equal(isValidLogicConnection({ sourceHandle: 'dataOut', targetHandle: 'triggerIn' }), false);
});

test('converts generated flow layouts into editable local positions', () => {
  const result = makeGeneratedLayoutEditable([{
    id: 'group',
    type: 'container',
    props: { layoutMode: 'row', style: { width: '400px', height: '120px', padding: '10px', gap: '8px' } },
    children: [
      { id: 'first', type: 'button', props: { style: { width: '100px', height: '40px' } } },
      { id: 'second', type: 'button', props: { style: { width: '120px', height: '40px' } } },
    ],
  }]);

  assert.equal(result[0].props.layoutMode, 'absolute');
  assert.deepEqual(result[0].children[0].props.position, { x: 10, y: 10 });
  assert.deepEqual(result[0].children[1].props.position, { x: 118, y: 10 });
});

test('scales nested component geometry with its parent group', () => {
  const result = scaleDescendantGeometry([{
    id: 'child',
    type: 'container',
    props: { position: { x: 20, y: 30 }, style: { width: '100px', height: '80px' } },
    children: [{
      id: 'nested',
      type: 'text',
      props: { position: { x: 10, y: 5 }, style: { width: '50px', height: '20px' } },
    }],
  }], 2, 0.5);

  assert.deepEqual(result[0].props.position, { x: 40, y: 15 });
  assert.equal(result[0].props.style.width, '200px');
  assert.equal(result[0].props.style.height, '40px');
  assert.deepEqual(result[0].children[0].props.position, { x: 20, y: 2.5 });
});

// ── buildSubmitChain (백로그 16) ─────────────────────────────────────────
test('워크플로우 선택이 Trigger→Submit→Output 노드 3종을 만든다', () => {
  const { nodes, edges, created } = buildSubmitChain('btn1', 42, [], []);

  assert.equal(created, true);
  assert.deepEqual(nodes.map((n) => n.type), ['triggerNode', 'submitNode', 'outputNode']);

  const [trigger, submit, output] = nodes;
  assert.equal(trigger.data.componentId, 'btn1');
  assert.equal(submit.data.projectId, '42');
  assert.equal(output.data.componentId, '');  // 출력 대상은 추측하지 않는다

  // 제어 흐름: trigger→submit→output, 데이터 흐름: submit.dataOut→output.dataIn
  assert.equal(edges.length, 3);
  assert.ok(edges.some((e) => e.source === trigger.id && e.target === submit.id && e.targetHandle === 'triggerIn'));
  assert.ok(edges.some((e) => e.source === submit.id && e.target === output.id && e.sourceHandle === 'triggerOut'));
  assert.ok(edges.some((e) => e.source === submit.id && e.target === output.id && e.sourceHandle === 'dataOut' && e.targetHandle === 'dataIn'));
  // 만들어지는 엣지가 전부 연결 규칙을 통과해야 캔버스에서 수동으로도 그릴 수 있는 그래프다
  edges.forEach((e) => assert.ok(isValidLogicConnection(e), `invalid edge: ${JSON.stringify(e)}`));
});

test('같은 버튼에 다시 고르면 노드를 늘리지 않고 Submit 의 워크플로우만 바꾼다', () => {
  const first = buildSubmitChain('btn1', 42, [], []);
  const second = buildSubmitChain('btn1', 99, first.nodes, first.edges);

  assert.equal(second.created, false);
  assert.equal(second.nodes.length, 3);
  assert.equal(second.nodes.find((n) => n.type === 'submitNode').data.projectId, '99');
  assert.equal(second.edges.length, 3);
});

test('AI 가 만든 기존 workflowNode 체인은 재배선하지 않는다', () => {
  // 트리거는 있지만 Submit 이 아니라 workflowNode 로 이어지는 그래프 — 사용자/AI 의 구성을
  // 조용히 덮어쓰면 안 된다.
  const nodes = [
    { id: 't1', type: 'triggerNode', data: { componentId: 'btn1', eventType: 'onClick' } },
    { id: 'w1', type: 'workflowNode', data: { projectId: '7' } },
  ];
  const edges = [{ id: 'e1', source: 't1', target: 'w1', sourceHandle: 'trigger', targetHandle: 'triggerIn' }];

  const result = buildSubmitChain('btn1', 42, nodes, edges);

  assert.equal(result.created, false);
  assert.deepEqual(result.nodes, nodes);
  assert.equal(result.nodes[1].data.projectId, '7');  // 기존 workflowNode 는 그대로
});

test('다른 버튼의 트리거는 새 체인 생성을 막지 않는다', () => {
  const existing = buildSubmitChain('btn1', 42, [], []);
  const result = buildSubmitChain('btn2', 43, existing.nodes, existing.edges);

  assert.equal(result.created, true);
  assert.equal(result.nodes.filter((n) => n.type === 'triggerNode').length, 2);
});

test('errorOut 은 제어 흐름으로만 연결된다', () => {
  assert.ok(isValidLogicConnection({ sourceHandle: 'errorOut', targetHandle: 'triggerIn' }));
  assert.ok(!isValidLogicConnection({ sourceHandle: 'errorOut', targetHandle: 'dataIn' }));
});

test('style.left/top win over a conflicting props.position and are stripped (AI double-offset bug)', () => {
  // 2026-08-28 타이머 앱: props.position 은 세로로 쌓인 값, style.top 은 카드 안 한 줄이었다.
  const [card] = normalizeComponents([{
    id: 'card',
    type: 'container',
    props: { position: { x: 262, y: 184 }, style: { width: '500px', height: '240px' } },
    children: [
      { id: 'start', type: 'button', props: { position: { x: 20, y: 180 }, style: { position: 'absolute', left: '24px', top: '156px', width: '96px', height: '44px' } } },
      { id: 'stop', type: 'button', props: { position: { x: 20, y: 260 }, style: { position: 'absolute', left: '132px', top: '156px', width: '96px', height: '44px' } } },
    ],
  }], { width: 1024, height: 768 });

  assert.deepEqual(card.children[0].props.position, { x: 24, y: 156 });
  assert.deepEqual(card.children[1].props.position, { x: 132, y: 156 });
  for (const child of card.children) {
    assert.equal(child.props.style.left, undefined);
    assert.equal(child.props.style.top, undefined);
    assert.equal(child.props.style.position, undefined);
  }
});

test('style.left/top fill in a missing props.position', () => {
  const [text] = normalizeComponents([
    { id: 't', type: 'text', props: { style: { left: '40px', top: '60px', width: '100px', height: '30px' } } },
  ], { width: 1024, height: 768 });
  assert.deepEqual(text.props.position, { x: 40, y: 60 });
});

test('fitContainersToChildren grows a container whose children overflow it', () => {
  const [card] = fitContainersToChildren([{
    id: 'card',
    type: 'container',
    props: { style: { width: '500px', height: '240px', padding: '24px' } },
    children: [
      { id: 'status', type: 'text', props: { position: { x: 24, y: 208 }, style: { width: '300px', height: '42px' } } },
    ],
  }]);
  assert.equal(card.props.style.height, '274px'); // 208 + 42 + 24 padding

  const [untouched] = fitContainersToChildren([{
    id: 'ok',
    type: 'container',
    props: { style: { width: '500px', height: '240px' } },
    children: [{ id: 'a', type: 'text', props: { position: { x: 0, y: 10 }, style: { height: '20px' } } }],
  }]);
  assert.equal(untouched.props.style.height, '240px');
});
