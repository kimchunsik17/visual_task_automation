# 메인 작업 공간·작업물 목록·홈 채팅 리디자인 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | 구현 계획 v1.0 — 미착수 |
| 작성일 | 2026-08-30 |
| 대상 | 로그인 후 Main Shell, 홈 채팅, 내 워크플로우, 내 앱, 운영 개요·스케줄 |
| 목표 | Blue 중심 Slate UI를 Black/Neutral 중심 작업 공간으로 전환하고, 작업물 정보·한도·행동을 한눈에 제공 |
| 예상 크기 | L, 1명의 숙련된 풀스택 개발자 기준 약 4~6주 |
| 관련 문서 | `DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md`, `STATISTICS_PAGE_AUDIT_AND_IMPROVEMENT_PLAN.md`, `../plans/DATABASE_OPERATIONS_EXPLORER_PLAN.md`, `../ROADMAP.md` |
| 제외 | Workflow Editor 노드 의미 색 재설계, Intro 마케팅 콘텐츠 재작성, 실제 요금제·결제 도입 |

이 문서는 기존 `DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md`의 **Blue 브랜드 유지 판단을 Main Shell과
관리 화면에 한해 대체**한다. Editor의 노드 카테고리 색과 Success/Warning/Danger 같은 의미 색은 없애지
않는다. 이번 작업에는 새 PNG/WebP가 필요하지 않다. 배경·표면·상태는 CSS token과 기존 SVG/Lucide
아이콘으로 구성한다.

## 1. 결론

방향은 **Ink Workspace**로 정한다. 검정색을 큰 면적에 칠하는 것만으로 끝내지 않고 다음 네 계약을 함께
바꿔야 한다.

1. **Monochrome가 기본이고 색은 의미가 있을 때만 쓴다.**
   - 페이지·Sidebar·Card는 Black/Neutral 표면 단계로 구분한다.
   - 주요 CTA는 Blue가 아니라 흰색 배경/검정 글자의 inverse button을 사용한다.
   - Blue는 링크·정보·필요한 focus 보조처럼 기능적 신호로만 남긴다.
   - Green/Amber/Red는 정상·주의·실패/삭제에만 쓴다.
2. **작업물 페이지는 갤러리가 아니라 운영 가능한 Library다.**
   - 제목과 설명뿐 아니라 실행 상태, Trigger, 노드/컴포넌트 수, 최근 실행, 최근 수정, 공개 범위를 보여준다.
   - 항상 보이는 주요 행동과 overflow menu를 제공하고, 삭제를 Card의 가장 눈에 띄는 아이콘으로 두지 않는다.
3. **한도는 생성 실패 뒤에 알리는 오류가 아니라 페이지의 상태다.**
   - `3 / 5 워크플로우`, `1 / 2 스케줄`처럼 사용량과 최대치를 Page Header에서 보여준다.
   - 실제 제한이 없는 앱은 숫자를 꾸며내지 않고 `2개 · 제한 없음`으로 표시한다.
   - 한도 계산과 생성 차단은 같은 서버 서비스가 담당한다.
4. **홈 채팅의 결과는 말풍선이 아니라 작업물이다.**
   - 생성된 Workflow/App을 구조화된 결과 Card로 보여주고 저장·편집·실행·재생성으로 이어지게 한다.
   - 대화 기록은 전역 메뉴를 밀어내지 않는 Drawer로 제공한다.

## 2. 현재 상태와 확인된 간극

### 2.1 시각 구조

- 전역 Dark token은 `#0f172a` 배경, `#1e293b` Card, `#3b82f6` Primary인 Navy/Blue 체계다.
- Main Sidebar의 활성 항목, 링크, Workflow 실행 버튼, clarification chip이 모두 Blue를 사용한다.
- 홈, Workflow 목록, App 목록, 운영 개요는 `MainPage.css`를 공유하지만 JSX inline style이 많아 같은
  역할의 버튼·Card·Header가 서로 다르다.
- 홈 초기 화면은 큰 로고와 한 줄 제목, 입력창만 중앙 768px에 몰려 있어 재방문 사용자의 최근 작업과
  운영 상태가 보이지 않는다.
- 홈 대화 응답의 App 행동은 Purple/Pink와 Green gradient button이고 Workflow 행동은 Blue button이라
  같은 생성 결과가 서로 다른 제품처럼 보인다.
- Sidebar 안에서 `메뉴 | 대화 기록` 탭을 전환하므로 대화 기록을 보는 동안 전역 탐색이 사라진다.

