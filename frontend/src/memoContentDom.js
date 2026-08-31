import { MEMO_CONTENT_VERSION, normalizeMemoContent } from './memoContent';

const appendSegment = (segments, text, bold, highlight) => {
  if (!text) return;
  const previous = segments[segments.length - 1];
  if (previous && previous.bold === bold && previous.highlight === highlight) {
    previous.text += text;
    return;
  }
  segments.push({ text, bold, highlight });
};

const selectionRangeInside = (root) => {
  const selection = root?.ownerDocument?.defaultView?.getSelection?.();
  if (!selection || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  return { selection, range };
};

const selectInsertedNode = (selection, node) => {
  const nextRange = node.ownerDocument.createRange();
  nextRange.selectNodeContents(node);
  selection.removeAllRanges();
  selection.addRange(nextRange);
};

/** DOM을 허용 목록 기반의 메모 조각으로 읽는다. 임의 태그와 속성은 저장되지 않는다. */
export const readMemoContentFromElement = (root) => {
  const segments = [];

  // Chromium은 contentEditable의 마지막 글자를 지우면 빈 DOM 대신 <br>만 남길 수 있다.
  // 우리 Enter 처리는 실제 \n 텍스트 노드를 넣으므로 textContent가 빈 경우는 빈 메모가 맞다.
  if (!root?.textContent) {
    return normalizeMemoContent({ version: MEMO_CONTENT_VERSION, segments });
  }

  const walk = (node, inheritedBold = false, inheritedHighlight = false) => {
    if (node.nodeType === 3) {
      appendSegment(segments, node.nodeValue || '', inheritedBold, inheritedHighlight);
      return;
    }
    if (node.nodeType !== 1) return;

    const tagName = node.tagName?.toUpperCase?.() || '';
    if (tagName === 'BR') {
      appendSegment(segments, '\n', inheritedBold, inheritedHighlight);
      return;
    }

    const bold = inheritedBold || tagName === 'STRONG' || tagName === 'B';
    const highlight = inheritedHighlight || tagName === 'MARK';
    const isBlock = tagName === 'DIV' || tagName === 'P';
    const hadContent = segments.length > 0;
    if (isBlock && hadContent && !segments[segments.length - 1].text.endsWith('\n')) {
      appendSegment(segments, '\n', bold, highlight);
    }
    node.childNodes.forEach((child) => walk(child, bold, highlight));
  };

  root?.childNodes?.forEach((child) => walk(child));
  return normalizeMemoContent({ version: MEMO_CONTENT_VERSION, segments });
};

/** 저장된 조각을 textContent만으로 렌더링한다. 저장 데이터가 HTML로 실행될 수 없다. */
export const renderMemoContentToElement = (root, content, fallbackText = '') => {
  if (!root) return;
  const documentRef = root.ownerDocument;
  const fragment = documentRef.createDocumentFragment();
  const normalized = normalizeMemoContent(content, fallbackText);

  normalized.segments.forEach((segment) => {
    let node = documentRef.createTextNode(segment.text);
    if (segment.bold) {
      const strong = documentRef.createElement('strong');
      strong.appendChild(node);
      node = strong;
    }
    if (segment.highlight) {
      const mark = documentRef.createElement('mark');
      mark.appendChild(node);
      node = mark;
    }
    fragment.appendChild(node);
  });

  root.replaceChildren(fragment);
};

export const insertMemoPlainTextAtSelection = (root, text) => {
  if (!root || typeof text !== 'string') return false;
  root.focus();
  let selectionState = selectionRangeInside(root);
  if (!selectionState) {
    const selection = root.ownerDocument.defaultView.getSelection();
    const range = root.ownerDocument.createRange();
    range.selectNodeContents(root);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    selectionState = { selection, range };
  }

  const { selection, range } = selectionState;
  range.deleteContents();
  const textNode = root.ownerDocument.createTextNode(text);
  range.insertNode(textNode);
  const nextRange = root.ownerDocument.createRange();
  nextRange.setStartAfter(textNode);
  nextRange.collapse(true);
  selection.removeAllRanges();
  selection.addRange(nextRange);
  return true;
};

export const applyMemoInlineFormat = (root, format) => {
  const selectionState = selectionRangeInside(root);
  if (!selectionState || selectionState.range.collapsed) return false;
  const { selection, range } = selectionState;
  const wrapper = root.ownerDocument.createElement(format === 'highlight' ? 'mark' : 'strong');
  wrapper.appendChild(range.extractContents());
  range.insertNode(wrapper);
  selectInsertedNode(selection, wrapper);
  return true;
};

export const clearMemoInlineFormat = (root) => {
  const selectionState = selectionRangeInside(root);
  if (!selectionState || selectionState.range.collapsed) return false;
  const { selection, range } = selectionState;
  const extracted = range.extractContents();
  const plainTextNode = root.ownerDocument.createTextNode(extracted.textContent || '');
  range.insertNode(plainTextNode);
  selectInsertedNode(selection, plainTextNode);
  return true;
};
