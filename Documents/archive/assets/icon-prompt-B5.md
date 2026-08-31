# B5 배치 프롬프트 — Tier 1 고급 + 레지스트리 (8개)

`icon-generation-prompts.md` §2 의 #30~37. **Puzzle 하나로 돌려쓰던 레지스트리 노드 5종**이 여기 들어있어
교체 효과가 가장 큰 배치다. 아래 블록을 통째로 복사해서 붙여넣으면 된다.

---

## 붙여넣을 프롬프트

```
당신은 프로덕션 UI 아이콘 세트를 만드는 아이콘 디자이너입니다.
아래 사양을 100% 준수하는 SVG 코드를 생성하세요.

[기하 사양]
- viewBox="0 0 24 24", 루트에 width/height 속성은 넣지 않는다
- 기하 좌표는 2~22 범위를 꽉 채운다 (=20×20). 최대 변이 18 미만이면 실패로 본다.
  (교체하지 않고 남겨둘 lucide 아이콘 약 60개가 2~22 규약이다. 3~21로 그리면 같은 줄에서
   새 아이콘만 10% 작아 보인다. 획 외곽(±1)이 1~23까지 나가는 건 허용.)
- stroke="currentColor", stroke-width="2", fill="none"
- stroke-linecap="round", stroke-linejoin="round"
- 좌표는 0.5px 그리드에 스냅한다 (2, 2.5, 3 … 형태. 3.7231 같은 값 금지)
- path/circle/rect/line 기본 도형만 사용. filter, mask, clipPath, 그라데이션, 텍스트, style 속성 금지
- 도형 개수는 아이콘당 최대 5개
- 평행한 획끼리는 중심 간격 4px 이상 (stroke-width 2라 4px 미만이면 16px에서 붙어 보인다)
- 작은 점은 lucide 관행대로 `M8 14h.01` (길이 0 + round cap) 으로 찍는다
- "채워진 1칸/선택된 상태" 같은 단일 강조 요소에만 fill="currentColor" stroke="none" 허용

[스타일 사양]
- lucide-react 0.300과 시각적으로 이어지는 기하학적 라인 아이콘 스타일
- 원근·그림자·질감 없음. 완전한 플랫 라인 드로잉
- 상대적 시각 무게가 세트 전체에서 균일해야 함
- 배지/서브 요소는 우상단 또는 우하단에만, 지름 6px 이하

[출력 형식]
아이콘 1개당 아래 형식으로만 출력. 설명 문장은 붙이지 않는다.

--- 파일명: <파일명>.svg ---
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  ...
</svg>

[중요 제약]
- 실제 기업 로고(Slack, Google, Toss, Python 등)를 재현하지 마라. 상표권 문제가 있다.
  대신 그 서비스의 "기능"을 은유하는 도형으로 그려라.
- 아래 8개는 현재 전부 lucide `Puzzle`(5종) 또는 `FileCode`(2종) 하나를 돌려쓰고 있다.
  8개가 서로 혼동되면 안 된다. 색이나 회전으로 구분하는 건 실패로 본다 — 실루엣이 달라야 한다.
- #30 과 #31 은 둘 다 문서 기반이므로 특히 주의: 한쪽은 내부 선, 한쪽은 돋보기로 갈라라.

[생성할 아이콘 8개]
1. node-file-modifier.svg (자동 완성) —
   문서 사각형(우상단 접힘) 안에 자동 채워지는 수평선 3개, 마지막 줄은 점선(stroke-dasharray)
2. node-template-analyzer.svg (템플릿 분석) —
   와이어프레임 프레임(내부에 길이 다른 막대 2개) 위에 돋보기가 우하단에서 겹침
3. node-human-approval.svg (사용자 승인) —
   사람 상반신 실루엣(머리 원 + 어깨 호) + 오른쪽에 체크 표시
4. node-slack.svg (Slack 메세지) —
   채널 해시 기호 #. 수직 획 2개를 살짝 기울여 정적인 격자로 보이지 않게
5. node-payment-link.svg (결제 링크 생성) —
   사슬 고리 2개(좌우 C자)가 마주보고, 그 사이 빈 공간에 속이 찬 코인 원 1개
6. node-google-sheets.svg (구글 시트) —
   3×3 스프레드시트 격자, 좌상단 1칸만 채워짐
7. node-google-calendar.svg (구글 캘린더) —
   달력 사각형 + 상단 걸이 2개 + 헤더 구분선, 날짜 점 3개와 속이 찬 선택 원 1개
8. node-poster-generator.svg (포스터/이미지 생성) —
   액자 사각형 안에 산 능선 + 태양, 우상단 액자 밖에 속이 찬 4각 별(AI 생성 함의)
```

---

## 실제 생성 결과

8개 모두 `frontend/src/assets/icons/node/` 에 있고, 정적 사양 검사 8/8 통과 · QA 광학 크기 8/8 일치.

| 파일 | 도형 | 크기 | 기하 bbox |
|---|---|---|---|
| `node-file-modifier.svg` | 5 | 0.36KB | x 4–20 · y 2–22 |
| `node-template-analyzer.svg` | 5 | 0.32KB | x 2–22 · y 2–22 |
| `node-human-approval.svg` | 3 | 0.28KB | x 2–21 · y 3–21 |
| `node-slack.svg` | 4 | 0.26KB | x 4–20 · y 3–21 |
| `node-payment-link.svg` | 3 | 0.31KB | x 2–22 · y 7–17 |
| `node-google-sheets.svg` | 3 | 0.34KB | x 3–21 · y 3–21 |
| `node-google-calendar.svg` | 5 | 0.37KB | x 3–21 · y 2–22 |
| `node-poster-generator.svg` | 4 | 0.40KB | x 2.5–22 · y 2–20.5 |

