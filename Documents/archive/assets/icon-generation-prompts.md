# 아이콘 신규 생성 — 리스트 & 프롬프트

> 대상 코드베이스: `frontend/src` (React + Vite, lucide-react 0.300)
> 작성일: 2026-08-27 · 최종 갱신: 2026-08-27
> 관련: [DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md](../../design/DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md)
> 61행 "아이콘 — Lucide 중심, 일부 emoji·텍스트 기호 / 혼용 제거 필요" 항목의 실행 문서다.

---

## 진행 상황 (여기서 이어서 시작)

**완료: B1 ~ B9 + TemplateModal + Tier 6 — 커스텀 SVG 79개 + 브랜드/일러스트 자산, 전부 적용·검증됨.**
(B7·B8, B9·TemplateModal, Tier6브랜드·빈상태 를 각각 병렬 에이전트 2개로 동시 진행, 2026-08-27)

| 지표 | 작업 전 | 현재 |
|---|---|---|
| 워크플로우 노드 커스텀 아이콘 | 0 / 37 | **37 / 37 (100%)** |
| 사이드바 내비 커스텀 아이콘 | 0 / 14 | **14 / 14 (100%)** |
| API 센터 프로바이더 (이모지 대체) | 0 / 8 | **9 / 9 (toss 신규 포함)** |
| 앱 빌더 팔레트 커스텀 아이콘 | 0 / 14 | **14 / 14** (캔버스 `logicNodes.jsx` 포함) |
| 실행 상태 아이콘 (색맹 대응) | 0 / 5 | **5 / 5** |
| 템플릿 카드 이모지 | 22개 | **0개** (기존 아이콘 재사용, 신규 제작 0) |
| 앱 전체 lucide 아이콘 종류 | 132 | **89** |
| 아이콘 충돌 (의미가 다른 기능이 같은 아이콘) | 9종 | **1종 경미** (`Box` — ChatSidebar·TutorialSandbox, AppBuilder 밖 잔존) |
| 커스텀 SVG 총량 | — | 79개 / **23.2KB** |
| 로고 라이트 테마 가시성 | **측정 불가**(배경과 차이나는 픽셀 0개) | **3.36:1 이상** (WCAG 하한 3:1 통과) |
| 파비콘 · OG 이미지 | 없음 | **있음** (`frontend/public/` 4개 — 구 WA 로고 합성, 16·32·180px + OG) |
| 로드되는 폰트 패밀리 | 5종 (한글 폰트 0) | **1종** (Pretendard Variable) |
| 빈 상태 일러스트 | 텍스트만 | **3종 SVG** (2.9KB, `currentColor` 테마 대응) |

### 다음에 할 일 (우선순위)

**Tier 1~6 전부 완료.** 폰트도 Pretendard 로 통일 완료.

> ⚠️ **로고는 기존 `logo.png`(WA 워드마크)를 유지한다 — 2026-08-27 사용자 결정.**
> 이미 홍보용 자료에 적용돼 있어 형태를 바꿀 수 없다. Tier 6 에서 만든 새 로고 SVG 는
> `frontend/src/assets/brand/` 에 **보관만** 하고 앱에서는 쓰지 않는다(삭제하지 말 것).
> 대신 구 로고의 결함 하나를 고쳤다: W 첫 획 카운터 안에 있던 **반투명 회색 사각형 얼룩**
> (x121~143, y236~259, 552픽셀)을 제거했다. 획 색은 `(240,240,240)`, 얼룩은 `(224,224,224)` 로
> 색이 달라 획 침범 없이 지울 수 있었다. 원본 백업은 세션 스크래치패드의 `logo.png.orig`.
>
> **미해결 1:** 구 로고는 흰색 단색이라 **라이트 테마에서 여전히 보이지 않는다**(대비 측정 시
> 배경과 다른 픽셀 0개). 워드마크 텍스트는 `var(--text-color)` 로 고쳐서 정상이다.
> 형태를 유지하면서 해결하려면 라이트 테마에서만 CSS 필터로 반전시키는 방법이 있으나,
> 브랜드 색이 두 개가 되는 문제라 사용자 결정이 필요하다.
>
> **미해결 2 — `logo.png` 자체가 우측에서 잘려 있다.** alpha bbox 가 `(3, 5, 568, 313)` 로
> 이미지 폭(568)에 닿아 있고, 마지막 3열에 각각 53·48·45 픽셀의 잉크가 있다. **A 의 오른쪽 획이
> 캔버스 경계에서 수직으로 절단된 상태다.** 원본 백업(`logo.png.orig`)도 동일하므로 얼룩 제거와
> 무관한 기존 결함이다. 32px 파비콘·45px 사이드바에서는 보이지 않지만 OG(320px)에서는 드러난다.
> 마스터 파일에서 우측 여백을 살려 재추출한 뒤 `icon-tier6-brand.md` 의 재생성 스니펫을 다시
> 돌리면 4개 자산이 한 번에 고쳐진다.

| 순위 | 배치 | 내용 | 가치 |
|---|---|---|---|
| 1 | — | **라이트 테마 로고 가시성** | 위 상자 참고. 사용자 결정 대기 |
| 2 | — | **`og:image` 절대 URL** | 배포 도메인 확정 시 `/og-image-1200x630.png` → 절대 URL. Twitter/X 등은 상대경로를 못 읽는다. index.html에 주석 표시됨 |
| 3 | — | `logo-lockup.svg` | 구 로고 유지 결정으로 **불필요해졌다.** 현재 `<img>` + `<span>` CSS 폰트(Pretendard) 구조로 충분 |
| 4 | — | 상태 아이콘 후속 표면 | `CustomAlert.jsx`(1순위), `AppBuilderPage.jsx:1626`(배포 완료), `AdvancedTutorialLab.jsx`(경고 2곳) |
| 5 | — | 빈 상태 미적용 화면 | `SchedulerPage` · `BotManagerPage`(둘 다 깨끗하나 새 모티프 필요), 그리고 미커밋 변경 파일 6개. `icon-empty-states.md` 참고 |
| 6 | — | 이모지 잔존 6파일 | `DeployModal.jsx` · `customNodes.jsx` · `MainPage.jsx` · `SettingsPage.jsx` · `EditorPage.jsx` · `ProjectRunsPage.jsx` — **전부 미커밋 변경 파일** |
| 7 | — | 신규 제작 후보 2개 | 범용 "도구(Tool)" · "쇼핑/스토어" 모티프 — TemplateModal 매핑에서 유일하게 부적합했던 2건 |
| 8 | — | `Box` 잔여 2곳 (ChatSidebar · TutorialSandbox) | 의미가 서로 달라 경미 |

### 폰트 — ✅ Pretendard 로 통일 완료 (2026-08-27)

**교체 전 문제:** 한글 웹폰트를 아예 로드하지 않았다. `index.html`(Inter·Outfit·Poppins)과
`index.css`(Inter·Jua·Quicksand)가 각각 Google Fonts를 불렀는데 전부 라틴 전용이고,
CSS의 `'Noto Sans KR'` 는 로드되지 않아 **한글이 사용자 OS 기본 폰트로 렌더됐다**
(Windows 맑은 고딕 / macOS Apple SD Gothic Neo / Android 본고딕). `Outfit` 은 참조 0회 죽은 로드.
5종 비교 렌더는 `Documents/font-compare.png` — 구 설정만 같은 문구가 2줄로 넘쳤다.

