# Documents

제품 문서의 지도다. 어디에 무엇이 있고 **무엇이 정본인지**만 적는다.

## 정본 문서 (루트)

| 문서 | 성격 | 언제 여는가 |
| --- | --- | --- |
| [ROADMAP.md](ROADMAP.md) | 남은 작업 | 다음에 무엇을 할지 정할 때. **완료분은 여기에 없다** |
| [UNIMPLEMENTED_BACKLOG.md](UNIMPLEMENTED_BACKLOG.md) | 미구현 항목 색인 | 11개 문서에 흩어진 미구현 항목을 한 번에 볼 때. **지시 필요 여부로 갈라 놓았다** |
| [ADR.md](ADR.md) | 결정 기록 | "왜 이렇게 만들었나"를 물을 때. ADR-0001~0024 |
| [PRD.md](PRD.md) | 제품 요구사항 | 제품의 범위와 대상을 확인할 때 |
| [TDD.md](TDD.md) | 기술 설계 | 시스템 구조를 확인할 때 |
| [기능정의서.md](기능정의서.md) | 기능 목록 | 무엇이 있는지 훑을 때 |
| [ERROR_CATALOG.md](ERROR_CATALOG.md) | **생성물** | 오류 code 를 찾을 때 |
| [LOCAL_LLM_RUNBOOK.md](LOCAL_LLM_RUNBOOK.md) | 운영 절차 | 로컬 LLM 을 띄울 때 |
| [PICKLE_LLM_GATEWAY.md](PICKLE_LLM_GATEWAY.md) | 운영 절차 | 지원처 LLM 게이트웨이(llm.pcl.kr) 설정·허용 필드·에러 대응을 볼 때 |

> **`ERROR_CATALOG.md` 를 직접 고치지 않는다.** 정본은 저장소 루트의 `error_catalog.json` 이고,
> 이 파일은 `python backend/export_node_definitions.py` 가 만든다. 경로도 그 스크립트에 박혀 있어
> 옮기면 깨진다.

## [plans/](plans/) — 진행 중인 작업 계획

| 문서 | 상태 |
| --- | --- |
| [KOREAN_SERVICE_NODE_EXPANSION_PLAN.md](plans/KOREAN_SERVICE_NODE_EXPANSION_PLAN.md) | Phase 0~2 완료. 남은 활성 범위는 공공데이터포털·도로명주소 (백로그 29번) |
| [DATABASE_OPERATIONS_EXPLORER_PLAN.md](plans/DATABASE_OPERATIONS_EXPLORER_PLAN.md) | 계획 완료, 미착수 (백로그 31번) |
| [INCOMPLETE_NODE_STRUCTURE_REVIEW.md](plans/INCOMPLETE_NODE_STRUCTURE_REVIEW.md) | P0 완료(ADR-0014·0015), P1 이후 미착수 |
| [LLM_GENERATION_QUALITY_PLAN.md](plans/LLM_GENERATION_QUALITY_PLAN.md) | 생성 품질·로컬 전환 계획 |
| [TROUBLESHOOTING_AUDIT_INTERIM.md](plans/TROUBLESHOOTING_AUDIT_INTERIM.md) | **중단됨** — 전반 감사 7/12축, 발견 55건(미검증). 재개 방법과 남은 축이 적혀 있다 |
| [TROUBLESHOOTING_EXECUTION_PLAN.md](plans/TROUBLESHOOTING_EXECUTION_PLAN.md) | **실행 계획** — 12축 감사 종합. P0 보안·0단계 상당수 완료. 여기서부터 이어간다 |
| [TROUBLESHOOTING_REVERIFICATION.md](plans/TROUBLESHOOTING_REVERIFICATION.md) | **실측 재검증(2026-09-01)** — 위 계획의 주장 약 110건을 코드와 대조했다. 개수 정정 5건·줄번호 표류 12곳·결정이 뒤집힌 항목 2개. **계획서보다 이걸 먼저 읽어라** |

## [design/](design/) — 디자인 계획과 기준

