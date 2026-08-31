import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_MEMO_FONT_SIZE,
  getMemoContentFingerprint,
  getMemoFontSize,
  memoContentToPlainText,
  normalizeMemoContent,
} from './memoContent.js';
import { createEditorSnapshot } from './editorCommands.js';

test('예전 일반 텍스트 메모를 구조화 모델로 읽는다', () => {
  const content = normalizeMemoContent(undefined, '기존 메모');

  assert.deepEqual(content.segments, [{ text: '기존 메모', bold: false, highlight: false }]);
  assert.equal(memoContentToPlainText(content), '기존 메모');
});

test('인접한 같은 서식 조각을 합치고 알 수 없는 필드는 버린다', () => {
  const content = normalizeMemoContent({
    version: 1,
    segments: [
      { text: '중요', bold: true, html: '<script>alert(1)</script>' },
      { text: ' 사항', bold: true },
      { text: ' 확인', highlight: true },
    ],
  });

  assert.deepEqual(content.segments, [
    { text: '중요 사항', bold: true, highlight: false },
    { text: ' 확인', bold: false, highlight: true },
  ]);
  assert.equal('html' in content.segments[0], false);
});

test('빈 구조화 메모는 오래된 fallback 텍스트로 되돌아가지 않는다', () => {
  const content = normalizeMemoContent({ version: 1, segments: [] }, '삭제 전 내용');

  assert.deepEqual(content.segments, []);
  assert.equal(getMemoContentFingerprint(content), '{"version":1,"segments":[]}');
});

test('글자 크기는 지원하는 프리셋만 허용한다', () => {
  assert.equal(getMemoFontSize('18'), 18);
  assert.equal(getMemoFontSize(13), DEFAULT_MEMO_FONT_SIZE);
  assert.equal(getMemoFontSize('large'), DEFAULT_MEMO_FONT_SIZE);
});

test('메모 서식과 글자 크기는 그래프 snapshot에 저장된다', () => {
  const memoContent = normalizeMemoContent({
    version: 1,
    segments: [{ text: '배포 전 확인', bold: true, highlight: true }],
  });
  const snapshot = createEditorSnapshot([{
    id: 'memo_1',
    type: 'memoNode',
    position: { x: 10, y: 20 },
    width: 360,
    height: 210,
    data: { text: '배포 전 확인', memoContent, memoFontSize: 18, memoSize: { width: 360, height: 210 } },
  }], []);

  assert.deepEqual(snapshot.nodes[0].data.memoContent, memoContent);
  assert.equal(snapshot.nodes[0].data.memoFontSize, 18);
  assert.deepEqual(snapshot.nodes[0].data.memoSize, { width: 360, height: 210 });
  assert.equal(snapshot.nodes[0].width, 360);
  assert.equal(snapshot.nodes[0].height, 210);
});