### 2.2 작업물 데이터와 행동

| 화면 | 현재 목록 정보 | 현재 주요 행동 | 빠진 것 |
| --- | --- | --- | --- |
| 내 워크플로우 | 제목, 설명, 공개 범위, 수정 시각 | 편집기, 앱 실행, 삭제 | 노드/Trigger/연동, live·최근 실행, 실행 로그, 실행, 복제, 이름/공개 수정, 버전, 공유 |
| 내 앱 | 제목, 설명, 생성/수정 시각 | Card 클릭 편집, 삭제 | 컴포넌트·로직·연결 Workflow 수, 미리보기, 복제, 이름 수정, 공개/배포 상태 |
| 스케줄 | 제목, cron, 상태, 다음 실행 | 일시 정지/재개, 에디터, 로그, 삭제 | 사람이 읽는 주기, timezone, 마지막 결과, 즉시 실행, 오류 요약, 해당 노드로 이동 |
| 홈 대화 기록 | 제목, 프로젝트 연결 여부 | 열기, 프로젝트 이동, 삭제 | 수정 시각 표시, 검색, 이름 변경, 고정, 생성 결과 종류/상태, 필요할 때만 본문 로드 |

`GET /api/projects/my`는 Card에 필요한 graph 요약이나 최근 실행을 반환하지 않는다. `GET
/api/apps/custom`도 컴포넌트·로직·Workflow mapping 수를 반환하지 않는다. 스케줄 API는 마지막 실행
결과와 timezone을 제공하지 않는다. 따라서 프론트 스타일만 바꿔서는 정보 밀도를 높일 수 없다.

### 2.3 한도 계약의 실제 상태

| 자원 | 현재 서버 제한 | 문제 |
| --- | ---: | --- |
| 수동 Workflow | 사용자당 5개 | 생성 API 안에 숫자와 분류가 hard-code되어 있고 목록 API는 사용량/한도를 반환하지 않음 |
| Schedule | 사용자당 2개 | 실제 타입은 `scheduleNode`인데 quota 검사는 `schedulerNode`를 세어 제한이 적용되지 않을 수 있음 |
| Webhook | 사용자당 2개 | Workflow graph를 매번 전수 순회하여 계산, UI에 남은 개수 없음 |
| Bot | 사용자당 2개 | Workflow graph를 매번 전수 순회하여 계산, UI에 남은 개수 없음 |
| Custom App | 제한 없음 | 최대값이 없으므로 UI가 임의의 `n / max`를 표시하면 거짓 정보가 됨 |

수동 Workflow 여부를 `description.startswith("Auto-generated backend workflow")`로 판별하는 것도 안정적인
도메인 계약이 아니다. SQL의 `NOT LIKE`는 `description IS NULL`인 행을 기대와 다르게 다룰 수 있고,
문구가 바뀌면 사용량과 생성 차단 결과가 달라진다. 또한 현재 count 후 insert 방식은 동시 요청 두 개가
모두 제한을 통과할 수 있다.

### 2.4 홈 채팅의 기술 간극

- `MainPage.jsx`가 초기 Hero, Composer, 대화, 생성 결과 action, 파일 chip과 mode menu를 한 파일에서
  렌더링하며 다수의 hover/색상 상태를 inline style로 직접 바꾼다.
- 생성 중 중단 동작과 명시적인 retry가 없다.
- `/api/chat/sessions`가 Sidebar 목록을 위해 모든 세션의 전체 `messages`를 반환하고, 각 세션의 프로젝트
  존재 여부를 반복 조회한다. 기록이 늘수록 첫 화면 데이터가 불필요하게 커진다.
- 생성 결과는 자연어 답변 아래 버튼 몇 개로만 표현되어 Trigger, 노드 수, 사용 연동과 저장 여부를
  한눈에 확인할 수 없다.
- 사용자 message와 AI reply의 폭·Avatar·행동 위치가 고정되지 않아 긴 Markdown, error, clarification,
  App/Workflow 결과가 한 흐름 안에서 다른 문법으로 보인다.

## 3. 목표 시각 체계: Ink Workspace

### 3.1 Dark-first token

검정색도 한 단계만 쓰면 경계가 사라진다. Page와 Component background를 나누고 hover/active/border를
별도 단계로 둔다. Vercel Geist도 기본 Page/Component 배경과 hover·active·border·text scale을 역할별로
나눈다. 이 구조만 참고하고 해당 제품의 외형을 복제하지 않는다.

