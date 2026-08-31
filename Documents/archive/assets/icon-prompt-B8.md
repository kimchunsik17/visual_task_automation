# B8 배치 — Tier 4 앱 빌더 팔레트 (14개)

`icon-generation-prompts.md` §2 의 #60~73. **남은 아이콘 충돌 2종을 끝내는 배치다**:
`Box`(AppBuilderPage Container), `TextCursorInput`(Input Field / Text Area 2중 재사용).
사각형 모티프가 7개 이상이라 **실루엣 충돌이 이 배치 최대 리스크**였다 — 16px에서
윤곽선만으로 구분되어야 하고, 색·회전 구분은 실패로 본다.

## 이 배치에서 원래 계획을 바꾼 것

1. **#73 Workflow Execute — "재생 삼각형 오버레이"를 폐기하고 재생 삼각형을 종단 노드로 만들었다.**
   라인 아이콘은 넉아웃이 없어 오버레이는 항상 충돌로 보인다(B4·B5 반복 교훈).
   → 미니 노드 2개 → 엘보 커넥터 → 큰 재생 삼각형, 즉 "플로우의 끝이 실행"인 구성.
   nav-workflows(사각 3개 삼각 배치)와도, node-start(삼각형+파동)와도 실루엣이 다르다.
2. **#63 Text Area — "우하단 리사이즈 삼각"을 챔퍼(모서리 절단) 코너로 구현했다.**
   테두리 안쪽에 붙는 작은 채움 삼각형은 스트로크와 0.5px 간격이라 16px에서 테두리에 붙어버린다.
   → 박스 패스 자체의 우하단 모서리를 대각선으로 잘라냈다. 실제 textarea 리사이즈 그립처럼 읽히고
   도형 2개로 끝난다. Input 과는 높이(18 vs 10) + 챔퍼 + 내부 선으로 삼중 구분.
3. **#65 Image — 태양을 속이 찬 점(r1.5 fill)으로.**
   lucide `Image`(외곽선 원 + 단일 산)와 사실상 같아지는 걸 피하고, 12px 하이라키 뱃지에서
   외곽선 원은 뭉개지기 때문. 산은 투피크로 lucide 와 실루엣을 갈랐다.
4. **#66 Dropdown — 셀렉트 박스 내부 라벨 선을 뺐다** (아래 "렌더로 고친 것" 참고).
5. **#70 Event Trigger — 클릭 파동선 2개를 번개 우상단 대각·수평 틱으로.**
   파동선을 번개에 겹치면 충돌로 보이므로 본체와 분리된 우상단 여백에 배치했다.

---

## 붙여넣은 프롬프트

마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 블록(수정된 2~22 사양) + §3 "B4·B5 보강" 전부를 쓰고 아래를 추가했다.

