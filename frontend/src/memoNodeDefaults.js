import {
  DEFAULT_MEMO_FONT_SIZE,
  getMemoFontSize,
  memoContentToPlainText,
  normalizeMemoContent,
} from './memoContent.js';
import { MEMO_MIN_NODE_HEIGHT } from './memoSizing.js';

export const MEMO_DEFAULT_WIDTH = 260;

const positiveDimension = (...values) => {
  for (const value of values) {
    const numeric = typeof value === 'string' ? Number.parseFloat(value) : Number(value);
    if (Number.isFinite(numeric) && numeric > 0) return numeric;
  }
  return null;
};

/**
 * 메모는 첫 ResizeObserver 측정 전에 치수가 정해져 있어야 한다. 치수가 없는 메모가
 * auto 크기로 측정된 뒤 100% 크기로 바뀌면 React Flow observer가 같은 frame에서 다시 돈다.
 */
export const ensureMemoNodeDefaults = (node) => {
  if (!node || node.type !== 'memoNode') return node;

  const data = node.data || {};
  const width = positiveDimension(
    node.width,
    node.initialWidth,
    node.style?.width,
    data.memoSize?.width,
    MEMO_DEFAULT_WIDTH,
  );
  const height = Math.max(MEMO_MIN_NODE_HEIGHT, positiveDimension(
    node.height,
    node.initialHeight,
    node.style?.height,
    data.memoSize?.height,
    MEMO_MIN_NODE_HEIGHT,
  ));
  const manualWidth = positiveDimension(data.memoSize?.width, width);
  const manualHeight = Math.max(
    MEMO_MIN_NODE_HEIGHT,
    positiveDimension(data.memoSize?.height, node.height, MEMO_MIN_NODE_HEIGHT),
  );
  const hasStructuredContent = data.memoContent?.version === 1 && Array.isArray(data.memoContent.segments);
  const memoContent = hasStructuredContent
    ? data.memoContent
    : normalizeMemoContent(undefined, typeof data.text === 'string' ? data.text : '');
  const text = typeof data.text === 'string' ? data.text : memoContentToPlainText(memoContent);
  const memoFontSize = getMemoFontSize(data.memoFontSize ?? DEFAULT_MEMO_FONT_SIZE);

  const alreadyNormalized = (
    node.width === width
    && node.height === height
    && data.memoSize?.width === manualWidth
    && data.memoSize?.height === manualHeight
    && data.memoFontSize === memoFontSize
    && data.text === text
    && data.memoContent === memoContent
  );
  if (alreadyNormalized) return node;

  return {
    ...node,
    width,
    height,
    data: {
      ...data,
      text,
      memoContent,
      memoFontSize,
      memoSize: { width: manualWidth, height: manualHeight },
    },
  };
};

export const ensureMemoNodeDefaultsForList = (nodes = []) => {
  let changed = false;
  const normalized = nodes.map((node) => {
    const nextNode = ensureMemoNodeDefaults(node);
    if (nextNode !== node) changed = true;
    return nextNode;
  });
  return changed ? normalized : nodes;
};
