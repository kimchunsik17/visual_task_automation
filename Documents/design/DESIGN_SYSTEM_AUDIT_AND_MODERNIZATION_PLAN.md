# 제품 디자인 감사와 현대화 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | 제안안 v1.0 |
| 작성일 | 2026-08-27 |
| 범위 | 로그인 후 제품 UI, Workflow Editor, App Builder, Tutorial, 소개 페이지 |
| 목표 | 현재 디자인 기조를 보존하면서 현대적인 IT 서비스 수준의 일관성, 정보 위계와 반응형 사용성을 확보 |
| 제외 | 이번 문서에서는 실제 UI 코드, 브랜드 로고와 기능 동작을 변경하지 않음 |

> **2026-08-30 적용 범위 갱신:** Main Shell·홈 채팅·Workflow/App/Schedule 목록의 Blue 유지 판단은
> `MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md`의 Black/Neutral **Ink Workspace** 방향이 대체한다.
> Workflow Editor와 App Builder의 도구 문법, 노드 의미 색, 접근성·공통 컴포넌트 원칙은 이 문서를 계속
> 따른다.

## 1. 검토 방법

다음 자료를 기준으로 현재 상태를 확인했다.

- 전역 스타일과 테마 변수: `frontend/src/index.css`
- 전역 탐색: `frontend/src/MainSidebar.jsx`, `frontend/src/MainSidebar.css`
- 홈과 목록 화면: `MainPage`, `WorkflowsPage`, `TemplatesPage`
- 핵심 제작 화면: `EditorPage`, `AppBuilderPage`
- 운영 화면: API Center, Scheduler, Bot Manager, Webhook Manager, Statistics
- 학습과 소개 화면: `TutorialPage`, `IntroPage`
- 1440×900 데스크톱과 390×844 모바일 브라우저 렌더링
- CSS 약 10,782줄, 색상 literal, radius, inline style과 breakpoint 사용 현황

이 평가는 기능 완성도보다 시각 언어, 화면 구조, 컴포넌트 일관성과 사용성을 중심으로 한다.

## 2. 결론 요약

현재 사이트는 **어두운 Slate 기반의 노코드 자동화 작업 도구**라는 기조가 분명하다. 파란색을 주 액션에 사용하고, Trigger·LLM·출력 같은 노드는 별도 의미 색으로 구분한다. Editor와 Tutorial은 비교적 조밀하고 정돈된 반면, 홈·목록·관리 화면과 App Builder는 서로 다른 시기에 별도 스타일로 만들어진 인상이 강하다.

새로운 시각 콘셉트를 덧씌우기보다 다음 세 가지를 먼저 통일하는 것이 효과가 크다.

1. **전역 Design Token과 공통 컴포넌트**
   - 정의되지 않은 변수, hard-coded color, inline style을 정리한다.
   - Button, Field, Page Header, Tabs, Drawer, Dialog 같은 기본 부품을 하나로 통합한다.

2. **화면 성격에 따른 두 가지 App Shell**
   - 관리 화면은 전역 사이드바와 일관된 Page Header를 사용한다.
   - Editor와 App Builder는 제작에 집중하는 전체 화면 Tool Shell을 공유한다.

3. **모바일에서 한 번에 한 작업만 표시**
   - 데스크톱의 3열 구조를 모바일에 축소하지 않는다.
   - Palette, Canvas, Inspector를 탭·Drawer·Bottom Sheet로 전환한다.

추천 디자인 방향은 **Calm Technical Workspace**다. 중립적인 Graphite 표면, 선명하지만 제한된 Blue 브랜드 색, 상태 의미에만 사용하는 Green·Amber·Red·Violet, 얇은 경계선과 작은 반경, 4px 단위의 조밀한 간격을 사용한다.

## 3. 현재 디자인 기조

### 3.1 시각적 성격

