import assert from 'node:assert/strict';
import test from 'node:test';
import { applyRunEvent, applyRunNote, isEventForProject, parseSseFrames, retryNote } from './runProgress.js';

test('SSE 프레임을 떼어 내고 주석·id 줄은 무시한다', () => {
  const chunk = 'event: ready\ndata: {"heartbeatSeconds": 15}\n\n: keepalive\n\nevent: run\nid: 3\ndata: {"type":"node_started","nodeId":"h","projectId":7}\n\nevent: run\ndata: {"type":"node_fin';
  const { frames, rest } = parseSseFrames(chunk);
  assert.equal(frames.length, 2, '완성된 프레임만 — keepalive 는 data 가 없어 빠진다');
  assert.deepEqual(frames[0], { event: 'ready', data: { heartbeatSeconds: 15 } });
  assert.equal(frames[1].event, 'run');
  assert.equal(frames[1].data.type, 'node_started');
  assert.equal(rest, 'event: run\ndata: {"type":"node_fin', '미완성 프레임은 다음 청크로');
  assert.deepEqual(parseSseFrames(''), { frames: [], rest: '' });
});

test('이벤트는 projectId 가 같을 때만 이 캔버스의 것이다', () => {
  assert.equal(isEventForProject({ projectId: 7 }, '7'), true);
  assert.equal(isEventForProject({ projectId: 7 }, 8), false);
  assert.equal(isEventForProject({ projectId: null }, 7), false);
  assert.equal(isEventForProject({ projectId: 7 }, null), false);
  assert.equal(isEventForProject(null, 7), false);
});

test('node_started/finished/retry 가 노드 상태를 running·success·error 로 바꾸고 나머지는 그대로', () => {
  let states = {};
  states = applyRunEvent(states, { type: 'node_started', nodeId: 'h' });
  assert.deepEqual(states, { h: 'running' });
  const same = applyRunEvent(states, { type: 'node_started', nodeId: 'h' });
  assert.equal(same, states, '변화가 없으면 같은 객체(리렌더 억제)');
  states = applyRunEvent(states, { type: 'node_finished', nodeId: 'h', status: 'failed' });
  assert.deepEqual(states, { h: 'error' });
  states = applyRunEvent(states, { type: 'node_retry', nodeId: 'h', attempt: 1, maxAttempts: 3 });
  assert.deepEqual(states, { h: 'running' });
  states = applyRunEvent(states, { type: 'node_finished', nodeId: 'h', status: 'succeeded' });
  assert.deepEqual(states, { h: 'success' });
  states = applyRunEvent(states, { type: 'node_finished', nodeId: 'p', status: 'pinned' });
  assert.equal(states.p, 'success', '고정 출력은 성공으로 그린다');
  assert.equal(applyRunEvent(states, { type: 'run_finished', status: 'succeeded' }), states);
  assert.equal(applyRunEvent(states, { type: 'weird', nodeId: 'h' }), states);
});

test('재시도 표시는 node_retry 가 붙이고 최종 node_finished 가 지운다', () => {
  let notes = {};
  const retry = { type: 'node_retry', nodeId: 'h', attempt: 1, maxAttempts: 3, errorCode: 'CONNECTOR_RATE_LIMITED' };
  assert.equal(retryNote(retry), '재시도 1/3');
  notes = applyRunNote(notes, { type: 'node_finished', nodeId: 'h', status: 'failed' });
  assert.deepEqual(notes, {}, '표시가 없을 때의 실패는 지울 것도 없다');
  notes = applyRunNote(notes, retry);
  assert.deepEqual(notes, { h: '재시도 1/3' });
  notes = applyRunNote(notes, { ...retry, attempt: 2 });
  assert.deepEqual(notes, { h: '재시도 2/3' });
  const untouched = applyRunNote(notes, { type: 'node_started', nodeId: 'other' });
  assert.equal(untouched, notes, '다른 노드는 건드리지 않는다');
  notes = applyRunNote(notes, { type: 'node_finished', nodeId: 'h', status: 'succeeded' });
  assert.deepEqual(notes, {});
});
