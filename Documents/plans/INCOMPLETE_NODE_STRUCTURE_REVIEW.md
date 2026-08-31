# 미완성·저품질 노드 구조 분석 및 개선안

작성일: 2026-08-28  
상태: 분석 문서 — **P0는 2026-08-28 구현 완료(ADR-0014)**, 사용자 승인의 durable
대기·알림·재개는 **2026-08-28 구현 완료(ADR-0015, §4.1)**. 나머지 P1 이후는 미착수

## 1. 분석 범위와 결론

대상 노드는 다음 5종이다.

- `humanApprovalNode` — 사용자 승인
- `databaseNode` — 데이터베이스
- `fileModifierNode` — 팔레트의 “자동 완성”, 실제 역할은 문서 서식 채우기
- `templateAnalyzerNode` — 템플릿 분석
- `posterGeneratorNode` — 포스터/이미지 생성

다섯 노드 모두 팔레트, 캔버스 컴포넌트와 백엔드 코드 생성기는 존재한다. 그러나 “실행 코드가
등록되어 있다”는 것과 “제품 기능으로 완성되어 있다”는 것은 다르다. 현재 상태를 요약하면 다음과 같다.

| 노드 | 현재 실질 기능 | 구조 완성도 | 우선순위 | 핵심 판단 |
| --- | --- | ---: | ---: | --- |
| 사용자 승인 | 전달받은 값으로 즉시 분기하며, 값이 없으면 자동 승인 | 매우 낮음 | P0 | 실제 대기·승인 기능이 아님 |
| 데이터베이스 | SQLAlchemy로 접속해 문자열 SQL 실행 | 낮음 | P0 | 접속정보 저장과 읽기 전용 보장이 위험함 |
| 자동 완성 | JSON 키로 문서의 `{{key}}` 치환 | 낮음 | P1 | 실패를 성공처럼 반환할 수 있음 |
| 템플릿 분석 | 명시적 `{{key}}` 검색, 파일이 없으면 새 서식 생성 | 낮음 | P1 | 분석과 생성의 책임이 섞여 있음 |
| 포스터/이미지 생성 | LLM HTML을 Chromium으로 캡처 | 보통 이하 | P1 | 이미지 생성기가 아니라 HTML 렌더러임 |

가장 먼저 막아야 할 것은 사용자 승인 자동 통과와 데이터베이스 접속정보 노출 가능성이다. 문서
품질과 포스터 품질은 그 다음 문제다.

현재 노출 권장 상태는 다음과 같다.

| 노드 | 권장 노출 상태 | 정식 기능으로 전환할 최소 조건 |
| --- | --- | --- |
| 사용자 승인 | 팔레트에서 숨김 또는 명확한 실험 기능 표시 | 자동 승인 제거, 승인·거절 UI, 대기 실행 저장 |
| 데이터베이스 | 내부 테스트 또는 beta | credential reference, read-only 강제, 실행 한도 |
| 자동 완성 | beta, 지원 형식 명시 | strict 입력 검증, 누락 키 보고, Artifact 출력 |
| 템플릿 분석 | beta, 업로드 파일에만 사용 | 분석 중 파일 생성 제거, 구조화된 출력 |
| 포스터/이미지 생성 | `HTML 포스터 렌더러 beta`로 정확히 표시 | HTML 격리, 크기 제한, Artifact 출력 |

## 2. 현재 공통 구조

현재 노드 하나의 동작은 여러 위치에 나뉘어 있다.

```text
팔레트 등록
  frontend/src/Sidebar.jsx
        ↓
캔버스 설정 UI
  frontend/src/customNodes.jsx 또는 frontend/src/nodeRegistry.js
        ↓
LLM 생성 설명·하드코딩 검증
  backend/meta_agent.py
        ↓
Python 코드 문자열 생성
  backend/node_generators/*.py
        ↓
동적 컴파일·exec 실행
  backend/graph.py
```

