export const DEFAULT_CANVAS = Object.freeze({ width: 1024, height: 768, autoHeight: true });

export const COMPONENT_DEFAULT_SIZES = Object.freeze({
  container: { width: 480, height: 260 },
  text: { width: 300, height: 36 },
  button: { width: 180, height: 45 },
  input: { width: 300, height: 45 },
  textarea: { width: 300, height: 100 },
  dropdown: { width: 300, height: 45 },
  checkbox: { width: 200, height: 36 },
  divider: { width: 560, height: 2 },
  image: { width: 150, height: 150 },
  file: { width: 300, height: 96 },
  terminal: { width: 400, height: 200 },
  radio: { width: 300, height: 110 },
  slider: { width: 300, height: 64 },
  link: { width: 200, height: 32 },
  markdown: { width: 480, height: 240 },
  table: { width: 560, height: 220 },
  progress: { width: 300, height: 48 },
});

// 값을 입력받아 워크플로우 payload 에 실리는 컴포넌트. UIEngine 의 namedInputPayload 와
// 속성 패널의 "Input Key" 노출 기준이 이 목록 하나다.
export const INPUT_COMPONENT_TYPES = Object.freeze(['input', 'textarea', 'dropdown', 'checkbox', 'radio', 'slider', 'file']);

// 워크플로우 결과를 받아 보여주는 용도의 컴포넌트. Output 노드의 대상으로 안내한다.
export const OUTPUT_COMPONENT_TYPES = Object.freeze(['text', 'textarea', 'markdown', 'table', 'progress', 'image']);

const positiveNumber = (value, fallback) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

export const normalizeCanvas = (canvas) => ({
  width: positiveNumber(canvas?.width, DEFAULT_CANVAS.width),
  height: positiveNumber(canvas?.height, DEFAULT_CANVAS.height),
  autoHeight: canvas?.autoHeight !== false,
});

export const normalizeWorkflowMappings = (mappings = {}) => Object.fromEntries(
  Object.entries(mappings || {}).flatMap(([componentId, rawMapping]) => {
    const projectId = typeof rawMapping === 'object' && rawMapping !== null
      ? rawMapping.projectId ?? rawMapping.id
      : rawMapping;

    if (projectId === undefined || projectId === null || projectId === '') return [];

    return [[componentId, {
      ...(typeof rawMapping === 'object' && rawMapping !== null ? rawMapping : {}),
      projectId: String(projectId),
    }]];
  })
);

export const applyWorkflowMappings = (components = [], mappings = {}) => {
  const normalizedMappings = normalizeWorkflowMappings(mappings);

  return components.map((component) => {
    const mapping = normalizedMappings[component.id];
    const props = { ...(component.props || {}) };
    if (mapping) props.workflowId = mapping.projectId;

    return {
      ...component,
      props,
      ...(component.children
        ? { children: applyWorkflowMappings(component.children, normalizedMappings) }
        : {}),
    };
  });
};

const pixelSize = (value, fallback, max) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.min(Math.max(value, 1), max);
  }
  if (typeof value === 'string' && /^\d+(\.\d+)?px$/.test(value.trim())) {
    return Math.min(Math.max(Number.parseFloat(value), 1), max);
  }
  return fallback;
};

const pixelValue = (value, fallback = 0) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && /^\d+(\.\d+)?px$/.test(value.trim())) {
    return Number.parseFloat(value);
  }
  return fallback;
};

/**
 * 위치는 props.position 하나로만 정한다. style 에 이 키가 남아 있으면 렌더러가 style 을 그대로
 * spread 하면서 props.position 과 **합산**돼 컴포넌트가 계단처럼 어긋난다(2026-08-28 타이머 앱:
 * 버튼이 x+108, y+80 씩 밀리고 상태 문구는 캔버스 밖으로 나가 잘렸다).
 */
export const LAYOUT_STYLE_KEYS = Object.freeze(['position', 'left', 'top', 'right', 'bottom']);

