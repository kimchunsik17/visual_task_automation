const UI_DATA_KEYS = new Set([
  'onChange',
  'onDelete',
  'onExpandChange',
  'onClearAIHighlight',
  'isAIModified',
  'aiChanges',
  'isTokenTrackingMode',
  'predictedTokens',
  'actualTokens',
  'tokenDisplayMode',
  'costCurrency',
  'isExecuting',
  'executionStatus',
  'onMemoAutoResize',
  'expandAllCommand',
]);

const TRANSIENT_NODE_KEYS = new Set([
  'selected',
  'dragging',
  'measured',
  'resizing',
  'internals',
]);

// 노드 data 에 실제로 쓰이는 자격증명성 키들. 여기 빠지면 복사/붙여넣기가 시크릿을
// OS 클립보드와 새 그래프에 복제한다(백엔드 로그 마스킹 ADR-0014 와 같은 원칙).
const SECRET_KEY_PATTERN = /^(?:password|secret|token|api_?key|access_?token|refresh_?token|private_?key|client_?secret|secret_?key|bot_?token|connection_?string|webhook_?url|smtp_?credentials)$/i;

export const EDITOR_CLIPBOARD_TYPE = 'agentforge/workflow-fragment';
export const EDITOR_CLIPBOARD_VERSION = 1;

// API 센터 reference 는 시크릿 원문이 아니라 실행 시점에 치환되는 안전한 자리표시자다 —
// 백엔드 로그 마스킹(usage_tracking.redact_payload_secrets)과 같은 규칙으로 보존한다.
const isCredentialReference = (value) => typeof value === 'string' && value.startsWith('{{API_CENTER:');

const clonePlainValue = (value, { redactSecrets = false } = {}) => {
  if (Array.isArray(value)) return value.map((child) => clonePlainValue(child, { redactSecrets }));
  if (value && typeof value === 'object') {
    const clean = {};
    Object.entries(value).forEach(([key, child]) => {
      if (typeof child === 'function') return;
      if (redactSecrets && SECRET_KEY_PATTERN.test(key) && !isCredentialReference(child)) {
        clean[key] = '';
        clean[`${key}NeedsConnection`] = true;
        return;
      }
      clean[key] = clonePlainValue(child, { redactSecrets });
    });
    return clean;
  }
  return value;
};

const stripNodeData = (data, { redactSecrets = false } = {}) => {
  const clean = {};
  Object.entries(data || {}).forEach(([key, value]) => {
    if (UI_DATA_KEYS.has(key) || typeof value === 'function') return;
    if (redactSecrets && SECRET_KEY_PATTERN.test(key) && !isCredentialReference(value)) {
      clean[key] = '';
      clean[`${key}NeedsConnection`] = true;
      return;
    }
    clean[key] = clonePlainValue(value, { redactSecrets });
  });
  return clean;
};

export const sanitizeNodeForSnapshot = (node, options = {}) => {
  const clean = {};
  Object.entries(node || {}).forEach(([key, value]) => {
    if (TRANSIENT_NODE_KEYS.has(key) || key === 'data' || typeof value === 'function') return;
    clean[key] = clonePlainValue(value);
  });
  clean.data = stripNodeData(node?.data, options);
  return clean;
};

export const createEditorSnapshot = (nodes = [], edges = []) => ({
  nodes: nodes.map((node) => sanitizeNodeForSnapshot(node)),
  edges: edges.map((edge) => {
    const clean = clonePlainValue(edge);
    delete clean.selected;
    return clean;
  }),
});

export const getSnapshotFingerprint = (snapshot) => JSON.stringify(snapshot);