```
[Tier 4 추가 사양 — 앱 빌더 팔레트]
- 팔레트 16px / 하이라키 제목 14px / 하이라키 항목 12px 로 렌더된다. 12px에서도 살아남아야 한다.
- 이 배치는 사각형 모티프가 7개 이상이다(container/input/textarea/image/checkbox/dropdown/button).
  각 사각형에 "그 요소만의 두 번째 표식"을 반드시 넣어라. 표식 없이 비율만 다른 사각형은 실패다.
  · container = 점선 테두리 + 내부 실선 블록   · input = 납작 슬래브 + 캐럿 + 입력 텍스트 선
  · textarea = 큰 박스 + 챔퍼 코너 + 내부 선 2  · image = 산 능선(투피크) + 채움 점 태양
  · dropdown = 상단 슬래브 + 셰브런 + 아래 펼침 선 2  · checkbox = 큰 라운드 + 내부 체크
  · button = 상단 슬래브 + 채움 커서 카이트 + 클릭 틱 2
- 반짝임(스파클)은 쓰지 마라. Sparkles 는 이 파일에서 "AI 어시스턴트" 전용 표식으로 남는다.
- bp-* 4개는 blueprint 로직 노드다. UI 요소(ui-*)와 그림 언어가 달라야 한다:
  화살표/번개/실린더/재생 삼각형 같은 "동작" 어휘를 쓴다.
- bp-get-value(실린더에서 나가는 화살표)와 bp-ui-action(화면으로 들어가는 화살표)는
  거울상이 되면 안 된다(B3 교훈). 질량 배치(도형 좌/우)와 몸체(실린더 vs 사각형)를 갈라라.
- 이미 만든 아이콘과 겹치면 안 된다:
  · node-dynamic-input = 입력 박스 + 커서 + 반짝임 → ui-input 은 반짝임 금지, 전폭 슬래브
  · node-database = 3단 실린더 → bp-get-value 는 밴드 없는 실린더 + 화살표
  · nav-workflows = 사각 노드 3개 삼각 배치 → bp-workflow-execute 는 재생 삼각형이 지배
  · node-poster-generator = 액자+산+별 → ui-image 는 별 없음, 투피크 산 + 채움 점
  · lucide Layers(교체 대상) → ui-hierarchy 는 스택 금지, 인덴트 트리 + 루트 블록

[생성할 아이콘 14개]
60. ui-container.svg (Container) — 점선 테두리 라운드 사각 + 내부 좌상단 실선 작은 사각
61. ui-text.svg (Text) — 세리프 없는 대문자 T, 가로획 18 · 세로획 18
62. ui-input.svg (Input Field) — 납작한 전폭 사각(높이 10) + 왼쪽 캐럿 + 입력된 텍스트 선
63. ui-textarea.svg (Text Area) — 높은 박스(18) + 내부 좌정렬 선 2 + 우하단 챔퍼 코너(리사이즈)
64. ui-button.svg (Button) — 상단 라운드 슬래브 + 우하단 채움 커서 카이트 + 클릭 틱 2
65. ui-image.svg (Image) — 사각형 + 투피크 산 능선 + 좌상단 채움 점 태양
66. ui-dropdown.svg (Dropdown) — 상단 슬래브 + 내부 우측 셰브런 + 아래 펼쳐진 항목 선 2
67. ui-checkbox.svg (Checkbox) — rx4 라운드 사각 + 박스 안에 완결되는 체크
68. ui-divider.svg (Divider) — 가로 실선 + 양끝 세로 마감선 (|——| 형)
69. ui-hierarchy.svg (Hierarchy) — 루트 컴포넌트 블록 + 스파인 엘보 + 인덴트 자식 선 2
70. bp-event-trigger.svg (Event Trigger) — 번개 볼트 + 우상단 방사 틱 2 (이벤트 발화)
71. bp-get-value.svg (Get Value) — 왼쪽 실린더 + 벽을 뚫고 오른쪽으로 나가는 화살표
72. bp-ui-action.svg (UI Action) — 오른쪽 화면 사각형 + 왼쪽에서 들어가 안에서 끝나는 화살표
73. bp-workflow-execute.svg (Workflow Execute) — 미니 노드 2개 → 엘보 커넥터 → 큰 재생 삼각형
```

---

## 실제 생성 결과

QA bbox 판정 14/14 "광학 크기 일치" (warn/bad 0건). 합계 3.9KB.