통합 `NodeDefinition`이 이미 존재하지만, 현재 정식 정의 파일을 가진 타입은 다섯 종류뿐이다.
이번 분석 대상 노드는 모두 `node_definitions/<type>.json`으로 이전되지 않았다. 따라서 필드, 기본값,
포트, 부수효과, 검증, LLM 설명이 서로 다른 파일에서 어긋날 수 있다.

또한 팔레트에서 노드를 직접 추가할 때 `EditorPage`는 타입별 기본값을 채우지 않고 공통 `label`과
콜백만 저장한다. UI가 첫 번째 선택지를 보여주더라도 실제 `graph_data`에는 그 값이 없을 수 있다.

## 3. 공통 구조 문제

### 3.1 문자열이 데이터·오류·파일을 모두 표현한다

현재 노드 간 출력은 대부분 문자열 하나다.

- DB 행 목록은 JSON **문자열**이다.
- 템플릿 스키마와 원본 데이터는 설명 문구가 붙은 **문자열**이다.
- 생성 파일은 `uploads/...` **경로 문자열**이다.
- 오류도 `Database Error: ...`, `Error formatting file: ...` 같은 **문자열**이다.

그래서 하류 노드는 성공 결과와 오류를 타입으로 구분할 수 없고, 실행 API도 문자열에 `Error` 또는
`❌`가 포함됐는지로 성공 여부를 추정한다. 정상 데이터에 “Error”라는 단어가 들어가거나 오류 문구가
예상 패턴과 다르면 상태가 잘못 기록될 수 있다.

공통 반환 계약이 필요하다.

```text
NodeResult<T>
  status: success | needs_input | waiting | error
  data: T | null
  artifacts: ArtifactRef[]
  error: { code, userMessage, retryable, details } | null
  metrics: { durationMs, tokenUsage, externalCalls }
```

### 3.2 파일 경로 대신 Artifact가 필요하다

업로드 파일에는 `UploadedFile` 소유·용량·보존 기록이 생기지만, 문서 및 포스터 노드가 직접 만든
결과 파일에는 같은 기록이 생성되지 않는다. 또한 대상 노드들은 공통 `resolve_stored_path()`를 쓰지
않아 파일 소유권을 실행 시점에 확인하지 않는다.

권장 계약:

```text
ArtifactRef
  id
  ownerUserId
  projectId
  kind: document | image | pdf
  mimeType
  originalName
  storedName
  sizeBytes
  width/height/pages
  createdAt/expiresAt
```

그래프와 노드 로그에는 서버 경로 대신 `artifactId`만 저장하고, 파일을 열 때 프로젝트 소유권과
보존 상태를 다시 확인해야 한다.

### 3.3 정의되지 않은 부수효과와 테스트 공백

현재 dry-run은 하드코딩 목록으로 DB·문서 수정·포스터 생성을 차단한다. 대상 노드가 통합 정의로
이전되지 않았기 때문에 새 mode를 추가했을 때 분류를 빼먹을 수 있다. 대상 5종에 대한 직접적인
노드 단위 테스트도 사실상 없고, 생성 그래프 평가 사례만 일부 존재한다.

각 정의에 다음 정보를 넣고 dry-run, validator, UI와 LLM 카탈로그가 같은 값을 읽어야 한다.

- 입력·출력 포트와 데이터 타입
- 필드와 기본값, 조건부 표시, 지원 확장자
- 자격 증명 provider와 최소 scope
- `sideEffect`, `riskLevel`, `executionMode`
- mock fixture와 표준 오류
- timeout, 결과 크기와 비용 한도

## 4. 노드별 분석

### 4.1 사용자 승인 (`humanApprovalNode`)

#### 현재 구조

- UI에는 입력 핸들 하나와 `out` 출력 핸들 하나만 있다.
- 백엔드 실행기는 `approved`, `rejected`/`else` source handle을 찾는다.
- 실행 인자에 `approval_decision`이 있으면 그 값을 사용한다.
- 인자가 없으면 콘솔에 메시지를 출력한 뒤 `Y`로 자동 승인한다.
- 결정값은 노드별이 아니라 실행 전체의 `approval_decision` 키 하나다.