| 요소 | 현재 상태 | 평가 |
| --- | --- | --- |
| 제품 유형 | Workflow Automation, AI Builder, 운영 Dashboard | 작업 중심 SaaS 방향이 적합함 |
| 기본 테마 | Dark-first Navy/Slate | 집중감은 좋지만 화면 전체가 한 색조로 읽힘 |
| 주 색상 | Blue `#3b82f6`, 일부 Cyan | 실행·선택 상태가 이해하기 쉬움 |
| 보조 색상 | Green, Violet, Orange, Red, Pink 등 | 노드 의미에는 유용하지만 페이지 장식에도 섞여 규칙이 흐림 |
| 글꼴 | Inter + Noto Sans KR, 일부 Jua·Quicksand·Poppins·Segoe UI | 제품 내부 글꼴 체계가 분산됨 |
| 형태 | 4~8px 반경 중심, 일부 12~20px와 pill | 도구 화면은 안정적이나 페이지별 반경 차이가 큼 |
| 깊이 | Border 중심, 일부 큰 shadow·glow | Editor는 적절하고 Modal·Landing은 과한 부분이 있음 |
| 아이콘 | Lucide 중심, 일부 emoji·텍스트 기호 | 기본 방향은 좋으나 혼용 제거 필요 |
| 밀도 | Editor는 높고 홈·빈 상태는 낮음 | 같은 제품 안에서 정보 밀도 변화가 큼 |
| 반응형 | 페이지별 개별 breakpoint | 데스크톱 축소 방식이 달라 모바일 품질 편차가 큼 |

### 3.2 화면별 현재 인상

#### 홈

- 중앙의 큰 문구와 넓은 AI 입력창으로 생성 시작점이 분명하다.
- 전역 Sidebar와 별도의 접힌 Chat Sidebar가 동시에 있어 왼쪽 탐색 면적이 중복된다.
- 시작 체크리스트가 주요 화면 위에 떠 있어 첫 사용에는 유용하지만 반복 사용 시 시선을 경쟁한다.
- 넓은 화면에서 주요 콘텐츠가 중앙에만 몰리고 작업 기록이나 최근 항목을 탐색하기 어렵다.
- 모바일에서는 입력창이 화면 가장자리에 밀착되고 체크리스트와 생성 영역의 세로 순서가 느슨하다.

#### Workflow 목록과 Template

- Sidebar, 제목, 주요 액션이라는 기본 구조는 이해하기 쉽다.
- 빈 상태가 큰 Card 안에 다시 버튼을 담는 방식이라 공간이 과도하게 비어 보인다.
- 390px 화면에서 메뉴 버튼, 제목, 옵션, 새 프로젝트 버튼이 같은 행에 겹친다.
- 필터와 검색 UI가 JSX inline style로 구현되어 다른 관리 화면과 모양이 달라질 가능성이 높다.

#### Workflow Editor

- 현재 제품에서 가장 일관성이 높은 화면이다.
- 상단 Toolbar, 왼쪽 Node Palette와 Canvas의 역할이 명확하다.
- 작은 반경, 낮은 shadow와 dot grid가 기술 도구의 인상을 잘 만든다.
- 체크리스트가 Canvas 위에 떠 있어 노드가 늘어나면 작업 영역을 가릴 수 있다.
- 노드 설정이 노드 내부에 들어가면서 크기와 Canvas 배치가 변하는 구조는 장기적으로 복잡한 노드에 불리하다.
- 모바일은 Palette를 숨기고 Canvas를 확보했지만, 현재 기능 발견과 Inspector 접근 경로가 약하다.

#### App Builder

- Canvas, Component Palette, Hierarchy, Settings라는 데스크톱 구조는 전문 제작 도구에 적합하다.
- `Code Native`, `Blueprint`, `Design`, `Preview`, `Code`, `Global CSS`가 한 Header에서 경쟁한다.
- Orange, Blue, Green, Cyan이 모두 주요 액션처럼 사용되어 시각적 우선순위가 분산된다.
- 일부 Popover가 전역 변수 대신 고정된 `#111827`, `#0b1220`을 사용해 다른 테마와 분리된다.
- 모바일에서 Palette, 좁은 Canvas, Settings가 동시에 3열로 유지되어 실제 조작이 불가능한 수준으로 축소된다.
- Editor와 유사한 제작 도구지만 Toolbar, Panel, Button 문법이 별개 제품처럼 보인다.

