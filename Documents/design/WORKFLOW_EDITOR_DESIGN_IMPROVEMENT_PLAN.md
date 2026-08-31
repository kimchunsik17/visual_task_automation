# Workflow Editor 디자인 개선 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-08-28 |
| 상위 문서 | `DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md` §3.2(Workflow Editor 인상), §5, §6.2(제작 도구 Shell), Phase 3(Editor Tool Shell) |
| 자매 문서 | `APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md` — 같은 원칙·같은 토큰. 이 문서는 그 결과(범위 토큰, 섹션 Inspector, 선택 툴바)를 **에디터로 넓히고 두 도구가 한 토큰을 쓰게** 한다 |
| 대상 코드 | `pages/EditorPage.jsx`(3.8k 줄), `index.css`(에디터 규칙 ≈1,100줄), `Sidebar.jsx`(노드 팔레트), `customNodes.jsx`(노드 카드), `OnboardingChecklist.css` |
| 범위 밖 | 캔버스 조작(드래그·연결·단축키·명령 팔레트·컨텍스트 메뉴)의 **동작**. 이미 잘 정리돼 있고 감사 문서도 유지 대상으로 봤다. 노드 카드 **내부 폼**(`customNodes.jsx` 인라인 style 206곳)의 전면 정리 — 별도 단계(§6 E3) |

## 1. 왜 지금 하는가

App Builder 개편으로 두 제작 도구 사이의 차이가 오히려 더 보이게 됐다. 헤더는 이미 같은 클래스를
쓰지만, 그 아래는 다르다 — 에디터의 실행 패널은 인라인 style 120여 곳으로 그려진 6색 탭이고,
팔레트는 폭·밀도·아이콘 타일이 App Builder 와 다르며, 노드 팔레트 목록이 `Sidebar.jsx` 와
`editorNodeCatalog.js` 두 곳에 중복돼 있다(색이 다른 항목도 있다: `rssTriggerNode` 카테고리
`trigger` vs `input`).

또 감사에서 놓친 실제 결함이 하나 있다: `.react-flow__edge-path { stroke: … !important }` 가
인라인 style 을 이기므로, 실행 중(파랑)·성공(초록) 연결선 색이 **화면에 절대 나타나지 않는다**
(§2.5).

## 2. 현재 상태 감사 (코드 기준, 2026-08-28)

### 2.1 Tool Header — 대부분 맞다

`.editor-header` + `editor-icon-button` + `project-title-btn`(제목·공개범위·저장 상태) + 저장(dirty 점) +
AI 토글 + 목업 + **실행**(Primary) + 더보기 메뉴. App Builder 가 이 문법을 가져다 썼으니 헤더는
기준이다. 남은 것:

- `.btn-mock` 이 Amber 외곽선이다. Amber 는 "사용자 확인"에만(감사 §5.2). 목업은 보조 동작이므로
  중립 Secondary 로.
- 되돌리기/다시 실행이 더보기 메뉴 안에만 있다. App Builder 는 헤더에 아이콘으로 노출한다 —
  같은 동작은 같은 자리에.

### 2.2 노드 팔레트(`Sidebar.jsx`) — 목록 중복, 밀도

- 260px, 항목 `0.6rem 0.8rem` 패딩(≈40px), 카테고리 헤더가 인라인 style 의 `div`(버튼이 아니라
  키보드로 못 연다), 검색창 안쪽 아이콘 절대 위치.
- **노드 목록이 `editorNodeCatalog.js` 와 중복**(40여 항목 × 색·아이콘·카테고리). 하나를 고치면
  다른 하나가 어긋난다. 카탈로그가 이미 명령 팔레트·노드 피커·교체 후보의 단일 원본이다.
- 노드 아이콘 타일 `${color}20` 문자열 합성 — 8자리 hex 로 알파를 흉내낸다.

### 2.3 실행 패널 — 인라인 style 로 그린 6색 탭

`EditorPage.jsx` 3217~3790 줄. 패널 컨테이너·손잡이·탭 6개·닫기·각 탭 내용이 전부 인라인
style 이다(이 영역만 110곳). 탭마다 활성 색이 다르다: 결과 `#60a5fa`, 로그 `#a78bfa`, 평가
`#10b981`, 목업 `#f59e0b`, 검사 `#f59e0b`, 문제 `#ef4444`. 색이 탭의 **정체**를 표시하는 데
쓰여 의미 색(성공·위험) 규칙과 충돌한다 — "문제" 탭은 문제가 0개여도 빨갛다.

