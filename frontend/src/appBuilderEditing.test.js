import assert from 'node:assert/strict';
import test from 'node:test';
import {
  alignComponents,
  cloneWithNewIds,
  distributeComponents,
  duplicateComponents,
  findParentId,
  matchSize,
  nudgeComponents,
  pasteComponents,
  reorderComponent,
  sharedParentId,
} from './appBuilderEditing.js';
import { defaultPropsFor, filterCatalog, catalogEntry, COMPONENT_CATALOG } from './appBuilderCatalog.js';
import { COMPONENT_DEFAULT_SIZES, INPUT_COMPONENT_TYPES } from './appBuilderSchema.js';

const box = (id, x, y, width, height, extra = {}) => ({
  id,
  type: 'button',
  props: { position: { x, y }, style: { width: `${width}px`, height: `${height}px` } },
  ...extra,
});

const tree = () => [
  box('a', 10, 10, 100, 40),
  box('b', 200, 60, 50, 20),
  { ...box('panel', 0, 200, 400, 200), type: 'container', children: [box('c', 20, 20, 80, 30), box('d', 150, 90, 80, 30)] },
];

let counter = 0;
const idFactory = (type) => `${type}-new-${counter += 1}`;

test('findParentId / sharedParentId resolve nesting', () => {
  const components = tree();
  assert.equal(findParentId(components, 'a'), 'root');
  assert.equal(findParentId(components, 'c'), 'panel');
  assert.equal(findParentId(components, 'missing'), null);
  assert.equal(sharedParentId(components, ['c', 'd']), 'panel');
  assert.equal(sharedParentId(components, ['a', 'c']), null);
});

test('cloneWithNewIds renames every node and does not share props', () => {
  const components = tree();
  const clone = cloneWithNewIds(components[2], idFactory);
  assert.notEqual(clone.id, 'panel');
  assert.notEqual(clone.children[0].id, 'c');
  clone.props.position.x = 999;
  assert.equal(components[2].props.position.x, 0);
});

test('duplicateComponents inserts the copy right after the original with an offset', () => {
  const { components, newIds } = duplicateComponents(tree(), ['a'], idFactory, { x: 20, y: 20 });
  assert.equal(newIds.length, 1);
  assert.equal(components[1].id, newIds[0]);
  assert.deepEqual(components[1].props.position, { x: 30, y: 30 });
  assert.equal(components.length, 4);
});

test('duplicateComponents skips descendants whose ancestor is also selected', () => {
  const { components, newIds } = duplicateComponents(tree(), ['panel', 'c'], idFactory);
  assert.equal(newIds.length, 1);
  assert.equal(components.length, 4);
  assert.equal(components[2].children.length, 2, 'original panel children untouched');
  assert.equal(components[3].children.length, 2, 'clone carries both children');
});

test('pasteComponents appends clones at the root', () => {
  const clipboard = [box('c', 20, 20, 80, 30)];
  const { components, newIds } = pasteComponents(tree(), clipboard, idFactory);
  assert.equal(components.length, 4);
  assert.equal(components[3].id, newIds[0]);
  assert.deepEqual(components[3].props.position, { x: 40, y: 40 });
});

test('nudgeComponents moves only top-level selections and clamps at zero', () => {
  const moved = nudgeComponents(tree(), ['a', 'panel', 'c'], -20, 5);
  assert.deepEqual(moved[0].props.position, { x: 0, y: 15 });
  assert.deepEqual(moved[2].props.position, { x: 0, y: 205 });
  assert.deepEqual(moved[2].children[0].props.position, { x: 20, y: 20 }, 'child rides along with its parent');
});

test('reorderComponent changes paint order among siblings', () => {
  const components = tree();
  assert.deepEqual(reorderComponent(components, 'a', 'front').map((c) => c.id), ['b', 'panel', 'a']);
  assert.deepEqual(reorderComponent(components, 'panel', 'back').map((c) => c.id), ['panel', 'a', 'b']);
  assert.deepEqual(reorderComponent(components, 'a', 'forward').map((c) => c.id), ['b', 'a', 'panel']);
  assert.deepEqual(reorderComponent(components, 'd', 'backward')[2].children.map((c) => c.id), ['d', 'c']);
  assert.equal(reorderComponent(components, 'a', 'backward'), components, 'already first: unchanged');
});

test('alignComponents aligns edges and centers within a shared parent', () => {
  const left = alignComponents(tree(), ['a', 'b'], 'left');
  assert.equal(left[1].props.position.x, 10);

  const right = alignComponents(tree(), ['a', 'b'], 'right');
  assert.equal(right[0].props.position.x, 150);
  assert.equal(right[1].props.position.x, 200);

  const hcenter = alignComponents(tree(), ['a', 'b'], 'hcenter');
  // span 10..250, center 130 → a: 80, b: 105
  assert.equal(hcenter[0].props.position.x, 80);
  assert.equal(hcenter[1].props.position.x, 105);

  const bottom = alignComponents(tree(), ['c', 'd'], 'bottom');
  assert.equal(bottom[2].children[0].props.position.y, 90);

  const mixed = tree();
  assert.equal(alignComponents(mixed, ['a', 'c'], 'left'), mixed, 'different parents: unchanged');
});

test('distributeComponents spaces items evenly between the outer two', () => {
  const components = [box('x', 0, 0, 10, 10), box('y', 15, 0, 10, 10), box('z', 100, 0, 10, 10)];
  const distributed = distributeComponents(components, ['x', 'y', 'z'], 'horizontal');
  assert.deepEqual(distributed.map((c) => c.props.position.x), [0, 50, 100]);
  assert.equal(distributeComponents(components, ['x', 'y'], 'horizontal'), components, 'needs three');
});

test('matchSize copies the first selection dimension to the rest', () => {
  const matched = matchSize(tree(), ['a', 'b'], 'width');
  assert.equal(matched[1].props.style.width, '100px');
  assert.equal(matched[1].props.style.height, '20px');
});

test('catalog covers every default size and input type', () => {
  const types = new Set(COMPONENT_CATALOG.map((entry) => entry.type));
  for (const type of Object.keys(COMPONENT_DEFAULT_SIZES)) {
    if (type === 'terminal') continue; // 실행 로그 패널 전용, 팔레트에 없다
    assert.ok(types.has(type), `${type} missing from catalog`);
  }
  for (const type of INPUT_COMPONENT_TYPES) {
    assert.ok(defaultPropsFor(type, 1).inputKey, `${type} needs a default inputKey`);
  }
  assert.equal(catalogEntry('markdown').category, 'display');
  assert.ok(filterCatalog('마크다운').some((entry) => entry.type === 'markdown'));
  assert.ok(filterCatalog('range').some((entry) => entry.type === 'slider'));
  assert.equal(filterCatalog('').length, COMPONENT_CATALOG.length);
});
