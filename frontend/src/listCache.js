// listCache.js — 페이지 재마운트 사이에 마지막 목록 데이터를 보존하는 메모리 캐시.
//
// 각 페이지가 <MainSidebar/>와 함께 라우트마다 통째로 다시 마운트되므로, 목록을 매번
// 빈 상태에서 다시 불러오면 탭을 옮길 때마다 스켈레톤 → 실데이터로 내용 높이가
// 출렁인다(잔상 버그, MainSidebar 의 features 캐시와 같은 계열). 마지막 결과를 남겨
// 재방문 첫 프레임부터 실데이터를 그리고, 백그라운드 재조회로 따라잡는다.
//
// 사용 규칙: key 에 사용자 식별자를 포함해(예: `schedules:${user.id}`) 계정이 바뀌면
// 남의 캐시를 읽지 않게 한다. 새로고침하면 사라지는 세션 캐시다 — 목록은 개인 데이터라
// features 플래그와 달리 localStorage 에 남기지 않는다.
const cache = new Map();

// 캐시된 값 또는 null(아직 없음). 빈 배열도 유효한 캐시다 — null 과 구분해
// "빈 목록"과 "아직 모름"이 다르게 그려진다(빈 상태 문구 vs 스켈레톤).
export const readListCache = (key) => (cache.has(key) ? cache.get(key) : null);

export const writeListCache = (key, value) => { cache.set(key, value); };
