// 템플릿 목록·소개 페이지가 함께 쓰는 표시 이름. 화면마다 복사해 두면 같은 값이 두 이름으로
// 불리는 날이 온다(목록은 "코드 노드", 소개는 "임의 코드" 같은 식).

export const CATEGORIES = [
  { id: '', label: '전체' },
  { id: 'automation', label: '자동화' },
  { id: 'content', label: '콘텐츠' },
  { id: 'data', label: '데이터' },
  { id: 'notification', label: '알림' },
  { id: 'document', label: '문서' },
  { id: 'etc', label: '기타' },
];

export const CATEGORY_LABEL = Object.fromEntries(
  CATEGORIES.filter((c) => c.id).map((c) => [c.id, c.label]),
);

// 위험 표시는 "이 템플릿이 무엇을 하는가" 를 말한다. 겁주는 말이 아니라 사실 서술이어야 한다.
export const RISK_LABEL = {
  arbitrary_code: '직접 작성한 코드 실행',
  arbitrary_url: '지정한 주소로 요청',
  database: '데이터베이스 읽기·쓰기',
  writes_files: '파일 생성',
  payment: '결제',
};

// 시작 방식. 서버 metadata 의 triggerType 과 짝이다(community_templates.graph_metadata).
export const TRIGGER_LABEL = {
  startNode: '수동 실행',
  scheduleNode: '정해진 시각마다',
  webhookNode: '웹훅 요청이 오면',
  gmailTriggerNode: '새 메일이 오면',
  rssTriggerNode: 'RSS 새 글이 올라오면',
  naverSearchTriggerNode: '네이버 검색 결과가 바뀌면',
  youtubeTriggerNode: '유튜브 새 영상이 올라오면',
  telegramTriggerNode: '텔레그램 메시지가 오면',
  discordTriggerNode: '디스코드 메시지가 오면',
};

// 자격증명 id 는 provider 키라 그대로 보여주면 읽기 어렵다. 모르는 값은 그대로 두고
// 아는 것만 사람 말로 바꾼다 — 표를 못 따라가 빈칸이 되는 쪽이 더 나쁘다.
const CREDENTIAL_LABEL = {
  openai: 'OpenAI', anthropic: 'Anthropic', google_gemini: 'Google Gemini',
  gmail_user_oauth: 'Gmail 연결', google_drive_user_oauth: 'Google Drive 연결',
  google_sheets_user_oauth: 'Google Sheets 연결', google_calendar_user_oauth: 'Google 캘린더 연결',
  naver_user_oauth: '네이버 연결', naver_search: '네이버 검색 API',
  slack_bot: 'Slack 봇', discord_bot: 'Discord 봇', telegram_bot: 'Telegram 봇',
  kakao_user_oauth: '카카오 연결', notion: 'Notion', youtube: 'YouTube API',
  data_go_kr: '공공데이터포털 인증키', juso: '도로명주소 승인키',
};

export function credentialLabel(id) {
  return CREDENTIAL_LABEL[id] || id;
}