**적용 내용:**
- `index.html` 의 Google Fonts link → **Pretendard variable dynamic-subset CDN** 하나로
  (`@v1.3.9`, `preconnect` 추가). Pretendard 는 Inter 기반에 한글을 붙인 글꼴이라 기존 라틴 인상이 유지된다
- `index.css` 의 `@import` 제거(렌더 블로킹 체인) → `:root` 에 **`--font-sans` / `--font-mono` 토큰** 신설.
  이게 폰트 스택 단일 원본이며 신규 CSS 는 글꼴을 직접 나열하지 않는다
- 흩어져 있던 선언 전부 토큰으로 이전: 본문 5곳(`index.css`, `MainSidebar.css` Poppins,
  `TemplateModal.css` Quicksand+Jua, `AppBuilderPage.css`·`ProjectRunsPage.css` Segoe UI 스택,
  `IntroPage.css`·`EvaluationPage.css` Inter), 고정폭 17곳(`monospace` / `Consolas, Monaco`)
- `MainPage.jsx` 히어로 제목의 `fontFamily: 'Noto Sans KR'` 인라인 하드코딩 제거 → body 상속

**실측 결과:** 로드되는 폰트 패밀리가 `Pretendard Variable` **하나**뿐(이전 5종). CSS 에 남은
명시적 `font-family` 선언 0건 — 전부 `var(--font-*)` 또는 `inherit`.

**남은 것:** `EditorPage.jsx`(2) · `AppBuilderPage.jsx`(4) · `UIEngine.jsx`(1) 의 인라인
`fontFamily: 'monospace'` 7곳. 미커밋 변경 파일이라 손대지 않았고, 폴백 체인이 작동하므로 렌더 차이는 미미하다.
`--font-mono` 의 `JetBrains Mono` 는 아직 로드하지 않으므로 실제로는 `SFMono/Consolas` 로 폴백된다.

### 이어서 시작하는 방법

1. §3 마스터 프롬프트 + §2 해당 Tier 표의 "모티프 프롬프트" 열로 SVG 생성
   — **§3 사양은 B1~B6 에서 실측으로 여러 번 보강했다. 반드시 현재 버전을 쓸 것.**
2. `frontend/src/assets/icons/<그룹>/` 에 저장 (파일만 넣으면 자동 등록 — §5-2)
3. `python3 Documents/build-icon-qa.py` → `Documents/icon-qa.html` 을 브라우저로 열어 검증
   — 새 배치는 스크립트 상단 `COLORS` / `LABELS` / `BEFORE` 에 항목 추가
4. **실제 컴포넌트를 띄워서 눈으로 확인할 것.** B1~B6 에서 고친 문제 9건 중
   **정적 검사로 잡힌 것은 0건, 전부 렌더해보고 발견했다.**
5. 적용 후 §5-3 순서대로 교체, 미사용이 된 lucide import 정리

### 배치별 상세 기록

| 배치 | 문서 | 핵심 성과 |
|---|---|---|
| Tier 6 | [icon-tier6-brand.md](icon-tier6-brand.md) | 로고(후보 3안 비교) · 파비콘 · OG. **구 로고는 라이트 테마에서 픽셀 차이 0개 = 문자 그대로 투명이었음**. 워드마크 `#ffffff` 하드코딩도 함께 수정 |
| 빈 상태 | [icon-empty-states.md](icon-empty-states.md) | 일러스트 3종 + `EmptyState` 컴포넌트. §3.2가 지적한 "큰 Card 안에 버튼" 구조 제거 |
| 템플릿 | [icon-template-emoji.md](icon-template-emoji.md) | 템플릿 이모지 22개를 **기존 아이콘 재사용으로** 제거 (신규 SVG 0개) + `builtin-14` id 중복 버그 수정 |
| B9 | [icon-prompt-B9.md](icon-prompt-B9.md) | 실행 상태 5종, 그레이스케일 형태 구분 확보, 회전 중심(12,12) 실측 검증 |
| B8 | [icon-prompt-B8.md](icon-prompt-B8.md) | 앱 빌더 팔레트 14개, `TextCursorInput` 앱에서 완전 제거, 하이라키 뱃지 5→9종 통일 |
| B7 | [icon-prompt-B7.md](icon-prompt-B7.md) | API 센터 이모지 8개 제거(컬러 SVG), `toss` 프로바이더 신규 추가 |
| B5 | [icon-prompt-B5.md](icon-prompt-B5.md) | `Puzzle` 5중 · `Settings` 캔버스 5중 · `FileCode` 2중 해소 |
| B4 | [icon-prompt-B4.md](icon-prompt-B4.md) | `MessageCircle` 3중 · `Send` 2중 해소 + `tossNode` 문제 발견 |
| B1+B2 | [icon-prompt-B1-B2.md](icon-prompt-B1-B2.md) | `Clock` 3중 · `LogOut` 2중 해소 + **트리거 언어**(재생 삼각형) 도입 |
| B3 | [icon-prompt-B3.md](icon-prompt-B3.md) | 노드 37/37 커스텀 달성 |
| B6 | [icon-prompt-B6.md](icon-prompt-B6.md) | 내비 14개 + `Globe` 앱에서 완전 제거 |

### 이 작업으로 변경된 파일 (커밋 안 됨)

**신규**
- `frontend/src/icons/index.jsx` — `import.meta.glob` 로더. **의존성 추가 없음**
- `frontend/src/assets/icons/node/*.svg` (37) · `nav/*.svg` (14) · `provider/*.svg` (9) · `ui/*.svg` (14)
- `Documents/build-icon-qa.py` · `Documents/icon-*.md`

**수정**
- `frontend/src/Sidebar.jsx` · `customNodes.jsx` · `MainSidebar.jsx` · `nodeRegistry.js`
- `frontend/src/pages/WebhookManagerPage.jsx`
- `frontend/src/pages/ApiCenterPage.jsx` (이모지→Icon, toss 추가) · `ApiCenterPage.css` (`.api-icon` 정렬만)
- `frontend/src/pages/AppBuilderPage.jsx` (Icon 23곳, lucide import 27→15종)
- `frontend/src/logicNodes.jsx` (Blueprint 캔버스 노드 4종 — 팔레트와 불일치였음)
- `frontend/src/TemplateModal.jsx` · `TemplateModal.css` (이모지 22개 제거, 제목 아이콘 정렬)
- B9 상태 적용 7파일: `pages/ProjectRunsPage.jsx` · `pages/EvaluationPage.jsx` · `pages/AdminPage.jsx`
  · `pages/AppRunnerPage.jsx` · `pages/TutorialPage.jsx` · `SiteFeedbackWidget.jsx` · `CustomConfirm.jsx`

> ⚠️ `git status` 에 보이는 다른 수정 파일(`App.jsx` `index.css` `EditorPage.jsx`
> `AppBuilderPage.*` `MainPage.*` `SettingsPage.jsx` `DeployModal.jsx` 및 `backend/` 전체)은
> **이 작업 전부터 커밋 안 된 상태였고, 아이콘 작업과 무관하다.** 건드리지 않았다.

### 아이콘 작업 중 발견한 별개 버그 2건

1. ✅ **고침** — `posterGeneratorNode` 가 팔레트에 아예 렌더되지 않았다.
   `category: 'action'` 인데 `Sidebar.jsx` 의 `categories` 에 `action` 이 없고, 기존 코드가
   `meta.category || 'integration'` 로 **undefined 만 걸러서** 잘못된 값이 통과했다.
   37개 정의 중 36개만 표시되던 상태. → 알려진 id 집합으로 검증 후 폴백하도록 수정.
