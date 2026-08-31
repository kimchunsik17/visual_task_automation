# 사이트 전반 트러블슈팅 — 실행 계획

| 항목 | 값 |
| --- | --- |
| 상태 | 계획 확정 · 2026-08-31. **긴급 보안(P0)과 0단계 대부분은 이미 처리됨**(아래 "완료" 참조) |
| 근거 | 12축 병렬 감사 → 적대적 검증 → 계획안 3개 경쟁 → 심사 종합. 발견 원문은 [TROUBLESHOOTING_AUDIT_INTERIM.md](TROUBLESHOOTING_AUDIT_INTERIM.md) |
| 검증 통과 발견 | 약 91건 (CRITICAL 8 · HIGH 20 · MEDIUM 44 · LOW 19) |
| 남은 예상 | **약 40시간 · 7~8세션** (원래 56h/10세션에서 0단계와 P0 보안 대부분이 완료됨) |

## 이 계획을 읽는 법

세 관점(위험 우선·사용자 체감 우선·레버리지 우선)이 각각 계획안을 냈고, 심사위원장이 근거를
직접 재검증해 하나로 종합한 것이다. 심사가 세 안을 모두 고친 **사실 정정**이 본문에 녹아 있다
(예: 유출 UI 키는 5개가 아니라 3개, uploads 교차 열람은 6h가 아니라 파일 이관 없이 3h).

각 단계는 **목표 · 항목(file:line + 추정) · 검증 · 시간 근거 · 이 자리에 둔 이유**로 되어 있다.
검증 항목이 서로 독립적이라, 세션이 끊겨도 "무엇까지 끝났는가"를 항목 번호로 말할 수 있다.

---

## ✅ 이미 완료 (2026-08-31, PR #25~#30, #28)

적대적 리뷰가 P0로 지목한 것과 0단계의 상당 부분을 먼저 처리했다.

