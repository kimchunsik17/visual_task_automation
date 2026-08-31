# 운영 데이터베이스 Explorer·내보내기·안전한 수정 계획

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | 구현 계획 v1.0 — 미착수 |
| 작성일 | 2026-08-30 |
| 대상 | 운영 탭, API 센터의 Database 자격증명, `databaseNode`, 후속 `Database Write` |
| 목표 | 연결된 외부 PostgreSQL의 구조와 데이터를 안전하게 탐색하고 JSON/XLSX로 내보내며, 별도 승인된 쓰기 권한으로 제한적인 행 수정을 제공 |
| 예상 크기 | L, 조회·내보내기 2~3주 + 수정 beta 2~3주 |
| 관련 | `../ADR.md` ADR-0017, `../ROADMAP.md` 백로그 31번, `../design/MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md` |
| 제외 | 제품 자체 운영 DB 노출, 범용 SQL 콘솔, DDL, 대량 수정·삭제, MySQL 지원, 제품 관리형 Data Store |

새 PNG/WebP는 필요하지 않다. Database·Table·Column icon은 기존 SVG/Lucide 체계를 사용한다.

## 1. 결론

운영 탭에 **연결된 데이터베이스**를 추가한다. 다만 `databaseNode에 저장된 데이터`라는 표현은 현재
동작과 다르다. `databaseNode`는 데이터를 보관하지 않고 API 센터에 등록한 외부 PostgreSQL을 SELECT하는
읽기 전용 노드다. 운영 화면도 노드별 데이터 사본이 아니라 **자격증명으로 연결한 Database → Schema →
Table/View → Row**를 탐색한다. 같은 연결을 참조하는 여러 노드는 중복 Database로 표시하지 않는다.

범위는 두 단계로 분리한다.

1. **기본 출시: 조회와 내보내기**
   - 연결 상태, schema/table/column, 데이터 grid, filter/sort/pagination, 사용 Workflow를 제공한다.
   - 현재 filter 결과를 JSON 또는 XLSX로 비동기 내보낸다.
   - 기존 Database Query v2의 credential·egress·read-only·timeout·오류 계약을 그대로 재사용한다.
2. **후속 beta: 제한적인 행 수정**
   - 기존 조회 credential로는 절대 쓰지 않는다.
   - 별도 `Database Write` capability, table/column allowlist, 변경 preview와 확인, 낙관적 잠금, 감사 로그가
     모두 있을 때 `insert | update | upsert`만 연다.
   - Delete, raw DML, DDL, 여러 행 일괄 수정은 beta 범위 밖이다.

제품 내부에 사용자가 직접 행을 저장하는 기능이 필요하면 후속 **Managed Data Store**와
`dataStoreReadNode`·`dataStoreWriteNode`를 별도 설계한다. 외부 연결 DB와 제품 소유 저장소는 보존·과금·
백업·권한 책임이 다르므로 한 화면 계약으로 섞지 않는다.

## 2. 현재 기반과 간극

### 이미 있는 것

- API 센터에 여러 Database 자격증명을 이름 붙여 저장하고 노드는 secret 대신
  `{{API_CENTER:database#<id>}}` reference만 보관한다.
- PostgreSQL 연결 진단을 driver → DNS → TCP → auth → read-only probe 단계로 제공한다.
- `information_schema` 기반 Schema/Table/View/Column 탐색과 5분 TTL cache가 있다.
- Database Query v2는 sqlglot AST allowlist, bind parameter, read-only transaction, timeout, 최대 1,000행,
  결과 256KB 제한과 구조화된 `NodeResult`를 제공한다.
- loopback·link-local·metadata·reserved 주소를 차단하고 private network는 self-host opt-in일 때만 허용한다.
- `openpyxl`이 설치되어 있어 XLSX 생성에 새 런타임 의존성은 필요하지 않다.
- 운영 개요는 Webhook·Bot·Schedule 세 관리 API를 합쳐 읽기 전용 상태를 보여준다.

