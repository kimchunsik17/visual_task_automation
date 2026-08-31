import { COMPONENT_DEFAULT_SIZES } from './appBuilderSchema.js';

/**
 * 컴포넌트 트리 편집 — 선택·복제·정렬·순서처럼 화면과 무관한 순수 함수들.
 * AppBuilderPage 는 이 함수들에 트리와 선택 id 만 넘기고 결과 트리를 setComponents 한다.
 * 모두 입력을 변경하지 않고 새 트리를 돌려준다.
 */

export const findComponent = (components, id) => {
  for (const component of components || []) {
    if (component.id === id) return component;
    if (component.children) {
      const found = findComponent(component.children, id);
      if (found) return found;
    }
  }
  return null;
};

export const updateComponent = (components, id, updater) => (components || []).map((component) => {
  if (component.id === id) return updater({ ...component });
  if (component.children) return { ...component, children: updateComponent(component.children, id, updater) };
  return component;
});

export const removeComponent = (components, id) => (components || [])
  .filter((component) => component.id !== id)
  .map((component) => (component.children
    ? { ...component, children: removeComponent(component.children, id) }
    : component));

export const collectIds = (components) => (components || []).flatMap((component) => [
  component.id,
  ...(component.children ? collectIds(component.children) : []),
]);

/** 해당 컴포넌트의 부모 id. 최상위면 'root', 없으면 null. */
export const findParentId = (components, id, parentId = 'root') => {
  for (const component of components || []) {
    if (component.id === id) return parentId;
    if (component.children) {
      const found = findParentId(component.children, id, component.id);
      if (found) return found;
    }
  }
  return null;
};

export const siblingsOf = (components, parentId) => (
  parentId === 'root' ? (components || []) : (findComponent(components, parentId)?.children || [])
);

/** 선택된 것들이 전부 같은 부모 아래에 있을 때만 그 부모 id 를 준다. 정렬·분배의 전제다. */
export const sharedParentId = (components, ids) => {
  if (!ids?.length) return null;
  const parents = new Set(ids.map((id) => findParentId(components, id)));
  if (parents.size !== 1) return null;
  const [parent] = parents;
  return parent ?? null;
};

export const pixelNumber = (value, fallback = 0) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && /^-?\d+(\.\d+)?px$/.test(value.trim())) return Number.parseFloat(value);
  return fallback;
};

const sizeOf = (component) => {
  const defaults = COMPONENT_DEFAULT_SIZES[component.type] || { width: 200, height: 45 };
  return {
    width: pixelNumber(component.props?.style?.width, defaults.width),
    height: pixelNumber(component.props?.style?.height, defaults.height),
  };
};

const positionOf = (component) => ({
  x: Number(component.props?.position?.x) || 0,
  y: Number(component.props?.position?.y) || 0,
});

const withPosition = (component, position) => ({
  ...component,
  props: { ...(component.props || {}), position },
});

const replaceSiblings = (components, parentId, nextSiblings) => (
  parentId === 'root'
    ? nextSiblings
    : updateComponent(components, parentId, (parent) => ({ ...parent, children: nextSiblings }))
);

/** 깊은 복사 + 모든 id 를 새로 발급. idFactory(type) 가 새 id 를 만든다. */
export const cloneWithNewIds = (component, idFactory) => {
  const props = JSON.parse(JSON.stringify(component.props || {}));
  return {
    ...component,
    id: idFactory(component.type),
    props,
    ...(component.children
      ? { children: component.children.map((child) => cloneWithNewIds(child, idFactory)) }
      : {}),
  };
};

/**
 * 선택한 컴포넌트를 각자의 부모 안에서 바로 뒤에 복제한다(offset 만큼 비껴서).
 * 조상이 함께 선택된 자손은 조상 복제에 포함되므로 따로 복제하지 않는다.
 */
export const duplicateComponents = (components, ids, idFactory, offset = { x: 20, y: 20 }) => {
  const selected = new Set(ids);
  const isNestedInSelection = (id) => {
    let parent = findParentId(components, id);
    while (parent && parent !== 'root') {
      if (selected.has(parent)) return true;
      parent = findParentId(components, parent);
    }
    return false;
  };

  const newIds = [];
  const duplicateLevel = (items) => items.flatMap((component) => {
    const next = component.children
      ? { ...component, children: duplicateLevel(component.children) }
      : component;
    if (!selected.has(component.id) || isNestedInSelection(component.id)) return [next];

    const clone = cloneWithNewIds(component, idFactory);
    const origin = positionOf(component);
    newIds.push(clone.id);
    return [next, withPosition(clone, { x: origin.x + offset.x, y: origin.y + offset.y })];
  });

  return { components: duplicateLevel(components || []), newIds };
};

/** 클립보드 조각(컴포넌트 배열)을 최상위에 붙인다. 원래 위치에서 offset 만큼 비껴 놓는다. */
export const pasteComponents = (components, clipboard, idFactory, offset = { x: 20, y: 20 }) => {
  const newIds = [];
  const pasted = (clipboard || []).map((component) => {
    const clone = cloneWithNewIds(component, idFactory);
    const origin = positionOf(component);
    newIds.push(clone.id);
    return withPosition(clone, { x: Math.max(0, origin.x + offset.x), y: Math.max(0, origin.y + offset.y) });
  });
  return { components: [...(components || []), ...pasted], newIds };
};

