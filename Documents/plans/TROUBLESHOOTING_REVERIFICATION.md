# 트러블슈팅 실행 계획 — 실측 재검증 (2026-09-01)

| 항목 | 값 |
| --- | --- |
| 대상 | [TROUBLESHOOTING_EXECUTION_PLAN.md](TROUBLESHOOTING_EXECUTION_PLAN.md) 의 실측 주장 전수 |
| 방법 | 읽기 전용 병렬 검증 6갈래(0단계·1단계·2단계·3단계·4+5단계·"일부러 하지 않는 것"). 서버·pytest·DB 접근 없이 코드와 `git show` 만 사용 |
| 기준 커밋 | `cd3802d` (계획 작성 커밋 `debc921` 이후) |
| 검증 주장 | 약 110건 |
| 결론 | **남은 견적 40h → 약 42h.** 총량은 비슷하지만 **모양이 바뀌었다** — 0단계는 줄고 2·5단계는 늘었다 |

## 왜 이 문서가 필요한가

계획서의 실측치는 **2026-08-31 기준**이고, 그 전후로 PR #24~#31 이 머지됐다. 계획서 스스로
"커밋 메시지는 고쳤다는데 diff 에 그 변경이 있는지 재확인 필요" 라고 경고한 항목도 있다.
착수 전에 무엇이 이미 해결됐고 무엇이 아직 유효한지 갈라야 견적이 선다.

**이 문서는 계획서를 대체하지 않는다.** 계획서의 판단·순서·근거는 그대로 유효하고, 여기서는
**수치와 줄 번호만** 갱신한다.

---

# 1. 즉시 처리가 필요했던 발견 2건

계획서에 묻혀 있었거나 뒤로 밀려 있었는데, 재검증에서 성격이 달라진 것들이다.

## 1.1 `GET /api/runs/{run_id}` fail-open — **미수정 확정 → 이 라운드에서 수정함**

계획서는 이걸 4단계(10h)에 묶고 "재확인 필요"라고만 적었다. 재검증 결과:

