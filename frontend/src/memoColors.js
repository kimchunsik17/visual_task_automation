export const DEFAULT_MEMO_COLOR = 'amber';

export const MEMO_COLOR_OPTIONS = Object.freeze([
  Object.freeze({
    id: 'amber', label: '노랑', swatch: '#eab308', accent: '#ca8a04',
    background: 'rgba(250, 204, 21, 0.10)', border: 'rgba(234, 179, 8, 0.65)',
  }),
  Object.freeze({
    id: 'rose', label: '분홍', swatch: '#fb7185', accent: '#fb7185',
    background: 'rgba(244, 63, 94, 0.11)', border: 'rgba(251, 113, 133, 0.65)',
  }),
  Object.freeze({
    id: 'sky', label: '하늘', swatch: '#38bdf8', accent: '#38bdf8',
    background: 'rgba(14, 165, 233, 0.11)', border: 'rgba(56, 189, 248, 0.65)',
  }),
  Object.freeze({
    id: 'emerald', label: '초록', swatch: '#34d399', accent: '#34d399',
    background: 'rgba(16, 185, 129, 0.11)', border: 'rgba(52, 211, 153, 0.65)',
  }),
  Object.freeze({
    id: 'violet', label: '보라', swatch: '#a78bfa', accent: '#a78bfa',
    background: 'rgba(139, 92, 246, 0.12)', border: 'rgba(167, 139, 250, 0.65)',
  }),
  Object.freeze({
    id: 'slate', label: '회색', swatch: '#94a3b8', accent: '#94a3b8',
    background: 'rgba(100, 116, 139, 0.13)', border: 'rgba(148, 163, 184, 0.65)',
  }),
]);

const MEMO_COLORS_BY_ID = new Map(MEMO_COLOR_OPTIONS.map((option) => [option.id, option]));

export const getMemoColorTheme = (colorId) => (
  MEMO_COLORS_BY_ID.get(colorId) || MEMO_COLORS_BY_ID.get(DEFAULT_MEMO_COLOR)
);
