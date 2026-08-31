# B9 배치 — Tier 5 실행 상태 (5개)

`icon-generation-prompts.md` §2 의 #74~78. **이 배치의 존재 이유는 색맹 대응이다** —
성공/실패/실행 중/대기/경고가 색을 빼고 그레이스케일로 렌더돼도 **형태만으로** 구분되어야 한다.
그래서 컨테이너 실루엣을 의도적으로 갈랐다: 원(성공·실패·대기) / 열린 원호(실행 중) / 삼각형(경고).
원 3형제는 내부 글리프(체크 / X / 점 3개)로 다시 갈린다.

## 붙여넣은 프롬프트

마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 블록(2~22 사양) + §3 "B4·B5 보강" 전부에 아래를 추가했다.

```
[Tier 5 추가 사양 — 실행 상태]
- 이 5개는 색을 빼도(그레이스케일) 형태만으로 서로 구분되어야 한다. 색맹 대응이 목적이다.
- 컨테이너를 갈라라: 원 / 원 / 원 / 열린 원호 / 삼각형. 원 3개는 내부 글리프로 구분.
- status-running 은 CSS 회전 애니메이션에 쓰인다. 회전 중심이 정확히 (12,12)여야 하며
  (viewBox 중앙 = 원호의 원 중심), 끝 캡은 라운드. 도형 1개(원호)만 허용 — 다른 요소를
  더하면 회전할 때 함께 돌아 스피너가 아니게 된다.
- status-pending 은 시계 금지. node-schedule(달력+시계바늘)·node-delay(모래시계)·
  nav-scheduler(시계)와 3자 구분이 이미 서 있다 — 바늘 달린 원을 그리는 순간 무너진다.
- status-success 의 체크는 원 안쪽 여백을 넉넉히 남긴다. ui-checkbox(사각+체크)·
  nav-admin(방패+체크)과는 컨테이너 실루엣으로 구분된다.
- status-failed 의 X 는 두 획 교차각 정확히 90° (기울기 ±1).

[생성할 아이콘 5개]
74. status-success.svg — 원 + 안쪽 여백 넉넉한 체크
75. status-failed.svg — 원 + 90° 교차 X
76. status-running.svg — 열린 원호 3/4, 라운드 캡, 중심 (12,12)
77. status-pending.svg — 원 + 수평 점 3개 (시계 아님)
78. status-warning.svg — 라운드 삼각형 + 감탄부호
```

## 실제 생성 결과

QA bbox 판정 5/5 "광학 크기 일치" (warn/bad 0건). 합계 1.2KB.

| 파일 | 도형 | 기하 bbox | 교체된 lucide | 비고 |
|---|---|---|---|---|
| `status-success.svg` | 2 | x 2–22 · y 2–22 | CheckCircle2 (7곳) / CheckCircle (3곳) | 체크 폭 7 (x8.5–15.5), 원 안쪽 여백 ≥4 |
| `status-failed.svg` | 2 | x 2–22 · y 2–22 | XCircle (5곳) | X 획 기울기 정확히 ±1 = 교차각 90° |
| `status-running.svg` | 1 | x 2–22 · y 2–22 | Activity (BEFORE 맵 기준) | `M12 2a10 10 0 1 1-10 10` — 아래 회전 검증 |
| `status-pending.svg` | 2 | x 2–22 · y 2–22 | Clock (다중) | 점 3개 `h.01`, 간격 5 (규약 ≥4) |
| `status-warning.svg` | 3 | x 2.2–21.8 · y 3.3–21 | AlertTriangle (3곳) | lucide 구조를 0.5/0.25 스냅으로 재작도 |

### 사전 지시로 확인한 것 2건 + 렌더로 확인한 것

1. **status-running 의 bbox warn 은 발생하지 않았다.** 작업 지시에는 "원호라 최대 변이 18을
   살짝 못 넘을 수 있다"고 했지만, 원호 시작점을 축 극점(상단 12,2)에 두고 270°를 돌리면
   경로가 우(22,12)·하(12,22)·좌(2,12) 극점을 전부 지나므로 getBBox 가 정확히 20×20 으로
   찍힌다. warn 자체가 안 뜨는 구성이라 "warn 이어도 지름 20이면 통과" 규칙을 쓸 일이 없었다.
2. **회전 중심 검증 (playwright)** — 0/90/180/270° 회전본 4개를 색만 바꿔 오버레이:
   완전한 단일 링으로 합쳐짐(이중 링·흔들림 없음). `getBoundingClientRect` 중심 좌표도
   4개 전부 동일. 원호의 원 중심(12,12) = viewBox 중앙이므로 HTML `transform: rotate` 의
   기본 origin(50% 50%)으로 그대로 돌려도 흔들리지 않는다 → 스크린샷 `running-rotation.png`.
3. **그레이스케일 5종 상호 구분** — QA 표 + 별도 계열 비교 렌더(`family-compare.png`)에서
   16px 그레이스케일로 확인: 원+체크 / 원+X / 원+점3 / 열린 원호 / 삼각형+! 전부 즉별 가능.
   `nav-intro`(원+i)와도 나란히 비교 — pending 의 점은 수평, intro 의 i 는 수직이라 안 섞인다.
