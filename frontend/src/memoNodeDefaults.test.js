import test from 'node:test';
import assert from 'node:assert/strict';
import { MEMO_DEFAULT_WIDTH, ensureMemoNodeDefaults, ensureMemoNodeDefaultsForList } from './memoNodeDefaults.js';
import { MEMO_MIN_NODE_HEIGHT } from './memoSizing.js';

test('팔레트가 만든 치수 없는 메모에 observer 실행 전 기본 치수를 부여한다', () => {
  const memo = ensureMemoNodeDefaults({
    id: 'memo_1',
    type: 'memoNode',
    position: { x: 10, y: 20 },
    data: { label: '메모 (주석)' },
  });

  assert.equal(memo.width, MEMO_DEFAULT_WIDTH);
  assert.equal(memo.height, MEMO_MIN_NODE_HEIGHT);
  assert.deepEqual(memo.data.memoSize, { width: MEMO_DEFAULT_WIDTH, height: MEMO_MIN_NODE_HEIGHT });
  assert.deepEqual(memo.data.memoContent, { version: 1, segments: [] });
  assert.equal(memo.data.text, '');
});

test('기존 일반 텍스트와 사용자가 조절한 크기를 보존한다', () => {
  const memo = ensureMemoNodeDefaults({
    id: 'memo_2',
    type: 'memoNode',
    width: 443,
    height: 258,
    data: { text: '검토 필요', memoSize: { width: 443, height: 258 } },
  });

  assert.equal(memo.width, 443);
  assert.equal(memo.height, 258);
  assert.equal(memo.data.memoContent.segments[0].text, '검토 필요');
});

test('이미 정규화된 목록은 같은 참조를 유지한다', () => {
  const memo = ensureMemoNodeDefaults({ id: 'memo_3', type: 'memoNode', data: {} });
  const nodes = [memo, { id: 'node_1', type: 'promptNode', data: {} }];

  assert.equal(ensureMemoNodeDefaultsForList(nodes), nodes);
});