2. ✅ **고침** — `tossNode` 가 캔버스 컴포넌트도 `nodeTypes` 등록도 없었다.
   백엔드는 완전히 지원(`meta_agent.py:290`, `dry_run.py:33`)하는데 프런트에 없어서,
   끌어놓거나 AI가 생성하면 빈 상자로 렌더되어 필드 입력이 불가능했다.
   → `nodeRegistry.js` 로 옮겨 `DynamicNode` 가 처리하게 함. 필드는
   `integration_nodes.py` 의 `generate_toss_node()` 가 읽는 키와 일치시킴.
3. ⬜ **미수정 (B7에서 발견)** — `ApiCenterPage.css` 가 정의되지 않은 CSS 변수
   (`--bg-secondary`, `--accent-color`, `--text-primary` 등)를 사용해 **라이트 테마에서
   저장 버튼이 거의 안 보인다.** 디자인 문서 §4.1이 지적한 바로 그 문제 — 디자인 토큰
   작업(Phase 1) 때 함께 고칠 것.

### 아직 손대지 않은 것 (의도적)

- `Sidebar.jsx` 의 `Puzzle`, `customNodes.jsx` 의 `Settings` 는 현재 도달하지 않는 폴백이다
  (레지스트리 6종 모두 `icon` 보유). 앞으로 `icon` 없이 추가될 노드용으로 남겨뒀다.
- `Shuffle` 은 두 파일에 남은 dead import 다. 아이콘 작업 이전부터 죽어 있어 손대지 않았다.
- `Clock`(9곳) · `Play`(13곳) · `Send`(5곳) 은 전부 같은 의미(시각·실행·전송)로 쓰이므로
  의도적으로 lucide 유지. §1 "UI chrome 은 손대지 않는다" 원칙.
- ~~`tossNode` 의 시크릿 키는 노드에 직접 입력해야 한다~~ → **B7에서 해결**: API 센터에
  `toss` 프로바이더 추가됨 (`graph.py:334` 가 `{{API_CENTER:<provider>}}` 를 화이트리스트 없이
  일반 생성하므로 프런트 추가만으로 동작). 단 `meta_agent` 가 tossNode 생성 시 placeholder 를
  자동 안내하지는 않아, 발급 가이드 4단계에서 `{{API_CENTER:toss}}` 입력을 안내하는 방식이다.

---

## 0. 먼저 결정할 것: SVG로 만들 것 vs PNG로 만들 것

| 자산 | 만드는 방식 | 이유 |
|---|---|---|
| UI 아이콘 (16~20px, 아래 Tier 1~5) | **SVG (Claude에게 직접 코드로 생성 요청)** | 16px에서 래스터는 뭉개짐. `currentColor`로 다크/라이트 테마 자동 대응. 파일 1개당 1KB 미만 |
| 로고 / 파비콘 / OG / 빈 상태 일러스트 (Tier 6) | **SVG 로 작성 → 필요한 것만 playwright 로 PNG 래스터화** | ⚠️ **초안의 "PNG(이미지 생성 모델)" 판단을 Tier 6 실작업에서 뒤집었다.** §4-2·§4-3 프롬프트 내용 자체가 `flat vector, line art, 2px uniform stroke, no photorealism` — 순수 벡터 명세이고 그라데이션·질감이 없다. PNG로 구우면 §4-1이 지적한 `logo.png` 실패(테마 색 고정)를 그대로 재현한다. 실제로 일러스트 3종은 `currentColor` 로 테마 대응하며 3종 합계 2.9KB다. 파비콘·OG처럼 규격이 PNG를 요구하는 것만 래스터화한다 |
| 인트로 히어로 등 회화적 이미지 | PNG (이미지 생성 모델) | 실제로 그라데이션·질감·깊이가 필요한 경우에만 |

**즉, "아이콘 이미지 생성"의 90%는 이미지 생성이 아니라 SVG 코드 생성이 정답입니다.**
아래 프롬프트도 그 기준으로 두 종류를 나눠 썼습니다.

---

## 1. 현재 상태 진단 — 왜 새로 만들어야 하는가

전체 132개의 lucide 아이콘이 쓰이고 있는데, **의미가 다른 기능에 같은 아이콘이 재사용되는 충돌**이 실제로 존재합니다. 이게 신규 제작의 가장 강한 근거입니다.

| 중복 아이콘 | 충돌하는 기능들 | 심각도 | 상태 |
|---|---|---|---|
| `Puzzle` | **레지스트리 노드 5종 전부** (Slack 메세지 / 결제 링크 생성 / 구글 시트 / 구글 캘린더 / 포스터 생성) — [nodeRegistry.js](../../../frontend/src/nodeRegistry.js) | 🔴 최상 | ✅ B5 |
| `MessageCircle` | 디스코드 봇(시작) / 디스코드 발송 / 카카오 알림톡 | 🔴 | ✅ B4 |
| `Clock` | 스케줄(시작) / Delay(대기) / 사이드바 "스케줄 관리" | 🔴 | ✅ B1+B2+B6 |
| `Globe` | 웹훅 수신 / 웹 크롤러 / 사이드바 "웹훅 관리" | 🔴 | ✅ B1+B4+B6 (앱에서 완전 제거) |
| `Send` | 텔레그램 봇(시작) / 텔레그램 발송 / 채팅 전송 버튼 | 🟠 | ✅ B4 (노드 간) |
| `LogOut` | 결과 출력 / 반복 종료(180° 회전으로 억지 구분) | 🟠 | ✅ B1+B2 |
| `FileCode` | 자동 완성 / 템플릿 분석 | 🟠 | ✅ B5 |
| `Box` | 토크나이저 / AppBuilder Container / 채팅 사이드바 | 🟠 | 🟡 B3+B8 (ChatSidebar·TutorialSandbox 2곳 잔존 — 의미 상이, 경미) |
| `TextCursorInput` | Input Field / Text Area — [AppBuilderPage.jsx](../../../frontend/src/pages/AppBuilderPage.jsx) | 🟠 | ✅ B8 (앱에서 완전 제거) |
| `Settings` | **레지스트리 5종의 캔버스 헤더 전부** — 팔레트(`Puzzle`)와도 불일치였음 | 🔴 | ✅ B5 |

> **B1~B9 적용 완료 실측:** 커스텀 SVG **79개** (노드 37 + 내비 14 + 프로바이더 9 + 앱 빌더 14 + 상태 5),
> 합계 23.2KB. 앱 전체 lucide 종류 **132 → 89개**. `Globe` · `LogOut` · `FileCode` ·
> `TextCursorInput` 은 앱에서 완전 제거. **남은 충돌은 `Box` 1종뿐이며 경미하다**
> (ChatSidebar "앱 연동됨" · TutorialSandbox "연습 캔버스" — 의미가 서로 다른 2곳).
> `Clock`(9곳) · `Play`(13곳) · `Send`(5곳) 은 전부 같은 의미(시각·실행·전송)로 쓰이므로
> 의도적으로 남겼다 — §1 의 "UI chrome 은 손대지 않는다" 원칙 그대로다.