#### Tutorial

- 현재 전역 디자인과 가장 잘 맞는 신규 화면 중 하나다.
- Track 선택 화면과 과정 화면이 분리되어 정보량이 통제되어 있다.
- 작은 Card, 제한된 Accent와 명확한 진행률이 작업 도구에 어울린다.
- Tutorial Sandbox가 Editor의 시각 언어를 재사용하는 방향은 유지할 가치가 있다.

#### 소개 페이지

- 제품 내부보다 큰 Typography, Gradient text와 Video를 사용해 마케팅 화면임을 분명히 한다.
- Dark Navy와 Blue/Violet Gradient가 제품 내부의 Slate UI와 연결되지만, 전체 페이지가 유사한 어두운 색조라 콘텐츠 구간의 차이가 약하다.
- 모바일 Hero는 읽기 쉽지만 영상이 지나치게 어둡고 작아 실제 제품을 확인하기 어렵다.
- 제품 내부보다 둥근 CTA와 강한 Glow를 사용해 전환 시 시각적 간극이 있다.

### 3.3 유지해야 할 장점

- Dark-first 도구라는 제품 정체성
- Blue 중심의 선택·실행 상태
- Trigger, Process, Output과 상태를 구분하는 Semantic color
- Lucide 아이콘 중심의 조작 체계
- Editor의 조밀한 Toolbar와 dot-grid Canvas
- Border 중심의 패널 구분
- Tutorial의 실제 화면과 유사한 학습 경험
- Light theme를 고려한 CSS variable 기반

## 4. 핵심 문제

### 4.1 Design Token이 단일 원본이 아님

전역에는 `--bg-color`, `--card-bg`, `--text-color`, `--text-muted`, `--primary-color`가 정의되어 있다. 그러나 일부 화면은 다음과 같은 정의되지 않은 변수를 사용한다.

```text
--bg-primary
--bg-secondary
--bg-hover
--text-primary
--text-secondary
--accent-color
--surface-color
--success-color
--error-color
--sidebar-bg
```

CSS fallback이 없는 사용처는 브라우저에서 선언 전체가 무효가 될 수 있다. Light theme에서도 고정된 Dark color가 남아 표면과 글자가 예상과 다르게 표시될 수 있다.

색상 literal 역시 여러 파일에 반복된다. 조사 시 `#10b981`은 93회, `#3b82f6`은 83회, `#ef4444`는 62회 사용되었다. 이는 같은 의미의 색을 한 번에 조정하기 어렵게 만든다.

### 4.2 공통 컴포넌트보다 페이지별 스타일이 우세함

- `customNodes.jsx`에는 약 197개의 inline style 선언이 있다.
- Settings, Editor, App Viewer, Main Page에도 많은 inline style이 남아 있다.
- 같은 Primary button도 Blue, Green, White-on-dark 방식이 혼재한다.
- Header, Empty State, Search Field, Modal이 페이지마다 별도 구현된다.
- Hover에서 DOM style을 직접 변경하는 코드가 있어 상태 관리와 접근성이 일관되지 않다.

결과적으로 작은 디자인 변경이 여러 JSX와 CSS 파일을 동시에 수정하는 작업이 된다.

### 4.3 Navigation과 App Shell이 일관되지 않음

- 일반 화면은 260px Main Sidebar를 사용한다.
- 홈은 여기에 68px Chat Sidebar를 추가한다.
- Editor와 App Builder는 서로 다른 전체 화면 Header를 사용한다.
- Tutorial은 일반 Sidebar와 전용 Header를 함께 사용한다.
- 페이지마다 콘텐츠 최대 폭, Header 높이와 좌우 padding이 다르다.

화면 성격에 따라 Shell이 달라지는 것은 맞지만, 같은 역할의 Back, Title, Save, Run, AI Assistant가 같은 위치와 모양을 가져야 한다.

