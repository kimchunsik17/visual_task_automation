export const MEMO_MIN_TEXTAREA_HEIGHT = 72;
// 헤더 + 서식 툴바 + 72px 편집 영역 + 내부 여백의 실제 최소 높이보다 작으면,
// 빈 메모를 추가하자마자 160→166px 재측정이 발생한다. 여유 2px를 둬 첫 측정을 없앤다.
export const MEMO_MIN_NODE_HEIGHT = 168;

/**
 * 메모 textarea를 내용 높이에 맞춘다.
 * 먼저 높이를 접어야 텍스트를 지운 경우에도 scrollHeight가 다시 작아진다.
 */
export const fitMemoTextareaToContent = (textarea, minHeight = MEMO_MIN_TEXTAREA_HEIGHT) => {
  if (!textarea) return minHeight;

  textarea.style.height = '0px';
  const nextHeight = Math.max(minHeight, Math.ceil(Number(textarea.scrollHeight) || 0));
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = 'hidden';
  return nextHeight;
};

export const getMemoRequiredHeight = ({
  contentTop,
  contentHeight,
  bottomPadding = 12,
  minHeight = MEMO_MIN_NODE_HEIGHT,
} = {}) => Math.max(
  minHeight,
  Math.ceil((Number(contentTop) || 0) + (Number(contentHeight) || 0) + (Number(bottomPadding) || 0)),
);
