# 미구현 계획 모음

| 항목 | 값 |
| --- | --- |
| 작성 | 2026-08-30 |
| 범위 | `Documents/` 아래 11개 문서에 흩어진 **계획은 있으나 구현되지 않은** 항목 |
| 목적 | "다음에 뭘 하지" 를 물을 때 문서 11개를 다시 열지 않게 한다 |

## 이 문서가 있는 이유

계획이 문서별로 흩어져 있어서 **미구현 항목의 전체 목록이 어디에도 없었다.** 로드맵은 백로그 번호
단위라 문서 안쪽의 개별 항목이 안 보이고, 개별 계획서는 자기 범위만 안다. 실제로 2026-08-30
작업 목록을 짤 때 `design/` 폴더 7개와 `plans/` 3개를 통째로 빠뜨렸다.

각 항목은 **지금 손댈 수 있는가**로 갈라 놓았다. 기준은 하나다 — 사람이 방향을 정해야 하면
아래쪽, 근거가 이미 문서에 있으면 위쪽이다.

> **문서의 '미구현' 을 그대로 믿지 않는다.** 처음 이 목록을 만들 때 계획 문서를 근거로 결함
> 6건을 적었는데, 코드로 확인해 보니 **4건은 이미 고쳐져 있었다.** 항목을 집어들 때는 코드를
> 먼저 본다. 확인한 것은 §1.1 처럼 결과를 적어 둔다.

## 1. 지시 없이 손댈 수 있는 것

근거와 판단 기준이 이미 문서에 적혀 있어서 그대로 구현하면 되는 것들이다.

### 1.1 결함 — 확인 결과

**2026-08-30 코드로 하나씩 확인했다. 6건 중 4건은 이미 고쳐져 있었고 문서만 낡아 있었다.**
계획 문서의 "미구현" 표시를 그대로 믿으면 안 된다는 뜻이라, 확인 결과를 남긴다.

| # | 내용 | 실제 상태 |
| --- | --- | --- |
| D1 | 에디터 연결선 색이 안 나온다(`!important` 가 인라인 style 을 이김) | **이미 해결.** `index.css:1792` 에 "!important 를 쓰지 않는다" 주석까지 있다. 죽은 빈 규칙 하나만 치웠다 |
| D2 | 노드 팔레트 정본이 둘(`Sidebar.jsx` / `editorNodeCatalog.js`) | **이미 해결.** `Sidebar.jsx` 가 `EDITOR_NODE_CATALOG` 하나만 읽는다 |
| D3 | 통계에서 `app_agent` 오분류 | **이미 해결.** `usage_tracking.usage_bucket` 이 `app_agent → app_builder` 로 넣는다 |
| D4 | 기간 필터가 추이 차트에만 걸림 | **이미 해결.** `build_statistics` 가 `period_logs` 하나에서 요약·비율·프로젝트별을 모두 만든다 |
| D5 | 390px 에서 가로 스크롤 | **구조는 고쳐졌으나 실측 못 함.** `1fr 310px` 고정 2열은 없어졌고 1100/768/380px 분기가 생겼다. 다만 **380px 분기가 390px 과 너무 가깝다** — 로그인이 필요해 실제 측정은 못 했다 |
| D6 | RSS 트리거 재통지 | **실제 결함이었다 → 2026-08-30 해결.** 아래 참조 |

**D6 은 두 가지가 겹쳐 있었다.**

- cursor 를 매번 현재 피드 id 로 통째로 교체해서, 밀려났다 돌아온 항목이 새 글로 잡혔다.
- `fresh[:max_items]` 로 잘라낸 항목까지 seen 에 넣어서, **통지되지 않은 채 영영 사라졌다.**
  피드에 새 글이 50개 올라오고 상한이 10이면 40개가 조용히 없어진다. 이건 문서에 없던 것이다.

`naverSearchTriggerNode` 와 같은 겹침 창(`SEEN_WINDOW = 300`)과 cursor 버전을 넣고, 통지한
것만 기억하도록 고쳤다. 잘려 나간 개수는 `pending` 으로 알린다. 회귀 테스트 8건.

### 1.2 작업 중 새로 찾은 결함 — 2026-08-30