### 4.4 모바일은 축소판에 머무는 화면이 있음

실제 390×844 렌더링에서 확인된 문제:

- Workflow 목록 Header의 제목과 옵션, 생성 버튼이 겹친다.
- App Builder는 좌우 Panel과 Canvas가 동시에 남아 Canvas가 가느다란 세로 띠가 된다.
- Home의 생성 입력창이 화면 폭에 밀착되어 주변 여백과 상태 설명을 수용하기 어렵다.
- Editor는 Canvas는 확보하지만 노드 추가와 설정 진입 경로가 Floating button에 과도하게 의존한다.
- 소개 페이지의 실제 제품 영상은 모바일 첫 화면에서 식별하기 어렵다.

페이지마다 430, 480, 520, 560, 600, 720, 768, 900, 992, 1024, 1250px 등 서로 다른 breakpoint를 사용한다. 기준이 많지만 공통 반응형 행동은 적다.

### 4.5 Typography와 밀도 기준이 분산됨

- 제품 내부에서 0.54rem부터 1.5rem 이상까지 작은 단위가 개별 지정된다.
- 홈 Hero는 3rem, App Builder Panel heading은 큰 대문자, 관리 화면은 1rem 안팎으로 차이가 크다.
- 영문 대문자 Section label이 일부 화면에만 적용된다.
- 한국어 본문에서 지나치게 작은 0.6rem대 텍스트가 자주 사용된다.
- Landing에 사용하는 표현적 Typography와 작업 화면 Typography의 경계가 명확하지 않다.

### 4.6 색과 브랜드 신호의 우선순위가 불분명함

- Blue, Cyan, Purple, Green, Orange가 모두 주요 버튼이나 선택 상태에 사용된다.
- AI 기능은 Cyan 또는 Purple, 배포는 Green, App Builder mode는 Orange를 사용하지만 규칙이 문서화되어 있지 않다.
- `WorkFlow Ai`, `My Visual App`, `Code Native` 같은 이름이 같은 단계의 브랜드처럼 나타난다.
- Semantic color와 브랜드 Accent가 혼용되어 사용자가 색만 보고 행동의 중요도를 예측하기 어렵다.

### 4.7 접근성과 상태 표현이 균일하지 않음

- 일부 Icon button은 tooltip과 aria-label이 있지만 일부는 title 또는 아이콘만 있다.
- Hover에서만 드러나는 액션은 Touch 환경에서 발견하기 어렵다.
- Focus ring이 Field마다 다르거나 없다.
- Muted text가 작은 크기와 함께 사용될 때 대비가 부족할 가능성이 있다.
- Loading, Empty, Error, Disabled와 Success 상태가 페이지별로 다른 형식이다.

## 5. 목표 디자인 방향

### 5.1 콘셉트: Calm Technical Workspace

사용자가 반복해서 오래 머무는 제작·운영 도구이므로 마케팅형 장식보다 다음 속성을 우선한다.

- 차분하고 중립적인 작업 배경
- 중요한 Action만 선명하게 보이는 색 위계
- 반복 사용에 맞는 작은 간격과 안정된 위치
- Canvas, List, Inspector 사이의 명확한 역할 구분
- 상태와 위험도를 즉시 읽을 수 있는 Semantic feedback
- 데스크톱과 모바일에서 기능은 같되 화면 배치는 다른 Adaptive UI

### 5.2 색상 체계

기존 Blue 브랜드를 유지하되 Navy 일색에서 중립 Graphite로 이동한다.

