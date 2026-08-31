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

## 이 문서들을 고칠 때

- **새 작업**은 `ROADMAP.md` §2 백로그에 추가한다. 번호는 이어서 매긴다(현재 31번까지).
- **끝난 작업**은 `ROADMAP.md` 에서 지우고 `archive/COMPLETED_WORK_*.md` 에 완료일·ADR·마이그레이션과
  함께 남긴다. 로드맵이 다시 4000줄이 되지 않게 하는 유일한 방법이다.
- **결정**은 `ADR.md` 에 번호를 이어 붙인다. ADR 은 로드맵의 옛 §4.x 번호를 참조하므로
  `archive/LONG_TERM_PRODUCT_ROADMAP_v1.9.md` 를 가리킨다 — 그 파일은 수정하지 않는다.