export const createClipboardFragment = (nodes = [], edges = []) => {
  const selectedNodes = nodes.filter((node) => node.selected);
  const selectedIds = new Set(selectedNodes.map((node) => String(node.id)));
  const nodeById = new Map(nodes.map((node) => [String(node.id), node]));
  const getAbsolutePosition = (node) => {
    let x = Number(node.position?.x || 0);
    let y = Number(node.position?.y || 0);
    let parentId = node.parentNode;
    const visited = new Set();
    while (parentId && !visited.has(String(parentId))) {
      visited.add(String(parentId));
      const parent = nodeById.get(String(parentId));
      if (!parent) break;
      x += Number(parent.position?.x || 0);
      y += Number(parent.position?.y || 0);
      parentId = parent.parentNode;
    }
    return { x, y };
  };
  return {
    type: EDITOR_CLIPBOARD_TYPE,
    version: EDITOR_CLIPBOARD_VERSION,
    nodes: selectedNodes.map((node) => {
      const clean = sanitizeNodeForSnapshot(node, { redactSecrets: true });
      if (clean.parentNode && !selectedIds.has(String(clean.parentNode))) {
        clean.position = getAbsolutePosition(node);
        delete clean.parentNode;
        delete clean.extent;
      }
      return clean;
    }),
    edges: edges
      .filter((edge) => selectedIds.has(String(edge.source)) && selectedIds.has(String(edge.target)))
      .map((edge) => {
        const clean = clonePlainValue(edge);
        delete clean.selected;
        return clean;
      }),
  };
};

export const serializeClipboardFragment = (fragment) => JSON.stringify(fragment);

export const parseClipboardFragment = (text) => {
  try {
    const parsed = JSON.parse(text);
    if (
      parsed?.type !== EDITOR_CLIPBOARD_TYPE
      || parsed?.version !== EDITOR_CLIPBOARD_VERSION
      || !Array.isArray(parsed.nodes)
      || !Array.isArray(parsed.edges)
    ) return null;
    return parsed;
  } catch {
    return null;
  }
};

// 노드/엣지 id 는 백엔드가 생성하는 파이썬 코드의 변수 이름에 그대로 들어간다. 그래서 서버의
// 보안 검증기(workflow_security.SAFE_NODE_ID)는 식별자 문자([A-Za-z0-9_])만 허용하고, 하이픈이
// 든 UUID 가 섞인 그래프는 "unsafe node id" 로 실행 자체가 거부된다. 여기서 만드는 id 는 항상
// 그 규칙을 만족해야 한다.
export const SAFE_ENTITY_ID = /^[A-Za-z_][A-Za-z0-9_]*$/;

export const toSafeEntityId = (value) => {
  const cleaned = String(value ?? '').replace(/[^A-Za-z0-9_]/g, '_');
  return /^[A-Za-z_]/.test(cleaned) ? cleaned : `n_${cleaned}`;
};

