# B1 + B2 배치 — Tier 1 기본·입력·AI·로직 (16개)

`icon-generation-prompts.md` §2 의 #1~16. 마지막 노드 간 중복(`Clock` 3중 · `LogOut` 2중)이
여기서 풀린다. 마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 블록을 그대로 쓴다.

## 이 배치의 설계 결정 — "트리거 언어"

시작 노드가 5개(`startNode` `scheduleNode` `webhookNode` `discordTriggerNode` `telegramTriggerNode`)나
되는데 서로 아무 공통점이 없었다. **재생 삼각형을 품으면 시작 노드**라는 규칙을 세웠다.

| 노드 | 구성 |
|---|---|
| 시작 | 재생 삼각형 + 뒤로 퍼지는 호 |
| 스케줄 (시작) | 달력 + 내부에 재생 삼각형 |
| 디스코드 봇 (시작) | 말풍선 + 내부에 재생 삼각형 |
| 텔레그램 봇 (시작) | 종이비행기 + 좌상단 작은 재생 삼각형 |
| 웹훅 수신 | 선 3개가 한 점으로 수렴 (외부에서 들어옴 — 삼각형 없음) |

덕분에 캔버스에서 "어디서 시작하는 흐름인지" 아이콘만 보고 판별된다.
같은 이유로 발송 노드와도 갈라진다: 디스코드 봇(말풍선+▷) vs 디스코드 발송(게임패드),
텔레그램 봇(비행기+▷) vs 텔레그램 발송(비행기+속도선).

---

## 붙여넣을 프롬프트 (생성할 아이콘 목록)

```
[중요 제약 — 이 배치 추가분]
- 시작(트리거) 노드 4개는 "재생 삼각형을 품는다"는 규칙을 공유한다. 단, 삼각형 위치와
  본체 모양은 서로 달라야 한다.
- 아래는 이미 만들어진 아이콘이므로 겹치면 안 된다:
  · 카카오 알림톡 = 알약형 말풍선 + 꼬리 + 감탄부호  → #6 은 말풍선이지만 rx 를 줄이고 삼각형
  · 텔레그램 발송 = 종이비행기 + 좌상단 속도선 2개   → #7 은 좌상단에 삼각형
  · 구글 캘린더 = 달력 + 날짜 점 + 선택 원          → #2 는 달력 + 삼각형
  · 웹 크롤러 = 지구 + 돋보기 배지                 → #5 는 지구를 쓰지 마라
- lucide Play / Repeat / Merge / Variable / RefreshCw 는 실행·새로고침 버튼에서 계속 쓰인다.
  노드 아이콘이 그 버튼들과 같아 보이면 안 된다.
- #13(반복)과 #14(반복 종료)는 둘 다 루프 기반이다. 실루엣이 확실히 달라야 한다.

[생성할 아이콘 16개]
 1. node-start.svg (시작) — 재생 삼각형 + 왼쪽 뒤로 퍼지는 얇은 호 1겹
 2. node-schedule.svg (스케줄, 시작) — 달력(걸이 2개 + 헤더선) 내부에 재생 삼각형
 3. node-output.svg (결과 출력) — 오른쪽 화살표가 길이 다른 수평선 3개(출력 텍스트)를 향함
 4. node-dynamic-input.svg (동적 입력) — 입력 필드 + 내부 캐럿과 텍스트선, 우상단 밖에 속이 찬 4각 별
 5. node-webhook.svg (웹훅 수신) — 왼쪽 3갈래(위 곡선/직선/아래 곡선)가 오른쪽 한 점으로 수렴,
    그 점에 속이 찬 원
 6. node-discord-trigger.svg (디스코드 봇, 시작) — 둥근 말풍선 + 좌하단 꼬리, 내부에 재생 삼각형
 7. node-telegram-trigger.svg (텔레그램 봇, 시작) — 종이비행기 + 좌상단에 작은 재생 삼각형
 8. node-value.svg (변수) — 좌우 각진 대괄호 [ ] 사이에 속이 찬 마름모
 9. node-prompt.svg (프롬프트) — 모서리 각진 말풍선 + 좌하단 꼬리, 내부에 길이 다른 수평선 3개
10. node-llm.svg (LLM) — 사각 칩 + 사방 핀 8개, 칩 내부에 속이 찬 4각 별
11. node-multi-agent.svg (Multi-Agent) — 삼각 배치된 원 3개를 선으로 연결, 상단 원이 더 큼
12. node-condition.svg (조건 분기) — 왼쪽 입력선 → 마름모 → 오른쪽 위/아래 두 갈래
13. node-loop.svg (반복) — 위/아래 레일이 순환하는 루프, 양 끝에 반대 방향 화살촉 2개
14. node-break.svg (반복 종료) — 같은 루프인데 진행 화살표가 오른쪽 굵은 세로 정지선에 막힘
15. node-delay.svg (Delay) — 모래시계 (시계 금지 — #2 와 구분)
16. node-merge.svg (Merge) — 위/아래 두 곡선이 오른쪽에서 하나로 합쳐져 화살표로 나감
```

---

## 실제 생성 결과

정적 사양 검사 16/16 통과 · QA 광학 크기 16/16 일치.