| 역할 | Dark 기본값 | Light 대응값 | 용도 |
| --- | --- | --- | --- |
| `--ink-canvas` | `#050505` | `#F7F7F7` | 페이지 최하단 배경 |
| `--ink-shell` | `#090909` | `#FFFFFF` | Sidebar, 상단 Shell |
| `--ink-surface-1` | `#0D0D0D` | `#FFFFFF` | List/Card 기본 |
| `--ink-surface-2` | `#141414` | `#F2F2F2` | Field, 보조 Panel |
| `--ink-surface-3` | `#1B1B1B` | `#EAEAEA` | Hover/selected |
| `--ink-border-subtle` | `#242424` | `#E2E2E2` | 기본 구분선 |
| `--ink-border-strong` | `#3A3A3A` | `#B8B8B8` | 선택·강한 경계 |
| `--ink-text-primary` | `#F5F5F5` | `#111111` | 제목·본문 |
| `--ink-text-secondary` | `#A3A3A3` | `#5F5F5F` | 설명·Metadata |
| `--ink-text-tertiary` | `#737373` | `#777777` | 비활성 보조 정보 |
| `--ink-action-primary` | `#F5F5F5` | `#111111` | 화면의 유일한 Primary CTA |
| `--ink-action-on-primary` | `#0A0A0A` | `#FFFFFF` | Primary CTA 글자 |
| `--ink-focus` | `#FFFFFF` | `#111111` | 2px focus ring |
| `--ink-link` | `#8AB4FF` | `#1859B7` | 본문 링크·정보 동작만 |

기존 `--bg-color`, `--card-bg`, `--primary-color`를 즉시 지우지 않는다. 새 semantic token을 도입하고
Main Shell에 alias한 뒤 화면별 inline literal을 제거한다. Editor/App Builder canvas 전체에 token을 강제로
바꾸지 않고 별도 작업으로 검증한다.

### 3.2 색 사용 규칙

- 기본 선택 상태는 `surface-3 + strong border + primary text`로 표현한다. Blue 배경을 쓰지 않는다.
- Primary CTA는 한 화면 하나만 inverse monochrome로 표시한다.
- 링크와 정보성 badge에만 제한적으로 Blue를 허용한다. Blue 없이도 알 수 있도록 underline, icon,
  label을 함께 사용한다.
- Success `#3CCB8E`, Warning `#F0B849`, Danger `#F26969`는 상태와 파괴적 행동에만 사용한다.
- Workflow 노드와 외부 서비스 로고의 고유 색은 16~20px icon tile 안에만 남긴다.
- gradient, 반복 glow, hover translate는 Main Shell에서 제거한다. Card hover는 표면·border 변화만 사용한다.

### 3.3 형태·밀도·움직임

- Page Header 64px, 기본 content padding 32px, mobile 16px.
- Control 6px, Card/Panel 8px, Dialog 12px radius. Badge만 pill을 허용한다.
- 목록 기본 본문 14px, metadata 12~13px, Page title 24~28px. 숫자는 tabular-nums.
- hover/focus 120~160ms, Drawer 180~220ms. `prefers-reduced-motion`에서는 위치 이동을 제거한다.
- shadow보다 border와 surface 단계로 깊이를 표현한다.
- 본문 대비는 WCAG AA 4.5:1을 기준으로 하고, 상태 경계·focus indicator는 색만으로 구분하지 않는다.

## 4. 목표 Main Shell과 정보 구조

```text
Main Shell
├─ Sidebar 232px
│  ├─ Brand
│  ├─ Navigation (항상 유지)
│  ├─ New / Search
│  └─ Account + usage shortcut
├─ Page
│  ├─ Page Header
│  ├─ Optional resource/filter bar
│  └─ Content
└─ Context Drawer
   ├─ Chat history
   ├─ Resource detail
   └─ Run input / Share / Version detail
```

- Sidebar 활성 항목은 흰색 글자·아이콘과 Neutral selected surface로 표시한다.
- 현재 `메뉴 | 대화 기록` 탭은 없앤다. 전역 메뉴는 사라지지 않고, 대화 기록은 홈의 History button으로
  여는 Drawer다.
- Page Header는 breadcrumb/eyebrow, 제목, 설명, Resource meter, Primary action, overflow 순서를 공유한다.
- 모바일 Sidebar와 Drawer는 동시에 열리지 않으며, 닫을 때 focus를 trigger로 돌려보낸다.

## 5. 작업물 Library

### 5.1 공통 Page Header와 Resource meter

예시:

