import {
  Activity, Bot, Boxes, Braces, Cable, Clock, Code2, Command, Database,
  FileText, GitBranch, Globe, Key, LayoutTemplate, MapPin, MessageCircle, MousePointer2,
  PlayCircle, Rocket, Search, Send, Settings2, Sparkles, TestTube, Webhook, Wand2,
} from 'lucide-react';

const foundationLessons = [
  {
    id: 'structure', title: 'Workflow 기본 구조', shortTitle: '입력 · 처리 · 출력', duration: '3분', icon: Boxes,
    description: '데이터가 입력되고 처리된 뒤 결과로 전달되는 기본 흐름을 익힙니다.',
    objective: '데이터 흐름 애니메이션을 끝까지 재생하세요.',
    concepts: ['입력 노드는 Workflow에 데이터를 전달합니다.', '처리 노드는 전달받은 값을 변환하거나 외부 작업을 수행합니다.', '출력 노드는 최종 결과를 사용자나 다른 서비스로 전달합니다.'],
  },
  {
    id: 'placement', title: '노드 배치', shortTitle: '캔버스 조작', duration: '4분', icon: MousePointer2,
    description: '팔레트의 노드를 캔버스에 직접 배치하고 위치를 조정합니다.',
    objective: '입력, 처리, 출력 노드를 각각 하나 이상 배치하세요.',
    concepts: ['노드는 카테고리별 팔레트에서 드래그하거나 클릭해 배치합니다.', '팔레트 상단 검색으로 원하는 노드를 바로 찾을 수 있습니다.', '노드를 드래그해 읽기 쉬운 방향으로 정렬하세요.'],
  },
  {
    id: 'connection', title: '노드 연결', shortTitle: 'Handle과 Edge', duration: '4분', icon: Cable,
    description: '출력 Handle을 다음 노드의 입력 Handle에 연결합니다.',
    objective: '입력 → 처리 → 출력 순서로 두 연결을 완성하세요.',
    concepts: ['오른쪽 Handle은 데이터를 내보내고 왼쪽 Handle은 데이터를 받습니다.', '연결선은 데이터와 실행 순서가 이동하는 방향을 나타냅니다.', '잘못 연결했다면 연결선을 선택하고 삭제할 수 있습니다.'],
  },
  {
    id: 'configuration', title: '노드 입력과 설정', shortTitle: '필드 수정', duration: '4분', icon: Settings2,
    description: '노드를 선택하고 처리에 필요한 세부 입력값을 설정합니다.',
    objective: '처리 노드를 선택하고 프롬프트 내용을 수정하세요.',
    concepts: ['노드마다 실행에 필요한 입력 필드가 다릅니다.', '앞 노드의 결과는 다음 노드의 입력값으로 전달됩니다.', 'API 키는 노드에 직접 남기지 않고 API 센터 연결을 사용합니다.'],
  },
  {
    id: 'execution', title: '실행과 로그', shortTitle: '테스트와 진단', duration: '4분', icon: PlayCircle,
    description: 'Workflow를 실행하고 노드 상태와 로그가 변하는 과정을 확인합니다.',
    objective: '연습 Workflow를 실행하고 성공 로그를 확인하세요.',
    concepts: ['실행 중인 노드는 강조되고 완료된 노드는 성공 상태로 바뀝니다.', '오류가 발생하면 실패한 노드와 해당 로그를 먼저 확인합니다.', '실제 외부 연동 전에는 평가나 Mock 실행을 사용하는 것이 안전합니다.'],
  },
  {
    id: 'assist', title: 'AI 생성과 어시스턴트', shortTitle: '자연어 → Workflow', duration: '4분', icon: Sparkles,
    description: '만들고 싶은 자동화를 문장으로 설명해 초안을 생성하고, 어시스턴트로 수정합니다.',
    objective: 'AI로 초안을 생성한 뒤 수정 요청까지 완료하세요.',
    concepts: ['홈 화면과 에디터의 AI 어시스턴트는 자연어 요청으로 노드를 만들어줍니다.', '생성된 초안은 에디터에서 직접 다듬는 것이 가장 빠릅니다.', '수정 요청은 기존 노드를 유지한 채 필요한 부분만 바꿉니다.'],
  },
  {
    id: 'convenience', title: '에디터 편의 기능', shortTitle: '명령 팔레트 · 빠른 추가', duration: '5분', icon: Command,
    description: '명령 팔레트, 캔버스 빠른 추가, 노드 사이 삽입으로 반복 작업을 줄입니다.',
    objective: '세 가지 편의 기능을 모두 직접 실행하세요.',
    concepts: ['명령 팔레트(Ctrl+K)에서 정렬·검사·저장 같은 명령을 검색해 실행합니다.', '빈 캔버스를 더블 클릭하면 원하는 노드를 바로 검색해 추가할 수 있습니다.', '연결선 사이에 노드를 삽입하면 흐름을 끊지 않고 중간 단계를 추가합니다.'],
  },
  {
    id: 'special', title: '특수 노드', shortTitle: '조건 · 반복 · 병합', duration: '6분', icon: GitBranch,
    description: '조건 분기, 반복, 대기, 병합, 웹훅, 승인 노드가 흐름을 바꾸는 방식을 살펴봅니다.',
    objective: '모든 특수 노드 시뮬레이션을 확인하세요.',
    concepts: ['Condition은 조건에 따라 서로 다른 경로를 선택합니다.', 'Loop는 지정된 횟수나 항목 수만큼 내부 작업을 반복하고, Delay는 정해진 시간을 기다립니다.', 'Merge는 나뉜 경로의 결과를 한 흐름으로 합칩니다.'],
  },
  {
    id: 'deployment', title: '저장과 배포', shortTitle: '공유 준비', duration: '4분', icon: Rocket,
    description: '저장, 검증, 배포 미리보기 순서와 배포 방식의 차이를 익힙니다.',
    objective: '배포 방식을 선택하고 미리보기 검증을 완료하세요.',
    concepts: ['배포 전에 최신 Workflow를 저장하고 한 번 이상 테스트합니다.', 'App Runner는 독립 실행 화면, Chatbot은 대화 UI를 제공합니다.', 'API 방식은 다른 시스템이 Workflow를 호출할 때 사용합니다.'],
  },
].map((lesson) => ({ ...lesson, trackId: 'foundation', labType: 'canvas' }));

