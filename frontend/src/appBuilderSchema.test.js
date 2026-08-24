import assert from 'node:assert/strict';
import test from 'node:test';
import {
  applyWorkflowMappings,
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