| 파일 | 도형 | 기하 bbox | 교체된 lucide |
|---|---|---|---|
| `node-start.svg` | 2 | x 2.2–21 · y 4–20 | Play *(실행 버튼과 공용)* |
| `node-schedule.svg` | 4 | x 3–21 · y 2–22 | Clock *(3중)* |
| `node-output.svg` | 3 | x 2–21 · y 7–17 | LogOut *(2중)* |
| `node-dynamic-input.svg` | 4 | x 2–22 · y 2–18 | Keyboard |
| `node-webhook.svg` | 4 | x 2–21 · y 4–20 | Globe *(3중)* |
| `node-discord-trigger.svg` | 3 | x 3–21 · y 3–21 | MessageCircle *(3중)* |
| `node-telegram-trigger.svg` | 3 | x 3–22 · y 4–20 | Send *(2중)* |
| `node-value.svg` | 3 | x 3–21 · y 3–21 | Variable *(중복 없음)* |
| `node-prompt.svg` | 3 | x 2–22 · y 2–21 | MessageSquare |
| `node-llm.svg` | 3 | x 2–22 · y 2–22 | BrainCircuit |
| `node-multi-agent.svg` | 4 | x 2.5–21.5 · y 2.5–20.5 | Users |
| `node-condition.svg` | 3 | x 2–20 · y 6–18 | SplitSquareHorizontal |
| `node-loop.svg` | 4 | x 3–21 · y 3–21 | Repeat *(중복 없음)* |
| `node-break.svg` | 4 | x 2–20 · y 3–21 | LogOut 180° 회전 *(2중)* |
| `node-delay.svg` | 4 | x 5–19 · y 2–22 | Clock *(3중)* |
| `node-merge.svg` | 3 | x 3–21 · y 5–19 | Merge *(중복 없음)* |

### 렌더해보고 고친 것

1. **`node-break` — 화살촉이 없어 루프로 안 읽혔다.**
   처음엔 "끊긴 레일 2개 + 정지선"으로 그렸는데 렌더해보니 그냥 `⊐|` 였다.
   진행 방향 화살촉을 넣어 **"루프의 진행 경로가 벽에 부딪혀 멈춘다"** 로 바꾸니 의미가 살았다.
   → 교훈: 루프/흐름 아이콘에서 **화살촉은 장식이 아니라 "이게 경로다"를 알리는 필수 요소**다.

2. **`node-value` — 마름모가 대괄호에 비해 너무 작았다.** d=4 → d=5 로 키웠다.

### 원래 모티프에서 바꾼 것

- **`node-value`: 중괄호 `{ }` → 각진 대괄호 `[ ]`.**
  원 모티프가 중괄호였는데, #18 `node-json-parser`(B3)도 중괄호가 모티프다. 먼저 만드는 쪽이
  가져가면 뒤가 막히므로, 변수는 대괄호로 양보했다. **배치를 나눠 진행할 때는 아직 안 만든
  뒤 배치의 모티프까지 확인해야 한다.**
- **`node-llm`: 뇌 → 칩 + 반짝임.** #11 Multi-Agent 가 "연결된 원 3개"라서, LLM 을 신경망
  모양으로 그리면 둘이 겹친다. 칩으로 갈라놓았다.
- **`node-delay`: 모래시계에서 모래알을 뺐다.** 16px 에서 알갱이는 얼룩이 된다.
- **`node-loop`: lucide `Repeat` 와 실루엣이 거의 같다.** `Repeat` 은 애초에 중복이 아니었고
  "반복"에 이보다 나은 그림이 없다 — 세트 통일성 목적이라 우선순위가 낮은 항목이었다.

---

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/Sidebar.jsx](../../../frontend/src/Sidebar.jsx) | 팔레트 16개 교체 |
| [src/customNodes.jsx](../../../frontend/src/customNodes.jsx) | 캔버스 16곳 (교체 13 + **아이콘이 없던 3곳에 신규 추가**) |

`OutputNode` · `LoopNode` · `BreakNode` 는 캔버스 헤더에 아이콘이 아예 없이 텍스트만 있었다
(B5 의 `FileModifierNode`·`TemplateAnalyzerNode` 와 같은 상태). 아이콘을 새로 넣었다.
`ConditionNode` 는 `size={isExpanded ? 14 : 28}` 로 크기가 동적이라 그 동작을 유지했다.

미사용이 된 lucide import 14개를 두 파일에서 제거했다. `Box`/`Terminal`/`Shuffle`/`Network`/
`CreditCard` 는 **이전부터** 죽어 있던 import 라 무관한 변경이 되지 않도록 그대로 뒀다.

### 검증 결과
- `npm run build` 통과, eslint 에러 0
- 실제 `Sidebar` 렌더 → 기본·입력·AI·로직 16개 정상, 콘솔 에러 없음
- `ReactFlowProvider` 로 캔버스 노드 16개 렌더 → 정상, 콘솔 에러 없음

---

## 최종 충돌 현황 (실측)

**팔레트 노드 37개 = 커스텀 32 + lucide 5. 노드 간 lucide 중복은 0.**

남은 lucide 5개는 정확히 **B3(코드 & 데이터) 배치** 하나다:

| 노드 | 현재 lucide | 중복 여부 |
|---|---|---|
| 파이썬 | `Terminal` | 없음 |
| JSON 파서 | `Braces` | 없음 |
| 토크나이저 | `Box` | AppBuilder Container / 채팅 사이드바와 3중 |
| 분배기 | `Network` | 없음 |
| 데이터베이스 | `Database` | 통계 페이지와 2중 |

B4·B5 시작 시점 9종이던 중복이 **0종**이 됐다 (노드 범위). 남은 중복은 노드 밖
(내비게이션 `Clock`/`Globe`, AppBuilder `Box`/`TextCursorInput`)이며 B6·B8 몫이다.

### 남은 확인 사항
- `node-condition` 은 16px 에서 마름모+분기가 다소 눌려 보인다. 실사용에서 문제되면
  입력선을 빼고 마름모를 키우는 게 대안.