즉 백엔드가 설명하는 승인·거절 분기를 에디터에서 정상적으로 만들 수 없고, 일반 실행은 사용자를
기다리지도 않는다. 승인 노드가 여러 개인 워크플로우는 하나의 결정값을 모두 공유한다.

#### 위험

- 결제, 외부 게시, 메시지 발송 전 승인 노드가 있어도 실제로는 자동 통과한다.
- 실행이 동기 함수 한 번으로 끝나므로 프로세스를 중단하고 나중에 이어갈 수 없다.
- 승인자, 승인 시각, 코멘트와 원본 요청의 변경 여부가 기록되지 않는다.
- 중복 승인, 만료 후 승인, 권한 없는 사용자 승인과 재전송을 막을 상태 모델이 없다.
- dry-run에서는 side effect로 분류되지 않아 “승인이 시뮬레이션되었다”는 의미도 불명확하다.

#### 개선 구조

노드는 단순 분기기가 아니라 실행을 중단하는 **durable interrupt**여야 한다.

```text
입력: ApprovalRequestInput
  subject
  summary
  payloadPreview
  riskLevel

설정:
  message
  approverPolicy: owner | workspace-role | explicit-users
  expiresIn
  onExpire: reject | cancel
  requireComment

출력 포트:
  approved
  rejected
  expired

출력: ApprovalDecision
  requestId
  decision
  decidedBy
  decidedAt
  comment
  approvedPayloadHash
```

필수 런타임 상태는 `WorkflowRun`, `NodeRun`, `ApprovalRequest`다. 노드에 도달하면 실행을
`waiting`으로 저장하고 API가 즉시 대기 상태를 반환한다. 승인 API는 권한, 만료, payload hash와
멱등성 키를 검증한 뒤 같은 실행을 해당 출력 포트에서 재개해야 한다.

#### 출시 전 최소 조치

1. 자동 승인을 제거하고 결정값이 없으면 반드시 `waiting` 또는 명시적 오류로 종료한다.
2. UI에 `approved`와 `rejected` 포트를 실제로 표시한다.
3. 다중 노드는 `approval_decisions[nodeId]`처럼 노드별 결정을 사용한다.
4. durable resume가 구현되기 전에는 팔레트에 “실험적/동기 실행 전용” 상태를 표시한다.

완료 기준은 브라우저를 닫고 서버가 재시작된 뒤에도 같은 승인 요청을 승인하여 정확한 지점부터 한
번만 재개할 수 있는 것이다.

#### 구현 진행 상황 (2026-08-28, ADR-0015)

durable 대기·알림·재개를 구현했다. 완료 기준(재시작 후 정확한 지점부터 한 번만 재개)을
테스트로 검증했다.

- 승인 노드 도달 → `ApprovalRequest` 행(그래프 스냅샷·payload·런타임 입력) + 알림(사이트
  항상, 노드 설정에 따라 이메일/카카오/디스코드 best effort) + "승인 대기" 반환. 모든 실행
  경로(에디터/스케줄/웹훅/트리거/앱)가 같은 동작을 얻는다.
- 승인/거절(`POST /api/approvals/{id}/decide`, 소유자만, 원자적 1회 전이, 코멘트) →
  `compile_workflow(entry_node_id=승인노드)`로 하류만 재컴파일해 저장된 payload(승인자가 본
  견본)부터 재개. 거절은 rejected 갈래로 재개되고, 갈래가 없으면 중단으로 기록.
- 에디터는 대기 시 즉석 모달(견본 미리보기+코멘트+승인/거절), 비동기 실행은 사이드바 배지와
  `/approvals` 대기함에서 처리한다.

위 개선 구조 중 미구현으로 남은 것: expiresIn/onExpire와 expired 포트, approverPolicy
(소유자 외 승인자 지정), 구조화된 ApprovalDecision 출력(현재는 payload 통과 + 코멘트 기록),
loop/distributor 내부 승인의 반복 문맥 보존.

### 4.2 데이터베이스 (`databaseNode`)

#### 현재 구조