| 문서 | 범위 |
| --- | --- |
| [DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md](design/DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md) | 상위 문서. 아래 둘이 여기서 갈라진다 |
| [MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md](design/MAIN_WORKSPACE_AND_HOME_CHAT_REDESIGN_PLAN.md) | Main Shell, 작업물 Library, 홈 채팅 리디자인 (백로그 30번) |
| [WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN.md](design/WORKFLOW_EDITOR_DESIGN_IMPROVEMENT_PLAN.md) | 에디터 |
| [APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md](design/APP_BUILDER_DESIGN_IMPROVEMENT_PLAN.md) | App Builder |
| [STATISTICS_PAGE_AUDIT_AND_IMPROVEMENT_PLAN.md](design/STATISTICS_PAGE_AUDIT_AND_IMPROVEMENT_PLAN.md) | `/statistics` |
| [INTRO_PAGE_EXPERIMENTAL_CANVAS_PLAN.md](design/INTRO_PAGE_EXPERIMENTAL_CANVAS_PLAN.md) | 소개 페이지 실험 |
| [RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md](design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md) | 일러스트 아트 디렉션 기준 |
| [GPT_RASTER_IMAGE_BACKLOG.md](design/GPT_RASTER_IMAGE_BACKLOG.md) | 이미지 생성 모델을 쓸 자산 목록 |

## [archive/](archive/) — 끝난 것

읽기용이다. 새 작업을 여기에 쓰지 않는다. 자세한 것은 [archive/README.md](archive/README.md).

- [COMPLETED_WORK_2026-08.md](archive/COMPLETED_WORK_2026-08.md) — 백로그 1~10·12·15~25번의 설계 근거와 구현 기록
- [LONG_TERM_PRODUCT_ROADMAP_v1.9.md](archive/LONG_TERM_PRODUCT_ROADMAP_v1.9.md) — 분리 전 원본(4072줄)
- 구현이 끝난 계획 3건과 [assets/](archive/assets/) 의 아이콘·래스터 작업 산출물

## 작업 방식 (git)

**작업 단위마다 `main` 에서 짧은 브랜치를 새로 따고, 끝나면 PR 로 합치고 브랜치를 지운다.**
계획서의 한 Phase, 버그 하나, 안정화 항목 하나가 브랜치 하나다. `main` 에 직접 쌓거나
장기 브랜치에 계속 얹지 않는다.

2026-08-31 에 이 규칙을 세운 이유가 있다. 마지막 커밋이 08-24 였고 7일치(336파일)가
`private/admin-reports` 라는 장기 브랜치에 커밋되지 않은 채 쌓여 있었다. 결과가 셋이었다.

1. 되돌릴 지점이 없었다.
2. 같은 파일에 여러 날의 변경이 섞여 **기능 단위로 쪼갤 수 없었다** — 한 커밋에 690파일이 들어갔다.
3. 더 심각하게, **클린 클론으로는 빌드도 스키마 생성도 불가능한 상태였다.** 프론트가 import 하는
   webp 6개, 백엔드가 런타임에 경로로 읽는 포스터 PNG 12개, alembic 마이그레이션 0001~0021
   전체가 추적되지 않고 있었다. 로컬에 파일이 있어서 아무도 몰랐다.

### 커밋 전에 확인할 것

- **산출물·캐시·스크래치가 섞이지 않았는가** — `frontend/dist`, `frontend/dist.prev`, `.vite`,
  `__pycache__`, `backend/chroma_db`(재색인 산출물), `.codex-qa`, 루트의 임시 스크립트.
  특히 루트 `test_models.py` 처럼 `test_` 로 시작하는 스크래치는 저장소 루트에서 pytest 를 돌리면
  수집돼 실제 외부 API 를 호출한다.
- **반대로, 런타임·빌드에 필요한 파일이 빠지지 않았는가** — 소스가 `import` 하는 자산,
  백엔드가 경로로 직접 읽는 파일(`poster_generator.py` 의 포스터 배경 등), 마이그레이션.
  위 3번이 이쪽 실수였다. 확인 방법은 **커밋된 트리만으로 빌드해 보는 것**이다.