export const makeEntityId = (prefix = 'node') => {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${globalThis.crypto.randomUUID().replace(/-/g, '')}`;
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
};

/**
 * 저장된 그래프의 노드 id 를 서버가 받아주는 형태로 정규화한다(엣지 source/target/parentNode 도 함께).
 * 하이픈 UUID 로 저장된 프로젝트가 열릴 때 한 번 고쳐 주기 위한 것이다 — 바꿀 것이 없으면
 * 입력 배열을 그대로 돌려준다.
 */
export const normalizeGraphIds = (nodes = [], edges = []) => {
  const idMap = new Map();
  const taken = new Set(nodes.map((node) => String(node.id)));
  nodes.forEach((node) => {
    const original = String(node.id);
    if (SAFE_ENTITY_ID.test(original)) return;
    let candidate = toSafeEntityId(original);
    while (taken.has(candidate) && candidate !== original) candidate = `${candidate}_${Math.random().toString(36).slice(2, 6)}`;
    taken.add(candidate);
    idMap.set(original, candidate);
  });
  if (idMap.size === 0) return { nodes, edges, changed: false };
  const remap = (value) => (value == null ? value : (idMap.get(String(value)) ?? value));
  return {
    changed: true,
    nodes: nodes.map((node) => ({
      ...node,
      id: remap(node.id),
      ...(node.parentNode ? { parentNode: remap(node.parentNode) } : {}),
    })),
    edges: edges.map((edge) => ({
      ...edge,
      source: remap(edge.source),
      target: remap(edge.target),
      ...(edge.id ? { id: `e_${remap(edge.source)}-${remap(edge.target)}${edge.sourceHandle ? `_${edge.sourceHandle}` : ''}` } : {}),
    })),
  };
};

/**
 * 분리 텍스트(popout, `detachedText` 노드)를 흡수한다 — 데이터 흐름 분리 계획 §5-7.
 *
 * popout 은 필드를 캔버스로 빼내 보여주기만 하는 시각 효과였고 실행 계약이 없었다(생성 코드는
 * 원래 필드만 읽는다). 필드를 밖으로 빼는 일은 이제 변수 허브 + 데이터 바인딩이 맡으므로,
 * 저장된 그래프를 **열 때 한 번** 값을 원래 필드로 되돌리고 분리 노드를 없앤다. 값은 보존한다.
 */
export const absorbDetachedText = (nodes = [], edges = []) => {
  const detached = nodes.filter((node) => node.type === 'detachedText');
  const strayFlags = nodes.some((node) => Object.keys(node.data || {})
    .some((key) => key.startsWith('isDetached_')));
  if (detached.length === 0 && !strayFlags) return { nodes, edges, changed: false };

  // 분리 노드에 있던 값이 정본이다 — 분리된 동안 사용자는 그쪽을 편집했다.
  const restored = new Map();
  detached.forEach((node) => {
    const sourceId = String(node.data?.sourceId ?? '');
    const fieldKey = node.data?.fieldKey;
    if (!sourceId || !fieldKey) return;
    const perNode = restored.get(sourceId) || {};
    perNode[fieldKey] = node.data?.value ?? '';
    restored.set(sourceId, perNode);
  });

  const removedIds = new Set(detached.map((node) => String(node.id)));
  return {
    changed: true,
    nodes: nodes
      .filter((node) => !removedIds.has(String(node.id)))
      .map((node) => {
        const values = restored.get(String(node.id));
        const data = { ...(node.data || {}), ...(values || {}) };
        Object.keys(data).forEach((key) => { if (key.startsWith('isDetached_')) delete data[key]; });
        return { ...node, data };
      }),
    edges: edges.filter((edge) => !removedIds.has(String(edge.source)) && !removedIds.has(String(edge.target))),
  };
};

export const materializeClipboardFragment = (fragment, offset = { x: 40, y: 40 }) => {
  if (!fragment?.nodes?.length) return { nodes: [], edges: [] };

  const idMap = new Map(fragment.nodes.map((node) => [String(node.id), makeEntityId('node')]));
  const nodes = fragment.nodes.map((node) => {
    const parentId = node.parentNode ? idMap.get(String(node.parentNode)) : null;
    const next = {
      ...clonePlainValue(node),
      id: idMap.get(String(node.id)),
      position: {
        x: Number(node.position?.x || 0) + (parentId ? 0 : Number(offset.x || 0)),
        y: Number(node.position?.y || 0) + (parentId ? 0 : Number(offset.y || 0)),
      },
      selected: true,
    };
    if (parentId) next.parentNode = parentId;
    else if (next.parentNode) {
      delete next.parentNode;
      delete next.extent;
    }
    return next;
  });
  const edges = fragment.edges.map((edge) => ({
    ...clonePlainValue(edge),
    id: makeEntityId('edge'),
    source: idMap.get(String(edge.source)),
    target: idMap.get(String(edge.target)),
    selected: false,
  }));

  return { nodes, edges };
};

export const isEditableShortcutTarget = (target) => Boolean(
  typeof Element !== 'undefined'
  && target instanceof Element
  && target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"], .monaco-editor')
);

const getNodeSize = (node) => ({
  width: Number(node.measured?.width || node.width || 240),
  height: Number(node.measured?.height || node.height || 160),
});

export const arrangeSelectedNodes = (nodes = [], arrangement) => {
  const selected = nodes.filter((node) => node.selected);
  if (selected.length < 2) return nodes;

  const groups = new Map();
  selected.forEach((node) => {
    const parentKey = node.parentNode ? String(node.parentNode) : '__canvas__';
    groups.set(parentKey, [...(groups.get(parentKey) || []), node]);
  });

  const positions = new Map();
  groups.forEach((group) => {
    if (group.length < 2) return;
    const metrics = group.map((node) => {
      const size = getNodeSize(node);
      return {
        node,
        ...size,
        left: Number(node.position?.x || 0),
        top: Number(node.position?.y || 0),
        right: Number(node.position?.x || 0) + size.width,
        bottom: Number(node.position?.y || 0) + size.height,
      };
    });
    const left = Math.min(...metrics.map((item) => item.left));
    const right = Math.max(...metrics.map((item) => item.right));
    const top = Math.min(...metrics.map((item) => item.top));
    const bottom = Math.max(...metrics.map((item) => item.bottom));
    const centerX = (left + right) / 2;
    const centerY = (top + bottom) / 2;

    if (arrangement === 'distribute-horizontal' && metrics.length >= 3) {
      const ordered = [...metrics].sort((a, b) => a.left - b.left);
      const totalWidth = ordered.reduce((sum, item) => sum + item.width, 0);
      const gap = (right - left - totalWidth) / (ordered.length - 1);
      let cursor = left;
      ordered.forEach((item) => {
        positions.set(String(item.node.id), { x: cursor, y: item.top });
        cursor += item.width + gap;
      });
      return;
    }

    if (arrangement === 'distribute-vertical' && metrics.length >= 3) {
      const ordered = [...metrics].sort((a, b) => a.top - b.top);
      const totalHeight = ordered.reduce((sum, item) => sum + item.height, 0);
      const gap = (bottom - top - totalHeight) / (ordered.length - 1);
      let cursor = top;
      ordered.forEach((item) => {
        positions.set(String(item.node.id), { x: item.left, y: cursor });
        cursor += item.height + gap;
      });
      return;
    }

    metrics.forEach((item) => {
      let x = item.left;
      let y = item.top;
      if (arrangement === 'align-left') x = left;
      if (arrangement === 'align-center-horizontal') x = centerX - item.width / 2;
      if (arrangement === 'align-right') x = right - item.width;
      if (arrangement === 'align-top') y = top;
      if (arrangement === 'align-center-vertical') y = centerY - item.height / 2;
      if (arrangement === 'align-bottom') y = bottom - item.height;
      positions.set(String(item.node.id), { x, y });
    });
  });

  if (!positions.size) return nodes;
  return nodes.map((node) => {
    const position = positions.get(String(node.id));
    return position ? { ...node, position } : node;
  });
};

const matchesShortcut = (event, shortcut) => {
  const key = event.key.toLowerCase();
  const matchesKey = key === shortcut.key.toLowerCase()
    || (/^[0-9]$/.test(shortcut.key) && event.code === `Digit${shortcut.key}`);
  const wantsMod = shortcut.mod === true;
  const hasMod = event.ctrlKey || event.metaKey;
  return matchesKey
    && (!wantsMod || hasMod)
    && (wantsMod || !hasMod)
    && Boolean(shortcut.shift) === event.shiftKey
    && Boolean(shortcut.alt) === event.altKey;
};

export const formatEditorShortcut = (shortcut, platform) => {
  if (shortcut.key === '?') return '?';
  const platformValue = platform || (
    typeof navigator !== 'undefined' ? `${navigator.platform || ''} ${navigator.userAgent || ''}` : ''
  );
  const isMac = /Mac|iPhone|iPad/i.test(platformValue);
  const keys = [];
  if (shortcut.mod) keys.push(isMac ? '⌘' : 'Ctrl');
  if (shortcut.shift) keys.push('Shift');
  if (shortcut.alt) keys.push(isMac ? 'Option' : 'Alt');
  const keyLabel = shortcut.key === 'escape'
    ? 'Esc'
    : shortcut.key.length === 1 ? shortcut.key.toUpperCase() : shortcut.key;
  keys.push(keyLabel);
  return keys.join('+');
};

export const createEditorCommandRegistry = (actions) => [
  {
    id: 'history.undo', label: '되돌리기', category: '편집', shortcuts: [{ mod: true, key: 'z' }],
    when: (context) => context.canUndo && !context.isTextEditing,
    execute: actions.undo,
  },
  {
    id: 'history.redo', label: '다시 실행', category: '편집',
    shortcuts: [{ mod: true, shift: true, key: 'z' }, { mod: true, key: 'y' }],
    when: (context) => context.canRedo && !context.isTextEditing,
    execute: actions.redo,
  },
  {
    id: 'project.save', label: '저장', category: '프로젝트', shortcuts: [{ mod: true, key: 's' }],
    when: (context) => context.isOwner,
    execute: actions.save,
  },
  {
    // §7.1 — 선택한 노드를 한 단계만, 외부 호출 없이 돌려본다. "기본은 mock" 이라 단축키도 목업이다.
    id: 'selection.testNode', label: '선택 노드 목업 테스트', category: '실행',
    shortcuts: [{ alt: true, key: 'Enter' }],
    when: (context) => context.selectedNodeCount === 1 && context.isOwner && !context.isTextEditing,
    execute: actions.testSelectedNode,
  },
  {
    id: 'selection.copy', label: '선택 항목 복사', category: '편집', shortcuts: [{ mod: true, key: 'c' }],
    when: (context) => context.selectedNodeCount > 0 && !context.isTextEditing,
    execute: actions.copy,
  },
  {
    id: 'selection.cut', label: '선택 항목 잘라내기', category: '편집', shortcuts: [{ mod: true, key: 'x' }],
    when: (context) => context.selectedNodeCount > 0 && context.isOwner && !context.isTextEditing,
    execute: actions.cut,
  },
  {
    id: 'selection.paste', label: '붙여넣기', category: '편집', shortcuts: [{ mod: true, key: 'v' }],
    when: (context) => context.isOwner && !context.isTextEditing,
    execute: actions.paste,
  },
  {
    id: 'selection.duplicate', label: '선택 항목 복제', category: '편집', shortcuts: [{ mod: true, key: 'd' }],
    when: (context) => context.selectedNodeCount > 0 && context.isOwner && !context.isTextEditing,
    execute: actions.duplicate,
  },
  {
    id: 'selection.all', label: '모든 노드 선택', category: '선택', shortcuts: [{ mod: true, key: 'a' }],
    when: (context) => context.hasNodes && !context.isTextEditing,
    execute: actions.selectAll,
  },
  {
    id: 'selection.none', label: '선택 해제', category: '선택', shortcuts: [{ key: 'escape' }],
    when: (context) => context.hasSelection && !context.isTextEditing,
    execute: actions.clearSelection,
  },
  {
    id: 'selection.delete', label: '선택 항목 삭제', category: '편집', shortcuts: [],
    when: (context) => context.hasSelection && context.isOwner && !context.isTextEditing,
    execute: actions.deleteSelection,
  },
  {
    id: 'viewport.fit-all', label: '전체 화면 맞춤', category: '화면', shortcuts: [{ shift: true, key: '1' }],
    when: (context) => context.hasNodes && !context.isTextEditing,
    execute: actions.fitAll,
  },
  {
    id: 'viewport.fit-selection', label: '선택 영역 화면 맞춤', category: '화면', shortcuts: [{ shift: true, key: '2' }],
    when: (context) => context.selectedNodeCount > 0 && !context.isTextEditing,
    execute: actions.fitSelection,
  },
  ...[
    ['layout.align-left', '왼쪽 정렬', 'align-left'],
    ['layout.align-center-horizontal', '가로 가운데 정렬', 'align-center-horizontal'],
    ['layout.align-right', '오른쪽 정렬', 'align-right'],
    ['layout.align-top', '위쪽 정렬', 'align-top'],
    ['layout.align-center-vertical', '세로 가운데 정렬', 'align-center-vertical'],
    ['layout.align-bottom', '아래쪽 정렬', 'align-bottom'],
  ].map(([id, label, arrangement]) => ({
    id, label, category: '배치', shortcuts: [],
    when: (context) => context.selectedNodeCount >= 2 && context.isOwner && !context.isTextEditing,
    execute: () => actions.arrangeSelection(arrangement, label),
  })),
  ...[
    ['layout.distribute-horizontal', '가로 간격 동일', 'distribute-horizontal'],
    ['layout.distribute-vertical', '세로 간격 동일', 'distribute-vertical'],
  ].map(([id, label, arrangement]) => ({
    id, label, category: '배치', shortcuts: [],
    when: (context) => context.selectedNodeCount >= 3 && context.isOwner && !context.isTextEditing,
    execute: () => actions.arrangeSelection(arrangement, label),
  })),
  {
    // 데이터 레이어(계획 DATA_FLOW_SEPARATION_PLAN §5-2). mod+d 는 복제가 쓰고 있어 맨 키 d 다.
    id: 'view.dataLayer', label: '데이터 레이어 토글', category: '화면', shortcuts: [{ key: 'd' }],
    when: (context) => !context.isTextEditing,
    execute: actions.toggleDataLayer,
  },
  {
    id: 'palette.open', label: '명령 팔레트 열기', category: '도구', shortcuts: [{ mod: true, key: 'k' }],
    when: () => true,
    execute: actions.openCommandPalette,
  },
  {
    id: 'help.shortcuts', label: '단축키 도움말', category: '도움말', shortcuts: [{ shift: true, key: '?' }],
    when: (context) => !context.isTextEditing,
    execute: actions.showShortcuts,
  },
];

export const findCommandForKeyboardEvent = (commands, event, context) => commands.find((command) => (
  command.shortcuts.some((shortcut) => matchesShortcut(event, shortcut))
  && command.when(context)
));
