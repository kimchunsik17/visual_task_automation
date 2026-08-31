# GPT 래스터 이미지 생성 백로그

> 작성일: 2026-08-28  
> 기준 문서: `../ROADMAP.md`, `DESIGN_SYSTEM_AUDIT_AND_MODERNIZATION_PLAN.md`, `../archive/assets/icon-empty-states.md`  
> 범위: Claude로 제작한 SVG 아이콘·선형 일러스트를 제외하고, 이미지 생성 모델을 쓸 이유가 분명한 PNG 원본 자산

## 1. 결론

현재 당장 필요한 것은 **아이콘을 PNG로 다시 만드는 일**이 아니다. SVG가 처리하기 어려운 아래 세 부류만 GPT 이미지 생성 대상으로 잡는 것이 좋다.

1. 사람·공간·실물·빛·재질이 함께 있는 에디토리얼 장면
2. 여러 서비스와 업무 맥락을 한 장면으로 설명하는 복합 시나리오 이미지
3. 향후 `OCR`, `Image Analysis`, `Image Generation` 노드의 데모와 테스트에 사용할 입력/출력 샘플

우선 제작 권장량은 **P0 11장, P1 9장**이다. P2는 기능 출시 시점에 맞춰 만든다. 아래 항목은 편의상 “GPT 전용”으로 부르지만, 다른 래스터 생성기도 이론상 만들 수 있다. 정확한 의미는 **현재 Claude SVG 제작 흐름으로 대체하기 어렵고 GPT 이미지 생성의 장점이 큰 자산**이다.

## 2. 우선순위 목록

### P0 — 가까운 제품 단계에 바로 쓰이는 11장

| ID | 이미지 | 수량 | 사용 위치 | 권장 원본 | GPT를 쓸 이유 | 로드맵 근거 |
| --- | --- | ---: | --- | --- | --- | --- |
| R01 | 커뮤니티 컬렉션 커버 | 6 | 템플릿 홈의 추천 컬렉션: 마케팅, CS, 문서, 데이터, 개발·운영, 개인 생산성 | 1600×900 PNG | 실제 업무 공간과 데이터 흐름을 결합한 에디토리얼 장면은 작은 SVG 아이콘보다 카테고리 구분력과 탐색 흥미가 높다 | 커뮤니티 템플릿의 카테고리·태그 도입 |
| R02 | Mock 시나리오 썸네일 | 3 | Mock 탭의 네이버 주문, 카카오 알림톡, 가상 결제 시나리오 선택 카드 | 1200×800 PNG | 택배 상자·스마트폰 알림·결제 단말 등 실물 맥락을 한눈에 설명할 수 있다 | Mock 탭의 시나리오 추천·재실행 |
| R03 | 온보딩 완료 축하 이미지 | 1 | 첫 mock 실행 또는 첫 워크플로 저장 완료 모달 | 1200×900 투명 PNG | 종이 조각, 빛, 부드러운 입체 재질 같은 축하 장면은 SVG보다 래스터가 자연스럽다 | 과업형 온보딩의 첫 성공 경험 |
| R04 | 안전한 자동화 에디토리얼 | 1 | 소개 페이지 또는 API Center의 credential 안내 상단 | 1600×1000 PNG | 자물쇠·승인·데이터 흐름을 차갑지 않은 신뢰 장면으로 묶는 데 유리하다 | credential reference, 권한, dry-run, audit 요구 |

#### R01 컬렉션별 모티프

| 파일명 제안 | 장면 |
| --- | --- |
| `collection-marketing.png` | 캠페인 보드, 콘텐츠 카드, 여러 채널로 퍼지는 데이터 |
| `collection-customer-support.png` | 상담 메시지, AI 분류, 사람의 승인, 답변 전송 |
| `collection-documents.png` | 문서 더미가 구조화된 데이터와 보고서로 변환되는 장면 |
| `collection-data-ops.png` | 데이터 소스, 검증 관문, 대시보드로 이어지는 파이프라인 |
| `collection-dev-ops.png` | 코드 변경, 테스트, 경고, 배포 승인으로 이어지는 운영 장면 |
| `collection-productivity.png` | 메일, 일정, 할 일, 요약 노트가 정돈되는 개인 업무 장면 |