추가 문제:
- ~~**이모지를 아이콘으로 사용 중**~~ → OS/브라우저마다 다른 그림으로 렌더링됨. 디자인 통제 불가.
  - ✅ **B7 해결** — [ApiCenterPage.jsx](../../../frontend/src/pages/ApiCenterPage.jsx) 프로바이더 8개
  - ✅ **해결** — [TemplateModal.jsx](../../../frontend/src/TemplateModal.jsx) 템플릿 **22개**(문서에 21개로 적혀 있었으나
    실측 22개 — ⏲️ 지연 리마인더 누락). 신규 제작 없이 기존 아이콘 재사용으로 처리
  - ⬜ **잔존** — `DeployModal.jsx` · `customNodes.jsx` · `MainPage.jsx` · `SettingsPage.jsx`
    · `EditorPage.jsx` · `ProjectRunsPage.jsx` (대부분 미커밋 변경 파일이라 후순위)
- **로고가 사실상 흰색 단색** — [logo.png](../../../logo.png)는 흰 "WA" 워드마크라 라이트 테마에서 보이지 않음. 파비콘/OG 이미지도 없음 ([index.html](../../../frontend/index.html) 확인).

### 반대로 — 새로 만들지 말고 lucide 그대로 둘 것 (약 60개)
`X, Menu, Plus, Minus, Search, Copy, Trash2, Save, Download, Upload, Edit, ExternalLink, MoreVertical, Chevron*(Down/Right/Up/sDown/sUp), Arrow*(Left/Right), Undo2, Redo2, RotateCcw, RefreshCw, Eye, Lock, Unlock, Check, Paperclip, Settings2, Star, ...`
→ 이건 만국 공통 UI chrome입니다. 커스텀하면 학습 비용만 늘고 얻는 게 없습니다. **정체성이 드러나는 곳에만 커스텀 아이콘을 씁니다.**

---

## 2. 생성 리스트 (총 80개)

### Tier 1 — 워크플로우 노드 아이콘 (37개) · 최우선

제품의 시그니처 자산. 캔버스에서 사용자가 가장 오래 보는 그림입니다.

| # | 파일명 | 노드 | 현재 아이콘 | 색상 | 모티프 프롬프트(→ §3 템플릿에 삽입) |
|---|---|---|---|---|---|
| **기본 (Core)** ||||||
| 1 | `node-start.svg` | 시작 | Play | `#10b981` | 오른쪽을 향한 삼각형 재생 버튼, 뒤에서 퍼지는 얇은 원형 파동 1겹 |
| 2 | `node-schedule.svg` | 스케줄 (시작) | Clock | `#8b5cf6` | 달력 그리드 사각형 좌하단에 작은 시계 바늘이 겹쳐진 형태 (달력+시계 조합, 시계 단독 금지) |
| 3 | `node-output.svg` | 결과 출력 | LogOut | `#f97316` | 열린 대괄호에서 오른쪽으로 나가는 화살표 + 화살표 끝에 짧은 수평선 3개(출력 텍스트) |
| **입력 (Input)** ||||||
| 4 | `node-dynamic-input.svg` | 동적 입력 | Keyboard | `#d946ef` | 입력 필드 사각형 안에 깜빡이는 텍스트 커서(I-beam), 우상단에 작은 반짝임 4각 별 |
| 5 | `node-webhook.svg` | 웹훅 수신 | Globe | `#0ea5e9` | 갈래가 셋인 훅(webhook) 곡선 3개가 한 점으로 **수렴**하며 그 점에 속이 찬 원 |
| 6 | `node-discord-trigger.svg` | 디스코드 봇 (시작) | MessageCircle | `#5865F2` | 둥근 말풍선 안에 눈 두 개 형태의 봇 얼굴, 왼쪽 아래에 작은 재생 삼각형 배지 |
| 7 | `node-telegram-trigger.svg` | 텔레그램 봇 (시작) | Send | `#26A5E4` | 종이비행기 실루엣, 왼쪽 아래에 작은 재생 삼각형 배지 |
| 8 | `node-value.svg` | 변수 (값) | Variable | `#ec4899` | 좌우 중괄호 `{ }` 사이에 속이 찬 작은 마름모 1개 |
| **AI 모델** ||||||
| 9 | `node-prompt.svg` | 프롬프트 | MessageSquare | `#3b82f6` | 각진 말풍선 안에 왼쪽 정렬된 수평선 3개(길이 다름) |
| 10 | `node-llm.svg` | LLM | BrainCircuit | `#8b5cf6` | 뇌 반쪽 윤곽 + 오른쪽 절반이 회로 노드 3개와 연결선으로 변환된 하이브리드 |
| 11 | `node-multi-agent.svg` | Multi-Agent | Users | `#6366f1` | 삼각 배치된 원 3개가 서로 선으로 연결, 상단 원이 조금 더 큼(supervisor 함의) |
| **제어 로직 (Logic)** ||||||
| 12 | `node-condition.svg` | 조건 분기 | SplitSquareHorizontal | `#0ea5e9` | 왼쪽에서 온 선이 마름모(판단)를 지나 위/아래 두 갈래로 갈라짐 |
| 13 | `node-loop.svg` | 반복 (Loop) | Repeat | `#ca8a04` | 시계방향 순환 화살표 루프, 상단 끊긴 지점에 카운터를 뜻하는 작은 점 3개 |
| 14 | `node-break.svg` | 반복 종료 | LogOut 회전 | `#dc2626` | 순환 루프가 오른쪽에서 **끊기고** 그 절단면에 굵은 수직 정지선 하나 |
| 15 | `node-delay.svg` | Delay (대기) | Clock | `#3b82f6` | 모래시계 실루엣, 아래쪽에 떨어진 모래 알 3개 (시계 아님) |
| 16 | `node-merge.svg` | Merge (병합) | Merge | `#ec4899` | 위·아래에서 온 선 2개가 오른쪽에서 하나로 합쳐지며 합류점에 원 |
| **코드 & 데이터** ||||||
| 17 | `node-python.svg` | 파이썬 | Terminal | `#eab308` | 터미널 창 사각형 안에 `>` 프롬프트 기호와 커서 밑줄 (뱀 로고 사용 금지 — 상표) |
| 18 | `node-json-parser.svg` | JSON 파서 | Braces | `#eab308` | 중괄호 `{ }` 안에서 계층 트리 형태로 갈라지는 짧은 선 3개 |
| 19 | `node-tokenizer.svg` | 토크나이저 | Box | `#14b8a6` | 하나의 긴 막대가 점선 경계로 조각 4개로 분할된 형태 |
| 20 | `node-distributor.svg` | 분배기 | Network | `#6366f1` | 왼쪽 원 1개에서 오른쪽 원 3개로 **발산**하는 연결선 (§5의 수렴형과 대칭) |
| 21 | `node-database.svg` | 데이터베이스 | Database | `#059669` | 원통형 실린더 3단, 최상단 면에 타원 하이라이트 |
| **외부 연동 (Integration)** ||||||
| 22 | `node-web-crawler.svg` | 웹 크롤러 | Globe | `#0ea5e9` | 지구 격자 구체 + 우하단에 대각선 손잡이 돋보기 겹침 (수집 함의) |
| 23 | `node-email.svg` | 이메일 전송 | Mail | `#f43f5e` | 봉투 실루엣, 봉투 오른쪽 상단에서 위로 뻗는 짧은 발송 화살표 |
| 24 | `node-kakao-alimtalk.svg` | 카카오 알림톡 | MessageCircle | `#facc15` | 모서리가 아주 둥근 말풍선 + 우상단에 작은 알림 벨 배지 (카카오 로고 재현 금지) |
| 25 | `node-discord-send.svg` | 디스코드 발송 | MessageCircle | `#5865F2` | 게임패드 실루엣 + 우상단 발송 화살표 (Tier1-6 트리거와 구분) |
| 26 | `node-telegram-send.svg` | 텔레그램 발송 | Send | `#26A5E4` | 종이비행기 + 뒤에 남는 궤적 점선 (트리거 버전과 궤적으로 구분) |
| 27 | `node-notion.svg` | Notion | StickyNote | `#9B9B9B` | 페이지 사각형 좌측에 세로 굵은 바인딩선, 내부에 수평선 2개 (Notion 로고 재현 금지) |
| 28 | `node-toss-payments.svg` | 토스페이먼츠 | CreditCard | `#3b82f6` | 카드 사각형 + 우하단에서 위로 향하는 결제 완료 체크 (토스 로고 재현 금지) |
| 29 | `node-http-request.svg` | HTTP Request | ArrowRightLeft | `#0ea5e9` | 상단 오른쪽 화살표(요청) / 하단 왼쪽 화살표(응답) 짝, 두 화살표 사이 여백 균등 |
| **고급 기능 (Advanced)** ||||||
| 30 | `node-file-modifier.svg` | 자동 완성 | FileCode | `#f43f5e` | 문서 사각형(우상단 접힘) 안에 자동 채워지는 수평선 3개, 마지막 줄은 점선 |
| 31 | `node-template-analyzer.svg` | 템플릿 분석 | FileCode | `#8b5cf6` | 문서 사각형 위에 돋보기 겹침, 문서 내부는 와이어프레임 블록 2개 |
| 32 | `node-human-approval.svg` | 사용자 승인 (대기) | UserCheck | `#f43f5e` | 사람 상반신 실루엣 + 오른쪽에 체크 표시, 머리 위에 얇은 대기 점선 호 |
| **레지스트리 노드 (현재 전부 Puzzle — 최우선)** ||||||
| 33 | `node-slack.svg` | Slack 메세지 | Puzzle | `#0ea5e9` | 격자 형태로 교차하는 둥근 막대 4개(해시 격자) + 우측 말풍선 꼬리 (Slack 로고 재현 금지) |
| 34 | `node-payment-link.svg` | 결제 링크 생성 | Puzzle | `#03c75a` | 사슬 고리 2개 + 아래쪽에 작은 원형 코인 1개 |
| 35 | `node-google-sheets.svg` | 구글 시트 | Puzzle | `#0f9d58` | 3×3 스프레드시트 격자, 좌상단 1칸만 채워짐 (구글 로고 재현 금지) |
| 36 | `node-google-calendar.svg` | 구글 캘린더 | Puzzle | `#4285f4` | 달력 사각형 상단에 고리 2개, 내부에 날짜 점 4개 중 1개만 채워짐 |
| 37 | `node-poster-generator.svg` | 포스터/이미지 생성 | Puzzle | `#f59e0b` | 액자 사각형 안에 산 능선 + 태양, 우상단에 4각 반짝임 별(AI 생성 함의) |

