# 사이트 전반 트러블슈팅 감사 — 중단 지점 기록

| 항목 | 값 |
| --- | --- |
| 상태 | **중단됨** · 2026-08-31. 12축 중 **7축** 감사 완료, **적대적 검증 이전** |
| 원인 | 서버 CPU 2개 → 동시 실행 상한 `min(16, CPU-2)` = 2. 29개 에이전트 예정에 에이전트당 평균 12분이라 완주에 약 4시간이 필요했다 |
| 발견 | **55건** (CRITICAL 8 · HIGH 23 · MEDIUM 20 · LOW 4) |
| 추정 공수 | 합계 약 178시간 (미검증 추정치) |

## ⚠️ 이 기록을 읽을 때

**아래 발견은 적대적 검증을 거치지 않았다.** 원래 설계는 축별 독립 검증자가 각 주장을 반박하고
(이미 다른 곳에서 막고 있는지, 도달 불가능한 경로인지) 심각도·공수를 재산정하는 단계였는데,
감사 7축이 끝난 지점에서 중단했다. 경험상 이런 감사에서 일부는 과대평가되거나 이미 막혀 있다.

예외: 아래 표시된 **5건은 사람이 직접 코드와 실행으로 확인**했다.

```
POST /api/projects/999999/run        → 404  (인증 없이 핸들러 도달)
GET  /api/apps/nonexistent-token     → 404  (인증 없이 핸들러 도달)
GET  /uploads/<파일명>.webp           → 200  (인증 없이 다운로드)
POST /api/deploy/999999              → 422  (본문 검증까지 도달 = 인증 의존성 없음)
```

## 완료한 축 (7/12)

- `exec-engine` — 실행 엔진과 코드 생성
- `api-auth` — API 표면과 인증·권한
- `editor-state` — 에디터 상태 관리와 경쟁 조건
- `frontend-pages` — 에디터 밖 프론트엔드 화면들
- `db-data` — 데이터 계층과 마이그레이션
- `security-sanitize` — 보안 — 비밀·정화·격리
- `definition-drift` — 정본과 파생물의 드리프트

## 하지 못한 축 (5/12)

| 축 | 무엇을 보려 했나 |
| --- | --- |
| `test-health` 테스트 건강도 | skip/xfail 로 잠든 검사, 개수 하드코딩 같은 취약한 테스트, 커버리지 없는 위험 지점, 프론트엔드 테스트 부재 |
| `perf-frontend` 프론트엔드 성능과 번들 | 단일 청크 2.2MB 분할 경계, 1.9MB PNG 자산, memo 를 무력화하는 렌더, 가상화 없는 목록 |
| `perf-backend` 백엔드 성능과 자원 | 요청 스레드의 긴 작업, async 안의 blocking 호출, 커넥션 풀·타임아웃, 단일 워커 병목 |
| `ops-deploy` 운영과 배포 | 배포 절차의 암묵지, 환경변수 누락 시 조용한 기본값, 무중단·롤백 수단, 로그 회전·관측성, DB 백업 |
| `ux-consistency` 제품 일관성과 사용자 흐름 | 용어 불일치, 시각 규칙 이탈, 개발자 말투 오류 문구, 막다른 흐름, 발견 불가능한 기능 |

그리고 7축의 **검증 단계, 계획안 3개 경쟁(위험 우선·사용자 체감 우선·레버리지 우선), 심사·종합,
누락 비평**이 모두 남았다.

## 다시 돌리려면

워크플로우 스크립트가 남아 있다:

```
/home/ubuntu/.claude/projects/-home-ubuntu/293e95b9-7e6b-475d-92e9-0b22d90a0f45/
  workflows/scripts/site-troubleshooting-audit-wf_c4a50c2c-ff7.js
```

- 같은 세션이 아니면 `resumeFromRunId` 캐시를 쓸 수 없다 — 새로 돌리면 6축을 다시 감사한다.
- **CPU 가 2개인 환경에서는 다시 4시간이 든다.** 로컬(코어가 더 많은 곳)에서 돌리거나,
  축을 나눠 여러 번 돌리거나, 검증을 축별 12개에서 묶음 4개로 줄이는 편이 낫다.
- 이미 끝난 7축은 아래 발견 목록으로 대체하고, **남은 5축 + 전체 검증**만 돌리는 것이 가장 싸다.

## 분류 분포

| 분류 | 건수 |
| --- | --- |
| correctness | 16 |
| security | 12 |
| data-integrity | 9 |
| ux | 7 |
| perf | 4 |
| ops | 4 |
| maintainability | 3 |

---

# 발견 목록 (미검증)

## API 표면과 인증·권한 (backend/main.py 176개 @app 라우트 + workspaces/community/project_access 권한 판정)

> 감사 범위: 실제로 읽은 것: backend/main.py 의 @app 데코레이터 176개를 스크립트로 전부 추출해 인증 의존성별로 표를 만들었다(get_current_user_required 108, get_current_user 21, staff 9, admin 7, sudo 7, 의존성 없음 24). 의존성 없는 24개는 모두 본문까지 읽었다(그 중 POST /execute L2907 은 deploy_project 의 f-string 안 생성 코드라 실제 라우트가 아니었다 — 오탐). 깊이 읽은 파일: main.py 의 인증 헬퍼(183~235, 560~600), 프로젝트/실행/배포/앱 계열(1019~1230, 1596~1830, 1863~2000, 2318~2470, 2880~3100), 워크스페이스(3686~3835), 커뮤니티(3833~4200, 4259~4400, 4477~4800, 5110~5260), backend/project_access.py 전문, backend/workspaces.py 전문, backend/community_safety.py(has_staff_access 부근), community_posts.py(can_view/accept/delete), community_templates.py(publish/publish_version/evaluate_gate/list_templates), graph.py 의 run_w

### 🔴 CRITICAL · POST /api/execute 가 요청 본문의 project_id 를 검증 없이 믿어, 비로그인 요청에도 그 프로젝트 소유자의 자격증명을 복호화해 실행한다