- 검사 탭: 노드 이름·id·상태 배지·버튼이 인라인, "이 노드부터 실행" 버튼이 Amber 채움.
- 로그 탭: `#1e1e1e` 배경 + `#00ff00` 글자 — 터미널 다크 유지는 맞지만 형광 초록은 가독성이
  낮고 토큰이 아니다. App Builder 로그(`--ab-log-*`)와 통일.
- 평가 탭: 점수 색이 `#10b981/#f59e0b/#ef4444` 삼항으로 흩어져 있다.
- 패널이 닫혔을 때 "실행 결과 보기" 알약 버튼이 화면 하단 중앙에 고정으로 뜬다 — 선택 툴바와
  같은 자리다(선택 시 겹침).

### 2.4 노드 카드(`customNodes.jsx` + `index.css`)

- 반경 16px(감사 §5.4 Card 8px, 노드는 캔버스 요소라 10~12px 가 적절), hover 시 `translateY(-2px)`
  (감사 §5.5: Layout 을 흔드는 hover transform 제거).
- 선택·실행·성공·오류 링이 hex(`#3b82f6`, `#10b981`, `#ef4444`)와 큰 glow(`0 0 15px`).
- 카테고리 색은 왼쪽 4px 막대 + 헤더 아이콘 색 — 유지한다(감사 §11).
- 접힌 노드 140px 정사각형 — 유지(캔버스 밀도의 핵심).
- 헤더 `1rem 1.25rem` 패딩, 삭제 ✕ 가 글자 — 아이콘 버튼 규격(28px)으로.

### 2.5 연결선 — 상태 색이 보이지 않는 결함

```css
.react-flow__edge-path { stroke: #94a3b8 !important; stroke-width: 2.5 !important; }
```

`EditorPage.jsx` 는 실행 중 `stroke: '#3b82f6'`, 성공 `'#10b981'` 을 엣지 **인라인 style** 로 준다.
CSS `!important` 는 인라인보다 우선하므로 이 색이 렌더되지 않는다. 선택 시 Amber(`#f59e0b`)만
`!important` 로 다시 이겨서 보인다. 고쳐야 할 결함이다 — 토큰 + `!important` 제거.

### 2.6 미니맵·배경

- MiniMap `nodeColor` 가 16개 `case` 하드코딩이고 카탈로그 색과 다르다(`promptNode` 초록 vs 카탈로그
  파랑). `getEditorNodeMeta(type).color` 하나로.
- Background 점 색이 `appTheme` 삼항 hex — 토큰으로.

### 2.7 온보딩 체크리스트

`position: fixed; top: 5.25rem; right: 1.25rem; z-index: 900` — 캔버스 우상단을 상시 가린다(감사
§3.2 지적). 접힘 상태가 있지만 펼친 상태로 시작한다.

### 2.8 모바일

≤1024px 에서 팔레트는 오프캔버스 + 우하단 FAB, 더보기 메뉴는 바텀시트, 선택 툴바·노드 피커도
바텀시트 — **이미 App Builder 보다 낫다.** Inspector 접근 경로(노드 검사)는 컨텍스트 메뉴에만
있다. 이번 범위에서는 실행 패널 탭이 6개라 가로로 넘치는 것만 정리한다.

### 2.9 유지해야 할 것

헤더 구성, dot grid 캔버스, 140px 접힌 노드, 카테고리 왼쪽 막대, 선택 툴바·컨텍스트 메뉴·명령
팔레트·노드 피커·단축키 도움말(이미 토큰 기반, 잘 만들어져 있다), 모바일 바텀시트 패턴.

## 3. 원칙

App Builder 계획 §3 의 7원칙을 그대로 쓴다. 추가로:

8. **두 도구는 한 토큰을 쓴다.** `--ab-*` 를 App Builder 전용으로 두지 않고 `styles/toolShell.css`
   의 `--ts-*` 로 올린다. App Builder 는 `--ab-x: var(--ts-x)` alias 한 줄로 갈아탄다.