### 빠진 것

- 운영 하위 navigation과 Database overview card
- 어떤 Workflow/노드가 어떤 credential을 참조하는지 보여주는 역참조
- Table 데이터를 안전한 filter DSL로 페이지 단위 조회하는 API
- 대용량 결과를 request memory에 모두 올리지 않는 export job과 Artifact download
- UI에서 쓸 수 있는 별도 write credential/capability와 승인 계약
- workspace credential 소유권, 역할별 browse/export/edit 권한
- 조회·내보내기·수정 감사 로그와 민감 컬럼 처리 정책

## 3. 정보 구조와 화면

### 3.1 Navigation

```text
운영
├─ 개요
├─ 웹훅
├─ 봇
├─ 스케줄
└─ 데이터베이스
```

- 경로는 `/operations/databases`로 둔다.
- 운영 개요 Card는 `연결 n개 · 정상 n개 · 사용 중 n개`를 보여준다. 연결 API 실패를 0으로 표시하지 않는다.
- `Main Shell`의 Ink token, PageHeader, StatusBadge, ContextDrawer와 Toast를 재사용한다.

### 3.2 연결 목록

각 연결은 다음 정보만 표시한다.

- 사용자가 붙인 label, PostgreSQL, host/database 이름, 최근 진단 결과와 진단 시각
- 참조하는 Workflow 수와 `databaseNode` 수, 마지막 조회 성공/실패 시각
- scope(`personal | workspace`)와 `browse | export | edit` capability
- `탐색`, `연결 테스트`, `사용 Workflow`, `API 센터에서 관리` 행동

URI, username, password, resolved IP와 실행 SQL 원문은 목록·telemetry·감사 로그에 넣지 않는다. 연결 생성·
교체·삭제는 계속 API 센터에서 하고 운영 화면은 data plane에 집중한다.

### 3.3 Explorer

```text
┌ 연결 ─────────┬ Schema / Table ─────┬ Data Grid ──────────────────────┐
│ 개발 DB       │ public              │ users                 1,248 rows │
│ 운영 DB       │  ├ users            │ [검색] [필터] [정렬] [내보내기] │
│               │  ├ orders           │ id │ name │ status │ updated_at  │
│               │  └ report_view      │ …                              │
└───────────────┴─────────────────────┴────────────────────────────────┘
```

- Desktop은 3-pane, 1024px 이하는 `연결 → Table → Data` 순서의 단계형 화면으로 바꾼다.
- Table과 View를 구분하고 View는 항상 read-only로 표시한다.
- Column type, nullable, primary key, editable 여부를 Header/Column inspector에서 보여준다.
- 기본 page size는 50, 선택지는 25/50/100이다. 전체 row count는 값싼 통계가 없으면 `정확한 수 계산`을
  사용자가 요청할 때만 수행한다.
- selection, filter, sort는 URL query에 남기되 행 값과 secret은 URL에 넣지 않는다.
- 빈 상태, 권한 없음, 연결 실패, timeout, schema 변경, partial export를 별도 상태로 표현한다.

### 3.4 Data Grid 행동

- Column 선택/숨김, 단일·복합 정렬, typed filter, 값 복사
- 선택 행을 JSON으로 복사, 현재 page 또는 현재 filter 전체 내보내기
- 이 Table을 참조하는 Workflow와 Node로 deep link
- 수정 capability가 있을 때만 `행 추가`와 한 행 단위 `수정` 표시
- destructive action을 hover 전용 icon으로 숨기지 않는다. Delete는 beta에서도 제공하지 않는다.

## 4. 조회 API 계약

기존 credential·schema endpoint는 호환을 유지한다. 새로운 Data Grid는 raw SQL 문자열을 받지 않고 서버가
허용된 identifier와 operator로 SQLAlchemy expression을 만든다.

### 4.1 연결과 사용처