const stripLayoutStyle = (style = {}) => {
  const clean = { ...style };
  LAYOUT_STYLE_KEYS.forEach((key) => { delete clean[key]; });
  return clean;
};

/**
 * style.left/top(px) 이 있으면 그것을 위치로 삼는다 — props.position 보다 우선한다.
 * AI 는 CSS 로 생각하기 때문에 둘이 어긋날 때 맞는 쪽은 거의 항상 CSS 다(타이머 앱에서
 * props.position 은 세로로 쌓인 값, style.top 은 카드 안 한 줄이었다). 정규화가 style 키를
 * 지우므로 한 번 저장되면 이 규칙은 다시 발동하지 않는다 — 사용자가 옮긴 위치를 되돌리지 않는다.
 */
const resolveDeclaredPosition = (props = {}) => {
  const style = props.style || {};
  const left = pixelValue(style.left, null);
  const top = pixelValue(style.top, null);
  if (left !== null && top !== null) return { x: left, y: top };
  const raw = props.position;
  if (Number.isFinite(Number(raw?.x)) && Number.isFinite(Number(raw?.y))) {
    return { x: Number(raw.x), y: Number(raw.y) };
  }
  return null;
};

export const normalizeComponents = (components = [], canvas = DEFAULT_CANVAS) => {
  const normalizedCanvas = normalizeCanvas(canvas);

  const normalizeLevel = (items, availableWidth, startY = 30) => {
    let nextY = startY;

    return (items || []).map((component) => {
      const type = component.type || 'text';
      const defaults = COMPONENT_DEFAULT_SIZES[type] || { width: 200, height: 45 };
      const originalProps = component.props || {};
      const originalStyle = stripLayoutStyle(originalProps.style || {});
      const width = pixelSize(originalStyle.width, defaults.width, Math.max(availableWidth, 1));
      const height = pixelSize(originalStyle.height, defaults.height, 2000);
      const declared = resolveDeclaredPosition(originalProps);
      const hasPosition = declared !== null;
      const position = hasPosition
        ? {
            x: Math.max(0, Math.min(declared.x, Math.max(availableWidth - width, 0))),
            y: Math.max(0, declared.y),
          }
        : { x: Math.max(0, Math.round((availableWidth - width) / 2)), y: nextY };

      if (!hasPosition) nextY += height + 16;

      const props = {
        ...originalProps,
        position,
        style: {
          ...originalStyle,
          width: `${width}px`,
          height: `${height}px`,
        },
      };

      const children = component.children
        ? normalizeLevel(component.children, width, 16)
        : component.children;

      return { ...component, type, props, ...(children ? { children } : {}) };
    });
  };

  return normalizeLevel(components, normalizedCanvas.width);
};

/**
 * 자식이 컨테이너 아래로 넘치면 컨테이너 높이를 늘린다. AI 가 준 컨테이너 높이는 자식 배치와
 * 따로 계산돼 어긋나기 쉽고, 컨테이너는 overflow 를 숨기지 않아 자식이 밖으로 튀어나온다.
 * 새로 생성된 레이아웃에만 적용한다 — 사용자가 편집한 크기는 건드리지 않는다.
 */
export const fitContainersToChildren = (components = []) => (components || []).map((component) => {
  if (!component.children?.length) return component;
  const children = fitContainersToChildren(component.children);
  const style = { ...(component.props?.style || {}) };
  const padding = pixelValue(String(style.padding || '').split(/\s+/)[0], 0);
  const bottom = children.reduce((max, child) => {
    const y = Number(child.props?.position?.y) || 0;
    const height = pixelValue(child.props?.style?.height, COMPONENT_DEFAULT_SIZES[child.type]?.height || 45);
    return Math.max(max, y + height);
  }, 0);
  const current = pixelValue(style.height, 0);
  const required = Math.ceil(bottom + padding);
  return {
    ...component,
    props: { ...(component.props || {}), style: required > current ? { ...style, height: `${required}px` } : style },
    children,
  };
});

