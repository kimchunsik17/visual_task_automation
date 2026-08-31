# 워크플로우 에디터 단축키·편의 기능 조사 및 우선순위

작성일: 2026-08-28  
상태: 조사 완료 — Slice 1~5 구현 완료 (그룹·sub-workflow는 아래 이관 기록 참고)

> 구현 상태 업데이트 (2026-08-28): Slice 1 구현 완료. 통합 그래프 히스토리, 중앙 명령
> 레지스트리, 저장·복사·잘라내기·붙여넣기·복제·전체 선택 단축키, 단축키 도움말과 dirty
> 표시를 에디터에 반영했다.

> 구현 상태 업데이트 (2026-08-28): Slice 2 구현 완료. 중앙 선택 모델, 선택 플로팅 툴바,
> 노드·선택·연결선·캔버스별 우클릭 메뉴, 6방향 정렬과 가로·세로 균등 간격, 한 번에
> 되돌릴 수 있는 Alt/Option 드래그 복제, 전체·선택 화면 맞춤과 명령 팔레트를 반영했다.
> 구현 상태 업데이트 (2026-08-28): Slice 3 구현 완료. 캔버스 더블클릭 빠른 추가,
> 연결을 빈 공간에 놓아 노드 생성·자동 연결, 연결선 중간 삽입, 역할이 같은 노드 교체와
> 설정 변경 사전 확인, 명령 팔레트 노드 검색, 최근 사용·즐겨찾기 정렬을 반영했다.
> 포트 타입 기반 호환성 추천은 Node Definition 포트 계약 이후로 유지한다.