- 사용자가 `connectionString`과 `query`를 노드 안에 직접 입력한다.
- 연결 문자열이 생성된 Python 소스 안에 삽입되고 SQLAlchemy `create_engine()`으로 접속한다.
- 검증기는 첫 단어가 `SELECT` 또는 `WITH`인지 확인한다.
- 결과 행을 JSON 문자열로 변환한다.
- 예외는 실패 상태가 아니라 `Database Error: ...` 결과 문자열이 된다.

#### P0 문제

**접속정보 노출**

`connectionString`은 프로젝트 `graph_data`, 모든 revision과 실행 요청 payload에 남을 수 있다.
실행 로그는 현재 전체 실행 payload를 JSON으로 기록하므로 비밀번호가 포함된 DB URI도 기록 대상이다.
API 센터 reference 원칙과 정면으로 충돌한다.

**읽기 전용 보장이 아님**

첫 단어 검사만으로 SQL을 읽기 전용으로 만들 수 없다. 예를 들어 PostgreSQL의 데이터 변경 CTE처럼
`WITH`로 시작하는 쓰기 SQL이 통과할 수 있고, `SELECT`로 호출 가능한 부수효과 함수도 있다. 실행기는
결과 행이 없으면 실제로 `commit()`까지 수행한다.

**실행 제한 부재**

- DB host·port allowlist 또는 네트워크 정책이 없다.
- statement timeout, 최대 행 수와 최대 결과 크기가 없다.
- read-only transaction과 전용 최소 권한 계정을 강제하지 않는다.
- 매 실행마다 engine을 만들고 명시적으로 dispose하지 않는다.
- 파라미터 바인딩 없이 완성 SQL 문자열만 받는다.
- 스키마 탐색, 연결 테스트와 컬럼 자동완성이 없다.

#### 개선 구조

기존 노드는 `Database Query`로 명확히 이름을 바꾸고, 향후 `Database Write`는 별도 타입으로 만든다.
이는 장기 로드맵의 “조회 노드와 schema allowlist 기반 쓰기 노드 분리”와도 일치한다.

```text
DatabaseQueryNode
  credentialRef: API 센터의 database provider
  dialect: postgres | mysql | sqlite 등 provider에서 파생
  queryTemplate
  parameters: [{ name, source, type, required }]
  maxRows: 기본 100, 상한 1,000
  timeoutSeconds: 기본 10, 상한 고정
  output: { columns, rows, rowCount, truncated }

DatabaseWriteNode (후속)
  operation: insert | update | upsert
  schema/table allowlist
  mapped fields
  dryRun preview
  approval policy
```

읽기 전용은 SQL 문자열 검사에 의존하지 말고 다음을 중첩 적용한다.

1. API 센터에 read-only 자격 증명을 별도로 등록한다.
2. DB 세션을 read-only transaction으로 시작한다.
3. 하나의 statement만 허용하고 dialect parser로 허용 AST를 제한한다.
4. timeout, 행·바이트 제한과 허용 schema를 적용한다.
5. 결과를 문자열이 아닌 구조화된 테이블 데이터로 반환한다.

SQLite는 서버 로컬 경로를 connection string으로 받지 말고 사용자가 업로드한 DB Artifact만 허용해야
한다. 외부 DB 연결은 workspace별 egress 정책을 적용한다.

### 4.3 자동 완성 (`fileModifierNode`)

#### 현재 구조

팔레트 명칭은 “자동 완성”, 노드 헤더는 `Auto Fill`이다. 실제 기능은 직전 노드의 JSON 키와 문서의
`{{key}}`를 일치시켜 새 파일을 만드는 **템플릿 채우기**다.

- 입력 문자열을 JSON으로 파싱하지 못하면 예외를 버리고 빈 객체 `{}`로 바꾼다.
- 빈 객체여도 문서를 저장하고 결과 파일 경로를 반환할 수 있다.
- 파일이 없으면 일부 형식에서 새 템플릿을 자동 생성한다.
- output이 `.pdf`면 업로드한 템플릿을 무시하고 새 PDF를 만든다.
- `.doc`, `.xls`, `.ppt`도 분기상 지원하는 것처럼 보이지만 사용 라이브러리는 주로 최신 OOXML
  형식인 `.docx`, `.xlsx`, `.pptx`용이다.

