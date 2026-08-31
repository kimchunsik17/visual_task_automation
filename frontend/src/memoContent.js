export const MEMO_CONTENT_VERSION = 1;
export const MEMO_FONT_SIZE_OPTIONS = [12, 14, 16, 18, 20, 24];
export const DEFAULT_MEMO_FONT_SIZE = 14;

const appendSegment = (segments, text, bold = false, highlight = false) => {
  if (typeof text !== 'string' || text.length === 0) return;
  const normalized = { text, bold: Boolean(bold), highlight: Boolean(highlight) };
  const previous = segments[segments.length - 1];
  if (previous && previous.bold === normalized.bold && previous.highlight === normalized.highlight) {
    previous.text += normalized.text;
    return;
  }
  segments.push(normalized);
};

/**
 * 메모는 HTML 대신 텍스트와 허용된 두 가지 서식만 저장한다.
 * 예전 메모(data.text)는 이 모델로 읽되, 새 모델이 비어 있으면 빈 메모로 취급한다.
 */
export const normalizeMemoContent = (content, fallbackText = '') => {
  const hasStructuredContent = (
    content?.version === MEMO_CONTENT_VERSION
    && Array.isArray(content.segments)
  );
  const sourceSegments = hasStructuredContent
    ? content.segments
    : [{ text: typeof fallbackText === 'string' ? fallbackText : '' }];
  const segments = [];

  sourceSegments.forEach((segment) => {
    if (!segment || typeof segment.text !== 'string') return;
    appendSegment(segments, segment.text, segment.bold, segment.highlight);
  });

  return { version: MEMO_CONTENT_VERSION, segments };
};

export const memoContentToPlainText = (content, fallbackText = '') => (
  normalizeMemoContent(content, fallbackText).segments.map((segment) => segment.text).join('')
);

export const getMemoContentFingerprint = (content, fallbackText = '') => (
  JSON.stringify(normalizeMemoContent(content, fallbackText))
);

export const getMemoFontSize = (value) => {
  const numeric = Number(value);
  return MEMO_FONT_SIZE_OPTIONS.includes(numeric) ? numeric : DEFAULT_MEMO_FONT_SIZE;
};

