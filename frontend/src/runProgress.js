// 실행 진행 이벤트(GET /api/workflow-runs/stream, ENGINE-1 3단계 · ENGINE-3 node_retry)를 캔버스 상태로 접는다.
//
// 서버는 SSE 로 `event: run` 프레임을 보낸다(data 는 JSON: type·runId·projectId·nodeId …). type 은
//   node_started   → 그 노드 실행 중
//   node_finished  → status succeeded|failed|pinned
//   node_retry     → 재시도 가능한 오류 뒤 다음 시도 전(attempt/maxAttempts/errorCode/delaySec)
//   run_finished   → 실행 끝(status)
// 캔버스는 executionNodeStates({nodeId: 'running'|'success'|'error'}) 와 executionNotes({nodeId: '재시도 1/3'}) 를 갖는다.
// 여기 함수들은 순수하다 — EditorPage 의 SSE 효과가 프레임을 넘기고 결과를 setState 한다.

/** 버퍼에서 완성된 SSE 프레임을 떼어 낸다. 주석(: keepalive)·id 줄은 무시하고 {event, data} 만 돌려준다. */
export function parseSseFrames(buffer) {
  const parts = String(buffer ?? '').split('\n\n');
  const rest = parts.pop() ?? '';
  const frames = [];
  for (const part of parts) {
    let event = 'message';
    const dataLines = [];
    for (const line of part.split('\n')) {
      if (line.startsWith(':')) continue;
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length === 0) continue;
    let data = dataLines.join('\n');
    try {
      data = JSON.parse(data);
    } catch {
      // JSON 이 아니면 문자열 그대로 — ready/keepalive 류
    }
    frames.push({ event, data });
  }
  return { frames, rest };
}

export function isEventForProject(event, projectId) {
  if (!event || event.projectId === null || event.projectId === undefined) return false;
  if (projectId === null || projectId === undefined || projectId === '') return false;
  return String(event.projectId) === String(projectId);
}

/** executionNodeStates 갱신. 모르는 type 이나 nodeId 없는 이벤트는 그대로 둔다. */
export function applyRunEvent(states, event) {
  if (!event || !event.nodeId) return states;
  const id = String(event.nodeId);
  switch (event.type) {
    case 'node_started':
    case 'node_retry':
      return states[id] === 'running' ? states : { ...states, [id]: 'running' };
    case 'node_finished': {
      const next = event.status === 'failed' ? 'error' : 'success';
      return states[id] === next ? states : { ...states, [id]: next };
    }
    default:
      return states;
  }
}

export const retryNote = (event) => `재시도 ${event.attempt}/${event.maxAttempts}`;

/** executionNotes 갱신 — node_retry 가 붙이고, 그 노드의 다음 node_finished(최종 시도) 가 지운다. */
export function applyRunNote(notes, event) {
  if (!event || !event.nodeId) return notes;
  const id = String(event.nodeId);
  if (event.type === 'node_retry') {
    const note = retryNote(event);
    return notes[id] === note ? notes : { ...notes, [id]: note };
  }
  if ((event.type === 'node_finished' || event.type === 'node_started') && id in notes) {
    // 실패한 시도의 node_finished(failed) 는 node_retry 보다 먼저 오므로 그때는 아직 표시가 없다 — 지울 것도 없다.
    // 재시도 뒤의 최종 node_finished 만 여기 걸린다.
    const next = { ...notes };
    delete next[id];
    return next;
  }
  return notes;
}
