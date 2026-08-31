# 빈 상태 일러스트 3종 — SVG 제작 · 적용 기록

> 대상: [icon-generation-prompts.md](icon-generation-prompts.md) §2 Tier 6 의
> `empty-workflows` / `empty-apps` / `empty-templates`
> 적용 기준: [DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md](../../design/DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md)
> §3.2 · §7.2 EmptyState · §8 "Empty State 축소"

---

## 1. PNG 가 아니라 SVG 로 만든 이유

[icon-generation-prompts.md](icon-generation-prompts.md) §0 표와 §4-3 은 이 3종을
**"PNG (이미지 생성 모델)"** 로 분류해 두었다. 그런데 §4-3 프롬프트 본문이 요구하는 것은

> *minimal flat vector illustration … monochrome slate line art (#334155 strokes) …
> **2px uniform stroke weight** … transparent background, no text, no characters,
> no background fill*

로, **그라데이션·질감·회화적 표현이 하나도 없는 완전한 벡터 명세**다.
§0 이 PNG 를 고른 근거("그라데이션·질감·회화적 표현이 필요. 벡터로는 비효율")가
이 3종에는 애초에 해당하지 않는다. 그래서 SVG 로 만들었다. 실측 근거:

| 항목 | PNG (800×600 @2x) 예상 | 실제 SVG | 비고 |
|---|---|---|---|
| 파일 크기 | 3종 합계 약 150KB | **3종 합계 2.9KB** | 약 1/50 |
| 다크/라이트 대응 | 라이트/다크용 2벌을 따로 굽거나, 한쪽에서 안 보임 | **자동** | 본체가 `currentColor` |
| 해상도 | 2x 고정. 4K·200% 확대에서 뭉개짐 | **무한** | |
| 색 토큰 연동 | 불가 | `color: var(--text-muted)` 상속 | |
| 수정 비용 | 재생성 | 좌표 한 줄 | |

특히 **다크/라이트 자동 대응**이 결정적이다. 이 앱은 `[data-theme="light"]` 로
`--text-muted` 가 `#94a3b8` ↔ `#64748b` 로 바뀐다. §4-3 이 지정한 `#334155` 를
PNG 에 구워버리면 다크 배경(`#0f172a`)에서 대비가 거의 사라진다.
같은 문제가 §4-1 에 이미 적혀 있다 — *"현재 logo.png는 흰색 단색이라 라이트 테마에서 보이지 않는다."*
그 실수를 빈 상태에서 반복하지 않으려면 SVG 여야 한다.

액센트(blue/violet/emerald)만 HEX 로 고정했다. 이 3색은 두 테마 모두에서
대비가 확보되고, 브랜드 색이라 테마를 따라 변하면 안 된다.

> §0 표와 §2 Tier 6 표의 `.png` 표기는 그대로 두었다 (해당 문서는 수정 금지).
> 실제 산출물은 `.svg` 다.

---

## 2. 3종 공통 사양

| 항목 | 값 | 근거 |
|---|---|---|
| viewBox | `0 0 320 240` (4:3) | UI 아이콘의 24 그리드와 분리. §4-3 의 800×600 과 같은 비율 |
| 기본 표시 폭 | 180px (데스크톱) / 132px (≤640px) | 아래 §4 참조 |
| stroke-width | **3.2** | 200px 표시 기준 역산: `2 ÷ (200/320) = 3.2`. 3종 동일 |
| linecap / linejoin | `round` | 아이콘 세트와 동일 |
| 본체 색 | `stroke="currentColor"` | 부모 CSS `color` 상속 → 테마 자동 대응 |
| 액센트 | HEX 고정 | blue `#3b82f6` / violet `#8b5cf6` / emerald `#10b981` |
| 점선 | `stroke-dasharray="9 10"` | "아직 없음"의 시각 언어. 실선 본체와 확실히 구분 |
| 텍스트·사람·배경 채움 | 없음 | §4-3 제약 |

### 계조(opacity) 규칙 — 3종 공통

| 역할 | opacity | 예 |
|---|---|---|
| 주 피사체 (점선 윤곽) | 0.75 | 캔버스 위 placeholder 노드 / 스마트폰 프레임 / 앞 카드 |
| 보조 구조 (실선) | 0.5~0.55 | 캔버스 프레임 / 스피커·홈 인디케이터 / 뒤 카드 |
| **유령 요소** | **0.4** | UI 블록 3개 / 콘텐츠 줄 2개 |
| 유령 연결 곡선 | 0.45 → 0 | `linearGradient` + `stop-color="currentColor"` 페이드 |
| 점 그리드 | 0.26 | |
| 액센트 | 1.0 | |

`stroke-dasharray="9 10"` 을 고른 이유: `linecap="round"` 라 각 대시 양끝에 반경 1.6 이
붙는다. 대시 9 → 실제 12.2, 간격 10 → 실제 6.8. 132px 표시(스케일 0.4125)에서도
간격이 2.8px 남아 **뭉개지지 않는다**. 초안의 `10 8` 은 간격이 4.8 → 2.0px 로
132px 에서 실선처럼 보였다.

### 개별 모티프

**`empty-workflows.svg`** (1.4KB) — §4-3 모티프 그대로
- 캔버스 프레임 `rect 32,40 256×160 r14` (실선 0.55)
- 점 그리드 32 간격 · 노드가 덮는 8개는 생략 (채움이 없어 노드 안으로 비쳐 보이므로)
- 중앙 점선 placeholder 노드 `112,96 96×48 r10`, 안에 **blue `+`**
- 유령 연결 곡선 2개 — 노드 좌/우 변에서 수평으로 출발해 캔버스 가장자리로 흐려지며 소멸

**`empty-apps.svg`** (0.9KB)
- 점선 스마트폰 프레임 `70,26 124×188 r20`
- 내부 유령 UI 블록 3개 (0.4)
- 스피커 / 홈 인디케이터 실선 (0.5)
- 우하단 모서리에 기댄 마법봉(축 + 그립 밴드) + **violet 반짝임 2개** (4각 별, r10 / r6)

**`empty-templates.svg`** (0.6KB)
- 앞 카드 `110,78 100×132 r12` (점선 0.75) + 유령 콘텐츠 줄 2개
- 뒤 카드 2장을 ∓11° 부채꼴로. **닫힌 rect 가 아니라 "보이는 부분만" 그린 열린 path** — 아래 §5 참조
- 위쪽에 **emerald 다운로드 화살표**

---

## 3. 로더를 아이콘과 분리한 이유

[frontend/src/illustrations/index.jsx](../../../frontend/src/illustrations/index.jsx) 를 새로 만들었다.
[icons/index.jsx](../../../frontend/src/icons/index.jsx) 를 재사용하지 않은 이유:

1. 아이콘 로더는 `<svg>` 래퍼에 **`viewBox="0 0 24 24"` 와 `stroke-width="2"` 를 하드코딩**한다.
   4:3 / 3.2 인 일러스트는 그 래퍼에 담기지 않는다.
2. 아이콘은 `size` 로 정사각 px 고정, 일러스트는 `width:100%` + `max-width` 반응형이다.
   props 시그니처가 다르다.
3. glob 경로가 `assets/icons/**` 밖이라 `build-icon-qa.py` 의 24-그리드 검사 대상과 섞이지 않는다.

구조는 아이콘 로더와 동일하다 — `import.meta.glob(..., '?raw', eager)` 로 빌드 타임 인라인,
`assets/illustrations/` 에 `.svg` 를 추가하면 자동 등록. 새 의존성 없음.
파일의 `viewBox` 는 하드코딩하지 않고 소스에서 읽는다.

```jsx
import { Illustration } from '../illustrations';
<Illustration name="empty-workflows" width={180} />
```

세트 공통 획 굵기는 `ILLUSTRATION_STROKE = 3.2` 한 곳에서만 정한다.
3종이 서로 다른 굵기로 보이는 사고가 구조적으로 불가능하다.

---

## 4. 공통 EmptyState 컴포넌트

[frontend/src/components/EmptyState.jsx](../../../frontend/src/components/EmptyState.jsx) +
[EmptyState.css](../../../frontend/src/components/EmptyState.css)

§7.2 표의 `EmptyState | icon, title, description, one primary action` 를 그대로 구현했다.

```jsx
<EmptyState
  illustration="empty-workflows"
  title="아직 저장된 워크플로우가 없습니다"
  description="빈 캔버스에 노드를 놓고 연결하면 첫 자동화가 만들어집니다."
  action={<button className="btn-primary" onClick={...}>…</button>}
/>
```

**§3.2 가 지적한 구조를 실제로 걷어냈다.** 기존 3곳 모두

```
큰 dashed Card ( padding 3rem 2rem, border-radius 16px, border 1px dashed )
  └ lucide 아이콘 40px @ opacity .4
  └ 문장
  └ 버튼
```

였다. 여기서 **Card 배경/테두리를 제거**했다 — 일러스트 자체가 점선이라
dashed 카드를 한 겹 더 두르면 "아직 없음" 기호가 중복된다.
세로도 줄였다: padding `3rem 2rem` → `1rem 1rem 1.75rem` (모바일 `0.5rem .75rem 1.25rem`).

`action` 은 **버튼을 그대로 받는다.** 컴포넌트가 `onClick` 을 만들지 않는다 —
기존 핸들러를 손대지 않기 위한 의도적 설계다.

클래스 접두어는 `.wf-empty` 다. `.empty-state` 는 SchedulerPage / BotManagerPage /
EvaluationPage / ProjectRunsPage / TemplateModal CSS 가 이미 쓰고 있어 충돌한다.

---

## 5. 렌더 검증에서 발견해 고친 문제 (전부 실제 렌더로 확인)

검증 결과물: `/tmp/…/scratchpad/empty-states/` (다크 `#0f172a` · 라이트 `#f1f5f9`, 160/200/240px 대조표 +
실제 화면 데스크톱 1280px · 모바일 390px × 2테마)

| # | 문제 | 발견 방법 | 조치 |
|---|---|---|---|
| 1 | **`empty-templates` 가 엉킨 덩어리로 보임** — 뒤 카드를 닫힌 `rect` 로 그렸더니 채움이 없어 **앞 카드 속으로 뒷카드의 안쪽 변이 그대로 비쳐** 부채꼴이 아니라 다각형 blob 이 됨 | 1차 대조표 렌더 | 뒤 카드를 "보이는 부분만" 그리는 **열린 path** 로 교체. 회전 좌표계에서 앞 카드 윤곽과 만나는 지점을 역산해 그 점에서 끊음 |
| 2 | 1 수정 후에도 **앞 카드 안쪽에 짧은 대시 꼬다리 2개**가 남음 — 끊는 지점을 앞 카드 안쪽(x=122/198)으로 잡아서 | 2차 렌더 240px | 끊는 지점을 앞 카드 **윤곽선 위**(x=110/210)로 재계산. 획 폭 3.2 가 캡을 덮어 완전히 사라짐 |
| 3 | 점선이 160px 에서 실선처럼 뭉개짐 | 대조표 160px | `dasharray 10 8` → `9 10` |
| 4 | **모바일에서 일러스트가 안 줄어듦** (390px 화면의 51% 차지) | 390px 실제 렌더 | 원인: `<svg>` 에 인라인 `max-width` 를 줘서 **인라인 스타일이 미디어 쿼리를 이김**. `max-width` 소유권을 래퍼 `div` 로 옮기고 `--wf-empty-art` 커스텀 프로퍼티로 전달 |
| 5 | 설명 문구가 `빈 캔버스에 … 만들어집니 / 다.` 로 끊김 | 데스크톱 실제 렌더 | `max-width: 42ch` 가 원인 — `ch` 는 라틴 글자폭 기준이라 한글에서 어긋난다. `30rem` + **`word-break: keep-all`** 로 교체 |
| 6 | `empty-apps` 의 시각 무게가 왼쪽으로 쏠림 (폰 중심이 캔버스 중심에서 -44) | 실제 화면 렌더 | 폰을 오른쪽으로, 마법봉을 더 세워서 -29 로 완화. bbox 중심은 160 유지 |
| 7 | `empty-workflows` 프레임이 나머지 2종보다 커 보임 | 대조표 3종 비교 | 프레임 280×172 → **256×160**, 점 그리드 재배치 |
| 8 | 라이트 테마에서 점 그리드가 거의 안 보임 | 라이트 대조표 | opacity 0.22 → **0.26** |

### 최종 확인 항목 (모두 통과)

- [x] 3종의 획 굵기가 같아 보인다 — 전부 viewBox 320 / stroke 3.2, 로더가 한 곳에서 부여
- [x] 점선이 뭉개지지 않는다 — 132 / 160 / 200 / 240px 전부
- [x] 유령 요소(opacity 0.4)가 **라이트에서도** 보인다
- [x] 세 그림의 시각 무게가 비슷하다 — bbox 각각 256×160 / 182×188 / 204×180
- [x] 390px 에서 가로 스크롤 없음 (`scrollWidth - clientWidth == 0` 실측)
- [x] `npx vite build` 통과

---

## 6. 적용한 화면

세 파일 모두 수정 전 `git status --short` 로 **미커밋 변경이 없음을 확인**했다.

| 화면 | 파일 | 상태 | 내용 |
|---|---|---|---|
| 내 워크플로우 | [pages/WorkflowsPage.jsx](../../../frontend/src/pages/WorkflowsPage.jsx) | ✅ | `filteredProjects.length === 0` → `empty-workflows`. **버튼 `onClick={() => navigate('/editor')}` 그대로** |
| 커뮤니티 템플릿 (전체 비어 있음) | [pages/TemplatesPage.jsx](../../../frontend/src/pages/TemplatesPage.jsx) | ✅ | `projects.length === 0` → `empty-templates`. 기존엔 Primary action 이 아예 없었다 — §7.2 의 "one primary action"에 맞춰 `navigate('/workflows')` 1개 추가 (기존 라우트) |
| 커뮤니티 템플릿 (검색 결과 없음) | 〃 | ✅ | `filtered.length === 0` → **일러스트 없는** EmptyState. 일러스트는 "처음부터 비어 있음"의 기호이지 "필터로 걸러짐"이 아니다 |
| 내 커스텀 앱 | [pages/CustomAppsDashboardPage.jsx](../../../frontend/src/pages/CustomAppsDashboardPage.jsx) | ✅ | 원래 빈 상태가 **없었다** — 앱이 0개여도 "새 앱 만들기" 카드 1장만 덩그러니 놓였다. `!loading && apps.length === 0` 분기를 추가하고 `empty-apps` 적용. Primary action 의 `onClick` 은 기존 카드와 **동일한** `navigate('/app-builder')` |

동작 변경 없음. 버튼 핸들러·API 호출·조건 분기의 의미는 그대로다.
`filteredProjects.length === 0` / `projects.length === 0` / `filtered.length === 0` 조건식은
한 글자도 건드리지 않았다.

## 7. 적용 보류 대상

아래는 빈 상태가 존재하지만 **해당 파일에 미커밋 변경이 있어 수정하지 않았다.**
자산과 `EmptyState` 컴포넌트는 준비돼 있으므로, 그 변경이 커밋된 뒤 같은 방식으로 적용하면 된다.

| 화면 | 파일 | 현재 빈 상태 | 권장 |
|---|---|---|---|
| 저장된 템플릿 목록 | `TemplateModal.jsx:629` | `.empty-state` + "저장된 템플릿이 없습니다." | `empty-templates` |
| 스케줄 관리 | `pages/SchedulerPage.jsx:126` | `Calendar 48px` + "등록된 스케줄이 없습니다" | 전용 일러스트 필요 (3종 밖) |
| 웹훅 관리 | `pages/WebhookManagerPage.jsx:152` | `nav-webhooks 48px` | 전용 일러스트 필요 |
| 봇 관리 | `pages/BotManagerPage.jsx:172` | `Bot 48px` | 전용 일러스트 필요 |
| 통계 | `pages/StatisticsPage.jsx:250` | `.statistics-empty-state` | 전용 일러스트 필요 |
| 평가 / 실행 기록 | `pages/EvaluationPage.jsx:208`, `pages/ProjectRunsPage.jsx:160·191` | 한 줄 텍스트 | 일러스트 없는 `EmptyState` 로 통일 |
| App Builder 로그 | `pages/AppBuilderPage.jsx:1601` | 한 줄 텍스트 | 인라인 상태 — EmptyState 대상 아님 |

`SchedulerPage` / `BotManagerPage` 는 파일 자체는 깨끗하지만
`.empty-state` CSS 가 각 페이지 CSS 에 있고 3종 모티프와 맞는 그림이 없어 이번 범위에서 제외했다.

## 8. 이번 범위 밖 (기존 문제, 손대지 않음)

390px 에서 `.section-header` 의 메뉴 버튼 · 제목 · 체크박스 · "새 빈 프로젝트" 버튼이
같은 행에서 겹친다. 이는 §3.2 가 별도로 지적한 항목이고
(*"390px 화면에서 메뉴 버튼, 제목, 옵션, 새 프로젝트 버튼이 같은 행에 겹친다"*),
공통 `PageHeader` 도입(§7.2)으로 풀 문제다. 빈 상태 블록과는 무관하다.

---

## 9. 변경/추가 파일

**추가**
```
frontend/src/assets/illustrations/empty-workflows.svg     1.4KB
frontend/src/assets/illustrations/empty-apps.svg          0.9KB
frontend/src/assets/illustrations/empty-templates.svg     0.6KB
frontend/src/illustrations/index.jsx                      일러스트 로더
frontend/src/components/EmptyState.jsx                    공통 빈 상태 블록
frontend/src/components/EmptyState.css
Documents/icon-empty-states.md                            이 문서
```

**수정** (3개 파일, +41 / −21)
```
frontend/src/pages/WorkflowsPage.jsx
frontend/src/pages/TemplatesPage.jsx
frontend/src/pages/CustomAppsDashboardPage.jsx
```

새 의존성 없음. 커밋하지 않았다.