**계획 문서 어디에도 없던 것들이다.** 새 노드로 템플릿을 만들다가 드러났다 — 만들어 보지 않으면
안 보이는 종류의 결함이라 여기 남긴다.

| # | 내용 | 영향 | 상태 |
| --- | --- | --- | --- |
| N1 | `meta_agent.NodeType` 이 하드코딩이라 한국형 노드 5종이 빠져 있었다 | **카탈로그는 LLM 에게 49종을 알리는데 출력 스키마는 45종만 받았다.** 그 5종을 쓴 그래프는 생성·dry-run·커뮤니티 게시가 전부 깨졌다 | 해결 + 카탈로그 대조 테스트 |
| N2 | `meta_agent` 의 시작 노드 판정이 하드코딩 5종이었다 | RSS·YouTube·Gmail·네이버 **트리거 4종으로 시작하는 그래프가 전부** "시작 노드는 정확히 1개여야 한다 (현재 0개)" 로 거부됐다 | 해결 — `dry_run` 처럼 정의에서 파생 |
| N3 | `rssTriggerNode` 가 `max_items` 로 잘라낸 항목을 통지 없이 seen 처리 | 새 글 50개 중 40개가 조용히 사라진다 | 해결(D6 과 함께) |

**셋 다 같은 모양이다** — "노드를 추가할 때 손으로 고쳐야 하는 목록" 이 여러 곳에 흩어져 있고,
하나를 빠뜨려도 아무도 알려주지 않는다. N1·N2 는 이제 테스트가 대조하지만, 남은 하드코딩
목록이 더 있는지는 확인하지 않았다.

### 1.3 템플릿 게시에서 막힌 것

| # | 내용 |
| --- | --- |
| T1 | **템플릿이 "설치자가 채울 일반 필드" 를 선언할 수 없다.** `community_sanitize.needs_input_for` 는 credential·secret·path 필드만 본다. 그래서 `naverCafeNode.clubId` 처럼 사용자마다 다른 **필수** 값은 템플릿에 담을 방법이 없다 — 비우면 구조 검사에서 막히고, 채우면 남의 카페를 가리킨다. 카페 게시 템플릿을 초안 생성까지로 줄인 이유다 |
| T2 | 게시 게이트는 **"본인 계정 실행 성공"** 을 요구한다. 승인키·자격증명이 있어야 만들 수 있어서 대신 만들어 둘 수 없다 |

### 1.4 커뮤니티 템플릿 242종 — 2026-08-30 완료

**갤러리에 템플릿이 0개였다.** 그것을 채우는 것이 이 작업이었다.

| | 내용 |
| --- | --- |
| 기존 142개 | `seed_curated_templates.py` 에 있던 것. GitHub n8n 템플릿 로직을 사람이 옮긴 것들인데 **벡터 스토어(LLM 생성 참고용)로만** 가고 갤러리에는 없었다 |
| 재검증 | 142/142 가 **현재** 생태계에서도 통과했다(노드 26종 추가, `url_guard`·NodeError·고위험 분류가 생긴 뒤) |
| 신규 100개 | `backend/official_templates/` — 142개를 만들 때는 **없던 노드**를 쓴다. 네이버·HWPX·도로명주소·Gmail·Drive·Sheets·Calendar·YouTube·RSS·노션·텔레그램 |
| 게시 | 242개 전량. 바로 공개 163, 검토 대기 79(`arbitrary_url` 등이 붙은 것) |

#### 게이트 3번에 예외를 하나 만들었다

일반 게시는 **"본인 계정에서 한 번 성공 실행"** 을 요구한다 — ADR-0023 이 "심사 인력 없이 얻는
가장 값싼 품질 신호" 라고 부르는 것이다. 242개는 Airtable·Outlook 같은 남의 서비스 자격증명이
있어야 실행되므로 이 요건을 채울 수 없었다.

`community_templates.publish_curated` 를 만들어 **그 한 가지만** 면제했다. 정화·구조 검사·
코드 노드·고위험 분류는 그대로 적용된다. 면제한 사실은 숨기지 않는다.