#### 품질 저하 원인

- “자동 완성”이라는 이름으로 입력 데이터 계약을 알기 어렵다.
- JSON 파싱 실패와 키 불일치가 성공 파일로 위장한다.
- DOCX/PPTX의 placeholder가 여러 run으로 나뉘면 run 단위 치환이 실패할 수 있다.
- HWPX의 placeholder가 여러 XML text node에 걸치면 단순 XML 문자열 치환이 실패할 수 있다.
- 어떤 키가 채워졌고 빠졌는지 보고하지 않는다.
- 템플릿 채우기와 새 문서 생성, PDF 렌더링이라는 세 역할이 한 노드에 섞여 있다.

#### 개선 구조

노드명을 `템플릿 채우기`로 바꾸고 새 문서 생성은 `문서 생성`으로 분리한다.

```text
TemplateFillNode
  template: ArtifactRef<Document>
  values: object
  mapping: [{ placeholder, valuePath, formatter, fallback }]
  strictMode: true
  outputFormat: same-as-template | pdf
  output: TemplateFillResult
    artifact
    replacedKeys
    missingKeys
    unusedValues
    warnings
```

- JSON이 아니면 즉시 `INPUT_SCHEMA_INVALID`로 실패시킨다.
- strict mode에서는 필수 키가 하나라도 비면 결과를 성공으로 표시하지 않는다.
- OOXML은 run 단위가 아니라 문서 모델에서 placeholder span을 재구성해 치환한다.
- PDF 변환은 별도 변환 단계로 취급하고 템플릿을 조용히 무시하지 않는다.
- `.doc/.xls/.ppt/.hwp`는 실제 변환기가 준비될 때까지 업로드 UI에서 지원 대상으로 표시하지 않는다.
- 실행 전 “필드 매핑 테스트”로 샘플 값, 누락 키와 미리보기를 보여준다.

### 4.4 템플릿 분석 (`templateAnalyzerNode`)

#### 현재 구조

- 문서 텍스트에서 `{{...}}` 정규식을 찾아 키 집합을 만든다.
- 결과는 스키마 JSON이 아니라 빈칸 목록과 직전 노드의 실제 데이터를 합친 설명 문자열이다.
- 업로드 파일이 없으면 파일명으로 문서 종류를 추측해 LLM이 필드명을 만들고 새 DOCX/HWPX를 쓴다.
- 뒤쪽의 LLM structured schema를 최대 8 hop 탐색해 필드명을 재사용하기도 한다.

#### 구조 문제

분석 노드가 파일을 생성하고 LLM까지 호출한다. 따라서 이름은 분석이지만 실제로는 외부 비용과 파일
쓰기 부수효과가 있으며, 존재하지 않는 파일을 오류로 알리지 않고 그럴듯한 새 파일로 대체한다. 이
동작은 사용자가 올린 원본 서식을 분석했다는 잘못된 인상을 줄 수 있다.

또한 출력이 자유 형식 문자열이므로 하류 LLM이 다시 내용을 해석해야 한다. 키 집합은 순서가 없고,
placeholder의 위치, 주변 문맥, 예상 타입, 필수 여부와 반복 영역을 제공하지 않는다. 구조 탐색으로
“뒤에 있는 LLM schema”를 가져오는 방식은 그래프의 하류 구현에 분석 결과가 역으로 의존하게 만든다.

#### 개선 구조

분석은 읽기 전용·결정론적 노드로 제한한다.

```text
TemplateAnalyzeNode
  input: ArtifactRef<Document>
  placeholderSyntax: braces | content-controls | named-cells
  output: TemplateDefinition
    artifactId
    format
    placeholders: [
      { key, location, context, inferredType, required, occurrences }
    ]
    warnings
```

- 파일이 없거나 지원하지 않으면 명시적으로 실패한다.
- 원본 데이터는 분석 결과에 문자열로 합치지 않고 별도 데이터 edge로 `TemplateFillNode`에 전달한다.
- “파일명으로 새 템플릿 만들기”는 `DocumentTemplateCreateNode`로 분리한다.
- 분석 결과는 UI에서 키 목록과 문서 위치를 보여주고 사용자가 이름·타입을 수정할 수 있게 한다.
- DOCX content control, XLSX named range와 표, PPTX shape name처럼 포맷 고유의 안정적인 표식을
  우선 사용하고 `{{key}}`는 공통 fallback으로 둔다.

