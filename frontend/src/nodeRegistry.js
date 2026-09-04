export const NodeRegistry = {
  slackNode: {
    type: 'slackNode',
    icon: 'node-slack',
    label: 'Slack 발송',
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
    icon: 'node-payment-link',
    label: '결제 링크 생성',
    category: 'integration',
    color: '#03c75a', // default green for Naver, or mixed
    headerColor: 'linear-gradient(135deg, #03c75a, #3182f6)',
    fields: [
      { name: 'provider', type: 'text', label: '결제사 (toss 또는 naver)', placeholder: 'toss' },
      { name: 'orderData', type: 'textarea', label: '주문 정보 데이터 (JSON, 텍스트 가능)', placeholder: '{{last_result}}' }
    ]
  },
  // 결제 "조회" 노드 (paymentLinkNode 는 "생성"). 전에는 Sidebar 팔레트에만 하드코딩돼 있고
  // 캔버스 컴포넌트도 EditorPage 의 nodeTypes 등록도 없어서, 끌어놓거나 AI가 생성하면
  // ReactFlow 기본 노드(라벨만 있는 빈 상자)로 떨어져 아래 필드를 입력할 수가 없었다.
  // 여기로 옮겨서 DynamicNode 가 처리하게 한다. 필드는 backend/node_generators/integration_nodes.py
  // 의 generate_toss_node() 가 읽는 키와 정확히 일치해야 한다.
  tossNode: {
    type: 'tossNode',
    icon: 'node-toss-payments',
    label: '토스 결제 조회',
    category: 'integration',
    color: '#3b82f6',
    headerColor: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
    fields: [
      { name: 'secretKey', type: 'password', label: '시크릿 키 (Secret Key)', placeholder: 'test_sk_... 또는 live_sk_...' },
      { name: 'searchType', type: 'select', label: '조회 기준', options: [
        { value: 'paymentKey', label: 'paymentKey (결제 키로 조회)' },
        { value: 'orderId', label: 'orderId (주문 번호로 조회)' }
      ] },
      { name: 'searchValue', type: 'text', label: '조회 값 (선택 — 비우면 직전 노드 출력을 사용)', placeholder: '비워두면 직전 노드 결과로 조회' }
    ]
  },
  googleSheetsNode: {
    type: 'googleSheetsNode',
    icon: 'node-google-sheets',
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
    icon: 'node-google-calendar',
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
  imageGenerationNode: {
    type: 'imageGenerationNode',
    icon: 'node-poster-generator',
    label: '이미지 생성',
    category: 'ai',
    color: '#06b6d4',
    headerColor: 'linear-gradient(135deg, #0891b2, #7c3aed)',
    fields: []
  },
  posterGeneratorNode: {
    type: 'posterGeneratorNode',
    icon: 'node-poster-generator',
    label: '포스터 생성',
    category: 'action',
    color: '#f59e0b',
    headerColor: 'linear-gradient(135deg, #f59e0b, #ea580c)',
    fields: [
      { name: 'outputFormat', type: 'select', label: '출력 형식', options: [
        { value: 'png', label: 'PNG (이미지)' },
        { value: 'pdf', label: 'PDF' }
      ] },
      { name: 'backgroundPreset', type: 'select', label: '배경 프리셋', options: [
        { value: 'none', label: '사용 안 함 (HTML 배경 유지)' },
        { value: 'poster-01-midnight-grid', label: '01 · 미드나이트 그리드' },
        { value: 'poster-02-cobalt-orbits', label: '02 · 코발트 오빗' },
        { value: 'poster-03-violet-arches', label: '03 · 바이올렛 아치' },
        { value: 'poster-04-emerald-flow', label: '04 · 에메랄드 플로우' },
        { value: 'poster-05-layered-paper', label: '05 · 레이어드 페이퍼' },
        { value: 'poster-06-dot-matrix', label: '06 · 도트 매트릭스 (밝음)' },
        { value: 'poster-07-blueprint-lines', label: '07 · 블루프린트 라인' },
        { value: 'poster-08-diagonal-blocks', label: '08 · 다이애거널 블록 (밝음)' },
        { value: 'poster-09-emerald-wave', label: '09 · 에메랄드 웨이브' },
        { value: 'poster-10-neutral-editorial', label: '10 · 뉴트럴 에디토리얼 (밝음)' },
        { value: 'poster-11-concentric-frames', label: '11 · 컨센트릭 프레임' },
        { value: 'poster-12-sparse-geometry', label: '12 · 스파스 지오메트리' }
      ] },
      { name: 'width', type: 'number', label: '가로 (px)', placeholder: '900' },
      { name: 'height', type: 'number', label: '세로 (px)', placeholder: '1200' },
      { name: 'output_path', type: 'text', label: '저장 파일명 (선택)', placeholder: '비우면 자동 생성' }
    ]
  }
};