### Tier 2 — 사이드바 내비게이션 (14개)

[MainSidebar.jsx:96-161](../../../frontend/src/MainSidebar.jsx#L96). 노드 아이콘보다 **한 단계 굵고 단순하게** 그려야 18px에서 읽힙니다.

| # | 파일명 | 메뉴 | 현재 | 모티프 프롬프트 |
|---|---|---|---|---|
| 38 | `nav-home.svg` | 홈 | Home | 경사 지붕 집, 문 없이 단순 실루엣 |
| 39 | `nav-workflows.svg` | 내 워크플로우 | LayoutGrid | 노드 사각형 3개가 연결선으로 이어진 미니 플로우 (격자 아님 — 통계와 구분) |
| 40 | `nav-app-builder.svg` | 앱 빌더 (AI) | Wand2 | 마법봉 대각선 + 궤적에 4각 반짝임 2개 |
| 41 | `nav-tutorial.svg` | 튜토리얼 | GraduationCap | 학사모 + 늘어진 태슬 |
| 42 | `nav-templates.svg` | 커뮤니티 템플릿 | LibraryBig | 세로로 꽂힌 책 3권, 가운데 한 권만 살짝 기울어짐 |
| 43 | `nav-webhooks.svg` | 웹훅 관리 | Globe | 훅 곡선 3갈래 + 우하단 톱니 배지 (Tier1-5와 배지로 구분) |
| 44 | `nav-bots.svg` | 봇 관리 | Bot | 사각 로봇 머리 + 안테나 1개 + 눈 2개 |
| 45 | `nav-scheduler.svg` | 스케줄 관리 | Clock | 달력 + 우하단 톱니 배지 |
| 46 | `nav-api-center.svg` | API 센터 | Key | 열쇠 실루엣 + 열쇠 머리 안에 중괄호 `{}` |
| 47 | `nav-statistics.svg` | 통계 | BarChart | 높이가 다른 막대 3개 + 상단을 지나는 상승 꺾은선 |
| 48 | `nav-settings.svg` | 설정 | Settings | 톱니 6개 기어, 중앙 원 크게 |
| 49 | `nav-patch-notes.svg` | 패치 노트 | ScrollText | 위아래 말린 두루마리 + 내부 수평선 3개 |
| 50 | `nav-intro.svg` | 서비스 소개 | Info | 원 안에 `i`, 획 굵기 내비 기준 |
| 51 | `nav-admin.svg` | 어드민 패널 | Shield | 방패 실루엣 + 내부 체크 (색상 `#2ecc71` 고정) |

### Tier 3 — API 센터 프로바이더 (8개) · 이모지 대체

[ApiCenterPage.jsx:11-100](../../../frontend/src/pages/ApiCenterPage.jsx#L11). **컬러 SVG 허용** (여기만 예외 — 프로바이더 식별이 목적).

| # | 파일명 | 프로바이더 | 현재 | 모티프 프롬프트 |
|---|---|---|---|---|
| 52 | `provider-openai.svg` | OpenAI (ChatGPT) | 🤖 | 6갈래 방사 대칭 매듭 문양, 단색 `#10a37f` (OpenAI 공식 로고 복제 금지 — 추상 대체) |
| 53 | `provider-gemini.svg` | Google Gemini | ✨ | 4각 반짝임 별 큰 것 1개 + 작은 것 1개, 청→자 그라데이션 |
| 54 | `provider-kakao-rest.svg` | Kakao REST API 키 | 💬 | 둥근 말풍선, 노란 배경 `#facc15` + 갈색 획 `#3c1e1e` |
| 55 | `provider-kakao-token.svg` | Kakao 메시지 토큰 | 🔑 | 말풍선 안에 작은 열쇠, 자동 갱신 뜻하는 순환 화살표를 말풍선 테두리로 |
| 56 | `provider-discord.svg` | Discord Bot Token | 🎮 | 둥근 게임패드 실루엣, `#5865F2` 단색 |
| 57 | `provider-telegram.svg` | Telegram Bot Token | ✈️ | 원 안에 종이비행기, `#26A5E4` 단색 |
| 58 | `provider-notion.svg` | Notion Token | 📝 | 흑백 문서 페이지 + 세로 바인딩선, `#191919` |
| 59 | `provider-gmail-smtp.svg` | Gmail SMTP | 📧 | 봉투 + 봉투 안쪽 V자 접힘선 강조, `#ea4335` |

### Tier 4 — 앱 빌더 팔레트 (14개)

[AppBuilderPage.jsx:1026-1105](../../../frontend/src/pages/AppBuilderPage.jsx#L1026)

| # | 파일명 | 항목 | 현재 | 모티프 프롬프트 |
|---|---|---|---|---|
| 60 | `ui-container.svg` | Container (Div) | Box | 점선 테두리 사각형 + 내부 좌상단에 실선 작은 사각형 |
| 61 | `ui-text.svg` | Text | Type | 대문자 `T` 세리프 없이, 좌우 균형 |
| 62 | `ui-input.svg` | Input Field | TextCursorInput | 납작한 사각형 1줄 + 왼쪽에 I-beam 커서 |
| 63 | `ui-textarea.svg` | Text Area | TextCursorInput(중복) | **높은** 사각형 + 내부 수평선 3개 + 우하단 리사이즈 삼각 (63과 높이로 구분) |
| 64 | `ui-button.svg` | Button | MousePointerClick | 라운드 사각형 + 우하단 클릭 커서와 클릭 파동선 2개 |
| 65 | `ui-image.svg` | Image | ImageIcon | 사각형 안에 산 능선 + 좌상단 원(태양) |
| 66 | `ui-dropdown.svg` | Dropdown | List | 사각형 우측에 아래 방향 산형(chevron), 아래로 펼쳐진 항목선 2개 |
| 67 | `ui-checkbox.svg` | Checkbox | CheckSquare | 라운드 사각형 안에 체크, 획 굵기 균일 |
| 68 | `ui-divider.svg` | Divider | Minus | 가로 실선 1개 + 양 끝에 짧은 세로 마감선 |
| 69 | `ui-hierarchy.svg` | Hierarchy | Layers | 인덴트된 트리 브랜치 3단 (레이어 스택 아님) |
| 70 | `bp-event-trigger.svg` | Event Trigger | Play `#ef4444` | 번개 + 클릭 파동선 2개 |
| 71 | `bp-get-value.svg` | Get Value | Database `#10b981` | 실린더에서 오른쪽으로 나오는 화살표 |
| 72 | `bp-ui-action.svg` | UI Action | ArrowRight `#3b82f6` | 화면 사각형 + 내부를 향해 들어가는 화살표 |
| 73 | `bp-workflow-execute.svg` | Workflow Execute | Sparkles | 미니 플로우 노드 3개 + 재생 삼각형 오버레이 |

### Tier 5 — 실행 상태 아이콘 (5개)

캔버스·실행 로그·통계에서 반복 노출. 색맹 접근성을 위해 **색만이 아니라 형태로도 구분**되어야 합니다.

| # | 파일명 | 상태 | 현재 | 모티프 프롬프트 |
|---|---|---|---|---|
| 74 | `status-success.svg` | 성공 | CheckCircle2 | 원 안에 체크, 체크 획이 원 안쪽 여백을 넉넉히 남김 |
| 75 | `status-failed.svg` | 실패 | XCircle | 원 안에 X, 두 획 교차각 정확히 90° |
| 76 | `status-running.svg` | 실행 중 | Activity | 열린 원호 3/4 (회전 애니메이션용 — 끝 캡 라운드, 회전 중심 정확히 12,12) |
| 77 | `status-pending.svg` | 대기 | Clock | 원 안에 점 3개 수평 배치 (시계 아님 — Tier1-2/15와 구분) |
| 78 | `status-warning.svg` | 경고 | AlertTriangle | 라운드 삼각형 + 내부 감탄부호 |

### Tier 6 — 브랜드 / 래스터 자산 (2 + 3개) · PNG 생성

| # | 파일명 | 용도 | 현재 상태 |
|---|---|---|---|
| 79 | `logo-mark.svg` + `logo-lockup.svg` | 사이드바 로고 | [logo.png](../../../logo.png)가 흰색 단색 → 라이트 테마에서 안 보임 |
| 80 | `favicon.svg` / `favicon-32.png` / `apple-touch-icon-180.png` | 브라우저 탭 · iOS 홈 | **없음** |
| — | `og-image-1200x630.png` | 링크 공유 카드 | **없음** |
| — | `empty-workflows.png` / `empty-apps.png` / `empty-templates.png` | 빈 목록 상태 | 현재 텍스트만 |
| — | `intro-hero.png` | 인트로 페이지 히어로 | `assets/demo-1~3.webp` 재활용 중 |

---

## 3. 마스터 프롬프트 — SVG 아이콘 (Tier 1~5, 78개)

> Claude에게 **한 번 붙여넣고**, 마지막 줄의 아이콘 목록만 바꿔가며 반복 사용합니다.
> 10~12개씩 배치로 나눠 요청하는 게 품질이 가장 안정적입니다.

```
당신은 프로덕션 UI 아이콘 세트를 만드는 아이콘 디자이너입니다.
아래 사양을 100% 준수하는 SVG 코드를 생성하세요.

[기하 사양]
- viewBox="0 0 24 24", 루트에 width/height 속성은 넣지 않는다
- **기하 좌표는 2~22 범위를 꽉 채운다 (=20×20).** 최대 변이 18 미만이면 실패로 본다.
  이유: 교체하지 않고 남겨둘 lucide 아이콘 약 60개가 2~22 규약이다. 3~21로 그리면
  같은 줄에 놓였을 때 새 아이콘만 10% 작아 보인다. 획 외곽(±1)이 1~23까지 나가는 건 허용.
- stroke="currentColor", stroke-width="2", fill="none"
- stroke-linecap="round", stroke-linejoin="round"
- 좌표는 0.5px 그리드에 스냅한다 (2, 2.5, 3 … 형태. 3.7231 같은 값 금지)
- path/circle/rect/line 기본 도형만 사용. filter, mask, clipPath, 그라데이션, 텍스트, style 속성 금지
- 도형 개수는 아이콘당 최대 5개 (16px에서 뭉개지지 않게)
- **평행한 획끼리는 중심 간격 4px 이상** (stroke-width 2라 4px 미만이면 획 사이 여백이 2px 아래로
  떨어져 16px에서 붙어 보인다). 20px 영역에 평행선은 최대 5줄까지만 들어간다.
- 작은 점은 lucide 관행대로 `M8 14h.01` (길이 0 + round cap) 으로 찍는다
- "채워진 1칸/선택된 상태" 같은 단일 강조 요소에만 `fill="currentColor" stroke="none"` 허용

[스타일 사양]
- lucide-react 0.300과 시각적으로 이어지는 기하학적 라인 아이콘 스타일
- 원근·그림자·질감 없음. 완전한 플랫 라인 드로잉
- 상대적 시각 무게가 세트 전체에서 균일해야 함
- 배지/서브 요소는 우상단 또는 우하단에만 배치하고 지름 6px 이하

[출력 형식]
아이콘 1개당 아래 형식으로만 출력. 설명 문장은 붙이지 않는다.

--- 파일명: <파일명>.svg ---
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  ...
</svg>

[중요 제약]
- 실제 기업 로고(Slack, Discord, Telegram, Notion, Google, Kakao, Toss, OpenAI, Python 등)를
  재현하지 마라. 상표권 문제가 있다. 대신 그 서비스의 "기능"을 은유하는 도형으로 그려라.
- 같은 세트 안에서 두 아이콘이 서로 혼동되면 안 된다. 아래 목록에 "~와 구분" 표기가 있으면
  반드시 형태 차원(윤곽선 실루엣)에서 달라야 한다. 색이나 회전으로 구분하는 건 실패로 본다.

[생성할 아이콘]
1. node-start.svg — 오른쪽을 향한 삼각형 재생 버튼, 뒤에서 퍼지는 얇은 원형 파동 1겹
2. node-schedule.svg — 달력 그리드 사각형 좌하단에 작은 시계 바늘이 겹쳐진 형태 (시계 단독 금지)
3. ...  ← §2 표의 "모티프 프롬프트" 열을 그대로 붙여넣기
```

### 배치 분할 권장 (충돌 아이콘을 같은 배치에 넣어야 구분이 잘 됩니다)

| 배치 | 포함 | 개수 | 상태 |
|---|---|---|---|
| B1 | Tier 1 기본+입력 (#1~8) | 8 | ✅ [B1+B2](icon-prompt-B1-B2.md) |
| B2 | Tier 1 AI+로직 (#9~16) — Clock 계열 #2/#15/#77 구분 검증 | 8 | ✅ [B1+B2](icon-prompt-B1-B2.md) |
| B3 | Tier 1 코드&데이터 (#17~21) | 5 | ✅ [B3](icon-prompt-B3.md) |
| B4 | Tier 1 연동 (#22~29) — MessageCircle 계열 #24/#25 구분 검증 | 8 | ✅ [B4](icon-prompt-B4.md) |
| B5 | Tier 1 고급+레지스트리 (#30~37) — Puzzle 5종 전부 한 배치 | 8 | ✅ [B5](icon-prompt-B5.md) |
| B6 | Tier 2 내비 (#38~51) — Tier 1과 굵기 대비 확인 | 14 | ✅ [B6](icon-prompt-B6.md) |
| B7 | Tier 3 프로바이더 (#52~59) + `provider-toss` 신규 — 컬러 허용 사양 | 9 | ✅ [B7](icon-prompt-B7.md) |
| B8 | Tier 4 앱 빌더 (#60~73) | 14 | ✅ [B8](icon-prompt-B8.md) |
| B9 | Tier 5 상태 (#74~78) | 5 | ✅ [B9](icon-prompt-B9.md) |

**B4·B5에서 얻은 사양 보강 — 남은 배치 프롬프트에 반드시 넣을 것**
- 라인 아이콘은 넉아웃이 없으므로 **배지를 본체에 겹치면 항상 충돌로 보인다.** 겹치지 않게 분리하거나
  본체 안으로 넣어라. (B4 웹 크롤러·카카오, B5 결제 링크·토스에서 모두 이 문제가 났다)
- **선으로 그린 반짝임은 작은 크기에서 `+`(더하기)로 읽힌다.** 속이 찬 4각 별 path 를 써라.
  → #40 `nav-app-builder`, #53 `provider-gemini`, #73 에 적용 필요
- 좌우 대칭 C자 2개는 사슬로 읽히지 않는다. 연결 요소가 있어야 한다.
- 기존 lucide 아이콘과 결과가 사실상 같아지면 그 아이콘은 만들 가치가 없다. 의미를 하나 더 담아라
  (B4 HTTP Request: 응답을 점선으로).
- **루프/흐름 아이콘에서 화살촉은 장식이 아니다.** 빼면 그냥 곡선 덩어리로 읽힌다 (B1+B2 반복 종료).
- **배치를 나눠 진행할 때 아직 안 만든 뒤 배치의 모티프까지 확인하라.** #8 변수와 #18 JSON 파서가
  둘 다 중괄호 모티프여서, 먼저 만든 #8 을 대괄호로 양보했다.
- 시작(트리거) 노드처럼 **같은 역할군에는 공통 표식**을 넣어라. B1 은 "재생 삼각형을 품으면
  시작 노드" 규칙으로 트리거 4종을 묶었다.
- **대칭/거울 관계인 두 아이콘은 16px에서 같은 그림이다.** 축을 바꿔야 한다 (B3 분배기:
  웹훅의 수평 팬과 거울상이 되어 수직 트리로 재설계).
- **세로 폭이 이웃의 절반 이하면 팔레트에서 유독 작아 보인다.** bbox 최대 변만 보지 말고
  짧은 변도 확인하라 (B3 토크나이저: 높이 8 → 10).
- **나란히 놓이는 세트는 "읽히는가"뿐 아니라 "무게가 같은가"도 봐야 한다.** 획이 하나뿐인
  아이콘은 이웃보다 흐리게 보인다 (B6 앱 빌더: 테두리 획 추가).
- **기어는 "두꺼운 링 위의 짧은 돌기"다.** 작은 허브에서 뻗은 긴 스포크로 그리면
  배의 조타륜으로 읽힌다 (B6 설정).
- **높이만 다른 세로 사각형 여러 개는 무조건 막대그래프로 읽힌다** (B6 템플릿: 책 3권 → 펼친 책).
- 어떤 아이콘을 바꾸면 **같은 기능의 다른 표면도 함께 확인하라.** 내비만 바꾸면 페이지 제목과
  어긋난다 (B6: WebhookManagerPage 도 함께 교체).

**B7만 마스터 프롬프트를 이렇게 수정**해서 보내세요:
```
[Tier 3 예외 사양 — 이 배치에만 적용]
- stroke="currentColor" 대신 각 항목에 지정된 HEX를 fill 또는 stroke에 직접 사용한다
- 단색 1~2색까지 허용. 그라데이션은 Gemini 항목에서만 linearGradient 1개 허용
- 20×20 라이브 영역, 2px 패딩 규칙은 동일하게 유지
```

---

## 4. 프롬프트 — 브랜드 / 래스터 자산 (Tier 6)

### 4-1. 로고 마크 (SVG — Claude에게 직접)

```
"WorkFlow Ai" 라는 AI 워크플로우 자동화 SaaS의 로고 마크를 SVG로 만들어라.

[컨셉 요구]
- 알파벳 W와 A가 결합된 모노그램이면서, 동시에 "연결된 노드 그래프"로 읽혀야 한다
- W의 세 꼭짓점을 노드(원)로, 사이 획을 연결선(엣지)으로 해석하는 방향을 우선 검토
- 상승하는 방향성(좌하단 → 우상단)이 느껴지게

[기술 사양]
- viewBox="0 0 32 32", 정사각. 32px에서 형태가 무너지지 않을 것
- 단색 currentColor 버전과, #3b82f6 → #8b5cf6 linearGradient 버전 2종을 모두 출력
- 도형 8개 이하. 최소 획 굵기 2px (16px 파비콘으로 축소해도 살아남게)
- 텍스트 요소 사용 금지 (모두 path로)

[출력]
1) logo-mark.svg  — 마크 단독, 32×32
2) logo-lockup.svg — 마크 + "WorkFlow Ai" 워드마크 가로 배치, viewBox="0 0 160 32"
   워드마크는 Quicksand 600 느낌의 기하학적 산세리프를 path로 아우트라인
   "WorkFlow"는 currentColor, "Ai"는 #3b82f6
3) favicon.svg — 마크를 #0f172a 라운드 사각 배경(radius 6) 위에 흰색으로 올린 버전

주의: 현재 logo.png는 흰색 단색이라 라이트 테마(#f1f5f9 배경)에서 보이지 않는다.
새 로고는 #0f172a 배경과 #f1f5f9 배경 양쪽에서 모두 대비 3:1 이상이어야 한다.
```

### 4-2. OG 이미지 (이미지 생성 모델 — 영문 프롬프트)

```
A 1200x630 social share card for an AI workflow automation SaaS.
Dark slate background (#0f172a) with a subtle dot-grid pattern at 6% opacity.
Left two-thirds: a clean abstract node-graph diagram — five rounded rectangular
nodes connected by smooth bezier curves, nodes glowing in blue (#3b82f6),
violet (#8b5cf6), and emerald (#10b981), thin 2px connector lines with soft glow.
Right third: generous negative space reserved for a logo.
Flat vector illustration style, no text, no letters, no watermark,
no photorealism, no 3D render, no drop shadows on the background.
Crisp edges, high contrast, centered composition with 80px safe margin.
```

### 4-3. 빈 상태 일러스트 3종 (이미지 생성 모델 — 영문 프롬프트)

각각 800×600, 투명 배경 PNG로 요청:

```
[empty-workflows.png]
A minimal flat vector illustration on a transparent background: an empty canvas
frame with a faint dot grid, and one single dashed-outline placeholder node
floating in the center with a soft plus sign inside it. Two ghosted connector
curves trail off to the edges and fade out. Monochrome slate line art
(#334155 strokes) with a single blue accent (#3b82f6) on the plus sign.
No text, no characters, no background fill. 2px uniform stroke weight.

[empty-apps.png]
Same style. A dashed-outline smartphone frame with three ghosted rectangular
UI blocks inside, and a small magic wand with two sparkles resting against the
frame's lower right corner. Slate line art with violet accent (#8b5cf6) on the
sparkles. Transparent background, no text.

[empty-templates.png]
Same style. Three dashed-outline cards fanned out in a shallow overlapping stack,
the front card showing two ghosted content lines. A small emerald (#10b981)
download arrow hovers above the stack. Transparent background, no text.
```

### 4-4. 인트로 히어로 (이미지 생성 모델 — 영문 프롬프트)

```
A 1600x900 hero image for an AI workflow automation product landing page.
Isometric-lite flat vector scene: a horizontal chain of five rounded workflow
node cards connected left to right by glowing bezier curves, sitting on a dark
slate (#0f172a) surface with a faint dot grid. The leftmost node is emerald
(#10b981) with a play triangle, the middle nodes are blue (#3b82f6) and violet
(#8b5cf6) with abstract glyph shapes, the rightmost is amber (#f97316).
Soft volumetric glow beneath each node. Depth-of-field blur on the far edges.
No text, no letters, no logos, no human figures, no photorealism.
```

---

## 5. 생성 후 적용 방법

### 5-1. 파일 배치
```
frontend/src/assets/icons/
├── node/       # Tier 1 — 37개
├── nav/        # Tier 2 — 14개
├── provider/   # Tier 3 — 8개
├── ui/         # Tier 4 — 14개
├── status/     # Tier 5 — 5개
└── brand/      # Tier 6 — logo-mark, logo-lockup, favicon
```

### 5-2. React 컴포넌트로 소비 — [src/icons/index.jsx](../../../frontend/src/icons/index.jsx) (구현 완료)

**새 의존성 없음.** `vite-plugin-svgr` 를 넣을 필요가 없었다 — Vite 내장 `import.meta.glob` 으로
`?raw` 임포트하면 빌드 타임에 인라인된다. lucide 와 동일한 props 시그니처라 교체가 1:1이다.

```jsx
import { Icon } from './icons';

<UserCheck size={16} color="#f43f5e" />                        // before
<Icon name="node-human-approval" size={16} color="#f43f5e" />   // after
```

`assets/icons/` 아래에 `.svg` 파일을 추가하면 **자동 등록**되므로 로더 코드를 고칠 필요가 없다.
`.svg` 가 단일 소스이고, QA 스크립트도 같은 파일을 읽는다 (중복 정의로 인한 drift 없음).

`color` 를 넘기면 `style.color` 로 들어가므로 `stroke="currentColor"` 와 강조 요소의
`fill="currentColor"` 가 **함께** 그 색으로 해석된다. 생략하면 부모 CSS 색을 상속하므로
[Sidebar.jsx](../../../frontend/src/Sidebar.jsx) 의 `style={{ color: node.color }}` 패턴이 그대로 동작한다.

### 5-3. 교체 순서 (한 번에 132개 바꾸지 말 것)
1. ~~**Tier 1 레지스트리 5종** (#33~37) — Puzzle 중복 해소~~ → **B5로 완료** (고급 3종까지 8개)
2. **Tier 1 나머지** — [Sidebar.jsx](../../../frontend/src/Sidebar.jsx)(팔레트) + [customNodes.jsx](../../../frontend/src/customNodes.jsx)(캔버스) + [logicNodes.jsx](../../../frontend/src/logicNodes.jsx) 동시 수정 필요.
   같은 노드가 팔레트/캔버스에서 아이콘을 **따로** import 하므로 한쪽만 바꾸면 불일치가 생긴다.
   B5에서 실제로 그런 상태였다: 레지스트리 5종이 팔레트에선 `Puzzle`, 캔버스에선 `Settings` 였고
   `FileModifierNode`·`TemplateAnalyzerNode` 는 캔버스에 아이콘이 아예 없었다.
3. **Tier 3 + TemplateModal 이모지** — 이모지 제거
4. **Tier 6 브랜드** — favicon/OG는 [index.html](../../../frontend/index.html) `<head>` 추가 필요
5. Tier 2 / 4 / 5

### 5-4. 품질 검증 — 자동화됨

```bash
python3 Documents/build-icon-qa.py   # → Documents/icon-qa.html (브라우저로 열기)
```

`assets/icons/**/*.svg` 를 스캔해 SVG 소스를 인라인한 QA 페이지를 만든다 (file:// 로 바로 열림).
검사 내용:

| 항목 | 방식 |
|---|---|
| 광학 크기 | 브라우저 `getBBox()` 실측 → 최대 변 18 미만이면 `warn`, 획이 1~23 넘으면 `bad` |
| 가독성 | 16 / 18 / 24px 을 다크·라이트 칩 위에 렌더 |
| 색맹 대응 | `filter: grayscale(1)` 렌더 |
| 형태 충돌 | 같은 배치 아이콘을 한 표에 나열해 실루엣 육안 비교 |
| 교체 전후 | 기존 lucide 아이콘(BEFORE 맵)과 나란히 |
| 기하 정밀도 | 24×24 그리드 + 2~22 가이드 위에 168px 확대 |

새 배치를 추가할 때는 스크립트 상단의 `COLORS` / `LABELS` / `BEFORE` 딕셔너리에 항목을 넣으면 된다.

수동 확인이 남는 항목:
- [ ] 실제 팔레트([Sidebar.jsx](../../../frontend/src/Sidebar.jsx))에 끼워넣고 **교체 안 한 lucide 아이콘과 같은 줄에서** 무게가 맞는지
- [ ] 기업 로고를 그대로 재현한 아이콘이 없는지 (상표 검토)

---

## 6. 주의: 상표

Slack, Discord, Telegram, Notion, Google Sheets/Calendar, Toss, Kakao, OpenAI, Gemini, Python 은
모두 등록 상표입니다. 세 가지 선택지가 있고, **혼용을 권합니다**:

| 방식 | 적용 대상 | 비고 |
|---|---|---|
| 공식 브랜드 애셋 다운로드 후 사용 | Tier 3 프로바이더 8개 (API 센터 = 사용자가 그 서비스 키를 넣는 화면이라 실제 로고가 정확) | 각 사 브랜드 가이드라인 준수 필요 |
| 기능 은유 아이콘 (§2 표대로 신규 제작) | Tier 1 노드 아이콘 | 캔버스 통일감이 로고 정확성보다 중요 |
| 생성 모델로 로고 "비슷하게" 만들기 | ❌ 하지 말 것 | 상표 침해 + 이미지 모델은 로고 재현 품질이 나쁨 |