- 커밋 `4b489b7`(PR #26)의 메시지는 "fail-closed 로 뒤집고 고아 로그는 로그 소유자만" 이라고
  적혀 있으나, **그 커밋의 `backend/main.py` diff 훅은 2224 → 2524 로 이 구간을 건너뛴다.**
- `git log --all -S"get_run_details"` → 최신 변경은 보안 라운드 **이전** 커밋.
- 이 라우트를 덮는 테스트 **0건**.

즉 메시지만 있고 변경이 없었다. 권한 검사가 `if project:` 안에만 있어, 프로젝트가 삭제됐거나
`project_id` 가 NULL 인 고아 로그는 **로그인한 아무 계정에게나** `run.result` 전문과 전 노드
`result_data` 를 내줬다.

→ 커밋 `c89e745` 에서 fail-closed 로 수정하고 회귀 테스트를 넣었다. 수정을 되돌리면 테스트가
403 자리에서 200 을 받고 실패하는 것까지 확인했다.

## 1.2 공개 저장소 히스토리에 OpenAI 키 노출 — **폐기 완료**

계획서에 없던 발견이다.

- 커밋 `4bbeecc` 의 `backend/chroma_db/chroma.sqlite3`(904KB 바이너리) 안에 `sk-proj-…` 키
  원문이 들어 있었다. 경위: 어떤 워크플로우의 `httpRequestNode` 가 OpenAI 이미지 API 를 직접
  호출하며 `headers` 에 `"Authorization": "Bearer sk-proj-…"` 를 하드코딩했고, 그 워크플로우가
  RAG 예제 색인에 들어갔으며, 그 sqlite 가 통째로 커밋됐다.
- `11d334d`~`4c12801` 9개 커밋에 걸쳐 추적됐다. `4c12801` 에서 추적 해제됐지만 **히스토리에는
  그대로** 남는다.
- 저장소가 public 이라 누구나 꺼낼 수 있었다. 바이너리 안이라 GitHub 시크릿 스캐닝을 통과했을
  가능성이 높다.

→ 키 폐기 확인(401). 새 키로 교체됨. **운영 서버 `.env` 는 아직 폐기된 키를 쓰고 있어 LLM 기능이
멈춰 있다** — 1단계에서 서버 접속할 때 함께 교체할 것.

---

# 2. 단계별 견적 갱신

| 단계 | 계획 | 재검증 | 변화 이유 |
| --- | --- | --- | --- |
| 0 우회로 + 테스트 인터록 | 6h | **~3h** | AppRunner·conftest·error_log 완료 확인. 이 라운드에서 catch-all 404·pytest.ini 추가 처리 |
| 1 배포 레일 + 로컬 전환 | 10h | **~9.5h** | `.env.example` 이 이미 있어 "만든다"가 "채운다"로 축소 |
| 2 저장 경로 | 9h | **~11h** | 오염 경로가 2개가 아니라 **4개** |
| 3 실행이 사실을 말하게 | 13h | **~13h** | 대상은 커졌으나 접근법 동일 |
| 4 남의 것이 남에게 | 10h | **~9h** | `/api/runs` 를 뺐고, public 프로젝트 노출 판단이 추가됨 |
| 5 실패가 실패로 | 8h | **~12h** | alert 호출이 22개가 아니라 **78건** |

## 2.1 개수 주장 정정 — 전부 **과소** 추정이었다

| 계획서 | 실제 | 확인 방법 |
| --- | --- | --- |
| alert 호출 22개 (성공 5 + 나머지 17) | **78건**. 초록 체크로 렌더 30건, 진짜 성공 6건 제외 시 **오표시 24건** | `grep -rn "\balert(" frontend/src` |
| 컴파일된 적 없는 노드 7종 | **16종** (7종은 "테스트에 이름조차 안 나오는" 최하위 집합. 명단 자체는 정확) | `compile_workflow` 호출 테스트 15파일 대조 |
| `log_step` 을 아예 안 부르는 노드 3종 | **6종** — `breakNode`·`conditionNode`·`distributorNode` 추가 | 51종 생성기 본문 데코레이터 단위 대조 |
| 저장 스냅샷 오염 경로 2개 | **4개** — `project_revisions.py:134`(매 저장마다 적재), `/api/dry-run`(`EditorPage.jsx:1953`) 추가 | 코드 경로 추적 |
| 성공 문구 5곳(DeployModal 포함) | **6곳.** DeployModal 에는 성공 alert 이 없다(오류 1건뿐). 대신 `EditorPage.jsx:2968`('저장되었습니다.')·`:973` 이 빠져 있었다 | 전수 대조 |

**정확했던 숫자**: 코드젠 51종, LEGACY_PATTERNS 7종, 이스케이프 65곳(파일별 분포 11개 전부
일치), seed 템플릿 slackNode 32건, 드리프트 3건, 비-함수 키 3개(`className`·`isPinnedOutput`·
`bindingContext`), `log_step` 중 `error=` 실질 누락 32곳.

## 2.2 줄 번호 표류

`main.py` 계열이 이 라운드 커밋들로 더 밀렸다. 착수 시 grep 으로 재확정할 것.

| 계획서 | 실제(기준 `cd3802d`) |
| --- | --- |
| `graph.py:441` (status='success') | **445** |
| `community_sanitize.py:333` | **330** (계획 작성 시점부터 오기) |
| `editorCommands.js:58` | **59** |
| `isMetadataDirty 2451-2454` | **2452-2455** |
| `update_project main.py:1383-1416` | **1390-1425** |
| 예외 처리기 `main.py:93-102`·`105-109` | **95-104**·**106-110** |
| `integration_nodes.py:311` (paymentLink) | **308** |
| `action_nodes.py:182-193` (delay) | **191-203** |
| `flow_nodes.py:99-142` (loop) | **100-143** |
| `serve_frontend main.py:5576` | 데코레이터 **5589**, def **5590** |
| `/runs`·`/evaluations` 분기 `2413`·`2438` | **2420**·**2446** |
| `delete_project 1353-1382` | **1361-1389** |

**경로 정정 1건**: `components/ErrorBoundary.jsx` → 실제는 **`frontend/src/ErrorBoundary.jsx`**
(`components/` 하위에 없다). 소비자 0건은 사실.

**사실 정정 1건**: 1단계의 "`main.py` 전체에 health/ready grep 0건" 은 부정확하다 —
`main.py:768` 에 `/api/admin/llm-health` 가 있다. 다만 관리자 인증이 걸린 라우트라 무인증
프로브 대용은 안 되므로, "프로브가 없다"는 취지는 유효하다.

---

# 3. "일부러 하지 않는 것" — 결정이 뒤집힌 항목

## 3.1 항목 9 (httpRequestNode SSRF) — **승격 권장**

"리다이렉트 추적 정책·allowlist 설계가 본체인 정책 과제(5h)" 라는 전제가 코드와 맞지 않는다.
정책은 이미 `url_guard.py` 에 구현돼 **webCrawlerNode 에서 돌고 있다**:

- `:124 check_url` — scheme → 호스트 → 해석 IP 순 검사
- `:113-115 _check_ip` — `is_global` 하나로 사설·루프백·링크로컬(169.254.169.254 메타데이터
  포함)·멀티캐스트·예약 대역을 전부 차단
- `:50 MAX_REDIRECTS = 5` + `fetch_text` 가 `allow_redirects=False` 루프로 **매 홉 재검증**
- `:86 requires_partnership` — allowlist 선례가 이미 있다(대상은 `dcinside.com`·`fmkorea.com` 둘)

반면 `httpRequestNode` 실행부는 url_guard 를 **한 번도 부르지 않는다**:
`connectors/services/http_request.py:71 session.request(...)` → `connectors/session.py:201/210
requests.request(...)`.

**다만 단순 배선이 아니다.** 착수 전 결정이 필요한 것 셋:

1. **리다이렉트.** 커넥터 전송은 `requests` 기본값(추적)이라 초기 URL 만 검사하면 30x 로 내부
   주소에 도달할 수 있다. `allow_redirects=False` 로 바꾸면 정상 리다이렉트에 의존하는 기존
   워크플로우가 깨지므로, `fetch_text` 처럼 재검증 루프를 커넥터 계약 위에 다시 구현해야 한다
   (재시도·mock 의미를 유지한 채로).
2. **mock 재생.** `RecordingTransport`(`connectors/mock_runtime.py:145`)가 네트워크를 타지 않는데,
   `check_url` 은 DNS 해석을 하므로 mock 시나리오의 가짜 URL 을 막을 수 있다. mock 컨텍스트에서는
   건너뛰어야 한다.
3. **테스트 영향.** DNS 해석이 들어가면 가짜 호스트를 쓰는 기존 커넥터 테스트가 `DNS_FAILED` 로
   깨질 수 있다. 범위를 먼저 재야 한다.

배선 자체는 `http_request.call` 한 곳이지만 위 셋 때문에 **5h 정책 과제는 아니고, 무인 작업도
아니다.** 1~3h 로 재견적하고 다음 라운드 상위에 둘 것.

## 3.2 항목 8 (드리프트 테스트) — **게이팅 조건이 이미 충족됐다**

"0단계 격리가 정착한 뒤가 안전하다" 의 전제가 PR #28(`3b46a6a`)로 해소됐다.
`backend/conftest.py:26-35` 가 두 겹 가드를 세운다 — `DATABASE_URL` 미설정 시
`sqlite:///./test_run.db` 강제, 운영 호스트가 잡히면 수집 전 `SystemExit(2)`.

남은 선행 과제였던 루트 `pytest.ini` 도 이 라운드에서 추가했다(`325b258`). 따라서 이 항목을
미룰 이유는 격리가 아니라 **"무시 목록 범위를 못 정했다" 하나만** 남는다.

덧붙여 드리프트 32건 중 **1건은 코드로 확정**됐다: `models.py:801` 은 `slug` 를 `unique=True` 로
선언하는데 마이그레이션 `0014_community_templates.py:46` 은 non-unique 인덱스다.

## 3.3 항목 1 (키 로테이션) — 위험 서술이 과장이다

"distinct key_id=1 이라 절반 실패 시 복구 불가" 는 코드가 반증한다.
`credential_crypto.py:48` 이 모든 암호문에 `enc:v1:{key_id}:` 로 키 식별자를 박고, `:66-73` 이
key_id 가 맞는 후보 키로만 복호화한다. 두 비밀이 슬롯에 남아 있으면 **절반만 재암호화된 혼재
상태도 양쪽 다 읽힌다.**

"안 한다" 결정 자체는 유지한다(재암호화 스크립트가 없는 것은 사실). 다만 1단계 78행의 금지
문단은 키가 둘로 갈린 환경을 반영해 **`JWT_SECRET` 과 `CREDENTIAL_ENCRYPTION_KEY` 양쪽**을
대상으로 써야 한다.

## 3.4 항목 6 (코드젠 이스케이프) — 결정 유지, 선행 조사 대상만 정정

숫자 65와 파일별 분포 11개는 전부 정확하고 이 라운드 커밋 뒤에도 불변이다. 다만 선행 판단
사항으로 지목한 "골든 테스트" 는 **존재하지 않는다** — `test_golden_hwpx.py` 는 HWPX 문서
텍스트·패키지 구조를 비교하지 생성 파이썬 소스가 아니다. 실제로 재고할 충돌 범위는
**`assert "…" in src` 형태 단정 38건 / 22파일**이고, 이스케이프 전용 테스트
(`test_codegen_escaping.py`)는 `ast`/`compile` 기반이라 repr 전환에 내성이 있다. 상방 위험
("6h 가 12h 가 된다")을 낮춰 잡을 여지가 있다.

---

# 4. 계획서에 없던 발견

| 발견 | 근거 | 영향 |
| --- | --- | --- |
| 저장할 때마다 `project_revisions` 에 오염 그래프가 한 행씩 적재된다 | `main.py:1418-1420` → `project_revisions.py:134` | 2단계 범위 확대 |
| `/api/dry-run` 도 enriched data 를 그대로 보낸다 | `EditorPage.jsx:1953` | 매 문제검사마다 O(N²) 페이로드. 2단계 네 번째 경로 |
| `visibility == 'public'` 프로젝트는 세 분기 모두 무검사 통과 | `main.py:2420`·`2446`·`2492` | 로그인만 하면 공개 프로젝트 실행 결과 **전문** 열람 가능. "세 분기 통일"로 안 닫힌다 — 별도 판단 필요 |
| `POST /api/없는경로` 는 여전히 405 | catch-all 이 GET 전용 | 이 위치에 POST catch-all 을 두면 뒤에 등록되는 `/api/builder/*`(5623·5669·5712)를 섀도잉한다. 405→404 는 예외 핸들러로 따로 다뤄야 함 |
| `mock_server/server.js:377` 이 호스트 미지정 `app.listen` | Express 기본 0.0.0.0 | 1단계 바인드 작업에 포함 |

---

# 5. 조건부 승격 트리거

계획이 "지금은 안 한다"를 조건부로 걸어 둔 곳. **트리거가 전부 운영 관측이라 로컬에서는 감시할
수 없다** — 서버 접속 시 함께 확인할 것.

| 트리거 | 승격 대상 | 관측 방법 |
| --- | --- | --- |
| 라이브 웹훅 또는 스케줄 프로젝트가 **1건이라도** 생기면 | webhook 이벤트 루프 블로킹(3h) + scheduler misfire(2.5h) → 다음 라운드 1순위 | `projects.graph_data` 에 `is_live=true` AND (webhookNode∨scheduleNode) |
| 업로드 **200개 / 200MB** 상한에 닿는 계정이 나오면 | 업로드 용량 영구 잠김(2.5h) | 임계값은 `upload_security.py:24-25` |
| 3단계 스모크가 선 뒤 | 코드젠 이스케이프 통일(6h) | 저장소 안에서 판정 가능 |
| 통계 재작성 뒤 EXPLAIN | `execution_time` 인덱스(3h) | 술어 불일치는 이미 확인됨 — `statistics_service.py:85-90` 은 `(billable_user_id OR user_id)` 를 쓰는데 후보 조합은 `(project_id, execution_time)` 이었다 |

코드 전제는 전부 살아 있다: `main.py:3094` 의 동기 ORM 전수 조회가 `async` 핸들러 안에 있고,
`database.py:18` 은 풀 크기를 지정하지 않으며, `scheduler.py:12` 는 `misfire_grace_time`·
`coalesce`·`max_instances` 를 하나도 설정하지 않는다. Gemini·Anthropic 어댑터
(`llm/providers/adapters.py:145-155`·`:166-176`)는 **timeout 없이** 생성된다.

---

# 6. 이 라운드에서 처리한 것

| 커밋 | 단계 | 내용 |
| --- | --- | --- |
| `c89e745` | 4→0 | `GET /api/runs/{run_id}` fail-open 수정 + 회귀 테스트 (§1.1) |
| `325b258` | 0 | 루트 `pytest.ini` — 수집 범위·`--strict-markers` |
| `a6e31c4` | 0 | 없는 `/api/` 경로 → 404 JSON |
| `acd4483` | 9→승격 | httpRequestNode 를 url_guard 에 배선 (SSRF, §3.1) |
| `7852a55` | — | 서브프로세스 테스트가 Windows 에서 인터프리터도 못 띄우던 것 수정 |
| `f31d708` | 0 | 인증 강제 테스트의 느슨한 단정 5개 확정 |
| `87a7e1f` | 1 | `/api/health`·`/api/ready` 프로브 |
| `c5563a6` | 1 | 검증 오류가 제출 값을 응답·로그에 되비치던 것 차단 |
| `655e130` | 1 | `JWT_SECRET` 의 `'super-secret-key'` 기본값 제거 |

## 6.1 SSRF 배선에서 실제로 정해야 했던 것 (§3.1 보완)

"배선만 하면 된다" 는 재검증 초기 판단은 절반만 맞았다. 배선 지점은 `http_request.call`
한 곳이 맞지만, 그 전에 셋을 정해야 했다:

1. **리다이렉트.** 초기 URL 만 검사하면 공격자가 자기 서버에서 302 로 내부를 가리켜 우회한다.
   커넥터 전송은 `requests` 기본값(추적)이라 `fetch_text` 의 `allow_redirects=False` 루프를
   그대로 쓸 수 없다 — 그렇게 바꾸면 정상 리다이렉트에 의존하는 기존 워크플로우가 깨진다.
   **requests 의 response 훅**을 쓴다. 훅은 다음 요청을 보내기 전에 발동하므로 내부 주소로는
   요청 자체가 나가지 않는다. 상대 경로 `Location` 은 `urljoin` 으로 푼다.
2. **mock 재생.** `node_definition.new_session` 이 재생 transport 를 끼워 네트워크를 안 타는데
   `check_url` 은 DNS 를 해석한다. `mock_runtime.current()` 이 있으면 건너뛴다.
3. **적용 범위.** 다른 커넥터는 목적지가 정의에 고정돼 있고, 특히 paymentLinkNode 가 목업
   서버(`localhost:3002`)를 부른다. 전송 계층에 일괄로 걸면 그게 막힌다 — httpRequestNode 만
   건다.

## 6.2 Windows 서브프로세스 문제 (계획서에 없던 발견)

`test_connector_cursor.py`·`test_project_revisions.py` 가 자식 환경을
`{"PATH": "/usr/bin:/bin", ...}` 로 넘겨, Windows 에서 자식 파이썬이 아예 뜨지 못했다
(`_Py_HashRandomization_Init` 실패 — 난수 초기화가 `SystemRoot` 를 필요로 한다). 4개 테스트가
이 이유로 실패하고 있었고 리눅스에서는 드러나지 않는다. `conftest.minimal_subprocess_env()`
로 통일했다.

**같은 뿌리가 `python_sandbox.py` 의 `SANDBOX_ENV` 에도 있다.** 다만 그쪽은 POSIX 전용
`resource` 모듈도 함께 쓰므로 `SystemRoot` 만 넣어도 Windows 에서 동작하지 않는다.
pythonNode 는 `PYTHON_NODE_ENABLED=0` 으로 닫아 두었다(커밋 `cd3802d`).

## 6.3 잔여

**0단계**: `main.jsx:2·20` DEV 가드 + `frontend/src/ErrorBoundary.jsx` 를 `App.jsx:65`
`<Routes>` 바깥에 감기 — **브라우저 확인이 필요해 미착수**. nginx `/telegram-webhook/`,
`.env` 권한은 서버 접근 필요.

**1단계 로컬 잔여**: `scripts/deploy.sh`·`rollback.sh`(저장소 전체 `.sh` 0건),
`main.py:81` 의 임포트 시점 `ensure_schema` 분리 + head 비교 기동 가드,
`requirements.lock.txt`, `mock_server/server.js:377` 의 호스트 미지정 `app.listen`.

**결정이 필요해 미착수**: `requirements_linux.txt` 의 4개 누락(python-hwpx·gspread·
google-auth-oauthlib·playwright). 삭제·통합·보완 중 무엇을 택하든 **서버 배포 절차가 바뀐다**
— playwright 를 추가하면 설치 시간과 브라우저 내려받기가 따라온다. 서버에서 어느 노드를
실제로 쓸지 정한 뒤에 결정할 것.
