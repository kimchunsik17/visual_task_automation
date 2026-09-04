import { createEditorCommandRegistry } from './editorCommands';

const noop = () => {};

const DOCUMENTATION_ACTIONS = {
  undo: noop,
  redo: noop,
  save: noop,
  copy: noop,
  cut: noop,
  paste: noop,
  duplicate: noop,
  selectAll: noop,
  clearSelection: noop,
  deleteSelection: noop,
  fitAll: noop,
  fitSelection: noop,
  arrangeSelection: noop,
  openCommandPalette: noop,
  showShortcuts: noop,
};

export const EDITOR_COMMAND_DOCUMENTATION = createEditorCommandRegistry(DOCUMENTATION_ACTIONS)
  .filter((command) => command.shortcuts.length > 0)
  .map(({ id, label, category, shortcuts }) => ({ id, label, category, shortcuts }));

export const EDITOR_CONVENIENCE_FEATURES = [
  {
    title: '명령 팔레트',
    description: '키보드만으로 저장, 정렬, 화면 맞춤 같은 편집 명령을 검색하고 실행합니다.',
  },
  {
    title: '캔버스 빠른 추가',
    description: '빈 캔버스를 더블 클릭해 원하는 노드를 바로 검색하고 추가합니다.',
  },
  {
    title: '연결하며 노드 생성',
    description: '연결선을 빈 공간에 놓으면 다음 노드를 선택해 연결된 상태로 생성합니다.',
  },
  {
    title: '노드 사이에 삽입',
    description: '기존 연결선에 노드를 끌어 놓아 흐름을 끊지 않고 중간 단계를 추가합니다.',
  },
  {
    title: '노드 교체',
    description: '위치와 연결 관계를 유지한 채 같은 종류의 노드로 바꿉니다.',
  },
  {
    title: '선택 항목 정렬',
    description: '여러 노드를 정렬하거나 가로·세로 간격을 균일하게 배치합니다.',
  },
  {
    title: '노드 검사 (입출력)',
    description: '노드 우클릭 → 노드 검사로 최근 실행의 입력과 출력을 그대로 확인하고 복사합니다.',
  },
  {
    title: '이 노드부터 실행',
    description: '샘플 입력을 고정해 두고 선택한 노드부터 하류만 실행합니다. 상류를 다시 돌리지 않습니다.',
  },
  {
    title: '문제 검사',
    description: '실행 없이 스키마·구조·컴파일을 검사하고, 문제를 클릭하면 해당 노드로 이동합니다.',
  },
  {
    title: '메모',
    description: '캔버스 우클릭 → 메모 추가로 스티키 노트를 남깁니다. 실행에는 포함되지 않습니다.',
  },
  {
    title: '위치 잠금',
    description: '완성된 영역의 노드를 실수로 끌지 않도록 우클릭 메뉴에서 위치를 잠급니다.',
  },
  {
    title: '캔버스 노드 검색',
    description: '명령 팔레트(⌘/Ctrl+K)에서 노드 이름을 검색해 큰 그래프에서도 바로 이동합니다.',
  },
];
