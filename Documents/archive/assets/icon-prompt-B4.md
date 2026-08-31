# B4 배치 프롬프트 — Tier 1 외부 연동 (8개)

`icon-generation-prompts.md` §2 의 #22~29. **`MessageCircle` 3중 충돌**과 **`Send` 2중 충돌**이
이 배치에서 풀린다. 마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 와 동일하니 그쪽 블록을
그대로 쓰고 `[생성할 아이콘]` 목록만 아래로 교체하면 된다.

```
[중요 제약 — 이 배치 추가분]
- 이 8개는 현재 Globe / MessageCircle(2종 공용) / Send / StickyNote / CreditCard /
  ArrowRightLeft / Mail 을 쓰고 있고, 그중 MessageCircle 은 '카카오 알림톡'과 '디스코드 발송'이
  같이 쓰는 중이다. 두 아이콘의 실루엣이 완전히 달라야 한다.
- 교체하지 않고 남는 아이콘과도 겹치면 안 된다:
  · lucide Globe   → '웹훅 수신' 이 계속 쓴다      → 웹 크롤러는 반드시 추가 요소가 필요
  · lucide MessageCircle → '디스코드 봇(시작)' 이 계속 쓴다 → 카카오는 말풍선만으로는 부족
  · lucide Send    → '텔레그램 봇(시작)' 이 계속 쓴다   → 텔레그램 발송은 종이비행기만으로는 부족

[생성할 아이콘 8개]
1. node-web-crawler.svg (웹 크롤러) —
   격자 있는 지구 구체를 좌상단에, 우하단에 작은 돋보기 배지. 두 도형이 겹치지 않게
2. node-email.svg (이메일 전송) —
   봉투(안쪽 V자 접힘선 포함), 봉투 오른쪽 위 바깥에 작은 우상향 화살표
3. node-kakao-alimtalk.svg (카카오 알림톡) —
   모서리가 아주 둥근 알약형 말풍선 + 좌하단 꼬리, 내부에 감탄부호(획 + 점)
4. node-discord-send.svg (디스코드 발송) —
   게임패드: 라운드 사각 본체 + 좌측 십자 방향키 + 우측 버튼 점 2개
5. node-telegram-send.svg (텔레그램 발송) —
   종이비행기(접힘선 포함) + 좌상단에 길이 다른 속도선 2개
6. node-notion.svg (Notion) —
   페이지 사각형 좌측에 세로 굵은 바인딩선, 오른쪽 영역에 길이 다른 수평선 2개
7. node-toss-payments.svg (토스페이먼츠) —
   카드 사각형 + 상단 가로 마그네틱 띠, 카드 안쪽에 체크 표시
8. node-http-request.svg (HTTP Request) —
   위쪽에 오른쪽 화살표(실선 = 요청), 아래쪽에 왼쪽 화살표(점선 = 응답)
```

---

## 실제 생성 결과

정적 사양 검사 8/8 통과 · QA 광학 크기 8/8 일치.

| 파일 | 도형 | 크기 | 기하 bbox | 교체된 lucide |
|---|---|---|---|---|
| `node-web-crawler.svg` | 5 | 0.33KB | x 2–22 · y 2–22 | Globe *(3중 중복)* |
| `node-email.svg` | 3 | 0.29KB | x 2–21.5 · y 5.5–18 | Mail |
| `node-kakao-alimtalk.svg` | 4 | 0.29KB | x 2–22 · y 3–21 | MessageCircle *(3중)* |
| `node-discord-send.svg` | 4 | 0.29KB | x 2–22 · y 6–18 | MessageCircle *(3중)* |
| `node-telegram-send.svg` | 3 | 0.26KB | x 2–22 · y 3–21 | Send *(2중)* |
| `node-notion.svg` | 3 | 0.27KB | x 3–21 · y 2–22 | StickyNote |
| `node-toss-payments.svg` | 3 | 0.26KB | x 2–22 · y 4–20 | CreditCard |
| `node-http-request.svg` | 4 | 0.29KB | x 3–21 · y 4–20 | ArrowRightLeft |

### 원래 모티프에서 바꾼 것

1. **`node-http-request` — 응답 화살표를 점선으로.**
   원 모티프는 "요청/응답 화살표 짝"이었는데 그대로 그리면 lucide `ArrowRightLeft` 와 사실상
   같은 그림이 된다(= 새로 만들 이유가 없음). 요청은 실선, 응답은 `stroke-dasharray` 로 갈라서
   의미를 담았다. **참고: `ArrowRightLeft` 는 애초에 중복이 아니었다** — 이 아이콘은 세트 통일성
   목적이므로 우선순위가 낮았다.