- 기존 `GET /api/database/credentials`: secret 없는 연결 목록
- 기존 `POST /api/database/credentials/{id}/test`: 연결 진단
- 기존 `GET /api/database/credentials/{id}/schema`: schema metadata
- 신규 `GET /api/database/credentials/{id}/usages`: 참조 Workflow/Node와 접근 가능한 deep link

사용처 검색은 `graph_data`를 매 요청 전수 순회하지 않는다. Project 저장 시
`DatabaseCredentialUsage(project_id, node_id, credential_id, updated_at)`를 갱신하거나 검증된 summary index를
유지한다. 권한이 없는 프로젝트의 제목·존재 여부도 노출하지 않는다.

### 4.2 Table browse

```http
POST /api/database/browse
```

```json
{
  "credentialId": 17,
  "schema": "public",
  "table": "users",
  "columns": ["id", "name", "status", "updated_at"],
  "filters": [{"column": "status", "operator": "eq", "value": "active"}],
  "sort": [{"column": "id", "direction": "asc"}],
  "page": {"limit": 50, "cursor": null}
}
```

응답:

```json
{
  "columns": [
    {"name": "id", "type": "integer", "nullable": false, "primaryKey": true, "editable": false}
  ],
  "rows": [{"id": 1, "name": "Kim", "status": "active"}],
  "pageInfo": {"nextCursor": "opaque", "hasNext": true, "countMode": "unknown"},
  "capabilities": ["browse", "export"],
  "schemaVersion": "opaque",
  "truncated": false
}
```

계약:

- schema/table/column은 live metadata allowlist와 대조하고 driver identifier quoting을 사용한다.
- operator는 type별 allowlist(`eq`, `neq`, `contains`, `startsWith`, `gt/gte/lt/lte`, `isNull`, `in`)만 허용한다.
- 값은 모두 bind parameter이며 raw SQL, expression, function 이름을 받지 않는다.
- Primary key 또는 안정적인 unique key가 있으면 keyset cursor를 쓴다. 없으면 읽기 전용 offset pagination과
  `결과가 변경될 수 있음` 안내를 사용하고 수정은 비활성화한다.
- 시스템 schema와 허용되지 않은 schema, binary/large object 원문은 반환하지 않는다.
- 기본 timeout 10초, page 상한 100, 응답 바이트 상한을 적용하고 NodeError v1으로 실패를 정규화한다.

`POST /api/database/preview`의 자유 SQL 미리보기는 Editor의 `databaseNode` 도구로 남긴다. 운영 Explorer는
범용 SQL client가 아니며 더 좁은 browse DSL을 사용한다.

## 5. JSON/XLSX 내보내기

### 5.1 사용자 흐름

1. 범위 선택: 현재 page | 선택 행 | 현재 filter 전체
2. Column과 format(JSON | XLSX) 선택
3. 예상 규모와 민감 데이터 경고 확인
4. export job 생성
5. 완료 알림에서 만료 시각이 있는 Artifact 다운로드

### 5.2 계약

```http
POST /api/database/exports
GET  /api/database/exports/{jobId}
GET  /api/database/exports/{jobId}/download
```

- browse와 동일한 filter DSL·권한·egress·timeout을 사용하며 클라이언트가 SQL을 제출하지 않는다.
- 작은 현재 page는 동기 다운로드가 가능하지만, filter 전체는 항상 background job으로 만든다.
- 기본 상한은 job당 50,000행 또는 50MB, 실행 5분으로 두고 config/plan resolver가 조정한다.
- JSON은 UTF-8 JSON array를 기본으로 한다. 상한을 넘을 가능성이 있는 범위에는 streaming JSONL 선택지를
  추가할 수 있지만 `.json`처럼 가장하지 않는다.
- XLSX는 `openpyxl` write-only mode로 생성하며 행 전체를 memory에 쌓지 않는다. 날짜·숫자·boolean type을
  유지하고 Excel formula로 해석될 수 있는 `=`, `+`, `-`, `@` 시작 문자열은 기본 neutralize한다.