개별 커뮤니티 템플릿마다 AI 커버를 생성하지 않는다. 개별 카드에는 실제 graph의 축소 렌더를 사용하고, GPT 이미지는 운영자가 만든 **컬렉션 커버**에만 쓴다. 그래야 템플릿 내용과 이미지가 어긋나지 않는다.

### P1 — 다음 기능 출시와 함께 필요한 9장

| ID | 이미지 | 수량 | 사용 위치 | 권장 원본 | GPT를 쓸 이유 | 로드맵 근거 |
| --- | --- | ---: | --- | --- | --- | --- |
| R05 | 팀 협업 소개 장면 | 2 | workspace 첫 진입, 팀 기능 소개 페이지 | 1600×1000 PNG | 여러 역할의 사람이 하나의 workflow를 검토·승인하는 복합 장면 표현 | workspace, RBAC, 댓글, 검토 요청, revision |
| R06 | 버전 복원/충돌 해결 장면 | 1 | revision 기능 소개 또는 릴리스 노트 | 1600×900 PNG | 갈라진 두 흐름이 안전한 하나의 버전으로 합쳐지는 서사적 표현 | revision, diff, 복원, 저장 충돌 |
| R07 | Connector vertical slice 장면 | 3 | YouTube·Gmail·Drive 추천 템플릿 컬렉션 상단 | 1600×900 PNG | 영상 제작 책상, 메일 triage, 파일 정리 등 서비스 사용 맥락을 풍부하게 표현 | 공식 연동 노드 Wave 1 |
| R08 | AI 미디어 노드 데모 세트 | 3 | OCR, Image Analysis, Image Generation 노드의 예제 선택기 | 아래 별도 사양 | 실제 이미지 입력이 기능의 일부이므로 아이콘으로 대체할 수 없다 | AI·미디어 노드 Wave 3 |

R08의 최소 세트:

- `ocr-receipt-clean.png`: 가상의 한국어 영수증. 실제 회사명·전화번호·카드번호는 쓰지 않는다.
- `vision-warehouse-anomaly.png`: 창고 선반에서 포장 손상 하나를 찾는 이미지 분석 예제.
- `imagegen-product-scene.png`: 가상의 무브랜드 제품을 광고 장면으로 변환하는 before/after용 결과 이미지.

OCR 테스트에서 글자 인식 정확도를 검증해야 하는 영수증 본문은 이미지 모델에 맡기지 말고 HTML/Canvas로 합성한다. GPT는 종이 질감·구김·조명·촬영 각도만 만든 뒤, 정확한 테스트 문자열을 코드로 올리는 방식이 적합하다.

### P2 — 출시/마케팅 필요가 생길 때 제작

| ID | 이미지 | 수량 | 사용 위치 | 권장 원본 | 비고 |
| --- | --- | ---: | --- | --- | --- |
| R09 | 랜딩 페이지 서사 장면 | 3 | 소개 페이지의 국내 업무 자동화, AI 오케스트레이션, 운영 가시성 섹션 | 1920×1200 PNG | 기존 `demo-1~3.webp` 제품 캡처를 대체하지 말고 그 사이의 감성/서사 구간에만 배치 |
| R10 | 포스터 생성용 배경 팩 | 12~20 | `posterGeneratorNode`의 선택형 배경 | 1800×2400 PNG | 텍스트 없는 추상 배경, 종이·유리·그레인 재질만 생성. 한글 제목과 레이아웃은 기존 HTML/CSS 렌더러가 담당 |
| R11 | 릴리스/OG 캠페인 아트 | 릴리스당 1 | Patch Notes, 블로그, 공유 카드 | 2400×1260 PNG | 큰 기능 출시 때만 생성. 제품 UI는 실제 캡처를 별도로 합성 |
| R12 | 커뮤니티 시즌 배너 | 캠페인당 1 | 템플릿 공모전, 신규 Connector 주간 | 2400×800 PNG | 상시 UI 자산이 아니라 운영 캠페인 자산 |

#### 2026-08-28 생성 상태

- R09: 3개 생성 완료. PNG 원본과 WebP 배포본을 저장하고 소개 페이지의 별도 서사 카드에 적용했다.
- R10: 12개 생성 완료. `posterGeneratorNode`의 선택형 배경 프리셋으로 적용했다.
- R11: 실제 릴리스별 파생본의 기준이 되는 무문자 OG 베이스 1개를 생성했다.
- R12: 실제 캠페인별 파생본의 기준이 되는 무문자 3:1 커뮤니티 배너 베이스 1개를 생성했다.

