# archive

**끝난 것들이다. 읽기용이고, 새 작업을 여기에 쓰지 않는다.**

지우지 않고 남긴 이유는 하나다 — "왜 그때 그렇게 정했나"를 나중에 물을 일이 생긴다.
어느 것도 현재 계획이 아니므로, 여기 적힌 미해결 항목은 이미 `../ROADMAP.md` 로 옮겨 왔거나
의도적으로 하지 않기로 한 것이다.

## 로드맵 분리 (2026-08-30)

| 파일 | 내용 |
| --- | --- |
| [COMPLETED_WORK_2026-08.md](COMPLETED_WORK_2026-08.md) | 백로그 1~10·12·15~25번의 설계 근거와 구현 기록. 완료 요약 표가 맨 앞에 있다 |
| [LONG_TERM_PRODUCT_ROADMAP_v1.9.md](LONG_TERM_PRODUCT_ROADMAP_v1.9.md) | 분리 전 원본 4072줄. **수정하지 않는다** — `ADR.md` 의 §4.x 참조가 이 파일의 번호를 가리킨다 |

## 구현이 끝난 계획

| 파일 | 완료 |
| --- | --- |
| [HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN.md](HOME_SIDEBAR_INFORMATION_ARCHITECTURE_PLAN.md) | 2026-08-28 |
| [EDITOR_SHORTCUTS_AND_CONVENIENCE_RESEARCH.md](EDITOR_SHORTCUTS_AND_CONVENIENCE_RESEARCH.md) | Slice 1~5 완료. 그룹·sub-workflow 는 문서 안 이관 기록 참고 |
| [INTRO_PAGE_DESIGN_AUDIT.md](INTRO_PAGE_DESIGN_AUDIT.md) | Slice 1~4 완료, 뷰포트 검증 전 항목 통과 |

## [assets/](assets/) — 아이콘·래스터 작업 산출물

Tier 1~6 아이콘 세트 교체가 끝나면서 소진된 프롬프트·매니페스트·QA 도구다. 18개 파일이 있다.

- `icon-generation-prompts.md`, `icon-prompt-B1-B2.md` ~ `icon-prompt-B9.md`, `icon-template-emoji.md`,
  `icon-tier6-brand.md`, `icon-empty-states.md` — 생성 프롬프트
- `P0_RASTER_GENERATION_MANIFEST.md`, `P1_P2_RASTER_GENERATION_MANIFEST.md`,
  `ANIMATED_MILESTONE_ASSET_MANIFEST.md` — 만들어진 자산 목록
- `icon-qa.html`, `build-icon-qa.py`, `design-samples/` — QA 도구와 샘플

새 아이콘이 필요하면 여기 프롬프트를 베끼기 전에
[`../design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md`](../design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md)
의 기준을 먼저 본다 — 그건 아카이브가 아니라 현행 기준이다.
