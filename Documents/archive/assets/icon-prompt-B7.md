# B7 배치 — Tier 3 API 센터 프로바이더 (8개) + 신규 provider-toss (1개)

`icon-generation-prompts.md` §2 의 #52~59 + 신규 `provider-toss`. **컬러 예외 배치** —
프로바이더 식별이 목적이라 `currentColor` 대신 지정 HEX 를 fill/stroke 에 직접 쓴다.
[ApiCenterPage.jsx](../../../frontend/src/pages/ApiCenterPage.jsx) 의 이모지 8개(`🤖 ✨ 💬 🔑 🎮 ✈️ 📝 📧`)를
전부 제거했고, 백엔드가 이미 지원하던 `{{API_CENTER:toss}}` 치환을 쓸 수 있도록
API 센터에 `toss` 프로바이더 카드를 신설했다.

## 이 배치에서 새로 확립한 규칙 — 컬러 아이콘의 양테마 대비

컬러 아이콘은 `currentColor` 가 아니므로 **다크(#0f172a/#1e293b)와 라이트(#f1f5f9) 양쪽에서
스스로 보여야 한다.** 이 배치에서 확인한 해법 두 가지:

1. **fill+stroke 쌍으로 대비를 내장한다.** 밝은 면(fill)과 어두운 획(stroke)을 한 도형에 같이 쓰면
   다크에서는 fill 이, 라이트에서는 stroke 가 실루엣을 만든다.
   → kakao 2종(노랑 fill `#facc15` + 갈색 stroke `#3c1e1e`), notion(흰 fill + `#191919` stroke).
   순수 노랑 stroke 는 라이트에서 대비 1.4:1 로 사실상 안 보인다 — 노랑은 반드시 fill 로만.
2. **내부 디테일은 fill 위에 올린다.** 흰 페이지 위의 검정 줄, 노랑 말풍선 안의 갈색 열쇠,
   파란 배지 위의 흰 체크는 배경 테마와 무관하게 항상 보인다.
3. **채워진 배지는 겹쳐도 된다.** 라인 아이콘의 "배지 겹침 금지"(B4·B5)는 넉아웃이 없어서였다.
   fill 배지는 스스로 넉아웃을 만든다 → provider-toss 의 파란 체크 배지가 카드 모서리를 덮는 구성이 가능.

## 붙여넣은 프롬프트

마스터 사양은 [icon-prompt-B5.md](icon-prompt-B5.md) 블록에 아래를 추가/치환한다.

```
[Tier 3 예외 사양 — 이 배치에만 적용]
- stroke="currentColor" 대신 각 항목에 지정된 HEX를 fill 또는 stroke에 직접 사용한다
- 단색 1~2색까지 허용. 그라데이션은 Gemini 항목에서만 linearGradient 1개 허용
  (id 는 전역 유일하게 — 로더가 SVG 를 인라인하므로 충돌 주의. 예: b7-grad-gemini)
- 20×20 라이브 영역, 2px 패딩 규칙은 동일하게 유지
- 로더(Icon 컴포넌트)가 루트에 stroke="currentColor" fill="none" 을 주입하므로
  모든 도형이 stroke 와 fill 을 명시적으로 선언해야 한다 (stroke="none" 포함)
- 아이콘이 자체 색을 가지므로 다크(#1e293b)·라이트(#f1f5f9) 양쪽에서 보여야 한다.
  어두운 단색 스트로크(#191919, #3c1e1e)는 다크에서 사라진다 — 밝은 fill 과 짝지어라
- 실제 기업 로고(OpenAI, Google, Kakao, Discord, Telegram, Notion, Toss) 재현 금지 — 기능 은유만

[생성할 아이콘 9개]
52. provider-openai.svg — 6갈래 방사 대칭 매듭 문양, 단색 #10a37f (공식 로고 복제 금지)
53. provider-gemini.svg — 속이 찬 4각 별 큰 것 1 + 작은 것 1, 청→자 그라데이션 (선 반짝임 금지 — +로 읽힘)
54. provider-kakao-rest.svg — 둥근 말풍선 + 점 3개, 노란 fill #facc15 + 갈색 stroke #3c1e1e
55. provider-kakao-token.svg — 말풍선 안에 작은 열쇠 (#54와 실루엣 구분: 사각 vs 타원, 꼬리 방향 반대)
56. provider-discord.svg — 둥근(날개형) 게임패드 실루엣 + 십자 패드 + 버튼 점 2, #5865F2 단색
    (node-discord-send 의 직사각 패드와 몸통으로 구분)
57. provider-telegram.svg — 원 테두리 안에 종이비행기, #26A5E4 단색
    (node-telegram-* 의 맨 비행기와 원으로 구분. 공식 로고(파란 원판+흰 비행기) 재현 금지 — 라인 스타일)
58. provider-notion.svg — 흰 fill 문서 페이지(우상단 접힘) + 세로 마진선 + 텍스트 줄 2, stroke #191919
59. provider-gmail-smtp.svg — 봉투 + 깊은 V자 접힘선, #ea4335 (node-email 과 달리 발송 화살표 없음)
+.  provider-toss.svg — 카드 사각형 + 스트라이프 + 우하단 파란 fill 원 배지 안 흰 체크, #0064FF
    (#28 node-toss-payments 의 컬러·배지 버전)
```

## 실제 생성 결과

QA 광학 크기 9/9 일치 (warn/bad 0건). 도형 1~4개, 합계 3.2KB.

| 파일 | 도형 | 기하 bbox | 색 |
|---|---|---|---|
| `provider-openai.svg` | 1 | x 2–22 · y 2–22 | #10a37f stroke |
| `provider-gemini.svg` | 2 | x 2–22 · y 2–22 | #3b82f6→#8b5cf6 grad fill (id `b7-grad-gemini`) |
| `provider-kakao-rest.svg` | 2 | x 2–22 · y 3–21 | #facc15 fill + #3c1e1e stroke |
| `provider-kakao-token.svg` | 3 | x 2.5–21.5 · y 3–21 | #facc15 fill + #3c1e1e stroke |
| `provider-discord.svg` | 3 | x 2–22 · y 5–18.5 | #5865F2 stroke |
| `provider-telegram.svg` | 3 | x 2–22 · y 2–22 | #26A5E4 stroke |
| `provider-notion.svg` | 4 | x 4–19.5 · y 2–22 | #fff fill + #191919 stroke |
| `provider-gmail-smtp.svg` | 2 | x 2–22 · y 4.5–19.5 | #ea4335 stroke |
| `provider-toss.svg` | 4 | x 2–22 · y 4.5–21 | #0064FF stroke/fill + #fff 체크 |

※ `provider-openai` 의 QA bbox 는 초안(회전 ellipse) 기준으로 y 8–16 으로 찍혔었다 —
`getBBox()` 는 요소 자신의 `transform` 을 무시한다. 최종본은 transform 없는 단일 path 라 정상 실측된다.

### 렌더로 발견해 고친 것 (2건 + 사전 차단 1건)

1. **`provider-openai` — React 로고로 읽혔다.** 초안은 "3개 ellipse 를 60°씩 회전"한 6갈래 매듭이었는데,
   168px 카드에서 보는 순간 원자 궤도(React 로고)였다. 개발자 대상 제품에서 최악의 오독.
   → 6개 꽃잎이 하나의 닫힌 path 로 이어지는 **로제트(매듭 꽃) 문양**으로 재설계.
   후보 2안(뾰족한 꽃잎 vs 둥근 꽃잎)을 렌더 비교해 둥근 쪽 채택. 16px 에서도 매듭으로 읽힌다.
2. **`provider-notion` — 다크에서 "문" 두 짝으로 갈라졌다.** 흰 fill 페이지에 **전체 높이 바인딩선**을
   그으면, 다크에서 검정 stroke 가 사라지면서 흰 영역이 좌우 두 조각(세로 막대 2개)으로 끊긴다.
   16px에선 냉장고/문으로 읽혔다. → 우상단 접힘(dog-ear) 페이지 + **부분 높이 마진선**(y7–17.5)으로
   재설계. 흰 실루엣이 한 덩어리로 유지되고, 접힘 덕에 node-file-modifier(접힘+줄 3개, 라인 스타일)와도
   fill 유무 + 마진선으로 구분된다.
3. **`provider-kakao-token` — 꼬리 분리 충돌을 코드 단계에서 차단.** 말풍선 몸통(rect)과 꼬리(삼각형)를
   따로 그리면 rect 의 갈색 테두리가 꼬리 밑동을 가로지른다(B4·B5의 배지 겹침과 같은 문제).
   렌더 전에 몸통+꼬리를 단일 path 로 합쳤다.

### 원래 모티프에서 바꾼 것

- **#55 kakao-token 의 "순환 화살표를 말풍선 테두리로"는 폐기.** 테두리 일부를 화살표로 바꾸는 안을
  기하로 여러 번 시도했지만, 원 위의 화살촉은 항상 날개 한쪽이 원 밖(다크에서 갈색이 안 보이는 영역)으로
  나간다. 갱신 상태는 카드 UI 가 이미 텍스트로 표시한다("자동 갱신 활성화됨"). 대신 실루엣 구분에 집중:
  rest = 가로 타원 말풍선 + 왼쪽 꼬리 + 점 3개, token = 둥근 사각 말풍선 + 오른쪽 꼬리 + 열쇠.
- **#56 discord 는 "둥근 게임패드"를 날개(그립) 실루엣으로 해석** — node-discord-send 가 이미
  직사각 몸통 게임패드라서, 몸통 형태를 바꿔야 세트 간 구분이 된다.
- **#57 telegram 은 원판+흰 비행기(공식 로고 구도)를 피해서** 원 "테두리" + 라인 비행기로.
- **#53 gemini 는 B4·B5 교훈대로 선 반짝임 대신 속이 찬 4각 별** — 큰 별 + 우하단 작은 별,
  둘 다 `url(#b7-grad-gemini)`.

## 앱 적용 완료

| 파일 | 변경 |
|---|---|
| [src/pages/ApiCenterPage.jsx](../../../frontend/src/pages/ApiCenterPage.jsx) | 이모지 8개 → 아이콘 이름 문자열. 카드 헤더 `<Icon size={24}/>`(이모지 1.5rem 과 동일 광학 크기), 가이드 모달 `<Icon size={20}/>`. **toss 프로바이더 카드 신설.** 미사용이던 `Plus` import 제거 |
| [src/pages/ApiCenterPage.css](../../../frontend/src/pages/ApiCenterPage.css) | `.api-icon` 에 `inline-flex` 정렬 추가 (svg 베이스라인 어긋남 방지) |

### toss 프로바이더 — 백엔드 치환 키 검증

- [backend/graph.py:334-337](../../../backend/graph.py) 이 `UserApiKey.provider` 값을 그대로
  `{{API_CENTER:<provider>}}` 키로 만들어 노드 데이터 전체에 대입한다. **하드코딩 화이트리스트 없음** —
  저장 시 provider id 가 정확히 `toss` 이기만 하면 `{{API_CENTER:toss}}` 가 치환된다.
- [backend/main.py:462](../../../backend/main.py) `POST /api/user/apikeys` 도 provider 문자열을 검증 없이
  저장하므로 프론트에서 `id: 'toss'` 로 보내면 끝. **백엔드 수정 없음.**
- 단, `tossNode` 의 secretKey 를 자동으로 `{{API_CENTER:toss}}` 로 채워주는 곳은 아직 없다
  (meta_agent 프롬프트는 discord/telegram/notion/kakao_token 만 안내). 사용자가 노드에 직접
  `{{API_CENTER:toss}}` 라고 입력해야 하며, 이 사용법을 발급 가이드 4단계에 적어뒀다.

### 검증 결과

- `npx vite build` 통과, 콘솔 `[Icon]` 경고 0 (9개 이름 전부 로더에 등록 확인)
- QA 페이지: bbox warn/bad 0건, 16/18/24px 다크·라이트 칩, 그레이스케일 전부 육안 확인
- 실행 중이던 dev 서버(5173)에 임시 하니스(`b7-harness.html` + `src/b7-harness.jsx`, 검증 후 삭제)를
  물려 **실제 ApiCenterPage CSS·마크업**으로 렌더: 카드 헤더 9개 + 가이드 모달 헤더,
  `data-theme="dark"/"light"` 양쪽 확인. 아이콘-제목 정렬과 광학 크기가 이모지 시절과 동일
- 실루엣 충돌 확인: kakao-rest vs kakao-token(타원+왼꼬리+점 vs 사각+오른꼬리+열쇠),
  provider-telegram vs node-telegram-trigger/send(원 유무), provider-discord vs
  node-discord-send(날개형 vs 직사각), provider-notion vs node-file-modifier(fill+마진선 vs 라인+줄 3개)
- 스크린샷: `scratchpad/b7/qa-table-providers-v2.png`, `qa-cards-providers-v2.png`, `harness-full.png`

### 남긴 것 / 발견한 별개 문제

- **[ApiCenterPage.css](../../../frontend/src/pages/ApiCenterPage.css) 가 쓰는 CSS 변수가 어디에도 정의돼 있지 않다**:
  `--bg-secondary` `--bg-primary` `--bg-hover` `--text-primary` `--text-secondary` `--accent-color`
  `--error-color` `--success-color`. 카드 배경은 투명으로 폴백돼 티가 안 나지만, 라이트 테마에서
  저장 버튼(`--accent-color` 배경 + 흰 글자)이 사실상 안 보인다. **이 작업 전부터 있던 문제**라
  아이콘 배치 범위 밖으로 판단하고 손대지 않았다 — 별도 수정 권장.
- `provider-gemini` 의 gradient id `b7-grad-gemini` 는 전역 유일해야 한다. 이후 배치에서 그라데이션을
  추가하게 되면 `b8-grad-*` 처럼 배치 접두사를 유지할 것.
- 가이드 모달의 마크다운 링크 파서는 한 줄에 링크 1개(`parts.length === 3`)만 처리한다 —
  toss 가이드도 그 형식에 맞춰 작성했다.
