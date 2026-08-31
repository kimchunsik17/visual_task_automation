function parseServerDate(value) {
  if (!value) return null;
  const text = String(value);
  const normalized = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatManagementDate(value) {
  const date = parseServerDate(value);
  return date ? date.toLocaleDateString('ko-KR') : '기록 없음';
}

export function formatManagementDateTime(value) {
  const date = parseServerDate(value);
  return date ? date.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' }) : '기록 없음';
}

export function shortResourceId(value, length = 12) {
  const text = String(value ?? '');
  if (!text) return '없음';
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

export function executionOutcomeLabel(value) {
  const normalized = String(value || '').toLowerCase();
  if (!normalized) return '실행 기록 없음';
  if (['success', 'succeeded', 'completed'].includes(normalized)) return '성공';
  if (['error', 'failed', 'failure'].includes(normalized)) return '실패';
  if (['running', 'pending'].includes(normalized)) return '진행 중';
  return value;
}