### 4.5 포스터/이미지 생성 (`posterGeneratorNode`)

#### 현재 구조

이 노드는 이미지를 생성하지 않는다. 직전 LLM이 만든 HTML/CSS를 Playwright Chromium으로 열고 PNG
스크린샷 또는 PDF를 저장한다. 12개 배경 프리셋은 CSS 배경으로 주입한다.

설정 UI도 통합 Node Definition이 아니라 별도 `nodeRegistry.js`의 범용 DynamicNode를 사용한다.
따라서 필드 기본값, 허용 크기, 부수효과와 LLM 설명이 한 정본에서 관리되지 않는다.

#### 품질과 안전 문제

- 디자인 품질을 긴 system prompt와 모델의 HTML 작성 능력에 의존한다.
- 카피, 레이아웃, 스타일이 하나의 HTML 문자열이라 부분 검증과 재사용이 어렵다.
- width·height의 최소/최대값이 없어 과도한 렌더링 자원을 요청할 수 있다.
- `page.set_content()` 전에 script 제거, 외부 요청 차단과 허용 CSS 검사가 없다.
- LLM HTML에 script, 외부 이미지, iframe 또는 fetch가 들어가면 서버 측 브라우저에서 실행될 수 있다.
- 렌더 timeout, 폰트 로딩 완료, overflow와 대비 검사가 없다.
- 결과 파일이 Artifact로 등록되지 않는다.
- “포스터/이미지 생성”이라는 명칭 때문에 사용자는 생성형 이미지 모델을 기대한다.

#### 권장 분리 구조

외부 이미지 API를 붙일 때 기존 노드에 provider 분기만 추가하지 않는다. 생성형 이미지와 정확한
텍스트 합성은 목적과 실패 방식이 다르므로 두 capability로 분리한다.

```text
ImageGenerationNode
  prompt
  negativePrompt
  provider/model
  aspectRatio/size
  stylePreset
  seed, quality, safety
  output: ArtifactRef<Image> + provider metadata + cost

PosterComposeNode
  content: PosterContent JSON
  background: ArtifactRef<Image> | built-in preset
  layoutPreset
  theme tokens
  size/outputFormat
  output: ArtifactRef<Image|PDF> + layout warnings
```

대표 흐름:

```text
행사 정보
  ├─→ 이미지 생성 ───────┐
  └─→ 카피 구조화 ───────┼─→ 포스터 합성 → PNG/PDF
                         └─ 제목·날짜·CTA는 정확한 HTML/Canvas 텍스트로 합성
```

`PosterComposeNode`는 LLM이 자유 HTML을 쓰게 하지 않고 제한된 `PosterDesignSpec`을 받는다.

```text
PosterDesignSpec
  title, subtitle, body, date, location, cta
  layoutId
  paletteId
  typographyScale
  alignment
  decorations
```

렌더러가 검증된 템플릿으로 이를 변환하면 한글 정확도는 유지하면서 결과 편차를 줄일 수 있다. 기존
HTML 방식은 `legacyHtml` mode로 한시적으로 유지하되 기본 경로에서는 제외한다. legacy mode에는
JavaScript 비활성화, 모든 네트워크 요청 차단, iframe/object 제거, 렌더 timeout, 픽셀 수 상한과
프로세스 격리를 적용해야 한다.

## 5. 대상 노드의 권장 Definition 요약

| 타입 | 입력 | 출력 | 실행 방식 | 부수효과/위험 |
| --- | --- | --- | --- | --- |
| `humanApprovalNode` | any + 승인 preview | `ApprovalDecision` | suspend/resume | control wait, high risk gate |
| `databaseQueryNode` | parameter object | `TableResult` | sync, bounded | external-read, high |
| `templateAnalyzeNode` | document Artifact | `TemplateDefinition` | sync/worker | none, file-read |
| `templateFillNode` | template Artifact + object | fill result + Artifact | worker | file-write |
| `imageGenerationNode` | generation spec | image Artifact | async provider job | external-write, billable |
| `posterComposeNode` | content + optional image | image/PDF Artifact | isolated worker | file-write, renderer |

