# 마일스톤 애니메이션 자산 매니페스트

> 생성일: 2026-08-28  
> 생성 방식: Codex 내장 `imagegen` + CSS 합성 애니메이션  
> 기준 캐릭터: `frontend/src/assets/editorial/character/nodi-reference.png`

## 구현 결과

| Variant | 최초 발생 조건 | PNG 원본 | WebP 배포본 |
| --- | --- | --- | --- |
| `tutorial-track` | 각 튜토리얼 트랙의 마지막 과정 완료 | `tutorial-track-complete.png` | `tutorial-track-complete.webp` |
| `tutorial-all` | 전체 학습 트랙 완료 | `tutorial-all-complete.png` | `tutorial-all-complete.webp` |
| `onboarding` | 시작 체크리스트 5/5 완료 | `onboarding-complete.png` | `onboarding-complete.webp` |
| `first-run` | 오류 로그가 없는 첫 실제 Workflow 실행 | `first-run-success.png` | `first-run-success.webp` |
| `first-deploy` | App Runner·Chatbot·Form 첫 실제 배포 | `first-deploy-success.png` | `first-deploy-success.webp` |

모든 PNG는 `1254 × 1254` RGBA이며, 배포본은 `640 × 640` 투명 WebP다. WebP 5개 합계는 약 133KB다.

## 동작 구조

- `MilestoneCelebrationHost`가 앱 전역에서 완료 이벤트를 수신한다.
- 동시에 발생한 이벤트는 큐에 쌓아 하나씩 재생한다.
- `milestoneCelebrations.js`가 `localStorage`에 최초 노출 여부를 기록한다.
- 튜토리얼·온보딩 진행률 초기화 시 대응하는 축하 기록도 함께 초기화한다.
- 실제 캐릭터 키 아트는 한 번 bounce하고, CSS ring과 12개 기하 파티클이 바깥으로 퍼진다.
- `prefers-reduced-motion` 사용자는 정적 카드만 본다.

## 적용 파일

- 전역 호스트: `frontend/src/MilestoneCelebration.jsx`
- 모션 스타일: `frontend/src/MilestoneCelebration.css`
- 이벤트·최초 노출 기록: `frontend/src/milestoneCelebrations.js`
- 연결 지점: `App.jsx`, `TutorialPage.jsx`, `OnboardingChecklist.jsx`, `EditorPage.jsx`, `DeployModal.jsx`
- 자산 폴더: `frontend/src/assets/editorial/celebrations/`

## 공통 프롬프트 골격

```text
Use case: stylized-concept.
Asset type: transparent milestone key art for CSS-composited web animation.
Input image 1 is the exact Nodi character reference.
Preserve the compact cobalt capsule body, navy oval face, two pale-blue eyes,
one upper-left antenna with an emerald node, two slate arms and two slate legs.
Restrained modern IT 2.5D illustration, matte plastic, simple rounded geometry.
Centered compact square silhouette with generous padding, readable at 160px.
Output a genuine RGBA PNG. No checkerboard, background, floor, frame, text,
logo, fake UI, realistic person, confetti, stars, neon, chrome or glass.
```

개별 주제는 각각 `양팔을 든 노디와 연결된 노드 3개`, `노디 팀의 마지막 타일 조립`, `상태점 5개가 있는 체크리스트`, `세 노드를 통과한 첫 실행`, `Workflow 타일에서 펼쳐지는 데스크톱·모바일 프레임`으로 지정했다.

## 검수 기록

- 생성 과정에서 체크무늬가 실제 배경으로 포함된 RGB 결과 6개는 제외했다.
- 사용 결과는 배경 제거 편집 후 `file` 검사에서 모두 RGBA로 확인했다.
- 데스크톱 1440×1000과 모바일 390×844에서 실제 렌더링을 확인했다.
- 모바일 카드의 content-box 오버플로를 발견해 `border-box`로 수정했다.