| 역할 | Dark 제안 | Light 제안 | 용도 |
| --- | --- | --- | --- |
| Background | `#0B0D12` | `#F6F8FB` | 앱 전체 배경 |
| Surface 1 | `#12161F` | `#FFFFFF` | Sidebar, Header |
| Surface 2 | `#181D27` | `#F0F3F7` | Panel, Field |
| Surface 3 | `#202632` | `#E8EDF3` | Hover, selected surface |
| Border | `#2B3340` | `#D6DCE5` | 기본 경계선 |
| Text Primary | `#F4F7FB` | `#172033` | 제목과 본문 |
| Text Secondary | `#98A2B3` | `#667085` | 설명과 Metadata |
| Brand Primary | `#4F8CFF` | `#2563EB` | 주요 CTA와 선택 |
| AI | `#A78BFA` | `#7C3AED` | AI 생성과 평가 기능 |
| Success | `#31C48D` | `#168A61` | 완료와 정상 상태 |
| Warning | `#F5B942` | `#B66A00` | 주의와 확인 필요 |
| Danger | `#F97066` | `#D92D20` | 삭제와 실패 |

색 사용 규칙:

- 한 화면의 Primary CTA는 원칙적으로 하나만 Blue로 표시한다.
- AI는 기능 식별용 Violet 아이콘이나 작은 Badge에 사용하고 모든 AI 버튼을 보라색으로 만들지 않는다.
- Green은 성공·배포 완료, Red는 파괴적 행동, Amber는 사용자 확인에만 사용한다.
- 노드의 Category color는 작은 Icon tile과 Handle에 제한하고 Panel 전체 배경을 채우지 않는다.
- Gradient는 소개 페이지의 Brand moment에만 제한하고 운영 UI에는 사용하지 않는다.

### 5.3 Typography

제품 내부는 `Inter, Noto Sans KR, system-ui` 하나로 통일한다. Landing의 표현용 글꼴이 필요하면 제품 Shell과 분리한다.

| Token | 크기/행간 | 용도 |
| --- | --- | --- |
| Display | 40/48 | 소개 페이지의 핵심 제목만 |
| Page title | 24/32 | 일반 페이지 제목 |
| Panel title | 16/24 | Panel과 Modal 제목 |
| Body | 14/21 | 기본 본문과 Field |
| Compact | 13/18 | Toolbar와 조밀한 목록 |
| Caption | 12/16 | Metadata, 상태 설명 |
| Micro | 11/14 | Badge와 보조 정보의 최소 크기 |

- 제품 내부에서 11px 미만 텍스트를 사용하지 않는다.
- 한국어 제목에는 음수 letter-spacing을 적용하지 않는다.
- 대문자 영문 Label은 짧은 Category 표시에만 제한한다.
- 숫자와 사용량에는 `font-variant-numeric: tabular-nums`를 적용한다.

### 5.4 간격, 크기와 반경

- Spacing은 4px 기반으로 `4, 8, 12, 16, 24, 32, 48`만 우선 사용한다.
- Toolbar 높이 56px, 일반 Page Header 64px를 기준으로 한다.
- Icon button은 데스크톱 36px, Touch 환경 최소 44px로 한다.
- Field 높이는 compact 32px, default 40px로 제한한다.
- Control radius 6px, Card·Panel 8px, Modal 12px를 기본으로 한다.
- Pill은 Badge, Filter chip, Toggle처럼 의미가 있는 경우에만 사용한다.
- Shadow보다 Border와 Surface 단계로 깊이를 구분한다.

### 5.5 Motion

- Hover와 selection은 120~180ms로 제한한다.
- Drawer와 Panel 전환은 180~240ms로 통일한다.
- Workflow 실행처럼 상태 이해에 도움이 되는 애니메이션은 유지한다.
- 장식적인 이동, 반복 Glow와 Layout을 흔드는 hover transform은 제거한다.
- `prefers-reduced-motion`에서 실행 상태를 제외한 전환을 줄인다.

## 6. 목표 App Shell

### 6.1 관리 화면 Shell

적용 대상: 홈, Workflow, Template, API Center, Bot, Scheduler, Webhook, Statistics, Settings, Tutorial.

```text
Global Sidebar
  232px expanded / 64px collapsed

Page
  Page Header: title, description, primary action, overflow menu
  Optional Filter Bar
  Content: list, table, grid or empty state
```