| 파일 | 도형 | 기하 bbox | 교체된 lucide |
|---|---|---|---|
| `ui-container.svg` | 2 | x 2–22 · y 2–22 | Box *(3중 중복)* |
| `ui-text.svg` | 2 | x 3–21 · y 4–22 | Type |
| `ui-input.svg` | 3 | x 2–22 · y 7–17 | TextCursorInput *(2중)* |
| `ui-textarea.svg` | 2 | x 2–22 · y 3–21 | TextCursorInput *(2중)* |
| `ui-button.svg` | 3 | x 2–22 · y 3–21.5 | MousePointerClick |
| `ui-image.svg` | 3 | x 2–22 · y 3–21 | Image |
| `ui-dropdown.svg` | 3 | x 2–22 · y 2–19 | List |
| `ui-checkbox.svg` | 2 | x 3–21 · y 3–21 | CheckSquare |
| `ui-divider.svg` | 2 | x 2.5–21.5 · y 8.5–15.5 | Minus |
| `ui-hierarchy.svg` | 3 | x 2.5–21.5 · y 2.5–19 | Layers |
| `bp-event-trigger.svg` | 2 | x 5.5–21.5 · y 2–22 | Play `#ef4444` *(실행버튼과 공용)* |
| `bp-get-value.svg` | 3 | x 2–21 · y 2–22 | Database `#10b981` *(2중)* |
| `bp-ui-action.svg` | 3 | x 2–22 · y 3–21 | ArrowRight `#3b82f6` |
| `bp-workflow-execute.svg` | 4 | x 2–22 · y 3–21 | Sparkles *(AI 버튼과 공용)* |

### 렌더해보고 고친 것 (2건)

1. **`bp-ui-action` — 다운로드 아이콘으로 읽혔다.**
   처음엔 모티프 그대로 "화면 사각형 + 위에서 안으로 들어가는 수직 화살표"로 그렸는데,
   기하 확대 렌더에서 보는 순간 lucide `Download`(트레이 + 아래 화살표)와 같은 그림이었다.
   **"사각형 + 아래로 향하는 화살표"는 무조건 다운로드로 읽힌다.**
   → 화면 사각형을 우측에 앉히고(x8–22), 화살표가 왼쪽에서 수평으로 들어와 화면 **안에서**
   화살촉이 끝나게 바꿨다(LogIn 문법). bp-get-value(왼쪽 실린더 + 오른쪽으로 나가는 화살표)와는
   질량 배치가 정반대라 거울상 문제도 없다.
2. **`ui-dropdown` — 셰브런이 오른쪽 벽과 융합하고, 라벨 선까지 넣으니 잡음이 됐다.**
   셰브런 끝(x19.5)과 박스 우벽(x22)의 스트로크 외곽 간격이 0.5px 라 확대 렌더에서
   체크 표시가 모서리에 눌어붙은 것처럼 보였고, 내부 라벨 선(`M6 6h4.5`)까지 겹쳐 지저분했다.
   → 라벨 선 삭제, 셰브런을 왼쪽으로 이동(x13–18)해 벽과 1px 이상 띄웠다.
   빈 셀렉트 박스 + 캐럿 + 아래 펼침 선 2개 — 16px에서 훨씬 깨끗하다.

### 검증에서 확인한 실루엣 구분 (사각형 계열 7종)

그레이스케일 16px 렌더에서: 점선(container) / 캐럿 슬래브(input) / 챔퍼 톨박스(textarea) /
산+점(image) / 셰브런+펼침선(dropdown) / 큰 체크(checkbox) / 커서 카이트(button) —
전부 표식이 달라 혼동 없음. bp 계열도 번개 / 실린더→ / →화면 / 노드▷ 로 구분 명확.

---

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/pages/AppBuilderPage.jsx](../../../frontend/src/pages/AppBuilderPage.jsx) | 팔레트 9 + Hierarchy 제목 1 + 로직 노드 4 + 하이라키 뱃지 9 = **23곳 `<Icon>`**. lucide import 27 → 15종 |

- **하이라키 뱃지(12px)를 5곳 → 9곳으로 늘렸다.** 기존엔 container/text/input/button/image 만
  뱃지가 있고 textarea/dropdown/checkbox/divider 행은 아이콘이 없었다. 팔레트와 같은 의미의
  다른 표면이므로(B6 교훈) 같은 아이콘으로 함께 채웠다.
- 제거된 lucide import 12종: `Box, Type, MousePointerClick, TextCursorInput, Layers,
  Image(ImageIcon), Play, Database, ArrowRight, List, CheckSquare, Minus`