- `templates.is_curated` (마이그레이션 0018) — 행에 남는다
- 버전의 `publish_gate.curated`·`curatedReason`·`source`·`reviewedBy` — 무엇으로 대체했는지 남는다
- 갤러리 카드의 **"공식" 배지** — 사용자에게도 보인다

회귀 테스트 508건(`test_official_templates.py`)이 100개를 매번 게이트와 같은 검사로 돌린다.

#### 여기서 정한 것

- **받은 메일에 자동 회신하는 템플릿은 승인 노드를 반드시 거친다.** 반대로 정기 보고 메일에는
  승인을 걸지 않는다 — 금요일 저녁 보고서를 아무도 승인하지 않아 영영 안 나가는 자리다.
  대신 받는 사람을 비워 두어 설치한 사람이 채우게 한다.
- **카페 게시는 `confirm` 기본값이 거짓이다.** 템플릿을 설치하고 실행해도 글이 올라가지 않는다.
- **사용자마다 다른 필수 ID 가 필요한 노드는 템플릿에 넣지 않았다**(`youtubeNode.playlistId`,
  `naverCafeNode.clubId`). 비우면 검증에서 막히고 채우면 남의 것을 가리킨다 — T1 의 결과다.

### 1.5 남은 기능 범위

| # | 내용 | 근거 | 크기 |
| --- | --- | --- | ---: |
| ~~F1~~ | ~~`jusoNode` 도로명주소~~ — **2026-08-30 완료.** 승인키 실호출 대조만 남음(Q9) | [KOREAN…](plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md) §6.8, Phase 3 | S |
| ~~F2~~ | ~~`dataGoKrNode` 공공데이터포털~~ — **2026-08-30 완료.** 인증키 실호출 대조만 남음(Q9) | 같은 문서 | M |

**§1.5 는 이제 비었다.** 지시 없이 할 수 있는 항목은 전부 처리했다.

**F2 에서 알게 된 것.** 같은 포털인데 **API 마다 JSON 요청 파라미터 이름이 다르다** —
과기정통부 보도자료는 `returnType`, 기상청 단기예보는 `dataType` 이다(`_type` 을 쓰는 것도 있다).
이름을 틀리면 오류가 아니라 **XML 이 돌아와서** 파서가 조용히 빈 결과를 낸다. 그래서 형식
파라미터 이름을 데이터셋별로 적어 두고, 파서는 XML·JSON 을 모두 읽는다.

인증키에도 함정이 있다. 포털이 Encoding/Decoding 두 가지를 주는데 Encoding 쪽을 그대로 넘기면
HTTP 라이브러리가 한 번 더 인코딩해 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 가 난다 —
네이버 카페의 이중 인코딩과 같은 계열이고 방향만 반대다. 넘어온 키가 이미 인코딩됐으면
되돌린 뒤 보낸다.
| ~~F3~~ | ~~`cursor.py` 의 baseline/backfill/since 모드와 overlap window~~ — **2026-08-30 완료** | 같은 문서 §10 | M |
| ~~F4~~ | ~~API Center 만료·scope 상태 표시~~ — **2026-08-30 완료.** IP allowlist 는 모델에 없어 제외 | 같은 문서 §10 | S |
| ~~F5~~ | ~~연동의 `verifiedAt` 채우기~~ — **2026-08-30 완료.** `jusoNode` 만 제외(아래) | 같은 문서 §10 | S |

**F3 에서 드러난 것.** 시작 정책이 `rss.py` 와 `naver_search.py` 에 **따로 구현돼 있었다.**
그래서 한쪽에서 찾은 결함(겹침 창 없음)이 다른 쪽에는 이미 고쳐진 채로 오래 남아 있었다.
`connectors/cursor.py:select_new` 한 곳으로 올리고, 두 트리거가 같은 함수를 쓰는지 테스트가
확인한다. 시작 모드 셋을 붙였다 — `baseline`(기본, 첫 실행 무통지) / `backfill`(전부) /
`since`(정한 시각 이후).

**F4 는 만들 것이 거의 없었다.** 백엔드가 만료·자동갱신 준비·scope 를 이미 계산하는데
**화면이 그 값을 받아만 두고 쓰지 않고 있었다.** 토큰이 만료됐는지 실행해 봐야 알던 상태다.