- Binary/large object는 `<binary omitted>`로 표시하고 별도 export를 지원하지 않는다.
- 파일은 기존 `ArtifactRef` 소유권·경로 검사를 사용하고 기본 24시간 후 만료한다. 다운로드할 때 권한을
  다시 검사하며 short-lived URL을 사용한다.
- export 파일, job status, log, notification 어디에도 credential URI와 SQL 원문을 넣지 않는다.
- audit에는 actor, credential ID, schema/table, column 이름, filter 구조, row/byte 수, format, 결과만 남긴다.
  실제 행 값과 filter 값은 기본적으로 저장하지 않는다.

## 6. 안전한 행 수정 beta

### 6.1 선행 조건

- 별도 `Database Write` credential 또는 binding. 조회 credential을 자동 승격하지 않는다.
- capability: `database:browse`, `database:export`, `database:edit`을 분리한다.
- workspace owner/admin이 schema/table/column allowlist와 operation(`insert | update | upsert`)을 승인한다.
- credential 자체 DB role도 허용 Table에 대한 최소 권한만 가져야 한다.
- `project_access`와 workspace credential 계약이 실제 endpoint 판정의 정본이어야 한다.

### 6.2 수정 흐름

```text
행 선택 → 편집 Drawer → type/schema 검증 → 변경 Diff → 재확인 → 단일 transaction → 결과/감사
```

- Preview는 SQL을 실행했다가 rollback하는 방식이 아니다. trigger·외부 함수의 부수효과를 피하기 위해
  schema/type/constraint와 생성될 operation을 **실행 없이** 검증하고 diff만 보여준다.
- Update는 primary key가 있는 base table에만 허용한다. version column이 있으면 그것을 쓰고 PostgreSQL에서는
  단기 opaque row version으로 `xmin`을 fallback할 수 있다. 버전이 달라지면 `DATABASE_ROW_CONFLICT`로
  새 값을 다시 불러오게 한다.
- 한 요청은 한 행만 수정하고 단일 transaction으로 commit한다. bulk update는 별도 승인 전까지 막는다.
- 서버는 table/column identifier를 metadata allowlist에서 만들고 값만 bind한다. 사용자가 DML 문자열을
  제출하는 endpoint는 만들지 않는다.
- 비밀번호·token·주민번호 등 민감 컬럼은 별도 classification/denylist로 기본 숨김·수정 금지한다.
- 감사 로그에는 대상 key의 안전한 hash, 변경 column 이름, actor, 승인/결과를 남긴다. 원본/변경 값을
  통째로 복사하지 않는다.
- insert/update/upsert를 우선 제공하고 Delete, truncate, schema 변경, stored procedure 호출은 제외한다.

### 6.3 승인과 실패 처리

- 개인 공간도 첫 write 연결 활성화는 재인증을 요구한다.
- workspace는 owner/admin이 write binding을 만들고 editor 이상 중 별도 capability가 있는 사용자만 수정한다.
- 민감 또는 운영 label 연결은 매 수정 확인 또는 Approval node/Inbox 연계를 선택할 수 있게 한다.
- timeout이나 연결 단절로 결과가 불명확하면 자동 retry하지 않고 `outcome: unknown`과 확인 쿼리를 제공한다.
- 외부 DB 변경은 일반적인 undo를 보장할 수 없으므로 UI에서 `되돌리기 가능`이라고 표현하지 않는다.

## 7. 보안·권한 원칙

- **제품 자체 운영 DB는 절대 목록에 자동 추가하지 않는다.** 사용자가 소유하고 API 센터에 등록한 연결만
  대상으로 한다.
- URI 복호화는 기존 실행기와 같은 서버 경계 안에서만 수행하고 response·browser·job queue payload에
  평문 secret을 전달하지 않는다.
