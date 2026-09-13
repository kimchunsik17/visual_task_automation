# 완료 작업 기록 — 2026-08-30 ~ 2026-09-06

## 문서 정보

| 항목 | 내용 |
| --- | --- |
| 상태 | 기록 문서. 새 작업을 여기에 쓰지 않는다 |
| 분리일 | 2026-09-06 |
| 출처 | `ROADMAP.md` v2.3(2026-08-30) 에서 잘라 온 완료분 + 로드맵 번호 밖에서 진행된 08-31~09-06 작업 |
| 이전 기록 | `COMPLETED_WORK_2026-08.md` (백로그 1~10·12·15~25, TEAM-0·1) |
| 현재 로드맵 | `../ROADMAP.md` v3.0 |

2026-08-30 부터 09-06 까지 끝난 것의 기록이다. 앞부분은 요약 표, 뒷부분은 로드맵 v2.3 에서
**원문 그대로** 옮겨 온 설계 근거와 구현 기록이다. 왜 그렇게 만들었는지 다시 볼 때만 열면 된다.

이 기간의 작업 대부분은 로드맵 번호 밖에서 일어났다 — 트러블슈팅(감사 → 재검증 → 0~5단계),
문서 포맷 스튜디오, 데이터 흐름 분리, 시연회 준비. 각각 `plans/` 에 정본 계획서가 있고 거기에
구현 기록이 남아 있으므로, 여기서는 **어디에 무엇이 있는지**와 완료 조건이 무엇이었는지만 적는다.

## 완료 요약

