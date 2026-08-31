# B3 배치 — Tier 1 코드 & 데이터 (5개)

`icon-generation-prompts.md` §2 의 #17~21. **이걸로 워크플로우 노드 37개가 전부 커스텀 아이콘이 된다.**
마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 블록을 그대로 쓴다.

## 붙여넣을 프롬프트 (생성할 아이콘 목록)

```
[중요 제약 — 이 배치 추가분]
- 이미 만들어진 아이콘과 겹치면 안 된다. 특히:
  · 웹훅 수신 = 왼쪽 3갈래가 오른쪽 한 점으로 수렴(수평 팬)
    → #20 분배기를 "1개에서 3개로 발산하는 수평 팬"으로 그리면 16px에서 거울상이 되어
      구분이 불가능하다. 반드시 다른 구조(예: 수직 트리)로 그려라.
  · Multi-Agent = 삼각 배치된 원 3개 + 연결선  → #20 도 원을 여러 개 쓰면 겹친다
  · 변수 = 각진 대괄호 [ ] + 마름모            → #18 은 중괄호 { } 를 써도 된다(양보받음)
- lucide TerminalSquare(콘솔 패널 버튼)와 lucide Database(통계 페이지 지표)는 계속 쓰인다.
  #17, #21 이 그것들과 똑같아 보이면 안 된다.
- 파이썬 뱀 로고를 그리지 마라 (상표).

[생성할 아이콘 5개]
17. node-python.svg (파이썬) — 터미널 창: 사각 프레임 + 상단 타이틀바 구분선 + 내부에 `>` 프롬프트
    기호와 커서 밑줄. 타이틀바가 lucide TerminalSquare 와 갈리는 지점이다
18. node-json-parser.svg (JSON 파서) — 좌우 중괄호 { } 안에 수직 척추 + 오른쪽으로 갈라지는
    가지 3개(계층 트리)
19. node-tokenizer.svg (토크나이저) — 가로로 긴 라운드 막대 하나가 점선 세로 경계 3개로
    조각 4개로 나뉜 형태
20. node-distributor.svg (분배기) — 상단에 사각 노드 1개, 아래로 내려간 뒤 수평 버스로 퍼져
    좌·중·우 3방향으로 내려가는 수직 배분 트리
21. node-database.svg (데이터베이스) — 원통 실린더, 상단 타원 + 구분 타원 2개로 3단
    (lucide Database 는 2단이다)
```

---

## 실제 생성 결과

정적 사양 검사 5/5 통과 · QA 광학 크기 5/5 일치.

| 파일 | 도형 | 기하 bbox | 교체된 lucide |
|---|---|---|---|
| `node-python.svg` | 4 | x 2–22 · y 4–20 | Terminal |
| `node-json-parser.svg` | 3 | x 3–21 · y 2–22 | Braces |
| `node-tokenizer.svg` | 2 | x 2–22 · y 7–17 | Box *(3중 중복)* |
| `node-distributor.svg` | 2 | x 3–21 · y 2–20 | Network |
| `node-database.svg` | 3 | x 3–21 · y 2–22 | Database *(2중 중복)* |

### 렌더해보고 고친 것

1. **`node-distributor` — 웹훅 수신과 16px에서 거울상이었다.**
   원 모티프대로 "왼쪽 원 1개 → 오른쪽 점 3개로 발산"을 그렸더니, `node-webhook`
   ("왼쪽 3갈래 → 오른쪽 점 1개로 수렴")과 나란히 놓았을 때 **둘 다 "3갈래 팬 + 점 하나"로만
   읽혀서 구분이 안 됐다.** 24px에서는 갈리지만 16px에서는 실패.
   → 수평 팬을 버리고 **수직 배분 트리**로 바꿨다. 방향축이 달라지니 확실히 갈린다.
   **교훈: 대칭/거울 관계인 두 아이콘은 작은 크기에서 같은 그림이다. 축을 바꿔야 한다.**

