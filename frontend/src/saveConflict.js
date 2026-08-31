// 저장 충돌(HTTP 409) 안내 문구 (ADR-0006).
//
// 서버는 "내가 편집을 시작한 시점 이후 서버에서 무엇이 바뀌었는지"를 노드/엣지 id 목록으로
// 돌려준다. 사용자가 덮어쓸지 판단하려면 개수만으로는 부족하고, 그렇다고 id를 전부 늘어놓으면
// 읽히지 않는다 — 그래서 종류별 개수를 먼저 보여주고 노드 id는 몇 개만 예시로 덧붙인다.

const MAX_LISTED_IDS = 3;

const listIds = (ids) => {
  if (!ids || ids.length === 0) return '';
  const shown = ids.slice(0, MAX_LISTED_IDS).join(', ');
  return ids.length > MAX_LISTED_IDS ? ` (${shown} 외 ${ids.length - MAX_LISTED_IDS}개)` : ` (${shown})`;
};

export const summarizeGraphChanges = (diff) => {
  if (!diff) return [];
  const nodes = diff.nodes || {};
  const edges = diff.edges || {};
  const parts = [];
  if (nodes.added?.length) parts.push(`노드 ${nodes.added.length}개 추가${listIds(nodes.added)}`);
  if (nodes.removed?.length) parts.push(`노드 ${nodes.removed.length}개 삭제${listIds(nodes.removed)}`);
  if (nodes.changed?.length) parts.push(`노드 ${nodes.changed.length}개 설정 변경${listIds(nodes.changed)}`);
  if (edges.added?.length) parts.push(`연결 ${edges.added.length}개 추가`);
  if (edges.removed?.length) parts.push(`연결 ${edges.removed.length}개 삭제`);
  return parts;
};

export const describeSaveConflict = (conflict) => {
  const lines = ['다른 곳에서 이 워크플로우가 먼저 저장됐습니다.'];

  const serverChanges = summarizeGraphChanges(conflict?.server_changes_since_base);
  if (serverChanges.length) {
    lines.push('', `서버에서 바뀐 것 — ${serverChanges.join(' / ')}`);
  } else if (conflict?.current_summary) {
    // 내가 편집을 시작한 시점의 스냅샷이 없어 무엇이 바뀌었는지 계산하지 못한 경우
    // (예: 버전 기록이 도입되기 전에 만들어진 프로젝트).
    const { nodes = 0, edges = 0 } = conflict.current_summary;
    lines.push('', `서버의 현재 버전 — 노드 ${nodes}개, 연결 ${edges}개`);
  }

  lines.push('', '내 변경으로 덮어쓸까요?');
  lines.push('덮어써도 서버의 현재 버전은 저장 이력에 남아 있어 되돌릴 수 있습니다.');
  return lines.join('\n');
};