## 3. 만들지 말아야 할 PNG

| 대상 | 올바른 방식 | 이유 |
| --- | --- | --- |
| 노드·내비게이션·상태·Provider 아이콘 | 현재 SVG 시스템 유지 | 작은 크기, 테마 전환, 선명도, 접근성에 SVG가 유리 |
| Scheduler/Webhook/Bot/Statistics 빈 상태 | 기존 일러스트 규칙을 따른 SVG | 단색 선형 모티프라 GPT 래스터의 장점이 없고 다크/라이트 대응이 어려움 |
| 개별 템플릿 workflow 미리보기 | graph를 서버/브라우저에서 자동 렌더 | 이미지와 실제 노드 구성이 항상 일치해야 함 |
| Inspector, Mock, Revision diff 화면 | 실제 UI 캡처 | 생성 이미지의 가짜 UI는 문서와 마케팅 신뢰도를 떨어뜨림 |
| 차트와 통계 | Recharts/HTML | 값, 라벨, 반응형 동작이 정확해야 함 |
| Google, Slack, YouTube 등 서비스 로고 | 공식 브랜드 에셋 | 상표 형태와 브랜드 가이드가 정확해야 함 |
| 사용자 프로필 사진·커뮤니티 작성자 얼굴 | 업로드 이미지 또는 이니셜 avatar | 허구의 인물을 실제 작성자처럼 보이게 하면 안 됨 |
| 로고·favicon·버튼 배지 | SVG/HTML | 작은 크기와 다양한 배율에서 래스터가 불리 |

현재 소개 페이지의 `demo-1.webp`, `demo-2.webp`, `demo-3.webp`는 실제 제품 화면이므로 유지할 가치가 높다. `intro-video-poster.jpg`도 영상 내용과 일치하는 실제 프레임으로 갱신해야 하며, GPT 이미지로 바꾸지 않는다.

## 4. 공통 아트 디렉션

제품 UI가 짙은 navy/slate 기반이므로 모든 이미지가 검은 배경에 녹아 없어지지 않도록 한다.

- 스타일: 세미 리얼 3D 에디토리얼, 정돈된 제품 광고 수준, 과도한 사이버펑크 금지
- 팔레트: deep navy `#0f172a`, slate `#1e293b`, blue `#3b82f6`, violet `#8b5cf6`, emerald `#10b981`
- 조명: 부드러운 스튜디오 광원, 가장자리 분리광, 충분한 중간톤
- 구성: 핵심 피사체를 중앙 60% 안에 두고, 제목/CTA가 올라갈 빈 공간을 한쪽에 확보
- 금지: 글자, 로고, 실제 서비스 UI, 워터마크, 읽을 수 없는 가짜 문장, 케이블 스파게티, 과도한 네온, 손가락이 강조된 인물
- 사람: 필요할 때만 사용하고, 한국의 현대적인 업무 환경을 자연스럽게 반영하되 특정 실존 인물처럼 만들지 않음
- 투명 PNG: 모달·완료 상태처럼 배경 위에 얹는 자산에만 사용
- 배경 포함 PNG: 컬렉션 커버와 랜딩 에디토리얼에 사용

## 5. GPT 생성 프롬프트 골격

### 컬렉션 커버

```text
Create a premium editorial hero image for a Korean visual workflow automation product.
Subject: [업무 장면]. Show physical objects and subtle luminous data paths that suggest
trigger → AI processing → human approval → action, without drawing a literal software UI.
Semi-realistic 3D editorial style, deep navy and slate environment, restrained blue,
violet and emerald accents, soft studio lighting, crisp material detail, calm and trustworthy.
16:9 composition, main subject within the center 60%, generous negative space on the [left/right].
No text, no letters, no numbers, no logos, no brand marks, no watermark, no fake interface.
```

### Mock 시나리오 썸네일