2. **`node-tokenizer` — 높이 8px로 너무 납작했다.** 세로 폭이 이웃(20px)의 40% 뿐이라
   팔레트에서 유독 작아 보였다. 10px 로 키웠다.

### 솔직한 평가 — 이 배치의 3개는 차별화 가치가 낮다

`node-python`(타이틀바만 추가) · `node-json-parser`(중괄호 유지) · `node-database`(2단→3단)는
원래 lucide 아이콘과 실루엣이 크게 다르지 않다. **애초에 중복이 없던 항목**이라 그렇다
(#17 Terminal, #18 Braces 는 노드 간 중복 0). 이 3개의 가치는 "충돌 해소"가 아니라
**37개 노드가 하나의 세트로 보이게 하는 통일성**과, 앞으로 색·굵기를 한 곳에서 바꿀 수 있는
소유권이다. 실제 중복이 있던 건 `Box`(토크나이저, 3중)와 `Database`(2중) 둘뿐이었고,
그것도 충돌 상대가 노드가 아니라 AppBuilder·채팅 사이드바·통계 페이지였다.

---

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/Sidebar.jsx](../../../frontend/src/Sidebar.jsx) | 팔레트 5개 교체 |
| [src/customNodes.jsx](../../../frontend/src/customNodes.jsx) | 캔버스 5곳 (교체 2 + **아이콘이 없던 3곳에 신규 추가**) |

`PythonNode` · `TokenizerNode` · `DistributorNode` 도 캔버스 헤더에 아이콘이 없었다.
**아이콘 없이 텍스트만 있던 캔버스 노드는 총 8개였다** (B5 2개 + B1/B2 3개 + B3 3개).

미사용이 된 lucide import 를 제거하면서, 이전부터 죽어 있던 `CreditCard`(customNodes.jsx)도
함께 정리됐다. `Shuffle` 은 두 파일에 여전히 남아 있는 dead import 다 — 아이콘 작업과
무관하므로 손대지 않았다.

두 파일의 lucide import 는 이제 UI chrome 만 남았다:
- `Sidebar.jsx`: `Shuffle, Search, ChevronDown, ChevronRight, Puzzle, X`
  (`Puzzle` 은 `meta.icon` 없는 레지스트리 노드용 폴백으로 유지)
- `customNodes.jsx`: `Shuffle, ChevronDown, ChevronRight`

### 검증 결과
- `npm run build` 통과, eslint 에러 0
- 실제 `Sidebar` 렌더 → **노드 37개 / 아이콘 SVG 37개**, 콘솔 에러 없음
- `ReactFlowProvider` 로 캔버스 노드 5개 렌더 → 정상, 콘솔 에러 없음

---

## 최종 상태 — 워크플로우 노드 37/37 커스텀

| 항목 | 값 |
|---|---|
| 팔레트 노드 | 37개 (정적 31 + 레지스트리 6) |
| 커스텀 아이콘 | **37개 (100%)** |
| 노드에 남은 lucide | **0개** |
| SVG 파일 | 37개, 합계 **11.1KB** (개당 평균 0.30KB) |
| 캔버스 적용 지점 | 32곳 (리터럴 31 + `DynamicNode` 의 `meta.icon` 1) |

시작 시점 9종이던 아이콘 충돌은 노드 범위에서 전부 해소됐다.
남은 중복은 모두 노드 밖이며 **B6(내비게이션) · B8(앱 빌더)** 몫이다:

| 남은 중복 | 위치 | 배치 |
|---|---|---|
| `Clock` | 내비 "스케줄 관리" ↔ 채팅 사이드바 | B6 |
| `Globe` | 내비 "웹훅 관리" | B6 |
| `Box` | AppBuilder Container ↔ 채팅 사이드바 | B8 |
| `TextCursorInput` | AppBuilder Input Field ↔ Text Area | B8 |

이모지를 아이콘으로 쓰는 29곳(ApiCenter 8 + TemplateModal 21)은 **B7** 과 별도 작업으로 남아 있다.
