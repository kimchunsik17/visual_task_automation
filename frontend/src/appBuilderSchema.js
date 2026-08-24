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
  terminal: { width: 400, height: 200 },
});

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

export const normalizeComponents = (components = [], canvas = DEFAULT_CANVAS) => {
  const normalizedCanvas = normalizeCanvas(canvas);

  const normalizeLevel = (items, availableWidth, startY = 30) => {
    let nextY = startY;

    return (items || []).map((component) => {
      const type = component.type || 'text';
      const defaults = COMPONENT_DEFAULT_SIZES[type] || { width: 200, height: 45 };
      const originalProps = component.props || {};
      const originalStyle = originalProps.style || {};
      const width = pixelSize(originalStyle.width, defaults.width, Math.max(availableWidth, 1));
      const height = pixelSize(originalStyle.height, defaults.height, 2000);
      const rawPosition = originalProps.position;
      const hasPosition = Number.isFinite(Number(rawPosition?.x)) && Number.isFinite(Number(rawPosition?.y));
      const position = hasPosition
        ? {
            x: Math.max(0, Math.min(Number(rawPosition.x), Math.max(availableWidth - width, 0))),
            y: Math.max(0, Number(rawPosition.y)),
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

  return convertLevel(components);
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
  const isControl = ['trigger', 'triggerOut'].includes(sourceHandle) && targetHandle === 'triggerIn';
  const isData = sourceHandle === 'dataOut' && ['dataIn', 'payloadIn'].includes(targetHandle);
  return isControl || isData;
};
