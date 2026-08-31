# P1·P2 래스터 생성 매니페스트

> 생성일: 2026-08-28  
> 생성 방식: Codex 내장 `imagegen`  
> 기준 문서: `Documents/design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md`

## 공통 생성 규칙

- 현대적인 IT 제품용 무광 2.5D 또는 종이 질감의 추상 일러스트를 사용한다.
- navy, cobalt, violet, emerald와 밝은 중립색을 제한적으로 사용한다.
- 실사 인물 대신 고정 캐릭터 노디를 사용하며, 외형은 `nodi-reference.png`를 따른다.
- 이미지 안에 텍스트, 숫자, 로고, 브랜드, 실제 UI, 기기 화면을 넣지 않는다.
- 한 장의 핵심 형태를 적게 유지하고, 유리·크롬·과도한 광택·생성형 장식 과밀을 피한다.
- 포스터 배경은 세로 3:4이며 중앙 또는 상단에 넓은 카피 안전 영역을 둔다.

## P1 결과 — 9개

| 분류 | 파일 | 생성 의도 |
| --- | --- | --- |
| 협업 | `collaboration/team-review.png` | 동일한 노디 3명이 편집·검토·승인 token으로 역할을 나눠 워크플로를 검수하는 장면 |
| 협업 | `collaboration/live-collaboration.png` | 동일한 노디 2명과 단순한 workflow tile로 실시간 공동 편집을 표현 |
| 리비전 | `revisions/revision-restore.png` | 이전 slate 흐름에서 컬러 흐름으로 복원되는 버전 회귀 개념 |
| 커넥터 | `connectors/video-publishing.png` | play tile과 outbound path로 영상 게시 연결을 추상화 |
| 커넥터 | `connectors/email-automation.png` | 텍스트 없는 envelope tile과 automation path로 이메일 자동화를 추상화 |
| 커넥터 | `connectors/cloud-files.png` | 폴더·파일 tile과 cloud path로 클라우드 파일 연결을 추상화 |
| 미디어 샘플 | `media-node-samples/ocr-korean-receipt.png` | OCR 검증에 사용할 한글 영수증 샘플 |
| 미디어 샘플 | `media-node-samples/vision-warehouse-anomaly.png` | 상자 6개 중 하나만 파손된 창고 비전 탐지 샘플 |
| 미디어 샘플 | `media-node-samples/imagegen-product-scene.png` | cobalt 제품 오브젝트, violet arch, emerald sphere로 구성한 이미지 생성 샘플 |

### P1 검수 기록

- 최초 이메일 커넥터 결과는 봉투 위에 의미 없는 가짜 문장선이 생성되어 제외했다.
- `email-automation.png`는 텍스트와 문장선이 없는 결과로 재생성했다.
- OCR 영수증만 기능 검증 목적상 의도적으로 한글과 숫자를 포함한다.

## P2 포스터 배경 팩 — 12개

| 파일 | 테마 | 권장 카피 배치 |
| --- | --- | --- |
| `poster-01-midnight-grid.png` | 외곽의 cobalt 시스템 트랙 | 상단·중앙 |
| `poster-02-cobalt-orbits.png` | 하단 양쪽의 굵은 orbital ring | 상단·중앙 |
| `poster-03-violet-arches.png` | 좌우를 감싸는 violet/cobalt arch | 중앙 |
| `poster-04-emerald-flow.png` | 하단의 emerald/cobalt ribbon | 상단 |
| `poster-05-layered-paper.png` | 하단의 navy/cobalt/violet paper wave | 상단 |
| `poster-06-dot-matrix.png` | 밝은 바탕의 우측·하단 dot matrix | 상단·좌측 |
| `poster-07-blueprint-lines.png` | 외곽을 따라 흐르는 blueprint track | 상단·우측 |
| `poster-08-diagonal-blocks.png` | 밝은 바탕 모서리의 diagonal block | 중앙 |
| `poster-09-emerald-wave.png` | 최하단의 단일 emerald wave | 상단·중앙 |
| `poster-10-neutral-editorial.png` | 밝은 바탕 하단의 세 가지 둥근 cutout | 상단 |
| `poster-11-concentric-frames.png` | 바깥쪽의 nested rounded frame | 중앙 |
| `poster-12-sparse-geometry.png` | 좌우 가장자리의 희소 기하 도형 | 중앙 |