2. **`node-kakao-alimtalk` — 벨 배지를 버리고 말풍선 안에 감탄부호.**
   6px 배지에 종 모양은 그려지지 않는다. 말풍선 밖 배지는 넉아웃(배경 지우기)이 없으면
   테두리와 충돌해 얼룩이 된다. 말풍선 내부에 넣는 쪽이 16px에서 훨씬 깨끗했다.

3. **`node-telegram-send` — 궤적 점선 → 속도선 2개.**
   비행기 뒤 궤적을 그릴 공간이 없었다(비행기 자체가 좌하단 대각선을 다 쓴다).
   좌상단 여백에 속도선 2개를 넣는 쪽으로 바꿨다. 평행선 4px 규칙을 지키느라
   `M2 3h4M2 7h2` 로 위치를 두 번 조정했다(처음 `y=4/8` 은 비행기 꼬리와 0.7px까지 붙었음).

4. **`node-web-crawler` — 돋보기를 겹치지 않는 배지로.**
   "지구 + 돋보기 겹침" 을 24px에 넣으면 두 원의 호가 교차해 렌즈 모양 얼룩이 생긴다.
   지구를 좌상단(r=7)에, 돋보기를 우하단 배지(r=3)로 분리해 0.5px 간격을 확보했다.

**교훈: 배지는 본체와 겹치면 안 된다.** 단색 라인 아이콘은 넉아웃을 쓸 수 없어서,
겹치는 배지는 항상 충돌로 보인다. B5의 `node-payment-link`·`node-toss-payments` 에서도
같은 이유로 배지를 본체 안으로 옮겼다.

---

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/Sidebar.jsx](../../../frontend/src/Sidebar.jsx) | 팔레트 8개 교체 |
| [src/customNodes.jsx](../../../frontend/src/customNodes.jsx) | 캔버스 7곳 교체 (`tossNode` 는 컴포넌트가 없어 제외 — 아래 참고) |

미사용이 된 lucide import(`Mail`, `ArrowRightLeft`, `CreditCard`, `StickyNote`)를 제거했다.
`Box`/`Terminal`/`Shuffle`/`LogOut`/`Network`/`Repeat` 는 **이전부터** 죽어 있던 import 라
무관한 변경이 되지 않도록 그대로 뒀다.

### 검증 결과

- `npm run build` 통과, eslint 에러 0
- 실제 `Sidebar` 렌더 → 외부 연동 카테고리 13개가 전부 서로 다른 아이콘, 콘솔 에러 없음
- `ReactFlowProvider` 로 캔버스 노드 7개 렌더 → 전부 정상, 콘솔 에러 없음

### 충돌 해소 현황 (실측)

팔레트 정적 노드 32개 중 **커스텀 11개 + lucide 21개**. 남은 중복은 2종뿐이다.

| 아이콘 | 남은 중복 | 해소 예정 |
|---|---|---|
| `Clock` | 스케줄 (시작) / Delay (대기) | B1 + B2 |
| `LogOut` | 결과 출력 / 반복 종료 | B1 + B2 |

B5 이전 9종이었던 중복이 2종으로 줄었다. `Puzzle`(5중) · `FileCode`(2중) ·
`MessageCircle`(3중) · `Send`(2중) · `Globe`(노드 간 2중) 모두 해소.

---

## 적용 중 발견한 별개 문제 — `tossNode` 캔버스 컴포넌트 없음

`tossNode` 는 팔레트에 있고 백엔드도 완전히 지원하는데
(`backend/meta_agent.py:290` LLM 생성 허용 목록, `backend/dry_run.py:33`),
**프런트엔드에 캔버스 컴포넌트가 없다.** [EditorPage.jsx](../../../frontend/src/pages/EditorPage.jsx)
의 `nodeTypes` 맵에도 없다 — 팔레트의 모든 노드 타입 중 유일하게 빠져 있다.

결과: 사용자가 토스페이먼츠를 캔버스에 끌어놓거나 **AI가 tossNode 를 포함한 워크플로우를
생성하면**, ReactFlow 기본 노드(라벨만 있는 빈 상자)로 렌더되어 `secretKey` / `searchType` /
`searchValue` 를 입력할 수 없다.

아이콘 작업 범위를 넘어서므로 손대지 않았다. 고치려면
`customNodes.jsx` 에 `TossNode` 컴포넌트를 추가하고 `nodeTypes` 에 등록해야 한다.
필드 정의는 `meta_agent.py:290` 에 이미 명세돼 있으므로, 아예
[nodeRegistry.js](../../../frontend/src/nodeRegistry.js) 로 옮겨 `DynamicNode` 가 처리하게 하는 게
가장 적은 코드로 끝난다 (`icon: 'node-toss-payments'` 도 그때 함께 지정).