/** 조상이 같이 선택된 자손은 조상이 움직일 때 함께 가므로 제외한다. 복사할 때도 같은 기준이다. */
export const topLevelSelection = (components, ids) => {
  const selected = new Set(ids);
  return ids.filter((id) => {
    let parent = findParentId(components, id);
    while (parent && parent !== 'root') {
      if (selected.has(parent)) return false;
      parent = findParentId(components, parent);
    }
    return true;
  });
};

export const nudgeComponents = (components, ids, dx, dy) => (
  topLevelSelection(components, ids).reduce((tree, id) => updateComponent(tree, id, (component) => {
    const position = positionOf(component);
    return withPosition(component, { x: Math.max(0, position.x + dx), y: Math.max(0, position.y + dy) });
  }), components)
);

/**
 * 형제 안에서 그리기 순서를 바꾼다. 나중에 그려지는 형제가 위에 보인다.
 * direction: 'forward' | 'backward' | 'front' | 'back'
 */
export const reorderComponent = (components, id, direction) => {
  const parentId = findParentId(components, id);
  if (!parentId) return components;
  const siblings = siblingsOf(components, parentId);
  const index = siblings.findIndex((component) => component.id === id);
  if (index < 0) return components;

  const target = direction === 'front' ? siblings.length - 1
    : direction === 'back' ? 0
      : direction === 'forward' ? Math.min(siblings.length - 1, index + 1)
        : Math.max(0, index - 1);
  if (target === index) return components;

  const next = [...siblings];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved);
  return replaceSiblings(components, parentId, next);
};

export const ALIGN_MODES = Object.freeze(['left', 'hcenter', 'right', 'top', 'vcenter', 'bottom']);

/**
 * 같은 부모 아래의 선택 컴포넌트들을 정렬한다. 부모가 다르면 좌표계가 달라 의미가 없으므로
 * 트리를 그대로 돌려준다(호출한 쪽이 sharedParentId 로 미리 안내한다).
 */
export const alignComponents = (components, ids, mode) => {
  if (!ALIGN_MODES.includes(mode) || (ids?.length || 0) < 2) return components;
  if (!sharedParentId(components, ids)) return components;

  const boxes = ids.map((id) => {
    const component = findComponent(components, id);
    const position = positionOf(component);
    const size = sizeOf(component);
    return { id, ...position, ...size, right: position.x + size.width, bottom: position.y + size.height };
  });

  const minX = Math.min(...boxes.map((box) => box.x));
  const maxRight = Math.max(...boxes.map((box) => box.right));
  const minY = Math.min(...boxes.map((box) => box.y));
  const maxBottom = Math.max(...boxes.map((box) => box.bottom));
  const centerX = (minX + maxRight) / 2;
  const centerY = (minY + maxBottom) / 2;

  return boxes.reduce((tree, box) => updateComponent(tree, box.id, (component) => {
    const position = positionOf(component);
    const next = { ...position };
    if (mode === 'left') next.x = minX;
    if (mode === 'right') next.x = maxRight - box.width;
    if (mode === 'hcenter') next.x = Math.round(centerX - box.width / 2);
    if (mode === 'top') next.y = minY;
    if (mode === 'bottom') next.y = maxBottom - box.height;
    if (mode === 'vcenter') next.y = Math.round(centerY - box.height / 2);
    return withPosition(component, next);
  }), components);
};

/** 양 끝은 그대로 두고 사이 간격을 균등하게. axis: 'horizontal' | 'vertical'. 셋 이상일 때만. */
export const distributeComponents = (components, ids, axis) => {
  if ((ids?.length || 0) < 3 || !sharedParentId(components, ids)) return components;
  const horizontal = axis === 'horizontal';

  const boxes = ids.map((id) => {
    const component = findComponent(components, id);
    const position = positionOf(component);
    const size = sizeOf(component);
    return { id, start: horizontal ? position.x : position.y, length: horizontal ? size.width : size.height };
  }).sort((a, b) => a.start - b.start);

  const first = boxes[0];
  const last = boxes[boxes.length - 1];
  const totalLength = boxes.reduce((sum, box) => sum + box.length, 0);
  const span = (last.start + last.length) - first.start;
  const gap = (span - totalLength) / (boxes.length - 1);

  let cursor = first.start;
  return boxes.reduce((tree, box) => {
    const start = Math.round(cursor);
    cursor += box.length + gap;
    return updateComponent(tree, box.id, (component) => {
      const position = positionOf(component);
      return withPosition(component, horizontal ? { ...position, x: start } : { ...position, y: start });
    });
  }, components);
};

/** 선택한 것들의 너비/높이를 첫 번째 선택(기준)과 같게. dimension: 'width' | 'height'. */
export const matchSize = (components, ids, dimension) => {
  if ((ids?.length || 0) < 2 || !['width', 'height'].includes(dimension)) return components;
  const reference = findComponent(components, ids[0]);
  if (!reference) return components;
  const value = sizeOf(reference)[dimension];

  return ids.slice(1).reduce((tree, id) => updateComponent(tree, id, (component) => ({
    ...component,
    props: {
      ...(component.props || {}),
      style: { ...(component.props?.style || {}), [dimension]: `${value}px` },
    },
  })), components);
};
