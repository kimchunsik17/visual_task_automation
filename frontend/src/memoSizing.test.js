import test from 'node:test';
import assert from 'node:assert/strict';
import {
  fitMemoTextareaToContent,
  getMemoRequiredHeight,
  MEMO_MIN_NODE_HEIGHT,
  MEMO_MIN_TEXTAREA_HEIGHT,
} from './memoSizing.js';

test('메모 높이는 내용의 scrollHeight만큼 늘어난다', () => {
  const textarea = { scrollHeight: 248.2, style: {} };

  const height = fitMemoTextareaToContent(textarea);

  assert.equal(height, 249);
  assert.equal(textarea.style.height, '249px');
  assert.equal(textarea.style.overflowY, 'hidden');
});

test('짧은 메모는 최소 높이를 유지한다', () => {
  const textarea = { style: { height: '300px' } };
  Object.defineProperty(textarea, 'scrollHeight', {
    get() {
      assert.equal(textarea.style.height, '0px');
      return 24;
    },
  });

  const height = fitMemoTextareaToContent(textarea);

  assert.equal(height, MEMO_MIN_TEXTAREA_HEIGHT);
  assert.equal(textarea.style.height, `${MEMO_MIN_TEXTAREA_HEIGHT}px`);
});

test('요소가 아직 없을 때도 안전하게 최소 높이를 반환한다', () => {
  assert.equal(fitMemoTextareaToContent(null), MEMO_MIN_TEXTAREA_HEIGHT);
});

test('서식 편집기의 위치와 내용 높이로 메모 전체 높이를 계산한다', () => {
  assert.equal(getMemoRequiredHeight({ contentTop: 66.2, contentHeight: 120.1, bottomPadding: 12 }), 199);
  assert.equal(getMemoRequiredHeight({ contentTop: 50, contentHeight: 20 }), MEMO_MIN_NODE_HEIGHT);
});