- connection owner/workspace scope와 현재 사용자의 browse/export/edit capability를 요청마다 확인한다.
- SSRF 방어, DNS pinning, TLS 기본값, system schema 차단과 timeout을 기존 Database Query v2와 공유한다.
- export와 write는 별도 rate limit과 동시 job limit을 적용한다.
- field value, filter value, exported content를 analytics·error tracking·support log에 전송하지 않는다.
- 사용자가 read-only DB role을 등록하도록 계속 권장하며 write role은 별도 연결로 분리한다.
- frontend에서 button을 숨기는 것은 권한 통제가 아니다. 모든 endpoint가 동일한 capability resolver를 쓴다.

## 8. 단계별 구현

### DBOPS-0. 계약과 선행 결함 — 2~3일

1. 연결 DB와 제품 Managed Data Store의 명칭·범위를 고정한다.
2. personal/workspace credential scope와 browse/export/edit capability 계약을 확정한다.
3. identifier/filter DSL, row/page/export limit과 typed error를 정의한다.
4. Database credential usage index 전략과 graph 저장 hook을 정한다.

완료 기준: UI가 raw SQL이나 secret을 받지 않고도 모든 조회 행동을 표현할 수 있다.

### DBOPS-1. 운영 진입점과 Schema Explorer — 3~4일

1. `OPERATIONS_SECTION_TABS`와 `/operations/databases` route를 추가한다.
2. 운영 개요 Database Card와 연결 목록·상태를 구현한다.
3. 기존 연결 진단·schema API를 Explorer에 연결한다.
4. credential usage index와 Workflow/Node deep link를 제공한다.

완료 기준: 연결 원문을 노출하지 않고 연결 → Table → 사용 Workflow를 탐색할 수 있다.

### DBOPS-2. 읽기 전용 Data Grid — 4~6일

1. metadata allowlist 기반 browse DSL과 server query builder를 구현한다.
2. typed filter/sort, keyset pagination, Column inspector와 Grid를 연결한다.
3. View·primary key 없음·schema 변경·timeout·partial result 상태를 처리한다.
4. 390/1024/1440px와 keyboard Grid navigation을 검증한다.

완료 기준: SELECT 문자열을 입력하지 않고 100만 행 Table도 bounded page로 탐색할 수 있다.

### DBOPS-3. JSON/XLSX export — 3~5일

1. export job, queue/worker, ArtifactRef와 만료 cleanup을 구현한다.
2. JSON stream과 XLSX write-only exporter, formula neutralization을 구현한다.
3. 진행/완료/실패 알림과 다운로드 권한 재검사를 연결한다.
4. 행·바이트·시간·동시 job 상한과 취소를 검증한다.

완료 기준: 50,000행 export에서도 API process memory가 결과 크기에 비례해 증가하지 않고 다른 사용자가
Artifact를 받을 수 없다.

### DBOPS-4. 안전한 수정 beta — 6~8일

1. Database Write binding·allowlist·capability와 감사 event를 구현한다.
2. no-execute preview, diff/confirm Drawer와 insert/update/upsert endpoint를 구현한다.
3. primary key·row version 기반 conflict detection과 outcome unknown 처리를 추가한다.
4. 개인 opt-in → 내부 workspace 순서의 feature flag로 연다.

완료 기준: read-only credential로는 어떤 write endpoint도 실행되지 않고, stale row 수정은 조용히
덮어쓰지 않으며 모든 성공 write에 감사 event가 남는다.

### DBOPS-5. Workspace·운영 hardening — 3~5일

1. TEAM-2 workspace credential과 역할별 capability를 연결한다.
2. export/write rate limit, telemetry, alert와 관리자 kill switch를 추가한다.
3. schema 변경·자격증명 회전·연결 삭제 시 cache/job/usage index 정리를 검증한다.
4. read/export/edit 지표를 보고 beta 범위를 결정한다.

## 9. 검증 매트릭스