```text
내 워크플로우                                  [새 워크플로우]
자동화 흐름을 만들고 실행·배포합니다.

워크플로우  3 / 5    남은 2개   [██████░░░░]
```

- `used`, `limit`, `remaining`은 서버 응답만 사용한다. 프론트에 `5`, `2`를 복사하지 않는다.
- `limit == null`이면 `2개 · 제한 없음`으로 표시하고 progress bar를 그리지 않는다.
- 80% 이상일 때만 meter를 강조하고, 100%에서는 생성 버튼을 disabled 처리하며 `한도 관리` 설명을
  바로 제공한다. 서버도 같은 계약으로 생성 요청을 거부한다.
- Workspace가 도입되면 `scope: personal | workspace`를 표시하고 누구의 한도인지 이름을 함께 보여준다.
- 좁은 화면에서는 제목 → 사용량 → Primary action 순으로 줄을 나눈다.

### 5.2 Filter와 보기 방식

- 검색: 제목·설명·노드/연동 이름.
- 필터: 상태(live/stopped/error), Trigger, 공개 범위, 최근 실행 결과.
- 정렬: 최근 수정, 최근 실행, 이름, 생성일.
- 기본은 정보 밀도가 높은 **List view**, 선택적으로 Grid view를 제공한다.
- URL query에 `q`, `status`, `sort`, `view`를 보존해 새로고침·뒤로가기·공유가 가능해야 한다.
- 지금의 `앱 빌더 백엔드 보기`는 checkbox 대신 `종류: 사용자 Workflow | App backend` filter로 바꾼다.

### 5.3 Workflow row/Card 정보 구조

```text
[status] 제목                         [편집] [실행] [···]
         설명 1~2줄
         Schedule · LLM · Gmail       노드 6 · 연결 5
         최근 실행 성공 · 18분 전      수정 2시간 전 · 비공개
```

항상 보이는 행동:

- `편집`: Primary navigation action.
- `실행`: 입력이 필요하면 Run Drawer를 먼저 열고, 없으면 확인 후 실행한다.
- `···`: 키보드와 touch에서 항상 접근 가능하며 hover 전용으로 숨기지 않는다.

Overflow menu:

- 실행 기록
- 배포/공유 및 공개 링크 복사
- App 화면 열기
- 복제
- 이름·설명·공개 범위 수정
- 버전 기록
- 삭제(구분선 아래 Danger)

삭제는 Card 우상단의 빨간 아이콘에서 제거한다. menu label에 대상 이름을 포함한 확인 Dialog를 사용하고,
가능하면 즉시 hard delete보다 복구 가능한 보관함 모델을 후속으로 검토한다. 이번 MVP에서는 기존 삭제
동작을 유지하되 성공/실패 toast와 focus 복귀를 보장한다.

### 5.4 App row/Card

표시 정보:

- 제목·설명, 컴포넌트 수, Logic node 수, 연결 Workflow 수
- 최근 수정, Preview 가능 여부, 공개/배포 상태가 생기면 해당 badge
- 연결이 깨진 Workflow mapping 수가 있으면 Warning

행동:

- 항상 표시: `빌더에서 편집`, `미리보기`
- Overflow: 복제, 이름·설명 수정, 연결 Workflow 보기, 공유 링크, 삭제
- 앱 수 제한은 현재 없으므로 `n개 · 제한 없음`으로 표시한다. 실제 앱 제한을 도입하려면 서버 enforcement와
  요금제 정책을 먼저 확정하고 같은 ResourceUsage 계약에 숫자만 추가한다.

### 5.5 Schedule row/Card

표시 정보:

- `매일 오전 9시` 같은 사람이 읽는 주기와 원문 cron
- timezone, 활성/일시 정지/설정 오류, 다음 실행
- 마지막 실행 결과·시각·소요 시간·토큰
- 연결 Workflow와 schedule node ID

행동:

- 항상 표시: `일시 정지/재개`, `지금 실행`
- Overflow: 해당 Schedule node로 이동, 전체 실행 기록, cron/timezone 수정, 삭제
- 삭제가 Workflow 전체 삭제가 아니라 `scheduleNode`와 연결 edge 제거임을 Dialog에 명확히 쓴다.

## 6. 서버 ResourceUsage와 목록 요약 계약

### 6.1 단일 사용량 계약

