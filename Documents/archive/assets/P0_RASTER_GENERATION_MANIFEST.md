# P0 래스터 생성 기록 — v2

> 생성일: 2026-08-28  
> 생성 방식: Codex 내장 `image_gen`  
> 아트 기준: `../../design/RASTER_ART_DIRECTION_AND_CHARACTER_BIBLE.md`  
> 캐릭터 레퍼런스: `frontend/src/assets/editorial/character/nodi-reference.png`

## 결과

| ID | 파일 | 레퍼런스 역할 |
| --- | --- | --- |
| R01-1 | `collections/collection-marketing-v2.png` | 노디 이미지의 팔레트·재질만 참조, 캐릭터 미사용 |
| R01-2 | `collections/collection-customer-support-v2.png` | 동일 |
| R01-3 | `collections/collection-documents-v2.png` | 동일 |
| R01-4 | `collections/collection-data-ops-v2.png` | 동일 |
| R01-5 | `collections/collection-dev-ops-v2.png` | 동일 |
| R01-6 | `collections/collection-productivity-v2.png` | 동일 |
| R02-1 | `mock-scenarios/mock-order-webhook-v2.png` | 동일 |
| R02-2 | `mock-scenarios/mock-mobile-notification-v2.png` | 동일 |
| R02-3 | `mock-scenarios/mock-virtual-payment-v2.png` | 동일 |
| R03 | `onboarding/onboarding-complete-v2.png` | 노디의 외형·비율·색상 고정, 투명 배경 |
| R04 | `security/safe-automation-v2.png` | 노디의 외형·비율·색상 고정 |

모든 경로의 기준 디렉터리는 `frontend/src/assets/editorial/`이다.

## 공통 최종 프롬프트

```text
Use case: stylized-concept
Input image 1 is the canonical style reference. Reuse its minimal geometric 2.5D language,
matte flat surfaces, rounded forms and restrained palette.
Style: modern IT product editorial illustration, simplified abstract 2.5D geometry,
matte flat-color surfaces, no outlines, one subtle shading step.
Camera: consistent shallow isometric view.
Background: near-solid deep navy #0f172a with no visible room, horizon, desk or scenery.
Palette: navy #0f172a, slate #1e293b and #334155, blue #3b82f6,
violet #8b5cf6, emerald #10b981, light neutral #e2e8f0.
Use at most two accent colors prominently.
Composition: only three main conceptual groups, one clear flow,
large simple silhouettes readable at 300px.
Constraints: no text, letters, numbers, logos, brand marks, watermark, actual UI,
detailed scenery, glass, chrome, reflections, glow, neon, particles, cables or clutter.
```

## 자산별 주제 프롬프트

```text
collection-marketing-v2:
Three blank campaign cards enter one blue processing block and become two clean outward
channel shapes. A single thin violet connector path. No character.

collection-customer-support-v2:
One incoming rounded message tile, one blue sorting block with three clean slots,
and one resolved reply tile. One emerald status dot. No character.

collection-documents-v2:
Three blank paper sheets enter one blue processing arch and become three aligned structured
blocks plus one blank finished report. One thin emerald path. No character.

collection-data-ops-v2:
A cylinder, a cube grid and a cloud-like block feed through one gate, become four aligned
data blocks, then three minimal unlabeled chart bars. No character.

collection-dev-ops-v2:
Two abstract bracket-like code shapes pass through three test checkpoints and reach one
deployment cube with a tiny emerald status dot. No character.

collection-productivity-v2:
A blank mail tile, a blank calendar grid and one task dot flow into one organizing block
and emerge as three aligned cards. No character.

mock-order-webhook-v2:
One unbranded shipping box with a blank tag, one blue event tile and one emerald response dot,
connected by one curved slate path. No character.

mock-mobile-notification-v2:
One unbranded smartphone slab, one blank violet notification card, one blue sender block
and one small emerald delivery dot. No character.

mock-virtual-payment-v2:
One unbranded payment card, one blue gateway arch, one blank receipt tile and one small
emerald completion dot. No character.

onboarding-complete-v2:
Exactly one canonical Nodi modestly celebrates beside exactly three connected workflow tiles,
one emerald status dot and eight small geometric confetti pieces. Genuinely transparent background.

safe-automation-v2:
Exactly one canonical Nodi holds one emerald approval token beside an abstract credential capsule;
a slate shield gate controls the path to one blue destination block. No padlock cliché.
```

## 캐릭터 프롬프트 불변 조건

```text
Exactly one Nodi: one-piece blue vertical rounded capsule body, height-to-width ratio 1.15,
navy oval face screen, exactly two pale-blue dot eyes, exactly one short upper-left antenna
with one emerald circular node, exactly two short slate capsule arms and two short slate legs.
No hair, clothing, glasses, nose, ears, fingers, shoes, eyebrows, blush, teeth or tongue.
No extra antennae or limbs. Preserve identity and proportions from the reference image.
```

## 버전 정책

- 앞서 생성된 세미 리얼 3D 시안 4장은 사용자 요청에 따라 삭제했다.
- 새 아트 방향은 모두 `-v2.png`로 저장했다.
- 온보딩 완료와 API Center 보안 이미지는 WebP 파생본을 만들어 실제 UI에 연결했다.
- 컬렉션 6장과 Mock 3장은 대응 UI가 구현된 뒤 연결한다.