4. **pending 이 시계로 읽히지 않는지** — node-schedule / node-delay / nav-scheduler 와
   4자 비교 렌더로 확인. 바늘이 없는 점 3개는 "진행 대기(...)"로 읽힌다.
   ※ 결과적으로 lucide `CircleEllipsis` 와 사실상 같은 그림이다. §3 "lucide 와 같아지면 만들
   가치가 없다" 규칙에 걸리지만, 모티프가 §2 표에 고정돼 있고 앱에서 CircleEllipsis 를 쓰는
   곳이 없어(충돌 0) 세트 완결성을 우선했다.
5. **체크 계열 교차 배치 구분** — status-success(원) vs ui-checkbox(rx4 사각) vs
   nav-admin(방패) vs node-human-approval(사람+체크): 컨테이너 실루엣이 전부 달라 혼동 없음.
6. **status-warning 좌표 스냅** — 라운드 삼각형은 모서리 접선 조건 때문에 완전한 0.5 스냅이
   불가능해서 밑변 아크 변위만 0.25 단위(±1.75)를 허용했다(마스터 사양의 금지 대상은
   3.7231 류 노이즈 좌표). 168px 확대 렌더에서 모서리 꺾임(kink) 없음 확인.

## 앱 적용 — "실행 상태 의미의 표면만"

교체 기준: **상태(성공/실패/경고/대기/실행 중)를 뜻하는 표면만** 커스텀으로 바꾸고,
타임스탬프·소요시간·활동 지표 같은 메타데이터 라벨은 lucide 를 유지했다 (§1 원칙).

