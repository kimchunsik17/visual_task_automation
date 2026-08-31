import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_MEMO_COLOR, getMemoColorTheme, MEMO_COLOR_OPTIONS } from './memoColors.js';
import { createEditorSnapshot } from './editorCommands.js';

test('기존 메모와 알 수 없는 값은 노란색으로 표시한다', () => {
  assert.equal(getMemoColorTheme().id, DEFAULT_MEMO_COLOR);
  assert.equal(getMemoColorTheme('unknown').id, DEFAULT_MEMO_COLOR);
});

test('지원하는 메모 색상 ID는 중복되지 않는다', () => {
  const ids = MEMO_COLOR_OPTIONS.map((option) => option.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('선택한 메모 색상의 전체 theme을 반환한다', () => {
  const theme = getMemoColorTheme('violet');

  assert.equal(theme.label, '보라');
  assert.match(theme.background, /^rgba\(/);
  assert.match(theme.border, /^rgba\(/);
});

test('선택한 메모 색상은 그래프 snapshot에 저장된다', () => {
  const snapshot = createEditorSnapshot([{
    id: 'memo_1',
    type: 'memoNode',
    position: { x: 10, y: 20 },
    data: { text: '검토 필요', memoColor: 'sky', onChange: () => {} },
  }], []);

  assert.equal(snapshot.nodes[0].data.memoColor, 'sky');
  assert.equal(snapshot.nodes[0].data.text, '검토 필요');
  assert.equal('onChange' in snapshot.nodes[0].data, false);
});
