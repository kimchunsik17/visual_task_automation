// 목록 화면들이 쓰는 시각 표기. 화면마다 복사해 두면 "방금 전" 의 기준이 조용히 갈린다.
//
// 서버가 주는 값에 타임존이 없으면 UTC 로 읽는다 — 브라우저는 타임존 없는 문자열을
// **로컬 시각**으로 읽어서, 그대로 두면 한국에서 9시간 전 일이 "9시간 뒤"가 된다.
function toDate(value) {
  if (!value) return null;
  const raw = String(value);
  const normalized = raw.match(/[zZ]|[+-]\d{2}:?\d{2}$/) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function timeAgo(value) {
  const date = toDate(value);
  if (!date) return '';
  const mins = Math.floor((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return '방금 전';
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}일 전`;
  return `${Math.floor(days / 30)}개월 전`;
}

export function formatDate(value, { empty = '기록 없음' } = {}) {
  const date = toDate(value);
  return date ? date.toLocaleDateString('ko-KR') : empty;
}