export const makeGeneratedLayoutEditable = (components = []) => {
  const convertLevel = (items) => (items || []).map((component) => {
    const props = { ...(component.props || {}) };
    const style = { ...(props.style || {}) };
    let children = component.children ? convertLevel(component.children) : component.children;

    if (component.type === 'container' && children?.length && (props.layoutMode || 'absolute') !== 'absolute') {
      const layoutMode = props.layoutMode;
      const gap = pixelValue(style.gap, 12);
      const padding = pixelValue(String(style.padding || '').split(/\s+/)[0], 0);
      const columnsMatch = String(style.gridTemplateColumns || '').match(/repeat\(\s*(\d+)/);
      const columns = layoutMode === 'grid' ? Math.max(1, Number(columnsMatch?.[1]) || 2) : 1;
      let cursorX = padding;
      let cursorY = padding;
      let rowHeight = 0;

      children = children.map((child, index) => {
        const childStyle = child.props?.style || {};
        const width = pixelValue(childStyle.width, COMPONENT_DEFAULT_SIZES[child.type]?.width || 200);
        const height = pixelValue(childStyle.height, COMPONENT_DEFAULT_SIZES[child.type]?.height || 45);

        if (layoutMode === 'grid' && index > 0 && index % columns === 0) {
          cursorX = padding;
          cursorY += rowHeight + gap;
          rowHeight = 0;
        }

        const position = { x: cursorX, y: cursorY };
        if (layoutMode === 'row' || layoutMode === 'grid') cursorX += width + gap;
        if (layoutMode === 'column') cursorY += height + gap;
        rowHeight = Math.max(rowHeight, height);

        return {
          ...child,
          props: { ...(child.props || {}), position },
        };
      });
      props.layoutMode = 'absolute';
    }

    return {
      ...component,
      props: { ...props, style },
      ...(children ? { children } : {}),
    };
  });

  return fitContainersToChildren(convertLevel(components));
};

const scalePixelValue = (value, factor) => {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.round(value * factor * 100) / 100;
  if (typeof value === 'string' && /^\d+(\.\d+)?px$/.test(value.trim())) {
    return `${Math.round(Number.parseFloat(value) * factor * 100) / 100}px`;
  }
  return value;
};

export const scaleDescendantGeometry = (children = [], scaleX = 1, scaleY = 1) => (
  children.map((child) => ({
    ...child,
    props: {
      ...(child.props || {}),
      position: child.props?.position
        ? {
            x: Math.round((Number(child.props.position.x) || 0) * scaleX * 100) / 100,
            y: Math.round((Number(child.props.position.y) || 0) * scaleY * 100) / 100,
          }
        : child.props?.position,
      style: {
        ...(child.props?.style || {}),
        width: scalePixelValue(child.props?.style?.width, scaleX),
        height: scalePixelValue(child.props?.style?.height, scaleY),
      },
    },
    ...(child.children
      ? { children: scaleDescendantGeometry(child.children, scaleX, scaleY) }
      : {}),
  }))
);

export const requiredCanvasHeight = (components = [], minimum = DEFAULT_CANVAS.height) => {
  const bottom = components.reduce((maxBottom, component) => {
    const y = Number(component.props?.position?.y) || 0;
    const fallback = COMPONENT_DEFAULT_SIZES[component.type]?.height || 45;
    const height = pixelSize(component.props?.style?.height, fallback, 100000);
    return Math.max(maxBottom, y + height + 30);
  }, 0);

  return Math.max(minimum, Math.ceil(bottom));
};

export const resolveCanvas = (components = [], canvas = DEFAULT_CANVAS) => {
  const normalized = normalizeCanvas(canvas);
  return {
    ...normalized,
    height: normalized.autoHeight
      ? requiredCanvasHeight(components, normalized.height)
      : normalized.height,
  };
};

export const inferButtonActionMode = (props = {}, hasBlueprintTrigger = false) => {
  if (props.actionMode) return props.actionMode;
  if (props.onClickHandler) return 'script';
  if (hasBlueprintTrigger) return 'blueprint';
  if (props.workflowId) return 'workflow';
  return 'auto';
};

export const isValidLogicConnection = ({ sourceHandle, targetHandle }) => {
  // errorOut 은 Submit 노드의 실패 흐름이다(백로그 16) — 제어 흐름으로 연결된다.
  const isControl = ['trigger', 'triggerOut', 'errorOut'].includes(sourceHandle) && targetHandle === 'triggerIn';
  const isData = sourceHandle === 'dataOut' && ['dataIn', 'payloadIn'].includes(targetHandle);
  return isControl || isData;
};

/**
 * 버튼의 "워크플로우 연결"을 Trigger → Submit → Output 노드 3종으로 만들어주는 단축키(백로그 16).
 *
 * 실행 모델은 Blueprint 하나로 합치되, "버튼에 워크플로우 하나 고르면 끝"이라는 쉬운 경로는
 * 남긴다 — 드롭다운을 고르면 이 함수가 노드를 만들어주고, 만들어진 노드는 Blueprint 탭에서
 * 그대로 보이고 수정할 수 있다. 자동 변환을 숨기지 않는 것이 원칙이다(로드맵 §4.8).
 *
 * 이미 이 버튼의 트리거가 있으면 연결된 Submit 의 workflow 만 갱신한다 — 사용자가 Blueprint
 * 탭에서 손본 그래프를 덮어쓰지 않는다.
 */
export const buildSubmitChain = (componentId, projectId, nodes = [], edges = []) => {
  const trigger = nodes.find(
    (node) => node.type === 'triggerNode'
      && node.data?.componentId === componentId
      && (node.data?.eventType || 'onClick') === 'onClick'
  );

  if (trigger) {
    const submitEdge = edges.find((edge) => edge.source === trigger.id
      && nodes.some((node) => node.id === edge.target && node.type === 'submitNode'));
    if (submitEdge) {
      return {
        nodes: nodes.map((node) => (
          node.id === submitEdge.target
            ? { ...node, data: { ...node.data, projectId: String(projectId) } }
            : node
        )),
        edges,
        created: false,
      };
    }
    // 트리거는 있는데 Submit 이 없다(예: AI 가 만든 workflowNode 체인). 그래프를 임의로
    // 재배선하지 않고 그대로 둔다 — 사용자가 Blueprint 탭에서 직접 정리하는 편이 안전하다.
    return { nodes, edges, created: false };
  }

  const stamp = Date.now();
  const baseY = 60 + nodes.length * 40;
  const triggerId = `logic-trigger-${stamp}`;
  const submitId = `logic-submit-${stamp}`;
  const outputId = `logic-output-${stamp}`;

  return {
    nodes: [
      ...nodes,
      { id: triggerId, type: 'triggerNode', position: { x: 40, y: baseY },
        data: { id: triggerId, componentId, eventType: 'onClick' } },
      { id: submitId, type: 'submitNode', position: { x: 320, y: baseY },
        data: { id: submitId, projectId: String(projectId), fields: [] } },
      // 출력 대상을 추측하지 않는다 — 비워두면 하단 패널로 가고(직접 연결과 같은 동작),
      // 사용자가 Blueprint 탭에서 원하는 컴포넌트를 고른다.
      { id: outputId, type: 'outputNode', position: { x: 640, y: baseY },
        data: { id: outputId, componentId: '', resultPath: '', format: 'text' } },
    ],
    edges: [
      ...edges,
      { id: `${triggerId}-${submitId}`, source: triggerId, target: submitId,
        sourceHandle: 'trigger', targetHandle: 'triggerIn' },
      { id: `${submitId}-${outputId}`, source: submitId, target: outputId,
        sourceHandle: 'triggerOut', targetHandle: 'triggerIn' },
      { id: `${submitId}-${outputId}-data`, source: submitId, target: outputId,
        sourceHandle: 'dataOut', targetHandle: 'dataIn' },
    ],
    created: true,
  };
};
