import assert from 'node:assert/strict';
import test from 'node:test';
import {
  decorateErrorEdge,
  errorWorkflowIdFrom,
  isErrorEdge,
  normalizeBackoffSec,
  normalizeRetries,
  supportsErrorPort,
  supportsPayloadDedupe,
} from './errorBranch.js';

test('흐름 노드·시작·메모에는 error 포트가 없고 나머지에는 있다', () => {
  for (const type of ['conditionNode', 'humanApprovalNode', 'loopNode', 'distributorNode', 'breakNode', 'outputNode', 'startNode', 'memoNode']) {
    assert.equal(supportsErrorPort(type), false, type);
  }
  for (const type of ['httpRequestNode', 'llmNode', 'emailNode', 'webhookNode', 'slackNode', 'valueNode']) {
    assert.equal(supportsErrorPort(type), true, type);
  }
  assert.equal(supportsErrorPort(undefined), false);
  assert.equal(supportsErrorPort(''), false);
});

test('error 간선은 sourceHandle 로 판정하고, 그릴 때만 점선·라벨을 입힌다', () => {
  const plain = { id: 'e1', source: 'a', target: 'b' };
  assert.equal(isErrorEdge(plain), false);
  assert.equal(decorateErrorEdge(plain), plain, '보통 간선은 그대로(같은 객체)');

  const error = { id: 'e2', source: 'a', target: 'c', sourceHandle: 'error', className: 'x', style: { strokeWidth: 2 } };
  const drawn = decorateErrorEdge(error);
  assert.equal(isErrorEdge(error), true);
  assert.equal(drawn.className, 'x edge-error');
  assert.equal(drawn.label, '실패 시');
  assert.equal(drawn.style.strokeDasharray, '6 4');
  assert.equal(drawn.style.strokeWidth, 2, '기존 스타일은 남긴다');
  assert.ok(String(drawn.style.stroke).includes('--ts-danger'));
  assert.equal(error.label, undefined, '원본은 바꾸지 않는다');

  const labelled = decorateErrorEdge({ ...error, label: '재시도 소진' });
  assert.equal(labelled.label, '재시도 소진', '사용자가 붙인 라벨이 우선');
});

test('retries 는 0~5 정수로, 비우면 키를 지운다', () => {
  assert.equal(normalizeRetries(''), undefined);
  assert.equal(normalizeRetries(null), undefined);
  assert.equal(normalizeRetries('0'), undefined);
  assert.equal(normalizeRetries('-2'), undefined);
  assert.equal(normalizeRetries('abc'), undefined);
  assert.equal(normalizeRetries('3'), 3);
  assert.equal(normalizeRetries(2.9), 2);
  assert.equal(normalizeRetries('99'), 5);
});

test('backoffSec 은 0~60 이고 0 은 유효(대기 없음)', () => {
  assert.equal(normalizeBackoffSec(''), undefined);
  assert.equal(normalizeBackoffSec('-1'), undefined);
  assert.equal(normalizeBackoffSec('x'), undefined);
  assert.equal(normalizeBackoffSec('0'), 0);
  assert.equal(normalizeBackoffSec('2.5'), 2.5);
  assert.equal(normalizeBackoffSec(1000), 60);
});

test('payload 중복 제거는 webhookNode 만, errorWorkflowId 는 양의 정수만', () => {
  assert.equal(supportsPayloadDedupe('webhookNode'), true);
  assert.equal(supportsPayloadDedupe('httpRequestNode'), false);
  assert.equal(errorWorkflowIdFrom({ errorWorkflowId: 7 }), 7);
  assert.equal(errorWorkflowIdFrom({ errorWorkflowId: '12' }), 12);
  assert.equal(errorWorkflowIdFrom({ errorWorkflowId: 0 }), null);
  assert.equal(errorWorkflowIdFrom({ errorWorkflowId: 'abc' }), null);
  assert.equal(errorWorkflowIdFrom({}), null);
  assert.equal(errorWorkflowIdFrom(null), null);
});
