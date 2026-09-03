// 노드 문서 (제품 문서 /documents/nodes/:type 의 본문).
//
// 라벨·색·아이콘·카테고리는 editorNodeCatalog, 필드의 종류·선택지·기본값은
// NodeDefinitions/NodeRegistry 가 정본이고, 이 파일은 **사람이 읽는 설명**만 담는다.
// 동작 설명의 근거는 backend/meta_agent.py 의 NODE_CATALOG 와
// node_definitions/<type>.json 의 llm.description 이다 — 노드 동작을 바꿀 때
// 그쪽 설명을 고쳤다면 여기도 함께 고칠 것.
//
// 형태:
//   summary : 한 줄 요약 (목록 카드와 상세 헤더)
//   details : 동작 설명 문단들
//   usage   : "이런 요청에 쓰세요" 예시
//   io      : { input, output } — 직전 노드 출력을 어떻게 받고 무엇을 내보내는지
//   fields  : { 필드이름: 설명 } — 정의된 필드에 붙는 설명
//   extraFields : NodeDefinitions/NodeRegistry 에 필드 명세가 없는 노드의 필드 목록
//   tips    : 주의사항
//   related : 관련 노드 타입 (상세 페이지에서 서로 링크)

export const NODE_DOCS = {
  // ── 기본 (core) ──────────────────────────────────────────────────────────
  startNode: {
    summary: '모든 Workflow의 기본 시작점입니다. 설정 없이 실행 버튼으로 흐름을 시작합니다.',
    details: [
      '실행 버튼을 누르거나 배포된 앱·API가 호출될 때 흐름이 이 노드에서 출발합니다. 별도의 설정 값이 없습니다.',
      '모든 Workflow는 시작 노드 계열(시작, 스케줄, 웹훅, 봇 트리거 등) 정확히 하나로 시작해야 합니다.',
    ],
    usage: ['수동으로 실행하는 일반적인 Workflow', '앱 빌더 화면이나 API 호출로 시작되는 Workflow'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '빈 값으로 시작하며, 첫 데이터는 보통 다음의 프롬프트·입력 노드가 만듭니다.' },
    fields: {},
    tips: ['정해진 시간에 자동 실행하려면 스케줄 (시작), 외부 요청으로 시작하려면 웹훅 수신으로 교체하세요.'],
    related: ['scheduleNode', 'webhookNode', 'dynamicInputNode', 'outputNode'],
  },
  scheduleNode: {
    summary: 'Cron 표현식으로 정해진 주기에 Workflow를 자동 실행하는 시작점입니다.',
    details: [
      '시작 노드 대신 사용합니다. 저장 후 스케줄을 켜 두면 지정한 주기마다 서버가 Workflow를 자동으로 실행합니다.',
      'Cron 표현식은 분·시·일·월·요일 순서입니다. 예: "0 7 * * *"는 매일 07:00, "0 9 * * 1-5"는 평일 09:00.',
    ],
    usage: ['"매일 아침 뉴스 요약해서 보내줘" 같은 주기 자동화', '주간 보고서 생성, 정기 데이터 수집'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '실행 시각 기준으로 흐름을 시작합니다.' },
    fields: { cronExpression: '분·시·일·월·요일 5칸. 운영 화면의 스케줄 탭에서 다음 실행 시각과 실행 로그를 확인할 수 있습니다.' },
    tips: ['사용자 시간대와 서버 시간대를 구분하세요. 운영 → 스케줄 화면에서 일시정지할 수 있습니다.'],
    related: ['startNode', 'webhookNode', 'rssTriggerNode', 'naverSearchTriggerNode'],
  },
  outputNode: {
    summary: '흐름의 최종 결과를 사용자·호출자에게 텍스트로 돌려주는 종료 노드입니다.',
    details: [
      '직전 노드의 출력이 Workflow의 최종 결과로 반환됩니다. 봇 트리거로 시작한 흐름이라면 봇이 이 결과를 받은 채널로 자동 답장합니다.',
      '이메일·디스코드·카카오처럼 그 자체로 외부에 결과를 발송하는 노드나, 파일을 저장하며 끝나는 노드(자동 완성, 포스터 생성)로 흐름이 끝나면 결과 출력을 덧붙이지 않아도 됩니다.',
    ],
    usage: ['실행 결과를 화면·앱·봇 답장으로 보여줘야 하는 모든 흐름의 끝'],
    io: { input: '직전 노드의 출력 — 그대로 최종 결과가 됩니다.', output: '없음 — 흐름이 종료됩니다.' },
    fields: {},
    tips: [
      '데이터베이스 노드는 조회 전용이라 결과를 보여줘야 하므로 뒤에 결과 출력을 반드시 붙입니다.',
      '분배기의 반복 경로 안에 결과 출력을 두면 첫 항목만 처리하고 전체가 끝나버립니다 — 반복 종료 후 실행할 것은 분배기의 done 경로로 연결하세요.',
    ],
    related: ['startNode', 'distributorNode', 'mergeNode'],
  },

  // ── 입력 (input) ─────────────────────────────────────────────────────────
  dynamicInputNode: {
    summary: '실행할 때마다 외부(호출자·봇 메시지·앱 입력)에서 값을 받는 자리입니다.',
    details: [
      '고정 문구가 아니라 "매번 다른 값"을 받아야 할 때 씁니다. 배포된 앱의 입력창, API 호출의 파라미터, 봇이 받은 메시지가 이 자리로 들어옵니다.',
      '에디터에서 미리보기 실행할 때는 테스트 값이 대신 쓰입니다. 실제 실행에서는 호출자가 넘긴 값으로 항상 대체되므로 테스트 값은 "기본값"이 아닙니다.',
    ],
    usage: ['앱 빌더 입력창과 연결되는 값 받기', 'API로 호출할 때 파라미터 받기'],
    io: { input: '없음 — 외부에서 값이 주입됩니다.', output: '주입된 값(문자열)을 다음 노드로 전달합니다.' },
    extraFields: [
      { name: 'inputLabel', label: '입력 설명', kind: 'text', description: '이 입력이 무엇인지 설명하는 라벨. 앱 화면과 실행 안내에 표시됩니다.' },
      { name: 'testValue', label: '테스트 값', kind: 'text', description: '에디터 미리보기 전용 예시값. 실제 배포 실행에서는 호출자의 값으로 항상 대체됩니다.' },
    ],
    tips: ['흐름에 고정으로 박히는 문구가 필요하면 이 노드가 아니라 프롬프트(또는 변수) 노드를 쓰세요.'],
    related: ['promptNode', 'valueNode', 'startNode'],
  },
  valueNode: {
    summary: '실행할 때마다 항상 같은 고정값(텍스트 또는 파일 경로)을 흐름에 넣습니다.',
    details: [
      '동적 입력의 반대입니다 — 매번 바뀌는 값이 아니라 언제나 같은 값을 씁니다.',
      '고정 텍스트를 넣거나, 파일 경로가 필요한 노드(토크나이저 등) 앞에 "항상 이 파일" 용도로 둡니다. 노드를 클릭해 파일을 업로드하면 경로가 채워집니다.',
    ],
    usage: ['토크나이저 앞에서 분석할 문서 지정', '프롬프트에 고정 문구·자료를 미리 넣어둘 때'],
    io: { input: '사용하지 않습니다.', output: '설정한 고정 텍스트 또는 파일 경로.' },
    extraFields: [
      { name: 'value', label: '고정 텍스트', kind: 'textarea', description: '항상 흐름에 넣을 고정 문자열. file_path와 둘 중 하나만 사용합니다.' },
      { name: 'file_path', label: '고정 파일 경로', kind: 'text', description: '항상 사용할 파일. 노드에서 파일을 업로드하면 자동으로 채워집니다.' },
    ],
    tips: ['토크나이저는 직전 노드의 출력이 파일 경로여야 동작합니다 — 그 사이에 이 노드를 두는 것이 정석입니다.'],
    related: ['dynamicInputNode', 'tokenizerNode', 'promptNode'],
  },
  webhookNode: {
    summary: '외부 시스템의 HTTP 요청이 도착하면 Workflow를 시작하는 진입점입니다.',
    details: [
      '시작 노드 대신 사용합니다. 저장하면 이 Workflow 전용 URL이 만들어지고, 외부 서비스가 그 URL로 요청을 보내면 흐름이 시작됩니다.',
      '요청 Body(Payload)가 흐름의 첫 입력이 됩니다. 운영 → 웹훅 화면에서 URL 확인과 수신 로그를 볼 수 있습니다.',
    ],
    usage: ['결제 완료·주문 접수 같은 외부 이벤트로 시작하는 자동화', '다른 서비스에서 이 Workflow 호출하기'],
    io: { input: '외부 HTTP 요청의 Payload.', output: '수신한 Payload를 다음 노드로 전달합니다.' },
    extraFields: [
      { name: 'method', label: 'HTTP Method', kind: 'select', description: 'GET·POST·PUT·DELETE 중 수신할 방식. Payload를 받으려면 보통 POST를 씁니다.' },
      { name: 'path', label: '엔드포인트 경로', kind: 'text', description: '웹훅 URL의 마지막 경로 부분.' },
    ],
    tips: ['공개 URL이므로 요청 검증(시크릿 헤더 등)을 흐름 안에서 확인하는 것이 안전합니다.'],
    related: ['startNode', 'httpRequestNode', 'jsonParserNode'],
  },
  discordTriggerNode: {
    summary: '디스코드에서 봇에게 DM·멘션을 보내면 그 메시지로 Workflow가 시작됩니다.',
    details: [
      '시작 노드 대신 쓰는 진입점입니다. 캔버스를 저장하고 에디터 상단의 "라이브 시작"을 켜면 그 순간부터 실제 디스코드 봇이 메시지를 기다립니다 — 별도의 배포 절차가 없습니다.',
      '흐름 끝에 결과 출력만 두면 봇이 메시지를 보낸 채널/DM으로 결과를 자동 답장합니다. 디스코드 발송 노드는 "다른" 채널로 별도 발송할 때만 추가합니다.',
    ],
    usage: ['"디스코드로 대화하는 봇 만들어줘"', '디스코드 문의 접수 → 분류 → 자동 답변'],
    io: { input: '봇이 받은 디스코드 메시지 텍스트.', output: '메시지 내용을 다음 노드로 전달합니다.' },
    extraFields: [
      { name: 'botToken', label: 'Bot Token', kind: 'secret', description: '디스코드 개발자 포털에서 발급한 봇 토큰. API 센터에 등록했다면 {{API_CENTER:discord}}로 자동 연결됩니다.' },
    ],
    tips: ['토큰은 노드에 직접 적지 말고 API 센터에 등록해 연결하는 것이 안전합니다.', '운영 → 봇 화면에서 시작·중지와 오류 로그(401 등)를 확인합니다.'],
    related: ['telegramTriggerNode', 'discordNode', 'outputNode'],
  },
  telegramTriggerNode: {
    summary: '텔레그램 봇에게 메시지를 보내면 그 메시지로 Workflow가 시작됩니다.',
    details: [
      '디스코드 봇 트리거와 같은 방식의 진입점입니다. 저장 후 "라이브 시작"을 켜면 봇이 대기하고, 결과 출력으로 끝내면 받은 채팅방으로 자동 답장합니다.',
      '봇 토큰은 @BotFather에서 한 번 발급받으면 만료되지 않습니다(카카오 access_token과 달리 자동 갱신이 필요 없습니다).',
    ],
    usage: ['"텔레그램으로 대화하는 봇 만들어줘"', '텔레그램 알림 봇의 질문·응답 처리'],
    io: { input: '봇이 받은 텔레그램 메시지 텍스트.', output: '메시지 내용을 다음 노드로 전달합니다.' },
    extraFields: [
      { name: 'botToken', label: 'Bot Token', kind: 'secret', description: '@BotFather에서 발급한 토큰. API 센터에 등록했다면 {{API_CENTER:telegram}}으로 자동 연결됩니다.' },
    ],
    tips: ['답장은 결과 출력 하나면 충분합니다 — 텔레그램 발송 노드는 "다른" 채팅방으로 보낼 때만 씁니다.'],
    related: ['discordTriggerNode', 'telegramNode', 'outputNode'],
  },
  youtubeTriggerNode: {
    summary: '유튜브 채널에 새 영상이 올라오면 실행되는 시작점입니다.',
    details: [
      '시작 노드 대신 사용합니다. 채널 ID를 비우면 API 센터에 연결한 구글 계정의 내 채널을 감시합니다.',
      '출력은 새 영상 목록 JSON이며 각 항목에 video_id·title·description·published_at·channel_title·url이 들어 있습니다. 첫 실행은 기준점만 잡고 알리지 않습니다.',
    ],
    usage: ['새 영상 업로드 시 커뮤니티·SNS에 자동 공지', '경쟁 채널 새 영상 모니터링'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '새 영상 목록(JSON 배열 문자열).' },
    fields: {
      channelId: '감시할 채널 ID. 비우면 내 채널. 모르는 값을 지어내지 말고 비워두세요.',
      maxResults: '한 번에 확인할 최대 영상 수.',
    },
    tips: ['목록(JSON)을 활용하려면 뒤에 LLM 요약이나 JSON 파서를 연결하세요.'],
    related: ['youtubeNode', 'rssTriggerNode', 'llmNode'],
  },
  rssTriggerNode: {
    summary: 'RSS/Atom 피드에 새 글이 올라오면 실행되는 시작점입니다. 자격증명이 필요 없습니다.',
    details: [
      '시작 노드 대신 사용합니다. 지정한 피드를 주기적으로 확인해 새 글이 있으면 흐름을 시작합니다.',
      '출력은 새 항목 배열의 JSON 문자열(각 항목: id·title·link·summary·published_at)입니다. 첫 실행은 기준점만 잡고 통지하지 않습니다.',
    ],
    usage: ['블로그·뉴스 새 글 알림 자동화', '새 글 요약 → 메신저 발송 파이프라인'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '새 글 목록(JSON 배열 문자열).' },
    fields: { feedUrl: 'RSS 또는 Atom 피드 주소.', maxItems: '한 번에 통지할 최대 항목 수.' },
    tips: ['항목별로 하나씩 처리하려면 뒤에 분배기를 연결하세요.'],
    related: ['naverSearchTriggerNode', 'distributorNode', 'webCrawlerNode'],
  },
  gmailTriggerNode: {
    summary: '조건에 맞는 새 Gmail 메일이 도착하면 실행되는 시작점입니다.',
    details: [
      '시작 노드 대신 사용합니다. Gmail 검색 문법으로 감시할 조건을 지정할 수 있습니다(예: "from:boss@example.com is:unread").',
      '출력은 새 메일 요약 배열의 JSON 문자열(각 항목: message_id·thread_id·from·subject·snippet·date)입니다. 첫 실행은 기준점만 잡고 통지하지 않습니다.',
    ],
    usage: ['특정 발신자의 메일 도착 시 자동 처리', '새 문의 메일 요약 → 메신저 알림'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '새 메일 요약 목록(JSON 배열 문자열).' },
    fields: { query: 'Gmail 검색 문법 그대로 씁니다. 비우면 모든 새 메일.', maxResults: '한 번에 통지할 최대 메일 수.' },
    tips: ['답장까지 자동화하려면 message_id를 Gmail 발송/답장 노드의 답장 모드로 넘기세요.'],
    related: ['gmailNode', 'jsonParserNode', 'distributorNode'],
  },
  naverSearchTriggerNode: {
    summary: '네이버 블로그·카페에 검색어와 일치하는 새 글이 올라오면 실행되는 시작점입니다.',
    details: [
      '시작 노드 대신 사용합니다. 지정한 검색어를 주기적으로 확인해 새 글이 발견되면 흐름을 시작합니다.',
      '출력은 새 항목 배열의 JSON 문자열이며 각 항목은 title·link·description·author·publishedAt입니다. 첫 실행은 기준점만 잡고 아무것도 알리지 않습니다 — 다음 새 글부터 알립니다.',
    ],
    usage: ['브랜드·제품 언급 모니터링', '특정 키워드 새 글 요약 알림'],
    io: { input: '없음 — 흐름의 출발점입니다.', output: '새 글 목록(JSON 배열 문자열).' },
    fields: {
      mode: 'blog(블로그) 또는 cafe_article(카페글) 중 감시 대상.',
      query: '감시할 검색어.',
      pollInterval: '확인 주기. 짧을수록 빨리 알지만 확인 횟수가 늘어납니다.',
      maxResults: '한 번에 확인할 개수.',
    },
    tips: ['Workflow 중간에서 검색하려면 트리거가 아니라 네이버 검색(액션) 노드를 쓰세요.'],
    related: ['naverSearchNode', 'naverCafeNode', 'distributorNode'],
  },

  // ── AI ──────────────────────────────────────────────────────────────────
  promptNode: {
    summary: 'LLM에게 전달할 사용자 프롬프트(요청 문구)를 흐름에 고정으로 넣습니다.',
    details: [
      '항상 인접한 LLM 노드와 짝으로 사용합니다. 여기 적은 문구가 LLM의 사용자 메시지가 됩니다.',
      '직전 노드의 출력과 함께 LLM에 전달되므로, "다음 내용을 요약해줘" 같은 지시문을 두는 자리입니다.',
    ],
    usage: ['LLM에게 시킬 일을 고정 문구로 지정', '수집한 데이터 앞에 처리 지시문 붙이기'],
    io: { input: '직전 노드의 출력(있다면 함께 LLM으로 전달됩니다).', output: '프롬프트 문구를 다음 LLM 노드로 전달합니다.' },
    extraFields: [
      { name: 'userPrompt', label: '사용자 프롬프트', kind: 'textarea', description: 'LLM에게 전달할 요청 문구.' },
    ],
    tips: ['매번 다른 값을 받아야 하면 프롬프트가 아니라 동적 입력을 쓰세요.', '프롬프트 노드로 들어오는 LLM 엣지는 1개까지만 — 2개 이상이면 어떤 모델이 쓰일지 비결정적이 됩니다.'],
    related: ['llmNode', 'dynamicInputNode', 'valueNode'],
  },
  llmNode: {
    summary: 'AI 모델을 호출해 텍스트를 생성·분석·변환하는 핵심 노드입니다.',
    details: [
      '시스템 프롬프트로 역할과 규칙을 정하고, 직전 노드의 출력(그리고 짝이 된 프롬프트 노드의 문구)을 입력으로 받아 응답을 생성합니다.',
      '출력이 반드시 유효한 JSON이어야 하는 경우 — JSON 파서·자동 완성으로 이어지거나 조건 분기가 특정 키를 검사하는 경우 — 시스템 프롬프트로 "JSON으로 답해"라고 지시하는 것만으로는 부족합니다. Structured Output을 켜고 JSON Schema를 함께 설정해 형식을 구조적으로 보장하세요.',
    ],
    usage: ['요약·분류·초안 작성 등 모든 생성 작업', '수집 데이터를 다음 노드가 쓰기 좋은 JSON으로 정리'],
    io: { input: '직전 노드의 출력 + (짝 프롬프트 노드의 문구).', output: '모델 응답 텍스트. Structured Output 사용 시 스키마에 맞는 JSON 문자열.' },
    fields: {
      model: '특별한 요청이 없으면 기본값(gpt-4o-mini)을 씁니다. 길고 복잡한 작업만 상위 모델로.',
      apiKey: 'API 센터에 등록해 연결하는 것을 권장합니다({{API_CENTER:openai}}). 노드에 직접 적지 마세요.',
      systemPrompt: '모델의 역할·규칙·출력 형식을 정하는 지시문.',
      userPrompt: '선택 — 짝 프롬프트 노드 대신 여기에 직접 적을 수도 있습니다.',
      useMemory: '켜면 같은 Workflow의 이전 대화를 기억합니다(봇 대화에 유용).',
      useStructuredOutput: '출력을 JSON Schema에 강제로 맞춥니다. 후속 노드가 JSON을 기대하면 반드시 켜세요.',
      jsonSchema: 'Structured Output이 따라야 할 JSON Schema.',
    },
    tips: ['조건 분기가 LLM 출력의 특정 키를 검사한다면 Structured Output + JSON 파서(extract) 조합이 안전합니다.'],
    related: ['promptNode', 'jsonParserNode', 'conditionNode', 'multiAgentNode'],
  },
  multiAgentNode: {
    summary: '여러 LLM 에이전트를 하나의 조율자 아래에서 협업시키는 노드입니다.',
    details: [
      'supervisor 모드는 조율자가 서브 에이전트들에게 일을 나눠주고 결과를 종합합니다. group_chat 모드는 에이전트들이 대화하듯 순서를 주고받습니다.',
      '서브 에이전트로 쓸 LLM 노드는 일반 연결이 아니라 엣지의 targetHandle을 "tools"로 지정해 이 노드에 연결합니다.',
    ],
    usage: ['역할이 다른 여러 AI(조사·작성·검수)가 협업해야 하는 작업', '단일 LLM 호출로는 품질이 부족한 복합 작업'],
    io: { input: '직전 노드의 출력이 작업 지시가 됩니다.', output: '에이전트 협업의 최종 결과 텍스트.' },
    extraFields: [
      { name: 'mode', label: '조율 방식', kind: 'select', description: 'supervisor(조율자 지휘) 또는 group_chat(그룹 대화).' },
    ],
    tips: ['서브 에이전트 연결은 targetHandle "tools" — 일반 실행 순서 연결과 다릅니다.'],
    related: ['llmNode', 'promptNode'],
  },
  imageGenerationNode: {
    summary: 'OpenAI 이미지 도구로 이미지를 새로 만들거나, 이전 결과를 이어받아 수정합니다.',
    details: [
      '프롬프트를 비우면 직전 노드의 출력을 프롬프트로 씁니다. 동작(auto·generate·edit)과 크기·품질·배경·출력 형식을 정할 수 있습니다.',
      '수정(edit)은 이전 생성 결과의 대화 문맥을 이어받아 진행되며, 수정본은 기존 파일을 덮어쓰지 않고 새 버전으로 저장됩니다.',
    ],
    usage: ['"이미지 만들어줘" 류 생성 요청', '피드백을 반영해 같은 이미지를 반복 수정하는 루프'],
    io: { input: '프롬프트가 비어 있으면 직전 노드의 출력을 프롬프트로 사용.', output: '생성된 이미지 파일(뒤의 발송 노드에서 자동 첨부 가능).' },
    fields: {
      apiKey: 'API 센터 연결을 권장합니다({{API_CENTER:openai}}).',
      prompt: '이미지 설명. 비우면 직전 노드의 출력을 사용합니다.',
      action: 'auto는 문맥에 따라 생성/수정을 알아서 선택합니다.',
      previousResponseId: '수정 시 이어받을 이전 응답 ID(고급). 비우면 같은 흐름의 직전 결과를 잇습니다.',
    },
    tips: ['만든 이미지는 뒤의 이메일·디스코드·Gmail 발송 노드에서 자동 첨부됩니다.'],
    related: ['posterGeneratorNode', 'discordNode', 'emailNode'],
  },

  // ── 로직 (logic) ─────────────────────────────────────────────────────────
  conditionNode: {
    summary: '직전 노드의 출력을 규칙과 비교해 서로 다른 경로로 분기합니다.',
    details: [
      '규칙마다 연산자(==, Contains, >, <, >=, <=)와 비교 값을 정합니다. 나가는 엣지는 sourceHandle에 통과한 규칙의 id를, 모두 불일치할 때의 경로는 "else"를 지정합니다.',
      '⚠️ 비교 대상은 직전 노드 출력 "전체"입니다 — JSON을 파싱해 특정 키만 꺼내 비교해주지 않습니다. LLM이 {"isValid": false, ...} 같은 JSON을 내놓는다면, 그중 isValid만 검사하고 싶을 때는 JSON 파서(extract)로 값을 먼저 꺼낸 뒤 비교하세요.',
    ],
    usage: ['금액·상태·분류 결과에 따라 다른 처리', 'LLM 판정 결과로 승인/반려 흐름 나누기'],
    io: { input: '직전 노드의 출력 전체(문자열).', output: '입력을 그대로, 일치한 규칙의 경로로 전달합니다.' },
    fields: { rules: '조건 규칙 목록. 각 규칙의 id가 분기 엣지의 sourceHandle이 됩니다.' },
    tips: ['같은 핸들(규칙 id 또는 else)에는 엣지를 1개까지만 — 2개 이상이면 첫 번째만 실행됩니다.', '갈라진 경로가 다시 합쳐질 때는 반드시 Merge를 거치세요.'],
    related: ['jsonParserNode', 'mergeNode', 'humanApprovalNode'],
  },
  loopNode: {
    summary: '내부 흐름을 지정한 횟수만큼 반복 실행하는 컨테이너입니다.',
    details: [
      '나가는 엣지는 sourceHandle로 구분합니다: "loop_start"는 매 반복마다 실행할 흐름의 시작, "done"은 반복이 모두 끝난 뒤 한 번 실행할 경로입니다.',
      '목록의 항목별 처리가 목적이라면 반복 횟수를 정하는 이 노드보다 분배기가 적합합니다 — 분배기는 리스트를 항목 단위로 꺼내 반복합니다.',
    ],
    usage: ['정해진 횟수만큼 시도·재생성 반복', '반복 후 마무리 단계(done)가 있는 흐름'],
    io: { input: '직전 노드의 출력.', output: 'loop_start 경로에는 매 반복 입력이, done 경로에는 반복 종료 후 결과가 흐릅니다.' },
    extraFields: [
      { name: 'maxIterations', label: '최대 반복 횟수', kind: 'number', description: '기본 5. 반복 안에서 반복 종료 노드로 조기 종료할 수 있습니다.' },
    ],
    tips: ['항목별 반복은 분배기, 조건 만족 시 중단은 반복 종료 노드와 조합하세요.'],
    related: ['distributorNode', 'breakNode', 'conditionNode'],
  },
  breakNode: {
    summary: '진행 중인 반복을 즉시 멈춥니다. 반드시 반복 구조 안에서만 사용합니다.',
    details: [
      '분배기(또는 반복)의 하류에서만 동작합니다. 반복 구조 밖에 두면 실행 자체가 오류로 깨집니다.',
      '보통 조건 분기와 짝을 이뤄 "특정 조건을 만나면 반복을 멈춘다"는 용도로 씁니다.',
    ],
    usage: ['원하는 항목을 찾으면 나머지 항목 처리 생략', '실패 감지 시 반복 중단'],
    io: { input: '직전 노드의 출력(반복 문맥).', output: '반복을 종료시키고 done 경로로 넘어갑니다.' },
    fields: {},
    tips: ['반복 구조(분배기 하류) 밖에서는 절대 사용하지 마세요.'],
    related: ['distributorNode', 'loopNode', 'conditionNode'],
  },
  delayNode: {
    summary: '지정한 시간(초)만큼 기다렸다가 다음 노드로 진행합니다.',
    details: [
      '직전 노드의 출력을 그대로 들고 지정한 초만큼 대기한 뒤 다음 노드로 전달합니다.',
      '외부 API의 속도 제한을 피하거나, 발송 전에 간격을 둘 때 씁니다.',
    ],
    usage: ['연속 API 호출 사이 간격 두기', '알림 발송을 일정 시간 뒤로 미루기'],
    io: { input: '직전 노드의 출력.', output: '입력을 그대로, 대기 후 전달합니다.' },
    fields: { seconds: '대기할 시간(초).' },
    tips: ['같은 목적지로 직행 경로와 대기 경로를 동시에 만들지 마세요 — 대기를 거치는 하나만 남깁니다.'],
    related: ['httpRequestNode', 'scheduleNode'],
  },
  mergeNode: {
    summary: '여러 갈래로 나뉜 흐름의 결과를 하나로 안전하게 병합합니다.',
    details: [
      '여러 갈래의 엣지가 이 노드로 모일 수 있습니다. 병합 방식은 줄바꿈 연결(join_newline), 쉼표 연결(join_comma), 배열(array) 중에서 선택합니다.',
      '갈라진 경로를 Merge 없이 임의의 노드(예: LLM)로 바로 합류시키면 그 노드가 중복 실행됩니다 — 합류 지점에는 반드시 Merge를 두세요. 조건 분기의 갈래가 다시 만날 때도 마찬가지입니다.',
    ],
    usage: ['병렬로 수집·생성한 결과를 하나의 문서로 합치기', '조건 분기 후 공통 마무리 단계로 합류'],
    io: { input: '여러 갈래에서 도착한 출력들.', output: '선택한 방식으로 합쳐진 하나의 값.' },
    extraFields: [
      { name: 'mergeStrategy', label: '병합 방식', kind: 'select', description: 'join_newline(줄바꿈으로 이어붙임) · join_comma(쉼표) · array(JSON 배열).' },
    ],
    tips: ['Merge 없이 여러 갈래를 한 노드로 합류시키는 구성은 금지입니다 — 중복 실행의 원인.'],
    related: ['conditionNode', 'distributorNode', 'outputNode'],
  },

  // ── 코드·데이터 (code) ───────────────────────────────────────────────────
  pythonNode: {
    summary: '제한된 파이썬 코드로 직전 출력을 변환합니다. 격리 실행이라 쓸 수 있는 것이 매우 제한적입니다.',
    details: [
      '직전 노드의 출력이 input_data 변수에 담기고, 처리 결과를 output_data 변수에 할당해야 합니다.',
      '⚠️ import·def·lambda·while·try·open·eval은 전부 금지이고 파일·네트워크·환경변수·DB에 접근할 수 없습니다. 쓸 수 있는 것은 변수 대입, if, for, 컴프리헨션, 사칙연산, f-string, len/str/int/sorted/sum 같은 기본 함수와 split/join/strip/get/append 같은 흔한 메서드뿐입니다. 실행 1초·메모리 256MB 제한이 있습니다.',
    ],
    usage: ['문자열 다듬기·목록 정리처럼 LLM을 부르기 아까운 가벼운 변환', '숫자 계산·정렬·중복 제거'],
    io: { input: 'input_data 변수로 주입됩니다.', output: 'output_data에 할당한 값.' },
    extraFields: [
      { name: 'code', label: '파이썬 코드', kind: 'textarea', description: 'input_data를 읽어 output_data에 결과를 할당하는 코드.' },
    ],
    tips: ['파일을 읽거나 외부를 호출해야 하면 이 노드가 아니라 전용 노드(자동 완성, HTTP Request 등)를 쓰세요.'],
    related: ['jsonParserNode', 'llmNode'],
  },
  jsonParserNode: {
    summary: 'JSON을 파싱하거나 문자열로 바꾸고, 특정 키의 값만 꺼냅니다.',
    details: [
      '모드 세 가지 — parse(문자열→JSON), stringify(JSON→문자열), extract(특정 키 값 꺼내기). extract일 때만 추출할 키를 지정합니다.',
      'LLM 출력의 특정 필드로 조건 분기하거나 다음 노드에 한 값만 넘기고 싶을 때 extract를 씁니다.',
    ],
    usage: ['LLM의 JSON 응답에서 필요한 필드만 추출', 'API 응답(JSON)을 다음 노드가 쓰기 좋게 변환'],
    io: { input: '직전 노드의 출력(JSON 문자열 또는 값).', output: '모드에 따라 JSON·문자열·추출된 값.' },
    fields: { mode: 'parse · stringify · extract 중 선택.', extractKey: 'extract 모드에서 꺼낼 키 이름.' },
    tips: ['앞의 LLM에는 Structured Output을 켜서 출력이 항상 유효한 JSON이 되게 하세요.'],
    related: ['llmNode', 'conditionNode', 'distributorNode'],
  },
  tokenizerNode: {
    summary: '업로드한 문서(PDF/PPTX/Excel/HWP)에서 텍스트를 추출합니다.',
    details: [
      '직전 노드의 출력이 파일 경로일 때만 동작합니다 — 문서 기반 작업이면 LLM 앞에 둡니다.',
      '시작·스케줄처럼 파일 경로를 만들지 않는 노드 바로 뒤에 두면 실행마다 실패합니다. 그 사이에 변수(값) 노드를 두고 파일을 업로드하세요.',
    ],
    usage: ['"이 PDF 요약해줘" 류 문서 기반 작업', '회의록·보고서에서 텍스트 뽑아 LLM에 넘기기'],
    io: { input: '직전 노드의 출력 — 반드시 파일 경로.', output: '추출된 텍스트.' },
    extraFields: [
      { name: 'method', label: '추출 방식', kind: 'select', description: 'extract_text(전체 텍스트) 또는 chunk_pages(페이지 단위 분할).' },
    ],
    tips: ['파일 지정은 앞의 변수(값) 노드에서 업로드로 해결하는 것이 정석입니다.'],
    related: ['valueNode', 'llmNode', 'templateAnalyzerNode'],
  },
  distributorNode: {
    summary: '직전 출력을 리스트로 보고 항목을 하나씩 꺼내, 뒤의 흐름을 항목 수만큼 반복 실행합니다.',
    details: [
      '"각각에 대해", "하나씩" 같은 요청에 씁니다. 리스트가 아니면 1개짜리로 취급합니다. 기본(핸들 없는) 엣지는 반복 "안"에서 항목마다 실행됩니다.',
      '⚠️ 반복 경로는 절대 결과 출력으로 이어지면 안 됩니다 — 반복 중 결과 출력에 닿으면 그 즉시 반환되어 첫 항목만 처리하고 전체가 끝나버립니다. 반복이 다 끝난 뒤 한 번 실행할 것(최종 요약·종료)은 sourceHandle을 "done"으로 지정해 연결하세요.',
      '항목별 결과는 순서대로 이어 붙여 done 경로로 전달됩니다.',
    ],
    usage: ['수집한 글 목록을 항목별로 요약', '여러 수신자에게 각각 발송'],
    io: { input: '직전 노드의 출력(JSON 배열이 이상적).', output: '반복 경로에는 항목 하나씩, done 경로에는 모인 전체 결과.' },
    fields: {},
    tips: ['결과 출력으로 끝내려면 반드시 done 경로를 거치세요.', '조건 만족 시 반복을 멈추려면 반복 종료 노드를 조합하세요.'],
    related: ['jsonParserNode', 'breakNode', 'loopNode', 'mergeNode'],
  },
  databaseNode: {
    summary: 'PostgreSQL 데이터베이스를 조회합니다. 조회 전용 — 변경 쿼리는 실행 전에 차단됩니다.',
    details: [
      '쿼리는 반드시 SELECT 또는 WITH로 시작하는 문장 하나여야 합니다. INSERT/UPDATE/DELETE/DROP 등 변경 쿼리는 SQL Guard가 실행 전에 차단합니다.',
      '접속 문자열 원문은 절대 노드에 적지 않습니다 — API 센터에 등록하고 {{API_CENTER:database}}로 연결하면 실행 시점에 해석됩니다.',
      '쿼리 파라미터로 직전 노드 출력의 값을 안전하게 바인딩할 수 있습니다(문자열 끼워넣기 대신 파라미터 사용).',
    ],
    usage: ['주문·회원 데이터 조회 후 요약·알림', '조건에 맞는 행을 뽑아 항목별 처리'],
    io: { input: '파라미터 값 출처로 직전 노드의 출력을 쓸 수 있습니다.', output: '조회된 행 목록(JSON) — 다음 노드의 입력이 됩니다.' },
    fields: {
      connectionString: '항상 {{API_CENTER:database}} 참조로 채웁니다. 원문 접속 정보 금지.',
      query: 'SELECT/WITH로 시작하는 조회 문장 하나.',
      parameters: '쿼리의 자리표시자에 바인딩할 값들. 출처를 "직전 노드 출력"으로 두면 실행 시점 값이 들어갑니다.',
      maxRows: '가져올 최대 행 수.',
      allowedSchemas: '조회를 허용할 스키마 목록(쉼표 구분).',
    },
    tips: ['조회 전용이므로 흐름은 항상 결과 출력으로 끝나야 합니다.'],
    related: ['outputNode', 'jsonParserNode', 'googleSheetsNode'],
  },

  // ── 외부 연동 (integration) ───────────────────────────────────────────────
  webCrawlerNode: {
    summary: '웹페이지를 읽어 제목·발행일·본문·링크로 갈라 전달합니다. robots.txt와 수집 상한을 지킵니다.',
    details: [
      '메뉴·광고·푸터를 빼고 본문만 남깁니다. URL을 비우면 직전 노드의 출력을 URL로 씁니다.',
      '출력 형식은 text(사람이 읽는 글), structured(전체 JSON), links(페이지의 링크 목록 JSON) 세 가지 — 목록 페이지에서 링크를 모아 상세로 넘어갈 때는 links를 씁니다.',
      'robots.txt를 지키고 호스트당 하루 요청 수 상한이 있어 같은 사이트를 대량으로 훑는 흐름은 도중에 막힙니다. 실패해도 흐름은 멈추지 않고 "수집하지 않았습니다: ..." 문자열이 다음 노드로 전달됩니다.',
    ],
    usage: ['기사·공지 본문 수집 후 요약', '목록 페이지 → 링크 수집 → 상세 순회(분배기 조합)'],
    io: { input: 'URL(필드를 비웠을 때 직전 노드의 출력).', output: '선택한 형식의 본문/JSON/링크 목록.' },
    extraFields: [
      { name: 'url', label: '수집할 URL', kind: 'text', description: '비우면 직전 노드의 출력을 URL로 사용. 비울 거면 URL을 만들어주는 노드를 바로 앞에 연결해야 합니다.' },
      { name: 'output', label: '출력 형식', kind: 'select', description: 'text(기본) · structured · links.' },
      { name: 'maxChars', label: '최대 글자 수', kind: 'number', description: '본문을 자를 상한. 기본 5000.' },
    ],
    tips: ['robots가 거부한 경로는 수집하지 않으며, 요청 간격도 자동으로 지킵니다.'],
    related: ['httpRequestNode', 'distributorNode', 'llmNode'],
  },
  emailNode: {
    summary: '직전 노드의 출력을 본문으로 이메일을 발송합니다. 앞에서 만든 파일은 자동 첨부됩니다.',
    details: [
      '수신자와 제목을 지정하면 본문은 직전 노드의 출력을 그대로 씁니다.',
      '앞의 파일 생성 노드(자동 완성·포스터 생성·AI 이미지)가 만든 파일은 첨부 설정을 비워 두면 자동으로 첨부됩니다 — 파일 경로 문자열을 본문에 끼워 넣지 마세요.',
    ],
    usage: ['"문서 만들어서 이메일로 보내줘"', '요약 결과 정기 발송(스케줄 조합)'],
    io: { input: '직전 노드의 출력 — 메일 본문이 됩니다.', output: '발송 결과. 발송으로 흐름을 끝내면 결과 출력은 생략 가능합니다.' },
    fields: {
      smtp_credentials: 'SMTP 계정(이메일:앱비밀번호). 서버 설정이 없으면 실행 시 실패합니다.',
      toEmail: '받는 사람 이메일 주소.',
      subject: '비우면 기본 제목이 쓰입니다.',
      attachments: '비워 두면 앞 노드가 만든 파일을 자동 첨부합니다.',
    },
    tips: ['Gmail 계정으로 답장·라벨까지 다루려면 Gmail 발송/답장 노드를 쓰세요.'],
    related: ['gmailNode', 'fileModifierNode', 'posterGeneratorNode'],
  },
  kakaoNode: {
    summary: '직전 노드의 출력을 카카오톡 메시지로 발송합니다(기본: 나에게 보내기).',
    details: [
      'access_token은 API 센터에 등록하고 {{API_CENTER:kakao_token}} 참조로 채웁니다 — 6시간마다 만료되어도 refresh_token으로 자동 갱신되므로 재입력이 필요 없습니다.',
      '수신자를 비우면 나에게 보내기로 발송됩니다.',
    ],
    usage: ['개인 알림(작업 완료·모니터링 감지)을 카카오톡으로 받기'],
    io: { input: '직전 노드의 출력 — 메시지 내용이 됩니다.', output: '발송 결과. 발송으로 흐름을 끝내면 결과 출력은 생략 가능합니다.' },
    extraFields: [
      { name: 'accessToken', label: 'Access Token', kind: 'secret', description: '항상 {{API_CENTER:kakao_token}} 참조를 권장 — 자동 갱신됩니다.' },
      { name: 'receiver', label: '수신자', kind: 'text', description: '비우면 나에게 보내기.' },
    ],
    tips: ['사업용 알림톡(템플릿 발송)과는 다른 노드입니다 — 이 노드는 카카오톡 메시지 API를 씁니다.'],
    related: ['discordNode', 'telegramNode', 'humanApprovalNode'],
  },
  discordNode: {
    summary: '디스코드 채널로 메시지를 발송합니다. 앞에서 만든 파일은 자동 첨부됩니다.',
    details: [
      'Bot Token(또는 Webhook URL)과 채널 ID로 발송합니다. 직전 노드의 출력이 본문이 됩니다.',
      '봇 트리거로 시작한 대화 봇이라면 이 노드가 아니라 결과 출력으로 끝내세요 — 받은 채널로 자동 답장됩니다. 이 노드는 "다른" 채널로 별도 발송할 때 씁니다.',
    ],
    usage: ['모니터링 결과를 팀 채널로 발송', '포스터·문서를 만들어 채널에 공유(자동 첨부)'],
    io: { input: '직전 노드의 출력 — 본문(캡션)이 됩니다.', output: '발송 결과. 발송으로 흐름을 끝내면 결과 출력은 생략 가능합니다.' },
    fields: {
      botToken: 'API 센터 연결을 권장합니다. Webhook URL을 쓰면 채널 ID는 생략합니다.',
      channelId: '보낼 채널의 ID. 모르는 값을 지어내면 발송이 조용히 실패합니다 — 반드시 실제 값을 입력하세요.',
      attachments: '비워 두면 앞 노드가 만든 파일을 자동 첨부합니다.',
    },
    tips: ['파일 경로 문자열을 본문에 끼워 넣지 마세요 — 첨부는 자동으로 처리됩니다.'],
    related: ['discordTriggerNode', 'slackNode', 'telegramNode'],
  },
  telegramNode: {
    summary: '텔레그램 채팅방으로 메시지를 발송합니다.',
    details: [
      '직전 노드의 출력을 그대로 발송합니다. chat_id는 숫자(그룹/채널은 보통 음수) 또는 "@channel_username" 형식만 유효합니다.',
      '봇 트리거로 시작한 흐름에서 받은 사람에게 답장하는 용도라면 이 노드 없이 결과 출력으로 끝내세요 — "다른" 채팅방으로 보낼 때만 씁니다.',
    ],
    usage: ['특정 그룹·채널로 알림 발송'],
    io: { input: '직전 노드의 출력 — 메시지 내용.', output: '발송 결과. 발송으로 흐름을 끝내면 결과 출력은 생략 가능합니다.' },
    extraFields: [
      { name: 'botToken', label: 'Bot Token', kind: 'secret', description: '트리거와 같은 값 — {{API_CENTER:telegram}} 연결을 권장합니다.' },
      { name: 'chatId', label: 'Chat ID', kind: 'text', description: '숫자(음수 가능) 또는 @channel_username. 실제 값을 모르면 비워 두세요.' },
    ],
    tips: ['chat_id를 지어내면 발송이 실패합니다 — 실제 값 확인 후 입력하세요.'],
    related: ['telegramTriggerNode', 'discordNode', 'kakaoNode'],
  },
  notionNode: {
    summary: 'Notion 데이터베이스에 페이지(행)를 추가하거나 페이지들을 조회합니다.',
    details: [
      'create 모드는 데이터베이스에 새 페이지를 추가하고, query 모드는 페이지들을 조회합니다. Integration Token은 API 센터에 등록해 {{API_CENTER:notion}}으로 연결합니다.',
      '⚠️ Notion은 속성 타입마다 JSON 형식이 다릅니다(title/rich_text/number/select/checkbox/date 등). 채울 속성을 비우면 직전 노드의 출력을 그대로 쓰는데, 이때 그 출력이 이미 Notion 속성 형식이어야 합니다 — 앞의 LLM에 실제 속성 스키마를 알려주고 그 형식의 JSON을 만들게 하세요.',
    ],
    usage: ['수집·요약 결과를 Notion 데이터베이스에 자동 기록', 'Notion에 쌓인 항목을 조회해 후속 처리'],
    io: { input: 'create에서 속성 JSON(비우면 직전 노드 출력).', output: 'query는 페이지 목록(JSON 배열 문자열) — 활용하려면 LLM/JSON 파서를 연결.' },
    extraFields: [
      { name: 'token', label: 'Integration Token', kind: 'secret', description: '{{API_CENTER:notion}} 연결을 권장합니다.' },
      { name: 'mode', label: '동작', kind: 'select', description: 'create(페이지 추가) 또는 query(조회).' },
      { name: 'databaseId', label: '데이터베이스 ID', kind: 'text', description: 'Notion 데이터베이스 URL에 있는 ID.' },
      { name: 'properties', label: '채울 속성 (JSON)', kind: 'textarea', description: 'Notion 속성 형식의 JSON. 비우면 직전 노드의 출력을 그대로 사용.' },
    ],
    tips: ['조회(query)로 끝나는 흐름은 결과 출력을 붙이고, 기록(create)으로 끝나면 생략해도 됩니다.'],
    related: ['llmNode', 'googleSheetsNode', 'jsonParserNode'],
  },
  youtubeNode: {
    summary: '유튜브에 영상을 올리거나 기존 영상의 메타데이터·댓글·재생목록을 다룹니다.',
    details: [
      '동작 네 가지 — upload_video(영상 업로드), update_metadata(제목·설명 수정), create_comment(댓글 작성), add_to_playlist(재생목록에 추가).',
      '업로드 시 파일 경로를 비우면 직전 노드의 출력을 경로로 씁니다. 공개 범위 기본값은 private입니다.',
    ],
    usage: ['생성한 영상 자동 업로드', '새 영상에 자동 댓글·재생목록 정리'],
    io: { input: '모드에 따라 파일 경로·텍스트(직전 노드 출력 활용 가능).', output: '처리 결과(JSON).' },
    fields: {
      mode: '네 동작 중 선택. 모드에 따라 필요한 필드가 달라집니다.',
      privacyStatus: '업로드 공개 범위 — 기본 private. 사용자가 명시했을 때만 public으로.',
    },
    tips: ['새 영상 감지는 이 노드가 아니라 YouTube 새 영상(시작) 트리거를 쓰세요.'],
    related: ['youtubeTriggerNode', 'googleDriveNode'],
  },
  gmailNode: {
    summary: 'Gmail로 메일을 발송·답장하거나 임시저장·라벨을 적용합니다. 파일 자동 첨부를 지원합니다.',
    details: [
      '동작 네 가지 — send_email(발송), reply_email(답장), create_draft(임시저장), add_label(라벨 적용).',
      '답장은 message_id만 주면 원본의 제목과 스레드를 자동으로 잇습니다. 없는 라벨은 만들어서 적용합니다. 발송·답장·임시저장은 앞의 파일 생성 노드가 만든 파일을 자동 첨부합니다.',
    ],
    usage: ['새 메일 트리거와 조합한 자동 답장', '생성한 문서를 첨부해 발송'],
    io: { input: '본문을 비우면 직전 노드의 출력을 본문으로 사용.', output: '처리 결과. 발송으로 흐름을 끝내면 결과 출력 생략 가능.' },
    fields: {
      mode: '발송·답장·임시저장·라벨 중 선택.',
      messageId: '답장·라벨 대상 메일의 ID — Gmail 트리거 출력의 message_id를 그대로 쓸 수 있습니다.',
      labelName: '적용할 라벨. 없으면 새로 만듭니다.',
      attachments: '비워 두면 앞 노드가 만든 파일을 자동 첨부합니다.',
    },
    tips: ['단순 SMTP 발송만 필요하면 이메일 전송 노드로도 충분합니다.'],
    related: ['gmailTriggerNode', 'emailNode', 'googleDriveNode'],
  },
  googleDriveNode: {
    summary: 'Google Drive에서 파일을 검색·업로드하고 공유 링크를 만들거나 내려받습니다.',
    details: [
      '동작 네 가지 — search_files(이름 부분 일치 검색), upload_file(업로드), create_share_link(공유 링크), download_file(내려받기).',
      '내려받은 파일은 첨부 가능한 결과물로 저장되므로, 뒤에 이메일·디스코드·Gmail 노드를 연결하면 그 파일이 그대로 첨부됩니다.',
    ],
    usage: ['드라이브의 문서를 찾아 요약·발송', '생성한 파일을 드라이브에 보관하고 공유 링크 발급'],
    io: { input: '업로드 파일 경로를 비우면 직전 노드의 출력을 사용.', output: '검색 결과·파일 정보·공유 링크(JSON).' },
    fields: {
      mode: '네 동작 중 선택.',
      query: '검색 모드에서 파일 이름 부분 일치 검색어.',
      fileId: '공유 링크·내려받기 대상 파일 ID(검색 결과에서 얻을 수 있음).',
    },
    tips: ['검색 → 내려받기 → 발송을 이으면 "드라이브의 OO 문서를 보내줘"가 됩니다.'],
    related: ['googleSheetsNode', 'gmailNode', 'emailNode'],
  },
  httpRequestNode: {
    summary: '임의의 외부 API를 호출합니다. Method·URL·Headers·Body를 자유롭게 구성합니다.',
    details: [
      'GET/POST/PUT/DELETE 요청을 보내고 응답 본문을 다음 노드로 전달합니다. Headers와 Body는 JSON 문자열로 적습니다.',
      '인증 키가 들어가는 Headers는 비밀값으로 취급됩니다 — API 센터 참조를 활용하세요.',
    ],
    usage: ['전용 노드가 없는 서비스의 API 호출', '사내 시스템 연동'],
    io: { input: '필요하면 직전 노드의 출력을 Body에 반영하도록 구성.', output: 'API 응답 본문 — JSON이면 뒤에 JSON 파서를 연결.' },
    fields: {
      method: '요청 의도에 맞는 Method — 조회 GET, 생성 POST.',
      url: '실제 호출 가능한 주소여야 합니다. 모르는 주소를 지어내지 마세요.',
      headers: '인증·형식 헤더(JSON). 예: {"Authorization": "Bearer ..."}',
      body: 'POST/PUT의 데이터(JSON).',
    },
    tips: ['429(요청 한도 초과)가 잦으면 Delay 노드로 간격을 두세요.', '공공데이터포털의 등록된 데이터셋은 전용 노드(공공데이터포털)가 더 간단합니다.'],
    related: ['jsonParserNode', 'delayNode', 'webhookNode', 'dataGoKrNode'],
  },
  naverSearchNode: {
    summary: '네이버에서 블로그·카페 글을 검색해 결과 목록을 가져오는 액션 노드입니다.',
    details: [
      'Workflow 중간에서 최신 글을 수집할 때 씁니다. 출력은 JSON 문자열이고 items 배열의 각 항목은 title·link·description·author·publishedAt입니다(제목의 강조 태그는 제거됨, 카페글에는 publishedAt 없음).',
      '"새 글이 올라오면 시작"이 목적이라면 이 노드가 아니라 네이버 새 검색결과(시작) 트리거를 쓰세요.',
    ],
    usage: ['최신 후기·리뷰를 모아 요약', '검색 결과 링크를 분배기로 순회하며 본문 수집'],
    io: { input: '사용하지 않습니다(검색어는 필드로 지정).', output: '검색 결과 목록(JSON 문자열).' },
    fields: {
      mode: 'blog(블로그) 또는 cafe_article(카페글).',
      query: '검색어. 비우면 직전 노드의 출력을 검색어로 씁니다 — 동적 입력이나 LLM이 만든 검색어를 그대로 넘길 때 유용합니다.',
      display: '가져올 개수(기본 10, 최대 100).',
      sort: 'sim(정확도순) 또는 date(최신순).',
    },
    tips: ['링크 본문까지 필요하면 뒤에 분배기 → 웹 크롤러를 연결하세요.'],
    related: ['naverSearchTriggerNode', 'webCrawlerNode', 'distributorNode'],
  },
  jusoNode: {
    summary: '사람이 쓴 주소를 행정안전부 도로명주소 표준으로 정규화합니다.',
    details: [
      '도로명·지번·우편번호·영문주소를 함께 가져옵니다. 검색어를 비우면 직전 노드의 출력을 주소로 씁니다.',
      '출력은 JSON 문자열이고 items 배열의 각 항목은 roadAddress·jibunAddress·englishAddress·zipCode·buildingName·sido·sigungu 등입니다.',
    ],
    usage: ['주문서·신청서의 주소 표준화', '주소가 섞인 텍스트에서 정확한 배송지 확정'],
    io: { input: '검색어를 비웠을 때 직전 노드의 출력.', output: '표준화된 주소 목록(JSON 문자열).' },
    fields: {
      keyword: '찾을 주소. 비우면 직전 노드의 출력 사용.',
      count: '가져올 개수(기본 10, 최대 100).',
      includeHistory: '행정구역 개편 전 옛 주소로도 찾을지 여부.',
    },
    tips: ['공공데이터 API라 인증키가 필요합니다 — API 센터에 등록해 연결하세요.'],
    related: ['dataGoKrNode', 'jsonParserNode'],
  },
  dataGoKrNode: {
    summary: '공공데이터포털의 미리 등록된 데이터셋(기상청 예보, 과기정통부 보도자료)을 조회합니다.',
    details: [
      '임의 주소를 열지 않습니다 — 등록된 데이터셋만 조회하며, 임의 HTTP 요청이 필요하면 HTTP Request 노드를 씁니다.',
      '데이터셋: kma_village_forecast(기상청 단기예보 — 동작 now/short_forecast/forecast), msit_press_release(보도자료 — 동작 list). 데이터셋별 요청값(기상청은 날짜·좌표 등)은 params(JSON)로 넘깁니다.',
    ],
    usage: ['아침 날씨 브리핑 자동화(스케줄 조합)', '정부 보도자료 모니터링'],
    io: { input: '사용하지 않습니다(요청값은 필드로 지정).', output: '조회 결과(JSON 문자열).' },
    fields: {
      dataset: '조회할 등록 데이터셋.',
      operation: '데이터셋별 동작 — 기상청은 now/short_forecast/forecast, 보도자료는 list.',
      params: '데이터셋별 요청값(JSON). 기상청은 base_date(YYYYMMDD)·좌표 등.',
      rows: '가져올 개수.',
    },
    tips: ['공공데이터포털 활용 신청 후 발급된 인증키를 API 센터에 등록해 연결하세요.'],
    related: ['jusoNode', 'httpRequestNode', 'scheduleNode'],
  },
  naverCafeNode: {
    summary: '네이버 카페 게시판에 글을 쓰거나 카페에 가입합니다 — 외부에 실제로 게시되는 동작입니다.',
    details: [
      'write_article(글쓰기)과 join(가입) 두 동작이 있습니다. 본문을 비우면 직전 노드의 결과를 씁니다.',
      '⚠️ "실제로 게시합니다"(confirm)가 켜져 있어야 실제로 올라갑니다. 기본값은 꺼짐이고 그때는 미리보기만 반환합니다 — 게시 전에 내용을 확인하는 안전장치입니다.',
    ],
    usage: ['완성된 소식지·공지를 운영 카페에 자동 게시', '승인 노드와 조합한 검수 후 게시'],
    io: { input: '본문을 비우면 직전 노드의 출력.', output: '게시 결과(미리보기 모드면 미리보기).' },
    fields: {
      mode: 'write_article(글쓰기) 또는 join(가입).',
      clubId: '카페 고유 숫자 ID(필수).',
      menuId: '게시판 숫자 ID(글쓰기 시 필수).',
      confirm: '꺼져 있으면 미리보기만. 실제 게시 전 사용자 승인 노드를 앞에 두는 것을 권장합니다.',
    },
    tips: ['네이버 사용자 인증(OAuth)이 필요합니다 — API 센터에서 네이버 계정을 연결하세요.'],
    related: ['naverSearchNode', 'humanApprovalNode', 'llmNode'],
  },
  slackNode: {
    summary: '슬랙 채널로 메시지를 발송합니다.',
    details: [
      '직전 노드의 출력을 지정한 채널로 발송합니다. 메시지 필드에 추가 문구를 함께 보낼 수 있습니다.',
    ],
    usage: ['팀 채널로 작업 결과·알림 발송'],
    io: { input: '직전 노드의 출력 — 발송 내용.', output: '발송 결과. 발송으로 흐름을 끝내면 결과 출력 생략 가능.' },
    fields: { channel: '보낼 채널명(예: #general).', message: '직전 노드 출력과 함께 보낼 추가 메시지(선택).' },
    tips: ['슬랙 토큰은 API 센터에 등록해 연결하세요.'],
    related: ['discordNode', 'telegramNode', 'emailNode'],
  },
  paymentLinkNode: {
    summary: '주문 정보를 받아 결제 링크를 생성합니다(조회인 토스페이먼츠 노드와 반대).',
    details: [
      '"주문/결제 링크 만들어줘" 같은 요청에 씁니다. 주문 정보(JSON)를 직접 적거나, 비워 두면 직전 노드의 출력을 그대로 주문 데이터로 씁니다.',
    ],
    usage: ['주문 접수 → 결제 링크 생성 → 고객에게 발송'],
    io: { input: '주문 정보를 비우면 직전 노드의 출력(JSON).', output: '생성된 결제 링크.' },
    fields: { provider: '결제사(기본 toss).', orderData: '주문 정보 JSON. 직전 노드 출력을 쓸 거면 비워 둡니다.' },
    tips: ['결제 정보 조회는 토스페이먼츠 노드를 쓰세요.'],
    related: ['tossNode', 'kakaoNode', 'emailNode'],
  },
  tossNode: {
    summary: '토스페이먼츠 API로 결제 정보를 조회합니다.',
    details: [
      'paymentKey 또는 orderId로 결제 건을 조회합니다. 조회 값을 비우면 직전 노드의 출력을 그대로 씁니다.',
    ],
    usage: ['결제 완료 웹훅 수신 후 상세 조회', '주문 번호로 결제 상태 확인'],
    io: { input: '조회 값을 비우면 직전 노드의 출력.', output: '결제 정보(JSON).' },
    fields: {
      secretKey: '토스페이먼츠 시크릿 키 — API 센터 등록을 권장합니다.',
      searchType: 'paymentKey 또는 orderId 중 조회 기준.',
      searchValue: '비우면 직전 노드 출력을 조회 값으로 사용.',
    },
    tips: ['결제 링크 "생성"은 결제 링크 생성 노드를 쓰세요.'],
    related: ['paymentLinkNode', 'webhookNode', 'jsonParserNode'],
  },
  googleSheetsNode: {
    summary: '구글 시트를 읽거나(조회) 행을 추가하고(append) 범위를 덮어씁니다(write).',
    details: [
      '별도 접속 정보가 필요 없습니다 — 서버가 서비스 계정으로 접근하므로, 사용자는 그 시트를 서비스 계정과 "공유"만 해두면 됩니다.',
      'read의 출력은 행 목록(list of list) JSON 문자열입니다 — 내용을 활용하려면 뒤에 LLM이나 JSON 파서를 연결하세요. append/write에서 기록할 값을 비우면 직전 노드의 출력(JSON)을 그대로 씁니다.',
    ],
    usage: ['수집·집계 결과를 시트에 자동 기록', '시트 데이터를 읽어 보고서 생성'],
    io: { input: 'append/write에서 기록할 값(비우면 직전 노드 출력).', output: 'read는 행 목록(JSON 문자열).' },
    fields: {
      mode: 'read(조회) · append(맨 끝에 한 행 추가) · write(지정 범위 덮어쓰기).',
      spreadsheetId: '시트 URL의 /d/⟨이 부분⟩/edit에 있는 ID.',
      range: '예: "Sheet1" 또는 "Sheet1!A1:D10". 비우면 첫 번째 시트 전체.',
      values: '기록할 값(JSON 배열). 비우면 직전 노드의 출력 사용. read에서는 쓰지 않습니다.',
    },
    tips: ['조회(read)로 끝나면 결과 출력을 붙이고, 기록(append/write)으로 끝나면 생략해도 됩니다.'],
    related: ['googleCalendarNode', 'databaseNode', 'jsonParserNode'],
  },
  googleCalendarNode: {
    summary: '구글 캘린더에 일정을 등록하거나 다가오는 일정을 조회합니다.',
    details: [
      '구글 시트와 같은 서비스 계정을 쓰므로 별도 인증 정보가 필요 없습니다 — 캘린더를 서비스 계정과 공유해 두면 됩니다.',
      '등록할 일정(JSON)의 start/end는 타임존 포함 ISO 8601 문자열이어야 합니다. 비우면 직전 노드의 출력(JSON)을 그대로 씁니다. 조회(list) 출력은 일정 목록 JSON이므로 활용하려면 LLM/JSON 파서를 연결하세요.',
    ],
    usage: ['회의 요청 메일 → 일정 자동 등록', '오늘 일정 조회 → 아침 브리핑'],
    io: { input: 'create에서 일정 JSON(비우면 직전 노드 출력).', output: 'list는 일정 목록(JSON 문자열).' },
    fields: {
      mode: 'create(일정 등록) 또는 list(다가오는 일정 조회).',
      calendarId: '캘린더 설정의 "캘린더 ID" — 보통 본인 gmail 주소.',
      eventData: '{"summary":"...","start":"2026-08-01T10:00:00+09:00","end":"..."} 형식. 비우면 직전 노드 출력.',
      timeMin: '조회 시작 시각(비우면 지금부터).',
    },
    tips: ['일정 JSON은 앞의 LLM에 Structured Output으로 만들게 하면 형식 오류가 없습니다.'],
    related: ['googleSheetsNode', 'llmNode', 'scheduleNode'],
  },
  posterGeneratorNode: {
    summary: '완성된 HTML+CSS를 받아 포스터·전단지·카드뉴스 이미지를 그려서 저장합니다.',
    details: [
      '이 노드 자신은 디자인을 하지 않습니다 — 반드시 직전 노드가 완성된 HTML+CSS 코드 하나를 통째로 만들어 넘겨야 하며, 받은 HTML을 그대로 그려 PNG나 PDF로 저장만 합니다.',
      '그래서 보통 프롬프트 → LLM을 앞에 연결하고, LLM의 시스템 프롬프트에 "전문 그래픽 디자이너로서 완성된 HTML 문서를 만들어라"는 구체적 디자인 지시를 넣습니다 — 지시가 헐거우면 흰 배경에 텍스트만 나열된 밋밋한 결과가 나오기 쉽습니다.',
    ],
    usage: ['"행사 포스터 만들어서 디스코드에 올려줘"', '카드뉴스·안내문 자동 생성'],
    io: { input: '직전 노드의 출력 — 완성된 HTML+CSS 문자열.', output: '저장된 이미지/PDF 파일(뒤의 발송 노드에서 자동 첨부).' },
    fields: {
      outputFormat: 'png 또는 pdf.',
      backgroundPreset: '준비된 배경 프리셋을 깔 수 있습니다.',
      output_path: '비우면 자동으로 이름이 지어집니다.',
    },
    tips: ['파일 저장으로 흐름이 끝나면 결과 출력을 붙이지 않아도 됩니다.'],
    related: ['llmNode', 'imageGenerationNode', 'discordNode', 'emailNode'],
  },

  // ── 문서 (document) ──────────────────────────────────────────────────────
  formatNode: {
    summary: '포맷(빈칸이 선언된 문서·포스터 골격)에 값을 채워 완성 파일을 만듭니다. LLM을 부르지 않는 결정적 노드입니다.',
    details: [
      '포맷은 프리셋 21종 — 문서류(시말서·제안서·입사지원서·회의록·공문·휴가신청서·사직서·지출결의서·주간업무보고서·출장보고서·견적서·거래명세서·재직증명서·표준근로계약서·위임장·보도자료·업무협조전)와 디자인류(행사 포스터·3단 팜플렛·카드뉴스·상장/수료증) — 또는 포맷 스튜디오에서 만든 내 포맷에서 고릅니다. 문서류는 한/글·워드·PDF(일부는 엑셀)로, 디자인류는 PNG·PDF로 출력됩니다.',
      '빈칸 값은 직전 노드의 출력(JSON)에서 같은 이름의 키로 자동으로 채워지고, 노드의 "빈칸 값" 필드로 고정값을 줄 수도 있습니다. 필수 빈칸이 비면 실행이 멈추고 채워 달라고 안내합니다 — 빈 문서가 조용히 저장되는 일이 없습니다.',
      '완성 파일은 자동으로 첨부 가능한 산출물이 되어, 뒤의 이메일·디스코드·Gmail 노드가 그대로 첨부합니다.',
    ],
    usage: ['"시말서 만들어서 메일로 보내줘" 류의 문서 자동화', '수집·판정 결과를 정형 문서·포스터로 발행'],
    io: { input: '빈칸 이름 → 값의 JSON (직전 노드 출력 또는 고정값).', output: '완성 문서/이미지 파일 — 발송 노드에서 자동 첨부. 파일 저장으로 끝나면 결과 출력 생략 가능.' },
    fields: {
      formatId: '프리셋 또는 내 포맷을 선택합니다. 노드에서 빈칸 목록을 미리 볼 수 있습니다.',
      output: '포맷마다 허용 형식이 다릅니다 — 문서류는 hwpx·docx·pdf(표 중심인 제안서·회의록·지출결의서·주간업무보고서·견적서·거래명세서는 xlsx 도), 디자인류는 png·pdf. 비워 두면 포맷의 기본값을 씁니다(노드의 드롭다운이 그 값을 보여줍니다).',
      values: '비우면 직전 노드의 출력(JSON)을 그대로 사용합니다.',
      output_path: '비우면 포맷 이름을 따서 자동으로 지어집니다.',
    },
    tips: [
      '빈칸을 LLM으로 채우려면 앞 llmNode에 Structured Output을 켜세요 — 노드의 "LLM 스키마 복사" 버튼이 빈칸 목록으로 만든 스키마를 복사해 줍니다(이미지 빈칸 제외).',
      '이미 갖고 있는 서식 파일의 빈칸을 채우는 작업이라면 템플릿 분석 → 자동 완성 조합을 쓰세요.',
    ],
    related: ['llmNode', 'templateAnalyzerNode', 'fileModifierNode', 'emailNode'],
  },

  // ── 고급 (advanced) ──────────────────────────────────────────────────────
  fileModifierNode: {
    summary: '템플릿 분석이 찾아낸 빈칸을 실제 값(JSON)으로 채워 문서 파일을 완성합니다.',
    details: [
      '반드시 JSON을 만들어주는 노드 뒤에 연결합니다 — 템플릿 분석 → LLM 조합이 일반적입니다. JSON이 아닌 입력이 오면 빈칸이 하나도 채워지지 않은 채 조용히 저장됩니다.',
      '앞의 LLM에는 시스템 프롬프트 지시만으로 JSON을 기대하지 말고 Structured Output + JSON Schema를 반드시 설정하세요.',
      '.hwpx/.docx는 템플릿이 없어도 자동 생성할 수 있습니다. 구버전 .hwp는 지원하지 않습니다.',
    ],
    usage: ['이미 갖고 있는 서식 파일의 빈칸 자동 채움 — 새 문서를 처음부터 만들 때는 문서 포맷 노드가 더 간단합니다'],
    io: { input: '빈칸 이름 → 값의 JSON.', output: '완성된 문서 파일(뒤의 발송 노드에서 자동 첨부).' },
    fields: {
      template_path: '원본 서식 파일 경로 — 템플릿 분석과 같은 파일.',
      output_path: '비우면 원본 이름을 따서 자동으로 지어집니다.',
    },
    tips: ['파일 저장으로 흐름이 끝나면 결과 출력은 생략 가능합니다.'],
    related: ['formatNode', 'templateAnalyzerNode', 'llmNode', 'hwpxDocumentNode', 'emailNode'],
  },
  templateAnalyzerNode: {
    summary: '서식 파일(.docx/.xlsx/.pptx/.hwpx/텍스트) 안의 빈칸을 스캔해 채워야 할 항목을 뽑아냅니다.',
    details: [
      '값은 채우지 않고 빈칸 목록만 뽑습니다. 출력은 "[채워야 할 빈칸 목록]"과 "[사용 가능한 실제 데이터]"(직전 노드가 갖고 있던 원본)를 함께 담은 텍스트입니다.',
      '순수 JSON이 아니므로 이 노드 바로 뒤에 JSON 파서를 연결하지 마세요. 대신 프롬프트로 "위 빈칸 목록과 실제 데이터로 빈칸을 채운 JSON을 만들어줘"라고 안내한 뒤 LLM(Structured Output)을 거쳐 자동 완성으로 넘기는 것이 정석입니다.',
    ],
    usage: ['서식 채움 파이프라인의 첫 단계(분석 → LLM → 자동 완성) — 서식 파일이 없다면 문서 포맷 노드를 쓰세요'],
    io: { input: '직전 노드의 출력(채울 값의 원천 데이터).', output: '빈칸 목록 + 원본 데이터 텍스트.' },
    fields: { template_path: '분석할 서식 파일 경로. 노드에서 업로드할 수 있습니다.' },
    tips: ['구버전 .hwp는 지원하지 않습니다 — .hwpx로 변환해 사용하세요.'],
    related: ['formatNode', 'fileModifierNode', 'llmNode', 'tokenizerNode'],
  },
  hwpxDocumentNode: {
    summary: '한/글 문서(.hwpx)를 서식 파일 없이 처음부터 만듭니다. 한컴 오피스가 없어도 동작합니다.',
    details: [
      '동작 세 가지 — create(새 문서 만들기), inspect(기존 .hwpx의 빈칸·구조 살펴보기), validate(문서가 열리는 상태인지 검사).',
      'create는 직전 노드가 준 DocumentSpec JSON({"title": "...", "blocks": [{"type": "heading", ...}]})으로 문서를 만듭니다 — 보통 LLM 바로 뒤에 붙이고, 그 LLM이 이 형식의 JSON을 만들게 합니다(Structured Output 권장).',
    ],
    usage: ['보고서·공문을 .hwpx로 자동 생성', '기존 한/글 문서의 구조 파악'],
    io: { input: 'create에서 DocumentSpec JSON.', output: '생성된 .hwpx 파일(뒤의 발송 노드에서 자동 첨부).' },
    fields: {
      mode: 'create(기본) · inspect · validate.',
      output_path: '저장할 파일 이름(선택).',
      source: 'inspect/validate에서 살펴볼 기존 .hwpx 파일.',
    },
    tips: ['서식 파일의 빈칸을 채우는 작업이라면 템플릿 분석 + 자동 완성 조합을 쓰세요.'],
    related: ['fileModifierNode', 'llmNode', 'emailNode'],
  },
  humanApprovalNode: {
    summary: '실행을 실제로 멈추고 사람의 승인·거절을 기다립니다. 결정에 따라 경로를 나눌 수 있습니다.',
    details: [
      '이 노드에 도달하면 실행이 멈추고 소유자에게 알림이 갑니다(사이트 알림 항상 + 이메일/카카오/디스코드 선택). 소유자가 직전 노드의 출력(견본)을 확인하고 승인/거절하면 그 지점부터 이어서 실행됩니다.',
      '승인/거절에 따라 다르게 처리하려면 뒤에 조건 분기를 붙이지 말고 — 값이 "승인" 같은 문자열이 되지 않아 항상 틀리게 분기합니다 — 이 노드 자체의 sourceHandle을 "approved"(승인) / "rejected"(거절)로 나눠 연결하세요.',
      '거절 갈래가 없으면 거절 시 워크플로우가 그대로 중단됩니다. 외부 발송·게시 전 승인이라면 거절 시 흐름(반려 사유 알림 등)도 만들어 두는 것이 좋습니다.',
    ],
    usage: ['외부 발송·게시 전 사람 검수', '금액이 큰 처리 전 승인 게이트'],
    io: { input: '직전 노드의 출력 — 승인 화면에 견본으로 표시되고, 결정과 무관하게 다음 노드로 그대로 전달됩니다.', output: '입력 그대로, approved/rejected 경로로.' },
    fields: {
      message: '승인 요청 알림에 표시할 메시지.',
      notifyDiscord: '켜면 디스코드로도 알림 — 채널 ID가 필요합니다.',
    },
    tips: ['반복(분배기/Loop) 안에 두지 말고 최상위 경로에 두세요 — 반복 문맥 없이 재개됩니다.'],
    related: ['conditionNode', 'naverCafeNode', 'kakaoNode'],
  },
  memoNode: {
    summary: '캔버스에 붙이는 주석입니다. 실행 그래프에 포함되지 않습니다.',
    details: [
      '설명·할 일·주의사항을 캔버스에 적어두는 용도입니다. 실행 순서·연결·검증 어디에도 영향을 주지 않으며, 연결/삽입/교체 후보에서도 제외됩니다.',
    ],
    usage: ['복잡한 흐름의 구획 설명', '함께 작업하는 사람에게 남기는 안내'],
    io: { input: '없음.', output: '없음 — 실행되지 않습니다.' },
    extraFields: [
      { name: 'memo', label: '메모 내용', kind: 'textarea', description: '색상과 글자 크기를 바꿀 수 있습니다.' },
    ],
    tips: [],
    related: [],
  },
};

export const getNodeDoc = (type) => NODE_DOCS[type] || null;