9. **탭 색은 정체가 아니라 상태다.** 실행 패널 탭은 중립 + 활성 Blue. "문제" 탭은 문제 수 배지가
   빨갈 때만 빨갛다.
10. **단일 원본.** 노드 팔레트는 `EDITOR_NODE_CATALOG` 에서 그린다. MiniMap 색도 같은 곳.

## 4. 목표 구조

```text
┌ Tool Header (56px, 기존) ─────────────────────────────────────────────────────────┐
│ [←] [프로젝트 ▾ / 공개·저장됨]                   [↶][↷] [💾] [✦ AI] [⚗ 목업] [▶ 실행] [⋮] │
└───────────────────────────────────────────────────────────────────────────────────┘
┌ Palette 240 ─┐ ┌ Canvas ────────────────────────────────────────────────────────┐
│ 🔍 노드 검색  │ │                                                                │
│ ▾ 기본  3    │ │        (dot grid, 노드 카드 r12, 상태 링은 토큰)                 │
│  ▣ 시작      │ │                                                                │
│  ▣ 결과 출력 │ │                          ┌ 선택 툴바(기존) ┐                    │
│ ▸ 입력  9    │ │                          └─────────────────┘   [미니맵: 카탈로그 색] │
│ ▸ AI    3    │ │ [Controls]                                  [실행 결과 · 3 ▲] ← 우하단 알약 │
└──────────────┘ └────────────────────────────────────────────────────────────────┘
┌ 실행 패널 (열었을 때, 하단) ───────────────────────────────────────────────────────┐
│ ═ [결과][로그 ·12][평가][목업][검사][문제 ●2]                        [자동 열기][✕] │
│  (탭 내용 — 클래스 기반, 토큰 색)                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## 5. 세부 설계

### 5.1 공용 토큰 `styles/toolShell.css`

`.tool-shell { --ts-bg, --ts-surface-1/2/3, --ts-border, --ts-border-strong, --ts-text, --ts-text-muted,
--ts-accent, --ts-accent-soft, --ts-ai(-soft), --ts-success(-soft), --ts-warning(-soft), --ts-danger(-soft),
--ts-on-accent, --ts-log-bg/surface/text/muted/border, --ts-radius-control/panel/modal, --ts-field-h,
--ts-focus, --ts-motion }` + `[data-theme="light"] .tool-shell` 재정의 + `:focus-visible` 링 +
`prefers-reduced-motion`. App Builder 계획 §5.1 표의 값을 그대로 옮긴다.

- `EditorPage` 루트 `.app-container` 에 `tool-shell` 클래스를 붙인다. App Builder 의
  `.builder-layout` 도 `tool-shell` 을 붙이고 `--ab-*` 선언 블록은 alias 로 바꾼다.
- 에디터 고유 토큰(캔버스): `--ts-edge`(기본 연결선), `--ts-edge-hover`, `--ts-grid-dot`.

### 5.2 Tool Header

- 되돌리기/다시 실행 아이콘 버튼을 저장 버튼 왼쪽에 추가(≤720px 에서는 숨기고 더보기 메뉴 유지).
- `.btn-mock` → `.btn-secondary` 문법(중립 외곽선). 플라스크 아이콘 유지.
- 나머지는 그대로.

### 5.3 노드 팔레트

- `Sidebar.jsx` 의 자체 목록 삭제 → `EDITOR_NODE_CATALOG` + `NODE_CATEGORY_LABELS`. `memoNode`
  (kind `annotation`)는 '고급'에 그대로 노출(컨텍스트 메뉴에도 있지만 팔레트에서 끌어 놓을 수 있어야 한다).
- 폭 240px. 헤더 44px("노드" + 개수 배지 + 모바일 닫기). 검색 32px(App Builder `.palette-search` 와
  같은 모양). 카테고리 헤더는 `<button aria-expanded>` 32px, 이름 + 개수. 항목 36px, 26px 타일
  (`color-mix(in srgb, var(--node-color) 14%, transparent)` 배경 + 노드 색 아이콘). 검색 중에는
  카테고리 소제목 대신 항목 옆에 카테고리 캡션.
- 접힘 상태는 localStorage(`editor.palette.categories`)에 기억한다(지금은 새로 고치면 초기화).

### 5.4 노드 카드 (CSS)

- `.custom-node` 반경 12px, 그림자 `0 2px 8px`, hover transform 제거(그림자만), 선택 링
  `0 0 0 2px var(--ts-accent)`, 실행 중 `--ts-accent` pulse(유지), 성공 `--ts-success`, 오류 `--ts-danger`
  — glow 반경 15→8px.
- `.node-header` 44px 고정 높이(펼침 상태), 삭제 ✕ 를 28px 아이콘 버튼 규격으로. 접힌 140px 카드는 그대로.
- `.node-body` 필드: 32px 높이 input/select, 토큰 색.
- 카테고리 왼쪽 막대 유지. hex 는 `--node-color` 로 카드가 받는다(`style={{'--node-color': meta.color}}`
  는 노드 피커가 이미 쓰는 방식) — 이번에는 CSS 의 15개 `.custom-node.xxx` 규칙을 그대로 두고 값만 남긴다
  (E3 에서 카탈로그 색으로 통합).

### 5.5 연결선

```css
.react-flow__edge-path { stroke: var(--ts-edge); stroke-width: 2.5; opacity: .85; }   /* !important 제거 */
.react-flow__edge.selected .react-flow__edge-path { stroke: var(--ts-accent); stroke-width: 3.5; }
```

`EditorPage` 의 상태 색은 `var(--ts-accent)`(실행 중), `var(--ts-success)`(성공)로. 기본 stroke 는
inline 을 주지 않고 CSS 에 맡긴다(라이트 테마에서 연결선이 보이도록).

### 5.6 실행 패널

`EditorPage.jsx` 3217~3790 을 클래스 기반으로 다시 쓴다. 로직(탭 상태, 검사 대상 계산, 문제 검사 호출,
평가 결과 구조)은 그대로.

- `.editor-execution-panel`(fixed 하단, `--ts-surface-1`, 손잡이) / `.editor-execution-header`
  (44px) / `.editor-execution-tabs`(밑줄 탭, 중립 + 활성 `--ts-accent`, 가로 스크롤) / `.editor-execution-body`.
- 탭 배지: 로그 개수(중립), 문제 개수(0 이면 배지 없음, >0 이면 `--ts-danger`), 평가 점수(있으면).
- 탭 내용 클래스: `.exec-section`(패딩 16/24), `.exec-card`(테두리 카드), `.exec-kv`(라벨·값 2열),
  `.exec-pre`(결과 pre), `.exec-log`(로그: `--ts-log-*`, 명령줄 `>` 은 `--ts-accent`), `.exec-badge`
  (상태 배지: success/warning/danger), `.exec-score`(점수 원), `.exec-testcase`(평가 케이스 카드),
  `.exec-actions`(버튼 줄), `.exec-empty`(빈 상태 문구), `.exec-spinner`(로딩).
- 버튼: `.btn-secondary`(기존) / `.btn-run`(실행 계열 Primary — "이 노드부터 실행"은 Amber 채움이
  아니라 Secondary + Play 아이콘).
- "실행 결과 보기" 알약 → 우하단(`right: 16px; bottom: 16px`, MiniMap 위쪽으로 살짝 띄움 — MiniMap 은
  `bottom: 15px` 기본이라 알약은 `bottom: 168px`) 또는 미니맵이 없는 모바일에서는 하단 중앙. 선택 툴바와 겹치지 않게 한다.
- 사용자 승인 모달(3749~)도 `.editor-approval-*` 클래스로.

### 5.7 미니맵·배경

- `nodeColor={(node) => getEditorNodeMeta(node.type).color}`, `maskColor` 는 토큰.
- `<Background color="var(--ts-grid-dot)">`(xyflow 는 CSS 변수를 그대로 받는다 — App Builder 에서 확인).

### 5.8 온보딩 체크리스트

- 접힌 상태로 시작(첫 방문에만 펼침 — 이미 localStorage 진행도가 있으니 "완료 0개 & 처음"일 때만).
- 위치는 유지(우상단은 컨트롤·미니맵과 겹치지 않는 유일한 코너)하되 접힌 폭 220px, 헤더 44px.

### 5.9 접근성·모션

- `.tool-shell` 공용 포커스 링. 카테고리 헤더·탭에 `aria-expanded`/`role="tablist"`.
- hover transform 제거(노드, `.btn-run`, `.btn-mock`).

## 6. 단계

| 단계 | 내용 | 규모 | 이번 구현 |
| --- | --- | --- | --- |
| **E1. 토큰 공유 + 실행 패널 + 연결선 결함** | §5.1 `toolShell.css`, App Builder alias, §5.5 엣지 `!important` 제거·토큰, §5.6 실행 패널 클래스화(6탭 → 중립 탭 + 배지), 승인 모달, 알약 위치, §5.7 미니맵·배경 | L | **예** |
| **E2. 팔레트·헤더·노드 카드 CSS** | §5.3 팔레트를 카탈로그로, §5.2 되돌리기 노출·목업 중립화, §5.4 카드 CSS, §5.8 체크리스트 | M | **예** |
| E3. 노드 카드 내부 폼 정리 | `customNodes.jsx` 인라인 206곳 → `.node-field` 클래스, 카테고리 색 15규칙 → `--node-color`, 토큰 사용량 배지 통일 | L | 아니오 — 노드 40종 회귀 위험이 커서 별도 작업 |
| E4. Node Inspector 도입 | 노드 설정을 카드 안이 아니라 우측 Inspector 에서(감사 §8 2차). 카드는 요약만 | XL | 아니오 — 정보 구조 변경, PRD 결정 필요 |
| E5. 공통 Primitive 추출 | ToolHeader / IconButton / Segmented / InspectorSection / LogView 를 `components/` 로, App Builder `.ab-*` 와 에디터 `.exec-*` 를 통합 | M | 아니오 — App Builder D 단계와 함께 |

## 7. 완료 조건과 검증

정량

- `EditorPage.jsx` 인라인 `style={{ }}` 122 → 15 이하(위치·높이 동적 값만).
- `EditorPage.jsx` hex 71 → 5 이하. `Sidebar.jsx` 노드 목록 0줄(카탈로그 참조).
- 실행 패널 탭 활성 색 6종 → 1종(`--ts-accent`).
- `index.css` `.react-flow__edge-path` 에 `!important` 없음.
- `vite build` 성공, `node --test` 통과, ESLint 오류 0.

정성(수동, 다크/라이트)

- 워크플로우를 실행하면 **실행 중 연결선이 파랗게, 성공한 연결선이 초록으로 보인다**(현재는 안 보임).
- 실행 패널 탭이 같은 색이고 "문제" 배지만 문제가 있을 때 빨갛다.
- 팔레트에 카탈로그의 모든 노드(레지스트리 노드 포함)가 카테고리별로 보이고 검색된다.
- 노드 카드가 hover 로 움직이지 않고, 선택 링이 Blue 하나다.
- 720px 에서 실행 패널 탭이 가로 스크롤되고 닫기 버튼은 제자리에 있다.

## 8. 피할 것

- 노드 카드의 카테고리 색을 이번에 바꾸는 것(감사 §11) — 반경·링·그림자만.
- `customNodes.jsx` 를 이번에 건드리는 것 — E3 로 분리. CSS 로 도달 가능한 것만.
- 실행 패널의 탭 구조·로직(검사 대상 계산, 문제 검사 API, 평가 리포트 구조)을 바꾸는 것 — 표현만.
- 새로운 버튼/필드 클래스 이름을 만드는 것 — 기존 `btn-run`/`btn-secondary`/`editor-icon-button`/
  `editor-field-input` 을 쓰고, 패널 내부 전용은 `exec-*` 접두 하나로 제한.

## 9. 구현 진행 상황 (2026-08-28)

E1 과 E2 를 구현했다. 대상: `styles/toolShell.css`(신설), `pages/EditorPage.css`(신설), `pages/EditorPage.jsx`,
`Sidebar.jsx`(재작성), `index.css`(노드 카드·연결선·버튼·팔레트 폭), `pages/AppBuilderPage.css`(alias).

### 구현한 것

- **공용 토큰**(§5.1): `.tool-shell { --ts-* }` + 라이트 재정의 + 포커스 링 + reduced-motion. 에디터 루트
  `.app-container` 와 App Builder 루트 `.builder-layout` 에 `tool-shell` 을 붙였다. App Builder 의 `--ab-*`
  선언 블록은 `var(--ts-*)` alias 로 바뀌었다 — 두 도구가 한 토큰을 쓴다.
- **연결선 결함 수정**(§5.5): `.react-flow__edge-path` 의 `!important` 제거, 색을 `--ts-edge`/`--ts-accent` 로.
  실행 중(파랑)·성공(초록) 연결선이 이제 렌더된다. 새 엣지의 기본 stroke 인라인도 없애 라이트 테마에서
  CSS 색이 적용된다.
- **실행 패널**(§5.6): 인라인 style 110곳 → `.editor-execution-*` / `.exec-*` 클래스. 탭 6개는 중립색 +
  활성 Blue, 상태는 배지(로그 수 · 문제 수(0이면 ✓) · 평가 점수)로. "이 노드부터 실행"은 Amber 채움 →
  Secondary + Play. 로그 형광 초록 → `--ts-log-*`. 승인 모달은 `.editor-approval-*`(승인 = `btn-run`,
  거절 = `btn-secondary danger`). 닫힘 알약은 우하단(미니맵 위)으로 이동, 로그 수 배지.
- **미니맵·배경**(§5.7): `nodeColor` 16개 `case` → `getEditorNodeMeta(type).color`, 마스크·배경·점 색 토큰.
- **팔레트**(§5.3): `Sidebar.jsx` 자체 목록 삭제 → `EDITOR_NODE_CATALOG`. 240px, 44px 헤더(개수 배지),
  32px 검색(지우기 버튼), 카테고리 헤더는 `button[aria-expanded]` + 개수, 36px 항목 + 26px 타일
  (`color-mix` 로 노드 색 14%), 검색 중 카테고리 캡션, 접힘 상태 localStorage 기억.
- **헤더**(§5.2): 되돌리기/다시 실행 아이콘을 저장 왼쪽에 노출(≤720px 숨김, 더보기 메뉴에도 유지).
  `.btn-mock` 중립 Secondary. `.btn-run`/`.btn-mock` hover transform 제거.
- **노드 카드 CSS**(§5.4): 반경 16→12, hover transform 제거, 선택 링 `--ts-accent` 2px, 실행/성공/오류
  링 토큰 + glow 축소, 실행 중 배지 토큰, 헤더 44px, 삭제 ✕ 24px 아이콘 버튼(hover 시 danger),
  AI 하이라이트 초록→AI Violet. 카테고리 왼쪽 막대와 140px 접힌 카드는 그대로.

### 정량 결과

| 지표 | 이전 | 이후 |
| --- | --- | --- |
| `EditorPage.jsx` 인라인 `style={{ }}` | 122 | 5 (팝오버·컨텍스트 메뉴 좌표 ×2, 패널 높이, `--node-color` ×2) |
| `EditorPage.jsx` hex | 71 | 1 (분리 핸들 연결선 `#ec4899` — 노드 색, E3 범위) |
| 실행 패널 탭 활성 색 | 6종 | 1종 |
| `Sidebar.jsx` 하드코딩 노드 목록 | 40여 줄 | 0 |
| `.react-flow__edge-path` `!important` | 6 | 0 |
| `EditorPage.css` hex | — | 0 |
| 빌드 / 테스트 / ESLint 오류 | — | 통과 / 38/38 / 0 |

### 검증하지 못한 것

브라우저 시각 확인은 못 했다. 다음 실행 때 볼 것: 워크플로우 실행 시 연결선이 파랑→초록으로 바뀌는지(이번에
고친 결함), 실행 패널 탭 배지, 라이트 테마의 미니맵·팔레트, 노드 카드 선택 링, 720px 에서 탭 가로 스크롤.

### 다음

- E3: `customNodes.jsx` 인라인 206곳 → `.node-field` 클래스, 15개 `.custom-node.xxx` 색 규칙 → `--node-color`.
- E4: Node Inspector(우측 패널) — PRD 결정 필요.
- E5: App Builder `.ab-*` 와 에디터 `.exec-*` 의 공통 Primitive 추출.