**보안 P0 (라이브 실증 후 배포)**
- 인증 없이 남의 워크플로우 실행·배포·열람하던 라우트 5개 (PR #25)
- tokenizer·dynamicInput 임의 파일 읽기(`.env`), `/api/runs` fail-open(887건), 무인증 LLM
  라우트 4개, webhook is_live 우회, 템플릿 게시 IDOR (PR #26)
- `/uploads` 무인증 마운트 → 소유권 라우트, 공유 라우트 owner_type 오분기(972건) (PR #27)
- **pytest 가 운영 RDS 에 붙던 것을 sqlite 로 격리** — conftest 두 겹 가드 (PR #28)
- AppRunnerPage 회귀 — 어제 보안 수정이 죽인 앱 링크 3개 되살림 (PR #30)

**주의**: 위는 라우트별로 막았지만 **원래 감사 계획의 0~5단계 항목 상당수는 그대로 남아 있다.**
특히 `GET /api/runs/{run_id}` 는 심사가 "커밋 메시지는 고쳤다는데 diff 에 그 변경이 있는지
재확인 필요"라고 지적했다 — **4단계 착수 시 실제 코드부터 확인할 것.**

---


# 단계별 계획

> **0단계 대부분과 P0 보안은 위 "완료" 절에서 이미 처리했다.** 각 단계를 그것과 대조하며 읽어라 — 특히 0단계의 AppRunner·conftest·error_log 는 끝났고, nginx telegram-webhook 프록시·catch-all 404·ErrorBoundary·.env 권한·systemd 바인드는 아직 남아 있다.

## 0단계 — 어제의 보안 수정이 앱 링크 3개를 전부 죽였고, 텔레그램은 프록시 규칙 한 줄이 없어 통째로 죽어 있으며, pytest 한 번이 운영 RDS 를 잡는다 — 6h

**목표**: 오늘 사용자가 못 지나가는 길을 뚫고, 이후 모든 단계가 반복해서 돌릴 pytest 를 잠근다. 인프라 공사에 인질로 잡히면 안 되는 한 줄짜리들만 모았다.

**항목**
- `frontend/src/pages/AppRunnerPage.jsx:47` 의 `axios.get(\`/api/apps/${shareToken}\`)` 에 `getAuthHeaders()` 를 넘긴다. 같은 파일 43행에 이미 정의돼 있고 75행 POST 는 쓴다. 커밋 45e8c11 의 `_require_shared_app_visibility` 가 들어오면서 비공개 앱은 소유자 본인도 403 이 되고, `:54` 가 그걸 '앱 정보를 불러오는 데 실패했습니다' 로만 보여 화면이 죽는다. **운영 share_token 3건이 전부 private 이라 현존 앱 링크 전부가 이 한 줄로 부활한다.** (0.5h)
- `/etc/nginx/sites-enabled/app` 에 `location /telegram-webhook/` 을 62행 `/webhook/` 블록과 동일하게 추가. 실측 재확인: location 8개(`/`, `/assets/`, `/api/`, `= /mockserver`, `/mockserver/`, `/mock/`, `/webhook/`, `/uploads/`)에 없다. 변경 전 파일을 손으로 복사해 둔다. (0.5h)
- `main.jsx:2`(unhandledrejection)·`:20`(error) 전역 오버레이에 `import.meta.env.DEV` 가드. 소비자 0건인 `components/ErrorBoundary.jsx` 를 `App.jsx` 의 `<Routes>` 바깥에 실제로 감는다. (1h)
- `main.py:5576` `serve_frontend` 안에서 `full_path.startswith('api/')` 면 `JSONResponse(404)`. 실측 재확인: `GET /api/no-such-route-xyz` → **200 text/html 3657B**. (0.5h)
- `backend/conftest.py` 에 `os.environ.setdefault("DATABASE_URL","sqlite:///:memory:")` 를 `database.py:7 load_dotenv()` 보다 먼저 걸고, 해석된 URL 이 `rds.amazonaws.com` 을 포함하면 `pytest.exit` 로 수집 전 중단. 현재 conftest 는 `DATABASE_QUERY_ALLOW_SQLITE` 한 줄뿐이다(실측). 루트에 `pytest.ini`(testpaths=backend, norecursedirs, --strict-markers, markers=slow_render). 루트 스크래치 4개 정리. (1.5h)
- `backend/test_auth_enforcement.py:20` 을 `test_security_hardening.py:80-84` 의 SCENARIO+subprocess+tmp sqlite 패턴으로 이관. 아울러 `:69·89·95` 의 `in (403,404)`, `:108·113` 의 `not in (401,403,404)` 를 기대 코드 하나로 못 박고 응답 본문 문구까지 확인. (1.5h)
- `chmod 600 backend/.env frontend/.env`(실측 둘 다 `-rwxr-xr-x`), `git rm --cached backend/error_log.txt` + .gitignore 명시 경로, `git log -p` 로 과거 판본 비밀 점검. (0.5h)

**검증**: ① 운영 share_token 3건을 소유자 계정 브라우저로 열어 실행까지 왕복. ② `curl -X POST -H 'Host: wa-pnu.duckdns.org' https://127.0.0.1/telegram-webhook/999999` 가 nginx 405 가 아니라 백엔드 404/422 JSON, 대조군 `/webhook/nonexist` 불변. ③ `/api/community/posts` 를 500 으로 만든 채 `/community/qna` 진입 → 다크레드 대신 페이지 내 오류. ④ `GET·POST /api/no-such-xyz` 양쪽 404 JSON. ⑤ 운영 RDS 에 `SELECT max(id) FROM users, projects` 를 재고 → `pytest backend/test_auth_enforcement.py` → 다시 재서 불변. ⑥ 운영 URL 을 세운 채 같은 명령 → 수집 전 중단.

**시간 근거**: 코드는 6h 중 2h 도 안 된다(한 줄 4개 + conftest). 나머지는 전부 검증 — 브라우저 왕복 3건, nginx reload 후 curl 대조, RDS 전후 SELECT, subprocess 이관 뒤 12케이스 재실행. **검증이 코드의 2배**인 단계다.

**이유**: 이 일곱 개는 배포 레일도 테스트 러너도 필요 없고, 앱 링크는 어제 만든 회귀라 방치할수록 신뢰가 깎인다. conftest 인터록을 여기 끼우는 이유는 1단계 deploy.sh 가 돌릴 첫 관문이 pytest 이기 때문이다 — **파이프라인을 먼저 만들면 파이프라인이 운영을 망가뜨린다**(C 의 논거가 정확하다).

---

## 1단계 — 배포 절차가 사람 기억에만 있어 반영 실패가 200 HTML 로 위장되고, 마이그레이션이 임포트 경로에 있어 6,645회 크래시가 매번 운영 스키마를 건드렸다 — 10h

**목표**: '고쳤다' 와 '서버에 반영됐다' 사이의 간격을 없앤다. 이 단계 이후 모든 변경은 이 레일을 통해 나간다. **로컬 개발 → 서버 배포 전환이 여기다.**

**항목**
- `/api/health`(프로세스만) / `/api/ready`(DB SELECT 1 + alembic 현재 리비전==head + 스케줄러 생존). 실측 재확인: `main.py` 전체에 health/ready/healthz **grep 0건**. nginx 에 `location = /api/health { access_log off; }`. (1h)
- `scripts/deploy.sh` — `export_node_definitions.py --check`(플래그 **이미 존재**, :89 확인) → 재생성 → `npm ci && npm run build`(20초) → `alembic upgrade head` → `systemctl restart fastapi`(5초) → 스모크. 실패 시 즉시 중단. 저장소 전체 `.sh` **0건**(실측). (2.5h)
- 스모크에 **비-/api 라우트 ↔ nginx location 대조**를 넣는다: `app.routes` 순회 → nginx 로 요청 → 응답이 index.html 이 아닌지. 0단계의 텔레그램 누락이 정확히 이것으로 잡혔을 사고다. (deploy.sh 시간에 포함)
- `scripts/rollback.sh` + 절차: 배포 직전 태그, 마이그레이션 포함 배포는 downgrade 대상 리비전을 릴리스 노트에. ADR 로 남긴다. (1h)
- `main.py:81` 의 임포트 시점 `db_migrate.ensure_schema(engine)` 를 걷고, 앱은 '리비전 != head 면 기동 거부' 만. **deploy.sh 의 alembic 단계를 먼저 완주시킨 뒤에 거부 가드를 켠다**(순서를 뒤집으면 서비스가 선다). (1.5h)
- `fastapi.service`: `--host 127.0.0.1`(실측 `LISTEN 0.0.0.0:8000`), `StartLimitIntervalSec=300`/`StartLimitBurst=5`, `OnFailure=` 알림 유닛, PATH 에 `/usr/local/bin:/usr/bin:/bin` 덧붙임(현재 venv/bin 뿐). mock_server 도 127.0.0.1 로. **변경 전 유닛 파일을 손으로 복사하고, 두 바인드 변경을 한 번에 하지 않는다.** ufw allow 22,80,443. (1.5h)
- `requirements.lock.txt` 를 pip freeze 로 승격, 배포는 lock 으로만. `requirements_linux.txt`(== 0개, python-hwpx·gspread·google-auth-oauthlib·playwright 4개 누락) 삭제 또는 include 통합. (1.5h)
- logrotate(daily/14/compress) + journald `SystemMaxUse=500M`/`MaxRetentionSec=30day`. 두 예외 처리기(`main.py:93-102`, `:105-109`)를 파일 append 에서 logging 으로 옮기고 `exc.errors()` 의 `input` 제거 + 마스킹 함수화. (0.5h)
- **로컬 개발 전환**: 로컬용 .env 템플릿(sqlite + 더미 키) + 절차를 Documents 에. 커밋 전 체크리스트에 `export --check` 와 프론트 테스트. **금지 사항 한 문단**: "`CREDENTIAL_ENCRYPTION_KEY` 를 새로 발급해 넣고 재암호화 스크립트를 돌리기 전까지 `JWT_SECRET` 을 절대 바꾸지 말 것 — 바꾸는 순간 `user_api_keys` 7행이 영구 복호화 불가가 되고 되돌릴 스크립트가 저장소에 없다." 실측: `.env` 에 `CREDENTIAL_ENCRYPTION_KEY` 0건, `main.py:73` 기본값 `'super-secret-key'` 그대로. 기본값 제거 + 부재 시 RuntimeError 는 여기서 같이 한다(0.3h). (0.5h)

**검증**: ① deploy.sh 완주, export 를 일부러 어긋나게 두면 --check 가 중단. ② startup 에서 예외를 던지는 브랜치로 restart → 5회 만에 failed, OnFailure 도착, journalctl 에 'start request repeated too quickly'. ③ `/api/ready` 가 리비전을 한 칸 뒤로 돌린 상태를 기동 거부로 구분. ④ `ss -ltn` 에 0.0.0.0:8000 사라짐 + 경로순회 5종을 8000 직접·nginx 양쪽 재실행(현재 8000 직접은 이미 index.html 3657B — 패치 배포 확인됨) + 정상 자산 200. ⑤ docker 클린 컨테이너에 lock 설치 후 `import gspread, playwright; from hwpx.document import HwpxDocument` + `test_hwpx_document_node.py`·`test_golden_hwpx.py` 파일 단위 통과. ⑥ `logrotate -d`.

**시간 근거**: 코드는 health 2개와 catch-all 뿐이고 나머지는 전부 **서버 상태 조작과 그 확인**이다. 강제 실패 리허설(0.5h), docker 클린 설치 검증(0.8h), 바인드 변경 후 사이트 왕복(0.5h)이 시간을 먹는다. 실패하면 사이트 전체가 502 이므로 각 변경을 따로 reload 하고 따로 확인해야 한다 — 이 "따로" 가 비용이다.

**이유**: 0단계 뒤인 이유는 위 다섯 개가 브라우저에서 눈으로 끝나는 한 줄짜리라 인프라 공사에 묶이면 안 되기 때문이고, 2단계 이후가 아닌 이유는 **남은 40h 어치가 전부 "서버에 반영해 눈으로 확인" 을 검증에 포함**하는데 지금 반영 실패가 200 HTML 로 위장되기 때문이다(저장소 메모리에 '빌드 통과 ≠ 화면 정상' 이 재발 이력으로 남아 있다). alembic 분리를 여기서 하는 이유: 기동에 붙어 있는 한 '배포 = 재기동' 이 곧 '운영 스키마 변경' 이고, 4.2일간 6,645회 크래시(실측 `journalctl -u fastapi | grep -c 'Failed with result'` = 6645)가 매 사이클 그것을 실행했다.

---

## 2단계 — enrich 가 심는 비-함수 키 3개가 저장 스냅샷에 섞여 저장 직후에도 영구 '저장 안 됨' 이고, 실행 결과가 노드마다 복제돼 공개 스냅샷으로 샌다 — 9h

**목표**: 제품의 기본 동작(저장)이 매번 거짓 상태를 보여주는 것을 끝내고, 같은 사고가 세 번째로 테스트를 통과하지 못하게 스냅샷 테스트를 뒤집는다.

**항목**
- `EditorPage.jsx:2860-2884` 의 enrich 를 EditorPage 밖 순수 함수(`editorEnrich.js`)로 추출하고, `editorCommands.js:1-17 UI_DATA_KEYS` 를 **그 함수가 심는 비-함수 키 집합**에서 파생시킨다. 최소 대응(`bindingContext`·`isPinnedOutput` 추가, `className` 을 TRANSIENT 에)만 하면 네 번째 재발을 못 막는다. 실측으로 확정한 누출 3개: `className`(항상 붙음 → 기존 프로젝트 저장 시 **100% 재현**), `isPinnedOutput`, `bindingContext`. `onInspect`·`onOpenFormatStudio`·`onInsertFillLLM` 은 `editorCommands.js:58` 의 함수 필터가 이미 거른다. (3h)
- `editorCommands.test.js:47` 을 허용목록으로: `assert.deepEqual(Object.keys(snapshot.nodes[0].data).sort(), [...])`. 입력 픽스처를 enrichedNodes 와 같은 모양으로. 더 좋게는 추출한 프로덕션 함수를 직접 부른다. (1h)
- `frontend/package.json` scripts 에 `"test": "node --test src/"`. 실측: scripts 는 dev/build/lint/preview 뿐이고 `src/` 에 테스트 파일 9개가 러너 없이 방치돼 있다. (0.5h)
- `EditorPage.jsx:2653-2663 stripUIProps` 에 `bindingContext` 추가 — 빠져 있어 AI 채팅 뒤 손대지 않은 노드까지 `isModified`(2677)로 찍힌다. (0.5h)
- `community_sanitize.py:333` 의 `data = dict(node.get("data") or {})` 를 키 화이트리스트로. 저장을 고쳐도 **이미 오염된 그래프**가 `community_templates.py:97/184/459` 공개 경로로 나가는 길이 열려 있다. `update_project`(main.py:1383-1416)에 graph_data 크기 상한. (1h)
- 첫 저장 navigate 재로드 가드: `App.jsx:91` 이 `/editor/:projectId?` 단일 라우트라 `EditorPage.jsx:910` navigate 가 로드 useEffect(deps: `:809`)를 재실행시켜 `resetEditorHistory` 가 undo 를 지운다. `loadedProjectIdRef` 로 막고, 샘플 입력·고정 출력 키를 URL projectId 대신 `:701 currentId` 기반으로 바꾸고 `:new:` 접두사를 첫 저장 시 한 번 rename(`nodeTestFixtures.js:64/70`). (2h)
- `EditorPage.jsx:2456 isDirty` 메모이즈 — 렌더 본문에서 그래프 전체를 깊은 복제 후 `JSON.stringify` 한다. markSaved 시점 지문만 ref 에 두고 `scheduleHistoryCommit`·`onNodeDragStop`(1308)에서만 재계산. 앞의 enrich 정리로 직렬화 대상이 작아진 뒤라 값이 싸진다. (1h)

**검증**: ① 노드 3개 저장 → '저장 안 됨' 소멸·유지, 이후 이동/수정/undo 로 다시 켜짐, 제목·공개범위만 바꿔도 켜짐(`:2451-2454` isMetadataDirty 경로). ② 서버 graph_data 바이트 수를 노드 3/10/30 으로 재서 노드 수에 선형(현재 bindingContext 가 그래프 전체를 담아 O(N²)). ③ 실행 후 저장한 프로젝트를 커뮤니티 게시 → 스냅샷에 실행 결과 문자열 0건 grep. ④ `npm test` 초록, 그리고 **일부러 새 UI 키를 심으면 빨개지는지** — 이것이 '세 번째로 안 난다' 의 유일한 근거다. ⑤ 첫 저장 직후 Ctrl+Z 동작 + AI 하이라이트 유지 + 샘플 입력 유지. ⑥ 40노드/50엣지 3초 드래그 Performance 녹화 전후 비교. ⑦ 운영 DB 읽기 전용으로 `graph_data LIKE '%bindingContext%'` 오염 행 수를 세어 기록한다(정리는 별건).

**시간 근거**: 3h 짜리 enrich 추출이 코드 시간의 대부분이고 — 4000줄 파일에서 클로저 의존 핸들러를 인자로 끌어내는 일이라 참조 안정성이 바뀐다. 나머지 6h 는 브라우저 왕복 3종(저장 배지, undo/샘플입력, 커뮤니티 게시)과 **드래그 프레임률 전후 측정**이다. 측정을 빼면 "저장은 고쳐졌는데 캔버스가 더 무거워졌다" 를 못 잡는다.

**이유**: 유일한 CRITICAL 이면서 발동 조건이 '기존 프로젝트를 저장한다' 뿐이고, 지금 이 순간에도 project_revisions 와 공개 스냅샷을 오염시킨다. 1단계 뒤인 이유는 검증이 서버 왕복을 요구해서다. 3단계보다 앞인 이유는, **저장 경로가 오염된 상태에서 코드젠을 고치면 '실행이 이상하다' 의 원인이 그래프 데이터인지 생성 코드인지 갈라낼 수 없다**(C 의 논거).

---

## 3단계 — 실패가 성공으로 기록되고, 코드젠 51종 중 7종은 컴파일된 적조차 없으며, 목업 결제 페이지가 실제 도메인으로 고객에게 나간다 — 13h

**목표**: 실행 한 번의 결과가 실제로 일어난 일과 일치하게 만든다. 먼저 관문(스모크)을 세우고, 그 관문이 만들어 준 빨간 목록을 작업 목록으로 쓴다.

**항목**
- `backend/test_codegen_smoke.py` — 등록 타입 전부를 parametrize 해서 `start → 노드 → output` 을 `compile_workflow` 하고 (a) 결과가 `Error` 로 시작 안 함 (b) `compile(src)` 성공 (c) 생성 소스에 `log_step('<node_id>'` 포함을 단정. **함정: `node_registry._generators` 는 임포트만으로 0개다 — `import graph` 후 51개(실측 확인). 이 순서를 놓치면 0건 parametrize 로 초록이 된다.** breakNode 는 반복 컨테이너 픽스처로 예외. 모드 있는 생성기는 정의 JSON enum 에서 파생. 순수 문자열 조립이라 네트워크·LLM 0. (2.5h)
- `log_step(error=)` 배선: `action_nodes.py:138`(webCrawler), `integration_nodes.py:254`(toss)·`:311`(paymentLink), `document_nodes.py:65-67`(hwpx 일반 except). 이들이 `error=` 를 안 넘겨 `node_errors/adapters.py:104-112` 의 LEGACY_PATTERNS 7종에 안 걸리는 문구가 `graph.py:441` 에서 `status='success'` 로 기록된다. **패턴 추가가 아니라 error= 를 실제로 넘기는 쪽으로** 고친다(패턴 추측은 다음 노드에서 또 샌다). (1.5h)
- `error_catalog.json` 에 `URL_BLOCKED`·`CRAWL_FAILED` 를 **먼저** 등록 → export 재생성(저장소 규약). `node_generators/` 의 `error_code` 리터럴이 전부 카탈로그에 있는지 세는 테스트. `test_pipeline_channels.py:100-101` 리터럴 assert 갱신. (1.5h)
- log_step 을 아예 안 부르는 노드 제거: `agent_nodes.py:17-124`(multiAgentNode, 파일 전체 0건), `flow_nodes.py:99-142`(loopNode), `action_nodes.py:182-193`(delayNode). 이 셋은 `__node_results__` 에 안 실려 mergeNode(`flow_nodes.py:167`)와 데이터 바인딩에서 값이 조용히 사라진다. (2h)
- `nodeTestFixtures.test.js:81` 을 `generated/nodeDefinitions.json` 에서 파생 + LEGACY_SIDE_EFFECT_TYPES 전체 드리프트 단정(지금 돌리면 3건 즉시 빨강). `nodeTestFixtures.js:132` 의 '정의 우선' 을 백엔드 `dry_run.py:19-45` 합집합과 맞춘다. **단, databaseNode 는 `sql_guard.py:113-134` 가 SELECT/WITH 만 허용하므로 정의의 external-read 가 옳다 — 백엔드 하드코딩 집합에서 빼는 쪽이 맞다**(C 의 판정이 정확하다). 두 판정 대조 테스트를 백엔드에도. (1.5h)
- paymentLinkNode: `integration_nodes.py:289` 의 하드코딩 `http://localhost:3002/mock/payment/create-link` 를 환경변수로, 미설정이면 NodeError 즉시 실패. `mock_server/server.js:8,15-24,281` 이 checkoutUrl 을 PUBLIC_BASE_URL 로 만들고 nginx `:53-54` 가 `/mock/` 을 공개 프록시하므로, kakaoNode 로 고객에게 나가는 링크는 제품 도메인에서 살아 있는 '토스페이먼츠 결제' 페이지다. 공개 `/mock/` 을 내릴지 판단하고 `meta_agent.py:202`·`nodeDocumentation.js:640-648`·`node_knowledge.py:164` 문구 정정. (2h)
- slackNode 를 **미지원으로 정직하게 선언**: 팔레트에서 내리고 정의 sideEffect=none, `nodeDocumentation.js:629-638`·카탈로그 정정, `seed_curated_templates.py` 의 32건 손보기. 코드젠은 `integration_nodes.py:207` 의 print 한 줄인데 정의·문서가 '실제 발송' 이라 말하고, 프론트 판정 때문에 '실제로 외부로 전송합니다' 확인창까지 떠서 기만을 키운다. (2h)

**검증**: ① `pytest test_codegen_smoke.py` 로 51종×모드가 몇 초 안에 끝나고, 무커버리지 7종(googleSheets·paymentLink·toss·multiAgent·break·notion·googleCalendar)이 `-v` 출력에 실제로 들어옴. ② 스모크의 log_step 단정에서 multiAgent·loop·delay 가 빠지지 않음. ③ webCrawler(robots 차단)·toss 401·paymentLink 연결거부·hwpx 실패를 각 1건 재현 → `flow_execution_logs.status='error'`, `summarize_logs` 의 error_count ≠ 0, `/api/statistics` 성공률이 실제로 내려감. ④ 카탈로그 전수 검사 테스트가 미등재 code 를 심으면 빨개짐. ⑤ 공개 도메인 `/mock/payment/...` 를 브라우저로 열어 결정한 처리가 실제로 보임. ⑥ slackNode 가 팔레트에 없고 손본 템플릿 32건이 dry_run 통과. ⑦ databaseNode 가 든 그래프 실행 시 확인창 동작이 백엔드 dry_run 판정과 일치.

**시간 근거**: 스모크 2.5h 중 절반이 breakNode·모드별 픽스처 설계다. log_step 배선은 코드 4줄인데 검증이 1.5h — **실패를 실제로 4번 재현해 DB 행과 통계 수치를 전후로 재야** '성공으로 기록' 이 끝났다고 말할 수 있다. slackNode 2h 의 대부분은 템플릿 32건 손보기와 dry_run 재실행이다.

**이유**: 2단계의 프론트 러너와 정본 파생 테스트가 있어야 이 규모의 변경에서 회귀를 잡는다. 그리고 **로그가 실패를 성공으로 남기는 한 이후 어떤 측정도 믿을 수 없다** — 4단계의 통계 재측정, 5단계의 오류 표현이 전부 이 배선 위에 얹힌다(C 의 논거).

---

## 4단계 — 로그인만 하면 남의 실행 결과 908건(94.7%)이 열리고, 파일명을 알면 남의 자기소개서를 자기 산출물로 만들 수 있다 — 10h

**목표**: 권한 검사가 조건문 안에 갇혀 fail-open 인 구조와, 경로만 가두고 소유자를 안 보는 구조를 닫는다.

**항목**
- `GET /api/runs/{run_id}` 를 fail-closed 로 뒤집는다. 실측 재확인: `main.py:2484` 의 `if project:` 가 권한 검사 전체를 감싸고, project 가 None 이면 `:2491-2513` 이 `run.result` 전문과 모든 `NodeExecutionLog.result_data` 를 무검사 반환한다. 운영 959건 중 project_id NULL 610 + 고아 298 = **908건**. 소유 판정을 `billable_user_id`/`actor_user_id`/`user_id` 로 세우고 셋 다 NULL 이면 404 로 존재를 숨긴다. **이것이 유일하게 남은 미수정 인증 구멍이다** — 커밋 4b489b7 의 메시지는 고쳤다고 적었지만 diff 에 그 변경이 없다. (3h)
- 같은 손수 쓴 visibility 분기가 복사된 `main.py:2413-2417`(/runs)·`:2438-2443`(/evaluations) 을 `project_access` 로 통일. 이 분기들은 workspace 멤버십을 안 봐서 **팀원이 자기 workspace 프로젝트 이력을 못 보는 반대 방향 결함**도 함께 있다. (1.5h)
- 고아 로그 908건 처리: 소유자 후보가 있는 514건 백필, 셋 다 NULL 인 394건은 **봉인 전에 execution_time 분포를 재서 최근 것이 있는지 확인**하고 덤프를 먼저 남긴다. 계속 고아가 생기는 원인(`main.py:1353-1382 delete_project` 가 BotLog 만 지운다, `models.py:178` project_id nullable·FK 없음)도 같이 결정. 전후 `/api/statistics` 재측정. (2.5h)
- **uploads 교차 열람 — 파일 이관 없이 닫는다.** `graph.py:300-310` 의 `_safe_user_path` 와 `template_nodes.py:48-62` 의 `_confine_to_uploads` 는 경로만 가두고 소유자를 안 본다. uploads/ 는 전 사용자 공용 평면 디렉터리이고 운영 디스크에 추측 가능한 이름이 여럿이다. `graph.py:777` 의 `namespace` 에 **이미 `db` 와 `__owner_user_id__` 가 들어 있으므로**(실측), 프리앰블에 `uploaded_files.owner_user_id` 대조를 넣으면 37개 파일을 옮기지 않고 `official_templates/e.py:73` 의 고정 output_path 도 안 깨진다. `artifacts.py:267-271 register_generated_file` 에 소유자 필터(`test_artifact_delivery.py:732` 의 동일 소유자 멱등성은 조건을 나눠 유지). uuid화/하위디렉터리 재구조화는 하지 않는다. (3h)

**검증**: ① 인프로세스 TestClient 로 user_id=2 의 JWT 로 `GET /api/runs/935`(project_id NULL)·`/api/runs/985`(고아 255) → 둘 다 404, 소유자 본인은 200 유지, `ProjectRunsPage.jsx:59` 브라우저 왕복. ② workspace 멤버가 자기 workspace 프로젝트의 `/runs`·`/runs/{id}`·`/evaluations` 를 볼 수 있음(현재는 못 본다). ③ 운영 DB 읽기 전용으로 무검사 대상 수 재측정: 908 → 0. ④ A 소유 파일명을 B 의 fileModifierNode `template_path` 로 지정해 실행 → NodeError, 결과에 A 내용 없음. ⑤ B 가 A 와 같은 output_path 로 register 해도 A 행이 갱신되지 않고 별도 행 생성 + 기존 멱등성 테스트 통과. ⑥ 정상 파일 읽기 경로(자기 업로드) 회귀 없음 + `test_upload_security.py` 통과.

**시간 근거**: 코드는 fail-closed 뒤집기와 프리앰블 한 블록이라 3h 남짓. 나머지 7h 는 **소유 판정이 세 필드로 갈리는 데이터를 실제로 세고 분류하는 일**(2.5h)과 회귀 확인이다. 특히 394건 봉인은 "소유자 본인이 지금 보고 있는 이력이 섞여 있으면 기능 회귀" 라서, 실행하기 전에 분포를 재는 시간이 실제로 든다.

**이유**: 사용자가 화면에서 겪는 고장은 아니지만 알게 되면 가장 크게 잃는 종류다 — 실행 결과에는 그 사람이 넣은 문서 내용과 LLM 출력이 통째로 들어 있고, 가입 제한이 없어(`main.py:681-707`) 구글 계정만 있으면 누구나 토큰을 받는다. 1단계 레일과 3단계 오류 표면이 먼저 있어야 '404 로 봉인' 이라는 변경의 회귀를 안전하게 확인할 수 있다.

---

## 5단계 — 실패 알림의 절반이 초록 체크로 뜨고, 실행 실패가 영어 스택트레이스 원문으로만 남는다 — 8h

**목표**: 3·4단계가 '무엇이 실제로 실패했는가' 를 정확하게 만들었으니, 이제 그것이 화면에서 실패로 보이게 한다.

**항목**
- `CustomAlert.jsx:33` 의 문자열 추측 제거. 지금은 문구에 '실패'/'오류' 가 있는지로 성공/실패 아이콘을 정해 '세션이 만료되었습니다. 다시 인증해주세요.' 가 **초록 체크**로 뜬다. `showAlert(message, { level })` 을 노출하고 `window.alert` 가로채기 기본값을 **error 로 뒤집는다**(실패를 성공으로 보이게 하는 쪽이 반대보다 훨씬 위험하다). 성공 문구 5곳(BotManagerPage:86, SettingsPage:159, WebhookManagerPage:36, SiteFeedbackWidget:101, DeployModal 계열)에만 `level:'success'` 명시하고 나머지 17개 호출 지점을 grep 재확인. (4h)
- 실행 결과 패널 영어 문구 7개(`EditorPage.jsx:1756/1780/1800/2011/2023/2026/1689`) 한국어화. catch 에서 서버가 준 `node_error_v1` 구조가 있으면 `setExecutionErrors` 로 넘겨 NodeErrorCard 가 해결 동작을 그리게 하고, 순수 통신 실패에는 '서버와 통신하지 못했습니다' + 재시도, 원문 detail 은 접힌 '자세히' 로. `:862` alert 도 한국어 + '내 워크플로우로 돌아가기'. (3h)
- 오류 상태를 빈 상태와 분리하는 공용 패턴을 하나 만들어 `ApprovalInboxPage.jsx:31-37`(catch 가 silent 라 실패를 '대기 중 0' 으로 표시, `:159` 새로고침이 `setLoading(true)` 를 안 해 눌러도 화면이 안 변한다)·`ProjectRunsPage.jsx:38-52`·`:56-69`(상세 실패 시 'Loading details...' 영구 고착 또는 직전 실행 상세가 다른 번호 아래 잔존)에 적용. (1h)

**검증**: ① CustomAlert level 3종 렌더 스냅샷 + 세션 만료 알림이 빨간 아이콘. 17개 호출 지점 grep 재확인. ② 실행 API 를 500 으로 만드는 Playwright 시나리오 1건 — 한국어 오류 카드 + 재시도, 원문은 '자세히' 안. ③ `/api/approvals`·`/api/runs` 를 500 으로 만든 상태에서 '없음' 이 아니라 오류 + 재시도, 새로고침이 실제 로딩 상태를 보임. ④ `/api/runs/{id}` 만 500 → 상세 패널이 고착되지 않고 다른 실행을 눌렀을 때 직전 상세가 안 남음.

**시간 근거**: CustomAlert 4h 의 대부분은 코드가 아니라 **22개 호출 지점의 의미를 하나씩 판정하는 일**이다. 기본값을 error 로 뒤집는 순간 성공 알림이 빨갛게 뜨는 회귀가 나므로 전수를 봐야 한다. Playwright 시나리오 3건이 나머지를 먹는다(건당 10~20분 + 재실행).

**이유**: 마지막인 이유는 이 단계가 앞 단계의 결과를 표시하는 층이기 때문이다. 3단계 전에 하면 "실패로 보이게" 만들 대상 자체가 여전히 success 로 기록되고, 4단계 전에 하면 오류 문구가 개선돼도 정작 남의 로그가 열린 채다.

---

# 전체 시간과 세션 수

| 단계 | 시간 | 세션 | 세션 분할 근거 |
| --- | --- | --- | --- |
| 0 우회로 뚫기 + 테스트 인터록 | 6h | 1 | 파일이 흩어져 있지만 항목마다 독립적이고 컨텍스트가 얕다 |
| 1 배포 레일 + 로컬 전환 | 10h | 2 | (a) 레일 제작(health·deploy.sh·rollback·lock) (b) 서버 컷오버(alembic 분리·systemd·바인드)와 강제 실패 리허설. **서버 상태를 바꾸는 작업은 제작과 같은 세션에 넣지 않는다** — 실패 시 되돌릴 판단력이 컨텍스트 압박 아래서 나빠진다 |
| 2 저장 경로 | 9h | 2 | (a) enrich 추출 + 테스트 뒤집기(4000줄 파일을 들고 있어야 한다) (b) navigate 가드 + isDirty + 프레임률 측정 |
| 3 실행이 사실을 말하게 | 13h | 2 | (a) 스모크 + log_step 배선 + 카탈로그 (b) 정본 파생 판정 + paymentLink + slack. **(a) 가 만든 빨간 목록을 보고 (b) 를 시작**하므로 자연 경계다 |
| 4 남의 것이 남에게 | 10h | 2 | (a) runs IDOR + 세 분기 통일 (b) 고아 로그 데이터 작업 + uploads 소유자 확인. 데이터 조작은 코드 변경과 분리 |
| 5 실패가 실패로 | 8h | 1~2 | CustomAlert 전수 판정이 한 세션을 거의 채운다 |

**연속 작업 시간 56h · 세션 10회**(범위 9~11).

세션당 6~9h 를 상한으로 잡았다. 이 저장소에서 한 세션의 컨테이너를 채우는 것은 코드량이 아니라 **동시에 들고 있어야 하는 파일의 크기와 개수**다 — `EditorPage.jsx` 4000줄, `main.py` 5727줄을 각각 들고 있는 작업은 다른 것과 겹칠 수 없다. 실제 회당 비용도 계산에 넣었다: 전체 pytest 3분(쓰지 않는다, 파일 단위만), 프론트 빌드 20초, Playwright 시나리오 10~20분/건.

**세션 경계에서 지킬 것**: 각 단계의 검증 항목은 서로 독립적으로 써 두었으므로, 세션이 끊겨도 "무엇까지 끝났는가" 를 검증 항목 번호로 정확히 말할 수 있다. 단계 안에서 하나가 예상보다 크면 **단계를 늘리지 말고 항목을 잘라 다음 라운드로 넘긴다.**

---

# 일부러 하지 않는 것

**1. CREDENTIAL_ENCRYPTION_KEY 재발급과 키 로테이션(A 안 7h)** — 이 위험은 **운영자가 능동적으로 키를 바꿀 때만** 발현한다. 계획에 넣는 순간 되돌릴 수 없는 조작(7행 재암호화, 되돌릴 스크립트 없음, distinct key_id=1 이라 절반 실패 시 복구 불가)을 스스로 불러온다. 대신 1단계에 **금지 문단 0.3h** 로 못 박는다. B 의 판단이 옳다.

**2. mergeNode 재합류 중복 방출(8h)** — 실측으로 확인된 가장 아픈 결함이다: 제품이 오류 문구로 직접 권하는 해법(mergeNode 를 사이에 두어라)을 그대로 따라도 메일이 두 통 간다(`meta_agent.py:1693` 이 규칙 9에서 mergeNode 를 제외 + `graph.py:519 visited = visited.copy()`). 그런데 본체가 **compile_workflow 재귀 구조 재구성**이고, conditionNode 의 분기별 방출(`flow_nodes.py:67-73`)과 loopNode 의 두 갈래 본문 판별(`:113-137`)을 동시에 만족해야 한다. 3단계의 스모크·log_step 변경과 같은 배에 태우면 회귀 원인을 분리할 수 없다. **51종 스모크가 안정된 뒤 독립 작업으로 떼고, 백로그 최상단에 둔다.**

**3. perf-backend 5건 전부(webhook 이벤트 루프 블로킹 3h, DB 풀 2h, 스케줄러 misfire 2.5h, 봇 이름 캐시 1h, LLM timeout 1.5h)** — 전부 CONFIRMED 지만 오늘 도달 0 이다: 운영 18개 프로젝트에 webhookNode·scheduleNode·telegramTriggerNode 0개, is_live 0개, 8일치 journal 103,462줄에 QueuePool 0건·'was missed by' 0건, graph_data 에 gemini/claude 0건. **조건부 승격 트리거를 명시한다: 라이브 웹훅 또는 스케줄 프로젝트가 1건이라도 생기는 순간 webhook 블로킹(3h)과 scheduler misfire(2.5h)를 즉시 다음 라운드 1순위로 올린다.** 공유 스냅샷 972건 중 147건이 webhookNode 를, 212건이 scheduleNode 를 포함하므로 템플릿 하나 설치 + 라이브 토글이면 살아난다.

**4. perf-frontend 전부(코드 분할 6h, edges 메모 2.5h, IntroPage WebP 2.5h, 사이드바 폴링 1.5h, 뷰포트 판정 1.5h)** — '느리다' 이지 '안 된다' 가 아니다. 게다가 **가장 큰 프레임당 할당원인 enrichedNodes 와 isDirty 를 2단계에서 고친다** — 그 뒤에 40노드/50엣지로 재측정해 수치를 근거로 잡아야 한다. 측정 전 최적화는 하지 않는다.

**5. slackNode 실제 구현(6h)** — 3단계에서 '미지원 선언'(2h)까지만. provider 신설 + delivery_runtime 경유는 트러블슈팅이 아니라 기능 과제이고, 검증에 실제 슬랙 워크스페이스 토큰이 필요해 확보 여부에 계획이 인질로 잡힌다.

**6. 코드젠 이스케이프 63~65곳 py_str 통일(6h)** — 내가 직접 센 결과 `.replace('\\'` 체인이 든 줄은 65개(integration 23, connector 13, core 6, action/agent/template/document 각 5, flow/data/graph 각 1)다. C 가 이걸 4단계 본체로 삼은 판단은 이해하지만, **골든 테스트 충돌 위험이 선행 판단 사항**이다 — repr 기반으로 바꾸면 생성 소스를 문자열로 비교하는 기존 골든이 대량으로 깨질 수 있고, 그러면 6h 가 12h 가 된다. CR 은 UI 로 입력 불가(textarea 정규화, input 값 정화)라 LLM 생성·임포트 경로로만 도달한다. 스모크가 선 뒤 골든 갱신 범위를 먼저 재고 결정한다.

**7. UX 일관성 나머지(노드 강조색 4갈래 6h, API 센터 미정의 토큰 7개 2.5h, conditionNode 라벨 2h, 라우터 404 2.5h, AppRunner 403 세분화 2.5h, 설정 탭 사본 1.5h, 햄버거 가림 1.5h, '앱 실행' 무언 배포 4h, 템플릿 페이지네이션 4h, 검색 디바운스 1.5h, ProjectRuns 한국어화 3.5h)** — 오해를 낳지만 데이터·비밀을 잃지 않는다. 예외로 CustomAlert 와 전역 오버레이만 남겼다(모든 화면이 공유하는 한 곳이라 레버리지가 다르다). **다만 템플릿 목록 limit 은 예외 취급**: 게시 168종 중 138종(82%)이 도달 불가인데 프론트에서 `limit` 을 명시하는 짧은 길이 0.3h 다 — 2단계 작업 중 곁다리로 넣고, 페이지네이션 본체(4h)는 다음 라운드.

**8. 모델↔마이그레이션 드리프트 테스트 + templates.slug unique(3h), 토큰 차감·잔액 게이트 테스트(4h)** — 둘 다 오늘 실피해 증거가 없다(중복 slug 0건, 음수 잔액 미관측). 그리고 둘 다 운영 DB 를 잡을 수 있는 테스트라 0단계 격리가 **정착한 뒤**가 안전하다. 드리프트는 지금 32건이 나오는데 무시 목록을 크게 잡으면 무의미해지고 작게 잡으면 상시 빨강이라, "TEST_POSTGRES_URL 없는 환경에서 어디까지 검사할지" 를 먼저 정해야 한다.

**9. httpRequestNode SSRF url_guard(5h)** — 리다이렉트 추적 정책·allowlist 설계가 본체인 정책 과제다. 이 인스턴스는 IMDSv1 이 꺼져 있어 '한 번의 GET 으로 IAM 자격증명' 은 성립하지 않고 수동 2단계 PUT 경로만 남는다.

**10. 백업 체계·복구 리허설(4h)** — 1단계에 'RDS 자동 백업 보존기간·최근 스냅샷 시각·EBS 스냅샷 정책을 AWS 콘솔에서 확인해 Documents 에 **사실로** 기록'(0.5h)만 남긴다. 손실 규모가 37파일 9.2MB 이고 chroma_db 는 `main.py:143-146` 이 기동 때 증분 재생성하는 파생물이다. 정확한 표현은 '백업이 없다' 가 아니라 '확인 못 했다' 다.

**11. 나머지 데이터 계층(통계 GROUP BY 2h, execution_time 인덱스 3h, soft delete purge 3.5h, 업로드 용량 잠김 2.5h, lease 죽은 코드 1.5h, 템플릿 설치 2트랜잭션 1.5h, record_first_run 커밋 경계 1.5h)** — 현 규모(로그 959행, 프로젝트 18개, 업로드 37파일, 만료 업로드 0건)에서 발현 증거가 없다. **execution_time 인덱스는 감사의 후보 조합 `(project_id, execution_time)` 이 실제 술어 `(billable_user_id OR user_id)` 와 어긋나므로** 통계 재작성 뒤 EXPLAIN 을 다시 보고 정해야 한다. 업로드 용량 영구 잠김은 조건부: 200개/200MB 에 닿는 계정이 나오면 즉시 승격.

---

# 가장 큰 위험과, 그것이 현실이 됐는지 일찍 아는 신호

## 최대 위험 — "고쳤다" 의 증거가 서버가 아니라 로컬에 머무는 것

이 계획은 0단계에서 로컬 개발로 전환하는 준비를 하고 1단계에서 실제로 전환한다. 그 뒤 2~5단계 39h 어치는 전부 로컬에서 작업해 deploy.sh 로 내보낸다. 그런데 **서버에만 있는 상태가 로컬에 없다**: uploads 37파일 9.2MB, chroma_db, .env 의 실제 키, mock_server, nginx location 8개. 여기에 이 저장소 고유의 오답 신호가 겹친다 — 반영 실패가 `GET → 200 text/html 3657B`, `POST → 405` 로 위장돼(실측) 개발자가 프론트부터 뒤진다. 저장소 메모리에 '빌드 통과 ≠ 화면 정상' 이 이미 재발 이력으로 남아 있다.

**이 위험이 현실이 되면**: 2단계 이후 매 단계의 검증이 조용히 "npm run build 가 통과했다" 로 퇴화하고, 4단계쯤에서 "로컬에서는 되는데 서버에서만 실패" 라는 새 종류의 드리프트가 쌓인다. 그 시점에는 원인이 어느 단계에서 들어왔는지 갈라낼 수 없다.

**가장 이른 신호 — 1단계 안에서 나온다**: deploy.sh 의 **비-/api 라우트 ↔ nginx location 대조 스모크를 쓸 수 있는가**. 이걸 쓰려면 "nginx 가 무엇을 프록시해야 하는가" 를 앱에서 파생시킬 수 있어야 한다. 만약 이 항목이 배정한 시간 안에 안 끝나거나, 대조 결과가 `/telegram-webhook/` 말고도 여러 건을 뱉으면 — **레일이 가정보다 얇다는 뜻이고, 그 자리에서 3~5단계 견적을 다시 잘라야 한다.** 반대로 이 스모크가 깨끗하게 서면 나머지 39h 는 같은 레일을 탄다.

**보강 신호 두 가지**: (a) deploy.sh 스모크에 **서버 쪽 파일 의존 노드 1건**(hwpx 또는 fileModifier)을 반드시 넣는다 — 로컬에 없는 상태를 밟는 유일한 자동 검사다. (b) 1단계 (b) 세션에서 **deploy.sh 를 거치지 않은 `systemctl restart` 를 일부러 한 번** 해 본다. alembic 분리 후 그것이 '리비전 != head 기동 거부' 로 멈추는 것이 의도된 동작인데, 운영자가 모르면 장애로 보인다. 런북에 먼저 적고, `/api/ready` 가 그 상태를 구분해 보여주는지 확인한다.

## 2순위 위험 — 테스트 격리가 검사 대상을 바꾼다

0단계가 `test_auth_enforcement.py` 를 subprocess+sqlite 로 옮기면, 그 12케이스가 실제로 검증하던 대상이 **운영 PostgreSQL 스키마에서 인메모리 SQLite 스키마로** 바뀐다. 지금 `compare_metadata` 로 32건의 모델↔마이그레이션 diff 가 있고 드리프트 테스트는 이번에 뺐으므로, 두 스키마가 다른 지점에서 테스트가 통과하는데 운영은 다르게 동작할 수 있다.

**신호**: 이관 직후 같은 12케이스를 **임시 PostgreSQL(`test_database_query_v2.py:443` 의 `TEST_POSTGRES_URL` skipif 패턴)에서도 한 번** 돌려 결과가 같은지 본다. 결과가 갈리면 그 자리에서 드리프트 테스트를 계획에 다시 넣는다(+3h).

## 3순위 위험 — 2단계 enrich 추출이 리렌더 특성을 바꾼다

`EditorPage.jsx` 4000줄에서 `2860-2884` 를 떼면 클로저로 잡던 핸들러가 인자로 나오면서 참조 안정성이 바뀐다. 최악의 경우 "저장은 고쳐졌는데 캔버스가 더 무거워졌다" 가 된다.

**신호**: 드래그 프레임률 전후 측정을 **선택이 아니라 병합 조건**으로 둔다(2단계 검증 ⑥). 추출 전에 40노드/50엣지 3초 드래그를 먼저 녹화해 기준선을 잡아 두지 않으면 이 신호 자체가 없다.

## 4순위 — 3단계 log_step 배선이 통계 수치를 바꾼다

실패가 처음으로 error 로 기록되기 시작하면 `/api/statistics` 의 성공률이 **내려간다.** 이건 버그가 아니라 정상이지만, 관리자 화면 수치가 갑자기 나빠지는 것으로 보인다.

**신호**: 3단계 검증 ③에서 전후 수치를 반드시 기록하고 Documents 에 남긴다. 4단계의 고아 로그 정리도 같은 수치를 움직이므로, 두 변경 사이에 한 번 더 재측정해 어느 쪽이 얼마나 움직였는지 분리해 둔다.

---

# 로컬 개발 → 서버 배포 전환의 위치: 1단계

**0단계가 아닌 이유**: 로컬 개발을 시작하는 순간 가장 먼저 하는 일이 `pytest` 인데, 지금 `database.py:7 load_dotenv()` 가 `backend/.env` 를 읽어 DATABASE_URL 을 운영 RDS 로 만들고 `test_auth_enforcement.py:20` 에는 오버라이드가 없다(실측). 전환의 **전제조건**이지 결과가 아니다. 그래서 인터록만 0단계에 박고 전환 자체는 1단계에 둔다.

**2단계 이후가 아닌 이유**: 2~5단계 39h 가 전부 백엔드/프론트 변경 + 파일 단위 pytest + 재기동 + 화면 확인을 요구하는데, 그 절차가 지금 사람 기억에만 있고 실패가 405/200 HTML 로 위장된다. 네 단계를 그 상태로 진행하면 **매 단계 검증 비용이 배로 든다.**

**전환의 구체적 형태**: 로컬에서 개발 → 파일 단위 pytest + `npm test` + `npm run build` → PR → 서버에서 `scripts/deploy.sh`. 커밋 전 체크리스트에 `export_node_definitions.py --check` 와 프론트 테스트를 넣는다. 서버를 직접 만지는 일은 **0단계의 nginx location 추가와 1단계의 systemd·바인드 변경까지**이고, 그 이후는 전부 파이프라인을 통해 나간다.