**F5 에서 `jusoNode` 는 비워 뒀다.** `verifiedAt` 은 "공식 문서를 실제로 열어 대조한 날"인데
juso.go.kr 이 자동 요청에 403 을 준다. 확인 없이 날짜를 넣으면 이 필드가 막으려던 거짓말을
기록에 넣는 셈이다. 비어 있는 것이 조용히 늘지 않도록 `UNVERIFIED_ON_PURPOSE` 목록과 테스트를
뒀다. 나머지 7종은 공식 문서로 호스트·경로·파라미터·응답 필드를 하나씩 대조했다.

## 2. 지시가 필요한 것

**막혀서가 아니라, 정하는 사람이 따로 있어서** 남아 있는 것들이다. 무엇을 정해야 하는지를 함께 적었다.

### 2.1 제품 판단

| # | 내용 | 정해야 하는 것 |
| --- | --- | --- |
| Q2 | 통계에서 비용 부담자와 로그 사용자가 다른 문제 | 공유 App Runner 는 소유자 잔액을 쓰면서 실행자를 로그에 남긴다. 익명 실행이면 `user_id` 가 `NULL` 이라 소유자 통계에서 사라진다. **누구의 사용량으로 셀지** |
| Q3 | 미완성 노드 5종의 팔레트 노출 등급 | `fileModifierNode`·`templateAnalyzerNode`·`posterGeneratorNode` 를 beta 로 낮출지, 이름을 실제 기능에 맞게 바꿀지(포스터 생성기가 아니라 HTML 렌더러다) |

### 2.2 비용·자격이 선행

| # | 내용 | 선행 조건 |
| --- | --- | --- |
| Q4 | X·Instagram Social Pack | **API 비용.** X 는 유료 등급 선택, Instagram 은 Business 인증과 App Review |
| Q5 | 네이버 커머스·NAVER WORKS·OpenDART | 사업자·법인 자격 |
| Q6 | 로컬 LLM 운영 검증 3건 | RTX 5070 Ti 실기 벤치마크, 실제 동의·채택 데이터, 메인 PC 10→100% 단계 검증 |

### 2.3 사용자 기기·계정이 필요

| # | 내용 |
| --- | --- |
| Q7 | golden 03 표 페이지네이션을 한/글에서 재확인 |
| Q8 | 네이버 카페 실제 게시 검증 — 되돌릴 수 없어서 첫 게시는 사람이 한다 |
| Q9 | 도로명주소·공공데이터포털 승인키 발급 |

### 2.4 외형이 바뀌는 것

전부 "고칠 수 있지만 앱이 달라 보인다" 라 승인이 필요하다.

| # | 내용 | 근거 | 크기 |
| --- | --- | --- | ---: |
| Q10 | `--accent-color` 미정의 — API Center 버튼이 라이트 모드에서 안 보인다. `var(--primary-color)` 로 한 줄 고침 | 2026-08-30 발견 | S |
| Q11 | 메인 작업 공간·홈 채팅 리디자인 (백로그 30) | [MAIN_WORKSPACE…](design/MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md) | L |
| Q12 | 운영 Database Explorer·export·안전한 수정 (백로그 31) | [DATABASE_OPERATIONS…](plans/DATABASE_OPERATIONS_EXPLORER_PLAN.md) | L |
| Q13 | App Builder 디자인 개선 — 헤더 버튼 9개, 속성 40여 개 목록, 인라인 다크 색 51곳 | [APP_BUILDER…](design/APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md) | M |
| Q14 | Workflow Editor 시각 정리 — 실행 패널 인라인 style 120여 곳 | [WORKFLOW_EDITOR…](design/WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN.md) | M |
| Q15 | Intro 페이지 실험형 조립 캔버스 | [INTRO_PAGE…](design/INTRO_PAGE_EXPERIMENTAL_CANVAS_PLAN.md) | M |
| Q16 | GPT 래스터 이미지 P0 11장·P1 9장 | [GPT_RASTER…](design/GPT_RASTER_IMAGE_BACKLOG.md) | M |

### 2.5 착수 시점만 정하면 되는 큰 것