| 층 | 필수 검증 |
| --- | --- |
| 연결 | 소유/비소유 credential, secret 비노출, DNS/SSRF/TLS, 연결 삭제·회전, personal/workspace |
| Schema | public/비허용/system schema, 500 Table·200 Column 상한, cache hit/무효화, View 구분 |
| Browse | type별 filter, identifier injection, bind value, stable cursor, PK 없음, 100행/응답 byte/timeout |
| Export | JSON type/encoding, XLSX type·formula injection, 0/1/50k/초과 행, memory 상한, 취소·만료·권한 재검사 |
| Write | read credential 거부, allowlist, type/constraint, PK 없음, stale version, 한 행 transaction, timeout unknown |
| 권한 | capability와 endpoint 일치, 권한 없는 Workflow usage 비노출, workspace role 변경 즉시 반영 |
| 감사 | 값·secret·SQL 비노출, export/write event 완전성, trace와 사용자 메시지 분리 |
| UI | loading/empty/error/partial, keyboard Grid/Drawer, 200% zoom, mobile 단계형 탐색, 대량 Column |
| 회귀 | 기존 `databaseNode`, API 센터, `/api/database/preview`, Editor schema panel과 57종 DB v2 테스트 |

PostgreSQL 실통합 환경에서 단위·API·브라우저 테스트를 모두 수행한다. SQLite fixture만으로 write transaction,
PostgreSQL type, TLS, `xmin`, statement timeout을 통과했다고 판단하지 않는다.

## 10. 성공 지표와 중단 기준

성공 지표:

- 연결 목록 → 첫 Table 확인까지 성공률과 소요 시간
- Explorer에서 Workflow/Node로 이동한 비율
- browse 요청 성공률, P95 latency, timeout과 schema stale 비율
- JSON/XLSX job 성공률, queue 시간, 평균/상위 row·byte 수
- write preview → commit 전환, conflict·unknown·권한 오류율
- raw SQL 없이 filter DSL로 해결한 탐색 비율
- secret/민감 행이 log·telemetry에 노출된 건수 0

중단 또는 재검토:

- Explorer가 Database Query node의 미리보기보다 사용되지 않으면 SQL console을 추가하지 말고 연결 → Table
  탐색과 Workflow deep link를 단순화한다.
- 대용량 export가 worker latency나 저장 비용을 악화시키면 상한을 올리지 않고 sampling·분할·직접 object
  storage 전달을 검토한다.
- write credential 오사용, tenant 격리 실패, secret/행 값 log 노출이 한 건이라도 발생하면 write beta를
  중단한다. read/export까지 영향받으면 해당 capability도 kill switch로 닫는다.
- stale row conflict가 잦으면 locking을 우회하지 않고 version column 설정과 읽기 갱신 UX를 개선한다.
- Managed Data Store 요구가 반복되면 외부 DB editor에 기능을 덧붙이지 않고 별도 제품 저장소를 설계한다.

## 11. 예상 변경 위치

- `frontend/src/navigation.js`, `frontend/src/App.jsx`: 운영 Database tab과 route
- `frontend/src/pages/OperationsOverviewPage.jsx`: Database summary Card
- 신규 `frontend/src/pages/DatabaseOperationsPage.jsx`: 연결·Schema·Data Grid 화면
- 신규 `frontend/src/components/database/`: ConnectionList, SchemaTree, DataGrid, FilterBuilder, ExportDialog, RowEditDrawer
- `backend/main.py`: usage/browse/export/write API route
- `backend/database_credentials.py`: personal/workspace scope와 capability-safe summary
- `backend/database_diagnostics.py`: primary key·column metadata와 schema version
- 신규 `backend/database_browse.py`: identifier/filter allowlist와 bounded query builder
- 신규 `backend/database_exports.py`: streaming JSON/XLSX job과 ArtifactRef
- 후속 `backend/database_writes.py`: allowlist, preview, optimistic lock, audit
- migration: credential usage index, export job, write binding/policy와 audit metadata
- `backend/test_database_query_v2.py`와 신규 API·export·write PostgreSQL 통합 테스트