### 원래 모티프에서 바꾼 것 (남은 배치에 반영할 교훈)

1. **`node-slack` — 말풍선을 버렸다.**
   원 모티프는 "해시 격자 + 우측 말풍선 꼬리"였는데, ⓐ 24px에 격자와 말풍선을 같이 넣으면
   평행선 간격 4px 규칙을 못 지키고 ⓑ #9 `node-prompt`(각진 말풍선 + 내부 선 3개)와 실루엣이 겹쳤다.
   → 채널 기호 `#` 단독. 개발자에게 `#`은 곧 채널이라 은유가 오히려 더 정확해졌다.

2. **`node-human-approval` — "머리 위 대기 점선 호"를 버렸다.**
   16px에서 머리 위 얇은 호는 뭉개져 얼룩으로만 보인다. 대기 상태는 노드 UI가 이미 표시한다.

3. **`node-poster-generator` — `+` 오독을 잡느라 한 번 갈아엎었다.**
   반짝임을 십자 획(`M20 3v3 M18.5 4.5h3`)으로 그렸더니 **더하기로 읽혀 "이미지 추가"로 오독**됐다.
   → 속이 찬 4각 별 path 로 교체. **선으로 그린 반짝임은 작은 크기에서 항상 +로 읽힌다.**
   Tier 2 #40 `nav-app-builder`, Tier 3 #53 `provider-gemini`, Tier 4 #73 도 반짝임을 쓰므로 같은 처리 필요.

4. **`node-payment-link` — 후보 4개를 렌더해 비교한 뒤 결정.**
   처음엔 "고리 2개를 마주보게 + 사이에 코인"으로 그렸는데 연결 바가 없으니 `C ● D`,
   즉 **사슬이 아니라 괄호로 읽혔다.** 맞물린 두 원은 16px에서 덩어리가 되고,
   대각 사슬 조각은 갈고리로 보였다. → lucide `link-2` 의 확실한 사슬 실루엣을 유지하고
   가운데 빈 공간에 r=2.5 속이 찬 코인. **좌우 대칭 C자 2개는 사슬로 읽히지 않는다 — 연결 요소가 필요하다.**

5. **사양 자체를 고쳤다 — 라이브 영역 20×20(패딩 2px) → 기하 좌표 2~22.**
   원안대로 그리면 기하 bbox가 3~21(18×18)에 들어가는데, 교체하지 않고 남기는 lucide 아이콘
   60여 개는 2~22(20×20)다. 섞이면 새 아이콘만 10% 작아 보인다.
   B1~B4, B6~B9 프롬프트도 반드시 수정된 사양으로 보낼 것.

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/icons/index.jsx](../../../frontend/src/icons/index.jsx) | **신규** — `import.meta.glob` 로더. 의존성 추가 없음 |
| [src/nodeRegistry.js](../../../frontend/src/nodeRegistry.js) | 5종에 `icon: 'node-...'` 필드 추가 |
| [src/Sidebar.jsx](../../../frontend/src/Sidebar.jsx) | 팔레트 8개 교체 + 레지스트리 루프가 `meta.icon` 사용 |
| [src/customNodes.jsx](../../../frontend/src/customNodes.jsx) | 캔버스 4곳: `DynamicNode`, `HumanApprovalNode`, `FileModifierNode`, `TemplateAnalyzerNode` |

교체하지 않은 노드는 lucide 폴백이 유지된다 (`meta.icon` 없으면 `Puzzle`).

### 검증 결과

- `npm run build` 통과. SVG는 별도 애셋 없이 번들에 인라인됨
- 실제 `Sidebar` 컴포넌트를 실제 CSS로 렌더 → 팔레트 8개 정상, 다크/라이트 양쪽 확인, 콘솔 에러 없음
- `ReactFlowProvider` 로 캔버스 노드 8개 렌더 → 그라데이션 헤더 위에서 강조 요소가 흰색으로 정상
- 새 아이콘이 교체하지 않은 lucide 이웃(웹 크롤러·이메일·카카오·Notion·토스·HTTP)과 무게가 맞음

### 적용 중 발견한 별개 버그 (고침)

`posterGeneratorNode` 는 `category: 'action'` 인데 [Sidebar.jsx](../../../frontend/src/Sidebar.jsx) 의
`categories` 배열에 `action` 이 없다. 기존 코드가 `meta.category || 'integration'` 이라
**undefined 만 걸러서** 목록에 없는 값은 그대로 통과했고, 그 결과 이 노드는 어느 카테고리 필터에도
걸리지 않아 **팔레트에서 아예 렌더되지 않았다** (검색으로만 나옴 — 37개 정의 중 36개만 표시).

→ 알려진 category id 집합으로 검증해서 벗어나면 `integration` 으로 폴백하도록 고쳤다.
`posterGeneratorNode` 를 정말 별도 카테고리로 두고 싶으면 `categories` 에
`{ id: 'action', title: '동작 (Action)' }` 를 추가하는 쪽이 맞다.

### 남은 확인 사항

- `node-google-sheets` 는 16px에서 3×3 격자가 다소 빽빽하다. 실제 팔레트에 넣고 최종 확인 필요.
  더 뭉개지면 격자를 2열×3행으로 줄이는 게 대안.
- `node-payment-link` 는 y 방향 기하 폭이 10 뿐이다(가로로 넓은 아이콘). lucide `link-2` 와 같은
  비율이라 규약 위반은 아니지만, 세로로 꽉 찬 이웃(`node-file-modifier` 등)과 나란히 두면
  살짝 작아 보일 수 있다.