```json
{
  "scope": { "type": "personal", "id": "user-7", "label": "내 공간" },
  "resources": {
    "workflows": { "used": 3, "limit": 5, "remaining": 2, "canCreate": true },
    "customApps": { "used": 2, "limit": null, "remaining": null, "canCreate": true },
    "schedules": { "used": 1, "limit": 2, "remaining": 1, "canCreate": true },
    "webhooks": { "used": 0, "limit": 2, "remaining": 2, "canCreate": true },
    "bots": { "used": 1, "limit": 2, "remaining": 1, "canCreate": true }
  }
}
```

`GET /api/me/resource-usage`가 위 응답을 제공한다. 실제 숫자는 config/plan resolver가 결정하고, 생성·복제·
import·App Builder backend Workflow 생성도 같은 `ResourceLimitService.reserve()`를 호출한다.

선행 정리:

1. `Project.kind = workflow | app_backend | imported | system` 같은 명시 필드를 추가하고 description prefix
   분류를 마이그레이션한다.
2. `schedulerNode` 오타를 `scheduleNode`로 고치고 기존 graph fixture로 회귀 테스트한다.
3. count 후 insert 경쟁을 DB transaction/advisory lock 또는 사용량 reservation으로 막는다.
4. 초과 응답은 영어 문자열 400 대신 typed `RESOURCE_LIMIT_REACHED`와 resource/used/limit을 반환한다.
5. 개인과 Workspace의 limit scope를 분리하고, UI가 owner/user를 추측하지 않게 한다.

### 6.2 Workflow 목록 요약

기존 배열 응답을 사용하는 App Builder·Template·Q&A가 있으므로 `/api/projects/my`의 응답 형태를 바로
envelope로 바꾸지 않는다. 기존 항목에 다음 optional 요약 필드를 추가하고 ResourceUsage는 별도 endpoint로
읽는다.

```json
{
  "id": 42,
  "title": "아침 뉴스 요약",
  "kind": "workflow",
  "visibility": "private",
  "isLive": true,
  "summary": {
    "nodeCount": 6,
    "edgeCount": 5,
    "triggerTypes": ["scheduleNode"],
    "integrationTypes": ["webSearchNode", "emailNode"]
  },
  "lastRun": {
    "at": "2026-08-30T08:00:00Z",
    "outcome": "success",
    "durationMs": 1250,
    "totalTokens": 840
  },
  "currentRevision": 7,
  "capabilities": ["edit", "run", "deploy", "duplicate", "delete"]
}
```

- graph 전체를 목록 응답에 싣지 않고 `ProjectRevision.summary` 또는 저장 시 계산한 summary를 재사용한다.
- 최근 실행은 project별 N+1이 아니라 window/subquery 한 번으로 읽는다.
- `capabilities`는 `project_access`가 계산해 Workspace role에 맞는 행동만 활성화한다.
- share token 원문과 credential/file/secret은 목록 응답·telemetry에 넣지 않는다.

App 목록에는 `componentCount`, `logicNodeCount`, `workflowMappingCount`, `brokenMappingCount`, `capabilities`를
추가한다. Schedule 목록에는 `timezone`, `humanSchedule`, `lastRun`, `nodeId`, `capabilities`를 추가한다.

### 6.3 행동 API

- `PATCH /api/projects/{id}/metadata`: graph 전체를 다시 보내지 않고 제목·설명·공개 범위만 수정.
- `POST /api/projects/{id}/duplicate`: credential 원문·upload path를 정화하고 한도 reservation 뒤 복제.
- 기존 run/deploy/live/runs/revisions endpoint를 Card action에 연결.
- `PATCH /api/apps/custom/{id}`와 `POST /api/apps/custom/{id}/duplicate`를 추가하고 owner/workspace 권한 검사.
- Schedule의 `run-now`는 별도 endpoint로 제공해 pause/resume와 의미를 섞지 않는다.
- 모든 action은 서버 `capabilities`와 동일한 권한 판정을 사용하고 성공·실패를 구조화된 toast로 반환한다.

## 7. 홈 채팅 리디자인

### 7.1 빈 대화 상태

```text
Home Header                              [대화 기록] [새 대화]

무엇을 자동화할까요?
Workflow와 App을 만들거나 문서를 기준으로 흐름을 설계하세요.

┌──────────────────────────────────────────────────────┐
│ 요청을 자세히 설명하세요…                            │
│ [첨부] [Workflow | App | 자동] [빠름]         [→]   │
└──────────────────────────────────────────────────────┘

[최근 작업 3개]                    [추천 시작점]
```