- Main Sidebar의 섹션을 `Build`, `Operate`, `Learn`, `Account`로 묶는다.
- Chat history는 두 번째 고정 Sidebar가 아니라 홈 또는 Editor의 Drawer로 제공한다.
- 모든 관리 화면은 같은 `PageHeader`와 24~32px content padding을 사용한다.
- Desktop 콘텐츠 최대 폭은 데이터 성격에 따라 1120~1280px로 제한하되 Table은 전체 폭을 허용한다.

### 6.2 제작 도구 Shell

적용 대상: Workflow Editor, App Builder.

```text
Tool Header
  Back / Project identity / View controls / Save state / AI / Run or Deploy / More

Tool Workspace
  Palette / Canvas / Inspector

Auxiliary
  Assistant Drawer / Logs Drawer / Mobile panel switcher
```

- Editor와 App Builder가 같은 Back, Project title, Save, AI, More button을 사용한다.
- `Run`과 `Deploy`만 제품별 Primary action으로 둔다.
- Palette 폭은 232~256px, Inspector는 280~320px 범위로 통일한다.
- Header에 모든 모드를 나열하지 않고 View Tabs와 More menu로 나눈다.
- 상태 정보는 Header를 늘리지 않고 Save indicator, Badge와 Tooltip으로 전달한다.

### 6.3 모바일 Adaptive Shell

- 전역 Sidebar는 Overlay Drawer로 전환한다.
- Page Header는 제목 한 줄, Primary icon button, More menu만 첫 행에 둔다.
- Filter는 별도 두 번째 행이나 Bottom Sheet로 연다.
- Editor와 App Builder는 `Palette | Canvas | Inspector` 중 하나만 주 화면에 표시한다.
- 선택한 노드·컴포넌트의 Inspector는 Bottom Sheet 또는 전체 높이 Drawer로 연다.
- Canvas에 Floating button을 여러 개 두지 않고 하나의 Add button과 Context toolbar를 사용한다.
- 모바일에서 기능을 숨길 경우 숨긴 이유와 Desktop 필요 여부를 명시한다.

## 7. 공통 컴포넌트 계획

### 7.1 Token 계층

```text
Primitive
  color.blue.500, gray.900, spacing.4, radius.6

Semantic
  bg.canvas, bg.surface, text.primary, border.default,
  action.primary, status.success, node.trigger

Component
  button.primary.bg, input.focus.ring, sidebar.active.bg
```

CSS 변수 이름은 `--color-*`, `--space-*`, `--radius-*`, `--size-*` 형태로 통일한다. 기존 변수는 한 번에 제거하지 않고 alias를 둔 뒤 단계적으로 이전한다.

### 7.2 우선 공통화 대상

| 컴포넌트 | 필수 상태 |
| --- | --- |
| Button | primary, secondary, quiet, danger, loading, disabled |
| IconButton | default, active, danger, tooltip, badge |
| TextField/TextArea | default, focus, error, disabled, secret |
| Select/Menu | selected, keyboard focus, empty, grouped |
| SegmentedControl/Tabs | compact, scrollable mobile |
| PageHeader | title, description, actions, breadcrumbs |
| Toolbar | grouped actions, divider, overflow |
| Drawer/BottomSheet | left, right, bottom, responsive |
| Dialog | confirm, form, destructive, loading |
| EmptyState | icon, title, description, one primary action |
| StatusBadge | neutral, info, success, warning, danger |
| Toast/InlineAlert | info, success, warning, error, retry |
| Skeleton | list, card, table, canvas panel |

공통 컴포넌트는 처음부터 범용 디자인 시스템 패키지로 과도하게 추상화하지 않는다. 실제 화면 2곳 이상에서 같은 행동이 확인된 부품부터 추출한다.

## 8. 화면별 개선안