| 항목 | 완료일 | PR | ADR | 마이그레이션 | 기록 위치 |
| --- | --- | --- | --- | --- | --- |
| 백로그 29 한국형 서비스 노드 Phase 0 이전 ~ Phase 3 | 2026-08-30 | (누적 커밋 `0564e5f`) | ADR-0007 계약 위 | 0016(OAuth callback)·0017(cursor) | 아래 §v2.3-3.4, `plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md` §8 |
| 백로그 12 실질 완성 — 커뮤니티 템플릿 242종 게시(공개 163·검토 대기 79) | 2026-08-30 | 같은 커밋 | ADR-0023 개정(`publish_curated` 예외) | 0018 | 아래 §v2.3-1.2, `UNIMPLEMENTED_BACKLOG.md` §1.4 |
| 결함 10건 — 템플릿 재생성 덮어쓰기·webCrawler SSRF·HWPX mimetype·python-hwpx 고정·`.hwp` 참조·RSS 겹침 창·NodeType 하드코딩·시작 노드 판정·max_items 유실·`--accent-color` | 2026-08-30 | 같은 커밋 | — | — | 아래 §v2.3-1.1 |
| 백로그 28 POINT-0·1 구현 — 계약·resolver·범위 검증기·에디터 UI (**UI 는 꺼 둠**) | 2026-08-30 | 같은 커밋 | — | — | 아래 §v2.3-3.3 |
| 백로그 11 TEAM-0·1 (권한 판정 한 곳·Workspace·멤버·초대·감사) | 2026-08-29 | 같은 커밋 | ADR-0024 | 0015 | 아래 §v2.3-3.1 (08 기록의 상세) |
| 파이프라인 채널 분리 — 지시문/데이터 경계, 노드 메타 사이드 채널 | 2026-08-31 | 같은 커밋 | ADR-0025 | — | `ADR.md` |
| 필드 데이터 바인딩 Phase 0~3 + 안정화 1차 | 2026-08-31 | 같은 커밋 | ADR-0026 | — | `plans/DATA_FLOW_SEPARATION_PLAN.md` |
| 문서 포맷 스튜디오 Phase 0~3 (FormatSpec·formatNode·스튜디오 모달·AI 생성·구노드 대체) | 2026-08-31 | 같은 커밋 | — | 0021(document_formats) | `plans/DOCUMENT_FORMAT_STUDIO_PLAN.md` §7 |
| 문서 포맷 Phase 4·5 — 파일→포맷 역변환, 프리셋 21종, `/formats` 탭, 디자인 캔버스 편집기, 풀페이지 3-pane 스튜디오(앱 빌더 셸 재사용) | 2026-09-02~03 | #44 #45 #47 #48 #49 #50 #51 #52 #53 #54 | — | — | 같은 문서 §5 |
| 트러블슈팅 — 감사(7/12축) → 실행 계획(12축) → 실측 재검증(~110건) → 0~5단계 완료. **보안 8건**(runs IDOR fail-open·공개 실행결과 노출·SSRF url_guard·검증오류 되비침·JWT 기본값·artifact 가로채기·공개 스냅샷 유출·uploads 교차 읽기) + 배포 레일(deploy.sh/rollback.sh/health/ready/AUTO_MIGRATE_ON_BOOT) + 서버 스크립트 01~06 적용 + ErrorBoundary·alert type + 로컬 개발 환경 | 2026-08-31 ~ 09-02 | #25~#37, #43 | — | 0022(templates.slug unique) | `plans/TROUBLESHOOTING_*.md` 3종, `scripts/server/README.md` |
| log_step 을 안 부르던 제어노드 6종 배선 + 코드젠 스모크 단정 51종 | 2026-09-02 | #38 | — | — | PR 본문 |
| mergeNode 재합류 중복 방출 제거 — 모든 갈래 도착 후 1회 방출(재합류 게이트 + 분기 경로 스택) | 2026-09-02 | #40 | — | — | `backend/test_merge_rejoin.py` |
| 업로드·생성 파일을 소유자 디렉토리(`uploads/u<owner>/`)로 물리 분리 — 공개 계약 불변, 레거시 폴백, 이관 스크립트 07 | 2026-09-02 | #41 #42 | — | 0023(uploads (owner, stored_name) unique) | `scripts/server/07-uploads-per-user-move.sh` |
| 병렬 분기 형제 오염 — 둘째 갈래 입력이 첫 갈래 출력으로 덮이던 결함 | 2026-09-04 | #69 | — | — | PR 본문 |
| 시연 플래그 5종(전부 opt-in, 변수 제거 = 원상 복구): `HIDDEN_NODE_TYPES`(노드 비가시화 3표면) · `DEMO_SHARED_CREDENTIALS_*`(부스 계정 키 대여·전량 기록) · `DEMO_LOGIN_CODE/SEATS`(좌석별 데모 계정) · `DEMO_UI`(API 센터 등 표면 숨김) · `DEMO_GUEST/_TOKENS/_MAX`(게스트 자동 입장·토큰 상한) | 2026-09-03~04 | #55 #57 #59 #62 #70 (+#79 갤러리 필터 500 수정) | — | — | `plans/노드_비가시화_시연플래그_계획.md` |
| 시연 콘텐츠 — v1 한국 연동 5종+앱 2종(#56) → 분기·병합 구조(#58) → 도로명주소 제외·공공데이터 중심(#61) → **v2 생활 밀착 5종**(핫딜·EBS·입사지원서·여행 일정·안내 포스터, #68) → 실물 실행 결함 4건(#74) → 이메일 전달·Word(#82) → WF1 키워드→핫딜 재설계(#88) + 어미새 병렬 출처(#92) | 2026-09-03~06 | 위 번호 | — | — | `backend/seed_demo_booth.py` 머리말 |
| 공개 실행 입력 상한(키 50·값 8,000자·총 32,000자, 실행 전 422) — 시연 체크리스트 7번 | 2026-09-03 | #60 | — | — | PR 본문 |
| 노드 이름 한글 통일 — 수신/감지/발송 스킴, 카카오 알림톡 오칭 교정, 후속 전수 동기화 | 2026-09-04 | #63 #64 | — | — | PR 본문 |
| 목록 화면 출렁임 제거(stale-while-revalidate 캐시·플래그 localStorage 보존·사이드바 재마운트) | 2026-09-04 | #65 #66 #67 | — | — | `frontend/src/listCache.js`, `features.js` |
| 빌드 중 reload 시 정적 마운트 경쟁으로 서버가 죽던 것 | 2026-09-04 | #71 | — | — | PR 본문 |
| **PICKLE LLM 게이트웨이 전환**(llm.pcl.kr, OpenAI 호환·OpenRouter 모델 id, 허용 17필드 엄격 모드) + 실측 확인 + 이미지 생성 지원 요청서 | 2026-09-05 | #72 #73 #75 | — | — | `PICKLE_LLM_GATEWAY.md` |
| 시연 LLM 노드 gpt-5.4-mini, 드롭다운 `gpt-5.6`→`gpt-5.6-terra`(게이트웨이에 없는 모델 제거) | 2026-09-05 | #80 | — | — | PR 본문 |
| 시연 결과 이메일 전달 — `{{USER_EMAIL}}` 수신자 해석, 게스트 최초 1회 이메일·이름 등록, 저장 전 그래프 실행도 실행 사용자를 소유자로 | 2026-09-06 | #82 #91 | — | — | `backend/delivery_runtime.py` |
| 부스 점검 결함 — 다운로드 경로 추출 통일(공백 파일명·첨부 안내), 커스텀 앱 결과 내려받기 버튼·패널 겹침, 온보딩 z-index, 인트로 마퀴 2건, 워크플로우 상한에서 시연 콘텐츠 제외(`MAX_MANUAL_WORKFLOWS`), 조건 분기·분배기·멀티 에이전트 노드 UI 리프레시, Google OAuth 앱 안내(웹 애플리케이션 유형) | 2026-09-05~06 | #76 #83 #84 #85 #86 #87 #89 #90 | — | — | PR 본문 |

### 완료했지만 결론이 "하지 않는다"인 것

- **`httpRequestNode` 에 URL 게이트를 걸지 않는다**(2026-08-30, 선택지 a) — 사설 IP 차단이 사내망·자체
  호스팅 연동을 깨는데 "임의 HTTP 요청"이 그 노드의 존재 이유다. 받아들인 노출과 재검토 조건은
  아래 §v2.3-7 과 `UNIMPLEMENTED_BACKLOG.md` §2.6 에 있다.
- **pythonNode 생성 차단(C2)은 하지 않는다**(2026-09-01, 재검증 2라운드) — `plans/TROUBLESHOOTING_REVERIFICATION.md` §6.3.
- **모델↔마이그레이션 드리프트 테스트는 좁게만 넣었다**(C3) — 같은 문서.
- **`transformNode`·adaptive fan-out 기본값 전환** — 08 기록 참조(그대로 유지).
- 트러블슈팅 실행 계획의 **"일부러 하지 않는 것" 11항**은 폐기가 아니라 조건부다. 승격 트리거는
  `ROADMAP.md` §3.6(37번) 으로 옮겼다.

### 완료했지만 서버·사용자 조치를 기다리는 것

| 항목 | 남은 조치 | 상태(2026-09-06) |
| --- | --- | --- |
| per-user uploads 물리 분리(#41) | 서버에서 `deploy.sh` 배포(0023) → `07-uploads-per-user-move.sh --dry-run` → `--apply` → 브라우저 왕복 | **미확인** — 서버 세션 기록 없음 |
| 도로명주소·공공데이터포털 승인키 실호출 대조 | 사용자 발급 | juso 는 시연 제외(`HIDDEN_NODE_TYPES=jusoNode`, 09-03). data_go_kr 은 시연 콘텐츠 v2 에서 빠져 **실호출 기록 없음** |
| 검토 대기 템플릿 79건 | 승인 주체 지정 → 승인 | **미결** |
| 익명 공유 앱 실행자의 생성 파일 다운로드(#43 알려진 한계) | share_token 스코프 다운로드 라우트 | **미착수** → `ROADMAP.md` 33번 APP-2 에 편입 |
| 요구사항 파일 결정(`requirements_linux.txt` 누락 4개) | 서버 배포 절차 결정 | `scripts/server/README.md` 가 `requirements.txt` 로 통일했다고 적음 — **폐기로 종결** |

---

## 로드맵 v2.3 에서 옮겨 온 기록 (원문)

아래는 `ROADMAP.md` v2.3 의 해당 절을 **글자 그대로** 옮긴 것이다. 절 번호는 v2.3 기준이다.

## v2.3-1.1 지금 새고 있는 것 — 2026-08-30 전부 처리

`plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md` 검토와 그 뒤 작업에서 나온, **어느 트랙에도 속하지
않지만 지금 사용자에게 영향이 있는** 결함이었다.

| 결함 | 영향 | 상태 |
| --- | --- | --- |
| 템플릿 자동 재생성이 사용자 업로드 원본을 덮어씀 | 되돌릴 수 없는 파일 손실 | **해결** — 덮어쓰지 않고 실패시킨다 |
| `webCrawlerNode`가 URL 검증 없이 요청 | SSRF. 커뮤니티 수집 정책도 무력화 | **해결** — `backend/url_guard.py` |
| HWPX 재압축이 `mimetype` STORED 규칙을 깸 | 엄격한 reader에서 파일이 열리지 않음 | **해결** — 원본 `ZipInfo` 보존 |
| `python-hwpx` 버전 미고정 | 라이브러리 변경 시 조용한 회귀 | **해결** — `==3.4.1` |
| 큐레이션 템플릿의 `.hwp` 참조 | 지원하지 않는 확장자로 실행 실패 | **해결** — `.hwpx` |
| `rssTriggerNode` cursor에 겹침 창 없음 | 피드에서 밀려났다 돌아온 항목 재통지 | **해결** — 아래 세 건과 함께 |

**이어서 발견한 네 건**(전부 2026-08-30 해결). 앞의 여섯과 달리 **계획 문서 어디에도 없던 것**이고,
새 노드로 템플릿을 실제로 만들어 보다가 드러났다.

| 결함 | 영향 |
| --- | --- |
| `meta_agent.NodeType`이 하드코딩이라 한국형 노드 5종이 빠짐 | 카탈로그는 LLM에게 49종을 알리는데 출력 스키마는 45종만 받았다 — 그 노드를 쓴 그래프는 **생성·dry-run·커뮤니티 게시가 전부 깨졌다** |
| 시작 노드 판정도 하드코딩 | RSS·YouTube·Gmail·네이버 **트리거 4종으로 시작하는 그래프가 전부** "시작 노드 0개"로 거부됐다 |
| `rssTriggerNode`가 `max_items`로 잘라낸 항목을 통지 없이 seen 처리 | 새 글 50개 중 40개가 조용히 사라진다 |
| `--accent-color` 미정의 | API Center 버튼이 라이트 모드에서 보이지 않았다 |

**앞의 두 건이 같은 모양이다** — 정의에서 파생시킬 수 있는 목록을 손으로 적어 둔 것. 둘 다
`node_definition`에서 파생시키고 대조 테스트로 묶었다. **단위 테스트는 넷 다 통과하고 있었다** —
새 노드로 그래프를 만들어 `dry_run_workflow`까지 돌려 보고서야 드러났다.

회귀 테스트는 `backend/test_url_guard.py`·`test_url_guard_politeness.py`·`test_template_safety.py`·
`test_web_extract.py`·`test_connector_cursor.py`·`test_node_definitions.py`에 있다.


## v2.3-1.2 2026-08-30에 닫힌 것

**백로그 29번(한국형 서비스 노드) — Phase 0~3 구현 완료.**

| Phase | 결과 |
| --- | --- |
| Phase 0 이전 | 위 결함 5건 |
| Phase 0 | 공통 OAuth 인가 코드 callback(`connectors/oauth_flow.py`, 마이그레이션 0016), cursor 저장소(0017), 연동 계약(mock·`docsUrl`·`termsGate`) |
| Phase 1 | HWPX 공용 엔진과 `hwpxDocumentNode` — golden 10종을 한/글에서 검증 |
| Phase 2 | `naverSearchNode`·`naverSearchTriggerNode`·`naverCafeNode` |
| Phase 3 | `jusoNode`(도로명주소), `dataGoKrNode`(공공데이터포털), `webCrawlerNode` 정비 |

**남은 것은 승인키로 하는 실호출 대조뿐이다** — 도로명주소·공공데이터포털 둘 다 문서 기준으로
만들고 mock으로 검증했다. 나머지 Phase(X·Instagram, 커뮤니티 preset, 네이버 커머스, NAVER WORKS,
OpenDART, 카카오 로컬, KOSIS)는 **비용·자격·수요를 이유로 보류**했고 재개 조건은 계획 문서 §8
보류표에 있다.

**커뮤니티 템플릿 242종 게시(백로그 12번의 실질 완성).** 갤러리가 0개였다. 기존 142개(n8n 템플릿
로직을 옮긴 것, 그동안 LLM 생성용 벡터 스토어로만 갔다)를 현재 생태계로 재검증해 전량 통과시키고,
그때 없던 노드를 쓰는 **신규 100개**를 만들어 함께 올렸다. 바로 공개 163, 검토 대기 79.

이 과정에서 ADR-0023의 게시 게이트에 **예외를 하나 만들었다** — 운영자 제작 템플릿은
"본인 계정 실행 성공" 요건을 면제한다(`publish_curated`). 나머지 네 게이트는 그대로다.
면제 사실은 `templates.is_curated`·`publish_gate.curated`·갤러리 "공식" 배지 세 곳에 남는다.


## v2.3-3.1 Workspace/RBAC — TEAM-0·1 구현 진행 상황 (2026-08-29)

TEAM-0과 TEAM-1을 구현했다(ADR-0024, 마이그레이션 0015). **TEAM-2·3은 남았다.**

- **TEAM-0 권한 판정 모으기** — `project_access.can(db, user, project, action)`. 착수 전 센 결과
  `user_id != user.id` 검사가 **42곳**에 흩어져 있었다. 판정 순서는 만든 사람 → workspace 역할 →
  공개 범위(**조회만**)다. 자격증명 주체(`credential_owner_for`)도 이 모듈이 정한다.
- **TEAM-1 Workspace·멤버·초대·감사** — 역할 5종의 권한 표가 코드와 테스트로 고정됐다. 초대는
  핸들 기반이고 §4.16의 알림함을 쓴다. 마지막 owner는 나갈 수도 강등될 수도 없다.
- **점진 이전이 안전한 이유**: 아직 옮기지 않은 엔드포인트는 `user_id`를 보는데 그건 workspace
  멤버십보다 **더 엄격하다** — 실패 방식이 "팀원이 아직 못 한다"이지 "남이 볼 수 있다"가 아니다.
  42곳 중 핵심 5곳(조회·편집·삭제·실행 자격증명·목록)을 옮겼다.
- **남은 것**: TEAM-2(workspace 전용 자격증명 저장소 — 지금은 workspace owner의 개인 자격증명을
  쓴다), TEAM-3(workspace 화면 — API만 있다), 그리고 나머지 37곳의 판정 이전.


## v2.3-3.3 AI 시맨틱 포인팅 — POINT-0·1 구현 기록

##### POINT-0. 계약·resolver·관측 기반 — **2026-08-30 완료**

구현은 `backend/pointing.py`(+ `test_pointing.py` 52건)에 있다. 원래 계획한 네 가지를 그대로 했다.

| | 결과 |
| --- | --- |
| 계약 | `PointingContext v1`, `PointingTarget`, scope 4종, 오류 code 6종(`error_catalog.json` 등록) |
| resolver | `workflow_node`·`workflow_edge`·`app_component`·`app_logic_node`. 컴포넌트는 `children` 중첩까지 훑는다 |
| scope validator | `validate_scope()` — 전후를 직접 비교해 범위 밖이 하나라도 바뀌면 **요청 전체 거부** |
| 관측 | `telemetry()` — 종류·수·scope·위반 수만. **label·본문은 남기지 않는다** |

`/api/chat`에 optional `pointing_context`를 붙였다. 없으면 예전과 똑같이 동작한다.

**구현하며 정한 것 넷.**

- **`whole_canvas`는 빈 집합이 아니라 `None`을 돌려준다.** 빈 집합("아무것도 못 바꾼다")과
  구분되지 않으면 위험한 쪽으로 잘못 읽힌다.
- **조회 권한과 편집 권한을 따로 본다.** `reference_only`는 조회면 충분하고 나머지는 편집이
  필요하다 — 묶으면 viewer가 "이 노드 고쳐줘"로 편집하게 된다. 공개 프로젝트도 편집은 막는다.
- **모르는 `version`을 "포인팅 없음"으로 강등하지 않는다.** 지목했는데 전체 캔버스가 편집
  대상이 되는 것이 가장 나쁘다.
- **`redact()`를 `community_sanitize`와 공유하지 않는다.** 저쪽은 "남에게 보여도 되는가",
  이쪽은 "모델 프롬프트에 넣어도 되는가"로 판단 기준이 다르다.

**아직 안 한 것 — POINT-1의 몫이다.** 프롬프트에 넣을 문맥을 줄이는 것(`build_prompt_context()`는
만들었지만 `run_agent_turn`이 아직 전체 그래프를 받는다)과 UI(첨부·칩·scope selector)다.
지금은 전체 상태를 모델에 주고 **결과만 검증**한다 — 계획의 POINT-0 3번 항목 그대로다.

<details>
<summary>원래 계획 (기록)</summary>

1. `PointingContext v1`, `PointingTarget`, scope와 공통 오류 code를 정의한다.
2. `workflow_node`/`workflow_edge`/`app_component`/`app_logic_node` resolver, 권한·revision·hash 검사,
   secret redaction을 구현한다.
3. 기존 전체-state 모델 응답에 post-diff scope validator를 붙인다. 범위 밖 변경은 일부 적용하지 않고
   요청 전체를 거부한다(atomic).
4. 대상 종류·개수·scope·prompt token·범위 위반·stale 비율을 기록한다. target label/본문/문서 내용은
   telemetry에 남기지 않는다.

</details>

##### POINT-1. Workflow Editor vertical slice — **2026-08-30 구현 완료, UI는 꺼 둠**

> **2026-08-30 결정: 기능을 껐다**(`EditorPage.jsx`의 `POINTING_ENABLED = false`).
> 계약·resolver·검증기(`backend/pointing.py`)와 UI 코드는 그대로 두고 진입점만 막았다 —
> 다시 열 때 상수 하나만 바꾸면 된다.
>
> **왜 껐나.** 범위 검증은 의도대로 동작했지만, **그 범위 안에서 모델이 하는 일을 통제할 수
> 없었다.** "이 LLM 노드를 정적 노드로 바꿔줘" 에 대해 지시문이 `update_node(node_type=...)`
> 를 쓰라고 명시했는데도 모델이 `delete_node` + `add_node` 를 썼고, 그 결과 **연결선이 전부
> 사라졌다.** 삭제된 엣지가 `연결 항목 포함` 범위에서는 허용 대상이라 오류도 나지 않았다.
>
> 즉 검증기는 "범위 밖을 건드렸는가" 는 잡지만 "범위 안에서 파괴적으로 했는가" 는 못 잡는다.
> 그걸 잡으려면 도구 단위 제약이 필요한데(예: 포인팅 요청에서는 `delete_node` 를 아예 빼기),
> 그건 POINT-1의 범위를 넘는다.
>
> **다시 열려면 필요한 것:** 포인팅 요청에서 파괴적 도구를 제외하거나, diff preview 를 먼저
> 만들어 사용자가 적용 전에 확인하게 하는 것. 후자가 계획의 POINT-1 4번 항목이다.

##### POINT-1 구현 내역 (참고)

| | 결과 |
| --- | --- |
| 첨부 UI | 선택 툴바의 "AI에 첨부" 버튼. **선택만으로 자동 첨부하지 않는다** |
| 대상 핸들 | **입력란 안**의 `@` 토큰(메일 To: 칸 방식). 클릭 또는 빈 입력에서 Backspace로 해제. 삭제된 대상은 취소선으로 남기고 다른 id에 재연결하지 않는다 |
| scope selector | 선택 항목만(기본) / 연결 항목 포함 / 전체 캔버스. 전체 캔버스는 경고 문구를 함께 띄운다 |
| 허용 집합 | `editable_ids()`가 결정론적으로 계산. 이웃은 1-hop, 방향을 가리지 않는다 |
| 모델 지시 | `instruction_block()`이 대상 id·type과 수정 가능한 id를 열거하고, 범위를 넘으면 거부된다고 예고한다 |
| 오류 처리 | 포인팅 실패는 일반 오류로 뭉뜽그리지 않는다. `POINTING_TARGET_NOT_FOUND`면 없어진 칩만 걷어낸다 |

**계획과 달라진 것 하나 — "프롬프트에 subgraph만"은 이 구조에 해당하지 않았다.**
계획은 전체 그래프가 프롬프트에 들어간다고 보고 토큰 절감을 노렸는데, 실제로는 그래프가
시스템 프롬프트가 아니라 **tools를 통해** 모델에 간다(`make_tools(graph_data, ...)`).
프롬프트를 줄여도 토큰이 줄지 않는다. 그래서 POINT-1은 토큰이 아니라 **지시의 명확성**에
집중했다 — 무엇을 고쳐야 하고 무엇을 건드리면 안 되는지를 요청 맨 앞에 놓는다.
토큰 절감이 실제로 필요하면 tools 응답을 좁히는 별도 작업이 된다.

**클라이언트와 서버가 같은 해시를 쓴다.** 다르면 멀쩡한 대상이 전부 stale로 튕겨 기능이
통째로 죽는다 — **실제로 그렇게 나갔다가 고쳤다.** 처음에는 직렬화 방식만 맞추고 *무엇을*
해싱하는지를 안 맞췄다. 서버는 `graph_data`(= `createEditorSnapshot` 을 거친 값)를 보는데
클라이언트는 React Flow **원본** 노드를 해싱해서, 모든 대상이 예외 없이 튕겼다. 지금은 같은
출처(`getCurrentFlowData()`)에서 꺼내고, 테스트가 그 출처를 붙들고 있다.

**범위 검증은 표현이 아니라 의미를 본다**(2026-08-30 실사용에서 고침). 처음에는 항목을 통짜로
비교했는데, `auto_layout` 이 노드를 `{id,type,position,data}` 로 재구성하고 엣지를
`FlowEdge.model_dump()` 로 만들면서 `className`·`style`·`width` 가 사라진다. 그래서 AI 가
손대지 않은 항목까지 전부 "바뀌었다" 로 잡혀 **정상 요청이 매번 거부됐다.**

지금은 노드의 `type`·`data`, 엣지의 `source`·`target`·handle 만 비교한다. 자리·색·클래스는
편집 범위가 지키려는 대상이 아니다 — 범위가 지키는 것은 **워크플로우가 하는 일**이다.
느슨해진 만큼 진짜 변경을 놓치지 않는지 테스트가 양방향으로 확인한다.

**핸들은 입력란 안에 둔다**(2026-08-30 사용자 요청). 처음에는 Drawer 상단 칩이었는데 하나씩
지우기 불편했다. 코드 에디터식 인라인 `@`멘션(contenteditable)도 검토했지만 **이 저장소는
한글 IME 문제가 재발한 이력**이 있어 textarea를 유지하는 토큰 필드로 갔다. Backspace 분기와
Enter 분기 모두 조합 상태(`isComposing`)를 확인한다.

<details>
<summary>원래 계획 (기록)</summary>

1. 선택 노드/엣지의 "AI에 첨부", 대상 칩, scope selector를 공통 Drawer에 연결한다.
2. `target_only`와 `target_and_neighbors`의 허용 node/edge 집합을 결정론적으로 계산한다. 이웃은 1-hop으로
   제한하고 방향과 포함 개수를 UI에 보여준다.
3. `/api/chat`에 `pointing_context`를 전달하고 모델 prompt에는 선택 subgraph만 구성한다.
4. diff preview → 적용 → editor history/revision → 포커스/Inspector 이동까지 E2E로 검증한다.

</details>

**아직 안 한 것.** diff preview와 `ui_actions`(focus_target·open_inspector)는 안 만들었다.
지금은 기존 AI 변경 하이라이트 경로를 그대로 쓴다 — 적용 전 미리보기는 POINT-1의 4번 항목이라
남은 몫이다.


## v2.3-3.4 한국형 서비스 노드 — 백로그 29번 — Phase 0~3 완료

전체 설계는 `plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md`(v1.7)에 있다. 여기에는 로드맵 차원의
판단만 둔다.

**채택하되 서비스 이름을 늘리는 방식으로 하지 않는다.** §4의 공식 연동 노드 공통 계약을 그대로
따르고, 범용 `httpRequestNode`보다 인증·Trigger·상태·오류·mock 경험을 확실히 개선할 때만 추가한다.
이 원칙이 실제로 걸러 낸 예가 `dataGoKrNode`다 — 임의 URL 프록시로 만들면 `httpRequestNode`와
같아지므로, **등록된 데이터셋만 부르는 registry**로 만들었다.

| Phase | 내용 | 상태 |
| --- | --- | --- |
| Phase 0 이전 | 결함 5건 | 완료 |
| Phase 0 | OAuth callback, credential provider, cursor 저장소, 연동 계약 | 완료 |
| Phase 1 | HWPX 공용 엔진과 `hwpxDocumentNode` | 완료 — 한/글 검증까지 |
| Phase 2 | 네이버 검색·트리거·카페 | 완료 |
| Phase 3 | 도로명주소, 공공데이터포털, `webCrawlerNode` 정비 | 완료 — **승인키 실호출 대조만 남음** |
| 보류 | X·Instagram, 커뮤니티 preset, 네이버 커머스·NAVER WORKS·OpenDART, 카카오 로컬, KOSIS | 계획 문서 §8 보류표에 재개 조건 |

**로드맵에 미치는 영향 세 가지.**

1. **Phase 0의 OAuth callback·cursor 저장소·연동 계약을 26·27번이 그대로 쓴다** — 한 번만 만들었다.
2. **`connectors/cursor.py:select_new()`가 트리거 공통 정책의 정본이다.** 시작 모드
   (baseline/backfill/since)·겹침 창·알린 것만 기억하기가 여기 있다. 새 트리거는 이 함수를 쓴다 —
   예전에 `rss.py`와 `naver_search.py`가 같은 일을 각자 구현해서 한쪽 결함이 다른 쪽에 오래 남았다.
3. **커뮤니티 수집은 전용 노드가 아니라 `webCrawlerNode`로 한다.** 사이트마다 전용 노드를 만들면
   그 수만큼 약관을 따로 관리하게 된다. 지금은 robots.txt·호스트별 일일 상한(50회)·요청 간 최소
   간격이 걸려 있다. 디시인사이드·에펨코리아는 차단 목록 유지.

**보류 판단의 근거를 남긴다.** X·Instagram은 **API 비용** 때문이다(X 유료 등급, Instagram Business
인증·App Review). "나중에"로만 적으면 왜 멈췄는지 잊고 같은 조사를 다시 한다.


## v2.3-7 결정된 질문 (9·10번)

10. ~~네이버 카페 게시를 계속 계획에 둘 것인가?~~
    → **2026-08-30 확인: 둔다.** 카페는 HUB 이관 대상이 아니었을 뿐 개발자센터에 그대로 있다
    (문서 온전·종료 공지 0건·엔드포인트가 405로 응답 — 미등록 경로의 400과 구분된다).
    남은 것은 등록 화면에서 '카페'를 고를 수 있는지 눈으로 보는 것 하나다
    (`plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md` §4.0).

9. ~~`webCrawlerNode`를 URL 게이트로 살릴 것인가, 폐기할 것인가?~~
   → **2026-08-30 결정: 선택지 A(게이트).** `backend/url_guard.py`로 구현했다.

   ~~이어지는 질문 — 같은 게이트를 `httpRequestNode`에도 걸 것인가?~~
   → **2026-08-30 결정: (a) 그대로 둔다.** 사설 IP를 막으면 사내망·자체 호스팅 연동이 깨지는데,
   "임의 HTTP 요청"이 그 노드의 존재 이유다. (b) 노드 설정 예외와 (c) workspace allowlist는
   둘 다 **사설 IP 접근을 여는 권한**이라 누가 그 목록을 편집하는지부터 정해야 하고, 잘못 열면
   그 자체가 권한 상승 경로가 된다. 지금 규모에서 감당할 복잡도가 아니라고 봤다.

   **그래서 남는 것 — 받아들인 위험이다.**

   - `httpRequestNode`는 URL 검증이 없다. LLM이나 사용자가 만든 주소가 `169.254.169.254`
     (클라우드 메타데이터)나 내부 주소를 가리키면 그대로 요청이 나간다.
   - `url_guard.PARTNERSHIP_REQUIRED_HOSTS`(디시인사이드·에펨코리아)도 이 노드로는 우회된다.
   - `rssTriggerNode`는 scheme만 본다.

   다시 볼 조건: **자체 호스팅 연동이 실제로 쓰이는지 확인되면** (b)를 재검토한다 — 아무도
   안 쓰는 기능 때문에 SSRF를 열어 둘 이유는 없다.
