# TemplateModal 이모지 제거 — 기존 아이콘 재사용 매핑

> 대상: [frontend/src/TemplateModal.jsx](../../../frontend/src/TemplateModal.jsx) · 작업일: 2026-08-27
> [icon-generation-prompts.md](icon-generation-prompts.md) §1 "다음에 할 일" 2순위 항목의 실행 기록.
> **신규 SVG 0개** — 전부 B1~B8 에서 만든 기존 아이콘(node 37 / nav 14) 재사용으로 해결했다.

## 결과 요약

| 지표 | 작업 전 | 작업 후 |
|---|---|---|
| TemplateModal.jsx 이모지 | **22개** (19종) | **0개** |
| 신규 제작 아이콘 | — | **0개** |

> 원 계획 문서에는 "이모지 21개(18종)"로 기록돼 있었는데 실측 **22개(19종)** 였다 —
> `⏲️ 지연 리마인더`(builtin-14)가 목록에서 빠져 있었다. 함께 제거했다.

## 구조

이모지는 각 템플릿의 `name` 문자열 맨 앞에 박혀 있었고, 렌더 지점은 두 곳이다:
카드 헤더 `<h4>{t.name}</h4>` 와 인포 팝업 `<h3>{t.name} 사용법</h3>`
(로드 확인 다이얼로그도 `name` 을 그대로 인용하므로 자동으로 깨끗해짐).

→ `name` 에서 이모지를 떼고 템플릿 정의에 `icon`(아이콘명) / `iconColor` 필드를 추가,
두 렌더 지점 모두 `<Icon name={t.icon} size={18} color={t.iconColor}/>` 를 제목 앞에 붙였다.
사용자 저장 템플릿은 `icon` 필드가 없으므로 아이콘 없이 기존과 동일하게 렌더된다 (`t.icon &&` 가드).

## 매핑 표 (22개)

**매핑 원칙: 템플릿이 실제로 사용하는 핵심(=정체성) 노드의 아이콘.** 색은 Sidebar.jsx /
nodeRegistry.js 의 노드 고유색.

| 템플릿 | 이모지 | 아이콘 | 색 | 선정 근거 |
|---|---|---|---|---|
| 문서 자동 채우기 (이력서) | 📝 | `node-file-modifier` | `#f43f5e` | 최종 노드 = fileModifierNode ("자동 채우기") |
| 단순 번역 파이프라인 | 🌐 | `node-llm` | `#8b5cf6` | 번역을 수행하는 유일한 실질 노드 = llmNode |
| 동적 챗봇 템플릿 | 🤖 | `node-dynamic-input` | `#d946ef` | "동적"이 정체성 — dynamicInputNode 가 차별 요소 |
| 동적 뉴스 요약기 | 📰 | `nav-patch-notes` | `#f59e0b` | 뉴스/기사 = 두루마리+기사줄. 크롤러 아이콘은 Tool Agent 카드에 양보 |
| 조건부 자동 응답기 | ❓ | `node-condition` | `#0ea5e9` | conditionNode 분기가 정체성 |
| API 데이터 가져오기 | 🌐 | `node-http-request` | `#0ea5e9` | 핵심 노드 = httpRequestNode |
| 웹훅 알리미 | 💬 | `nav-webhooks` | `#0ea5e9` | 웹훅으로 "보내는" 쪽 — 수신 노드(`node-webhook`)와 구분해 갈고리 사용 |
| 다중 소스 병합 | 🔗 | `node-merge` | `#ec4899` | mergeNode 가 정체성 |
| 승인 기반 자동 발행 | 📝 | `node-human-approval` | `#f43f5e` | humanApprovalNode 가 차별 요소 |
| 서버 상태 경고 알림 | 🚨 | `node-kakao-alimtalk` | `#eab308`* | 경고를 실제 발송하는 노드. 알림 벨 배지가 🚨 의미도 담음 |
| 고객 피드백 감정 분석 | 📊 | `node-database` | `#059669` | 피드백 소스 = databaseNode |
| 자동화된 SEO 리포트 | 📈 | `nav-statistics` | `#10b981` | "리포트/지표"가 결과물 — 막대+상승선 |
| 데이터 클렌징 파이프라인 | 🧹 | `node-python` | `#eab308` | 클렌징을 수행하는 노드 = pythonNode |
| 지연 리마인더 | ⏲️ | `node-delay` | `#3b82f6` | delayNode(모래시계)가 정체성 |
| 복합 이벤트 프로세서 | 🧠 | `nav-workflows` | `#8b5cf6` | 정체성이 특정 노드가 아니라 5단 파이프라인 그 자체 — 미니 플로우 |
| 디스코드 AI 챗봇 | 🤖 | `node-discord-trigger` | `#5865F2` | 봇 얼굴 말풍선 = 디스코드 상호작용 봇 |
| 멀티에이전트 - Supervisor | 👨‍💼 | `node-multi-agent` | `#6366f1` | 상단 원이 큰 3원 구도가 supervisor 함의 그대로 |
| 멀티에이전트 - Group Chat | 🗣️ | `node-prompt` | `#3b82f6` | 말풍선 = 토론. multi-agent 아이콘은 Supervisor 카드와 나란해 회피 |
| 멀티에이전트 - Tool Agent | 🛠️ | `node-web-crawler` | `#0ea5e9` | 시나리오의 도구가 "웹 검색" — 지구+돋보기 |
| 스마트스토어→알림톡 자동화 | 🛍️ | `node-webhook` | `#0ea5e9` | 트리거 = webhookNode (주문 웹훅 수신) |
| B2B 리드 분석·슬랙 알림 | 🏢 | `node-slack` | `#0ea5e9` | 결과 액션 = Slack 알림 |
| AI 챗봇 동적 결제 시스템 | 💳 | `node-payment-link` | `#03c75a` | 핵심 노드 = paymentLinkNode |

