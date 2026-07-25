export const NodeRegistry = {
  slackNode: {
    type: 'slackNode',
    label: 'Slack 메세지',
    category: 'integration',
    color: '#0ea5e9', // e.g., skyblue for Slack
    headerColor: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
    fields: [
      { name: 'channel', type: 'text', label: '채널명 (예: #general)', placeholder: '#general' },
      { name: 'message', type: 'textarea', label: '메시지', placeholder: '보낼 메시지를 입력하세요' }
    ]
  },
  paymentLinkNode: {
    type: 'paymentLinkNode',
    label: '결제 링크 생성',
    category: 'integration',
    color: '#03c75a', // default green for Naver, or mixed
    headerColor: 'linear-gradient(135deg, #03c75a, #3182f6)',
    fields: [
      { name: 'provider', type: 'text', label: '결제사 (toss 또는 naver)', placeholder: 'toss' },
      { name: 'orderData', type: 'textarea', label: '주문 정보 데이터 (JSON, 텍스트 가능)', placeholder: '{{last_result}}' }
    ]
  },
  googleSheetsNode: {
    type: 'googleSheetsNode',
    label: '구글 시트',
    category: 'integration',
    color: '#0f9d58',
    headerColor: 'linear-gradient(135deg, #0f9d58, #34a853)',
    fields: [
      { name: 'mode', type: 'select', label: '동작', options: [
        { value: 'read', label: '읽기 (조회)' },
        { value: 'append', label: '추가 (맨 끝에 한 행)' },
        { value: 'write', label: '쓰기 (범위 덮어쓰기)' }
      ] },
      { name: 'spreadsheetId', type: 'text', label: '스프레드시트 ID', placeholder: '시트 URL의 /d/ 뒤에 있는 값' },
      { name: 'range', type: 'text', label: '시트/범위 (선택)', placeholder: '예: Sheet1 또는 Sheet1!A1:D10' },
      { name: 'values', type: 'textarea', label: '기록할 값 (JSON, 선택 — 비우면 직전 노드 출력 사용)', placeholder: '["값1", "값2"] (읽기 모드에서는 사용 안 함)' }
    ]
  },
  googleCalendarNode: {
    type: 'googleCalendarNode',
    label: '구글 캘린더',
    category: 'integration',
    color: '#4285f4',
    headerColor: 'linear-gradient(135deg, #4285f4, #34a853)',
    fields: [
      { name: 'mode', type: 'select', label: '동작', options: [
        { value: 'create', label: '일정 등록' },
        { value: 'list', label: '일정 조회' }
      ] },
      { name: 'calendarId', type: 'text', label: '캘린더 ID', placeholder: '예: your-email@gmail.com' },
      { name: 'eventData', type: 'textarea', label: '등록할 일정 (JSON, 선택 — 비우면 직전 노드 출력 사용, 등록 모드에서만 사용)', placeholder: '{"summary":"팀 회의","start":"2026-08-01T10:00:00+09:00","end":"2026-08-01T11:00:00+09:00"}' },
      { name: 'timeMin', type: 'text', label: '조회 시작 시각 (선택, 조회 모드에서만 사용)', placeholder: '비우면 지금부터' },
      { name: 'timeMax', type: 'text', label: '조회 종료 시각 (선택, 조회 모드에서만 사용)', placeholder: '예: 2026-08-31T23:59:59+09:00' },
      { name: 'maxResults', type: 'number', label: '최대 조회 개수 (선택, 조회 모드에서만 사용)', placeholder: '10' }
    ]
  },
  posterGeneratorNode: {
    type: 'posterGeneratorNode',
    label: '포스터/이미지 생성',
    category: 'action',
    color: '#f59e0b',
    headerColor: 'linear-gradient(135deg, #f59e0b, #ea580c)',
    fields: [
      { name: 'outputFormat', type: 'select', label: '출력 형식', options: [
        { value: 'png', label: 'PNG (이미지)' },
        { value: 'pdf', label: 'PDF' }
      ] },
      { name: 'width', type: 'number', label: '가로 (px)', placeholder: '900' },
      { name: 'height', type: 'number', label: '세로 (px)', placeholder: '1200' },
      { name: 'output_path', type: 'text', label: '저장 파일명 (선택)', placeholder: '비우면 자동 생성' }
    ]
  }
};