```text
Create a compact scenario thumbnail for a workflow testing tool.
Scene: [택배 주문 / 모바일 알림 / 온라인 결제] represented by 2–3 recognizable real-world
objects, with one subtle dotted path connecting event, validation and successful response.
Friendly semi-realistic 3D miniature diorama, dark navy base, one emerald success accent,
high legibility at 300 px, simple silhouette, no text, no logos, no people, no UI screenshot.
3:2 landscape composition.
```

### 온보딩 완료

```text
Create a transparent-background celebration asset for completing a first automation workflow.
A small chain of three polished workflow tiles successfully connected, a soft emerald pulse,
restrained paper confetti and tiny blue/violet particles, premium 3D product illustration,
balanced silhouette, readable at 240 px. No text, no logo, no background plane, no watermark.
4:3 composition with generous transparent padding.
```

## 6. 저장·납품 규칙

1. 생성 원본은 PNG로 보관한다. 컬러 프로필은 sRGB, 최소 긴 변 1600px를 권장한다.
2. 웹 배포본은 품질 78~85의 WebP/AVIF로 변환하고 PNG는 투명이 필요할 때만 직접 제공한다.
3. 각 자산은 desktop crop과 mobile crop을 별도로 검수한다. 단순 중앙 crop으로 의미가 잘리면 두 버전을 만든다.
4. 프롬프트, seed/생성 일자, 원본, 수정본을 함께 보관해 이후 세트의 일관성을 유지한다.
5. 생성물 안의 글자·로고·실존 브랜드 형태는 전수 확인하고 발견 시 제거한다.
6. 다크/라이트 테마 양쪽에서 실제 컴포넌트 위에 올려 대비를 확인한다.
7. 인물 이미지에는 실존 인물·유명인 유사성이 없는지 확인한다.

추천 디렉터리:

```text
frontend/src/assets/editorial/
  collections/
  mock-scenarios/
  onboarding/
  connectors/
  media-node-samples/
  campaigns/
```

## 7. 외부 서비스에서 확인한 패턴

- [n8n Workflow Templates](https://n8n.io/workflows/)는 방대한 커뮤니티 workflow 탐색 자체를 핵심 콘텐츠로 둔다. 이 제품도 템플릿 카드는 실제 graph 미리보기가 중심이어야 하고, GPT 아트는 컬렉션 수준에서만 보조하는 편이 정확하다.
- [Make Templates](https://www.make.com/en/templates)는 카테고리 탐색과 실제 automation 설명을 전면에 둔다. 따라서 장식 이미지를 대량 생산하기보다 카테고리 구분용 커버와 정확한 앱/시나리오 정보가 우선이다.
- [Make Scenario Templates 도움말](https://help.make.com/scenario-templates?fromSubscription=true)은 public/team template과 guided setup을 분리한다. 팀·커뮤니티 기능에서는 허구의 썸네일보다 실제 설정 상태와 검증 신호가 더 중요하다는 근거가 된다.
- [Zapier Templates](https://zapier.com/templates)는 workflow뿐 아니라 Agents, Chatbots, Forms 등 결과물 유형별 템플릿을 함께 탐색하게 한다. 향후 App Builder·AI 미디어 노드를 별도 컬렉션으로 보여줄 때 R01 계열 커버를 확장할 수 있다.
- [Retool Workflows](https://retool.com/build-enterprise-apps/workflows)는 AI 생성과 workflow builder를 실제 제품 화면으로 설명한다. 핵심 기능 증명에는 GPT로 만든 가짜 UI보다 현재의 실제 캡처를 유지하는 것이 맞다.

## 8. 권장 제작 순서

1. R02 Mock 시나리오 3장: 기능 범위가 이미 구체적이고 서로 다른 모티프라 품질 기준을 잡기 쉽다.
2. R01 중 `customer-support`, `documents`, `dev-ops` 3장: 커뮤니티 커버 스타일을 먼저 검증한다.
3. 같은 스타일이 UI와 맞으면 R01 나머지 3장으로 확장한다.
4. R03 온보딩 완료 1장과 R04 안전한 자동화 1장을 만든다.
5. Wave 1/3 구현 일정이 확정될 때 R07/R08을 제작한다.

첫 생성 배치는 **R02 3장**이 가장 적합하다. 실제 시나리오가 이미 존재하고, 제품 안에서 용도가 분명하며, 실패하더라도 기능 정보나 실제 UI를 왜곡하지 않는다.