\* 카카오 노드 고유색은 `#facc15` 지만 **라이트 테마 카드 위에서 대비가 죽는다**
(사이드바는 `${color}20` 색칩 배경이 받쳐주지만 카드 제목엔 칩이 없음).
같은 계열 한 단계 어두운 `#eab308` 로 조정 — 같은 색을 쓰는 파이썬 카드로 양 테마 가독성이 검증된 값이다.

같은 아이콘을 두 번 쓴 항목은 없다 (22카드 22종). `#0ea5e9` 색은 6카드에서 반복되지만
전부 노드 고유색 그대로이고, 인접 카드끼리는 실루엣이 명확히 다른 것을 렌더로 확인했다.

## 렌더 검증

임시 하니스(`template-harness.html` + `src/template-harness.jsx`, B6 방식 — 검증 후 삭제)로
dev 서버(5173)에서 TemplateModal 을 직접 마운트, Playwright 로 촬영해 확인했다.

- **카드 22 / 제목 SVG 22**, 콘솔 에러·경고 0 (Icon 로더는 미등록 이름에 경고를 내므로 매핑 전부 유효)
- 다크·라이트 양 테마, 카드 그리드 상/하단 + 인포 팝업 + 카드 클로즈업
- 광학 크기: `size={18}` — 제목 1.1rem(17.6px) 옆에서 이모지 대비 작아 보이지 않음 (클로즈업으로 확인)
- 정렬: 제목이 두 줄로 감기는 카드(Supervisor, Group Chat, 스마트스토어)에서 아이콘이
  첫 줄에 붙도록 `align-items: flex-start` + 아이콘 `margin-top: 2px` (TemplateModal.css)
- `npx vite build` 통과

**렌더로 발견해 고친 문제 1건**: 라이트 테마에서 `#facc15` 경고 알림 아이콘이 거의 안 보임 → `#eab308` 로 조정 (위 각주).

스크린샷: `/tmp/claude-1000/-home-ubuntu/1bfeb871-95b6-4056-84c0-723093f0178d/scratchpad/template-emoji/` (세션 임시 경로)

## 부적합 매핑 (신규 제작 후보)

치명적 오매핑은 없지만, 나중에 아이콘을 더 만들 일이 있으면 아래 2개가 후보다:

| 카드 | 현재 | 아쉬운 점 |
|---|---|---|
| 멀티에이전트 - Tool Agent (🛠️) | `node-web-crawler` | "도구를 쓰는 에이전트" 일반 개념이 아니라 예시 시나리오(웹 검색)에 맞춘 매핑. 렌치/도구 모티프가 없음 (`nav-settings` 기어는 앱에서 "설정" 의미로 고정돼 있어 오용) |
| 스마트스토어→알림톡 (🛍️) | `node-webhook` | 트리거 노드 기준으론 정확하지만 "쇼핑/주문" 의미는 담지 못함. 쇼핑백 모티프가 없음 |

## 함께 고친 별개 버그 1건

두 템플릿이 `id: 'builtin-14'` 를 중복 사용하고 있었다 (⏲️ 지연 리마인더 · 💳 AI 챗봇 동적 결제).
`id` 는 카드 목록의 React key 로 쓰이므로 중복 키 상태였다 → 결제 템플릿을 `builtin-17` 로 변경.

## 변경 파일

- `frontend/src/TemplateModal.jsx` — 이모지 22개 제거, `icon`/`iconColor` 22쌍 추가, 렌더 2곳 `<Icon>` 삽입, id 중복 수정
- `frontend/src/TemplateModal.css` — 제목 아이콘 정렬 (`.template-title-icon`, h4/h3 flex) 만 추가