const advancedTracks = [
  {
    id: 'triggers', title: '트리거 자동화', shortTitle: 'Schedule · Webhook', icon: Clock,
    description: '시간과 외부 요청을 시작점으로 사용하는 자동화를 구성합니다.',
    lessons: [
      {
        id: 'trigger-choice', title: 'Trigger 선택', shortTitle: '시작 방식 구분', duration: '4분', icon: GitBranch,
        description: '상황에 맞는 Schedule과 Webhook 시작 방식을 구분합니다.', objective: '제시된 세 상황에 알맞은 Trigger를 선택하세요.',
        concepts: ['Schedule은 정해진 시간에 실행합니다.', 'Webhook은 외부 HTTP 요청이 도착할 때 실행합니다.', '한 Workflow에는 의도가 분명한 시작점을 사용해야 합니다.'], scenario: 'trigger-choice',
      },
      {
        id: 'schedule-setup', title: 'Schedule 설정', shortTitle: '주기 · 시간대 · 운영', duration: '6분', icon: Clock,
        description: '실행 주기와 시간대를 설정하고 예약 실행을 시뮬레이션합니다.', objective: '평일 오전 실행 스케줄을 저장하고 테스트하세요.',
        concepts: ['Cron은 분·시·일·월·요일 순서로 표현합니다.', '사용자 시간대와 서버 시간대를 구분해야 합니다.', '관리 화면에서 일시정지와 실행 로그를 확인할 수 있습니다.'], scenario: 'schedule-setup',
      },
      {
        id: 'webhook-setup', title: 'Webhook 수신', shortTitle: 'URL · Payload · 응답', duration: '6분', icon: Webhook,
        description: 'Webhook URL과 JSON Payload를 이해하고 Mock 요청을 전송합니다.', objective: '유효한 JSON 요청을 보내고 200 응답 로그를 확인하세요.',
        concepts: ['Webhook URL은 외부 서비스가 호출하는 진입점입니다.', 'Payload는 요청 Body에 담긴 입력 데이터입니다.', '공개 URL에는 인증과 요청 검증을 추가해야 합니다.'], scenario: 'webhook-setup',
      },
    ],
  },
  {
    id: 'api', title: 'API 연동', shortTitle: 'HTTP · API Center', icon: Key,
    description: '외부 API를 안전하게 호출하고 응답을 처리하는 방법을 익힙니다.',
    lessons: [
      {
        id: 'api-basics', title: 'API 요청의 구조', shortTitle: 'Method · URL · Body', duration: '6분', icon: Braces,
        description: 'HTTP 요청을 구성하는 핵심 요소를 직접 조합합니다.', objective: 'POST 요청을 완성하고 Mock API의 성공 응답을 받으세요.',
        concepts: ['Method는 요청 의도를 표현합니다.', 'Header는 인증과 데이터 형식을 전달합니다.', 'Body는 생성하거나 처리할 데이터를 담습니다.'], scenario: 'api-basics',
      },
      {
        id: 'api-center', title: 'API Center', shortTitle: '키 저장 · 노드 연결', duration: '5분', icon: Key,
        description: '민감한 키를 중앙에 저장하고 노드에서 참조하는 흐름을 익힙니다.', objective: '연습용 키를 등록하고 HTTP 노드에 연결하세요.',
        concepts: ['키를 프롬프트나 노드 텍스트에 직접 넣지 않습니다.', 'API Center의 키는 실행 시점에 안전하게 주입됩니다.', '노출되거나 만료된 키는 즉시 교체해야 합니다.'], scenario: 'api-center',
      },
      {
        id: 'api-errors', title: '응답과 오류 처리', shortTitle: '2xx · 401 · 429', duration: '6분', icon: Code2,
        description: '상태 코드에 맞는 처리 전략과 재시도 여부를 판단합니다.', objective: '세 가지 응답 상태에 맞는 대응을 모두 선택하세요.',
        concepts: ['2xx는 요청이 정상 처리되었음을 뜻합니다.', '401은 인증 정보를 확인해야 하며 무작정 재시도하지 않습니다.', '429는 대기 후 제한적으로 재시도해야 합니다.'], scenario: 'api-errors',
      },
    ],
  },
  {
    id: 'bots', title: '봇 운영', shortTitle: '연결 · 대화 · 로그', icon: Bot,
    description: '메신저 봇을 Workflow와 연결하고 안전하게 운영합니다.',
    lessons: [
      {
        id: 'bot-setup', title: '봇 연결 준비', shortTitle: '플랫폼 · Token', duration: '5분', icon: Key,
        description: '봇 플랫폼을 선택하고 API Center의 연습용 Token을 연결합니다.', objective: '플랫폼과 Token 연결을 완료하세요.',
        concepts: ['Bot Token은 계정 비밀번호처럼 취급합니다.', '수신 Trigger와 발신 노드는 역할이 다릅니다.', 'Token은 API Center에서 교체하고 관리합니다.'], scenario: 'bot-setup',
      },
      {
        id: 'bot-workflow', title: '대화 Workflow', shortTitle: '수신 · LLM · 전송', duration: '6분', icon: Send,
        description: '메시지 수신부터 답변 전송까지의 노드를 올바른 순서로 구성합니다.', objective: '세 단계를 올바르게 정렬하고 테스트 메시지를 처리하세요.',
        concepts: ['Trigger가 사용자 메시지를 Workflow 입력으로 만듭니다.', 'LLM은 정책과 사용자 메시지를 바탕으로 응답을 생성합니다.', '발신 노드가 같은 대화 채널로 결과를 전달합니다.'], scenario: 'bot-workflow',
      },
      {
        id: 'bot-operations', title: '봇 관리와 진단', shortTitle: '시작 · 중지 · 로그', duration: '5분', icon: Activity,
        description: '봇 상태를 제어하고 실패 로그에서 원인을 찾습니다.', objective: '봇을 시작하고 오류 로그의 원인을 확인하세요.',
        concepts: ['운영 중인 봇은 관리 화면에서 상태를 확인합니다.', '401 로그는 Token 만료나 권한 문제일 가능성이 큽니다.', '문제 해결 중에는 봇을 중지해 반복 실패를 막습니다.'], scenario: 'bot-operations',
      },
    ],
  },
  {
    id: 'quality', title: '품질과 운영', shortTitle: '평가 · 개선 · 비용', icon: TestTube,
    description: 'Workflow를 평가하고 개선하며 실행 비용을 점검합니다.',
    lessons: [
      {
        id: 'workflow-evaluation', title: 'Workflow 평가', shortTitle: '리포트 읽기', duration: '6분', icon: TestTube,
        description: '구조, 안정성, 의도 충족 점수를 확인하고 문제 항목을 찾습니다.', objective: '평가를 실행하고 리포트의 세 영역을 모두 확인하세요.',
        concepts: ['평가는 실제 배포 전 구조적 문제를 발견합니다.', '총점보다 실패한 세부 항목이 수정 방향을 알려줍니다.', '평가와 실제 실행 테스트는 서로 대체할 수 없습니다.'], scenario: 'workflow-evaluation',
      },
      {
        id: 'auto-improvement', title: 'AI 자동 개선', shortTitle: '제안 · Diff · 적용', duration: '6분', icon: Wand2,
        description: '평가 제안을 검토하고 필요한 변경만 적용합니다.', objective: '개선 전후 차이를 확인하고 안전한 제안을 적용하세요.',
        concepts: ['자동 개선 결과는 적용 전에 변경 내용을 확인합니다.', '외부 전송이나 삭제 동작은 사람이 다시 검토해야 합니다.', '적용 후에는 평가와 실행 테스트를 다시 수행합니다.'], scenario: 'auto-improvement',
      },
      {
        id: 'cost-readiness', title: '비용과 배포 준비', shortTitle: 'Token · 체크리스트', duration: '5분', icon: Activity,
        description: '노드별 사용량을 확인하고 배포 전 운영 조건을 점검합니다.', objective: '사용량 추적을 켜고 배포 준비 항목을 모두 확인하세요.',
        concepts: ['입력과 출력이 길수록 LLM 사용량이 증가합니다.', '노드별 사용량은 병목과 비용 집중 지점을 보여줍니다.', '키, 오류 경로, 테스트 여부를 배포 전에 확인합니다.'], scenario: 'cost-readiness',
      },
    ],
  },
  {
    id: 'app-builder', title: 'App Builder', shortTitle: '화면 · Workflow · 배포', icon: LayoutTemplate,
    description: 'Workflow를 사용할 수 있는 앱 화면을 구성하고 배포합니다.',
    lessons: [
      {
        id: 'app-components', title: '컴포넌트와 Hierarchy', shortTitle: 'Container · 자식 배치', duration: '7분', icon: LayoutTemplate,
        description: 'Container 안에 입력과 버튼을 배치하고 부모·자식 이동을 이해합니다.', objective: 'Container에 두 컴포넌트를 배치하고 함께 이동하세요.',
        concepts: ['Hierarchy는 컴포넌트의 부모·자식 관계를 표현합니다.', 'Container를 이동하면 자식 컴포넌트도 함께 이동합니다.', '선택한 컴포넌트의 크기와 위치는 속성 패널에서 조정합니다.'], scenario: 'app-components',
      },
      {
        id: 'app-workflow-mapping', title: 'Workflow 연결', shortTitle: '버튼 Action · 입력 매핑', duration: '7분', icon: Cable,
        description: '버튼 동작을 기존 Workflow와 연결하고 입력값을 매핑합니다.', objective: '실행 버튼을 Workflow에 연결하고 미리보기에서 테스트하세요.',
        concepts: ['컴포넌트 이벤트는 Workflow 실행을 시작할 수 있습니다.', '입력 컴포넌트의 값은 Workflow 입력 필드와 매핑합니다.', '실행 결과를 표시할 출력 컴포넌트가 필요합니다.'], scenario: 'app-workflow-mapping',
      },
      {
        id: 'app-playground-deploy', title: 'Playground와 배포', shortTitle: '반응형 · Preview · 배포', duration: '7분', icon: Rocket,
        description: '화면 크기를 바꿔 레이아웃을 확인하고 앱 배포를 완료합니다.', objective: '모바일과 데스크톱 Preview를 확인한 뒤 연습 배포를 완료하세요.',
        concepts: ['Playground 크기는 앱이 표시될 화면을 가정합니다.', '모바일과 데스크톱에서 겹침과 잘림을 확인합니다.', '저장 및 배포 후 공개 URL과 실행 로그를 확인할 수 있습니다.'], scenario: 'app-playground-deploy',
      },
    ],
  },
  {
    id: 'data', title: '데이터 처리', shortTitle: 'DB · 크롤러 · 가공', icon: Database,
    description: '외부 데이터를 안전하게 조회·수집하고 다음 노드가 쓰기 좋게 다듬습니다.',
    lessons: [
      {
        id: 'data-query', title: '데이터베이스 조회', shortTitle: 'SQL Guard · 조회 결과', duration: '5분', icon: Database,
        description: '데이터베이스 노드로 조회 쿼리를 실행하고 위험한 쿼리가 차단되는 방식을 확인합니다.',
        objective: '위험한 쿼리 차단을 확인한 뒤 조회 쿼리를 성공시키세요.',
        concepts: ['조회(SELECT)와 변경(UPDATE·DELETE)은 위험도가 다릅니다.', 'SQL Guard는 읽기 전용 모드에서 변경 쿼리를 실행 전에 차단합니다.', '조회 결과는 행 목록으로 다음 노드에 전달됩니다.'], scenario: 'data-query',
      },
      {
        id: 'data-crawler', title: '웹 크롤러', shortTitle: 'robots · 간격 · 상한', duration: '6분', icon: Globe,
        description: '웹 크롤러 노드가 robots.txt와 요청 간격, 일일 상한을 지키며 수집하는 과정을 실습합니다.',
        objective: '차단되는 페이지와 수집되는 페이지를 모두 실행해 보세요.',
        concepts: ['robots.txt가 거부한 경로는 수집하지 않습니다.', '같은 사이트에는 요청 간격을 두고 접근합니다.', '일일 수집 상한이 있어 무제한 수집이 되지 않습니다.'], scenario: 'data-crawler',
      },
      {
        id: 'data-shaping', title: 'JSON 파서와 분배기', shortTitle: '추출 · 항목별 처리', duration: '6분', icon: Braces,
        description: 'LLM 응답에서 JSON을 추출하고, 분배기로 항목별 처리 결과를 모으는 흐름을 실습합니다.',
        objective: 'JSON을 파싱한 뒤 분배 실행으로 합쳐진 결과를 확인하세요.',
        concepts: ['JSON 파서는 응답 문자열에서 지정한 필드를 추출합니다.', '분배기는 목록의 각 항목을 같은 처리 경로로 하나씩 보냅니다.', '항목별 결과는 순서대로 이어 붙여 하나의 출력으로 모입니다.'], scenario: 'data-shaping',
      },
      {
        id: 'data-binding', title: '값 연결로 LLM 줄이기', shortTitle: '⚡ 바인딩 · 변수 허브', duration: '5분', icon: Cable,
        description: '앞 노드의 값을 다음 노드의 필드에 직접 연결해, 값을 옮기기만 하는 LLM 노드를 없앱니다.',
        objective: '두 필드를 모두 앞 노드의 값에 연결해 LLM 없이 흐름을 완성하세요.',
        concepts: [
          '값을 옮기는 일에 LLM 을 쓰면 매 실행 토큰이 들고 값이 바뀌어 나올 수 있습니다 — 연결은 결과에서 값을 그대로 꺼냅니다.',
          '필드 오른쪽 위 ⚡ 로 앞 노드와 경로를 고릅니다. 캔버스에 선은 생기지 않고, D 를 누르면 점선으로 한눈에 볼 수 있습니다.',
          '연결할 수 있는 것은 실행 순서상 앞선 노드뿐입니다 — 뒤 노드는 실행 시점에 결과가 없습니다.',
          '같은 값을 여러 곳에 쓸 때는 변수 노드에 이름을 붙여 한 번 받고, 하류에서 그 노드를 연결합니다.',
        ], scenario: 'data-binding',
      },
      {
        id: 'data-format', title: '문서로 발행', shortTitle: '포맷 · 빈칸 · 출력', duration: '6분', icon: FileText,
        description: '정리한 데이터를 문서 포맷의 빈칸에 채워 한글·워드·PDF·엑셀 파일로 만듭니다.',
        objective: '빈칸을 모두 채우고 출력 형식을 골라 문서를 생성하세요.',
        concepts: ['포맷은 빈칸 선언과 문서 골격을 함께 담고 있어, 값만 채우면 문서가 완성됩니다.', '정형 데이터는 앞 노드에서 그대로 오고, 비정형 해석만 LLM이 맡습니다 — 문서 포맷 노드 자체는 LLM을 부르지 않습니다.', '필수 빈칸이 비면 실행이 멈춰 알려주므로, 빈 문서가 조용히 저장되지 않습니다.'], scenario: 'data-format',
      },
    ],
  },
  {
    id: 'korea', title: '한국형 연동', shortTitle: '네이버 · 카카오 · 공공데이터', icon: MapPin,
    description: '네이버 검색·카페, 카카오 알림톡, 공공데이터 노드를 상황에 맞게 사용합니다.',
    lessons: [
      {
        id: 'kr-naver', title: '네이버 검색과 카페', shortTitle: '트리거 · 수집 · 게시', duration: '5분', icon: Search,
        description: '네이버 검색 트리거·검색 노드·카페 노드의 역할을 구분해 상황에 맞게 선택합니다.',
        objective: '제시된 세 상황에 알맞은 네이버 노드를 선택하세요.',
        concepts: ['네이버 새 글 감지는 새 글이 발견될 때 Workflow를 시작합니다.', '네이버 검색은 Workflow 중간에서 최신 글을 수집하는 액션 노드입니다.', '네이버 카페 노드는 완성된 결과를 카페 게시글로 발행합니다.'], scenario: 'kr-naver',
      },
      {
        id: 'kr-kakao', title: '카카오 알림톡', shortTitle: '템플릿 · 변수 · 발송', duration: '5분', icon: MessageCircle,
        description: '사전 승인된 템플릿과 변수 치환으로 알림톡을 발송하는 규칙을 실습합니다.',
        objective: '승인된 템플릿에 변수를 채워 발송을 완료하세요.',
        concepts: ['알림톡은 사전 심사를 통과한 템플릿만 발송할 수 있습니다.', '#{변수} 자리에는 실행 시점의 값이 치환됩니다.', '미등록 문구 발송 시도는 반려되며, 템플릿을 먼저 등록해야 합니다.'], scenario: 'kr-kakao',
      },
      {
        id: 'kr-open-data', title: '공공데이터 활용', shortTitle: '인증키 · 도로명주소', duration: '5분', icon: MapPin,
        description: '공공데이터포털 인증키를 연결하고 도로명주소 검색으로 주소를 표준화합니다.',
        objective: '인증키를 연결하고 주소 검색을 성공시키세요.',
        concepts: ['공공데이터포털 API는 활용 신청 후 발급된 인증키가 필요합니다.', '인증키는 노드가 아니라 API Center에 저장해 연결합니다.', '도로명주소 검색은 입력 주소를 표준 형식(도로명·지번·우편번호)으로 바꿔줍니다.'], scenario: 'kr-open-data',
      },
    ],
  },
];

export const TUTORIAL_TRACKS = [
  {
    id: 'foundation', title: '기본 학습', shortTitle: 'Workflow 시작하기', level: 'basic', icon: Boxes,
    description: '처음부터 실행과 배포까지 한 번에 익히는 필수 과정입니다.', lessons: foundationLessons,
  },
  ...advancedTracks.map((track) => ({
    ...track,
    level: 'advanced',
    prerequisiteTrackIds: ['foundation'],
    lessons: track.lessons.map((lesson) => ({ ...lesson, trackId: track.id, labType: 'guided' })),
  })),
];

export const TUTORIAL_LESSONS = TUTORIAL_TRACKS.flatMap((track) => track.lessons);
export const getTutorialTrack = (trackId) => TUTORIAL_TRACKS.find((track) => track.id === trackId) || TUTORIAL_TRACKS[0];
export const getTutorialLesson = (lessonId) => TUTORIAL_LESSONS.find((lesson) => lesson.id === lessonId) || TUTORIAL_LESSONS[0];