| 화면 | 1차 개선 | 2차 개선 |
| --- | --- | --- |
| 홈 | 이중 Sidebar 제거, 생성 입력 폭과 여백 정리, 체크리스트 비침해형 배치 | 최근 Workflow, 추천 Template와 실행 기록을 조밀한 Section으로 제공 |
| Workflow 목록 | 공통 Page Header, 겹치지 않는 모바일 Action, Empty State 축소 | Grid/List 전환, Filter bar, 상태·최근 실행 중심 Metadata |
| Template | 공통 Search/Filter, Card metadata 통일 | Category와 credential 요구사항, 검증 상태 표시 |
| Editor | Header와 Button token 적용, 체크리스트 최소화 | Node Inspector 도입, Input/Output/Logs 탭, 모바일 Panel switcher |
| App Builder | Editor Tool Shell과 통합, Primary action 하나로 정리 | 모바일 단일 Pane, Component Inspector, Preview preset 개선 |
| API Center | 정의되지 않은 token 제거, Credential Card 통일 | Provider filter, scope·최근 사용·오류 상태 표시 |
| Bot/Scheduler/Webhook | Page Header와 List/Table 패턴 통일 | 운영 상태, 마지막 실행, 오류를 같은 Status 문법으로 제공 |
| Statistics | 숫자 Typography와 Chart palette 통일 | Filter 기간, Empty/Loading/Error 상태 표준화 |
| Tutorial | 현재 Track 분리 구조 유지, token만 통합 | 실제 제품 Shell과 Sandbox 컴포넌트 공유 확대 |
| Intro | 영상 가시성, 제품 UI와 CTA 형태 연결 | 실제 제품 장면 중심 Section, Dark 구간의 명도 차 확대 |

## 9. 단계별 실행 계획

기간은 1명의 숙련된 Frontend 개발자를 기준으로 한 상대 추정치이며 기능 수정은 포함하지 않는다.

### Phase 0. 기준선과 결정, 1주

- Dark-first 유지와 목표 palette 확정
- Typography, spacing, radius와 control size 확정
- 핵심 화면 6개의 Desktop/Mobile screenshot baseline
- 공통 breakpoint를 `600`, `900`, `1200` 중심으로 정리
- 접근성, overflow와 visual regression 체크리스트 작성

완료 조건:

- Token 이름과 값이 문서와 코드 초안에서 1:1로 대응한다.
- 신규 UI가 따라야 할 기본 예시 화면 하나를 승인한다.

### Phase 1. Token과 Primitive, 2~3주

- 정의되지 않은 CSS 변수 제거 또는 alias 처리
- Color, spacing, radius, type, elevation token 도입
- Button, IconButton, Field, Select, Tabs, Badge 구현
- Focus, disabled, loading, error 상태 통일
- inline style 신규 추가 금지 규칙 적용

완료 조건:

- 전역에서 정의되지 않은 Design Token 사용이 0건이다.
- 공통 색상의 literal 사용을 기존 대비 80% 이상 줄인다.
- Dark/Light에서 Primitive Story 화면이 모두 정상 표시된다.

### Phase 2. App Shell과 관리 화면, 2~4주

- Main Sidebar 정보 구조와 반응형 Drawer
- PageHeader, FilterBar, EmptyState 도입
- Home, Workflow, Template 우선 이전
- API Center와 운영 화면을 공통 List/Card/Table 패턴으로 이전

완료 조건:

- 일반 페이지의 Header 높이, padding과 Primary action 위치가 같다.
- 390px에서 Header text와 action이 겹치지 않는다.
- Loading, Empty, Error 상태가 모든 관리 화면에 존재한다.

### Phase 3. Editor Tool Shell, 2~3주

- Tool Header와 IconButton 통합
- Node Palette와 Panel token 적용
- 체크리스트와 AI Assistant를 비침해형 Drawer로 정리
- 모바일 Palette/Canvas/Inspector 전환 구조 도입

완료 조건:

- Desktop에서 Canvas 위를 상시 가리는 보조 UI가 없다.
- 모바일에서 노드 추가, 선택, 설정, 연결, 실행을 모두 완료할 수 있다.

### Phase 4. App Builder 재배치, 3~5주