| 파일 | 위치 | before → after | 판단 |
|---|---|---|---|
| [pages/ProjectRunsPage.jsx](../../../frontend/src/pages/ProjectRunsPage.jsx) | 실행 목록 170·172 / 스텝 254·256 | CheckCircle2/XCircle → `status-success`/`status-failed` | 실행·스텝 상태 뱃지 |
| 〃 | 234 "Executed At" | **Clock 유지** | 실행 시각 = 타임스탬프 메타데이터 |
| [pages/EvaluationPage.jsx](../../../frontend/src/pages/EvaluationPage.jsx) | 요약 카드 187 / PASS 217 / FAIL 219 | CheckCircle(주의: 2 아님)/XCircle → `status-success`/`status-failed` | 통과·실패 상태 |
| 〃 | 114 페이지 제목 | **Activity 유지** | "성능 평가" 페이지 정체성 아이콘. 실행 상태가 아니고, 정적 자리에 원호(running)를 놓으면 로딩으로 오독된다 |
| 〃 | 192·246 응답 속도 | **Clock 유지** | 소요시간 메타데이터 |
| [pages/AdminPage.jsx](../../../frontend/src/pages/AdminPage.jsx) | 180 User acceptance / 185 Dry-run pass | CheckCircle2 → `status-success` | 통과·수락률 = 성공 지표 |
| 〃 | 190 Fallback rate | AlertTriangle → `status-warning` | 폴백은 경고성 지표 |
| 〃 | 175 Generation success | **Activity 유지** | 처리량·활동 지표 라벨. success 로 바꾸면 4칸 중 3칸이 같은 아이콘이 돼 스캔성이 죽는다 |
| [pages/AppRunnerPage.jsx](../../../frontend/src/pages/AppRunnerPage.jsx) | 131 전면 오류(48px) / 217 오류 박스 | AlertTriangle → `status-failed` | 둘 다 빨강(#ef4444) 실패 표면인데 형태만 경고 삼각형이었다 — **색과 형태의 의미 불일치를 바로잡음** (이 배치의 목적 그대로) |
| 〃 | 179 "지우기" | **XCircle 유지** | 입력 클리어 컨트롤 = UI chrome, 상태 아님 |
| 〃 | 209 소요 안내 | **Clock 유지** | "10~30초 소요" 시간 메타데이터. 실행 중 표시는 기존 CSS `.spinner-small` 이 담당 |
| [pages/TutorialPage.jsx](../../../frontend/src/pages/TutorialPage.jsx) | 213 완료 배지 / 228 상태 패널 | CheckCircle2 → `status-success` | 완료 상태. 파일 내 지역변수 `Icon`(track.icon)과 충돌해 `Icon as StatusIcon` 으로 임포트 |
| [SiteFeedbackWidget.jsx](../../../frontend/src/SiteFeedbackWidget.jsx) | 132 버튼 / 159 모달(40px) | CheckCircle2 → `status-success` | 제출 완료 상태 |
| [CustomConfirm.jsx](../../../frontend/src/CustomConfirm.jsx) | 33 (32px, #fbbf24) | AlertTriangle → `status-warning` | 파괴적 확인 경고 — lucide import 0이 됨 |
| [pages/WebhookManagerPage.jsx](../../../frontend/src/pages/WebhookManagerPage.jsx) | 179 "최근 수신:" | **Activity 유지 (무수정)** | 최근 수신 시각 = 메타데이터 라벨이지 수신 상태 뱃지가 아니다. 남은 Activity 3곳(평가 제목·어드민 지표·여기)이 전부 "활동/지표" 한 의미로 수렴 → §1 "같은 의미는 lucide 유지" |

미사용이 된 lucide import 정리: `CheckCircle2` `CheckCircle` `XCircle`(상태 용례) `AlertTriangle` —
7개 파일에서 제거. `status-running` 은 **이번 배치에 적용 표면이 없다**: 범위 내에 lucide 기반
스피너가 없었다 (AppRunner 는 CSS `.spinner-small`, WebhookManager 의 회전은 lucide `RefreshCw`
+ `.spinning` = "새로고침 동작"이지 실행 상태가 아님). EditorPage 캔버스의 노드 실행 상태 등
후속 표면을 위해 세트로 만들어 두었다 — 쓸 때 기존 회전 CSS 클래스(`animation: spin`)를 svg 에
그대로 붙이면 된다 (회전 중심 검증 완료).

### 검증 결과

- `python3 Documents/build-icon-qa.py` → 79개 중 B9 5개 bbox 판정 전부 "광학 크기 일치"
- **회전 중심**: 4방향 오버레이 + rect 중심 좌표 일치 (위 2번 항목)
- **실제 페이지 렌더** (실행 중이던 dev 서버 5173 재사용 — 죽이지 않음. 임시 하니스
  `b9-harness.html` + `src/b9Harness.jsx`, playwright 로 `/api/**` 목 응답, 검증 후 삭제):
  - ProjectRunsPage: 실행 목록 성공/실패 + 스텝 타임라인 (스텝 펼침 포함)
  - EvaluationPage: SSE 목으로 실제 평가 플로우 구동 → 요약 카드 + PASS/FAIL 뱃지
  - AppRunnerPage: 실행 오류 박스(20px) + 전면 오류 상태(48px)
  - AdminPage: LLM 지표 4카드 — 남긴 lucide Activity 와 시각 무게 균일 확인
  - TutorialPage: 완료 배지(15px) + 상태 패널(22px) — 진도 localStorage `version: 2` 필요
  - CustomConfirm 경고 모달(32px) + SiteFeedbackWidget 제출 완료 버튼(18px)·모달(40px)
  - 콘솔 에러 0 (의도한 목 500/404 제외), `[Icon]` 미등록 경고 0
- `npx vite build` 통과. eslint 에러 0 (경고는 이 프로젝트 eslint 가 JSX 사용을 인식하지
  못하는 기존 설정 문제 — 손 안 댄 파일도 동일 패턴)
- 스크린샷: `scratchpad/b9/` — `qa-b9-rows.png` `qa-b9-grid.png` `family-compare.png`
  `running-rotation.png` `app-runs.png` `app-eval.png` `app-runner-errorbox.png`
  `app-runner-errorstate.png` `app-admin-llm.png` `app-tutorial.png`
  `app-widgets-confirm.png` `app-widgets-feedback.png`

## 현재 상태

| 항목 | 값 |
|---|---|
| 커스텀 SVG (B9 후) | **79개** (node 37 + nav 14 + provider 9 + ui 14 + status 5), status 5개 = 1.2KB |
| 상태 의미의 CheckCircle2/CheckCircle/XCircle/AlertTriangle | B9 범위 7파일에서 제거 |

### 남은 상태 표면 — 정직한 평가 (전부 B9 범위 밖, 보고만)

- [pages/AppBuilderPage.jsx:1626](../../../frontend/src/pages/AppBuilderPage.jsx) — `CheckCircle2`
  "배포 완료" 모달. 의미상 `status-success` 감이지만 B8 파일(git 수정 상태)이라 건드리지 않았다.
- [CustomAlert.jsx](../../../frontend/src/CustomAlert.jsx) — `CheckCircle`(성공 알럿)/`AlertCircle`(오류 알럿).
  CustomConfirm 의 형제 컴포넌트. `status-success`/`status-failed` 후속 교체 후보 1순위.
- [components/AdvancedTutorialLab.jsx](../../../frontend/src/components/AdvancedTutorialLab.jsx) —
  `AlertTriangle` 2곳 (warning tone 피드백) → `status-warning` 후보.
- [pages/StatisticsPage.jsx](../../../frontend/src/pages/StatisticsPage.jsx) — `CheckCircle2`("실행
  성공률")·`Activity` 있음. **오케스트레이터 지시로 불가침** (대규모 리워크 진행 중인 파일.
  참고: 지시문에는 "워킹 트리에서 삭제된 상태"라 했으나 실제로는 수정 상태로 존재한다 —
  어느 쪽이든 손대지 않았다).
- [pages/SettingsPage.jsx:198](../../../frontend/src/pages/SettingsPage.jsx) — `AlertTriangle`
  회원 탈퇴. 지시대로 잔존 (무관한 미커밋 변경 보유 파일).
- lucide `Activity` 는 3곳(평가 제목·어드민 Generation success·웹훅 최근 수신)에 남았고
  전부 "활동/지표" 의미로 동일 — 충돌 아님.