> 구현 상태 업데이트 (2026-08-28): Slice 5 구현 완료, **Slice 4는 부분 구현**.
> - **Slice 4 (부분)**: 노드 Inspector(최근 입력/출력/오류, raw 복사), 진입점 샘플 입력
>   (브라우저 저장), "이 노드부터 실행"(승인 재개의 진입점 컴파일 재사용 — 상류 재실행 없음),
>   dry-run 기반 문제 패널(클릭 → 노드 포커스). Artifact 미리보기는 NodeResult/ArtifactRef
>   계약(INCOMPLETE_NODE_STRUCTURE_REVIEW P1) 이후로 유지.
> - **Slice 4 미구현분 (2026-08-29 재점검에서 확인)**: ① **완료 기준("외부 API를 실제 호출하지
>   않고 한 노드의 입력부터 출력까지 검증")이 성립하지 않는다** — "이 노드부터 실행"은
>   `/api/execute` 실경로라 실제 자격증명으로 외부 호출이 나가고, Mock 탭은 진입점이 트리거로
>   고정돼(`mock_service.ENTRY_NODE_TYPES`) 중간 노드에서 시작할 수 없다. 두 축이 만나는 지점이
>   없다. ② 그래서 side-effect 노드(discord/email/kakao)를 "이 노드부터 실행"하면 §7.1·§7.4의
>   "기본은 mock, 실제 외부 쓰기는 별도 확인"과 달리 확인 없이 실제로 발송된다. ③ Inspector 에
>   Logs 탭·key/value 검색·JSON tree·다운로드가 없다. ④ **"샘플 데이터 고정"은 §7.3 이 요구한
>   노드 출력 fixture 가 아니라 진입점 샘플 입력이다** — 하류를 반복 테스트할 때 상류 외부 API
>   재호출을 막지 못하고, 고정 표시·redaction·stale 경고도 없다. ⑤ 범위 실행은 "여기부터"만
>   있고 "이 노드만"·"여기까지"·"이전 실행 데이터로 다시 실행"이 없다. ⑥ `Alt+Enter` 단축키와
>   결과 badge → Inspector 진입, "다시 테스트 필요" 표시가 없다.
>
> 구현 상태 업데이트 (2026-08-29): **Slice 4 완료** — 위 ①~⑥을 구현했다. 완료 기준이 성립한다.
> - **범위 실행 × 목업(①)**: `compile_workflow` 가 `stop_node_id`(하류 간선 제거)·`scope_node_ids`
>   (그래프 축소)를 받고, `mock_service.run` 이 `start_node_id` 로 임의 노드를 진입점 삼아 목업
>   컴파일한다. 이제 "이 노드만 목업"이 외부 요청 0건으로 입력→출력을 보여준다. 생성기는 손대지
>   않았다 — 순회할 간선 자체를 줄이는 방식이라 노드가 늘어도 조건이 흩어지지 않는다.
> - **외부 전송 확인(②)**: 실제 실행 전에 하류의 외부 전송 노드를 모아 이름과 함께 확인을 받는다
>   (`nodeTestFixtures.downstreamExternalNodes` — 정의의 `sideEffect`/`sideEffectByMode` 와 백엔드
>   `dry_run.SIDE_EFFECT_NODE_TYPES` 를 같은 근거로 쓴다). 컨텍스트 메뉴도 목업이 먼저 온다.
> - **Inspector(③)**: 입력·출력·로그·Raw 탭, 줄 단위 key/value 검색, 복사·다운로드, 오류 카드
>   (ADR-0016), 외부 전송 배지(`components/NodeInspector.jsx`).
> - **출력 고정(④)**: 노드 출력을 fixture 로 굳혀 그 노드(와 상류)를 실행하지 않고 하류만 반복
>   테스트한다. 저장 전 시크릿 redaction, 노드 설정 변경 시 stale 경고, 노드 배지의 "고정" 표시,
>   실행 로그의 `pinned` 플래그까지 포함(`nodeTestFixtures.js`).
> - **범위 실행 전체(⑤)**: 이 노드만 / 여기부터 / 여기까지 / 선택 영역만 / 직전 입력으로 다시.
> - **진입 경로(⑥)**: `Alt+Enter`(선택 노드 목업 테스트), 노드 헤더의 결과 배지 클릭 → Inspector.
> - **검증**: 백엔드 `test_editor_execution.py` 11종(범위 실행·고정 출력·API E2E)과
>   `test_mock_service.py` 의 범위×목업 5종, 프론트 `nodeTestFixtures.test.js` 7종. 전체 백엔드
>   567개 통과, 프론트 47종 통과, 빌드 통과.
> - **남은 것**: Artifact 미리보기(NodeResult/ArtifactRef 계약 이후 — 우선 백로그 20), JSON tree
>   접기·펼치기와 upstream field 추적(현재는 줄 검색으로 대체), "설정이 바뀐 노드 = 다시 테스트
>   필요" 배지(고정 출력에는 stale 경고가 있으나 실행 결과에는 아직 없다).
> - **Slice 5**: 메모(캔버스 주석 — 실행·검증·컴파일에서 제외), 위치 잠금, 명령 팔레트의
>   캔버스 노드 검색·이동(Navigator v1), 부분 정렬은 Slice 2에서 완료.
> - **이관**: 그룹(접기)은 loopNode의 parentNode 컨테이너 의미론·AI 생성과의 조정이 필요해
>   Node Definition 포트 계약과 함께 재설계한다. 재사용 블록·sub-workflow는 백엔드 실행
>   모델이 필요하므로 로드맵 Wave 2(Subworkflow 노드)로 이관한다.

> 검증 (2026-08-28): Slice 1~3 코드 리뷰·테스트 완료. 발견된 결함 3건을 수정했다 —
> ① 클립보드 시크릿 마스킹 패턴에 실제 노드 키(botToken·connectionString·webhookUrl·
> smtp_credentials·secretKey) 누락 → 보강, ② 안전한 API 센터 reference까지 마스킹되던
> 오탐 → 백엔드(redact_payload_secrets)와 같은 규칙으로 보존, ③ 승인 대기 모달(ADR-0015)이
> 열린 동안 캔버스 단축키가 동작하던 충돌 → 다른 모달과 같은 규칙으로 차단.

## 1. 결론

조사 당시 에디터는 실행·목업·자동 정렬·노드 검색·다중 선택 같은 기본 기능은 갖추고 있지만, 반복 편집을
빠르게 만드는 복사·붙여넣기, 복제, 전체 선택, 저장 단축키와 노드 단위 테스트가 부족하다.

추가 순서는 다음이 적절하다.

1. **모든 편집을 되돌릴 수 있는 통합 히스토리**
2. **명령 레지스트리와 명령 팔레트**
3. **복사·붙여넣기·복제·저장 등 표준 단축키**
4. **선택 항목 툴바와 우클릭 메뉴**
5. **빠른 노드 추가·연결선 중간 삽입·노드 교체**
6. **노드 단위 목업 실행과 입출력 검사**
7. **그룹·메모·부분 정렬과 큰 그래프 탐색 기능**

단축키를 개별 `keydown` listener로 계속 추가하면 메뉴, 모바일 UI와 실제 동작이 어긋난다. 모든
기능을 `EditorCommand`로 한 번 정의하고 단축키·메뉴·명령 팔레트·컨텍스트 메뉴가 같은 명령을
실행하도록 만드는 것이 핵심이다.

## 2. 현재 구현 상태

### 이미 있는 기능

| 기능 | 현재 동작 | 평가 |
| --- | --- | --- |
| 삭제 | 선택 후 `Backspace` 또는 `Delete` | 유지 |
| 되돌리기/다시 실행 | `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, `Ctrl+Y` | AI 변경 스냅샷에만 적용되어 불완전 |
| 다중 선택 | 데스크톱 드래그 선택, React Flow 기본 보조키 선택 | 존재하지만 안내 부족 |
| 캔버스 이동·확대 | 휠 확대, 스크롤 이동, Controls와 MiniMap | 데스크톱 중심 |
| 자동 정렬 | 더보기 메뉴에서 전체 그래프를 LR dagre 정렬 | 부분 선택·미리보기 없음 |
| 펼치기/접기 | 모든 노드 일괄 펼치기·접기 | 선택 노드만 처리하는 기능 없음 |
| 노드 검색 | 좌측 팔레트 검색 | 키보드만으로 빠른 삽입하기 어려움 |
| 연결선 삭제 | 연결선 우클릭 후 확인 | 우클릭 메뉴가 삭제 하나뿐 |
| 실행 | 상단 실제 실행 버튼 | 단축키 없음 |
| 목업 | 상단 목업 패널 진입 | 노드 단위 테스트 없음 |
| 저장 | 상단 저장 버튼, 실행·배포 전 저장 | `Ctrl/Cmd+S`, 변경 상태 표시 없음 |

### 현재 되돌리기의 중요한 한계

`EditorPage`의 히스토리는 AI 챗봇이 그래프를 변경할 때만 스냅샷을 쌓는다. 사용자가 직접 수행한
다음 변경은 표준적인 `Ctrl/Cmd+Z` 대상으로 보장되지 않는다.

- 노드 추가·삭제·이동
- 연결 추가·삭제
- 노드 필드 변경
- 자동 정렬
- 템플릿 불러오기

따라서 복사·붙여넣기와 빠른 삽입보다 통합 히스토리를 먼저 구현해야 한다.

## 3. 유사 편집기 조사

### Make

Make의 공식 단축키에는 저장, 모듈 복사·붙여넣기, 한 번 실행, 기존 데이터로 실행, 박스 선택,
자동 정렬과 전체 undo/redo가 포함된다. 특히 undo/redo는 모듈 위치뿐 아니라 연결, route와 설정
필드 변경까지 되돌린다.

제품에 가져올 점:

- `Ctrl/Cmd+S` 저장
- 선택 모듈 복사·붙여넣기
- 전체 실행과 기존 데이터 실행 분리
- 선택 박스와 자동 정렬 단축키
- 설정 필드까지 포함하는 통합 undo

출처: [Make keyboard shortcuts](https://help.make.com/keyboard-shortcuts),
[Make undo/redo and output inspection](https://help.make.com/module-output-search-raw-data-view-undo-and-redo-gemini-flash)

### n8n

n8n은 선택한 노드와 연결을 복사해 같은 또는 다른 워크플로우에 붙여넣을 수 있다. 노드 메뉴에는
단계 실행, 비활성화, 데이터 고정, 복사, 복제, 정렬, sub-workflow 변환과 전체 선택이 있다. 여러
노드는 그룹화할 수 있고 그룹 설명도 함께 복사된다.

제품에 가져올 점:

- 부분 그래프를 연결과 함께 복사
- 노드 단위 실행·비활성화·데이터 고정
- 선택 영역을 sub-workflow 또는 재사용 블록으로 전환
- 그룹과 설명을 그래프의 일부로 저장

출처: [n8n export and copy/paste](https://docs.n8n.io/build/manage-workflows/export-and-import),
[n8n work with nodes](https://docs.n8n.io/build/understand-workflows/workflow-components/work-with-nodes),
[n8n canvas groups](https://docs.n8n.io/build/understand-workflows/workflow-components/canvas-groups)

### Zapier

Zapier Canvas는 확대·축소, 화면 맞춤, 전체 레이아웃 정리, undo/redo와 삭제 단축키를 안내 화면에서
보여준다. 단계는 개별 테스트할 수 있고, 테스트 데이터는 후속 단계 필드 매핑에 사용된다. 단계나
경로를 복사해 아래에 붙이거나 선택 항목을 교체할 수도 있다.

제품에 가져올 점:

- 단축키 도움말을 제품 안에서 바로 제공
- 개별 단계 테스트와 후속 데이터 매핑
- `아래에 붙여넣기`와 `선택 노드 교체` 구분
- 필수 단계의 미테스트 상태 표시

출처: [Zapier Canvas shortcuts](https://help.zapier.com/hc/en-us/articles/30520228992525-Use-keyboard-shortcuts-on-Zapier-Canvas),
[Zapier step testing](https://help.zapier.com/hc/en-us/articles/18811411817741-Test-Zap-steps),
[Zapier copy/paste steps](https://help.zapier.com/hc/en-us/articles/13007162721293-Copy-and-paste-triggers-and-actions-across-Zap-workflows)

### Figma/FigJam

Figma 계열 편집기는 명령 팔레트, 복제, Alt/Option 드래그 복제, 그룹, 전체 선택, 정렬·간격 맞춤과
선택 항목 중심 작업을 제공한다. 명령 팔레트는 단축키가 없는 기능까지 검색해 실행할 수 있어 기능이
늘어날수록 메뉴 탐색 비용을 낮춘다.

제품에 가져올 점:

- 검색 가능한 명령 팔레트
- 선택 직후 나타나는 작은 작업 툴바
- Alt/Option 드래그 복제
- 선택 항목 정렬·간격 맞춤
- 최근 사용 명령 노출

출처: [Figma copy and duplicate](https://help.figma.com/hc/en-us/articles/4409078832791-Copy-and-paste-objects),
[FigJam selection and tidy](https://help.figma.com/hc/en-us/articles/1500004292221-Select-move-and-order-objects-in-FigJam),
[FigJam quick actions](https://help.figma.com/hc/en-us/articles/14477051168791-Use-FigJam-with-a-screen-reader)

### React Flow에서 활용 가능한 기반

현재 사용하는 `@xyflow/react`는 선택 변경, 선택 컨텍스트 메뉴, 연결 재지정, 다중 선택, 삭제 키,
Space 이동과 키보드 접근성 기능을 제공한다. 선택 노드의 화살표 이동도 기본 접근성 범위에 있으므로
새로 만들기 전에 현재 버전에서 동작을 검증하고 도움말에 노출하는 편이 낫다.

출처: [React Flow component API](https://reactflow.dev/api-reference/react-flow),
[React Flow interactivity](https://reactflow.dev/learn/concepts/adding-interactivity)

## 4. P0 — 먼저 추가할 기반과 표준 편집 기능

### 4.1 통합 undo/redo

AI 변경 전용 `chatHistory`를 모든 그래프 변경을 기록하는 `editorHistory`로 확장한다.

기록 단위:

- 노드·연결 추가와 삭제
- 노드 이동과 다중 이동
- 필드 값 변경
- 자동 정렬
- 붙여넣기·복제·노드 교체
- AI 수정 한 턴
- 템플릿 불러오기

노드 드래그 중 매 프레임과 텍스트 입력의 매 글자를 기록하면 안 된다.

- 이동은 `onNodeDragStop`에서 한 번 기록
- 필드 입력은 focus 시작값과 blur 최종값을 한 transaction으로 기록
- 연속 입력은 500~800ms 단위로 병합
- 자동 정렬과 붙여넣기는 전체를 한 transaction으로 기록
- 실행 상태, 선택 여부, viewport와 AI 하이라이트는 히스토리에서 제외

메뉴에는 단순히 “되돌리기”가 아니라 `노드 3개 붙여넣기 취소`, `자동 정렬 취소`처럼 다음 동작명을
표시한다.

### 4.2 중앙 명령 레지스트리

```text
EditorCommand
  id
  label
  description
  category
  shortcuts: { mac, windows }
  when(context)
  execute(context)
  danger
```

`when`에는 입력창 포커스, 읽기 전용 여부, 선택 노드 수, 실행 중 여부, 소유자 권한과 모바일 여부를
포함한다. 메뉴와 단축키가 같은 `execute()`를 호출해야 한다.

필수 가드:

- `input`, `textarea`, `select`, contenteditable과 코드 편집기에서는 텍스트 단축키 우선
- IME 조합 중 `event.isComposing`이면 실행하지 않음
- 모달이 열렸으면 해당 모달 scope만 활성화
- 실제 실행·배포·라이브 전환은 키 반복을 막고 위험 확인 적용
- Mac의 `Meta`, Windows/Linux의 `Control`을 동일한 `Mod`로 추상화

### 4.3 복사·잘라내기·붙여넣기·복제

복사 범위:

- 선택 노드
- 선택 노드 사이의 내부 연결
- 그룹·메모
- 노드 설정 중 공유 가능한 값

붙여넣기 규칙:

1. 새 node/edge ID를 만들고 내부 연결 ID를 재매핑한다.
2. 마우스 위치 또는 viewport 중앙을 기준으로 배치한다.
3. 반복 붙여넣기는 일정 간격으로 이동한다.
4. 전체 붙여넣기를 하나의 undo transaction으로 기록한다.
5. 실행 상태·콜백·선택 상태·AI 하이라이트는 제거한다.
6. credential 원문과 서버 파일 경로는 복사하지 않고 reference 또는 `연결 필요` 상태로 바꾼다.
7. 다른 워크플로우로 붙여넣으면 접근할 수 없는 credential과 Artifact를 명확히 표시한다.

브라우저 Clipboard API가 막힌 환경을 위해 세션 내부 clipboard fallback도 둔다.

### 4.4 명령 팔레트와 단축키 도움말

`Ctrl/Cmd+K`로 명령 팔레트를 열고 노드 추가와 편집 명령을 함께 검색한다.

예시:

```text
노드 추가: HTTP Request
선택 노드 복제
선택 영역 자동 정렬
워크플로우 목업 실행
누락된 설정 보기
모든 노드 접기
실행 기록 열기
```

`?`는 현재 scope에서 사용 가능한 단축키 표를 연다. 입력창에서는 동작하지 않는다. 메뉴 버튼의
tooltip에도 해당 단축키를 병기한다.

## 5. 권장 기본 단축키 맵

`Mod`는 macOS의 `Cmd`, Windows/Linux의 `Ctrl`이다.

| 범주 | 기능 | 권장 단축키 | 우선순위 | 비고 |
| --- | --- | --- | ---: | --- |
| 파일 | 저장 | `Mod+S` | P0 | 브라우저 저장 동작 차단 |
| 편집 | 되돌리기 | `Mod+Z` | P0 | 모든 편집 대상 |
| 편집 | 다시 실행 | `Mod+Shift+Z`, `Ctrl+Y` | P0 | 기존 키 유지 |
| 편집 | 복사 | `Mod+C` | P0 | 선택 그래프 직렬화 |
| 편집 | 잘라내기 | `Mod+X` | P0 | 복사 성공 후 삭제 |
| 편집 | 붙여넣기 | `Mod+V` | P0 | 새 ID와 위치 적용 |
| 편집 | 복제 | `Mod+D` | P0 | 선택 옆에 즉시 복제 |
| 선택 | 전체 선택 | `Mod+A` | P0 | canvas scope에서만 |
| 선택 | 선택 해제 | `Esc` | P0 | 열린 경량 UI부터 닫기 |
| 선택 | 삭제 | `Backspace`, `Delete` | 기존 | 입력 포커스 제외 |
| 탐색 | 명령 팔레트 | `Mod+K` | P0 | 명령·노드 통합 검색 |
| 도움말 | 단축키 보기 | `?` | P0 | 현재 scope 기준 |
| 실행 | 안전 목업 실행 | `Mod+Enter` | P1 | 외부 side effect 없음 |
| 실행 | 실제 전체 실행 | `Mod+Shift+Enter` | P1 | 고위험 노드 확인 필요 |
| 실행 | 선택 노드 테스트 | `Alt/Option+Enter` | P1 | 기본은 mock |
| 화면 | 확대/축소 | `+`, `-` | P1 | 키보드 레이아웃 고려 |
| 화면 | 전체 맞춤 | `Shift+1` | P1 | Figma 계열 관례 |
| 화면 | 선택 영역 맞춤 | `Shift+2` | P1 | 선택이 없으면 비활성 |
| 배치 | 자동 정렬 | `Shift+A` | P1 | 선택이 있으면 선택만 |
| 배치 | 미세 이동 | `Arrow` | P1 | React Flow 기본 동작 검증 |
| 배치 | 큰 폭 이동 | `Shift+Arrow` | P1 | 10px 단위 |
| 배치 | 드래그 복제 | `Alt/Option+Drag` | P1 | 전체를 한 undo로 기록 |
| 그룹 | 그룹화 | `Mod+G` | P2 | 연결된 선택 우선 |
| 그룹 | 그룹 해제 | `Mod+Shift+G` | P2 |  |

실제 실행은 되돌릴 수 없는 외부 동작을 포함할 수 있으므로 `Mod+Enter`를 실제 실행에 바로 연결하지
않는다. 기본 단축키는 목업 실행이고 실제 실행은 Shift가 추가된 chord로 분리한다.

## 6. P1 — 체감 효과가 큰 캔버스 편의 기능

### 6.1 선택 항목 플로팅 툴바

하나 이상의 노드를 선택하면 선택 영역 위에 작은 툴바를 표시한다.

```text
테스트 | 복제 | 정렬 | 그룹 | 비활성화 | 더보기 | 삭제
```

다중 선택이면 `왼쪽/가운데/오른쪽 정렬`, `위/가운데/아래 정렬`, `가로/세로 간격 동일`을 제공한다.
모바일에서는 같은 기능을 하단 action sheet로 표시한다.

### 6.2 우클릭 메뉴 확장

현재 연결선 삭제 하나뿐인 우클릭을 scope별 메뉴로 확장한다.

**노드**

- 열기/접기
- 테스트
- 복제·복사·잘라내기
- 이름 변경
- 비활성화/우회
- 앞에서 실행·여기까지 실행
- 재사용 블록으로 저장
- 삭제

**연결선**

- 연결 재지정
- 중간에 노드 삽입
- 조건/라벨 편집
- 삭제

**빈 캔버스**

- 노드 추가
- 붙여넣기
- 전체 맞춤
- 자동 정렬
- 메모 추가
- 모두 펼치기/접기

### 6.3 빠른 노드 추가

- 캔버스 더블클릭 또는 명령 팔레트에서 노드 검색
- source handle 연결을 빈 공간에 놓으면 노드 검색창을 열고 선택 노드를 자동 연결
- 연결선의 `+` 버튼으로 중간 노드 삽입
- 팔레트 검색 결과는 키보드 위·아래와 Enter로 배치
- 최근 사용·즐겨찾기 노드를 검색 상단에 표시

초기 버전은 모든 노드를 보여주고, Node Definition의 입출력 타입 이전이 진행되면 현재 연결과
호환되는 노드를 먼저 추천한다.

### 6.4 노드 교체

선택 노드를 다른 타입으로 바꾸되 가능한 연결과 공통 필드는 보존한다.

예:

- Discord 발송 → Telegram 발송
- OpenAI 모델 → 다른 LLM 설정
- HTTP Request → 공식 Connector

교체 전에 보존·삭제될 필드를 preview하고, 전체 교체를 한 번에 되돌릴 수 있어야 한다. trigger와
action처럼 포트 계약이 다른 타입은 자동 교체하지 않는다.

### 6.5 부분 정렬과 위치 잠금

현재 자동 정렬은 전체 그래프의 수동 배치를 덮어쓴다. 다음을 추가한다.

- 선택 노드/선택 branch만 정렬
- 노드 위치 잠금
- 정렬 제외 그룹
- smart guide와 선택적 snap grid
- 정렬 결과 preview 후 적용
- 적용 직후 한 번에 undo

### 6.6 변경 상태와 자동 복구

- 제목 옆에 `저장됨`, `저장 중`, `저장 안 됨`, `충돌` 상태 표시
- 브라우저 종료 전 저장되지 않은 변경 경고
- 짧은 주기의 local draft 저장
- 서버 autosave는 revision이 과도하게 쌓이지 않도록 idle 구간을 합쳐 저장
- 충돌 시 로컬 변경과 서버 revision 비교 진입점 제공

## 7. P1~P2 — 실행·디버깅 편의 기능

### 7.1 선택 노드 테스트

노드 위의 작은 실행 버튼 또는 `Alt/Option+Enter`로 한 단계만 테스트한다.

- 기본은 mock/dry-run
- 실제 외부 쓰기는 별도 확인
- 필요한 upstream 값이 없으면 샘플 입력 편집기를 표시
- 최근 성공 입력을 다시 사용할 수 있게 함
- 설정이 바뀐 노드는 `다시 테스트 필요` 상태 표시

### 7.2 입력·출력 데이터 Inspector

실행 후 노드 위 결과 badge를 클릭하면 우측 Inspector에서 다음을 보여준다.

```text
Input | Output | Logs | Raw JSON
```

- key와 value 검색
- JSON tree 접기·펼치기
- raw 복사·다운로드
- 큰 값과 파일 Artifact 미리보기
- 어떤 upstream field에서 왔는지 추적
- 오류 발생 field 바로가기

Make의 output 검색·raw view와 Zapier의 step test data를 현재 실행 패널보다 노드 가까이에 배치하는
방식이다.

### 7.3 샘플 데이터 고정

노드 출력의 특정 실행 결과를 test fixture로 고정한다. 하류 노드를 반복 테스트할 때 앞의 외부 API를
매번 호출하지 않게 한다.

- 고정 데이터임을 노드에 명확히 표시
- 민감정보를 저장하기 전 redaction
- 실제 실행과 mock 실행에서 고정 데이터 사용 여부 분리
- schema가 바뀌면 오래된 fixture 경고

### 7.4 실행 범위 선택

- 이 노드만 테스트
- 여기부터 실행
- 여기까지 실행
- 선택 branch 실행
- 이전 실행 데이터로 다시 실행

side effect 노드는 기본 mock으로 두고 실제 실행은 명시적으로 선택한다.

## 8. P2 — 큰 워크플로우를 위한 구조화 기능

### 그룹과 메모

- 연결된 노드를 접을 수 있는 그룹
- 그룹 이름·설명·색상
- sticky note와 링크
- 그룹 복사·복제·템플릿 저장
- 접힌 그룹의 입력·출력 경계 표시

### Navigator와 검색

`Ctrl/Cmd+F`로 노드명, 타입, 필드값과 오류를 검색한다.

- 결과 선택 시 해당 노드로 이동
- `type:llm`, `status:error`, `credential:missing` 필터
- MiniMap 표시/숨김
- start/trigger 목록과 빠른 이동
- 현재 선택의 upstream/downstream 강조

### Problems 패널

저장·실행 전에 다음을 지속적으로 검사한다.

- 필수 설정 누락
- credential 미연결
- 닿을 수 없는 노드
- 잘못된 포트 연결
- 순환과 종료 노드 뒤의 죽은 경로
- 실행 후 schema가 달라진 field mapping

문제 행을 선택하면 해당 노드와 정확한 필드로 이동한다.

### 재사용 블록과 sub-workflow

선택한 연결 구간을 이름 있는 재사용 블록 또는 sub-workflow로 저장한다. 저장 시 입력·출력 경계를
사용자가 확인하고 credential 값은 포함하지 않는다.

## 9. 모바일·접근성 원칙

단축키 기능은 반드시 마우스·터치 경로도 제공한다.

- 명령 팔레트의 모든 명령은 메뉴에서도 접근 가능
- 길게 누르기로 노드·연결선 context action sheet 표시
- 선택 툴바는 모바일 하단 sheet로 전환
- 포커스된 노드와 연결선에 명확한 focus ring
- 노드 이동·연결·삭제 결과를 screen reader live region으로 알림
- 키보드 이동 중 viewport가 선택 노드를 자동 추적
- 사용자 키보드 배열과 OS에 맞는 단축키 표기
- 단일 문자 단축키는 canvas에 포커스가 있을 때만 활성화

## 10. 구현 순서

### Slice 1 — 표준 편집 기반

1. `EditorCommandRegistry`와 shortcut scope
2. 전체 편집 undo/redo
3. `Mod+S`, 복사·잘라내기·붙여넣기·복제·전체 선택
4. `?` 단축키 도움말
5. dirty 상태 표시

완료 기준: 노드 이동, 설정 변경, 연결 삭제와 붙여넣기를 순서대로 모두 undo/redo할 수 있다.

### Slice 2 — 선택 중심 편집

1. 선택 상태 중앙 관리
2. 플로팅 툴바와 scope별 context menu
3. 선택 정렬·간격 맞춤·Alt drag 복제
4. 전체/선택 화면 맞춤
5. 명령 팔레트

완료 기준: 팔레트나 더보기 메뉴를 열지 않고 선택한 노드의 주요 편집을 수행할 수 있다.

### Slice 3 — 빠른 구성

1. 캔버스 quick add
2. 연결을 놓아 노드 생성
3. 연결선 중간 삽입
4. 노드 교체
5. 최근 사용·즐겨찾기

완료 기준: `노드 검색 → 배치 → 연결` 과정을 한 흐름으로 끝낼 수 있다.

### Slice 4 — 테스트와 디버깅

1. 선택 노드 mock 실행
2. Input/Output/Logs Inspector
3. raw 검색·복사와 Artifact 미리보기
4. 샘플 데이터 고정
5. 범위 실행과 Problems 패널

완료 기준: 외부 API를 실제 호출하지 않고 한 노드의 입력부터 출력까지 검증할 수 있다.

### Slice 5 — 큰 그래프 관리

1. 그룹·메모
2. Navigator와 고급 검색
3. 부분 정렬·위치 잠금
4. 재사용 블록·sub-workflow 변환

완료 기준: 50개 이상 노드에서도 원하는 영역을 빠르게 찾고 접고 재사용할 수 있다.

## 11. 검증 지표

- 첫 노드 추가부터 첫 mock 성공까지 걸린 시간
- 노드 10개 워크플로우 구성 시 마우스 이동·클릭 수
- undo 후 원래 graph JSON과 정확히 일치하는 비율
- 복사·붙여넣기 후 깨진 내부 연결 수
- 단축키 충돌·오작동 신고율
- node test 성공 후 전체 실행 성공률
- Problems 항목 클릭 후 해결 완료율
- 명령 팔레트 검색 후 실행 전환율
- 큰 그래프에서 목표 노드를 찾는 시간

단축키 사용률 자체보다 작업 완료 시간과 오류 감소를 우선 평가한다.

## 12. 이번 조사에서 구현하지 않는 범위

- 실제 keyboard handler와 명령 팔레트 구현
- 히스토리 저장소 교체
- Clipboard 직렬화 포맷 구현
- 노드 단위 실행 API
- 그룹·메모 graph schema
- sub-workflow 백엔드
- Node Inspector 구현

현재 Slice 1~5까지 구현했다(그룹·sub-workflow 제외, 상단 이관 기록 참고). Slice 3의 빠른 선택기는 전체 목록과 역할 기반 안전 필터를 사용하며,
포트 타입 기반 추천과 Slice 4 이후 테스트 기능은 Node Definition의 타입형 입출력과 앞서 분석한
`NodeResult` 계약이 갖춰진 뒤 품질을 높인다.