NodeDefinition 스키마에도 현재 없는 다음 개념을 추가해야 한다.

- `kind: artifact`, `kind: credentialRef`, 객체형 input schema
- `executionMode: sync | async-job | suspend`
- `riskLevel: low | medium | high`
- `limits: timeoutSeconds, maxInputBytes, maxOutputBytes, maxPixels, maxRows`
- `errors` 표준 목록
- mode별 side effect와 credential scope

## 6. 권장 작업 순서

### P0. 기능명과 실제 안전성 일치 — 완료 (2026-08-28, ADR-0014)

1. ~~사용자 승인의 자동 승인 제거 및 fail-closed 처리~~ — 결정 없으면 대기(또는 대기를
   만들 수 없는 경로에서는 명시적 오류)로 중단. UI에 approved/rejected 핸들 표시.
   durable 대기·알림·재개는 같은 날 ADR-0015로 구현 완료(§4.1 구현 진행 상황).
2. ~~DB 연결 문자열의 graph/revision/log 저장 중단, API 센터 credential reference 도입~~ —
   `database` provider 추가, 노드는 `{{API_CENTER:database}}` reference만 실행,
   평문은 실행 관문(graph.run_workflow)에서 차단, 실행 로그 payload의 자격증명 키 마스킹,
   LLM 카탈로그·few-shot도 reference로 교체.
3. ~~DB 쿼리의 read-only session, timeout, 행 제한 적용~~ — `db_query_runtime.py`로 실행
   로직 이전(단일 statement → SELECT/WITH → dialect별 read-only 세션 → 행 100·256KB 제한 →
   오류 URI 마스킹, commit 제거).
4. ~~포스터 legacy HTML의 JavaScript·네트워크 차단과 크기 상한 적용~~ — 위험 태그·인라인
   핸들러 제거 + `java_script_enabled=False` + 전 네트워크 차단, 크기 [100, 4000]px 고정,
   렌더 timeout 15초.

의도된 동작 변화: 평문 접속 문자열을 쓰던 기존 databaseNode는 API 센터 등록 안내를
반환하고, 승인 노드가 있는 자동 실행(스케줄/웹훅/앱)은 자동 통과 대신 중단된다.

### P1. 공통 계약 도입 — 부분 완료 (2026-08-28)

1. `NodeResult`, `ArtifactRef`, 표준 오류 계약 추가 — **부분 완료** (2026-08-28, ADR-0016:
   `NodeResult`·`NodeError v1`·중앙 `error_catalog.json` 완료, Database·Discord·SMTP·connector 노드
   이전. 노드 사이 값은 아직 문자열이고 `ArtifactRef` 는 우선 백로그 20에서 확정한다)
2. ~~대상 5종을 `node_definitions`로 이전~~ — 우선 백로그 9번(주요 10종 이전)에 포함해 완료.
   databaseNode의 SQL 가드는 규칙 DSL 밖이라 하이브리드(정의+잔여 분기)로 남았다.
3. ~~팔레트, 기본값, UI, validator, LLM 카탈로그를 정의에서 생성~~ — dry-run 분류는
   기존 하드코딩과 정의 파생의 합집합(ADR-0008 방식) 그대로.
4. 대상 노드별 단위·통합 테스트 — 정의 회귀 테스트(test_node_definitions)가 15종을 커버.
   NodeResult 기반 실행 테스트는 1번과 함께 진행.

### P2. 책임 분리

1. 템플릿 분석과 템플릿 생성을 분리
2. 자동 완성을 템플릿 채우기와 문서 생성으로 분리
3. DB Query와 DB Write 분리
4. Image Generation과 Poster Compose 분리
5. 사용자 승인 durable resume 구현

### P3. 품질 고도화

