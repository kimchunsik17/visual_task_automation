// 섹션별 보조 내비게이션 정의 (HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN §4).
// 사이드바에는 1차 목적지만 두고, 섹션 안의 하위 페이지는 이 탭 정의를 SectionTabs 로
// 렌더링해 이동한다. 페이지마다 배열을 복사하면 항목 누락·경로 불일치가 생기므로 여기가 정본이다.

export const TUTORIAL_SECTION_TABS = [
  { label: '학습 센터', path: '/tutorial' },
  { label: '문서', path: '/documents' },
];

export const OPERATIONS_SECTION_TABS = [
  { label: '개요', path: '/operations', match: (pathname) => pathname === '/operations' },
  { label: '웹훅', path: '/operations/webhooks' },
  { label: '봇', path: '/operations/bots' },
  { label: '스케줄', path: '/operations/schedules' },
];

export const SETTINGS_SECTION_TABS = [
  { label: '프로필', path: '/settings/profile' },
  { label: '친구', path: '/settings/friends' },
  { label: '화면', path: '/settings/appearance' },
  { label: '토큰', path: '/settings/tokens' },
  { label: '데이터', path: '/settings/privacy' },
  { label: 'API 센터', path: '/settings/api-center' },
];

// 커뮤니티 섹션 (ADR-0021). Q&A 가 기본 목적지다 — 템플릿은 그 위에서 승격되는 계층이라
// 사람이 먼저 모이는 쪽을 앞에 둔다(§4.12 판단).
export const COMMUNITY_SECTION_TABS = [
  { label: 'Q&A', path: '/community/qna', match: (pathname) => pathname.startsWith('/community/qna') },
  { label: '템플릿', path: '/community/templates' },
];