- **생성물이 정본과 어긋나지 않는가** — `python backend/export_node_definitions.py --check`.
  `node_definitions/`·`error_catalog.json`·`credential_providers.json` 등을 고쳐 놓고 파생물을
  다시 만들지 않으면, 프론트는 옛 정의로 화면을 그리는데 백엔드는 새 정의로 실행한다.
  `--check` 는 어긋나면 0 이 아닌 코드로 끝나므로 배포 스크립트의 첫 관문으로도 쓴다.
- **테스트를 돌렸는가** — 바꾼 영역의 백엔드 테스트를 파일 단위로(`pytest backend/test_X.py`).
  전체는 느리니 상시로 돌리지 않는다. 프론트는 러너가 아직 없다 — `frontend/src/*.test.js` 9개가
  `package.json` 에 스크립트가 없어 방치돼 있으므로, 그 파일들을 고쳤다면 손으로 확인해야 한다.
- 커밋 메시지는 한국어로 "무엇을 왜". 일부러 뺀 것이 있으면 그 이유까지 적는다.

## ⛔ 운영 비밀을 바꾸기 전에 — 되돌릴 수 없는 것

**`JWT_SECRET` 과 `CREDENTIAL_ENCRYPTION_KEY` 중 어느 쪽이든, 재암호화 없이 바꾸면
`user_api_keys` 에 저장된 자격증명이 영구히 복호화 불가가 된다.** 되돌릴 스크립트는 저장소에
없다. 잃는 것은 사용자들이 API 센터에 연결해 둔 OAuth refresh token·SMTP 비밀번호·봇 토큰이고,
사용자가 직접 다시 연결하는 것 말고는 복구 수단이 없다.

이유는 `backend/credential_crypto.py:19-33` 에 있다. 암호화 키 후보를 이 순서로 만든다:

```
CREDENTIAL_ENCRYPTION_KEY  →  JWT_SECRET      (둘 다 sha256 으로 키 유도)
```

그래서 **`CREDENTIAL_ENCRYPTION_KEY` 가 비어 있으면 `JWT_SECRET` 이 사실상 암호화 키다.**
계획서 초안이 `JWT_SECRET` 만 금지 대상으로 적었던 것은 이 폴백을 놓친 것이고, 두 값 모두가
대상이다.

한편 암호문에는 `enc:v1:{key_id}:` 로 어느 키로 잠갔는지가 박혀 있다(`:48`, `:56`, `:66-73`).
그래서 **두 값이 슬롯에 함께 남아 있는 동안에는** 옛 키로 잠긴 것과 새 키로 잠긴 것이 섞여
있어도 양쪽 다 읽힌다. 안전한 교체 순서는 여기서 나온다:

1. 새 `CREDENTIAL_ENCRYPTION_KEY` 를 **추가**한다(기존 값은 지우지 않는다).
2. 기존 자격증명을 새 키로 재암호화한다 — **이 스크립트를 먼저 만들어야 한다.**
3. 전부 옮겨진 것을 확인한 뒤에야 옛 값을 지운다.

이 절차를 밟기 전에는 두 변수 중 어느 것도 건드리지 않는다. 로컬 개발용 값은 서버와 무관하니
자유롭게 새로 만들어도 된다.

## 이 문서들을 고칠 때

- **새 작업**은 `ROADMAP.md` §2 백로그에 추가한다. 번호는 이어서 매긴다(현재 31번까지).
- **끝난 작업**은 `ROADMAP.md` 에서 지우고 `archive/COMPLETED_WORK_*.md` 에 완료일·ADR·마이그레이션과
  함께 남긴다. 로드맵이 다시 4000줄이 되지 않게 하는 유일한 방법이다.
- **결정**은 `ADR.md` 에 번호를 이어 붙인다. ADR 은 로드맵의 옛 §4.x 번호를 참조하므로
  `archive/LONG_TERM_PRODUCT_ROADMAP_v1.9.md` 를 가리킨다 — 그 파일은 수정하지 않는다.