- 80px 로고와 일반적인 `쉽고 빠른 업무 자동화` 제목을 줄이고 실제 할 일을 질문하는 제목으로 바꾼다.
- Composer를 첫 화면 핵심으로 유지하되 생성 종류, 복잡도, attachment 상태를 한 surface 안에서 정돈한다.
- plain hint pill 대신 `제목 + 한 줄 결과`가 있는 2×2 starter Card를 사용한다.
- 재방문 사용자에게 최근 Workflow/App 3개와 마지막 상태를 보여주고 바로 이어서 편집하게 한다.
- Onboarding checklist는 콘텐츠 위 floating Card가 아니라 Header 아래 접을 수 있는 progress strip 또는
  Drawer로 이동한다.

### 7.2 대화 상태

- 상단에 대화 제목, 연결 작업물, 새 대화, history를 둔다.
- message column은 760~840px, assistant 결과 Card만 최대 960px까지 확장한다.
- 사용자 message는 compact neutral bubble, AI text는 surface 없는 document형 본문으로 유지하되 Avatar와
  action footer 위치를 고정한다.
- 각 AI message footer: 복사, 다시 생성, 피드백. 오류에는 retry와 trace ID 복사.
- 생성 중에는 단계, 경과 시간, 취소 button을 Composer와 message 한 곳에서만 보여준다.
- Composer는 하단 sticky, 긴 대화에서 focus가 가려지지 않게 safe-area와 scroll padding을 둔다.
- 파일 chip, upload progress/error, clarification option을 공통 Chip/Button으로 이전하고 inline hover를 제거한다.

### 7.3 생성 결과 Artifact Card

Workflow 결과:

```text
Workflow 생성됨                                      Draft
아침 뉴스 요약
Schedule → Web Search → LLM → Email
노드 6 · 연결 5 · 외부 연동 2 · 저장 전

[에디터에서 검토] [저장] [다시 생성] [···]
```

App 결과는 컴포넌트 수, 연결 Workflow, Preview 가능 여부를 같은 문법으로 보여준다. 색 gradient나 emoji로
종류를 구분하지 않고 icon + label + metadata를 사용한다. 저장 전 Draft와 저장된 ID를 명확히 구분하고,
세션을 다시 열었을 때 삭제된 작업물을 살아 있는 것처럼 표시하지 않는다.

### 7.4 대화 기록

- Sidebar 메뉴를 바꾸는 탭 대신 우측 또는 좌측 Context Drawer로 연다.
- 목록 endpoint는 `id`, `title`, `updatedAt`, `artifactKind`, `artifactId`, `status`, `messageCount`만 반환한다.
  전체 messages는 세션을 선택할 때 한 건만 불러온다.
- 프로젝트 존재 여부 N+1을 join/subquery로 바꾼다.
- 검색, 오늘/최근 7일/이전 grouping, 이름 변경, 고정, 연결 작업물 열기, 삭제를 제공한다.
- 현재 대화 삭제 뒤 빈 상태로 안전하게 이동하고 focus를 `새 대화`로 돌린다.

## 8. 공통 프론트엔드 컴포넌트

```text
frontend/src/components/product/
  ProductShell
  PageHeader
  ResourceMeter
  CollectionToolbar
  ArtifactList / ArtifactCard
  ArtifactActionsMenu
  StatusBadge
  MetaRow
  ContextDrawer
  Toast

frontend/src/components/chat/
  HomeComposer
  ChatMessage
  GenerationStatus
  GeneratedArtifactCard
  ConversationDrawer
```

- 실제로 두 화면 이상이 공유하는 역할만 추출한다. 한 번 쓰는 Card를 범용 schema renderer로 만들지 않는다.
- MainPage의 inline style과 DOM `onMouseOver/onMouseOut` 변경을 CSS state와 component variant로 옮긴다.
- Button은 `primary-inverse`, `secondary`, `quiet`, `danger`; IconButton은 항상 accessible name을 가진다.
- Menu는 roving focus, Escape 닫기, trigger focus 복귀를 지원한다.
- loading/empty/error/partial-error를 분리하고 Skeleton과 retry를 공통화한다.

## 9. 단계별 구현

### MAIN-0. 사용량·분류·목록 계약 — 3~4일

1. `ResourceLimitService`와 `GET /api/me/resource-usage`를 구현한다.
2. `Project.kind`를 도입하고 기존 description prefix를 backfill한다.
3. `scheduleNode` quota 오타, NULL description count, 동시 생성 경쟁을 회귀 테스트와 함께 수정한다.
4. Workflow/App/Schedule 목록 summary와 `capabilities` API 계약을 확정한다.