1. 문서별 안정적인 placeholder 표현과 위치 미리보기
2. 포스터 DesignSpec, 레이아웃 템플릿과 자동 대비·overflow 검사
3. DB schema browser, parameter mapper와 샘플 실행
4. 실제 실패 fixture를 포함한 mock 및 회귀 평가

## 7. 노드별 최소 테스트 게이트

### 사용자 승인

- 결정이 없을 때 하류 노드가 절대 실행되지 않는다.
- 승인·거절·만료 포트가 각각 한 번만 실행된다.
- 승인자가 아닌 사용자는 결정할 수 없다.
- 재시작 후 재개와 중복 요청 멱등성이 보장된다.

### 데이터베이스

- 자격 증명 원문이 graph, revision, 로그와 오류에 남지 않는다.
- 쓰기 CTE, 다중 statement와 side-effect 함수가 차단된다.
- timeout, 행·바이트 제한이 실제로 적용된다.
- 쿼리 오류가 성공 결과 문자열이 아니라 오류 상태가 된다.

### 템플릿 분석·채우기

- DOCX/HWPX/PPTX에서 여러 run/XML node에 나뉜 placeholder를 처리한다.
- 지원하지 않는 구형 포맷이 업로드 단계에서 명확히 거절된다.
- 누락 키가 있는 결과를 성공으로 표시하지 않는다.
- 다른 사용자의 Artifact를 경로 추측으로 열 수 없다.
- 결과 파일이 소유·용량·보존 기록과 함께 등록된다.

### 이미지 생성·포스터 합성

- 외부 이미지 API의 비용·안전 실패가 표준 오류로 기록된다.
- 생성형 배경 위 텍스트가 원문과 정확히 일치한다.
- overflow, 대비와 해상도 제한을 자동 검증한다.
- legacy HTML에서 script와 모든 외부 네트워크가 차단된다.
- 결과 이미지와 PDF가 Artifact로 등록된다.

## 8. 이번 분석에서 구현하지 않는 범위

- 실제 NodeDefinition JSON 작성
- DB credential provider와 migration 구현
- 승인 요청 UI·알림과 실행 재개 엔진 구현
- 문서 parser/renderer 교체
- 외부 이미지 생성 provider 선정 및 API 연동
- 기존 프로젝트 graph migration

구현 전에는 P0 안전 조치와 공통 `NodeResult`/`ArtifactRef` 계약을 먼저 확정해야 한다. 이 두 계약
없이 개별 노드 UI만 개선하면 오류·파일·대기 상태가 다시 문자열에 섞여 같은 구조 문제가 반복된다.

## 9. 코드 근거 위치

| 확인 항목 | 현재 코드 |
| --- | --- |
| 대상 노드 팔레트 등록 | `frontend/src/Sidebar.jsx` |
| 대상 노드 캔버스 UI | `frontend/src/customNodes.jsx` |
| 포스터의 별도 프론트 레지스트리 | `frontend/src/nodeRegistry.js` |
| 드롭 시 타입별 기본값을 넣지 않는 경로 | `frontend/src/pages/EditorPage.jsx`의 `onDrop`, `handleNodeTap` |
| 통합 Node Definition 스키마 | `backend/node_definition.py`, `node_definitions/*.json` |
| LLM 노드 설명과 하드코딩 검증 | `backend/meta_agent.py` |
| 사용자 승인 실행기 | `backend/node_generators/ui_nodes.py` |
| 데이터베이스 실행기 | `backend/node_generators/data_nodes.py` |
| 분석·채우기·포스터 실행기 | `backend/node_generators/template_nodes.py` |
| HTML Chromium 렌더러 | `backend/poster_generator.py` |
| 동적 코드 실행과 credential 치환 | `backend/graph.py` |
| 전체 실행 payload 로그 저장 | `backend/main.py`의 `/api/execute` |
| 업로드 소유·용량 모델 | `backend/models.py`의 `UploadedFile`, `backend/upload_security.py` |
| dry-run 하드코딩 위험 분류 | `backend/dry_run.py` |
| 장기 노드 방향 | `Documents/ROADMAP.md`의 공식 연동 Wave 2·3 |