포스터 파일은 모두 `1086 × 1448` PNG다. 배경 위의 제목, 본문, 날짜, CTA는 이미지 생성 단계가 아니라 `posterGeneratorNode`의 HTML/CSS 렌더러에서 합성한다.

### 적용 상태

- `posterGeneratorNode`에 `backgroundPreset` 선택 필드를 추가해 12개 배경을 즉시 사용할 수 있게 했다.
- 선택값은 생성 코드로 전달되고, 서버가 화이트리스트의 PNG만 data URI로 합성한다.
- `none`을 선택하거나 기존 프로젝트에 선택값이 없으면 기존 HTML 배경 렌더링을 그대로 유지한다.
- P1 이미지는 대응하는 협업·리비전·커넥터·미디어 노드의 전용 화면이 아직 없어 자산만 선반영했다.

## P2 랜딩 페이지 서사 장면 — 3개

| 파일 | 주제 | 카피 여백 | 적용 위치 |
| --- | --- | --- | --- |
| `landing-narrative/korean-work-automation.png` | 문서·일정·메시지가 승인 흐름으로 이어지는 국내 업무 자동화 | 좌측 | 소개 페이지 서사 카드 01 |
| `landing-narrative/ai-orchestration.png` | 입력이 분기·처리된 뒤 검증 단계로 모이는 AI 오케스트레이션 | 우측 | 소개 페이지 서사 카드 02 |
| `landing-narrative/operational-visibility.png` | 상태 node 하나를 골라 점검하는 운영 가시성 | 좌측 | 소개 페이지 서사 카드 03 |

- PNG 원본과 별도로 `1200 × 750` WebP 배포본을 만들었으며 랜딩 페이지는 WebP만 불러온다.
- 기존 `demo-1.webp`, `demo-2.webp`, `demo-3.webp` 제품 캡처는 교체하지 않았다.
- 실제 적용 코드: `frontend/src/pages/IntroPage.jsx`, `frontend/src/pages/IntroPage.css`

## P2 릴리스·커뮤니티 캠페인 베이스 — 2개

| 파일 | 규격 | 용도 |
| --- | --- | --- |
| `campaigns/release-og-feature-launch.png` | `1726 × 911`, 약 1.9:1 | 실제 릴리스명과 제품 캡처를 후합성하는 무문자 OG 베이스 |
| `campaigns/community-season-banner.png` | `2172 × 724`, 3:1 | 행사명과 CTA를 후합성하는 무문자 커뮤니티 시즌 배너 베이스 |

- 구체적인 릴리스·캠페인 문구가 아직 없으므로 두 파일은 재사용 가능한 베이스 자산으로 저장했다.
- 커뮤니티 배너 첫 결과는 violet token 안에 사람 모양 픽토그램이 생겨 제외했고, 기호 없는 단색 role token 버전으로 재생성했다.

## 저장 위치

- P1: `frontend/src/assets/editorial/collaboration/`, `revisions/`, `connectors/`, `media-node-samples/`
- P2: `frontend/src/assets/editorial/poster-backgrounds/`
- P2 랜딩: `frontend/src/assets/editorial/landing-narrative/`
- P2 캠페인: `frontend/src/assets/editorial/campaigns/`
- 캐릭터 기준표: `frontend/src/assets/editorial/character/nodi-reference.png`
- 캐릭터 구조화 설정: `frontend/src/assets/editorial/character/nodi.json`

## 재생성용 프롬프트 골격

```text
Input image 1 is a STYLE REFERENCE ONLY. Preserve the matte tactile finish,
restrained modern IT palette, rounded geometry, soft ambient shadows, and clean
editorial simplicity. Do not include recognizable objects from the reference.
No text, letters, numbers, logos, branding, UI, icons, people, screens, devices,
or mockups. Use a few large intentional forms, low visual noise, and preserve a
large calm copy-safe area. No glossy 3D look, stock-art look, or generative clutter.
```

각 재생성 시 위 골격 뒤에 표의 테마와 권장 카피 배치를 추가한다. 인물이 필요한 P1 장면은 캐릭터 바이블의 노디 외형과 협업 token 규칙을 함께 고정한다.