완료 기준: UI 표시값과 실제 생성 차단값이 항상 같고, 5개 Workflow 상태에서 동시 생성 두 요청 중 하나만
성공한다.

### MAIN-1. Ink token과 Main Shell — 3~4일

1. Dark/Light semantic token과 기존 변수 alias를 추가한다.
2. Sidebar, PageHeader, Button, IconButton, Menu, Badge, Drawer, Toast를 vertical slice로 만든다.
3. Sidebar 활성 상태를 Blue fill에서 Neutral surface로 바꾸고 chat history를 Drawer trigger로 분리한다.
4. 1440/1280/390px Shell과 keyboard focus를 검증한다.

완료 기준: Main Shell에서 파랑 없이도 현재 위치와 Primary action을 구분하고, 전역 메뉴가 어떤 Drawer에서도
사라지지 않는다.

### MAIN-2. 내 Workflow vertical slice — 4~5일

1. Resource meter, search/filter/sort, List/Grid 전환을 적용한다.
2. summary/lastRun/capabilities를 연결하고 list row와 mobile Card를 만든다.
3. 편집·실행·로그·배포/공유·복제·metadata 수정·버전·삭제 action을 연결한다.
4. empty/loading/error/limit reached와 app backend filter를 검증한다.

완료 기준: Workflow graph를 열지 않고도 최근 상태와 구조를 파악하고, 삭제 외 주요 행동을 한 곳에서
수행할 수 있다.

### MAIN-3. 홈 채팅 — 5~7일

1. MainPage를 HomeComposer, ChatMessage, GeneratedArtifactCard로 분리한다.
2. 초기 화면에 최근 작업과 starter Card를 추가한다.
3. sticky Composer, 생성 취소/retry, message action, Artifact Card를 적용한다.
4. Chat session summary/lazy load, history Drawer, 검색·이름 변경·고정을 구현한다.
5. 긴 Markdown, file upload, clarification, Workflow/App/error/cancelled 상태를 전부 검증한다.

완료 기준: 생성 성공 뒤 `에디터에서 검토`까지 행동이 명확하고, 세션 100개가 있어도 전체 message 본문을
첫 요청에 내려받지 않는다.

### MAIN-4. App·Schedule·운영 개요 — 5~7일

1. App 목록을 공통 Library 문법으로 이전하고 preview/duplicate/metadata action을 연결한다.
2. Schedule 목록에 human schedule, timezone, lastRun, run-now와 node deep link를 추가한다.
3. 운영 개요에 Webhook/Bot/Schedule `used / limit`, 활성/오류 상태와 문제 항목 바로가기를 제공한다.
4. 운영 개요와 하위 navigation에 `연결된 데이터베이스` 진입점을 추가한다. 실제 Schema/Data Grid·
   JSON/XLSX export·안전한 수정은 백로그 31번의 별도 계획을 따른다.
5. 각 화면의 inline style과 전용 red delete icon을 공통 component로 교체한다.

완료 기준: Workflow/App/Schedule이 같은 정보 위계와 action 문법을 사용하고, 제한이 없는 자원은 제한이
있는 것처럼 보이지 않는다.

### MAIN-5. 반응형·접근성·점진 출시 — 3~5일

1. 1440×900, 1280×800, 1024×768, 390×844에서 visual regression 기준 화면을 만든다.
2. keyboard-only, screen reader name, 200% text zoom, reduced motion, Dark/Light를 검증한다.
3. `MAIN_INK_V1` flag로 내부 사용자 → 일부 사용자 → 전체 순서로 연다.
4. 구/신 화면의 작업 완료 지표와 오류율을 비교하고 flag를 제거한다.

## 10. 검증 매트릭스

| 층 | 필수 검증 |
| --- | --- |
| 한도 | Workflow 0/4/5, App unlimited, Schedule 0/1/2, app backend 제외, NULL description, import/duplicate/동시 생성 |
| 정보 | graph를 목록에 싣지 않고 node/edge/trigger 요약이 정확한지, 최근 실행이 project별 N+1 없이 맞는지 |
| 권한 | owner/workspace 역할별 capabilities와 실제 endpoint 허용이 일치하는지, 숨긴 버튼만으로 권한을 막지 않는지 |
| 행동 | 편집, 실행 입력, 로그, 배포/공유, 복제, metadata, version, pause/resume/run-now, 삭제 성공·실패 |
| 채팅 | 빈 상태, 긴 대화, Markdown/code, attachment, clarification, Workflow/App 결과, error/cancel/retry, session lazy load |
| 접근성 | 본문 4.5:1, 큰 글자/상태 UI 3:1, 2px focus, 키보드 Menu/Drawer, touch target 44px, focus not obscured |
| 반응형 | Header/action wrap, List→Card 전환, sticky Composer, Sidebar/Drawer 상호 배타, 가로 overflow 0 |
| 테마 | Dark가 기본이며 Light preference도 정보 손실 없이 동작, node/semantic color가 Black surface에서 식별되는지 |
| 회귀 | Editor/App Builder 기능, 기존 list API 소비자, legacy route, Tutorial selector가 깨지지 않는지 |