- **위치**: `backend/main.py:1864`
- **분류**: security · **추정** 5h · **감사자 확신** high
- **근거**: main.py:1863-1870 — `@app.post("/api/execute")` / `def execute_flow(payload: FlowPayload, db=..., user=Depends(get_current_user))`. get_current_user 는 토큰이 없으면 None 을 돌려주고(main.py:183-185) 라우트는 `if user and user.token_balance <= 0` 만 본다 — 즉 비로그인도 통과한다. payload.project_id 는 FlowPayload 의 자유 입력이다(main.py:149-151). 이 값이 그대로 run_workflow 로 넘어가고, graph.py:702-712 에서 `project = db.query(models.Project).filter(models.Project.id == project_id).first()` → `owner_user_id = project_access.credential_owner_for(db, project)` → `api_keys = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == project.user_id).all()` → `decrypt_secret(k.api_key)` 로 `{{API_CENTER:*}}` 자리를 **평문 비밀값으로 치환**한다. DB 자격증명도 같은 기준이다: database_credentials.py:160 `row = get_owned(db, owner_user_id, credential_id)` — owner 는 caller 가 아니라 caller 가 적어 보낸 project_id 에서 나온다. 호출자가 그 프로젝트에 권한이 있는지는 어디서도 확인하지 않는다(project_access.c
- **사용자가 겪는 장면**: 공격자가 로그인도 없이 `POST /api/execute` 에 `{"project_id": 7, "nodes":[{"id":"a","type":"databaseNode","data":{"connectionString":"{{API_CENTER:database}}","query":"select * from members"}}],"edges":[]}` 를 보낸다. 서버는 7번 프로젝트 소유자의 DB 자격증명을 복호화해 접속하고, 조회 결과를 응답 result 에 담아 돌려준다. 같은 방식으로 nodes 에 kakaoNode(`{{API_CENTER:kakao_token}}`)를 넣으면 피해자 계정으로 카카오 메시지가 발송되고(graph.py:715-720 이 만료 임박 토큰을 refresh 까지 해 준다), llmNode 에 `{{API_CENTER:openai}}` 를 넣으면 피해자 API 키로 LLM 호출이 과금된다. 피해자에게는 자기 API 센터 자격증명이 쓰인 실행 로그만 남고 누가 시켰는지는 남지 않는다(billable_user_id = None).
- **수정안**: execute_flow 를 get_current_user_required 로 올리고, payload.project_id 가 있으면 `project_access.require(db, user, project, project_access.RUN)` 를 통과시킨 뒤에만 그 project_id 를 run_workflow 로 넘긴다(권한 없으면 project_id 를 버리고 익명 실행으로 강등하는 편이 안전하다). 정본 표에 RUN/DEPLOY 가 선언돼 있는데 강제하는 호출부가 0곳이라는 사실(project_access.py:31-37 vs main.py 의 can 호출 3곳)을 같이 메운다. 회귀 확인: 에디터 실행(부분/범위/승인 재개), 앱 러너, 스케줄·웹훅 경로.

### 🔴 CRITICAL · POST /api/deploy/{project_id} 가 인증 없이 남의 프로젝트 deploy_mode 를 바꾸고, 컴파일된 파이썬 소스에 봇 토큰을 평문으로 담아 돌려준다

- **위치**: `backend/main.py:2883`
- **분류**: security · **추정** 2.5h · **감사자 확신** high
- **근거**: main.py:2883-2885 — `@app.post("/api/deploy/{project_id}")` / `async def deploy_project(project_id: int, payload: DeployPayload, db=Depends(get_db))`. 인증 의존성이 아예 없다. 본문은 곧바로 `project.deploy_mode = payload.mode; db.commit()`(2893-2894) 을 하고, mode 가 fastapi/mcp 면 `compile_workflow(project.graph_data...)` 결과를 `{"code": ...}` 로 반환한다(2896-2941). 생성기는 노드 data 를 컴파일 타임 리터럴로 굽는다: node_generators/integration_nodes.py:124 `bot_token = node.get('data', {}).get('botToken','')...` → 137 `token=\"{bot_token}\"`, 같은 패턴이 텔레그램에도 있다(154, 158). 실측 확인: backend/venv/bin/python 으로 discordNode/telegramNode 를 넣어 compile_workflow 를 호출한 결과 `DISCORD TOKEN LEAKED: True`, `TELEGRAM TOKEN LEAKED: True`. 봇 토큰은 실제로 graph_data 안에 산다(main.py:3299-3302 update_bot_token 이 `trigger_node['data']['botToken']` 에 쓴다). 대조: 같은 값을 화면에 보여주는 reveal-token 은 로그인 + Google 재인증을 요구한다(main.py:3252-3266).
- **사용자가 겪는 장면**: 공격자가 `curl -X POST https://<host>/api/deploy/1 -d '{"mode":"fastapi"}'` 를 project_id 1..N 으로 반복한다. 토큰 하나 없이 각 프로젝트의 전체 실행 로직(프롬프트, 수신자 주소, 채널 ID)과 디스코드/텔레그램 봇 토큰 평문을 응답으로 받는다. 그 토큰으로 피해자의 봇을 자기 서버에 붙이면 피해자 서버가 재시작될 때까지 봇 대화가 공격자에게 흐른다. 부수 피해로 모든 프로젝트의 deploy_mode 가 조용히 바뀌어, 관리 화면의 배포 상태 표시가 실제와 어긋난다.
- **수정안**: 라우트에 get_current_user_required 를 붙이고 `project_access.require(db, user, project, project_access.DEPLOY)` 로 막는다. 프론트 호출부는 소유자용 DeployModal 한 곳뿐이므로(frontend/src/DeployModal.jsx:40) 호환 부담이 없다. 더불어 코드 응답에서 비밀값을 빼는 것을 별도로 다뤄야 한다 — 생성 소스에 토큰 리터럴을 굽는 대신 databaseNode 처럼 reference 를 남기고 실행기가 소유자 기준으로 해석하는 방식(graph.py:736-744 의 v2 패턴)으로 옮기는 것이 정공법이다.

### 🔴 CRITICAL · 프로젝트 실행 라우트 두 개(/api/projects/{id}/run, /api/deploy/{id}/execute)가 소유·공개범위 검사 없이 정수 id 만으로 남의 워크플로우를 실행한다

- **위치**: `backend/main.py:1758`
- **분류**: security · **추정** 3.5h · **감사자 확신** high
- **근거**: main.py:1758-1762 — `@app.post("/api/projects/{project_id}/run")` / `def run_project_workflow(project_id: int, request: Request, payload=None, db=Depends(get_db))`: 프로젝트를 id 로 찾은 뒤(1760) Authorization 헤더를 '있으면 파싱'만 하고(1766-1774, except 는 pass), visibility 도 소유자도 보지 않고 곧장 `run_workflow(nodes, edges, db=db, ..., project_id=project.id)` 를 부른다(1794). 유일한 관문은 `owner.token_balance <= 0`(1777-1779). main.py:2944-2946 의 `/api/deploy/{project_id}/execute` 도 같다 — `user=Depends(get_current_user)`(옵션) + 소유 검사 없음 + `if user and user.token_balance <= 0`. 대조 두 개가 같은 파일 안에 있다: (1) 바로 위 `/api/apps/{share_token}/execute` 는 private/friends 를 명시적으로 막는다(main.py:1703-1706), (2) 익명 업로드 규칙은 "공개된 프로젝트에 한해" 로 못박혀 있다(main.py:226-243, "비공개 프로젝트 id 를 찍어보며 남의 용량을 소모시키는 것을 막는다"). run 계열만 그 규칙 밖에 있다. 실행은 소유자 자격증명으로 이뤄지고(graph.py:708-712) 과금은 소유자에게 붙는다(main.py:1799-1808 `billable_user_id=project.user_id`).
- **사용자가 겪는 장면**: 공격자가 `POST /api/projects/3/run` 을 id 1부터 눌러 본다. 3번이 '매일 아침 거래처에 카카오 알림톡 보내기' 라면 요청 한 번마다 실제 발송이 일어나고, 요금과 실행 로그는 소유자에게 쌓인다. 노드에 데이터베이스 쓰기나 시트 추가가 있으면 남의 데이터가 변경된다. 소유자가 알아채는 시점은 토큰이 0이 되어 자기 워크플로우가 멈출 때다 — 그리고 로그의 actor_user_id 는 None 이라 누가 눌렀는지 추적할 수 없다.
- **수정안**: 두 라우트 모두 `project_access.can(db, user, project, project_access.RUN)` 을 통과해야 실행하도록 바꾼다. 익명 앱 실행이 필요한 경우(배포된 커스텀 앱)는 project_access 를 우회하지 말고 `visibility == 'public'` 또는 share_token 경유로만 허용하고, 그때도 익명 호출 rate limit 을 붙인다. UIEngine 이 Bearer 를 이미 실어 보내므로(frontend/src/components/UIEngine.jsx:425-428) 로그인 사용자 경로는 그대로 동작한다.

### 🟠 HIGH · GET /api/runs/{run_id} 는 실행 로그가 가리키는 프로젝트가 없으면 권한 검사를 통째로 건너뛴다 — 실측 933건 중 882건(94%)이 무검사 상태다

- **위치**: `backend/main.py:2390`
- **분류**: security · **추정** 3h · **감사자 확신** high
- **근거**: main.py:2390-2404 — 로그를 id 로 찾은 뒤 `project = db.query(models.Project).filter(models.Project.id == run.project_id).first()` 하고 **`if project:` 안에서만** visibility 검사를 한다. project 가 None 이면 아무 검사 없이 run.result 전문과 노드별 result_data·error_message 를 반환한다(2405-2429). project_id 는 FK 도 cascade 도 없는 맨 Integer 컬럼이라(models.py:178) 프로젝트가 지워지면 로그가 고아로 남고, 에디터에서 저장 전 실행하면 애초에 NULL 로 기록된다. 운영 DB 읽기 전용 조회 실측: flow_execution_logs 총 933건, project_id NULL 610건, 존재하지 않는 project_id 를 가리키는 고아 272건 → 882건(94.5%)이 검사 없이 열린다. node_execution_logs 592건이 여기에 딸려 있다. 덧붙여 project 가 있어도 검사가 낡았다 — project_access 대신 손으로 쓴 private/friends 분기라(2396-2401) **public 프로젝트의 실행 이력은 로그인한 아무나 다 읽는다**. 같은 낡은 분기가 /api/projects/{id}/runs(2325-2331)와 /evaluations(2352-2358)에도 복사돼 있다.
- **사용자가 겪는 장면**: 아무 계정으로 로그인한 사람이 `GET /api/runs/1` 부터 순차로 훑는다. 응답에는 다른 사용자가 에디터에서 돌린 실행의 결과 문자열 전문과 노드별 출력이 들어 있다 — 크롤링해 온 원문, DB 조회 결과, 생성한 메일 본문, 그리고 오류 메시지가 그대로 보인다. 계정을 탈퇴한 사용자(프로젝트는 삭제되지만 로그는 user_id 만 NULL 로 바뀌어 남는다, main.py:1021-1040)의 실행 내용도 영구히 조회 가능하다.
- **수정안**: `if project:` 을 `if project is None: raise 404` 로 뒤집는다(권한을 확인할 수 없는 로그는 보여주지 않는다). 그리고 소유 판정을 run.billable_user_id/actor_user_id 로도 걸어 프로젝트가 사라진 로그를 본인만 보게 한다. 남아 있는 손수 쓴 private/friends 분기 세 곳(2325, 2352, 2396)을 project_access.can(..., VIEW) 로 통일하고, public 프로젝트에 실행 이력 열람까지 딸려 가지 않게 별도 액션으로 분리한다.

### 🟠 HIGH · has_successful_run 이 owner_user_id 를 인자로 받고도 쓰지 않아 '본인 계정 실행 성공' 게이트가 무의미하고, 그 결과 남의 비공개 워크플로우를 내 템플릿의 새 버전으로 공개 게시할 수 있다

- **위치**: `backend/community_templates.py:70`
- **분류**: correctness · **추정** 2.5h · **감사자 확신** high
- **근거**: community_templates.py:70-83 — `def has_successful_run(db, project_id, owner_user_id)` 인데 쿼리는 `filter(FlowExecutionLog.project_id == project_id, FlowExecutionLog.outcome == OUTCOME_SUCCESS)` 뿐이다. owner_user_id 는 어디에도 안 쓰인다(billable_user_id/actor_user_id 조건이 없다). 그런데 이 함수의 docstring 은 "자기도 안 돌려본 워크플로우는 템플릿이 될 수 없다" 이고, evaluate_gate 는 그 결과를 `"label": "본인 계정 실행 성공"` 으로 사용자에게 표시한다(community_templates.py:125-127). 게이트가 검사한다고 표시하는 것을 실제로는 검사하지 않는다. 여기에 라우트 쪽 구멍이 겹친다: main.py:4115-4131 `publish_template_version` 은 `project = db.query(models.Project).filter(models.Project.id == payload.projectId).first()` 만 하고 소유자를 확인하지 않으며, community_templates.py:438-465 publish_version 도 template.owner_id 만 보고 project.user_id 는 보지 않는다. 대조: 같은 파일의 최초 publish 는 `project.user_id != owner_user.id` 를 막고(community_templates.py:172-173), revise 라우트는 주석까지 달아 막는다(main.py:3999-4002 "남의 프로젝트를 가리켜 그 내용을 공식 템플릿으로 밀어넣지 못하게
- **사용자가 겪는 장면**: 공격자가 자기 프로젝트로 템플릿 하나를 정상 게시한다. 그다음 `POST /api/community/templates/<my-slug>/versions` 에 `{"projectId": <피해자 프로젝트 id>, "version": "1.0.1"}` 을 보낸다. 게이트의 '본인 계정 실행 성공' 은 피해자 자신이 한 번이라도 성공 실행한 로그로 통과되고(owner_user_id 미사용), 소유 확인이 없으므로 피해자의 비공개 그래프가 정화만 거쳐 공개 템플릿 v1.0.1 로 게시된다. 피해자는 자기 워크플로우 구조·프롬프트·수신자 구성이 커뮤니티 템플릿 목록에 올라간 것을 나중에 발견한다. 필요하면 공격자는 앞의 /api/execute 구멍으로 성공 실행 로그를 직접 만들어 낼 수도 있다.
- **수정안**: has_successful_run 쿼리에 `FlowExecutionLog.billable_user_id == owner_user_id`(레거시 행 호환을 위해 user_id 도 OR)를 추가한다 — 인자를 받는 함수가 그것을 무시하지 않게. 그리고 publish_version 에 `project.user_id != owner_user.id → TemplateError` 를 넣어 revise 와 같은 규칙으로 맞춘다. 검증: 게이트 관련 테스트(backend/test_community_templates*.py) 파일 단위로 실행.

### 🟠 HIGH · GET /api/apps/{share_token} 이 공개범위를 확인하지 않고 graph_data 전체를 반환한다 — 바로 아래 같은 토큰의 execute 는 확인한다(GET/POST 비대칭)

- **위치**: `backend/main.py:1669`
- **분류**: security · **추정** 2h · **감사자 확신** high
- **근거**: main.py:1669-1682 — share_token 으로 프로젝트를 찾아 `visibility` 값과 함께 `"graph_data": project.graph_data` 를 그대로 반환한다. 인증도 공개범위 판정도 없다. 반면 바로 아래 `POST /api/apps/{share_token}/execute` 는 `if project.visibility == 'private' and (not user or project.user_id != user.id): 403`, friends 면 친구 관계까지 확인한다(main.py:1703-1710). 즉 실행은 막고 열람은 안 막는다. graph_data 안에는 봇 토큰이 평문으로 산다(main.py:3299-3302 가 `trigger_node['data']['botToken']` 에 저장), 그래서 동일한 값을 화면에 노출하는 reveal-token 이 Google 재인증을 요구하는 것과 정면으로 어긋난다(main.py:3252-3266). share_token 은 프로젝트를 비공개로 되돌려도 지워지지 않으며(main.py:1604-1612 은 없을 때만 만든다), 공개 프로젝트의 share_token 은 인증 없는 목록에서 그대로 배포된다(main.py:1081).
- **사용자가 겪는 장면**: 사용자가 '친구 공개' 로 앱 링크를 한 명에게 보낸다. 그 링크(또는 카톡방에 전달된 링크)를 받은 누구든 `GET /api/apps/<token>` 만 호출하면 로그인 없이 워크플로우 전체 구조와 디스코드/텔레그램 봇 토큰 평문을 얻는다. 실행은 403 으로 막히지만 이미 토큰이 넘어갔으므로 봇을 가로챌 수 있다. 예전에 공개로 두었다가 비공개로 바꾼 프로젝트도 옛 링크로 계속 열린다.
- **수정안**: execute 와 동일한 판정을 GET 에도 적용한다(가능하면 project_access.can(..., VIEW) 로 통일). 그리고 앱 뷰어가 실제로 필요한 필드만 내려준다 — 뷰어는 입력 스키마와 제목만 필요하고 graph_data 전체는 필요하지 않다. visibility 를 private 으로 바꿀 때 share_token 을 무효화하는 동작도 함께 넣는다.

### 🟡 MEDIUM · 인증 없는 /webhook/{endpoint_id} 가 매 요청마다 projects 테이블 전체와 모든 graph_data JSON 을 메모리로 읽는다

- **위치**: `backend/main.py:2986`
- **분류**: perf · **추정** 3h · **감사자 확신** high
- **근거**: main.py:2984-2986 — `@app.api_route("/webhook/{endpoint_id:path}", methods=["GET","POST"])` 안에서 첫 줄이 `projects = db.query(models.Project).all()` 이고, 이어서 모든 프로젝트의 graph_data 를 파이썬에서 순회하며 webhookNode 의 URL 을 문자열 비교한다(2988-3010). 인덱스도 상한도 없고, 매칭 실패 시에도 전체 스캔을 끝낸다. 게다가 루프 안에서 `print(f"Checking project {p.id}: ...")` 를 프로젝트마다 찍는다(3005). 같은 부류로 인증 없는 main.py:1080-1081 `/api/projects/public` 이 `.all()` 로 상한 없이 전부 반환하며 각 항목에 share_token 까지 실어 준다(커뮤니티 목록은 limit 을 max(1, min(limit,100)) 으로 조이고 있어서 규칙이 갈라져 있다 — community_templates.py:731).
- **사용자가 겪는 장면**: 프로젝트가 수천 개로 늘어난 뒤, 누군가 존재하지 않는 엔드포인트로 `/webhook/aaa` 를 초당 수십 번 때린다. 요청마다 전체 프로젝트 + graph_data JSON 역직렬화가 일어나 커넥션 풀과 CPU 를 먹고, 정상 웹훅(텔레그램·외부 SaaS 콜백)이 타임아웃되어 재전송 폭풍이 뒤따른다. 운영자는 로그에 'Checking project ...' 만 수십만 줄 쌓인 것을 보게 된다.
- **수정안**: webhook 엔드포인트 매칭을 조회 시점 전체 스캔에서 저장 시점 인덱스로 옮긴다 — 프로젝트 저장/라이브 토글에서 (endpoint, project_id, node_id) 행을 별도 표에 유지하고 여기서는 그 표를 한 번 조회한다. 루프 안 print 는 제거하거나 debug 로 내린다. /api/projects/public 에는 limit 상한과 커서를 넣고 응답에서 share_token 을 뺀다.

### ⚪ LOW · 인증 없는 실행 라우트들이 예외 원문을 그대로 500 detail 로 돌려줘, 전역 핸들러가 감추려던 내부 정보가 빠져나간다

- **위치**: `backend/main.py:1818`
- **분류**: security · **추정** 1.5h · **감사자 확신** high
- **근거**: main.py:94-105 의 전역 예외 핸들러는 의도적으로 `{"message": "Internal Server Error", "error_id": ...}` 만 주고 상세는 파일에만 쓴다. 그런데 개별 라우트가 그 앞에서 원문을 돌려준다: main.py:1818 `/api/projects/{project_id}/run` 의 `raise HTTPException(status_code=500, detail=str(e))`, main.py:1752 `/api/apps/{share_token}/execute` 의 같은 줄, main.py:3080 `/webhook/{endpoint_id}` 의 `JSONResponse(status_code=500, content={"status":"error","detail": str(e)})`. 세 라우트 모두 인증 의존성이 없다(각각 1758-1759, 1687-1688, 2984-2985). run_workflow 는 생성 코드를 exec 하므로 예외 문자열에 SQLAlchemy 오류(접속 대상 호스트·DB 이름), 파일 경로, 서드파티 API 응답 본문이 실려 나온다.
- **사용자가 겪는 장면**: 공격자가 `POST /api/projects/3/run` 을 일부러 잘못된 입력으로 눌러 500 을 유도한다. 응답 detail 에 `(psycopg2.OperationalError) could not translate host name "db-prod.internal"` 같은 문구가 그대로 담겨, 내부 호스트명·DB 이름·설치 경로가 노출된다. 이것이 위의 자격증명 대여 구멍과 결합하면 다음 공격의 정찰 자료가 된다.
- **수정안**: 세 곳의 `str(e)` 를 전역 핸들러와 같은 형태(고정 문구 + error_id)로 바꾸고 상세는 error_log 와 실행 로그(error_message)에만 남긴다. NodeError v1 이 이미 안전한 사용자 문구/safe_details 를 갖고 있으므로(node_errors) 실행 실패는 그 채널로 내려주면 된다.

## 실행 엔진과 코드 생성 (backend/graph.py compile_workflow, node_generators/*, workflow_security.py, dry_run.py)

> 감사 범위: 실제로 읽고 검증한 것: backend/graph.py 전체(800줄), backend/workflow_security.py 전체, backend/dry_run.py 전체, backend/node_registry.py, node_generators/{core,flow,action,data,agent,document,ui}_nodes.py 전체, connector_nodes.py 1~320줄, integration_nodes.py 1~320줄, node_errors/adapters.py, meta_agent.py 의 validate_flow 관련 구간(1485/1712~1845/2595~2615), main.py 의 /api/execute(1863~1935), frontend/src/customNodes.jsx 의 loop·condition·multiAgent·notion 구간, node_definitions/delayNode.json, official_templates(107종) 전수 스캔.

정적 분석만으로 끝내지 않고 backend/venv/bin/python 으로 compile_workflow 를 직접 호출해 생성 소스를 눈으로 확인했다(LLM 호출 없음). 검증에 쓴 임시 스크립트는 /tmp/claude-1000/-home-ubuntu/293e95b9-7e6b-475d-92e9-0b22d90a0f45/scratchpad/{t1

### 🟠 HIGH · tools 핸들에 연결된 노드가 제어 흐름으로도 도달하면 compile_workflow 가 UnboundLocalError 로 죽고, 사용자에겐 실행 로그 한 줄 없이 파이썬 오류 문구만 뜬다

- **위치**: `backend/graph.py:494`
- **분류**: correctness · **추정** 2h · **감사자 확신** high
- **근거**: generate_block 첫 부분:
```python
494:        if node_id in tool_node_ids and node.get('type') != 'multiAgentNode':
...
505:        node = node_dict.get(node_id)
```
505행이 `node` 를 대입하므로 파이썬은 `node` 를 generate_block 의 지역 변수로 만든다. 그래서 494행의 `node.get(...)` 은 **항상** 대입 전 접근이다 — `node_id in tool_node_ids` 가 참이 되는 순간 무조건 터진다. 494~502행 본문은 `pass` 와 주석뿐이어서("wait, if it's explicitly called...") 아무 일도 하지 않는데 예외만 낸다.

실제 호출:
```
$ venv/bin/python  # start(s1) → llm(tool1) → (tools) → multiAgent(ma1)
UnboundLocalError: cannot access local variable 'node' where it is not associated with a value
  File "/home/ubuntu/app/graph.py", line 526, in generate_block
  File "node_generators/flow_nodes.py", line 13, in generate_start_node
```
이 예외는 compile_workflow 가 반환하는 "Error: ..." 문자열이 아니라 그냥 전파된다. main.py:1907 의 `except Exception as e` 가 받아 `logs = []` 로 덮고(main.py:1911) 문구만 만든다.
- **사용자가 겪는 장면**: 사용자가 멀티 에이전트 워크플로우를 만든다. multiAgentNode 에 전문가 llmNode 두 개를 tools 포트로 붙인 뒤, "전문가에게도 시작 입력을 주자"고 생각해 startNode 에서 그 llmNode 로 선을 하나 더 긋는다. 실행을 누르면 결과창에 `❌ 워크플로우 실행 중 오류가 발생했습니다: cannot access local variable 'node' where it is not associated with a value` 만 뜨고, 실행 로그 탭은 완전히 비어 있다(logs=[]). 어느 노드가 문제인지, 어떤 선을 지워야 하는지 화면 어디에도 없어서 사용자는 그래프를 처음부터 다시 만든다.
- **수정안**: 494~502행의 죽은 블록을 제거하고, tool 노드를 제어 흐름으로 만났을 때의 의도를 명시적으로 정한다(권장: `node = node_dict.get(node_id)` 를 함수 맨 앞으로 올린 뒤, tools 전용 노드가 제어 흐름 대상이면 생성을 건너뛰고 `log_step` 에 VALIDATION 계열 NodeError 로 "이 노드는 도구로만 쓰인다"를 남긴다). 아울러 compile_workflow 전체를 try/except 로 감싸 예상 못 한 코드젠 예외도 "Error: ..." 문자열 + 구조화 step 으로 내려보내 실행 로그가 비지 않게 한다.

### 🟠 HIGH · webCrawler·toss·paymentLink·hwpx 노드의 실패 문구가 legacy 패턴에 걸리지 않아, 실패한 실행이 로그·집계에서 전부 '성공'으로 기록된다

- **위치**: `backend/node_generators/action_nodes.py:138`
- **분류**: ops · **추정** 4h · **감사자 확신** high
- **근거**: webCrawlerNode 는 예외를 잡아 문구만 만들고 log_step 에 error= 를 넘기지 않는다:
```python
130:    lines.append(f"{indent}except Exception as e:")
131:    lines.append(f"{indent}    crawl_res_{node_id} = 'Crawling failed: ' + str(e)")
132:    lines.append(f"{indent}    _set_node_meta('{node_id}', status='error', ...)")
138:    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
```
graph.py:409 의 log_step 은 error= 가 없을 때 `_detect_legacy_pattern(res_str)` 에만 의존한다. 실제 호출 결과:
```
detect_legacy_pattern('Crawling failed: HTTPSConnectionPool... timed out') -> None
detect_legacy_pattern('수집하지 않았습니다: robots.txt 가 금지함')        -> None
detect_legacy_pattern('Toss Query Failed: ...')  -> None
detect_legacy_pattern('Payment Link Error: ...') -> None
flow_outcome('Crawling failed: timeout', [그 로그])  -> 'success'
summarize_logs(...) -> {'error_count': 0, 'first_error': N
- **사용자가 겪는 장면**: 매일 아침 뉴스 사이트를 크롤링해 요약을 슬랙으로 보내는 스케줄 워크플로우. 사이트가 robots.txt 를 바꿔 수집이 막힌다. 크롤러 노드는 '수집하지 않았습니다: ...' 를 내놓고, 하류 LLM 은 그 문구를 요약해 슬랙으로 보낸다. 그런데 실행 이력 화면에서 그 노드는 초록색 '성공', 실행 상태도 '성공'이고 오류 개수는 0이다. 운영자는 실패 알림도 못 받고 대시보드에서도 아무 이상을 못 본다 — 몇 주 뒤 슬랙 내용이 계속 이상하다는 제보를 받고서야 알게 된다. 결제 조회(tossNode)·결제 링크 생성(paymentLinkNode)도 같아서, 결제 링크 생성이 실패한 실행이 '성공'으로 남는다.
- **수정안**: 네 곳 모두 log_step 에 error 를 넘긴다: webCrawlerNode 는 URL_BLOCKED/CRAWL_FAILED 를 `_make_node_error` 로 만들어 error= 로, hwpxDocumentNode 는 이미 있는 `_hx_err_{node_id}` 를 그대로 error= 로, toss/paymentLink 는 상태코드·예외 분기에서 NodeError 를 만들어 넘긴다. 근본 대책으로 log_step 이 error 없이 호출되는 것을 막을 수 없다면, '노드 결과 문자열은 실패를 표현할 수 없다'는 규약을 테스트로 고정한다 — 각 생성기를 컴파일해 실패 분기가 error= 또는 NodeResult 를 싣는지 검사하는 회귀 테스트(오늘 fuzz 스크립트와 같은 방식)를 추가.

### 🟠 HIGH · multiAgentNode 는 log_step 을 아예 호출하지 않아 로그·__node_results__ 에서 사라지고, mode 가 지원 3종이 아니면 생성 코드가 컴파일은 되지만 실행 시 res_ma_* NameError 로 죽는다

- **위치**: `backend/node_generators/agent_nodes.py:121`
- **분류**: correctness · **추정** 4h · **감사자 확신** high
- **근거**: generate_multi_agent_node(agent_nodes.py:17~124) 전체에 log_step 이 한 번도 없다(전 생성기 스캔 결과 log_step 미호출: delayNode, dynamicInputNode(구 webhook 분기), multiAgentNode, conditionNode, loopNode, breakNode, distributorNode). 그래서 graph.py:441 의 `__node_results__[node_id] = ...` 가 실행되지 않고, mergeNode(flow_nodes.py:167 은 `__node_results__.get(_sid,'')`)와 데이터 바인딩(graph.py 의 `_resolve_binding`: `if source not in __node_results__: raise BINDING_SOURCE_NOT_RUN`)이 이 노드의 결과를 찾지 못한다.

또 mode 분기는 supervisor/group_chat/tool_agent 세 개뿐이고 else 가 없는데, 그 뒤 121~124행이 무조건 하류로 `res_ma_{node_id}` 를 넘긴다:
```python
121:    # Continue flow
122:    next_edges = forward_edges.get(node_id, [])
124:        generate_block_fn(target_id, ..., prev_res_var=f"res_ma_{node_id}", ...)
```
실제 생성 결과(mode='router'):
```
# --- Multi-Agent Node (ma1) ---
# --- Output Node (o1) ---
_start_o1 = ...
last_result = res_ma_ma1          ← 정의된 적 없음
- **사용자가 겪는 장면**: (1) 사용자가 멀티 에이전트 뒤에 mergeNode 를 붙여 다른 갈래와 합친다. 실행하면 멀티 에이전트의 답변이 통째로 사라진 채 다른 갈래 결과만 합쳐지고, 실행 로그에는 멀티 에이전트 노드 줄이 아예 없어서 "실행이 안 된 건가?" 만 남는다. 데이터 바인딩을 걸었다면 대신 BINDING_SOURCE_NOT_RUN('상류가 실행되지 않았다') 오류가 뜬다 — 실제로는 실행됐는데.
(2) 템플릿 갤러리에서 '도구 에이전트' 템플릿을 꺼내 Dry Run 을 누르면 "mode는 'supervisor' 또는 'group_chat'이어야 한다" 로 실패한다. 제품이 기본 제공하는 템플릿이 제품 자신의 검증에서 불합격이다.
(3) data.mode 가 빈 문자열이나 낯선 값인 그래프(AI 편집·API 저장 경로)에서는 노드 카드가 UI 상 '관리자(supervisor)'로 보이는데(customNodes.jsx:2305 `data.mode || 'supervisor'`) 실행은 `► Flow 1 Error: name 'res_ma_ma1' is not defined` 로 끝난다.
- **수정안**: ① generate_multi_agent_node 끝에 `last_result` 와 함께 log_step 을 추가(토큰 집계는 이미 add_tracking 이 하므로 결과·상태만). ② mode 분기 앞에서 `mode = mode if mode in ('supervisor','group_chat','tool_agent') else 'supervisor'` 로 정규화하거나, 알 수 없는 mode 는 `_make_node_error('VALIDATION_REQUIRED', field='mode')` 를 남기고 `res_ma_{id}` 를 안내 문구로 초기화한다(그 변수를 항상 먼저 대입하면 NameError 자체가 사라진다). ③ 허용 mode 목록을 UI·코드젠·검증기 세 곳에 하드코딩하지 말고 node_definitions/multiAgentNode.json(현재 없음)을 만들어 정의에서 파생시킨다 — 지금은 정의 파일이 없어서 세 곳이 갈라진 것이다.

### 🟠 HIGH · 반복 구조 검증기의 하드코딩 목록에 loopNode 가 없어서, loopNode 본문에 outputNode 가 있으면 반복이 1회만 돌고도 '정상'으로 통과하고, 반대로 정상적인 loopNode+breakNode 그래프는 거부된다

- **위치**: `backend/meta_agent.py:1485`
- **분류**: correctness · **추정** 3h · **감사자 확신** high
- **근거**: ```python
meta_agent.py:1485: LOOP_PRODUCING_NODE_TYPES = {"distributorNode"}  # ... 추후 loopNode 등 추가 시 여기에 더한다
meta_agent.py:1728:     if not _has_upstream_type(n.id, g, LOOP_PRODUCING_NODE_TYPES):
meta_agent.py:1826:     if n.type != "distributorNode":   # outputNode-in-loop 규칙도 distributorNode 만 본다
```
주석에 적힌 "추후 loopNode 등 추가"가 실행되지 않았다. 실측 두 방향:
```
# (A) loopNode 본문 → outputNode : 검증 통과, 실행은 1회
validate_flow -> (True, [])
생성 코드:
  for _loop_idx_n2 in range(int(3)):
      # --- Output Node (n3) ---
      log_step('n3', 'outputNode', _start_n3, result=last_result)
      return last_result          ← ui_nodes.py:11
      loop_acc_n2 = last_result   ← 도달 불가(죽은 코드)

# (B) loopNode + breakNode (nodeDocumentation.js:281 이 '반복 종료 노드로 조기 종료할 수 있습니다'라고 문서화한 조합)
validate_flow -> (False, ['n4(breakNode)의 상류에 distributorNode(반복을 만드는 노드)가 없다 ... distributorNode 하류에 연결하라'])
실제 compile_workflow ->
- **사용자가 겪는 장면**: (A) 사용자가 "초안을 3번 반복해서 다듬고 결과를 보여줘" 를 만든다. 반복 컨테이너 안에 LLM 노드와 결과 출력 노드를 놓는다. Dry Run 도 통과, 실행도 오류 없이 끝난다. 그런데 결과는 1회만 다듬은 것이고, 실행 로그에는 반복 노드 줄이 없어서 몇 번 돌았는지 확인할 방법조차 없다. 사용자는 "반복 횟수를 5로 올렸는데 결과가 똑같다"로 문의한다.
(B) 사용자가 "반복 중 조건 만족하면 멈춰줘" 를 요청한다. AI 가 문서대로 loopNode + breakNode 를 그리면 검증에서 튕겨 나가 다시 생성되고, 결국 breakNode 가 빠진(또는 distributorNode 로 바뀐) 다른 구조가 나온다. 손으로 그린 뒤 Dry Run 을 누른 사용자는 정상 동작하는 그래프에 대해 '실패' 판정을 받는다.
- **수정안**: ① `LOOP_PRODUCING_NODE_TYPES = {"distributorNode", "loopNode"}`. ② meta_agent.py:1825 의 outputNode 규칙을 loopNode 로 일반화한다 — distributorNode 는 `sourceHandle != 'done'`, loopNode 는 `sourceHandle in (None,'loop_start')` 또는 parentNode 로 본문을 판별하고, 그 경로가 outputNode 에 닿으면 같은 오류를 낸다. ③ 근본적으로는 반복 본문을 판별하는 함수를 한 곳(예: loop_body_targets(node, edges))에 두고 검증기와 flow_nodes.py 코드젠이 같은 함수를 읽게 해 목록이 다시 갈라지지 않게 한다. ④ loopNode/distributorNode 에도 log_step(반복 횟수·수집 항목 수 포함)을 추가해 '몇 번 돌았는지'가 로그에 남게 한다.

### 🟠 HIGH · 생성 코드의 문자열 리터럴 이스케이프가 공용 헬퍼 없이 28곳에 복사돼 있고 어느 곳도 CR(\r)을 처리하지 않는다 — 값 하나 때문에 워크플로우 전체가 '생성된 코드가 248번째 줄에서 잘못됐다'로 실행 거부된다

- **위치**: `backend/node_generators/core_nodes.py:19`
- **분류**: correctness · **추정** 6h · **감사자 확신** high
- **근거**: 전형적인 이스케이프 체인(각 생성기에 인라인 복사):
```python
core_nodes.py:19:  val = ...get('value','').replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
```
같은 체인이 28곳(`grep -c` 결과), `\r` 을 다루는 곳은 0곳(`grep -rn '\\\\r' node_generators/ graph.py` → template_nodes.py:407 의 무관한 필터 하나뿐), 공용 헬퍼 없음(`grep 'def .*escape|_py_str'` → 없음).

valueNode.value = 'a\r\nb' 로 실제 컴파일:
```
Error: Security validation failed: generated workflow is invalid at line 248
실제 생성 줄: '        val_v1 = "a\r\\nb"'   ← 생 CR 이 리터럴을 끊는다
```
conditionNode 는 \n 조차 이스케이프하지 않는다:
```python
flow_nodes.py:76:  value_escaped = str(value).replace('\\','\\\\').replace('"','\\"')   # \n 없음
```
→ rules[0].value='a\nb' 로 컴파일: `'        if "a'` 에서 unterminated string literal.

51개 노드 타입 × 필드 전수 fuzz 로 확인한 CR 취약 노드: valueNode, promptNode, llmNode, conditionNode, discordNode, telegramNode, kakaoNode, tossNode, notionNode, googleSheetsNode, googleC
- **사용자가 겪는 장면**: 사용자가 AI 대화창에 워드에서 복사한 안내문을 붙여 "이 문구를 값 노드에 넣어줘" 라고 한다. LLM 이 그대로 넣으면 CRLF 가 data.value 에 살아 들어간다(meta_agent 에 \r 정리 코드 없음). 이후 그 프로젝트는 실행 버튼을 누를 때마다 `❌ 워크플로우 실행 중 오류가 발생했습니다: Error: Security validation failed: generated workflow is invalid at line 248` 만 낸다. 248번째 줄은 사용자가 볼 수 없는 생성 소스의 줄이고, 어느 노드·어느 필드가 문제인지 화면에 전혀 안 나온다. 실행 로그도 비어 있다. 노드를 하나씩 지워 보는 이분 탐색 말고는 원인을 찾을 방법이 없다. 템플릿 JSON 임포트, 공개 API 로 graph_data 를 저장하는 경로도 같다.
- **수정안**: 이스케이프를 없애는 방향이 옳다 — 문자열은 f-string 조립 대신 파이썬 `repr()`(또는 `json.dumps`)로 굽는다. 즉 `f'val_{id} = "{val}"'` → `f'val_{id} = {value!r}'`. 이미 emailNode(bound_expr)·pythonNode(`{user_code!r}`)·paymentLinkNode(`repr(order_data)`)가 그 방식을 쓰고 있으니 규약을 통일하면 된다. 단계적으로는 `node_generators/_lit.py` 에 `py_str(value)` 하나를 두고 28곳을 교체(`\r`·`\t`·` ` 포함), core_nodes.py:33 의 `r"..."` 도 repr 로 바꾼다. 회귀 방지로 오늘 쓴 fuzz(51 타입 × 필드 × 페이로드 → compile()) 를 pytest 로 편입한다. 별도로 compile_workflow 가 SyntaxError 를 낼 때 '생성 소스 N번째 줄' 대신 그 줄을 만든 node_id 를 되돌려 주도록 lines 와 node_id 를 함께 쌓는 것도 같이 처리해야 진단 가능성이 생긴다.

### 🟡 MEDIUM · delayNode 는 대기 시간에 상한이 없고 log_step 도 호출하지 않아, 동기 실행 스레드를 임의 시간 점유하면서 로그에는 아무 흔적도 남기지 않는다

- **위치**: `backend/node_generators/action_nodes.py:189`
- **분류**: ops · **추정** 3h · **감사자 확신** medium
- **근거**: ```python
action_nodes.py:182: @node_registry.register('delayNode')
action_nodes.py:186:     seconds = node.get('data', {}).get('seconds', 5)
action_nodes.py:189:     lines.append(f"{indent}time.sleep(float({seconds}))")
action_nodes.py:191~193:  # 곧바로 하류 생성 — log_step 호출이 없다
```
상한을 두는 곳이 어디에도 없다: node_definitions/delayNode.json 의 seconds 검증은 `{"rule":"number","min":0}` 뿐이고 max 가 없다. 그 검증조차 validate_flow(=AI 생성/Dry Run) 경로에서만 돌고, main.py:1863 `def execute_flow(...)` → graph.run_workflow 는 검증을 거치지 않는다.
실행 엔드포인트가 `async def` 가 아니라 `def` 이므로 FastAPI 의 스레드풀 워커를 그대로 점유한다(main.py:1863). 값은 리터럴로 구워지므로 `seconds=3600` 이면 생성 코드가 `time.sleep(float(3600))` 이 된다.
또 log_step 이 없어 `__node_results__[node_id]` 도 채워지지 않는다 — 하류 mergeNode/바인딩이 이 노드를 소스로 지목하면 값을 못 찾는다(graph.py:441, flow_nodes.py:167).
- **사용자가 겪는 장면**: 사용자가 "1시간 뒤에 후속 메일 보내기" 를 만들려고 대기 노드에 3600 을 넣는다(UI 는 숫자 입력이고 상한 안내가 없다). 스케줄러가 이 워크플로우를 매시간 돌리면 대기 중인 실행이 계속 쌓여 스레드풀(기본 40)이 차고, 어느 순간 로그인·프로젝트 저장·에디터까지 전부 응답하지 않는다. 운영자가 실행 이력을 열어 봐도 대기 노드 줄이 없어서 마지막 성공 노드에서 멈춘 것처럼만 보이고, 무엇이 붙잡고 있는지 알 수 없다.
- **수정안**: ① 코드젠에서 상한을 강제한다: `seconds = max(0, min(float(seconds or 0), MAX_DELAY_SECONDS))` (예: 300초) 로 클램프하고, 잘렸다는 사실을 log_step 의 safe_details 로 남긴다. ② node_definitions/delayNode.json 의 number 규칙에 max 를 넣어 검증기·UI·문서가 같은 값을 읽게 한다. ③ delayNode 에 log_step 추가(실제 대기한 초 포함). ④ 장시간 대기는 sleep 이 아니라 승인 노드처럼 durable 대기(ADR-0015 구조 재사용)로 가는 것이 정공법이므로, 상한 도입과 함께 "긴 대기는 스케줄 트리거로 나누라"는 안내를 노드 문서에 넣는다.

### 🟡 MEDIUM · 한 노드에서 두 갈래로 나뉜 흐름이 mergeNode 없이 다시 합쳐지면 합류 노드의 코드가 갈래마다 중복 생성돼 메일·메신저가 두 번 발송된다

- **위치**: `backend/graph.py:502`
- **분류**: correctness · **추정** 8h · **감사자 확신** high
- **근거**: ```python
graph.py:502:        visited = visited.copy()
graph.py:503:        visited.add(node_id)
```
visited 를 갈래마다 복사하므로 같은 노드가 여러 갈래에서 각각 생성된다. 실측(start→v1, start→v2, v1→email, v2→email):
```
-> compiled OK
   emailNode emitted 2 times
```
두 블록은 조건 분기 안이 아니라 같은 들여쓰기의 순차 코드로 놓이므로 런타임에 둘 다 실행된다(조건 분기로 갈라진 경우에는 if/else 안에 들어가 하나만 실행된다 — 공식 템플릿 107종 중 다중 유입 2건은 모두 conditionNode 분기라 안전했다: '피드에 키워드 뜨면 알림' n206, '고객 불만 분류·긴급 건 즉시 알림' n319).
meta_agent.py:285~286 은 AI 에게 "병렬 분기를 적극 활용하고, 합류할 때는 반드시 mergeNode" 라고 지시하지만, 사람이 에디터에서 직접 그릴 때는 이를 막거나 경고하는 검증이 없다(validate_flow 에 해당 규칙 없음).
- **사용자가 겪는 장면**: 사용자가 "기사를 요약도 하고 키워드도 뽑아서 한 메일로 보내줘" 를 만든다. 시작 노드에서 두 갈래로 나눠 각각 LLM 을 태우고, 두 갈래를 이메일 노드 하나에 연결한다(mergeNode 를 쓰라는 안내를 못 봤다). 실행하면 같은 수신자에게 메일이 두 통 간다 — 하나는 요약만, 하나는 키워드만. 실행 로그에도 이메일 노드가 두 줄로 찍히는데, 사용자는 노드를 하나만 놓았으므로 로그가 잘못됐다고 생각한다. 슬랙·디스코드·카카오 발송에서도 같고, 결제 링크 생성처럼 되돌리기 어려운 노드에서도 같다.
- **수정안**: 단기: validate_flow 에 "제어 흐름 유입이 2개 이상이고 타입이 mergeNode 가 아닌 노드"(조건 분기·승인 분기에서 온 상호 배타 유입은 제외) 규칙을 추가해 Dry Run·AI 경로에서 잡고, 에디터에서 두 번째 선을 그을 때 인라인 경고를 띄운다. 근본: 코드젠을 '노드마다 한 번만 생성'으로 바꾼다 — 위상 순서로 노드를 한 번씩 방출하고 각 노드가 자기 유입을 __node_results__ 에서 읽게 하면(mergeNode 가 이미 하는 방식) 중복이 구조적으로 사라진다. 다만 조건 분기의 지연 실행 의미를 유지해야 하므로 변경 범위가 크고 회귀 위험이 있어, 검증·경고를 먼저 넣고 코드젠 재구성은 별도 계획으로 다루는 것이 안전하다.

### 🟡 MEDIUM · 반복 컨테이너의 최대 횟수 칸을 비우면 0 이 저장돼 range(int(0)) 이 생성되고, 반복이 한 번도 돌지 않은 채 로그에도 남지 않는다

- **위치**: `backend/node_generators/flow_nodes.py:111`
- **분류**: ux · **추정** 2h · **감사자 확신** high
- **근거**: ```python
flow_nodes.py:102:  max_iter = node.get('data', {}).get('maxIterations', 5)
flow_nodes.py:111:  lines.append(f"{indent}for _loop_idx_{node_id} in range(int({max_iter})):")
```
값이 리터럴로 그대로 구워진다. 실측:
```
maxIterations=0     -> for _loop_idx_l1 in range(int(0)):     # 본문 0회
maxIterations=''    -> for _loop_idx_l1 in range(int()):      # int()==0, 역시 0회
maxIterations='다섯' -> for _loop_idx_l1 in range(int(다섯)):  # 컴파일 통과, 런타임 NameError
validate_flow(maxIterations=0) -> (True, [])                  # 검증도 통과
```
UI 는 숫자 입력이고 `min="1"` 은 표시용이라 강제되지 않는다:
```jsx
customNodes.jsx:1060:  value={data.maxIterations ?? 5}
customNodes.jsx:1061:  onChange={(e)=> data.onChange?.(id,'maxIterations', Number(e.target.value))}   // Number('') === 0
```
비운 칸은 0 으로 저장되고 `0 ?? 5` 는 0 이므로 화면에도 0 으로 남는다. loopNode 는 log_step 을 호출하지 않아(flow_nodes.py:100~142) 실행 로그에 반복 노드 줄이 없다. meta_agent.py:2601~2605 의 검증은 
- **사용자가 겪는 장면**: 사용자가 반복 횟수를 5에서 3으로 바꾸려고 칸을 전부 지우고 3을 타이핑하려다 다른 곳을 클릭한다. 그 순간 0 이 저장된다. 이후 실행하면 오류 하나 없이 즉시 끝나고, 반복 안의 노드들은 실행 로그에 한 줄도 나오지 않는다(반복 노드 자체도 안 나온다). 사용자는 "반복 안의 노드들이 왜 실행이 안 되나" 로 문의하지만, 화면의 작은 숫자 칸이 0 이라는 것을 눈치채기 어렵다.
- **수정안**: ① 코드젠에서 정수화·클램프한다: 파싱 실패하면 기본 5, 범위는 1~100(UI 의 max 와 동일)으로 잡고 리터럴이 아니라 안전한 정수를 굽는다 — 이것만으로 NameError/0회 두 문제가 동시에 사라진다. ② node_definitions 에 loopNode 정의(현재 없음)를 만들어 min/max 를 정본으로 두고 UI·검증기가 파생하게 한다. ③ customNodes.jsx:1061 에서 빈 문자열은 저장하지 않거나 기본값으로 되돌린다(정수 draft 패턴). ④ loopNode 에 log_step 을 추가해 '몇 회 설정, 몇 회 실행'이 로그에 남게 한다.

## 에디터 상태 관리와 경쟁 조건 (frontend/src/pages/EditorPage.jsx, customNodes.jsx, editorCommands.js)

> 감사 범위: 실제로 읽은 것: pages/EditorPage.jsx 전체를 훑고(핵심 구간 260-470, 700-1010, 1014-1360, 1500-1740, 1830-2270, 2355-2800, 2824-2900, 3490-3790 은 정독), editorCommands.js 1-140, useEditorHistory.js 전체, AuthContext.jsx 전체, main.jsx, ChatSidebar.jsx, nodeTestFixtures.js 1-75, customNodes.jsx 의 100-430 및 grep 으로 뽑은 입력창 전부(defaultValue 14곳, value={data.*} 17곳). 교차 확인: backend/main.py update_project(1334-1410), project_revisions, meta_agent.run_agent_turn/modify_flow 서명부, node_modules/@xyflow/react getNodes 구현(1098행).

검증 방법: 읽기 전용 원칙을 지켜 파일은 수정하지 않았다. 발견 1은 scratchpad 에 probe.mjs 를 만들어 저장소의 실제 editorCommands.createEditorSnapshot/getSnapshotFingerprint 를 import 해 raw 노드와 enriched 노드의 지문을 비교했다(결과: 불일치, bindingConte

### 🔴 CRITICAL · enrichedNodes 가 노드 data 에 심는 bindingContext·isPinnedOutput·className 이 UI_DATA_KEYS 에서 빠져 저장 스냅샷에 들어간다 — 저장 직후에도 영구 "저장 안 됨", 그래프에 전체 그래프·실행 결과가 노드마다 복제

- **위치**: `frontend/src/editorCommands.js:1`
- **분류**: data-integrity · **추정** 3h · **감사자 확신** high
- **근거**: editorCommands.js:1-17 의 UI_DATA_KEYS 는 하드코딩 목록이고 `bindingContext`, `isPinnedOutput` 이 없다. TRANSIENT_NODE_KEYS(19-25)에도 `className` 이 없어 sanitizeNodeForSnapshot(70-78)이 그대로 보존한다.

반면 EditorPage.jsx:2841-2884 의 enrichedNodes 는 노드마다 `className: nodeClass`(2862), `isPinnedOutput`(2874), `bindingContext`(2879)를 심는다. bindingContext(2832-2840)는 `{nodes: 전체 노드 목록, edges: 전체 엣지, results: 모든 노드의 실행 result_data, dataLayer}` 객체다.

ReactFlow 에 넘기는 것은 `nodes={enrichedNodes}`(3496)이고, node_modules/@xyflow/react/dist/esm/index.js:1098 은 `getNodes: () => store.getState().nodes.map((n) => ({...n}))` — data 는 얕은 복사로 enriched 그대로다. 저장 payload 는 getCurrentFlowData()(2042-2050) → createEditorSnapshot(getNodes(), ...) → handleSave(878).

실제 실험(저장소의 editorCommands.js 를 그대로 import):
  raw     : {..."data":{"label":"LLM","prompt":"안녕"}}
  enriched: {..."className":"node-success","data":{...,"isPinnedOutput":fals
- **사용자가 겪는 장면**: 이미 저장된 프로젝트를 열어 노드 하나를 고치고 저장 버튼을 누른다. "저장되었습니다" alert 가 뜨는데, 헤더의 부제는 계속 "· 저장 안 됨"(2921)이고 저장 버튼도 계속 dirty 강조(editor-save-dirty, 2965)로 남는다. 탭을 닫으려 하면 매번 "변경사항이 저장되지 않았습니다" 경고가 뜬다(2558-2565). 새로고침 전까지 이 상태가 풀리지 않아 사용자는 무엇이 저장됐는지 판단할 근거를 잃는다(새 프로젝트는 첫 저장 뒤 재로드가 일어나 우연히 가려진다 — 발견 2 참고).

동시에 노드 40개짜리 워크플로우를 한 번 실행한 뒤 저장하면, bindingContext.results 안의 모든 노드 실행 결과(LLM 출력·크롤링 본문)가 노드 40개의 data 에 각각 한 벌씩 복제되어 저장된다. 결과가 노드당 2KB 만 되어도 80KB × 40 = 약 3MB 가 한 번의 PUT 으로 올라가고, 저장할 때마다 같은 크기의 리비전 행이 쌓인다. 그 그래프는 /api/chat 의 graph_data(2601)로 LLM 프롬프트에도, /api/execute 의 node.data(1765)로 실행 요청에도 그대로 들어가 토큰과 대역폭을 먹는다. 또 AI 채팅 응답을 되받아 노드를 비교할 때(2660-2680, stripUIProps 에도 bindingContext 가 없다) 손대지 않은 노드까지 "[수정] 변경
- **수정안**: (1) UI 전용 키를 하드코딩 목록으로 두지 말고 enrichedNodes 가 심는 키를 한 곳(예: `const ENRICHED_DATA_KEYS`)에서 export 해 editorCommands 의 UI_DATA_KEYS 가 그것을 파생시키게 한다 — 노드 등록 누락과 같은 부류의 드리프트다. (2) className 을 TRANSIENT_NODE_KEYS 에 넣거나, enrichedNodes 가 className 을 노드 객체가 아닌 별도 채널로 넘긴다. (3) 근본적으로는 저장·지문 계산이 getNodes()(=enriched) 대신 raw `nodesRef.current`/`nodes` 를 읽게 바꾸는 편이 안전하다. (4) 회귀 테스트: enrichedNodes 가 심는 키 집합과 UI_DATA_KEYS 의 차집합이 비어 있는지 검사하는 테스트를 editorCommands.test.js 에 추가. (5) 이미 저장된 그래프에 섞여 들어간 bindingContext 를 로드 시 걷어내는 정리 경로(absorbDetachedText 와 같은 자리)도 필요하다.

### 🟠 HIGH · 첫 저장 뒤 navigate 가 projectId 를 바꿔 로드 useEffect 가 재실행 → 서버 사본이 캔버스를 덮어쓰고 undo 히스토리가 초기화되며 AI 수정 하이라이트가 사라진다

- **위치**: `frontend/src/pages/EditorPage.jsx:910`
- **분류**: correctness · **추정** 3.5h · **감사자 확신** high
- **근거**: 라우트는 `/editor/:projectId?` 하나뿐이라(App.jsx:91) projectId 가 undefined → id 로 바뀌어도 컴포넌트는 언마운트되지 않는다.

handleSave 의 신규 생성 경로: `setCurrentId(res.data.id)`(906) → `navigate(\`/editor/${res.data.id}\`, { replace: true })`(910).

로드 useEffect(753-806)의 의존성은 `[projectId, location.state]`(806)이고 본문 첫 줄이 `if (projectId) { loadProject(projectId); }`(754-756)다. 재실행을 막는 가드(currentId 비교 등)가 없다.

loadProject(810-861)는 서버 GET 결과로 `replaceGraph(loadedNodes, absorbed.edges, {...})`(838/841)를 부르고, replaceGraph(388-397)는 `resetEditorHistory(...)`(396)로 히스토리 배열을 [초기 상태] 하나로 갈아 끼운다(useEditorHistory.js:14-21). 이어서 `setChatMessages(chatRes.data.session.messages)`(852)로 채팅 스레드까지 서버 사본으로 교체한다.

AI 자동 저장 경로(2745-2751)도 같은 handleSave 를 타므로, 방금 commitEditorHistory 로 쌓은 `AI 수정: …` 엔트리(2713)와 노드 data 의 isAIModified/aiChanges(2685-2687)가 재로드로 전부 날아간다 — 저장 payload 는 stripUIPropsForSave(2730-2739)로 그 플래그를 지우고 보냈기 때문이다.
- **사용자가 겪는 장면**: AI 어시스턴트에 "슬랙 알림 워크플로우 만들어줘" 를 넣으면 노드가 생기고 자동 저장이 돌면서 URL 이 /editor/123 으로 바뀐다. 그 직후 캔버스가 서버에서 다시 읽혀 통째로 교체되고, (a) AI 가 어떤 노드를 만들었는지 알려주던 노란 하이라이트와 변경 속성 목록이 한순간에 사라지고, (b) Ctrl+Z 버튼이 비활성으로 죽어 사용자는 AI 가 한 일을 되돌릴 수 없다(히스토리에 '초기 상태' 하나만 남는다).

수동 경로는 편집 손실까지 간다: 새 프로젝트에서 노드를 몇 개 놓고 Ctrl+S 를 누른 뒤, POST 응답과 이어지는 GET 이 도는 수백 ms~수 초 사이에 노드를 하나 더 놓거나 프롬프트를 타이핑한다. GET 이 도착하면 replaceGraph 가 서버 사본으로 캔버스를 갈아 끼워 그 편집이 경고 없이 사라진다. 사용자 눈에는 "방금 만든 노드가 저장하니까 없어졌다" 로 보인다.
- **수정안**: 로드 useEffect 앞단에 "이미 이 프로젝트를 이 세션에서 들고 있으면 재로드하지 않는다" 가드를 둔다: `if (projectId && String(projectId) !== String(loadedProjectIdRef.current)) loadProject(projectId)` 형태로 loadedProjectIdRef 를 두고, handleSave 의 생성 경로에서 navigate 전에 그 ref 를 새 id 로 미리 채운다. 채팅 히스토리 재조회도 같은 가드 아래로 옮긴다. 검증은 (1) 새 프로젝트 저장 후 undo 가 계속 살아 있는지, (2) AI 생성 직후 하이라이트가 남는지 Playwright 로 확인.

### 🟠 HIGH · 노드 펼침 밀어내기(onExpandChange)가 setNodes 업데이터 안에서 ref 를 갱신하고 이미 펼친 노드에 재적용까지 되어, "모두 펼치기" 를 거치면 주변 노드가 220px 씩 영구히 밀린 채 저장된다

- **위치**: `frontend/src/pages/EditorPage.jsx:1119`
- **분류**: correctness · **추정** 4h · **감사자 확신** high
- **근거**: 밀어낸 양은 `pushDeltasRef`(1111) 한 곳에만 기록되고, 기록·삭제가 모두 setNodes 업데이터 **안**에서 일어난다: 펼칠 때 `pushDeltasRef.current[expandedId] = currentPushes`(1159), 접을 때 `delete pushDeltasRef.current[expandedId]`(1165) 후 감산(1167-1173). dw=320-140=180, dh=260-140=120, PUSH_MARGIN=40 이므로 한 번 밀 때 dx=220, dy=160(1113-1117, 1141-1148).

호출 측(customNodes.jsx:107-129)에 현재 펼침 상태를 확인하는 가드가 없다:
· 브로드캐스트 effect(111-119): `if (!cmd || cmd.token === lastCommandToken.current) return;` 로 토큰만 보고, isExpanded 가 이미 next 와 같은지는 보지 않은 채 `data.onExpandChange(id, next)`(118)를 부른다.
· toggleExpand(121-127): `setIsExpanded(prev => { ... data.onExpandChange(id, next); return next; })` — 부수효과가 상태 업데이터 안에 있다. main.jsx:53 이 StrictMode 이므로 개발 모드에서는 업데이터가 두 번 호출되어 클릭 한 번에 onExpandChange 가 두 번 간다.

"모두 펼치기/모두 접기" 버튼은 `setExpandAllCommand({ action, token: Date.now() })`(3050-3051)로 토큰만 새로 발급한다.

밀린 위치는 setNodes(1120)를 타므로 scheduleHistoryCommi
- **사용자가 겪는 장면**: 노드 A 헤더를 눌러 펼친다(옆 노드 B 가 오른쪽으로 220px, 아래로 160px 밀린다). 그 상태에서 상단 "모두 펼치기" 를 누르면 A 의 effect 가 토큰이 새롭다는 이유로 onExpandChange(A, true) 를 한 번 더 불러 B 를 또 220px 밀고, pushDeltasRef[A] 는 한 벌만 덮어쓴다. 이어 "모두 접기" 를 누르면 220px 만 되돌려서 B 는 원래 자리에서 오른쪽 220px·아래 160px 어긋난 채 남는다. "모두 펼치기" 를 두 번 연달아 누르면 440px 어긋난다.

어긋난 위치는 undo 히스토리에 정상 편집으로 기록되고 저장 payload 에도 들어가므로, 다시 열어도 레이아웃이 복구되지 않는다. 큰 그래프에서 이 동작을 몇 번 반복하면 노드가 화면 밖으로 흩어져 사용자가 수동으로 재배치하거나 자동 정렬을 다시 돌려야 한다. 개발 모드(StrictMode)에서는 "모두 펼치기" 없이 노드 하나를 펼쳤다 접기만 해도 매번 220px 씩 드리프트가 쌓인다.
- **수정안**: (1) customNodes.jsx 의 toggleExpand 에서 onExpandChange 호출을 업데이터 밖으로 빼고(현재 isExpanded 를 읽어 next 를 계산한 뒤 호출), 브로드캐스트 effect 에도 `if (next === isExpanded) return;` 가드를 넣는다. (2) EditorPage 의 onExpandChange 는 setNodes 업데이터 안에서 ref 를 쓰지 말고, expandedNodesRef 로 "이미 펼침" 을 먼저 판정해 중복 적용 자체를 거부하도록 멱등하게 만든다(가장 확실한 방법은 밀어낸 델타를 ref 가 아니라 노드 data 에 두어 상태와 함께 롤백되게 하는 것). (3) 검증: 펼치기→모두 펼치기→모두 접기 뒤 노드 position 이 원래 값과 같은지 Playwright 로 확인하고, StrictMode 개발 모드에서도 같은지 본다.

### 🟠 HIGH · AI 채팅이 요청 시작 시점 스냅샷으로 만든 서버 그래프를 그대로 캔버스에 덮어써, 생성이 도는 10초 이상 동안의 사용자 편집이 경고 없이 사라진다

- **위치**: `frontend/src/pages/EditorPage.jsx:2601`
- **분류**: data-integrity · **추정** 5h · **감사자 확신** high
- **근거**: handleSendChat(2568-)은 요청 시작 시점의 그래프를 서버로 보낸다: `graph_data: getCurrentFlowData()`(2601). 응답을 받은 뒤에는 diff 용으로만 최신 상태를 다시 읽고(`const currentNodes = getNodes();` 2646), 실제 캔버스는 서버가 준 graph_data 로 통째로 교체한다: `finalNodes = ensureMemoNodeDefaultsForList(loadedNodes)`(2700, loadedNodes 는 2650 의 `(graph_data.nodes || []).map(...)`) → `setNodesState(finalNodes); setEdgesState(finalEdges);`(2711-2712) → `commitEditorHistory(finalNodes, finalEdges, ...)`(2713).

요청 중 캔버스를 잠그는 장치가 없다: ReactFlow(3495-3571)에 isChatLoading 을 반영하는 nodesDraggable/nodesConnectable/오버레이가 없고, 보호되는 것은 전송 버튼뿐이다(`sendDisabled={!chatInput.trim() || isChatLoading}` 3587). 생성이 짧지 않다는 건 코드가 스스로 말한다 — 진행 문구가 5단계이고 간격이 2500ms 다(2578-2586).

낙관적 동시성 검사는 서버 저장에만 있고(main.py:1345-1352 base_revision) 이 그래프 교체 경로에는 없다.
- **사용자가 겪는 장면**: 사용자가 AI 에게 "이메일 발송 단계를 추가해줘" 를 보내고, 응답을 기다리는 동안 유휴 시간이 아까워 캔버스에서 조건 노드를 하나 새로 놓고 LLM 노드 프롬프트를 다듬는다. 15초 뒤 응답이 도착하면 캔버스는 서버가 만든 노드 목록으로 교체된다 — 새로 놓은 조건 노드는 목록에 없어 사라지고, 다듬은 프롬프트는 요청 시점의 옛 문장으로 되돌아간다. 게다가 diff 는 최신 노드(2646)와 서버 노드를 비교하므로, 사용자가 방금 고친 프롬프트가 "[수정] 노드가 변경되었습니다 … 변경된 속성: userPrompt" 로 로그(2673-2675)에 찍히고 노란 AI 하이라이트가 붙는다. 사용자는 자기가 쓴 문장이 지워진 것을 AI 가 고친 것으로 오해한다. 되돌리는 유일한 수단은 Ctrl+Z 한 번(2713 의 커밋)이고, 그마저 AI 결과 전체를 함께 되돌린다.
- **수정안**: (1) 요청 시작 시 보낸 스냅샷의 지문(getSnapshotFingerprint)을 보관하고, 응답 적용 직전에 현재 raw 그래프 지문과 비교해 다르면 덮어쓰기 전에 customConfirm 으로 물어본다(저장 409 충돌에서 이미 쓰는 패턴 — 936-949, saveConflict.js). (2) 또는 isChatLoading 동안 ReactFlow 를 읽기 전용으로(nodesDraggable/nodesConnectable/elementsSelectable=false + 편집 입력 비활성) 두고 그 사실을 배너로 알린다. (3) diff 기준을 최신 getNodes() 가 아니라 실제로 보낸 스냅샷으로 바꿔 AI 변경 표시가 사용자 편집을 흡수하지 않게 한다. 검증: 요청 중 노드를 추가하고 응답을 받았을 때 확인 대화가 뜨는지 Playwright 로 본다.

### 🟡 MEDIUM · 정의 기반 노드 필드가 uncontrolled defaultValue 라서, Undo·AI 수정·자동 개선으로 data 가 바뀌어도 입력창은 옛 텍스트를 그대로 보여준다(화면 값과 저장·실행 값이 갈린다)

- **위치**: `frontend/src/customNodes.jsx:399`
- **분류**: correctness · **추정** 5h · **감사자 확신** high
- **근거**: 정의 파일에서 파생되는 모든 텍스트·숫자 필드의 공통 렌더러가 uncontrolled 다: customNodes.jsx:391-402 의 `<input type={...} className="nodrag" defaultValue={value ?? field.default ?? ''} onChange={(e) => commit(...)} />`. ADR-0008 기반 공식 연동 노드는 이 렌더러 하나로 그려진다(주석 405-407: "헤더도 필드도 전부 정의 파일에서 나오므로 … 새로 쓸 JSX 가 사실상 없다"). 별도 하드코딩 필드도 같은 방식이다 — varName(818), output_path(1356), inputLabel(1497), url(1580), maxChars(1603), receiver(1687), webhookUrl(2752), 그리고 또 하나의 동적 렌더러(2249/2257/2269). 파일 전체에서 defaultValue 14곳.

Undo 는 노드 data 를 되돌리지만 DOM 을 되돌리지 않는다: applyHistoryEntry(2069-2089)는 setNodesState 로 스냅샷을 복원할 뿐이고, 노드 컴포넌트는 같은 id 로 재사용되어 언마운트되지 않으므로 uncontrolled input 의 DOM 값은 유지된다. AI 채팅(2711)과 autoImproveFlow(1631-1637)도 같은 방식으로 data 만 교체한다.

같은 파일이 이 문제의 정답을 이미 갖고 있다 — NodeTextField(136-149)와 DraggableTextarea(152-198)는 draft + controlled 패턴이지만, NodeTextField 사용처는 3곳뿐이다(grep).
- **사용자가 겪는 장면**: webCrawlerNode 의 "타겟 URL" 에 잘못된 주소를 붙여넣고 Ctrl+Z 로 되돌린다. 화면의 입력창은 잘못된 주소를 그대로 보여주는데, 노드 data 와 저장·실행 payload 에는 되돌려진 옛 주소가 들어간다. 사용자는 화면에 보이는 주소로 크롤링될 것이라 믿고 실행하지만 다른 URL 을 긁는다.

반대 방향도 같다. AI 에게 "이 노드 URL 을 공지사항 페이지로 바꿔줘" 라고 하면 AI 는 제대로 바꾸고 로그에 "[수정] … 변경된 속성: url" 까지 찍히지만, 펼쳐 둔 노드의 입력창은 옛 URL 을 계속 표시한다. 사용자는 "AI 가 안 바꿨다" 고 판단해 같은 요청을 반복한다(그때마다 토큰을 쓴다). 노드를 접었다 다시 펼치면(isExpanded 로 node-body 가 언마운트→재마운트) 그때야 바뀐 값이 보인다 — 재현·설명이 어려운 형태의 불일치다.
- **수정안**: defaultValue 를 쓰는 필드를 NodeTextField(136-149)로 갈아 넣는다 — draft 가 null 이면 부모 값을 그대로 보여주므로 Undo·AI 수정이 즉시 반영되고, 편집 중에는 draft 가 정본이라 IME 문제도 재발하지 않는다. 특히 391-402 의 공통 렌더러 한 곳만 바꿔도 정의 기반 노드 전부가 함께 고쳐진다. 검증: Playwright 로 (1) 한글 조합 입력이 지워지지 않는지, (2) Ctrl+Z 후 입력창 표시값이 바뀌는지, (3) 부모 값이 갱신되는 사이에 커서가 튀지 않는지 확인한다(과거 재발 이력이 있어 IME 회귀 확인이 필수).

### 🟡 MEDIUM · scheduleHistoryCommit 이 pendingHistoryLabelRef 를 labelOverride 보다 우선해서, 서로 다른 편집이 한 undo 단계로 합쳐지고 라벨도 엉뚱하게 붙는다

- **위치**: `frontend/src/pages/EditorPage.jsx:342`
- **분류**: ux · **추정** 2.5h · **감사자 확신** high
- **근거**: scheduleHistoryCommit(342-357)의 라벨 결정 순서:
```
const label = (meta.label !== '워크플로우 편집' ? meta.label : null)
  || pendingHistoryLabelRef.current
  || labelOverride
  || '워크플로우 편집';
const delay = delayOverride ?? meta.delay ?? 0;
```
첫 호출이 nextHistoryMetaRef 를 소비해 기본값으로 되돌리고(349) pendingHistoryLabelRef 를 채우므로(350), 디바운스 창이 열려 있는 동안 들어온 두 번째 호출은 자기 labelOverride 를 **쓰지 못한다** — pendingHistoryLabelRef 가 먼저 걸린다. 동시에 delay 가 meta 기본값 0 으로 떨어져 타이머가 즉시 만료된다.

디바운스 창을 만드는 쪽: commitNodeDataChanges 의 `markNextHistory('노드 설정 변경', 650)`(1021).
그 창 안에서 자기 라벨을 잃는 쪽: onNodesChange 의 `scheduleHistoryCommit('노드 삭제')`(404), onEdgesChange 의 `scheduleHistoryCommit('연결 변경')`(433), onNodeDragStop 의 `scheduleHistoryCommit(historyLabel)`(1311, historyLabel 은 '노드 이동' 또는 'Alt 드래그 복제').

라벨은 화면에 노출된다: undoLabel/redoLabel(useEditorHistory.js:73-76) → Undo 버튼 title `${undoLabel} 취소`(2958), 그리고 시스템 로그 `> ↩ ${entry.labe
- **사용자가 겪는 장면**: llmNode 프롬프트를 한 줄 고친 직후(650ms 디바운스가 도는 중) 필요 없는 노드를 골라 Delete 키를 누른다. 히스토리에는 "노드 삭제" 엔트리가 따로 생기지 않고, 방금 고친 프롬프트와 노드 삭제가 '노드 설정 변경' 이라는 하나의 엔트리로 합쳐진다. 삭제만 취소하려고 Ctrl+Z 를 한 번 누르면 노드가 돌아오면서 공들여 쓴 프롬프트 수정도 함께 사라진다. Undo 버튼 툴팁에는 '노드 삭제 취소' 가 아니라 '노드 설정 변경 취소' 가 떠 있어, 무엇이 되돌아갈지 미리 알 방법도 없다.
- **수정안**: 라벨 우선순위를 뒤집는다 — 호출자가 명시한 labelOverride 를 pendingHistoryLabelRef 보다 앞에 둔다. 더 정확한 해법은 "성격이 다른 편집이 들어오면 대기 중인 커밋을 먼저 flush 하고 새 엔트리를 시작" 하는 것: onNodesChange/onEdgesChange/onNodeDragStop 이 scheduleHistoryCommit 대신 `flushHistoryCommit()` 후 자기 라벨로 새로 스케줄하게 한다(deleteSelection 2219-2237 이 이미 쓰는 패턴). 검증: 프롬프트 수정 후 300ms 안에 노드를 지우고 Ctrl+Z 한 번에 삭제만 되돌아가는지, 툴팁 라벨이 맞는지 확인.

### 🟡 MEDIUM · 샘플 입력·고정 출력이 URL 의 projectId 로 키를 만들어(저장 전엔 'new'), 첫 저장 순간 사용자가 넣어 둔 테스트 데이터가 전부 사라진다

- **위치**: `frontend/src/pages/EditorPage.jsx:1704`
- **분류**: ux · **추정** 2h · **감사자 확신** high
- **근거**: 키를 만드는 쪽은 URL 파라미터 projectId 다: EditorPage.jsx:1704-1705 `readSampleInput = useCallback((nodeId) => readStoredSampleInput(projectId, nodeId), [projectId])`, 1706 writeSampleInput 도 동일, 1708-1711 `collectPinnedOutputs(projectId, nodes)`, 1713/1720 pinOutput/unpinOutput 도 projectId, 3739 `readPinnedOutput(projectId, inspected.id)`.

저장소 키: nodeTestFixtures.js:64 `sampleKey = (projectId, nodeId) => \`${SAMPLE_PREFIX}:${projectId || 'new'}:${nodeId}\``, 70 pinnedKey 도 같다.

첫 저장은 URL 을 바꾼다: handleSave 910 `navigate(\`/editor/${res.data.id}\`, { replace: true })`. 이때 projectId 가 undefined → '123' 으로 바뀌므로 키 접두사가 `wfai:sampleInput:new:` → `wfai:sampleInput:123:` 로 갈아치워진다. 이미 저장된 값을 새 키로 옮기는 코드는 없다(grep: sampleKey/pinnedKey 사용처는 read/write 뿐).

같은 파일이 currentId(701)라는 정답을 들고 있는데 이 경로만 projectId 를 쓴다.
- **사용자가 겪는 장면**: 아직 저장하지 않은 새 워크플로우에서, 사용자가 크롤러 노드에 샘플 입력을 붙여 넣고 목업을 여러 번 돌려 LLM 프롬프트를 조율한다(§7.1 이 의도한 사용법 그대로다). 마음에 드는 결과가 나와 저장 버튼을 누르면 URL 이 /editor/123 이 되고, 검사 탭의 샘플 입력 칸이 빈칸으로 바뀐다. 고정해 둔 출력(§7.3)도 사라져 다음 목업 실행이 상류 노드를 처음부터 다시 돌린다 — 외부 API 재호출을 피하려고 만든 장치가 바로 그 순간 무력해진다. 사용자는 값을 처음부터 다시 채워야 하고, 원인이 "저장 버튼" 이라는 걸 짐작할 수 없다.

부수 효과로 저장 전 프로젝트는 모두 `:new:` 접두사를 공유하므로, 서로 다른 미저장 프로젝트의 잔여 픽스처가 같은 네임스페이스에 계속 쌓인다.
- **수정안**: 키 소스를 `projectId` 에서 `currentId || projectId` 로 통일하고(701 의 currentId 는 저장 직후 갱신된다), 첫 저장 시 `wfai:*:new:*` 키를 새 프로젝트 id 로 rename 하는 마이그레이션을 handleSave 의 생성 성공 지점(906-912)에 넣는다. 아니면 픽스처 키를 프로젝트 대신 노드 id 기준(노드 id 는 makeEntityId 로 충분히 고유하다)으로 바꿔 프로젝트 id 변화에 영향받지 않게 한다. 검증: 저장 전 샘플 입력 입력 → 저장 → 검사 탭에 값이 남아 있는지 확인.

### 🟡 MEDIUM · editorCommands/visiblePaletteCommands 가 매 렌더 새로 만들어져 document keydown 리스너가 렌더마다 재등록되고, enrichedNodes 가 모든 노드의 data 객체를 새로 만들어 드래그 프레임마다 전체 노드가 리렌더된다

- **위치**: `frontend/src/pages/EditorPage.jsx:2359`
- **분류**: perf · **추정** 4h · **감사자 확신** high
- **근거**: 의존성 사슬이 매 렌더 끊긴다:
· handleSave(866)와 getCurrentFlowData(2042), getAuthHeaders(751), runFlow(1736)는 useCallback 없는 평범한 함수라 렌더마다 새 참조다.
· `saveFromCommand = useCallback(..., [handleSave])`(2359-2363) → 매 렌더 새 참조.
· `runNodeMock = useCallback(..., [getAuthHeaders, ...])`(1850, 1895) → 매 렌더 새 참조.
· 따라서 `editorCommands = useMemo(..., [..., runNodeMock, saveFromCommand, ...])`(2365-2386)도 매 렌더 새 배열.
· 그 결과 (a) 단축키 useEffect(2458-2506)의 deps 에 editorCommands 가 있어(2506) 렌더마다 `document.removeEventListener/addEventListener('keydown')`(2504-2505)가 반복되고, (b) `visiblePaletteCommands = useMemo(..., [..., editorCommands, ...])`(2400-2441)가 매 렌더 커맨드 필터링·노드 목록 매핑을 다시 돌린다.

노드 리렌더 쪽: enrichedNodes(2841-2884)는 노드마다 `data: { ...n.data, ...9개 필드, bindingContext, expandAllCommand }`(2865-2881)로 **새 객체**를 만든다. deps 에 `nodes`(2884)가 있고, bindingContext 자체도 `[nodes, edges, ...]`(2840)에 매달려 있다. 노드 하나를 드래그하면 onNode
- **사용자가 겪는 장면**: 노드 30개짜리 워크플로우에서 노드 하나를 캔버스 위로 드래그하면, 프레임마다 30개 노드가 전부 리렌더되고(각 노드의 data 참조가 새로 생기므로) 그와 동시에 document 의 keydown 리스너가 떼였다 붙었다 반복된다. 드래그가 눈에 띄게 끊기고, 저사양 노트북에서는 노드가 마우스를 못 따라온다. 번들이 이미 단일 2MB 청크인 환경이라 첫 로드 뒤 상호작용 지연이 더 두드러진다.

리스너 재등록 자체도 위험을 남긴다 — 리렌더가 몰리는 순간에 눌린 Ctrl+Z 가 떼어진 리스너와 새 리스너 사이 틈에 떨어지면 조용히 무시된다(사용자에게는 "가끔 Ctrl+Z 가 안 먹는다" 로 보인다).
- **수정안**: (1) getAuthHeaders/getCurrentFlowData/handleSave/runFlow 를 useCallback 으로 안정화한다 — 단, runNodeMock(1890-1894)의 주석이 경고하는 TDZ 함정이 있으므로 함수 선언 순서를 먼저 정리하거나 최신 값을 담는 ref(latestRef 패턴)로 우회해야 한다. 이걸 건드리지 않고 안정화만 하면 runNodeMock 이 옛 currentId/baseRevision 을 잡은 채 굳어 저장 대상이 어긋나므로, 순서상 이 finding 을 고칠 때 함께 처리해야 한다. (2) 단축키 useEffect 는 editorCommands 를 ref 로 읽어 리스너를 한 번만 등록한다. (3) enrichedNodes 의 전역 필드(isTokenTrackingMode/tokenDisplayMode/bindingContext 등)를 노드 data 대신 React context 로 내려 노드별 data 참조가 위치 변경마다 바뀌지 않게 하고, 노드 컴포넌트에 memo 를 붙인다. 검증: 노드 30개 그래프에서 드래그 시 React Profiler 커밋 수와 프레임 시간을 전후 비교.

## 에디터 밖 프론트엔드 화면들 (frontend/src/pages/ 비-에디터 페이지 + components/, 라우터·navigation 정합성, 로딩/빈/오류 상태, 반응형, 접근성, 목록 규모)

> 감사 범위: 실제로 읽은 것: src/App.jsx(라우트 전체), src/navigation.js, src/MainSidebar.jsx + MainSidebar.css(전체), src/mainSidebarState.js, src/main.jsx, src/ErrorBoundary.jsx, src/AuthContext.jsx, pages/CommunityQnaPage.jsx(731줄 전체) + CommunityQnaPage.css, pages/TemplatesPage.jsx(307줄 전체), pages/StatisticsPage.jsx(392줄 전체) + StatisticsPage.css의 미디어쿼리 전부, pages/ProjectRunsPage.jsx(366줄 전체), pages/ApprovalInboxPage.jsx, pages/OperationsOverviewPage.jsx, pages/PatchNotesPage.jsx + css, pages/CustomAppViewerPage.jsx, pages/MessagesPage.jsx(1~120·200~245) + MessagesPage.css(전체), pages/SettingsPage.jsx(1~60·165~230), pages/EvaluationPage.jsx(1~30), pages/ManagementPage.css, pages/MainPage.css(레이아웃·미디어쿼리), pages/Docume

### 🔴 CRITICAL · catch 없는 목록 로더 + main.jsx 의 전역 오류 오버레이가 겹쳐, API 500 한 번에 앱 전체가 다크레드 스택트레이스 화면으로 덮인다 (ErrorBoundary 는 만들어두고 안 씀)

- **위치**: `frontend/src/main.jsx:2`
- **분류**: ux · **추정** 3h · **감사자 확신** high
- **근거**: main.jsx:2-17 이 프로덕션 엔트리에서 무조건 전역 핸들러를 건다: `window.addEventListener('unhandledrejection', function(event) { ... div.style.width='100vw'; div.style.height='100dvh'; div.style.backgroundColor='darkred'; div.style.zIndex='999999'; div.innerHTML = '<h1>FATAL PROMISE ERROR</h1><pre>' + (event.reason?.stack || event.reason) + '</pre>'; document.body.appendChild(div); })`. main.jsx:20-35 에 `window.'error'` 용 쌍둥이 핸들러가 또 있다. 이 코드는 배포 번들에 그대로 들어가 있다 — `grep -c "FATAL PROMISE ERROR" frontend/dist/assets/index-DA2pDoUH.js` → 1.
한편 거부를 만들어 낼 자리가 열려 있다. CommunityQnaPage.jsx:194-205 `const load = useCallback(async () => { setLoading(true); try { const res = await axios.get('/api/community/posts', ...); setPosts(...); } finally { setLoading(false); } }` — **catch 가 없다**. 이걸 호출하는 곳도 맨손이다: CommunityQnaPage.jsx:207 `useEffect(() => { load(); }, [load]);`. 같은 모양이 TemplatesPage.jsx:159-167(try/finally, catch
- **사용자가 겪는 장면**: 백엔드가 재시작 중이거나 /api/community/posts 가 500 을 내는 순간, 커뮤니티 Q&A 에 들어온 일반 사용자 화면이 통째로 진한 빨강으로 덮이고 그 위에 `AxiosError: Request failed with status code 500` 같은 원시 스택 트레이스가 뜬다. 사이드바도 메뉴도 안 보이고 오버레이는 z-index 999999·100vw/100dvh 라 클릭으로 치울 수도 없어 새로고침 말고는 탈출구가 없다. 템플릿 목록에서 게시할 워크플로우를 고르다 gate 확인이 실패하는 경우(TemplatesPage.jsx:63)나, 질문자가 답변 채택 버튼을 눌렀는데 이미 채택된 상태여서 409 가 오는 경우(CommunityQnaPage.jsx:355)에도 같은 빨간 화면이 뜬다. 반대로 렌더링 중 예외가 나면(ErrorBoundary 미사용) React 트리가 통째로 unmount 되어 완전한 흰 화면이 된다.
- **수정안**: (1) main.jsx:2-35 의 두 전역 오버레이를 `import.meta.env.DEV` 가드 안으로 옮기거나 삭제하고, 프로덕션에서는 조용한 로깅 + 눈에 거슬리지 않는 토스트로 바꾼다. (2) App.jsx 의 `<Routes>` 를 `ErrorBoundary` 로 감싸고, 사용자에게 보여줄 폴백을 한국어로 다시 쓴다(현재 'Something went wrong.' + componentStack 노출). (3) 위에 나열한 6곳에 catch 를 채워 화면 안 오류 배너로 바꾼다 — 이미 같은 파일 안에 좋은 본보기가 있다(CommunityQnaPage.jsx:326-333 의 `catch { setPost(false) }`, StatisticsPage.jsx:90-98).

### 🟠 HIGH · 승인 대기함·실행 이력이 API 실패를 '없음'으로 표시해, 멈춘 워크플로우가 아무 경고 없이 방치된다

- **위치**: `frontend/src/pages/ApprovalInboxPage.jsx:35`
- **분류**: ops · **추정** 2.5h · **감사자 확신** high
- **근거**: ApprovalInboxPage.jsx:31-38 `const load = useCallback(async () => { try { const res = await axios.get('/api/approvals', authHeaders()); setRequests(res.data.requests || []); } catch (e) { /* silent */ } finally { setLoading(false); } }, [authHeaders]);` — 오류 상태를 담는 state 가 아예 없다. 그 결과 ApprovalInboxPage.jsx:161-165 가 `{loading ? <p>불러오는 중...</p> : (<><h3>대기 중 (0)</h3><p>대기 중인 승인 요청이 없습니다.</p>...` 를 그린다. 사이드바 배지도 같이 침묵한다 — MainSidebar.jsx:88-90 `try { const res = await axios.get('/api/approvals/count', ...); setApprovalCount(res.data.count); } catch (e) {/* silent */ }`.
새로고침 버튼도 반응이 없다: ApprovalInboxPage.jsx:159 `<button className="btn-refresh" onClick={load} disabled={loading}>새로고침</button>` 인데 `load` 는 `setLoading(true)` 를 하지 않고 :36 에서 false 로만 내린다 — 같은 저장소의 OperationsOverviewPage.jsx:67 은 `onClick={() => { setLoading(true); load(); }}` 로 제대로 한다.
같은 부류가 실행 이력에도 있다: ProjectRunsPage.jsx:4
- **사용자가 겪는 장면**: 사용자 승인 노드에서 멈춘 실행 3건이 대기 중인데 /api/approvals 가 500(또는 토큰 만료로 401)을 낸다. 운영자는 사이드바 배지가 안 뜨고 승인 대기함이 "대기 중 (0) / 대기 중인 승인 요청이 없습니다." 라고 말하는 것을 보고 처리할 것이 없다고 판단한다. 새로고침을 눌러도 화면이 미동조차 없어(로딩 표시가 안 뜨므로) 문제가 있다는 신호가 전혀 없다. 승인 대기 중이던 스케줄 실행 3건은 아무도 손대지 않은 채로 남는다. 실행 이력 화면도 같아서, 실패한 배포를 조사하러 온 사람이 "No execution history found." 를 보고 '이 워크플로우는 한 번도 실행되지 않았다' 고 잘못 결론 낸다.
- **수정안**: 세 로더에 `error` state 를 추가하고 catch 에서 채운다. 빈 상태와 오류 상태를 반드시 다른 문구로 분리한다 — StatisticsPage.jsx:227-233(오류 패널 + 다시 시도 버튼)과 :249-254(빈 상태)가 이미 이 저장소의 올바른 본보기다. ApprovalInboxPage.jsx:159 의 새로고침은 `setLoading(true)` 를 함께 호출하고, MainSidebar 배지는 연속 실패 시 배지를 0 으로 덮어쓰지 않도록 마지막 성공값을 유지한다.

### 🟠 HIGH · 쪽지·통계 페이지 제목이 모바일 햄버거 버튼에 가려진다 — 저장소가 index.css 에 적어 둔 '기준 폭은 1024px' 규칙을 두 페이지만 안 따랐다

- **위치**: `frontend/src/pages/MessagesPage.css:7`
- **분류**: ux · **추정** 2h · **감사자 확신** high
- **근거**: 햄버거는 1024px 부터 뜨고 위치가 고정이다 — MainSidebar.css:54-55 `@media (max-width: 1024px) { .mobile-sidebar-toggle { display: grid; position: fixed; top: 0.85rem; left: 0.85rem; z-index: 40; width: 40px; height: 40px; ...` → 화면좌표 x 13.6~53.6, y 13.6~53.6 를 차지한다.
이 저장소는 이 규칙을 이미 글로 남겨놨다 — index.css:2522-2524: "모바일에서는 좌측 상단 고정 햄버거(사이드바 토글)가 섹션 탭을 가리므로 비켜준다. **기준 폭은 햄버거(.mobile-sidebar-toggle)가 뜨는 1024px 과 같아야 한다 — 768px 으로 두면 769~1024px 구간에서만 탭이 햄버거 밑에 깔려 첫 탭 글자가 잘린다.**" DocumentsPage.css:751·TutorialPage.css:2394 도 1024px 로 맞춰 `margin-left: 64px` 를 준다. ManagementPage.css:269-272 도 1024px 이다.
그런데 두 페이지는 어긋난다. MessagesPage.css:7 `.main-page-content.msg-page { padding: 1.35rem 1.5rem 1.5rem; }` 이고 좌측 여백을 늘려주는 규칙이 **어느 브레이크포인트에도 없다**(:130-144 의 720px 블록은 `padding: 1rem` 으로 오히려 줄인다, :147 은 0.8rem). StatisticsPage.css:6 `.statistics-main { padding: 32px 48px 48px; }`, :509 는 1100px 에서 좌우를 28px 로 줄이고, 햄버거 
- **사용자가 겪는 장면**: 아이패드 세로(768px 은 통과하지만 820px·834px 짜리 기기)나 노트북에서 창을 반만 넓혀 쓰는(900px) 사용자가 통계를 열면, 좌상단 40px 짜리 햄버거 카드가 BarChart3 아이콘과 "사용 통계" 제목 위에 겹쳐 앉는다. 햄버거에는 box-shadow 가 있어(MainSidebar.css:55) 제목이 그림자 밑에서 잘려 보이고, 반대로 제목 위를 누르면 원치 않게 사이드바가 열린다. 쪽지 페이지는 더 나빠서 폭과 무관하게 1024px 이하 전부 — 아이폰까지 — "쪽지" 제목과 실시간 연결 상태 위계가 햄버거에 깔린다.
- **수정안**: MessagesPage.css 에 `@media (max-width: 1024px) { .msg-page-head { padding-left: 56px; } }` 를 추가하고 720px·480px 블록에서 이 여백을 지우지 않게 한다. StatisticsPage.css:517 의 `padding-left: 48px` 를 768px 블록에서 꺼내 새 `@media (max-width: 1024px)` 블록으로 올린다. 고칠 때 index.css:2522-2524 의 주석을 근거로 인용해 두면 다음 페이지가 또 768 로 쓰는 것을 막는다. 검증은 이번에 쓴 방식대로 1024/1000/900/800/769/768 여섯 폭에서 bounding box 교차를 재측정.

### 🟠 HIGH · 커뮤니티 템플릿 목록이 서버 기본값 limit=30 에서 잘리는데 더 보기·페이지가 없어 나머지 템플릿이 UI 로 도달할 수 없고, '첫 실행 성공률' 정렬도 30개 안에서만 다시 줄 세운다

- **위치**: `frontend/src/pages/TemplatesPage.jsx:162`
- **분류**: correctness · **추정** 3h · **감사자 확신** high
- **근거**: 프론트는 limit 을 보내지 않는다 — TemplatesPage.jsx:159-167 `const res = await axios.get('/api/community/templates', { params: { category: category || undefined, q: query || undefined, sort } });`. 페이지네이션·무한 스크롤·더 보기 버튼은 파일 전체(307줄)에 없다.
서버 기본값은 30 이다 — backend/main.py:3847-3849 `def list_community_templates(category=None, tag=None, q=None, sort="quality", limit: int = 30, ...)`, community_templates.py:731 `rows = rows.limit(max(1, min(limit, 100))).all()`.
카탈로그는 그보다 훨씬 크다 — `backend/venv/bin/python -c "import official_templates as ot; print(len(ot.TEMPLATES))"` → **107**, Documents/ROADMAP.md:7 은 "커뮤니티 템플릿 242종 게시" 로 적고 있다.
같은 API 를 부르는 홈 화면은 limit 을 명시한다 — MainPage.jsx:108 `axios.get('/api/community/templates', { params: { sort: 'installs', limit: IDEA_SLOTS } })`. 즉 이 화면만 기본값에 기대고 있다.
정렬도 무너진다. community_templates.py:720-721 주석이 "**자르기 전에** 정렬해야 한다 ... 파이썬에서 다시 세우면 '최신 N개를 그 기준으로 줄세운 것'이 되어 전체 상
- **사용자가 겪는 장면**: 사용자가 커뮤니티 → 템플릿에 들어가 스크롤을 끝까지 내린다. 30개에서 목록이 끝나고 더 볼 방법이 없다. 헤더는 "표시 중 30" 이라고만 말하므로 이게 전부라고 믿는다. 카테고리를 '마케팅'으로 바꾸면 그 안의 템플릿이 다시 30개까지만 나오므로 이 경로로도 나머지를 찾을 수 없다. 슬러그 URL 을 직접 아는 사람만 /community/templates/<slug> 로 들어갈 수 있다. 게다가 기본 정렬인 '첫 실행 성공률' 은 id 역순 최신 30개를 다시 줄 세운 결과라, 성공률 92% 인 오래된 공식 템플릿은 1페이지 어디에도 못 올라온다 — 이 화면의 존재 이유(TemplatesPage.jsx:6-7 주석)가 무력화된다.
- **수정안**: 짧은 길: TemplatesPage.jsx:162 에 `limit: 100`(서버 상한)을 넣어 즉시 출혈을 막는다. 제대로: 서버에 offset/cursor 를 추가하고 quality 정렬을 SQL 서브쿼리나 사전 계산 컬럼으로 옮겨 자르기 전에 정렬하게 한 뒤(community_templates.py:720 주석의 요구), 프론트에 '더 보기' 또는 페이지 컨트롤과 총 개수(`total`)를 붙이고 :187 의 '표시 중' 을 '30 / 242' 형태로 바꾼다.

### 🟡 MEDIUM · 템플릿 검색이 키 입력마다 요청을 보내고 응답 순서를 보장하지 않아, 한글 검색어에서 엉뚱한 결과가 남는다

- **위치**: `frontend/src/pages/TemplatesPage.jsx:167`
- **분류**: perf · **추정** 1.5h · **감사자 확신** high
- **근거**: TemplatesPage.jsx:159-169: `const load = useCallback(async () => { setLoading(true); try { const res = await axios.get('/api/community/templates', { params: { category: category || undefined, q: query || undefined, sort } }); setItems(res.data.templates || []); } finally { setLoading(false); } }, [category, query, sort]);` 다음 줄이 `useEffect(() => { load(); }, [load]);` 다. `query` 가 useCallback 의 의존성이므로 입력 한 글자마다 `load` 의 정체성이 바뀌고 effect 가 다시 돌아 **키 입력마다 GET 이 나간다**. 입력창은 :201-202 `<input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} ...>` 로, Enter 핸들러는 이미 중복이다. 디바운스도, AbortController 도, 시퀀스 가드도 없다.
같은 저장소의 다른 화면은 둘 다 갖췄다 — StatisticsPage.jsx:63 `const requestSequence = useRef(0);`, :77-78 `const controller = new AbortController(); const sequence = ++requestSequence.current;`, :89 `if (sequence === requestSequence.current) setStats(
- **사용자가 겪는 장면**: 사용자가 검색창에 "디스코드" 를 입력한다. 한글 IME 조합 중 `value`가 바뀌는 매 시점마다(ㄷ/디/딧/디스/…) GET /api/community/templates?q=… 가 나가 한 단어에 6~10건의 요청이 쌓인다. 각 응답은 도착 순서대로 `setItems` 를 덮으므로, "디스" 요청이 "디스코드" 요청보다 늦게 도착하면 검색창에는 "디스코드"가 적혀 있는데 목록은 "디스" 결과가 남는다. 게다가 서버 쪽 quality 정렬은 템플릿당 quality_signals(db, template) 를 도는 N+1 성격이라(community_templates.py:736-739), 검색창을 몇 번 두드리는 것만으로 DB 부하가 배로 뛴다.
- **수정안**: `query` 를 `deferredQuery`(250~300ms 디바운스) 로 분리해 load 의 의존성에서 원시 입력을 빼고, StatisticsPage.jsx:63·77-78·89·102 의 AbortController + requestSequence 패턴을 그대로 옮긴다. :202 의 Enter 핸들러는 디바운스를 즉시 flush 하는 용도로만 남긴다.

### 🟡 MEDIUM · 실행 이력 화면이 키보드로 조작 불가능하고, 상세 조회가 실패하면 'Loading details...' 로 영구 고착되거나 직전 실행의 상세를 다른 실행 번호로 보여준다 (화면 전체가 영어)

- **위치**: `frontend/src/pages/ProjectRunsPage.jsx:164`
- **분류**: ux · **추정** 4h · **감사자 확신** high
- **근거**: 클릭 대상이 전부 시맨틱 없는 요소다 — ProjectRunsPage.jsx:164-168 `<li key={run.id} className={...} onClick={() => setSelectedRunId(run.id)}>`(role·tabIndex·onKeyDown 없음), :195-199 평가 목록도 동일, :252 `<div className="step-card-header" onClick={() => toggleNodeExpand(step.id)}>`(단계 펼치기 — 접이식인데 aria-expanded 도 없음). 같은 저장소의 TemplatesPage.jsx:232-234 는 `role="link" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(t); } }}` 로 제대로 처리한다.
상세 실패가 두 갈래로 잘못 끝난다 — :56-69 `const fetchRunDetails = async (runId) => { try { setLoadingDetails(true); const res = await axios.get(`/api/runs/${runId}`, ...); setRunDetails(res.data); ... } catch (error) { console.error("Failed to fetch run details:", error); } finally { setLoadingDetails(false); } }` 는 실패 시 `runDetails` 를 건드리지 않는다. 그래서 :222-223 `: loadingDetails || !runDetails ? (<div className="loading-state">Loading details.
- **사용자가 겪는 장면**: 실패한 야간 배치를 조사하려고 에디터 메뉴에서 실행 이력을 연다. 목록의 최신 실행 #57 이 자동 선택되지만(:46-48) /api/runs/57 이 타임아웃 난다. 오른쪽 패널은 "Loading details..." 로 굳어 몇 분을 기다려도 바뀌지 않고, 무엇이 잘못됐는지 알려주는 문구가 없다. 목록에서 #56 을 눌러 상세를 본 뒤 다시 #57 을 누르면 이번에는 더 나쁘게, 왼쪽에서 #57 이 파랗게 선택된 채 오른쪽에는 "Run #56 Details" 와 #56 의 실행 단계·토큰 수가 그대로 남아 있어 실패 원인을 엉뚱한 실행에서 찾게 된다. 마우스를 못 쓰는 사용자는 Tab 으로 이 화면의 어떤 실행도 선택할 수 없어(li·div 는 포커스를 받지 않는다) 실행 이력을 전혀 읽을 수 없다.
- **수정안**: 목록 항목을 `<button>` 으로 바꾸거나 role="option"/tabIndex/onKeyDown 을 붙이고(TemplatesPage.jsx:232-234 패턴 재사용), step-card-header 는 `<button aria-expanded={...}>` 로 만든다. fetchRunDetails 의 catch 에서 `setRunDetails(null)` 과 `setDetailError(...)` 를 함께 세워 '상세를 불러오지 못했습니다 + 다시 시도' 패널을 그린다. 문구는 이 파일 전체를 한국어로 번역한다(다른 페이지들과 같은 어투).

### 🟡 MEDIUM · 설정 페이지만 navigation.js 의 탭 정본을 안 쓰고 자체 배열을 하드코딩해, 같은 섹션 안에서 탭 UI 가 바뀌고 친구 요청 배지가 사라진다

- **위치**: `frontend/src/pages/SettingsPage.jsx:167`
- **분류**: maintainability · **추정** 2h · **감사자 확신** high
- **근거**: navigation.js:1-3 이 정본 선언을 한다: "섹션별 보조 내비게이션 정의 ... **페이지마다 배열을 복사하면 항목 누락·경로 불일치가 생기므로 여기가 정본이다.**" 그리고 :17-24 에 `SETTINGS_SECTION_TABS`(프로필/친구/화면/토큰/데이터/API 센터)가 있다.
`grep -rn "SETTINGS_SECTION_TABS" src` 결과 소비자는 **ApiCenterPage 뿐**이다 — ApiCenterPage.jsx:12 import, :248·:262 `<SectionTabs ariaLabel="설정 섹션" tabs={SETTINGS_SECTION_TABS} />`.
반면 섹션의 본체인 SettingsPage 는 navigation 을 import 하지도 않고 SettingsPage.jsx:167-174 에서 같은 목록을 다시 적는다: `const tabs = [{ id: 'profile', label: '프로필', icon: <User size={16} /> }, { id: 'friends', label: '친구', icon: <Users size={16} />, badge: friendRequests.length }, ... { id: 'api-center', label: 'API 센터', ... }];` 그리고 :189-212 에서 SectionTabs 대신 인라인 스타일 pill 버튼으로 직접 렌더한다(`background: activeTab === tab.id ? 'var(--primary-color, #3b82f6)' : 'transparent'`).
두 구현의 차이가 이미 눈에 보인다: SettingsPage 쪽만 :169 `badge: friendRequests.length` 를 갖고 :205-209 에서 빨간 배지를 그린다. 공
- **사용자가 겪는 장면**: 친구 요청 2건이 와 있는 사용자가 설정 → 프로필에서 파란 pill 탭 줄과 '친구' 위의 빨간 ② 배지를 본다. 'API 센터' 를 누르면 같은 섹션인데 탭 줄이 전혀 다른 모양(회색 테두리 박스형 SectionTabs)으로 바뀌고 위치·높이가 튀며, 친구 요청 배지가 사라진다. 이 상태에서 친구 요청이 새로 와도 API 센터에 머무는 동안은 알 수 없다. 운영 입장에서 더 위험한 것은 다음 변경이다 — 설정에 탭을 하나 추가하면 navigation.js·SettingsPage.jsx:167·SettingsPage.jsx:18 세 곳을 모두 고쳐야 하고, 한 곳을 놓치면 이 저장소가 이미 겪은 '하드코딩 목록의 조용한 갈라짐'(노드 등록 누락 이력)이 그대로 재현된다.
- **수정안**: SectionTabs 에 optional `badge` 를 받게 확장하고 `SETTINGS_SECTION_TABS` 항목에 badge 키를 선언한 뒤, SettingsPage.jsx:167-174·189-212 를 지우고 ApiCenterPage 와 동일하게 `<SectionTabs tabs={SETTINGS_SECTION_TABS} badges={{ friends: friendRequests.length }} />` 를 쓴다. :18 의 VALID_TABS 도 `SETTINGS_SECTION_TABS` 의 path 에서 파생시킨다. 검증은 /settings/profile ↔ /settings/api-center 를 왕복하며 탭 줄의 위치·모양·배지가 유지되는지 브라우저에서 확인.

### ⚪ LOW · EvaluationPage(258줄 + 전용 CSS)는 라우트도 링크도 없는 고아 화면이라 도달 불가인데 단일 번들에는 계속 실려 나간다

- **위치**: `frontend/src/pages/EvaluationPage.jsx:7`
- **분류**: maintainability · **추정** 1.5h · **감사자 확신** high
- **근거**: `grep -rn "EvaluationPage|'/evaluation|\"/evaluation" src` 결과 EvaluationPage.jsx 자기 자신(:5 자기 CSS import, :7 export)과 EmptyState.css:11 의 주석 언급 외에 **참조가 0건**이다. App.jsx:4-34 의 import 목록에도 없고, App.jsx:66-108 의 라우트 34개 어디에도 /evaluation 경로가 없다. MainSidebar.jsx:16-44 의 NAV_GROUPS·navigation.js 의 어느 탭 배열에도 없다.
그런데 화면 자체는 완성품이다 — EvaluationPage.jsx:22-30 이 `/api/evaluate/cases` 를 불러 케이스 목록을 채우고, :18·:130-147 이 targeted/full 평가 범위 토글을 그리고, :110 은 `navigate('/')` 로 홈 복귀까지 붙여 뒀다. 전용 스타일시트 pages/EvaluationPage.css 도 함께 존재한다.
번들은 단일 청크다 — frontend/dist/assets/index-DA2pDoUH.js 2,248,542 bytes, index-B_0Qpyl9.css 463,308 bytes 로 코드 스플리팅이 없으므로 이 고아 화면과 CSS 도 모든 첫 방문자가 내려받는다.
- **사용자가 겪는 장면**: 운영자가 생성 품질 평가를 UI 로 돌리려고 사이드바를 훑는다 — '통계' 에는 '워크플로우 평가' 항목이 사용량 종류로만 등장하고(StatisticsPage.jsx:35), 평가를 실행할 화면은 어디에도 없다. 주소창에 /evaluation 을 직접 쳐도 App.jsx 의 라우트 목록에 없으니 매칭되는 Route 가 없어 아무 것도 렌더되지 않는 빈 화면이 나온다(catch-all `*` 라우트조차 없다). 결국 평가는 CLI 로만 돌게 되고, 이미 만들어 둔 targeted/full 범위 선택 UI 는 아무도 쓰지 못한 채 모든 방문자의 첫 로딩에 계속 실려 나간다.
- **수정안**: 둘 중 하나를 택한다. (a) 살릴 경우: App.jsx 에 `/admin/evaluation` 을 AdminRoute 로 추가하고 AdminPage.jsx:21 의 섹션 배열에 항목을 넣어 어드민 nav 에서 도달하게 한다(운영자 전용 도구이므로 AdminRoute 가 맞다). (b) 버릴 경우: pages/EvaluationPage.jsx·EvaluationPage.css 를 삭제한다. 어느 쪽이든 App.jsx 에 `<Route path="*" ...>` 폴백을 두어 없는 주소가 빈 화면이 되지 않게 하는 것을 함께 한다.

## 데이터 계층과 마이그레이션 (backend/models.py, backend/migrations/versions/*, backend/database.py, 트랜잭션 경계·인덱스·보존)

> 감사 범위: 실제로 읽은 것: backend/database.py 전체, backend/db_migrate.py 전체, backend/alembic.ini(관련 부분), backend/migrations/env.py 전체, migrations/versions/ 21개 파일 전부를 grep 수준으로 훑고 0014·0015·0017 은 전문. models.py 는 1~120, 165~400, 430~560, 620~960 구간(모든 테이블 정의를 최소 한 번은 봄). backend/upload_security.py, backend/scheduler.py, backend/usage_tracking.py, backend/community_templates.py, backend/community_shares.py, backend/community_posts.py, backend/community_safety.py, backend/connectors/cursor.py, backend/statistics_service.py, backend/artifacts.py 의 데이터 접근 부분. main.py 는 264KB 라 전체는 못 읽었고 grep 으로 찾은 삭제 경로(1019~1044, 1300~1332), record_usage 호출부(1700~1760, 1920~1975), N+1 후보(1216~1245, 3340~3375), 템플릿 slug 조회(3900~

### 🟠 HIGH · record_usage 가 "커밋하지 않는다"고 문서에 못 박았는데 내부의 record_first_run 이 db.commit() 을 해서, 실행 로그 저장이 실패해도 토큰 차감은 이미 확정된다

- **위치**: `backend/usage_tracking.py:173`
- **분류**: data-integrity · **추정** 2.5h · **감사자 확신** high
- **근거**: usage_tracking.py:128-131 docstring — "The function intentionally does not commit. Callers may add node logs or other state and commit everything atomically."
usage_tracking.py:136-143 — `user = db.query(models.User)...with_for_update().first()` 뒤 `user.token_balance = int(user.token_balance or 0) - normalized_total` (차감).
usage_tracking.py:168-176 —
```
if event_type == EVENT_WORKFLOW_EXECUTION and project_id:
    try:
        import community_templates
        community_templates.record_first_run(db, project_id, normalized_outcome)
```
community_templates.py:571-582 `record_first_run` 의 마지막 줄이 `db.commit()` 이다.

스크래치패드 sqlite 로 재현했다(제품 코드 수정 없음). 템플릿에서 설치한 프로젝트(TemplateInstall.first_run_outcome IS NULL)를 만들고 record_usage 를 호출한 뒤 호출부가 실패한 것처럼 db.rollback() 만 했더니:
  balance before: 1000 -> after rollback: 900
  flow_execution_logs rows after rollback: 1
  node_execution_logs rows: 0
  fi
- **사용자가 겪는 장면**: 커뮤니티 템플릿으로 설치한 프로젝트를 에디터에서 처음 실행한다. main.py:1930 이 record_usage 로 토큰을 차감하고 로그 행을 만든 뒤, main.py:1944-1961 에서 노드별 로그를 붙인다. 이때 `datetime.datetime.fromisoformat(step['start_time'])`(main.py:1945-1946)이 깨진 타임스탬프를 만나 ValueError 를 던지거나 result_data 가 컬럼 제약을 넘기면, except 절(main.py:1962-1964)이 `print("Failed to save log to DB")` 후 `db.rollback()` 한다. 그런데 record_first_run 이 이미 커밋해 버렸으므로 롤백이 되돌리는 것은 노드 로그뿐이다 — 사용자는 토큰이 100 빠진 채로, 실행 기록 목록에는 "성공" 한 줄이 있는데 그 줄을 눌러도 노드 단계가 텅 빈 실행을 보게 된다. 서버 로그에는 print 한 줄만 남고 사용자에게는 아무 오류도 안 간다. 같은 이유로 `with_for_update()` 로 잡은 users 행 잠금도 record_usage 가 반환하기 전에 풀려서, 원래 의도했던 "차감과 로그를 한 트랜잭션에서"라는 보장이 사라진다.
- **수정안**: record_first_run 에 `commit: bool = True` 파라미터를 붙이고(community_safety.record_action 이 이미 같은 패턴을 쓴다 — community_safety.py:206-221), usage_tracking.py:173 에서는 `commit=False` 로 부른다. record_usage 가 호출부의 트랜잭션 안에서만 동작한다는 계약을 테스트로 고정한다: record_usage 직후 rollback 하면 token_balance 와 flow_execution_logs 가 둘 다 원상복귀해야 한다(위 재현 스크립트를 그대로 pytest 로 옮기면 된다). 부수적으로 main.py:1962-1964 의 except 가 오류를 삼키는 것도 최소한 outcome 에 남기도록 고친다.

### 🟠 HIGH · templates.slug 의 unique 제약이 마이그레이션 0014 에서 빠져 운영 DB 에는 없다 — 모델·테스트만 unique 라서 드리프트가 검출되지 않는다

- **위치**: `backend/migrations/versions/0014_community_templates.py:34`
- **분류**: data-integrity · **추정** 3.5h · **감사자 확신** high
- **근거**: models.py:801 — `slug = Column(String, unique=True, nullable=False, index=True)`
migrations/versions/0014_community_templates.py:34 — `sa.Column("slug", sa.String(), nullable=False),`  ← unique=True 가 없다
migrations/versions/0014_community_templates.py:46 — `op.create_index("ix_templates_slug", "templates", ["slug"])`  ← 평범한 인덱스

운영 RDS 읽기 전용 조회 결과(pg_index):
  ('ix_templates_slug', False, 'slug')   ← indisunique=False
  ('templates_pkey',    True,  'id')
  → templates 에 slug 유일 인덱스/제약이 **없다**. 비교 대상: 같은 마이그레이션 계열에서 `unique=True` 를 제대로 쓴 workspaces.slug 는 ('workspaces_slug_key', True, 'slug'), community_profiles.handle 은 ('community_profiles_handle_key', True, 'handle') 로 존재한다.

왜 안 걸렸는가: 테스트는 전부 `Base.metadata.create_all(engine)` 로 스키마를 만든다(test_community_templates.py:40, test_workspaces.py, test_project_revisions.py:28 등 15개 이상). create_all 은 모델의 unique=True 를 그대로 만들므로 테스트 DB 에는 제약이 있다.
- **사용자가 겪는 장면**: 두 사용자가 같은 주소(예: `daily-report`)로 템플릿 게시를 거의 동시에 누른다. 둘 다 community_templates.py:181 의 조회에서 "없다"를 보고 통과하고, DB 에 제약이 없으므로 두 행이 모두 들어간다(운영은 워커 1개지만 async 엔드포인트라 요청이 겹칠 수 있고, 재시도/더블클릭으로도 재현된다). 그 뒤 `/api/templates/daily-report` 소개 페이지는 main.py:3904 의 `.first()` 가 돌려주는 한쪽만 보여주므로, 나머지 템플릿은 게시 성공 메시지를 받았는데도 자기 링크로 절대 열리지 않는다. 작성자는 "게시했는데 남의 템플릿이 뜬다"로 문의하고, 운영자는 화면상 존재하지 않는 행을 지워야 한다. 249개 공식 템플릿을 스크립트로 일괄 게시/보수하는 운영 작업(enrich_curated_templates.py)에서도 같은 slug 로 두 번 도는 사고가 조용히 통과한다.
- **수정안**: (1) 새 마이그레이션에서 중복 slug 를 먼저 정리(있으면 `slug || '-' || id` 로 재명명하고 리다이렉트 표를 남긴다 — 현재 운영에는 중복 0건임을 확인했으니 지금은 무손실로 붙일 수 있다) 후 `op.create_unique_constraint`/`create_index(..., unique=True)` 로 제약을 만든다. (2) 근본 대책으로 pytest 를 하나 추가한다: 임시 sqlite 에 `alembic upgrade head` 를 돌린 뒤 `alembic.autogenerate.compare_metadata(ctx, Base.metadata)` 결과에서 PK 부수 인덱스 같은 알려진 잡음만 화이트리스트로 걸러 diff 가 비었는지 단정한다. 이 테스트가 있으면 앞으로 손으로 쓰는 마이그레이션이 모델에서 갈라지는 일을 즉시 잡는다(이 저장소가 이미 node_definitions 에서 겪은 "정의에서 파생하지 않은 목록은 조용히 갈라진다"와 같은 부류다). (3) 애플리케이션 쪽은 IntegrityError 를 잡아 같은 "이미 사용 중인 주소입니다" 메시지로 변환한다.

### 🟠 HIGH · APScheduler interval 잡의 첫 실행이 등록 시각 +24시간이고 잡 저장소가 메모리라, 배포마다 재시작되는 운영에서 업로드 만료 정리와 템플릿 유지율 측정이 사실상 한 번도 돌지 않는다

- **위치**: `backend/scheduler.py:203`
- **분류**: ops · **추정** 1.5h · **감사자 확신** high
- **근거**: scheduler.py:12 — `scheduler = AsyncIOScheduler()`  ← jobstore 지정 없음 = MemoryJobStore, 프로세스가 죽으면 잡과 다음 실행 시각이 함께 사라진다.
scheduler.py:200-209 —
```
if not scheduler.get_job("purge_expired_uploads"):
    scheduler.add_job(purge_expired_uploads_job, "interval", hours=24,
                      id="purge_expired_uploads", replace_existing=True)
```
start_date/next_run_time 을 주지 않았다. scheduler.py:221-229 의 measure_template_retention(24h), 211-219 의 purge_rate_limit_counters(6h) 도 같다.

APScheduler 의 동작을 venv 에서 직접 확인:
```
$ ./venv/bin/python -c "from apscheduler.triggers.interval import IntervalTrigger; ..."
apscheduler 3.11.3
start_date 2026-09-01 13:55:33+00:00
now        2026-08-31 13:55:33
```
venv/lib/python3.12/site-packages/apscheduler/triggers/interval.py:17 docstring — "starting on start_date if specified, datetime.now() + interval otherwise".

운영 프로세스의 나이:
```
$ systemctl show fastapi 
- **사용자가 겪는 장면**: 운영자가 하루에 한 번 이상 배포하거나(현재 개발 속도가 그렇다) 프로세스가 재시작되면, purge_expired_uploads_job 은 예정 시각에 도달하지 못하고 매번 24시간 뒤로 밀린다. 결과: 보존 기간(기본 30일)이 지난 업로드 파일이 디스크와 uploaded_files 에 무한히 남는다 — ADR-0010 이 약속한 보존 정책이 코드에는 있지만 실행되지 않는다. measure_template_retention_job 도 마찬가지라서 TemplateInstall.retained_at_7d 가 영원히 NULL 이고, community_templates.quality_signals(community_templates.py:598-604)가 계산하는 "7일 유지" 품질 신호가 항상 0 으로 나온다 — 템플릿 정렬의 1차 기준(ADR-0023)이 조용히 죽은 값이 된다. 운영자는 화면에 아무 오류도 없으니 이 사실을 알 수 없다. (현재 운영 데이터로는 만료된 업로드가 아직 0건, 7일 경과 설치가 0건이라 증상이 드러나기 직전 상태다 — 가장 이른 업로드의 expires_at 이 2026-09-28 이므로 그때부터 새기 시작한다.)
- **수정안**: add_job 세 곳에 `next_run_time=datetime.datetime.now(tz)` 를 주어 프로세스 시작 직후 한 번 돌게 한다(또는 CronTrigger 로 바꿔 절대 시각에 고정한다 — 재시작에 영향받지 않는 편이 낫다). 잡이 실제로 언제 도는지 검증할 방법도 함께 만든다: 각 job 에 마지막 실행 시각을 남기고 /api/admin 진단에 노출하거나, 최소한 startup 로그에 `next_run_time` 을 찍는다. 지금은 "등록했다"만 로그에 나와서 등록과 실행이 구분되지 않는다(scheduler.py:210 `print("[Scheduler] Registered daily upload cleanup.")`).

### 🟡 MEDIUM · 커뮤니티 soft delete 의 "30일 뒤 hard delete" 는 문서 3곳에 적혀 있지만 구현이 없다 — Report.resolved_at 은 쓰기만 하고 아무도 읽지 않는다

- **위치**: `backend/community_posts.py:200`
- **분류**: data-integrity · **추정** 4h · **감사자 확신** high
- **근거**: models.py:632 — `deleted_at = Column(DateTime, nullable=True, index=True)   # soft delete → 30일 → hard delete`
community_posts.py:200 — `"""soft delete. 신고 조사 중인 글이 사라지면 판단할 근거가 없어진다 — 30일 뒤 hard delete."""`
community_safety.py:298-299 — `# soft delete — 신고 조사 중에 근거가 사라지면 안 된다. 30일 뒤 정리된다.`
community_safety.py:199-200 — `# 보존 기간(30일)은 **신고 처리가 끝난 시점부터** 센다` + `row.resolved_at = datetime.datetime.utcnow() if status in ("resolved","rejected") else None`

그런데 정리하는 코드가 없다:
```
$ grep -rn "resolved_at" --include=*.py . | grep -v venv
community_safety.py:200   ← 쓰기
models.py:550             ← 컬럼 선언(index=True)
test_community_safety.py:172,174,176   ← 값이 찍히는지만 검증
migrations/versions/0011_community_safety.py:71,73
```
읽는 코드가 0건이다. 스케줄러에 등록된 잡은 셋뿐이고(scheduler.py:200,211,221) posts/answers/comments/reports 를 정리하는 것은 없다. community_safety.py 의 함수 목록에도 purge/cleanup 계열이 없다(is_staff…restore_user 까지 20
- **사용자가 겪는 장면**: 사용자가 실수로 개인정보가 들어간 질문 글을 올리고 삭제한다. community_posts.delete_post 는 deleted_at 만 찍고 status 를 hidden 으로 바꾼다(본문·태그·첨부 워크플로우 스냅샷은 posts / workflow_shares 에 그대로 남는다). 30일이 지나도 어떤 잡도 이 행을 지우지 않으므로 본문은 영구 보존된다. 사용자가 "삭제했는데 정말 지워졌나"라고 물으면 운영자는 "정책상 30일 뒤 삭제된다"고 답할 수밖에 없는데(모델 주석·docstring 이 그렇게 적혀 있다) 실제로는 지워지지 않는다. 신고 기록도 같다 — resolved_at 이 찍힌 신고가 무기한 쌓이고, 신고자 id·신고 사유·대상 본문이 계속 남는다. 부수 효과 하나 더: delete_post 는 unpin_images(community_posts.py:205)로 이미지의 보존 고정을 풀어 30일 뒤 파일이 정리되게 하는데, 글 행은 남으므로 관리자가 나중에 community_safety.moderate_content 로 글을 되살리면(community_safety.py:295 `row.deleted_at = None`) 본문은 돌아오지만 이미지는 이미 파일이 없어 깨진 채로 공개된다.
- **수정안**: scheduler 에 `purge_soft_deleted_community_content` 잡을 추가한다(발견 3 의 next_run_time 문제도 같이 고쳐야 실제로 돈다). 대상과 기준을 한 함수에 모은다: posts/answers/comments 는 `deleted_at <= now - 30d` AND 그 대상에 미처리 신고(status in ('pending','reviewing'))가 없을 때, reports 는 `resolved_at <= now - 30d`. 글을 지울 때 workflow_shares(owner_type='post', owner_id=post.id)와 execution_excerpts 도 같이 지운다 — workflow_shares 는 다형 참조라 FK 가 없어서(models.py:696-697) DB 가 대신 지워주지 않는다. 복원 창(30일)과 이미지 unpin 시점이 어긋나는 문제는 unpin 을 hard delete 시점으로 옮겨서 맞춘다. 테스트는 "미처리 신고가 있는 글은 30일이 지나도 남는다"를 반드시 포함한다(docstring 이 약속한 것이 그것이다).

### 🟡 MEDIUM · 업로드 용량 한도가 만료된 행까지 세는데 목록 조회는 만료된 행을 빼고, 사용자가 파일을 직접 지울 수단이 없어 화면에 안 보이는 파일 때문에 업로드가 막힌다

- **위치**: `backend/upload_security.py:143`
- **분류**: ux · **추정** 3h · **감사자 확신** high
- **근거**: 할당량 계산 — upload_security.py:136-147:
```
row = (db.query(func.coalesce(func.sum(models.UploadedFile.size_bytes), 0), func.count(models.UploadedFile.id))
       .filter(models.UploadedFile.owner_user_id == owner_user_id).one())
```
expires_at 조건이 없다. 이 값으로 upload_security.py:150-166 ensure_quota 가 413 을 던진다(기본 한도: 200MB / 200개 — upload_security.py:24-25).

목록 조회 — artifacts.py:525-534:
```
.filter(models.UploadedFile.owner_user_id == owner_user_id)
.filter(models.UploadedFile.artifact_id.isnot(None))
.filter((models.UploadedFile.expires_at.is_(None)) | (models.UploadedFile.expires_at > now))
```
같은 표를 두 기준으로 읽는다 — 목록은 만료분을 빼고, 할당량은 넣는다.

사용자가 스스로 지울 경로가 없다: `grep -n "delete.*artifact" main.py` → 0건. 유일한 해방 경로가 하루 한 번 도는 purge 잡이고(scheduler.py:203, 발견 3 때문에 실제로는 안 돈다) 그 잡도 한 번에 500행만 처리한다(upload_security.py:220 `limit: int = 500`).

오류 메시지 자체가 이 무력함을 인정한다 — upload_security.py:154-157: "업로드
- **사용자가 겪는 장면**: 워크플로우로 매일 첨부를 만드는 사용자가 200개 한도에 닿는다. 사이트의 파일 목록에는 예를 들어 140개만 보인다(60개는 expires_at 이 지났지만 purge 잡이 돌지 않아 행이 남아 있다). 사용자는 "140개인데 왜 200개 한도 초과냐"는 413 을 받고, 지울 버튼도 없으므로 할 수 있는 일이 없다. 발견 3 때문에 정리 잡이 영구히 밀리면 이 상태는 저절로 풀리지 않는다 — 결국 운영자가 DB 에 직접 들어가 행을 지워야 한다. 하루에 500개 넘게 만료되는 계정이 생기면 잡이 돌더라도 잔여가 계속 누적된다.
- **수정안**: current_usage 의 filter 에 artifacts.py:528 과 **똑같은** 만료 조건을 넣어 두 쿼리가 같은 정의를 쓰게 한다 — 더 좋은 것은 `_live_uploads(db, owner_user_id)` 같은 쿼리 팩토리 한 개를 두고 목록·할당량이 그것을 공유하는 것이다(이 저장소가 반복해서 겪은 "같은 규칙을 두 곳에 적으면 갈라진다" 패턴). 함께: 사용자가 자기 업로드를 지우는 DELETE 엔드포인트를 만들고(소유 검증 + 참조 중인 워크플로우 경고), purge 의 limit=500 을 "남은 게 있으면 다음 배치를 이어서 돌린다"로 바꾼다. 검증은 만료 행이 섞인 상태에서 목록 개수와 ensure_quota 판정이 일치하는지 pytest 로 고정한다(test_upload_security.py 에 붙일 자리가 이미 있다).

### 🟡 MEDIUM · 템플릿 설치가 두 트랜잭션으로 쪼개져, 두 번째 커밋이 실패하면 사용자에게 제목이 잘못된 프로젝트만 남고 설치 기록·설치 수·첫 실행 신호가 사라진다

- **위치**: `backend/community_templates.py:558`
- **분류**: data-integrity · **추정** 2h · **감사자 확신** high
- **근거**: community_shares.py:112-121 (`import_share`) —
```
project = models.Project(user_id=user.id, title=title, ...)   # title = "[가져온 워크플로우]"
db.add(project)
share.import_count = (share.import_count or 0) + 1
db.commit()          # ← 커밋 1
return project
```
community_templates.py:557-568 (`install`) —
```
project = community_shares.import_share(db, user, share)     # 여기서 이미 커밋됐다
project.title = f"[{template.title}] {version.version}"      # 커밋 1 이후의 변경
project.description = (f"커뮤니티 템플릿 '{template.slug}' v{version.version} 에서 가져왔습니다.")
db.add(models.TemplateInstall(template_version_id=version.id, installed_project_id=project.id, ...))
template.install_count = (template.install_count or 0) + 1
db.commit()          # ← 커밋 2
```
TemplateInstall.installed_project_id 에는 FK 가 없어서(models.py:870) DB 가 정합성을 대신 지켜주지도 않는다.
- **사용자가 겪는 장면**: 사용자가 템플릿 "[일일 리포트] 1.0.0" 을 설치한다. 커밋 1 이 끝나 프로젝트가 만들어진 직후 커밋 2 가 실패한다(연결 끊김, 배포로 인한 프로세스 종료, 또는 install_count 갱신에서의 경합). 사용자의 프로젝트 목록에는 제목이 "[가져온 워크플로우]" 이고 설명이 "커뮤니티에서 가져온 워크플로우 (share #972, revision None)" 인 프로젝트가 남는다 — 어느 템플릿의 어느 버전에서 온 것인지 화면에서 알 수 없다. 동시에 TemplateInstall 행이 없으므로 (a) 템플릿의 설치 수가 늘지 않고, (b) usage_tracking.record_usage → record_first_run 이 매칭할 행을 못 찾아 첫 실행 성공률(ADR-0023 의 핵심 품질 신호)에 이 설치가 영원히 반영되지 않고, (c) measure_template_retention_job 의 7일 유지 측정 대상에서도 빠진다. 작성자는 "설치는 되는데 카운터가 안 늘어난다"를 보고, 어디서 새는지 추적할 단서가 없다.
- **수정안**: import_share 에 `commit: bool = True` 를 두고(community_safety.record_action 과 같은 방식) install() 에서는 `commit=False` 로 불러서 프로젝트 생성·제목 설정·TemplateInstall·install_count 를 한 커밋으로 묶는다. 같은 패턴이 community_shares.create_share 를 쓰는 글 작성 경로(main.py:4544-4562)에도 있는데 거기서는 실패 시 `db.delete(post); db.commit()` 로 보상 트랜잭션을 손으로 쓰고 있다 — 그것도 같이 단일 트랜잭션으로 정리하면 보상 코드를 없앨 수 있다. 검증은 "커밋 2 지점에서 예외를 주입하면 프로젝트도 남지 않는다"를 pytest 로 고정한다.

### 🟡 MEDIUM · 트리거 중복 폴링을 막는 lease 가 아무 곳에서도 호출되지 않는 죽은 코드이고, 호출하더라도 행 잠금이 없어 두 워커가 동시에 lease 를 얻는다

- **위치**: `backend/connectors/cursor.py:133`
- **분류**: correctness · **추정** 3h · **감사자 확신** high
- **근거**: models.py:99-102 — `# 같은 노드를 두 워커가 동시에 폴링하면 둘 다 통지한다. 먼저 잡은 쪽만 진행한다.` 뒤에 `lease_owner`, `lease_expires_at` 컬럼. 즉 이 표의 설계 의도에 상호배제가 들어 있다.

그런데 호출부가 없다:
```
$ grep -rn "acquire_lease\|purge_stale_leases" --include=*.py . | grep -v venv | grep -v test_
connectors/cursor.py:133   ← 정의
connectors/cursor.py:181   ← 정의
```
실행 코드젠이 내보내는 wrapper 는 load/save 뿐이다 — graph.py:386-391:
```
lines.append("def _load_node_cursor(node_id, db, kwargs, provider=None):")
lines.append("    return _cursor_store.load(db, project_id=kwargs.get('project_id') or 0, node_id=node_id)")
lines.append("def _save_node_cursor(node_id, cursor, db, kwargs, provider=None):")
lines.append("    _cursor_store.save(db, cursor, ...)")
```
트리거 서비스도 select_new/cursor 만 쓴다(connectors/services/rss.py:118-131, connectors/services/naver_search.py:180-186).

게다가 acquire_lease 자체가 경합에 안전하지 않다 — cursor.py:147-166:
```
row = _row(db, proj
- **사용자가 겪는 장면**: RSS 트리거 + 스케줄 노드가 있는 워크플로우에서, 스케줄이 발화하는 순간에 사용자가 에디터의 "실행" 을 누른다(또는 웹훅이 겹친다). 두 실행이 각각 _load_node_cursor 로 같은 cursor 를 읽어 같은 새 항목 목록을 얻고, 각자 디스코드/카카오로 통지한다 — 사용자는 같은 RSS 항목 알림을 두 번 받는다. 이어서 두 실행이 _save_node_cursor 로 cursor 를 덮어쓰는데 늦게 끝난 쪽이 이긴다. 늦은 쪽이 더 적은 항목을 본 실행이었다면 seen_ids 에서 항목이 빠지고, 다음 폴링에서 **또 한 번** 같은 항목이 통지된다. cursor.py:1-10 의 문서와 models.py:99 의 주석은 이 상황이 막혀 있다고 읽히므로, 중복 알림을 조사하는 사람은 lease 를 먼저 의심하고 시간을 버린다.
- **수정안**: 둘 중 하나를 택해 코드와 문서를 일치시킨다. (a) 실제로 쓴다: graph.py 의 트리거 코드젠에 `_acquire_node_lease` wrapper 를 추가하고 폴링 전에 부르고 finally 에서 release 한다. 이때 acquire_lease 의 `_row` 조회를 `.with_for_update()` 로 바꾸고, 행이 없을 때의 동시 INSERT 는 uq_connector_cursor(models.py:103) 위반을 잡아 재시도한다. purge_stale_leases 도 스케줄에 등록한다. (b) 안 쓸 거라면 lease 컬럼과 두 함수를 지우고 models.py:99 의 주석을 "중복 폴링은 막지 않는다"로 고쳐, 다음 사람이 있다고 믿지 않게 한다. 어느 쪽이든 검증은 두 세션을 동시에 열어 acquire_lease 를 겹쳐 부르는 통합 테스트로 한다(sqlite 로는 재현이 안 되므로 TEST_POSTGRES_URL 을 쓰는 경로에 넣는다 — test_database_query_v2.py 가 이미 그 패턴이다).

### 🟡 MEDIUM · flow_execution_logs.execution_time 에 인덱스가 없어 모든 통계 조회가 Seq Scan 이고, /api/webhooks 는 웹훅 노드마다 그 정렬 쿼리를 반복하며, 이 표에는 보존 정책이 아예 없다

- **위치**: `backend/models.py:179`
- **분류**: perf · **추정** 3.5h · **감사자 확신** high
- **근거**: models.py:179 — `execution_time = Column(DateTime, default=datetime.datetime.utcnow)`  ← index 없음. 같은 클래스의 user_id·actor_user_id·billable_user_id·project_id·event_type·outcome·trigger_type·request_id 는 전부 index=True 인데 정작 범위·정렬에 쓰이는 컬럼만 빠졌다.
운영 RDS pg_indexes 확인: flow_execution_logs 에 execution_time 인덱스 없음(pkey + 위 8개 단일 컬럼 인덱스만).

이 컬럼이 range/order 의 주 컬럼이다 — statistics_service.py:145-148:
```
models.FlowExecutionLog.execution_time >= period["start_utc"],
models.FlowExecutionLog.execution_time <  period["end_utc"],
... .order_by(models.FlowExecutionLog.execution_time.asc())
```
(같은 함수가 이전 기간 비교까지 한 번 더 돈다 — 181-182행.)

운영에서 EXPLAIN ANALYZE(읽기 전용):
```
Sort  (cost=315.58..315.75 rows=69 width=730)
  Sort Key: execution_time
  ->  Seq Scan on flow_execution_logs  (rows=120) 
        Filter: (execution_time >= (now() - '30 days'::interval))
        Rows Removed by Filter: 813
```

N+1 — ma
- **사용자가 겪는 장면**: 지금은 933행이라 밀리초 단위지만 형태가 문제다. 프로젝트 하나가 5분 스케줄로 돌면 연 10만 행 / 300MB 이고, 통계 화면(hourly/weekly/monthly/yearly 네 탭)을 열 때마다 payload·result 를 포함한 폭 730바이트 행 전체를 Seq Scan 으로 훑고 정렬한다 — 대시보드가 수 초씩 걸리고 그 시간만큼 다른 요청의 커넥션을 잡는다. 웹훅 관리 화면은 웹훅 노드 수만큼 같은 정렬 쿼리를 반복하니 노드가 많은 사용자에게서 먼저 느려진다. 그리고 아무도 지우지 않으므로 RDS 스토리지는 단조 증가하고, 어느 시점에 운영자가 원인 없이 커지는 표를 손으로 잘라야 한다.
- **수정안**: (1) `execution_time` 에 인덱스를 추가한다 — 실제 쿼리 모양이 "project_id 로 좁히고 execution_time 으로 정렬"과 "execution_time 범위" 두 가지이므로 복합 인덱스 `(project_id, execution_time DESC)` 와 단일 `(execution_time)` 을 함께 넣고 EXPLAIN 으로 Index Scan 전환을 확인한다(모델과 마이그레이션 양쪽에 — 발견 2 의 드리프트 테스트가 있으면 한쪽만 고치는 사고를 막는다). (2) /api/webhooks 는 프로젝트 id 목록에 대해 마지막 실행을 한 번에 구하는 쿼리(윈도 함수 또는 GROUP BY max)로 바꾸고, 안쪽 노드 루프 밖으로 뺀다. /api/schedules 도 같이. (3) 보존 정책을 정한다: payload/result 를 저장 시 상한(예: 8KB)으로 자르고, N일 지난 로그는 본문 컬럼을 NULL 로 만드는(집계용 메타는 남기는) 정리 잡을 추가한다 — 이때 발견 3 의 next_run_time 문제를 먼저 고쳐야 잡이 실제로 돈다.

## 보안 — 비밀·정화·격리 (community_sanitize / python 격리 / 업로드·아티팩트 / SSRF / 자격증명 처리)

> 감사 범위: 실제로 끝까지 읽은 파일: backend/workflow_security.py, python_runtime.py, python_sandbox.py, url_guard.py, artifacts.py, upload_security.py, community_sanitize.py, credential_crypto.py, connectors/session.py, connectors/services/http_request.py, node_generators/action_nodes.py(httpRequest·webCrawler·pythonNode), node_generators/core_nodes.py(valueNode), node_generators/template_nodes.py(templateAnalyzer·fileModifier), documents/hwpx_runtime.py(경로 정규화 부분), usage_tracking.py(redact_payload_secrets), generation_trace.py(_SENSITIVE_DATA_KEY), community_posts.py(sanitize_markdown·가시성), main.py 의 관련 구간(정적 마운트 88, 커뮤니티 이미지 4625-4655, 글 이미지 검증 4510-4552, 실행 로그 2320-2420, 실행 기록 1715-1940), node_definitions/*.j

### 🔴 CRITICAL · valueNode 의 file_path 가 경로 제한 없이 open() 되어 backend/.env(DATABASE_URL·JWT_SECRET·OPENAI_API_KEY)가 워크플로우 결과로 그대로 나온다

- **위치**: `backend/node_generators/core_nodes.py:18`
- **분류**: security · **추정** 4h · **감사자 확신** high
- **근거**: core_nodes.py:18 은 사용자 값을 역슬래시 치환만 하고 끝낸다: `file_path = node.get('data', {}).get('file_path', '').replace('\\', '/')`. 그 값이 core_nodes.py:32-33 에서 그대로 생성 소스에 박힌다. `file_path=/home/ubuntu/app/backend/.env` 로 compile_workflow 를 돌린 결과(실측):
    if os.path.exists(r"/home/ubuntu/app/backend/.env"):
        with open(r"/home/ubuntu/app/backend/.env", 'r', encoding='utf-8', errors='replace') as f:
            file_content_v = f.read()
    val_v = f"[Attached File: /home/ubuntu/app/backend/.env]:\n{file_content_v}"
upload_security.py:260 의 resolve_stored_path 가 바로 이 목적으로 존재하고 docstring 에 "검증 없이 열면 `/etc/passwd` 같은 서버 파일이 외부로 업로드되거나 첨부될 수 있다" 고 적혀 있는데, 호출부는 connectors/services/youtube.py:62 와 drive.py:66 둘뿐이다(grep 전수). templateAnalyzer/fileModifier 는 최소한 'uploads/'+basename 으로 가두는데(template_nodes.py:56-57) valueNode 는 그것조차 없다. 생성 소스는 workflow_security.validate_compiled_workflow 를 통과한다 — 금지 목록(eval
- **사용자가 겪는 장면**: 가입만 한 사용자가 에디터에서 valueNode 하나를 놓고 file_path 에 `/home/ubuntu/app/backend/.env` 를 넣어(UI 는 업로드로 채우지만 PUT /api/projects/{id} 로 graph_data 를 직접 보내도 검증이 없다) 실행을 누른다. 결과 패널에 `[Attached File: /home/ubuntu/app/backend/.env]:` 뒤로 .env 전문이 출력되고 flow_execution_logs.result 에도 저장된다. 얻은 JWT_SECRET 은 세션 토큰 위조에 쓰이고, credential_crypto.py:19-23 이 JWT_SECRET 을 자격증명 복호화 키 후보로 쓰므로 UserApiKey 테이블에 저장된 **모든 사용자의** API 키·refresh token 을 복호화할 수 있다. DATABASE_URL 로 운영 PostgreSQL 에 직접 붙을 수도 있다.
- **수정안**: valueNode 의 파일 읽기를 upload_security.resolve_stored_path(raw_path, allowed_extensions=GENERAL_UPLOAD_EXTENSIONS|CONTEXT_UPLOAD_EXTENSIONS, max_bytes=...) 경유로 바꾸고, 더 좋은 건 file_path 를 폐기하고 artifactId 로 받아 artifacts.resolve(db, id, owner_user_id=__owner_user_id__) 를 쓰는 것이다(ADR-0018 이 이미 그 계약이다). 과도기에는 생성 코드에서 절대경로·'..' 를 거부하고 UPLOAD_DIR 안으로 강제하는 한 줄을 넣고, workflow_security.validate_compiled_workflow 의 금지 목록에 `open` 을 추가해 같은 부류의 재발을 컴파일 단계에서 막는다. 검증: test_p0_node_safety 에 '절대경로 valueNode 는 거부' 회귀 테스트 + 실제 실행 1회.

### 🔴 CRITICAL · /uploads 정적 마운트가 인증 없이 모든 업로드·생성 산출물을 서비스하고, 생성 파일 이름은 사람이 정한 값이라 주소를 맞히면 남의 자기소개서·포스터가 그대로 내려간다

- **위치**: `backend/main.py:88`
- **분류**: security · **추정** 8h · **감사자 확신** high
- **근거**: main.py:88 `app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")` — 인증 의존성이 없다. main.py 에 /uploads 를 가리는 미들웨어도 없다(add_middleware 는 112행 CORS 하나뿐). nginx 운영 설정(/etc/nginx/sites-enabled/app:71-77)도 `location /uploads/ { proxy_pass http://127.0.0.1:8000; }` 로 그대로 통과시킨다. 인증 헤더 없이 실측: `curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/uploads/output.docx` → 200, 1079 bytes / `/uploads/자기소개서.hwpx` → 200, 8468 bytes. main.py:4630-4632 는 커뮤니티 이미지에 대해 "/uploads 정적 경로로 바로 주지 않는 이유는 … 정적 경로는 주소만 알면 누구나 받을 수 있어서" 라고 문제를 정확히 알고 우회 엔드포인트를 만들었지만, 정적 마운트 자체는 남겨뒀다. 업로드는 uuid4 이름을 쓰지만(upload_security.py:109) 생성 산출물은 사용자·LLM 이 정한 이름을 쓴다 — documents/hwpx_runtime.py:80 `return "uploads/" + name`, node_generators/template_nodes.py:197-198, official_templates/e.py:73 `output_path="작성완료.hwpx"`. 운영 디스크 실측 37개 중 30개가 uploaded_files 테이블에 없는(=소유자 없음, 만료 없음) 파일이고 이름이 전부 추측 가능하다: output.doc
- **사용자가 겪는 장면**: 누구든(로그인조차 필요 없다) https://wa-pnu.duckdns.org/uploads/자기소개서.hwpx 를 열면 다른 사용자가 워크플로우로 만든 자기소개서 전문을 받는다. poster_ 는 16진수 6자리(1600만)라 스크립트로 훑을 수 있고, output.docx·output.hwpx 처럼 기본 이름은 맞힐 필요조차 없다. 반대로 커뮤니티 글 이미지는 친구 공개로 걸어둬도 stored_name 만 알면 /uploads 로 우회 조회된다 — 4625행 엔드포인트가 지키는 가시성이 무의미해진다. 게다가 30개 파일은 등록 행이 없어 purge_expired_uploads(upload_security.py:224)의 대상도 아니라 영구히 남는다.
- **수정안**: main.py:88 의 정적 마운트를 삭제하고, 파일 접근을 전부 인증된 엔드포인트(GET /api/artifacts/{artifact_id}/content → artifacts.resolve(db, id, owner_user_id=user.id) → FileResponse)로 모은다. 프론트에서 `/uploads/...` 직접 참조를 쓰는 자리(FormatStudio.jsx:195 `previewUrl = \`/${res.data.file_path}\``, AppViewerPage.jsx:133/158, UIEngine.jsx:540, customNodes.jsx:792)를 artifactId 기반으로 바꾼다. 생성 산출물 이름도 사용자 값 대신 uuid 저장명 + original_name 표시로 분리한다(documents/hwpx_runtime.normalize_path, template_nodes 의 output_file). 정리: 등록 행이 없는 기존 30개 파일의 소유자를 확인해 백필하거나 격리 이동. 검증: 마운트 제거 후 Playwright 로 에디터 파일 미리보기·앱 러너 첨부·FormatStudio 미리보기가 실제로 렌더되는지 확인(빌드 통과만으로는 알 수 없다).

### 🟠 HIGH · GET /api/runs/{run_id} 의 권한 검사가 `if project:` 안에 들어 있어, 프로젝트가 삭제됐거나 project_id 가 NULL 인 실행 기록은 아무 로그인 사용자나 전부 읽는다 (운영 933건 중 882건)

- **위치**: `backend/main.py:2396`
- **분류**: security · **추정** 2.5h · **감사자 확신** high
- **근거**: main.py:2390-2404
    run = db.query(models.FlowExecutionLog).filter(models.FlowExecutionLog.id == run_id).first()
    if not run: raise HTTPException(404)
    project = db.query(models.Project).filter(models.Project.id == run.project_id).first()
    if project:
        if project.visibility == 'private' and project.user_id != user.id: raise HTTPException(403)
        ...
→ project 가 None 이면 어떤 검사도 하지 않고 run.result 와 모든 NodeExecutionLog.result_data / error_message 를 돌려준다(main.py:2406-2427). models.FlowExecutionLog.project_id 는 `Column(Integer, nullable=True, index=True)` 로 FK·cascade 가 없고(models.py:178), delete_project(main.py:1304-1332)는 BotLog 만 지우고 실행 로그는 남긴다 — 즉 프로젝트를 지우면 그 프로젝트의 모든 실행 기록이 '무주공산' 이 된다. 운영 PostgreSQL 읽기 전용 실측: 전체 flow_execution_logs 933건 중 project_id 가 가리키는 projects 행이 없는 것 272건, project_id IS NULL 610건 → 합계 882건(94.5%)이 무검사 대상. 같은 파일의 목록 엔드포인트(main.py:2320-2332)는 프로젝
- **사용자가 겪는 장면**: 공격자가 계정 하나를 만들고 `for id in 1..2000: GET /api/runs/{id}` 를 돈다. 삭제된 프로젝트·앱 러너·챗봇·스케줄러 실행 882건의 결과 전문과 노드별 result_data 가 그대로 응답된다 — databaseNode 가 뽑은 고객 이메일 목록, emailNode 가 보낸 본문, webCrawlerNode 가 긁은 내용, llmNode 에 들어간 원문이 여기 들어 있다. 피해자는 "프로젝트를 지웠으니 기록도 없어졌다"고 믿는다.
- **수정안**: 권한 검사를 `if project:` 밖으로 꺼내 '프로젝트를 못 찾으면 run 의 소유자 필드로 판정' 로 바꾼다 — run.billable_user_id / actor_user_id / user_id 중 하나라도 user.id 와 맞지 않으면 404. 판정 자체를 project_access 또는 community_posts.visible_post_query 처럼 한 함수로 모으고 목록·상세가 같은 함수를 쓰게 한다. 삭제 시 실행 로그를 함께 정리하거나(권장) 최소한 소유자 필드를 남기도록 delete_project 를 보완하고, 이미 남은 882건의 소유자를 백필한다. 검증: 다른 사용자 토큰으로 orphan run id 를 찍어 404 가 나오는 회귀 테스트.

### 🟠 HIGH · register_generated_file 이 stored_name 만으로 기존 행을 찾아 소유자 확인 없이 hash·크기를 갱신한다 — 같은 output_path 를 쓰는 다른 사용자가 남의 artifact 내용을 갈아치우고 검증까지 통과시킨다

- **위치**: `backend/artifacts.py:268`
- **분류**: data-integrity · **추정** 6h · **감사자 확신** high
- **근거**: artifacts.py:264-285 은 `resolved = (upload_root() / Path(path).name)` 로 이름만 남긴 뒤 `existing = db.query(models.UploadedFile).filter(models.UploadedFile.stored_name == resolved.name).first()` 로 찾고, 찾으면 owner_user_id 를 보지 않고 `existing.size_bytes = size_bytes; existing.sha256 = digest` 만 갱신한다. 저장 이름은 사용자 값이다 — documents/hwpx_runtime.py:80 `return "uploads/" + name`, template_nodes.py:197-198 `output_file = 'uploads/' + os.path.basename(output_file)`, 그리고 공식 템플릿이 아예 고정 이름을 싣는다(official_templates/e.py:73 output_path="작성완료.hwpx", :81/f.py:53 template_path="uploads/서식.hwpx"). PoC 실행 결과(sqlite 임시 DB, UPLOAD_DIR=임시디렉터리):
  A artifact: 1bb8a41e… owner: 1 sha: d561a64b438b
  B 등록 결과 artifact: 1bb8a41e… owner: 1      ← B 의 등록이 A 의 행을 돌려준다
  행 개수: 1 | owner: 1 | sha: 6edbef397dd0     ← A 의 행 hash 가 B 내용으로 갱신
  A 가 열게 되는 실제 내용: b'PK\x03\x04B-CONTENTB-CONTENT…'
즉 artifacts.resolve 의 sha256 검증(artifacts.p
- **사용자가 겪는 장면**: (1) 유출: 사용자 B 가 fileModifierNode 에 template_path="자기소개서.hwpx", output_path="steal.docx" 를 넣고 실행하면 A 의 문서가 통째로 복사돼 B 의 산출물이 되고 B 는 그걸 자기 artifact 로 첨부·다운로드한다. (2) 훼손: 공식 템플릿 e 를 두 사용자가 설치해 각자 실행하면 둘 다 uploads/작성완료.hwpx 를 쓴다 — 나중에 실행한 쪽 내용으로 앞 사람의 UploadedFile 행이 재해시되어, A 가 이메일/디스코드로 "내 계약서"를 첨부해 보내면 B 의 내용이 나간다. 전송 직전 검증은 hash 가 이미 맞춰졌으므로 아무 경고도 없다.
- **수정안**: ① register_generated_file 의 existing 조회에 `owner_user_id` (그리고 project_id) 조건을 넣고, 소유자가 다른 같은 stored_name 을 만나면 등록을 거부하고 새 저장명으로 다시 쓴다. ② 저장명 자체를 사용자 값에서 떼어낸다 — normalize_path / output_file 생성 시 `{uuid4().hex}{suffix}` 를 저장명으로 쓰고 사용자 문자열은 original_name(표시 이름)으로만 남긴다. ③ templateAnalyzerNode·fileModifierNode 의 template_path 를 artifactId 로 전환하거나, 최소한 artifacts.lookup_by_stored_path + artifacts.resolve(owner_user_id=__owner_user_id__) 를 거치게 한다. 검증: test_artifact_delivery.py:732 의 idempotent 테스트 옆에 '다른 소유자의 같은 이름은 새 행이 생기고 A 의 hash 는 변하지 않는다' 테스트 추가.

### 🟠 HIGH · httpRequestNode 만 url_guard 를 안 거쳐 SSRF 가 남아 있다 — 169.254.169.254 메타데이터·내부 관리 API 응답이 노드 결과로 사용자에게 되돌아온다

- **위치**: `backend/node_generators/action_nodes.py:52`
- **분류**: security · **추정** 5h · **감사자 확신** high
- **근거**: url_guard.py 의 모듈 docstring 이 이 위협을 명시한다: "`http://169.254.169.254/...` 나 `http://localhost:8000/admin` 이면 서버 내부를 긁어 사용자에게 돌려준다(SSRF)". 그런데 방어는 webCrawlerNode 에만 붙었다(action_nodes.py:103-114 가 url_guard.fetch_text 를 쓴다). httpRequestNode 경로에는 url_guard 가 없다 — action_nodes.py:52-56 에서 URL 을 만들고(비어 있으면 `_http_url_{id} = str(prev_res_var).strip()` — 즉 상류 LLM 출력이 곧 요청 대상), action_nodes.py:62-64 가 connectors/services/http_request.py:73 `session.request(method, str(url).strip(), **kwargs)` 로 보내고, connectors/session.py:201 이 `requests.request(method, url, **kwargs)` 를 allow_redirects 기본값(True)으로 그냥 호출한다. 실측 컴파일 결과(SSRF 검사 한 줄도 없음):
  _http_url_a = 'http://169.254.169.254/latest/meta-data/iam/security-credentials/'
  req_out_a = _http.call(_node_definition.get_definition('httpRequestNode'), method="GET", url=_http_url_a, ...)
  → 'url_guard' in src == False
DB 접속은 database_policy.py:77-128 이 link_
- **사용자가 겪는 장면**: 사용자가 httpRequestNode 하나에 url=`http://169.254.169.254/latest/meta-data/iam/security-credentials/` 를 넣고 실행하면(또는 앞 노드 출력이 그 문자열이면) 서버가 대신 요청해 응답 본문을 `req_out` 으로 돌려주고 실행 결과 패널에 그대로 표시한다. 클라우드 인스턴스면 IAM 임시 자격증명, 온프렘이면 http://127.0.0.1:8000/api/... 나 내부망 관리 페이지를 서버 권한으로 읽는다. 공개 도메인에서 내부 IP 로 302 하는 고전 우회도 그대로 통한다 — url_guard.fetch_text 는 홉마다 재검증하지만 이 경로는 requests 의 자동 리다이렉트를 쓴다.
- **수정안**: connectors/session.py 의 _requests_transport 진입점(또는 ConnectorSession.request)에서 url_guard.check_url 을 부르고 allow_redirects=False + 홉마다 재검증으로 바꾼다 — 한 곳에 넣으면 모든 connector 서비스가 함께 보호된다(공식 API 호스트는 어차피 is_global 을 통과한다). robots/일일상한은 크롤러 전용이므로 check_url 만 공유하고 fetch_text 는 재사용하지 않는다. localhost mock(integration_nodes.py:289 의 http://localhost:3002/mock/...)은 명시적 예외 목록으로 뚫는다. 검증: test_url_guard.py 옆에 'httpRequestNode 로 169.254.169.254 를 부르면 요청이 나가지 않고 URL_BLOCKED 로 끝난다' 테스트(가짜 transport 로 네트워크 없이).

### 🟠 HIGH · databaseNode.connectionString 이 정의에 secret/credential 선언이 없어, 커뮤니티 정화가 DB 비밀번호가 든 접속 문자열을 공개 스냅샷에 그대로 남기고 '지워진 항목' 에도 알리지 않는다

- **위치**: `node_definitions/databaseNode.json:24`
- **분류**: security · **추정** 3h · **감사자 확신** high
- **근거**: node_definitions/databaseNode.json:24-30 → `{"name": "connectionString", "kind": "text", "label": "DB 연결", "ui": {"hidden": true}}` — kind 가 secret 이 아니고 credential 블록도 없다(전 정의 파일 스캔에서 secret 선언은 discordNode.botToken, emailNode.smtp_credentials, imageGenerationNode.apiKey, llmNode.apiKey, httpRequestNode.headers 뿐). community_sanitize.rule_for 는 정의가 있으면 secret_fields/credential_fields 를 kind·credential 에서만 파생하므로 실측 결과가 `NodeRule(secret_fields=(), credential_fields=(), path_fields=(), attachment_fields=(), risk_flags=('database',))` 다. 실제 정화 실행 결과:
  입력  connectionString: "postgresql://appuser:S3cr3t-Prod-Pw@db.internal.corp:5432/sales"
  출력  connectionString: "postgresql://appuser:[이메일 제거됨]:5432/sales"   ← EMAIL_RE 우연 적중(부분)
  report: {"cleared": [], "needsInput": [], "requiredCredentials": []}       ← 사용자에게 아무 고지 없음
EMAIL_RE(community_sanitize.py:39)에 걸리지 않는 흔한 형태는 전문이 그대로 남는다(scrub_tex
- **사용자가 겪는 장면**: 사용자가 API 센터 대신 접속 문자열을 노드에 직접 붙여 넣고(필드가 ui.hidden 이라 본인은 지웠는지 확인하기 어렵다) 그 워크플로우를 Q&A 글이나 템플릿으로 공개한다. 게시 전 미리보기에는 '지워질 항목' 이 하나도 뜨지 않아 안전하다고 믿는다. 공개된 스냅샷을 아무나 내려받아 그 DB 에 접속한다 — 노출된 값은 재발급이 아니라 비밀번호 교체가 필요한 자격증명이다.
- **수정안**: ① databaseNode.json 의 connectionString 을 kind:"secret" + credential:{provider:"database"} 로 바꾸고 backend/export_node_definitions.py 로 frontend/src/generated 를 재생성, fastapi 재시작. ② community_sanitize 에 접속 URI 값 패턴(`scheme://user:pass@host`) 마스킹을 scrub_text 에 추가해 선언이 빠진 다른 필드도 덮는다. ③ test_community_qna.py:102 의 커버리지 테스트를 강화한다 — '규칙이 있다' 가 아니라 '비밀성 이름 패턴(token/secret/key/password/connection)에 걸리는 필드는 모두 secret_fields 또는 credential_fields 에 있다' 를 검사(정의에서 파생하도록). ④ 이미 게시된 스냅샷을 재정화하는 일회성 스크립트.

### 🟡 MEDIUM · 실행 로그 payload 정화가 키 이름 정규식이라, 정의가 kind:"secret" 이라고 선언한 httpRequestNode.headers(Authorization 토큰)를 놓치고 평문으로 DB 에 남긴다

- **위치**: `backend/usage_tracking.py:74`
- **분류**: security · **추정** 3h · **감사자 확신** high
- **근거**: usage_tracking.redact_payload_secrets(74-108)는 노드 정의를 보지 않고 generation_trace.py:21-24 의 하드코딩 정규식만 쓴다: `api.?key|token|secret|password|authorization|credential|connection.?string|bot.?token|access.?token|refresh.?token`. 그런데 node_definitions/httpRequestNode.json 은 비밀 필드 이름을 `headers` 로 선언한다(`{"name":"headers","kind":"secret","credential":{"provider":"openai"}}`) — 'headers' 는 위 정규식에 걸리지 않는다. 실측:
  gt._SENSITIVE_DATA_KEY.search("headers") → None
  redact_payload_secrets(...) 출력: "headers": "{\"Authorization\": \"Bearer sk_live_51H8xQ2abcdef\"}"  ← 원문 그대로
  같은 payload 안 emailNode.smtp_credentials 는 "[REDACTED_CREDENTIAL]" 로 정상 치환
main.py:1936 이 실행마다 `payload=json.dumps(payload.dict())` 로 그래프 전문을 넘기므로(usage_tracking.py:154 에서 redact 를 거친 뒤 저장) 이 값은 flow_execution_logs.payload 에 실행 횟수만큼 평문으로 쌓인다. 학습 데이터 쪽(generation_trace.sanitize_training_graph)도 같은 키 정규식이라 'Bearer <token>' 패턴만 우연히 잡고 나머지는 통
- **사용자가 겪는 장면**: 사용자가 httpRequestNode 의 headers 에 `{"Authorization": "Bearer sk_live_..."}` 를 넣고 워크플로우를 하루 수십 번 돌린다(API 센터 reference 를 쓰지 않는 흔한 사용법 — 필드가 자유 JSON 이다). API 센터 자격증명은 AES-GCM 으로 암호화되는데(credential_crypto.py) 이 토큰은 실행 로그에 평문으로 남는다. DB 백업 유출·운영자 조회·향후 로그 노출 엔드포인트 추가 어느 쪽이든 그대로 새고, 사용자는 자기 토큰이 로그에 있다는 사실을 모른다.
- **수정안**: redact_payload_secrets 를 node_definition 에서 파생시킨다 — 노드 type 별로 `{f.name for f in definition.fields if f.kind == 'secret' or f.credential}` 를 구해 그 필드를 치환하고, 정의가 없는 타입은 지금의 정규식 + community_sanitize.LEGACY_RULES 를 합집합으로 쓴다(정화와 로그 마스킹이 같은 출처를 보게 된다). 값 기반 패턴(_SECRET_PATTERNS)도 payload 경로에 함께 적용한다. 검증: test_p0_node_safety.py:189 옆에 '정의가 secret 이라고 선언한 모든 필드는 redact_payload_secrets 를 통과하지 못한다' 를 정의 전수로 도는 파라미터 테스트로 추가(새 노드가 추가돼도 자동 커버).

### ⚪ LOW · template_nodes 의 코드젠 이스케이프 순서가 뒤집혀 있다(.replace('\\','/') 가 마지막) — 따옴표가 든 서식 파일명이면 워크플로우 전체가 'Security validation failed' 로 컴파일 실패한다

- **위치**: `backend/node_generators/template_nodes.py:52`
- **분류**: correctness · **추정** 1.5h · **감사자 확신** high
- **근거**: template_nodes.py:52(및 동일한 173행)
  template_file = node.get('data', {}).get('template_path', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\\', '/')
마지막 `.replace('\\', '/')` 가 앞의 두 단계가 만든 이스케이프 역슬래시를 전부 '/' 로 바꿔 되돌린다 — `a"b` → (2단계) `a\"b` → (4단계) `a/"b`. 그 값이 생성 소스의 큰따옴표 문자열 약 10곳에 그대로 박힌다(`template_ext = "{template_file}"`, `os.path.exists("{template_file}")`, `_DocxDocument("{template_file}")` …). 실측 compile_workflow:
  payload 'a"b.hwpx' → Error: Security validation failed: generated workflow is invalid at line 249
같은 파일 document_nodes.py:23/88 은 순서가 올바르다(`.replace('\\','/')` 를 **먼저** 하고 나서 이스케이프). 즉 두 곳만 순서가 반대다. 다행히 임의 코드 주입까지는 가지 않는다 — 삽입 지점이 여러 곳이라 전부 문법적으로 성립시키기 어렵고 validate_compiled_workflow 의 ast.parse 가 걸러낸다(위 실측이 그 결과다). upload_security.validate_filename(83-99)은 파일명에서 따옴표를 제거하지 않으므로(artifacts.safe_filename 만 제거한다) 사용자 입력에 따옴표가 남을 수 있다.
- **사용자가 겪는 장면**: 사용자가 templateAnalyzerNode 의 서식 경로에 `보고서 "최종".hwpx` 처럼 따옴표가 든 이름을 적거나 챗봇이 그런 이름을 지어내면, 실행을 누르는 순간 그 노드가 아니라 **워크플로우 전체**가 'Security validation failed: generated workflow is invalid at line 249' 로 죽는다. 어느 노드의 어느 필드가 문제인지 아무 단서가 없어서(줄 번호는 생성 소스의 줄이다) 사용자는 원인을 찾을 수 없고, 운영자는 보안 검증기가 오작동한 것으로 오해한다.
- **수정안**: template_nodes.py:52 와 173 의 replace 순서를 document_nodes.py:23 과 같게 고친다 — `.replace('\\','/')` 를 맨 앞으로 옮기거나, 더 낫게는 세 곳 모두 수동 이스케이프를 버리고 `repr()`(pythonNode 가 이미 쓰는 `{user_code!r}` 방식)로 통일한다. 겸사겸사 upload_security.validate_filename 에도 artifacts._UNSAFE_FILENAME_CHARS 와 같은 문자 제거를 적용해 두 곳의 파일명 규칙을 하나로 맞춘다. 검증: test_codegen_escaping.py 에 따옴표·역슬래시·개행이 든 template_path/output_path 가 compile_workflow 를 통과하고 경로가 원래 이름을 보존하는지 확인하는 케이스 추가.

## 정본과 파생물의 드리프트 (node_definitions / workflow_patterns / error_catalog / document_formats 와 그 파생물·소비자)

> 감사 범위: [실제로 읽고 실행한 것]
· 파생 파이프라인 전체: backend/export_node_definitions.py 를 `--check` 로 실행 → 7개 산출물(nodeDefinitions/credentialProviders/errorCatalog/ERROR_CATALOG.md/workflowPatterns/documentFormats/bindableFields) 모두 "최신 상태". 번들 드리프트는 없다.
· 정본 51종 카탈로그를 meta_agent._NODE_CATALOG_TEMPLATE 에서 추출해 (a) node_registry 코드젠 51종, (b) EditorPage.jsx nodeTypes 46종 + nodeRegistry.js 7종, (c) editorNodeCatalog STATIC_EDITOR_NODES, (d) meta_agent.NodeType, (e) dry_run.TRIGGER_NODE_TYPES, (f) node_knowledge.NODE_ALIASES 와 전수 대조 — **등록 누락은 0건**. 트리거 목록 3곳(정의/START_NODE_TYPES/dry_run/프론트 kind='trigger')도 일치.
· nodeDocumentation.js 52종을 node 스크립트로 실행해 팔레트 커버리지·related 참조·fields 키 ↔ 실제 필드명 전수 대조 — 불일치 0건.
· workflow_pat

### 🔴 CRITICAL · slackNode 는 정의가 external-write·카탈로그가 "슬랙 메시지 발송"·문서가 "API 센터에 토큰 등록"이라고 말하지만, 코드젠은 print 한 줄뿐이라 실제로 아무것도 보내지 않는다

- **위치**: `backend/node_generators/integration_nodes.py:207`
- **분류**: correctness · **추정** 5h · **감사자 확신** high
- **근거**: 코드젠 전문(187~210행)에 HTTP 호출이 없다. 실제로 컴파일해 확인했다 —
  graph.compile_workflow([startNode, slackNode{channel:'#general',message:'보고'}], edges) →
    # --- Slack Node (n2) ---
    slack_channel_n2 = '#general'
    slack_msg_n2 = '보고'
    print(f'Mocking Slack send to {slack_channel_n2}: {slack_msg_n2}')
    last_result = slack_msg_n2
    log_step('n2', 'slackNode', _start_n2, result=last_result)
  생성 소스 전체에 'slack.com' 문자열이 없다(False). 정의 파일에서 token 계열 필드를 찾을 수 없고 credentials 도 빈 배열이다.

반면 정본과 파생물은 전부 "실제 발송"이라고 말한다:
· node_definitions/slackNode.json:48  "sideEffect": "external-write"  (credentials: [] 인데도)
· node_definitions/slackNode.json llm.description  "슬랙 메시지 발송. data.channel …"
· backend/testdata/node_catalog_snapshot.txt:422  "- slackNode : 슬랙 메시지 발송. …"
· frontend/src/nodeDocumentation.js:630,637  summary '슬랙 채널로 메시지를 발송합니다.' / tips ['슬랙 토큰은 API 센터에 등록해 연결하세요.']
· backend/node_bindings.p
- **사용자가 겪는 장면**: 사용자가 "매일 아침 뉴스 요약해서 슬랙 #general 에 보내줘"라고 입력한다. 카탈로그가 slackNode 를 발송 노드로 알리므로 LLM 은 scheduleNode→…→slackNode 를 생성한다. 에디터에서 실행하면 "실제 실행하면 아래 노드가 외부로 전송·기록합니다 · Slack 메세지" 확인창이 뜨고(사용자는 진짜 나간다고 믿는다), 실행 로그는 slackNode 가 status='success' 이며 result_data 에 보낼 메시지 본문이 그대로 찍힌다. 그런데 슬랙 채널에는 아무것도 오지 않는다. 원인을 찾으려 노드 문서를 열면 "슬랙 토큰은 API 센터에 등록해 연결하세요"라고 안내하는데, API 센터에는 슬랙 항목 자체가 없어 사용자는 등록할 방법을 찾지 못하고 "토큰을 못 넣어서 안 갔나" 하며 무한히 헤맨다. 스케줄로 배포하면 매일 조용히 성공 로그만 쌓인다.
- **수정안**: 둘 중 하나를 택하고 정본을 그에 맞춘다. (A) 실제 구현: credential_providers.json 에 slack provider(bot token) 추가 → slackNode.json 에 token 필드+credentials 추가 → delivery_runtime 을 타는 실제 chat.postMessage 호출로 코드젠 교체(discordNode 와 같은 NodeError 매핑) → export 재실행 → nodeDocumentation·카탈로그 문구 확인. (B) 미구현 선언: 카탈로그에서 slackNode 를 빼고(또는 "현재 미지원"으로 명시) 정의의 sideEffect 를 none 으로 내리고 팔레트에서 감춘다. 어느 쪽이든 재발 방지 테스트를 함께 넣는다 — "정의가 sideEffect: external-write 이면서 credentials 가 비어 있고 코드젠에 외부 호출/런타임 모듈 참조가 없는 노드"를 금지하는 검사(현재 이 조건을 만족하는 유일한 노드가 slackNode 다).

### 🟠 HIGH · webCrawlerNode 코드젠이 error_catalog.json 에 없는 error_code(URL_BLOCKED·CRAWL_FAILED)를 __node_meta__ 에 쓴다 — "정본은 이 파일 하나" 규칙을 우회하고, 그 결과 실행 로그에는 성공으로 남는다

- **위치**: `backend/node_generators/action_nodes.py:129`
- **분류**: data-integrity · **추정** 2.5h · **감사자 확신** high
- **근거**: backend/node_generators/action_nodes.py:129,132
  lines.append(f"{indent}    _set_node_meta('{node_id}', status='error', error_code='URL_BLOCKED', error_message=str(e))")
  lines.append(f"{indent}    _set_node_meta('{node_id}', status='error', error_code='CRAWL_FAILED', error_message=str(e))")

두 code 는 정본에 없다:
  $ grep -n "URL_BLOCKED\|CRAWL_FAILED" error_catalog.json  → 없음(exit 1)
  node_errors.catalog.has('URL_BLOCKED') == False, has('CRAWL_FAILED') == False
 error_catalog.json:2 의 _comment 는 "정본은 이 파일 하나다 … 새 code 는 catalog 에 먼저 등록한다"고 못박고, node_errors/catalog.py:36 은 catalog 밖 code 사용을 UnknownErrorCode("프로그래밍 오류다")로 규정한다. 정상 경로(graph.py:445)는 node_error.code 만 쓰므로 catalog 를 통과하는데, 이 두 자리만 문자열 리터럴로 우회한다.

같은 실패가 실행 로그에서는 성공으로 남는다: action_nodes.py:124-132 는 예외를 직접 삼키고 crawl_res 에 '수집하지 않았습니다: …' / 'Crawling failed: …' 를 넣은 뒤 log_step(result=...) 을 호출한다. graph.py:406-427 의 log_step 은 n
- **사용자가 겪는 장면**: 운영자가 크롤링 흐름을 배포한다. 대상 사이트가 robots.txt 로 막히거나 일일 상한에 걸려 url_guard.UrlBlocked 가 난다. 사용자 화면의 실행 로그에는 webCrawlerNode 가 초록색 성공으로 표시되고 결과칸에 '수집하지 않았습니다: …' 텍스트만 있다. NodeErrorCard 는 뜨지 않아 '해결 동작' 버튼(robots 안내·API 센터 이동)도 없고, 커뮤니티 Q&A 의 error_code 묶음(/community/qna?error_code=…)에도 이 실패가 집계되지 않는다. 운영자가 Documents/ERROR_CATALOG.md 에서 CRAWL_FAILED 를 찾아도 항목이 없어 무슨 오류인지 확인할 방법이 없다. 하류 llmNode 는 __node_meta__ 힌트 덕에 "자료가 아니라 오류 안내문"이라고만 듣고 넘어가므로, 결과물은 "수집하지 못했습니다"를 요약한 문서가 되어 사용자에게 배달된다.
- **수정안**: error_catalog.json 에 crawl 카테고리 code 2개를 등록한다(예: CRAWL_URL_BLOCKED / CRAWL_FAILED, owner=runtime 또는 신규 crawl, resolution=focus_field, retryable=false/true, effectStateDefault=not_applicable) → export_node_definitions.py 재실행(errorCatalog.json + ERROR_CATALOG.md 자동 생성) → action_nodes.py 를 NodeError 를 실어 log_step(error=...) 하도록 바꿔 실행 로그 status 가 error 로 남게 한다 → test_pipeline_channels.py 의 리터럴 assert 를 code 이름으로 갱신. 재발 방지: backend/**/*.py 에서 `error_code='...'` / `code="..."` 리터럴을 정규식으로 모아 전부 node_errors.catalog.has() 를 통과하는지 검사하는 테스트를 test_node_errors.py 에 추가(현 저장소에서는 이 2건만 걸린다).

### 🟠 HIGH · 프론트 nodeWritesExternally 가 "정의 우선" 규칙이라, 정의가 생기면서 databaseNode·fileModifierNode·posterGeneratorNode 가 하드코딩 목록에서 조용히 탈락 — 백엔드 dry_run 의 합집합 규칙과 갈라져 실제 실행 확인창이 안 뜬다

- **위치**: `frontend/src/nodeTestFixtures.js:132`
- **분류**: correctness · **추정** 2.5h · **감사자 확신** high
- **근거**: frontend/src/nodeTestFixtures.js:116-134
  // 백엔드 dry_run.SIDE_EFFECT_NODE_TYPES 와 같은 근거를 쓴다:
  // 정의가 있는 노드는 정의의 sideEffect 에서, 아직 정의로 옮기지 않은 노드는 아래 목록에서.
  const LEGACY_SIDE_EFFECT_TYPES = new Set([ 'databaseNode', 'discordNode', 'emailNode', 'fileModifierNode', 'googleCalendarNode', 'googleSheetsNode', 'httpRequestNode', 'kakaoNode', 'notionNode', 'paymentLinkNode', 'posterGeneratorNode', 'slackNode', 'telegramNode', 'tossNode', 'webCrawlerNode' ]);
  …
  if (definition?.sideEffect) return definition.sideEffect === 'external-write';   // ← 132행: 정의가 있으면 목록을 아예 보지 않는다
  return LEGACY_SIDE_EFFECT_TYPES.has(node.type);

백엔드는 **합집합**이다 — backend/dry_run.py:19-45
  SIDE_EFFECT_NODE_TYPES = { databaseNode, discordNode, emailNode, fileModifierNode, googleCalendarNode, googleSheetsNode, httpRequestNode, kakaoNode, notionNode, paymentLinkNode, posterGeneratorNode, slackNode, telegramNode, toss
- **사용자가 겪는 장면**: 사용자가 startNode → llmNode → fileModifierNode(서식 채워 파일 저장) 흐름을 만들고, 중간 노드를 고친 뒤 fileModifierNode 에서 우클릭 → "이 노드부터 실행"을 누른다. §7.1 에 따라 "실제 실행하면 아래 노드가 외부로 전송·기록합니다" 확인창이 떠야 하지만 external.length === 0 이라 확인 없이 곧바로 실제 실행되고, 파일이 생성되어 artifact 로 등록된다(같은 흐름을 백엔드 dry-run 으로 돌리면 fileModifierNode 는 "외부 쓰기"로 표시된다 — 사용자에게 서로 다른 두 판정이 보인다). databaseNode 만 있는 흐름도 같아서, 읽기 전용이라 해도 접속·쿼리가 실제 DB 로 나가는데 사전 확인이 없다. NodeInspector 의 "외부 전송" 배지도 사라져 사용자는 이 노드가 안전하다고 오해한다.
- **수정안**: nodeTestFixtures.js:123-134 를 백엔드와 같은 합집합으로 바꾼다 — connector.sideEffectByMode → 정의 sideEffect === 'external-write' → LEGACY 목록 순서로 OR 판정(`return definition?.sideEffect === 'external-write' || LEGACY_SIDE_EFFECT_TYPES.has(node.type)`). 더 나은 방향은 목록을 손으로 복제하지 않는 것: export_node_definitions.py 가 dry_run.SIDE_EFFECT_NODE_TYPES 를 sideEffectNodeTypes.json 으로 내보내고 프론트가 그것만 읽게 하면 이 부류의 재발이 구조적으로 막힌다. 검증은 nodeTestFixtures.test.js 에 3종(databaseNode/fileModifierNode/posterGeneratorNode)의 true 기대치를 추가 + 백엔드 목록과 프론트 판정이 51종 전체에서 일치하는지 대조하는 테스트, 그리고 Playwright 로 "이 노드부터 실행" 시 확인창이 뜨는지 확인.

### 🟡 MEDIUM · document_formats/*.json 의 output.allowed 는 정본인데 실행 경로가 전혀 읽지 않는다 — 시말서 포맷을 xlsx 로 렌더하면 정본이 금지한 조합인데도 파일이 만들어진다(에디터 드롭다운만 allowed 를 지킨다)

- **위치**: `backend/documents/format_renderer.py:96`
- **분류**: data-integrity · **추정** 2h · **감사자 확신** high
- **근거**: backend/documents/format_renderer.py:96-99
  allowed = DOCUMENT_OUTPUTS if layout == "document" else DESIGN_OUTPUTS   # ← spec 의 allowed 가 아니라 layout 전체 목록
  if output not in allowed:
      raise FormatSpecError(…, reason="FORMAT_OUTPUT_UNSUPPORTED")
 backend/documents/format_spec.py:28-29  DOCUMENT_OUTPUTS = ("hwpx","docx","pdf","xlsx") / DESIGN_OUTPUTS = ("pdf","png")
 backend/documents/format_runtime.py:86  chosen_output = (output or "").strip() or spec["output"]["default"]   ← default 만 쓰고 allowed 는 끝까지 안 본다(82-108행 전체에 spec["output"]["allowed"] 참조가 없다)

정본은 프리셋마다 다르게 선언한다:
  incident-report  allowed=['hwpx','docx','pdf']        job-application allowed=['hwpx','docx','pdf']
  official-letter  allowed=['hwpx','docx','pdf']        meeting-minutes allowed=['hwpx','docx','pdf','xlsx']
  proposal         allowed=['hwpx','docx','pdf','xlsx'] event-poster    allowed=['png','pdf']  tri-fold-
- **사용자가 겪는 장면**: LLM 생성이나 커뮤니티 템플릿 가져오기, 또는 bindings 로 채워진 흐름에 formatNode{formatId:'incident-report', output:'xlsx'} 가 들어온다(정의 enum 에 xlsx 가 있으므로 검증도 통과한다). 실행하면 서버가 거부하지 않고 시말서 서식을 엑셀 시트 한 장으로 렌더해 artifact 로 등록하고, 뒤의 emailNode 가 그 .xlsx 를 상대방에게 자동 첨부한다 — 결재선에 제출된 시말서가 표 조각 파일이다. 반대로 사용자가 그 노드를 에디터에서 열면 출력 드롭다운의 옵션은 hwpx/docx/pdf 뿐이라 value='xlsx' 가 어느 option 과도 일치하지 않아 선택칸이 빈 채로 보인다. 사용자는 "출력 형식이 비어 있는데 파일은 엑셀로 나온다"는 상태를 설명받지 못한다.
- **수정안**: format_runtime.run() 에서 chosen_output 을 정한 직후 spec["output"]["allowed"] 로 한 번 더 검사해 FORMAT_OUTPUT_UNSUPPORTED 를 던지거나(사용자 문구에 프리셋 이름과 허용 목록을 넣는다), render_format 의 allowed 를 `normalized["output"]["allowed"]` 로 바꾼다(format_spec.py:88-98 이 이미 layout 상위집합 검증을 하므로 안전하다). test_format_spec.py:193 의 skip 을 "허용 밖 조합은 FormatSpecError(FORMAT_OUTPUT_UNSUPPORTED) 로 거부된다"는 assert 로 바꾸고, 에디터에서 값이 옵션 밖일 때 경고 문구를 보여주는지 Playwright 로 확인한다.

### 🟡 MEDIUM · formatNode 정의의 output enum 5종과 llm.description 이 프리셋별 제약을 무시해, 문서 프리셋에 png 를 고른 그래프가 모든 정적 검증을 통과하고 실행에서만 FORMAT_OUTPUT_UNSUPPORTED 로 죽는다

- **위치**: `node_definitions/formatNode.json:27`
- **분류**: correctness · **추정** 3h · **감사자 확신** high
- **근거**: node_definitions/formatNode.json:27-42 — output 필드는 layout 구분 없이 5종을 모두 허용한다
  options: hwpx / docx / pdf / xlsx / png,  validation: [{rule: enum, allowMissing: true}]
같은 파일 61행 llm.description:
  "data.output(문자열 — 문서류는 hwpx|docx|pdf|xlsx, 디자인류(포스터·팜플렛)는 png|pdf. 비우면 포맷의 기본값)"
  → 프리셋 7종 중 incident-report·job-application·official-letter 는 xlsx 를 허용하지 않으므로 이 문구가 LLM 에게 틀린 조합을 가르친다.

검증이 통과하는 것을 실측했다:
  node_definition.validate_node_data('formatNode','n1',{'formatId':'incident-report','output':'png'})  → []
  같은 입력 xlsx → []   hwpx → []
실행은 죽는다:
  render_format(PRESETS_BY_ID['incident-report'], {}, 'png', …)
  → FormatSpecError / reason=FORMAT_OUTPUT_UNSUPPORTED / "document 포맷의 출력은 ('hwpx','docx','pdf','xlsx') 만 가능합니다: 'png'"

즉 정의(정본)의 enum → meta_agent.validate_flow → dry_run 까지 전부 초록이고, 실패는 사용자가 실제 실행한 뒤에야 나타난다. test_node_definitions.py 의 test_catalog_description_only_mentions_declared
- **사용자가 겪는 장면**: 사용자가 "시말서 써서 이미지로 보내줘" 또는 "제안서 만들어서 png 로 저장"이라고 요청한다. 카탈로그 문구가 formatNode 를 권하고 output 에 png 를 쓰는 것을 막지 않으므로 LLM 은 formatNode{formatId:'incident-report', output:'png'} 를 생성한다. 생성 직후의 검증·dry-run 이 모두 통과해 사용자에게 "흐름이 만들어졌습니다"로 제시되고, 실행 버튼을 누른 순간에만 "document 포맷의 출력은 ('hwpx','docx','pdf','xlsx') 만 가능합니다: 'png'" 오류가 난다. 사용자는 무엇을 고쳐야 하는지 모른 채(에디터 드롭다운에는 png 가 아예 없어 지금 값이 무엇인지도 보이지 않는다) 같은 요청을 재생성하며 반복 실패한다.
- **수정안**: (1) llm.description 을 프리셋별 허용 목록에 맞게 고친다 — "출력은 포맷마다 다르다. 확실치 않으면 output 을 비워 포맷 기본값을 쓴다"로 바꾸고 프리셋 나열에 각 허용 형식을 붙인다(정본 document_formats/*.json 에서 파생시켜 문구를 조립하면 프리셋 추가 시 자동 반영된다 — 지금은 프리셋 7종 이름도 이 설명에 손으로 적혀 있다). (2) 값 수준 검증을 추가한다: meta_agent 의 formatNode 검증(또는 flow_validation)에서 formatId 가 알려진 프리셋일 때 output ∈ spec.output.allowed 를 확인해 생성 단계에서 재시도가 걸리게 한다. (3) 재발 방지 테스트: 모든 프리셋 × 정의 enum 5종 조합에 대해 "정적 검증 통과 == render_format 이 받아들임"이 성립하는지 대조.

### 🟡 MEDIUM · paymentLinkNode 는 결제 링크를 localhost:3002 해커톤 목업 서버에 하드코딩으로 요청하는데, 카탈로그·노드 문서·dry_run(HIGH_RISK) 은 실제 결제 링크 생성으로 소개한다

- **위치**: `backend/node_generators/integration_nodes.py:289`
- **분류**: correctness · **추정** 3h · **감사자 확신** high
- **근거**: backend/node_generators/integration_nodes.py:289
  lines.append(f"{indent}    resp_{node_id} = requests.post('http://localhost:3002/mock/payment/create-link', json=payload_{node_id}, timeout=10)")
  — 환경변수·설정 분기 없이 리터럴이다(저장소 전체에서 3002 를 참조하는 곳은 이 한 줄과 mock_server/README.md·server.js 뿐).
 mock_server/README.md:1-4  "# 🚀 Mock API Server (MVP 해커톤 시연용) … 사업자 등록 이슈로 실제 연동이 불가능한 … 로컬에서 100% 동일하게 모방(Mocking)"
 mock_server/server.js:7  const PORT = 3002;

정본·파생물은 실제 기능이라고 말한다:
 · backend/testdata/node_catalog_snapshot.txt:418-421  "- paymentLinkNode: 주문 정보를 받아 결제 링크를 생성한다(결제 \"조회\"인 tossNode와 반대로 \"생성\"). … \"주문/결제 링크 만들어줘\" 같은 요청에 쓴다."
 · frontend/src/nodeDocumentation.js:641-648  summary '주문 정보를 받아 결제 링크를 생성합니다', io.output '생성된 결제 링크.'
 · backend/dry_run.py:29,49  SIDE_EFFECT_NODE_TYPES 와 HIGH_RISK_NODE_TYPES 에 모두 포함 → "실제 외부 쓰기·고위험"으로 분류
 · backend/node_knowledge.py:165  _CATALOG_SIDE_EFFECTS
- **사용자가 겪는 장면**: 사용자가 "주문 접수되면 결제 링크 만들어 카톡으로 보내줘" 흐름을 만들어 배포한다. 에디터에서 실행하면 "고위험·외부 전송" 확인창까지 뜨고 결과에 "✅ 주문이 확인되었습니다! 🔗 결제 링크: …" 가 나와 사용자는 진짜 결제 링크를 받았다고 믿는다. 실제로는 로컬 목업이 만든 가짜 URL 이고, 그 링크가 고객에게 카카오 알림톡으로 발송된다(kakaoNode 는 실제 발송이다). 목업 서버를 재시작하지 않은 운영 서버라면 링크 생성이 Connection refused 로 실패하는데, 실행 로그에는 여전히 초록색 성공으로 남고 결과 문자열만 'Payment Link Error: …' 라서 고객에게 오류 문구가 그대로 발송된다.
- **수정안**: 엔드포인트를 설정으로 뺀다(PAYMENT_LINK_BASE_URL 등, 미설정 시 노드가 NodeError(예: CONNECTOR_NOT_FOUND 또는 신규 code)로 즉시 실패하게 해서 성공으로 오해되지 않게 한다). 실패 경로는 문자열이 아니라 NodeError 를 log_step 에 실어 status='error' 로 남긴다. 그리고 정본을 실제 상태에 맞춘다 — 카탈로그와 nodeDocumentation 에 "현재는 목업 연동(시연용)"을 명시하거나, 실제 PG 연동이 없다면 카탈로그에서 내려 LLM 이 이 노드를 고르지 않게 한다. 검증: 목업을 내린 상태로 흐름을 실행해 실행 로그가 error 로 남는지 확인.

### ⚪ LOW · 합성 학습 데이터가 존재하지 않는 slackNode.token 필드와 등록되지 않은 {{API_CENTER:slack}} provider 를 정답 예시로 가르친다

- **위치**: `backend/training/generate_synthetic.py:189`
- **분류**: maintainability · **추정** 1h · **감사자 확신** high
- **근거**: backend/training/generate_synthetic.py:189
  slack = b.add("slackNode", {"token": "{{API_CENTER:slack}}", "channel": "{{slack_channel}}"})
 backend/training/generate_synthetic.py:204  (동일 패턴 반복)

두 값 모두 정본에 없다:
 · node_definitions/slackNode.json 의 fields 는 channel, message 두 개뿐이다 — token 필드가 없다(frontend/src/nodeRegistry.js:9-11 도 동일).
 · credential_providers.json 의 provider id 17개에 slack 이 없다. 저장소 전체에서 `{{API_CENTER:<id>}}` 리터럴을 스캔해 provider 목록과 대조한 결과 **미등록 참조는 이 slack 하나뿐**이다(나머지 database/discord/kakao_token/notion/openai/telegram 은 모두 유효).
 · 자격증명 해석은 등록된 provider 만 본다(backend/discord_bot.py:74, telegram_bot.py:41, db_query_runtime.py:9 의 parse_reference 패턴) — slack 은 해석기가 존재하지 않는다.
- **사용자가 겪는 장면**: 이 생성기로 만든 합성 데이터로 생성 모델을 미세조정하거나 few-shot 예시로 쓰면, 모델이 slackNode 에 존재하지 않는 token 필드와 {{API_CENTER:slack}} 를 채운 그래프를 내놓는다. 정의에 없는 키는 검증이 통과시키므로(unknown key 검사는 없다) 사용자에게는 정상 흐름으로 보이지만, 에디터에서 그 노드를 펼치면 채널·메시지 두 칸만 있어 방금 채워진 token 이 화면에서 사라지고, 사용자가 API 센터에서 'slack' 을 찾아 등록하려 해도 항목이 없다.
- **수정안**: generate_synthetic.py 의 slackNode data 에서 token 을 지워 정의된 필드(channel, message)만 쓰게 한다. 근본 해결은 위 slackNode 발견과 한 묶음이다 — slack provider 와 token 필드를 실제로 도입하든 노드를 내리든, 정의를 정한 뒤 학습 데이터를 그에 맞춘다. 재발 방지: 저장소 전체의 `{{API_CENTER:<id>}}` 리터럴이 credential_providers.json 의 id 집합에 속하는지, 그리고 합성 데이터의 노드 data 키가 정의된 필드명에 속하는지 검사하는 테스트를 추가(이 검사를 지금 돌리면 정확히 이 2줄만 걸린다).