- **남긴 것:** 1016행 `<Sparkles size={16}/> AI 어시스턴트` — AI 기능 표식이라 의도적으로 lucide 유지.
  이제 이 파일에서 Sparkles 는 AI 의미로만 쓰인다. 팔레트 `Code2`(Custom JS Code)는 B8 범위 밖.
  `Workflow`(1540행)·`Coins`(1535행)는 AI 드로어 컨트롤로 남음.

### 검증 결과

- `python3 Documents/build-icon-qa.py` → bbox 판정 14/14 일치, warn/bad 0건.
  16/18/24px 다크·라이트·그레이스케일 렌더 전부 육안 확인 (스크린샷 4장, 아래 경로)
- `npx vite build` 통과. `npx eslint src/pages/AppBuilderPage.jsx` 에러 0
  (경고 26건은 전부 아이콘과 무관한 기존 hooks/unused-vars 경고)
- **실제 AppBuilderPage 를 임시 하니스로 렌더** (실행 중이던 dev 서버 5173 사용,
  `b8-harness.html` + `src/b8Harness.jsx` — AuthProvider + MemoryRouter, 검증 후 삭제):
  - Design 탭: UI Components 팔레트 9개 + Hierarchy 제목 정상
  - 팔레트 9종을 캔버스에 실제 드래그&드롭 → 하이라키 항목 9개 / SVG 뱃지 9개 (12px) 정상
  - Blueprint 모드 → Logic 탭: bp 4종이 지정색(#ef4444/#10b981/#3b82f6)으로 정상,
    **남겨둔 lucide `Code2`(Custom JS Code)와 같은 목록에서 시각 무게 균일 확인**
  - 콘솔 에러 0
- 스크린샷: `/tmp/claude-1000/-home-ubuntu/1bfeb871-95b6-4056-84c0-723093f0178d/scratchpad/b8/`
  (`qa-b8-render-v2.png` `qa-b8-grid-v2.png` `app-design-sidebar.png` `app-logic-sidebar.png` `app-canvas.png`)

---

## 현재 상태

| 항목 | 값 |
|---|---|
| 커스텀 SVG (B8 후) | **65개** (node 37 + nav 14 + ui 14) + B7 병렬 진행분 |
| `TextCursorInput` | **앱에서 완전 제거** (0곳) |
| `Box` | AppBuilderPage 에서 제거. ChatSidebar("앱 연동됨" 뱃지)·TutorialSandbox("연습 캔버스") 2곳 잔존 |
| `Sparkles` | AppBuilderPage 에서 **AI 의미 전용**이 됨 (AI 어시스턴트 버튼 1곳) |

### 남은 확인 사항 — 정직한 평가

- **`Box` 잔존 2곳은 서로 의미가 다르다** (채팅의 "앱 연동됨" vs 튜토리얼 "연습 캔버스").
  둘 다 B8 범위(AppBuilderPage) 밖이라 손대지 않았다. 둘 다 "앱/캔버스" 근처 의미라 심각도는
  낮지만, 완전 해소하려면 별도 배치에서 각각 커스텀하거나 한쪽을 다른 lucide 로 바꿔야 한다.
- `ui-divider` 는 세로 기하폭이 7 뿐이다(가로형 아이콘). Minus(획 1개)보다는 무겁지만
  팔레트에서 여전히 가장 가벼운 항목이다 — 의미상 어쩔 수 없는 부분.
- `ui-text` 는 도형 2개(T자)라 미니멀하다. 팔레트 렌더에서 이웃과 무게가 크게 어긋나지 않아
  그대로 뒀지만, 더 무겁게 하려면 밑줄 추가가 후보다.
- 캔버스(디자인 탭)의 컴포넌트는 실제 HTML 요소로 렌더되므로 아이콘 표면이 아니다.
  `components/UIEngine.jsx` 에 lucide 없음 확인 — 이 페이지의 아이콘 표면은 팔레트+하이라키가 전부다.