프론트 pure helper는 현재의 `node:test` 방식을 사용하고, 핵심 사용자 흐름 세 가지(Workflow 열기/실행,
한도 도달, 홈 생성→Artifact 열기)는 Playwright 기반 브라우저 테스트를 추가한다. 접근성 자동 검사는 보조
수단이며 keyboard와 screen reader 수동 검증을 출시 gate에서 제외하지 않는다.

## 11. 성공 지표와 중단 기준

성공 지표:

- `/workflows` 진입 후 원하는 Workflow 열기까지 median 시간과 클릭 수
- Card의 비삭제 action 사용률, 실행 기록/복제/공유 도달률
- 생성 시도 뒤 `RESOURCE_LIMIT_REACHED`로 처음 한도를 알게 되는 비율
- 홈 prompt 전송률, 생성 성공률, 결과 Artifact Card의 `검토/열기` 전환율
- 기존 세션 재개율과 새 대화 시작률
- 삭제 직후 취소/문의율, 즉시 뒤로가기율
- mobile 가로 overflow·Drawer focus 이탈·Composer 가림 오류 0건

중단 또는 재검토:

- Black surface 단계가 실제 모니터에서 구분되지 않으면 shadow를 늘리기 전에 border/text token 대비를
  조정한다.
- 정보가 많아 Workflow 찾는 시간이 늘면 필드를 무작정 제거하지 않고 기본 List와 compact view를 분리한다.
- Card action이 권한 오류를 자주 내면 UI 조건을 추가하기 전에 서버 `capabilities`와 실제 access 판정을
  하나로 합친다.
- Home 최근 작업이 Composer 전환을 낮추면 삭제하지 않고 첫 화면 아래로 이동해 역할을 분리한다.
- App quota 정책이 정해지지 않았는데 숫자 max를 먼저 디자인하지 않는다. `제한 없음`이 정직한 기본값이다.

## 12. 예상 변경 위치

- `frontend/src/index.css`: Ink semantic token과 기존 alias
- `frontend/src/MainSidebar.jsx`, `MainSidebar.css`: Neutral active state, History Drawer trigger
- `frontend/src/pages/MainPage.jsx`, `MainPage.css`: Home/Chat 분리와 inline style 제거
- `frontend/src/ChatSidebar.jsx`, `ChatSidebar.css`: summary/lazy-load 기반 Conversation Drawer로 전환
- `frontend/src/pages/WorkflowsPage.jsx`: Workflow Library vertical slice
- `frontend/src/pages/CustomAppsDashboardPage.jsx`: App Library
- `frontend/src/pages/SchedulerPage.jsx`, `SchedulerPage.css`: Schedule summary/action
- `frontend/src/pages/OperationsOverviewPage.jsx`: Resource usage와 문제 상태
- `frontend/src/navigation.js`: 운영의 `연결된 데이터베이스` 진입점(기능 본체는 백로그 31번)
- `backend/main.py`: ResourceUsage, list summary, metadata/duplicate/run-now endpoint
- `backend/models.py`, Alembic migration: `Project.kind`와 필요한 App/usage metadata
- `backend/project_access.py`: list item capabilities 정본
- 신규 `backend/resource_limits.py`: 사용량 계산·reservation·typed error

## 13. 참고 기준

- [Vercel Geist Colors](https://vercel.com/geist/colors): Page/Component 배경, hover/active, border,
  text/icon을 역할별 scale로 구분하는 공식 색 체계
- [Vercel Geist Material](https://vercel.com/geist/material): Dark surface에서 shadow만으로 깊이를 표현하지
  않고 낮은 elevation과 경계를 함께 사용하라는 기준
- [WCAG 2.2](https://www.w3.org/TR/wcag/): 본문 대비, keyboard focus와 일관된 navigation 기준
- [W3C WCAG 2.2 변경 사항](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/): focus가 sticky
  Composer/Drawer에 가려지지 않아야 하고 조작 target과 focus indicator가 식별되어야 한다는 기준