| # | 내용 | 근거 |
| --- | --- | --- |
| Q17 | Workspace/RBAC TEAM-2·3 (백로그 11) | [ROADMAP](ROADMAP.md) §3 |
| Q18 | 사용자 지식베이스와 `documentIndexNode`·`knowledgeSearchNode` (26) | 같은 문서 |
| Q19 | `webSearchNode` vertical slice (27) | 같은 문서 |
| Q20 | AI 시맨틱 포인팅 — **POINT-0·1 완료(2026-08-30)**. POINT-2(App Builder)와 diff preview 남음 (28) | 같은 문서 |

### 2.6 이미 결정된 것 — 기록으로 남긴다

| # | 결정 | 날짜 |
| --- | --- | --- |
| Q1 | **`httpRequestNode` 에 URL 게이트를 걸지 않는다**(선택지 a). 사설 IP 차단이 사내망·자체 호스팅 연동을 깨는데, "임의 HTTP 요청" 이 그 노드의 존재 이유다 | 2026-08-30 |

**남는 노출을 받아들인 결정이다.** `httpRequestNode` 는 URL 검증을 거치지 않으므로 (1) LLM·사용자가
만든 주소가 내부 주소나 클라우드 메타데이터를 가리켜도 요청이 나가고, (2)
`url_guard.PARTNERSHIP_REQUIRED_HOSTS`(디시인사이드·에펨코리아)도 이 경로로는 우회된다.

그래서 계획 §11 비목표의 "URL 게이트로 강제한다" 문장을 고쳤다 — 그 경로에 대해서는
**정책이지 강제가 아니다.** 문서에만 있는 약속을 강제라고 적어 두면 나중에 누군가 그것을
믿는다.

**다시 볼 조건:** 자체 호스팅 연동이 실제로 쓰이는지 확인되면 (b) 노드 설정 예외를 재검토한다.
아무도 안 쓰는 기능 때문에 SSRF 를 열어 둘 이유는 없다.

## 3. 원본 문서

이 표의 항목은 전부 아래에서 왔다. 상세는 원본을 본다.

| 문서 | 미구현 항목 |
| --- | --- |
| [ROADMAP.md](ROADMAP.md) | 백로그 11·26·27·28·30·31, 보류 13·14 |
| [plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md](plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md) | F1~F5, D6, Q1, Q4·Q5, Q7~Q9 |
| [plans/INCOMPLETE_NODE_STRUCTURE_REVIEW.md](plans/INCOMPLETE_NODE_STRUCTURE_REVIEW.md) | Q3 (P0 는 완료, P1~P3 미착수) |
| [plans/LLM_GENERATION_QUALITY_PLAN.md](plans/LLM_GENERATION_QUALITY_PLAN.md) | Q6 (69/72 완료) |
| [plans/DATABASE_OPERATIONS_EXPLORER_PLAN.md](plans/DATABASE_OPERATIONS_EXPLORER_PLAN.md) | Q12 |
| [design/STATISTICS_PAGE_AUDIT_AND_IMPROVEMENT_PLAN.md](design/STATISTICS_PAGE_AUDIT_AND_IMPROVEMENT_PLAN.md) | D3·D4·D5, Q2 |
| [design/WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN.md](design/WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN.md) | D1·D2, Q14 |
| [design/APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md](design/APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md) | Q13 |
| [design/MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md](design/MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md) | Q11 |
| [design/INTRO_PAGE_EXPERIMENTAL_CANVAS_PLAN.md](design/INTRO_PAGE_EXPERIMENTAL_CANVAS_PLAN.md) | Q15 |
| [design/GPT_RASTER_IMAGE_BACKLOG.md](design/GPT_RASTER_IMAGE_BACKLOG.md) | Q16 |
| [design/DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md](design/DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md) | Main Shell 판단은 Q11 이 대체 |
| [design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md](design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md) | 작업이 아니라 Q16 의 검수 기준 8항목 |

**여기 없는 것.** `ADR.md`·`archive/` 는 결정과 완료 기록이라 미구현 항목이 없다.
`ERROR_CATALOG.md` 는 생성물이다(`python backend/export_node_definitions.py`).