- Editor와 동일한 Tool Header 적용
- Mode와 View control 정리
- Palette, Canvas, Inspector 크기와 상태 통일
- 모바일 단일 Pane과 Bottom Sheet Inspector 구현

완료 조건:

- 390px에서 Canvas가 독립 작업 영역으로 확보된다.
- Component 추가, Hierarchy 이동, 속성 편집, Preview와 Deploy가 Touch로 가능하다.
- Editor와 App Builder의 공통 Action이 같은 모양과 위치를 가진다.

### Phase 5. Landing, Light theme와 품질 게이트, 2~3주

- Intro와 제품 UI의 브랜드 연결 강화
- Light theme hard-coded dark surface 제거
- Keyboard, focus, contrast와 reduced motion 점검
- 주요 Viewport visual regression 자동화

완료 조건:

- Dark/Light 모두에서 핵심 화면의 내용과 상태가 식별된다.
- 390×844, 768×1024, 1440×900, 1920×1080에서 문서 전체 가로 overflow가 없다.
- Keyboard만으로 주요 제작·저장·실행 흐름을 완료한다.

## 10. 검증 지표

### 정량 기준

- 정의되지 않은 CSS variable: 0건
- 공통 의미 색상의 raw literal: 80% 이상 감소
- JSX inline style: 핵심 화면에서 70% 이상 감소
- 공통 Button·Field·Header 사용률: 대상 화면 90% 이상
- Mobile document horizontal overflow: 0건
- 주요 Interactive target: Touch 환경 최소 44px
- 기본 본문: 14px, 보조 정보 최소 11px
- Primary CTA: 한 화면 기본 1개

### 제품 지표

- 첫 Workflow 생성까지 걸린 시간
- Editor에서 노드 설정 완료 시간
- App Builder 모바일 과업 완료율
- UI 오조작과 되돌리기 비율
- 화면별 이탈률과 Empty State CTA 전환율
- 접근성 관련 사용자 신고와 Keyboard 과업 성공률

### Visual regression 화면

- Home: 초기, 생성 중, 답변, 오류
- Workflow: loading, empty, populated, mobile filter
- Editor: empty, node selected, running, failed, mobile Inspector
- App Builder: empty, component selected, mobile Canvas, deploy modal
- API Center: no credential, connected, expired, error
- Tutorial: track catalog, basic canvas, advanced lab
- Intro: Desktop/Mobile hero와 실제 영상

## 11. 피해야 할 방향

- 운영 도구 전체를 Gradient와 Glow로 장식하는 것
- 모든 Section을 떠 있는 Card로 만드는 것
- 기능 설명을 큰 Hero 영역으로 반복하는 것
- Desktop 3열 화면을 비율만 줄여 모바일에 유지하는 것
- 페이지별로 새로운 Button, Modal과 색 이름을 만드는 것
- Semantic color를 단순 장식이나 브랜드 색으로 사용하는 것
- Design system 구축을 이유로 기능 개발을 장기간 중단하는 것
- 현재 Editor의 익숙한 Canvas 조작과 노드 색 구분을 한 번에 교체하는 것

## 12. 권장 시작점

첫 구현 범위는 **Token + Workflow 목록 + App Builder Mobile Shell**이 적합하다.

1. `index.css`에 새 Semantic token과 기존 변수 alias를 정의한다.
2. Button, IconButton, Field, PageHeader 다섯 Primitive를 만든다.
3. Workflow 목록을 공통 PageHeader와 EmptyState로 이전해 관리 화면 기준을 만든다.
4. App Builder 모바일에서 한 Pane만 보이게 해 가장 큰 사용성 문제를 먼저 제거한다.
5. 같은 기준을 Editor와 나머지 운영 화면으로 확장한다.

이 순서는 눈에 보이는 개선을 빠르게 만들면서도 전체 재작성 위험을 피한다. 디자인 현대화의 성공 기준은 “더 화려해 보임”이 아니라 **사용자가 현재 위치, 다음 행동, 실행 상태를 더 빠르게 판단하고 같은 조작법을 모든 화면에서 재사용하는 것**이다.
