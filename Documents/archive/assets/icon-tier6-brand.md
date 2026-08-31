# Tier 6 브랜드 코어 — 로고 마크 · 파비콘 · OG 이미지

`icon-generation-prompts.md` §2 Tier 6 의 **#79 로고 · #80 파비콘 · OG 이미지**.
빈 상태 일러스트(`assets/illustrations/`)는 별개 배치다 — 이 문서 범위 밖.

UI 아이콘 79개(B1~B9)와 달리 이 배치는 **24 그리드가 아니라 32 그리드**다.
공통으로 지킨 것은 §3 의 "0.5px 스냅 · 도형 최소화 · 텍스트 요소 금지" 원칙뿐이다.

---

## 이 배치에서 문서와 다르게 한 결정 3가지

### 1. OG 이미지를 이미지 생성 모델이 아니라 SVG 로 만들었다

§0 표는 OG 를 "PNG (이미지 생성 모델)" 로 분류했다. 그런데 **§4-2 프롬프트 본문이
`flat vector illustration, no text, crisp edges, no photorealism, 2px connector lines`** —
회화적 표현이 하나도 없는 **벡터 명세**다. §0 이 든 근거("그라데이션·질감·회화적 표현이
필요")가 이 프롬프트에는 해당하지 않는다.

그래서 `og-image.svg` 를 직접 쓰고 playwright 로 래스터화했다. 결과:

| | 이미지 생성 모델 | SVG → 래스터화 (채택) |
|---|---|---|
| 1200×630 정확도 | 리사이즈·크롭 필요 | 정확히 1200×630 |
| 색상 | #3b82f6 근사치 | 정확히 스펙 HEX |
| 재현성 | 매번 다른 그림 | 소스가 3.5KB SVG, 언제든 재생성 |
| 용량 | 보통 300KB~1MB | **128KB** |
| 수정 | 전체 재생성 | 노드 좌표 한 줄 |

### 2. 락업(`logo-lockup.svg`)을 만들지 않았다

§4-1 은 워드마크를 path 로 아웃라인한 락업을 요구하지만, **사용자가 폰트를 검토 중**이다.
path 로 아웃라인하면 폰트 결정과 즉시 어긋난다.
현재 [MainSidebar.jsx](../../../frontend/src/MainSidebar.jsx) 구조가

```jsx
<img src={logoMark} alt="WorkFlow Ai" className="brand-logo" />
<span className="brand-name logo-container">
  <span className="text-workflow">WorkFlow</span>
  <span className="text-ai">&nbsp;Ai</span>
</span>
```

**마크(이미지) + 워드마크(CSS 텍스트)** 라서, 폰트를 바꾸면 워드마크가 자동으로 따라간다.
이 구조를 그대로 유지했다. 폰트가 확정되면 그때 락업 SVG 를 만들면 된다.

### 3. 브랜드 SVG 는 `assets/icons/` 가 아니라 `assets/brand/` 에 뒀다

[icons/index.jsx](../../../frontend/src/icons/index.jsx) 로더는 `assets/icons/**/*.svg` 를 글롭해서
**`viewBox="0 0 24 24"` 래퍼를 직접 그린다.** 32 그리드인 로고를 거기 넣으면 잘린다.
`assets/icons/brand/` 디렉터리는 비어 있는 채로 뒀다 (§5-1 이 예고한 자리이지만
로더 사양이 맞지 않는다).

브랜드 마크는 `<img src>` 로 소비한다 — Vite 가 4KB 미만 SVG 를 data URI 로 인라인하므로
네트워크 요청도 없고, `<img>` 라서 **그라디언트 id 충돌도 원천적으로 없다.**
그래도 §4-1 지침대로 id 는 전역 유일하게 `brand-logo-grad` 로 지었다.

---

## 로고 마크 — 후보 3개 비교와 선정

### 컨셉 (공통)

W 를 **꼭짓점 5개의 지그재그**로 그리고, 그 가운데 봉우리(Λ)에 가로획을 넣어 **A** 를 만든다.
W 의 마지막 획만 위로 오버슛시켜 **좌하단 → 우상단 상승**을 만든다.
양 끝점에 원(노드)을 찍으면 같은 그림이 **연결된 노드 그래프**로도 읽힌다.

```
M4 13.5 L9.5 25.5 L16 10.5 L22.5 25.5 L28 6.5   ← W 지그재그 (마지막 획만 상승)
M12 19.5 H20                                     ← 가운데 Λ 를 A 로 만드는 크로스바
circle(4, 13.5, r3)  circle(28, 6.5, r3.5)       ← 시작/종료 노드 (종료가 더 큼)
```

가운데 Λ 의 기울기를 **6.5 : 15** 로 잡은 이유: 크로스바 y=19.5 에서 좌우 다리와의 교점이
x=12.1 / 19.9 로 떨어져 **크로스바 양 끝(12, 20)이 0.5 그리드에 스냅**된다.

### 후보

| | 컨셉 | 도형 | 획 | W | A | 노드그래프 | 16px |
|---|---|---|---|---|---|---|---|
| **C1 node** ✅ | 지그재그 + 양 끝 노드 + 크로스바 | 4 | 3 | ✅ | ✅ | ✅ | 보통 |
| C2 solid | 굵은 지그재그, 노드 없음 | 2 | 4 | ✅ | ✅ | ❌ | **최상** |
| C3 arrow | 지그재그 + 종단 화살촉 + 시작 노드 | 4 | 3 | ✅ | ✅ | △ | 낮음 |

### 선정: C1 (`logo-mark.svg`)

- **§4-1 이 요구한 세 가지 읽기를 모두 만족하는 유일한 후보다.**
  C2 는 16px 가독성이 가장 좋지만 "연결된 노드 그래프" 읽기가 **완전히 사라진다** —
  노드 없는 굵은 W 일 뿐이다. C3 은 상승은 가장 강하지만 화살촉이 흔한 클리셰이고
  작은 크기에서 실루엣이 가장 지저분하다.
- C1 의 16px 가독성은 "보통"이지만 **실제로 16px 로 쓰이는 곳은 파비콘 하나뿐**이고,
  파비콘은 `#0f172a` 라운드 사각 위 흰색이라 대비 17.85:1 로 형태가 남는다 (렌더 확인).
  앱에서 마크가 쓰이는 실제 크기는 36 / 45 / 56 / 80px 다.
- 종료 노드를 시작 노드보다 크게(r3 → r3.5) 해서 방향성을 형태로도 한 번 더 준다.

탈락 후보 2종은 **`frontend/src/assets/brand/candidates/`** 에 단색·그라디언트 쌍으로 남겼다.
좌표계를 최종본과 동일하게 맞춰뒀으므로 **파일 복사만으로 교체된다.**

```bash
cd frontend/src/assets/brand
cp candidates/logo-mark-c2-solid.svg          logo-mark.svg
cp candidates/logo-mark-c2-solid-gradient.svg logo-mark-gradient.svg
# favicon.svg / apple-touch-icon.svg 안의 <path>·<circle> 도 같이 갈아끼우고
# 아래 "PNG 재생성" 스니펫을 다시 돌릴 것
```

---

## 렌더해보고 고친 것 (8건)

정적으로 잡힌 것은 0건이다. B1~B9 와 똑같이 **전부 렌더해보고 발견했다.**

1. **1차 후보 3개가 전부 16px 에서 소문자 낙서로 뭉갰다.**
   봉우리를 18 → 12 → 6 으로 계단식 상승시켰더니 왼쪽 봉우리가 너무 낮아 W 가 잘려 보였다.
   → **대칭 W + 마지막 획만 오버슛** 으로 재설계. W 가 W 로 읽히고 상승도 남는다.

2. **굵은 버전(획 5, butt cap)에서 A 크로스바가 완전히 삼켜졌다.**
   기하로 확인해보니 획 5 일 때 크로스바 높이에서 Λ 두 다리 사이 빈 공간이 **1.4px** 뿐이다.
   → **"굵은 획 + A 카운터"는 32 그리드에서 양립 불가.** Λ 를 넓히고 획을 4 로 낮춰서 해결.
   교훈: 카운터(글자 속 빈 공간)가 있는 글자는 획 굵기에 상한이 있다.

3. **링 노드 5개 + 엣지(`e-rings`)는 W 로도 A 로도 안 읽혔다.**
   그냥 원 3개 달린 V 였다. 노드 그래프를 "노드 우선"으로 그리면 글자가 죽는다.
   → **획이 주(主), 노드가 종(從)** 이어야 둘 다 읽힌다.

4. **크로스바를 아래로 내리면(`g-lowbar`) A 가 삼각형이 된다.** 카운터가 사라진다.
   A 의 크로스바는 apex~foot 의 **50~60% 지점**이 한계다.

5. **Λ 꼭짓점에 노드 점을 찍으면(`h2`) A 의 뾰족한 끝이 뭉개진다.** 노드는 양 끝에만.

6. **획 3.5 + 노드 r3 이면 노드가 노드로 안 읽힌다.** 지름/획 비가 1.7배라 그냥 둥근 끝이다.
   → **노드 지름은 획 굵기의 2배 이상.** 최종본은 획 3 / 지름 6~7 (2.0~2.3배).

7. **`<img src="*.svg">` 로는 OG 이미지가 아예 로드되지 않았다.**
   `<img>` 의 SVG 는 secure static mode 라 `<filter>` + `<use>` 가 있는 문서가
   통째로 실패한다. 4.3KB 짜리 **빈 PNG** 가 나왔는데 에러도 콘솔 경고도 없었다.
   → 래스터화는 `page.goto('file://…svg')` 로 SVG 문서에 **직접 이동**해서 찍는다.
   (`Documents/build-icon-qa.py` docstring 의 `<img>` 예시로는 이 케이스가 안 된다)

8. **로고만 문제가 아니었다 — 워드마크도 라이트 테마에서 안 보였다.**
   [MainSidebar.css](../../../frontend/src/MainSidebar.css) 의 `.logo-container` 와 `.text-workflow`
   가 `color: #ffffff` 하드코딩이고, `.text-ai` 는 **규칙 자체가 없어서** 같은 흰색을 상속했다.
   즉 라이트 테마에서 `[로고]` `WorkFlow Ai` **전체가** 흰 배경에 흰 글씨였다.
   → `var(--text-color)` + `.text-ai { color: #3b82f6 }`. **폰트(`Poppins`)는 손대지 않았다.**

---

## 대비 실측

WCAG 상대 휘도 기준. 3:1 이 §4-1 이 요구한 하한이다.

### 로고 마크 (그라디언트 `#3b82f6` → `#8b5cf6`)

| 색 | `#0f172a` 다크 페이지 | `#1e293b` 다크 사이드바 | `#f1f5f9` 라이트 페이지 | `#fdfefe` 라이트 사이드바 |
|---|---|---|---|---|
| `#3b82f6` (시작) | **4.85:1** ✅ | **3.98:1** ✅ | **3.36:1** ✅ | **3.64:1** ✅ |
| `#8b5cf6` (끝) | **4.22:1** ✅ | **3.45:1** ✅ | **3.87:1** ✅ | **4.19:1** ✅ |
| 렌더 픽셀 실측(마크 코어) | 4.65:1 | 3.81:1 | 3.89:1 | 4.22:1 |

**최악 케이스 3.36:1** (그라디언트 시작색 × 라이트 페이지 배경) — 하한 통과.
그라디언트를 파랑→보라로 잡은 게 여기서 이득이다: 파랑은 라이트에서, 보라는 다크에서
상대적으로 약한데 **한 마크 안에 둘 다 있어서 어느 테마에서도 절반은 강하다.**

`.text-ai` 액센트 `#3b82f6` 도 같은 표를 따른다 (라이트 사이드바 3.64:1).

### 구 `logo.png` 와의 비교 — 문제의 실증

| | `#0f172a` | `#1e293b` | `#f1f5f9` | `#fdfefe` |
|---|---|---|---|---|
| 구 `logo.png` (흰 "WA") | 17.06:1 | 13.98:1 | **측정 불가** | **측정 불가** |

"측정 불가" = 256px 로 렌더한 뒤 **배경과 채널 합 90 이상 차이나는 픽셀이 0개**.
안티에일리어싱 가장자리를 빼면 라이트 배경에서 남는 픽셀이 하나도 없다.
즉 §1 이 적은 "라이트 테마에서 안 보임"은 과장이 아니라 **문자 그대로 투명**이었다.

### 파비콘

| | 대비 |
|---|---|
| 흰 마크 on `#0f172a` 플레이트 (내부 대비) | **17.85:1** |
| `#0f172a` 플레이트 vs 라이트 탭바 `#f1f5f9` | **16.30:1** ✅ |
| `#0f172a` 플레이트 vs 다크 탭바 `#202124` | 1.11 |

다크 탭바에서는 **플레이트가 배경에 녹지만** 그게 문제가 아니다 — 흰 마크가
17:1 로 남아서 오히려 잘 보인다 (스크린샷 `07-favicon-png.png` 두 번째 칸).
라이트/다크 양쪽에서 식별된다는 요구는 충족한다.

---

## 산출 파일

### 벡터 소스 — `frontend/src/assets/brand/` (5.7KB)

| 파일 | 용도 | 비고 |
|---|---|---|
| `logo-mark.svg` (398B) | 단색 마크 | `stroke="currentColor"`, 부모 색 상속 |
| `logo-mark-gradient.svg` (681B) | **앱에서 실제 쓰는 마크** | `id="brand-logo-grad"` (전역 유일) |
| `favicon.svg` (526B) | 브라우저 탭 | `#0f172a` rx=6 플레이트 + 흰 마크 |
| `apple-touch-icon.svg` (737B) | iOS 홈 화면 소스 | 라운드 없음·풀블리드 (iOS 가 자체 마스킹) |
| `og-image.svg` (3.5KB) | OG 카드 소스 | 1200×630 |
| `candidates/logo-mark-c2-solid{,-gradient}.svg` | 탈락 후보 | 좌표계 동일, 복사로 교체 가능 |
| `candidates/logo-mark-c3-arrow{,-gradient}.svg` | 탈락 후보 | 〃 |

### 정적 자산 — `frontend/public/` (신규 디렉터리)

Vite 는 `public/` 을 **가공 없이 루트(`/`)로 서빙**하고 빌드 시 `dist/` 로 그대로 복사한다.
이 프로젝트에 `public/` 이 없어서 새로 만들었다.

| 파일 | 크기 | 투명도 |
|---|---|---|
| `favicon.svg` | 526B | — |
| `favicon-32.png` | 966B | **투명** (라운드 모서리 밖) |
| `apple-touch-icon-180.png` | 3.6KB | **불투명** (iOS 는 알파를 검게 합성한다) |
| `og-image-1200x630.png` | 128KB | 불투명 |

**PNG 재생성** (SVG 를 고쳤을 때):

```bash
cd /home/ubuntu/app
./backend/venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
B='frontend/src/assets/brand/'; P='frontend/public/'
import os
JOBS=[(B+'favicon.svg', P+'favicon-32.png', 32,32, True),
      (B+'apple-touch-icon.svg', P+'apple-touch-icon-180.png', 180,180, False),
      (B+'og-image.svg', P+'og-image-1200x630.png', 1200,630, False)]
with sync_playwright() as p:
    b=p.chromium.launch()
    for src,out,w,h,tr in JOBS:
        # <img src="*.svg"> 는 filter/use 가 있으면 로드 실패한다. 문서로 직접 이동할 것.
        pg=b.new_page(viewport={'width':w,'height':h}, device_scale_factor=1)
        pg.goto('file://'+os.path.abspath(src)); pg.wait_for_timeout(500)
        pg.screenshot(path=out, omit_background=tr); pg.close()
        print(out)
    b.close()
PY
cp frontend/src/assets/brand/favicon.svg frontend/public/favicon.svg
```

### OG 이미지 구성 (§4-2 대조)

| §4-2 요구 | 구현 |
|---|---|
| 1200×630 | ✅ |
| `#0f172a` + dot grid 6% | ✅ `<pattern>` 24px 간격, `fill-opacity="0.06"` |
| 좌 2/3 노드 그래프 5개 | ✅ x 80~800 (= 정확히 2/3), 150×80 rx18 |
| 베지어 커넥터, 2px, soft glow | ✅ 5개, `feGaussianBlur` |
| blue / violet / emerald | ✅ `#3b82f6` ×2, `#8b5cf6` ×1, `#10b981` ×2 |
| 우 1/3 여백 | ✅ **로고 마크 220px 배치** (문서는 "비워둔다"였으나 로고가 생겼으므로 채움) |
| no text / no letters | ✅ 텍스트 요소 0개. 카드 내부는 추상 바 도형 |
| 80px safe margin | ✅ 최좌 x=80, 최상 y=115, 최하 y=510, 최우 로고 x=1105 (여백 95) |

---

## 적용 내역

| 파일 | 변경 |
|---|---|
| [frontend/index.html](../../../frontend/index.html) | `lang` en→**ko** · `<title>` "Business Automation Flow"→**"WorkFlow Ai — 코딩 없이 연결하는 시각적 업무 자동화"** · `description` · 파비콘 3종 link · OG 7개 · Twitter 4개 |
| [src/MainSidebar.jsx](../../../frontend/src/MainSidebar.jsx) | `logo.png` → `logo-mark-gradient.svg` · `alt` "Auto Flow Logo"→**"WorkFlow Ai"**. `<span class="brand-name">` 구조 유지 |
| [src/MainSidebar.css](../../../frontend/src/MainSidebar.css) | `.logo-container`·`.text-workflow` 의 `#ffffff` → `var(--text-color)` · `.text-ai` 규칙 신설(`#3b82f6`). **폰트 미변경** |
| [src/RequireAuth.jsx](../../../frontend/src/RequireAuth.jsx) | 로그인 화면 56px 로고 교체 (`alt` 는 이미 "WorkFlow Ai Logo" 였다) |

`frontend/src/logo.png` 는 **삭제하지 않았다.** import 만 뺐다.

---

## 검증

| 항목 | 결과 |
|---|---|
| 후보 3개 × 다크/라이트/그레이스케일 × 16~128px | `01`~`04` 스크린샷, 4라운드 반복 |
| 최종본 × 4배경 × 16/20/24/32/45/56/96px | `05-final-assets.png` |
| 파비콘 실제 탭 크기(16·20·32) + 8배 확대 | `07-favicon-png.png` — 16px 에서도 W 실루엣과 노드 2개 남음 |
| OG 1200×630 전체 | `06-og-image.png` |
| 실제 사이드바 (다크·라이트 × 확장·축소) | `10-sidebar-grid.png` — dev 서버 5173 재사용 |
| 로그인 화면 (다크·라이트) | `11-login-grid.png` |
| `npx vite build` | ✅ 통과 (24.9s) |
| `dist/` 복사 | ✅ `favicon.svg` `favicon-32.png` `apple-touch-icon-180.png` `og-image-1200x630.png` |
| `vite preview` HTTP | ✅ 4개 모두 200 + 올바른 `content-type` |

스크린샷: `/tmp/claude-1000/-home-ubuntu/1bfeb871-95b6-4056-84c0-723093f0178d/scratchpad/tier6-brand/`

> `RequireAuth` 는 13행에 `// 테스트 빌드 임시 해제: 항상 통과` + `return children;` 가 있어
> **로그인 화면이 현재 앱에서 도달 불가능**하다. 캡처를 위해 잠깐 조건을 걸었다가
> **원상 복구했다** (`git diff` 로 확인 — 남은 변경은 로고 2줄뿐).

---

## index.html 에서 발견했지만 손대지 않은 것

| 발견 | 판단 |
|---|---|
| **`Outfit` 폰트가 죽은 로드다.** `frontend/src` 전체 참조 **0회** (Inter 64회 · Poppins 1회) | 지시대로 **미수정**. 폰트 검토가 끝난 뒤 정리할 것 |
| `Poppins` 는 참조가 딱 1곳 — `MainSidebar.css` 의 `.logo-container` 뿐인데 **700 굵기 하나 때문에 폰트 파일 하나를 통째로 받는다** | 폰트 결정 시 함께 판단 |
| 폰트 `<link>` 에 `preconnect` 가 없어 렌더 블로킹 | 성능 이슈, 이 배치 밖 |
| `<meta name="theme-color">` 없음 — 모바일 브라우저 주소창이 테마를 못 따라간다 | 요구 밖이라 미추가 |

## 남은 것

1. **`og:url` · `og:image` 를 절대 URL 로.** 배포 도메인을 몰라 루트 상대경로
   (`/og-image-1200x630.png`)로 뒀다. **Twitter/X 등 일부 크롤러는 절대 URL 을 요구한다.**
   도메인이 정해지면 `index.html` 의 `og:image` / `twitter:image` 를
   `https://<도메인>/og-image-1200x630.png` 로 바꾸고 `og:url` 을 추가할 것.
   (주석으로 표시해뒀다)
2. **[MainPage.jsx:415](../../../frontend/src/pages/MainPage.jsx#L415) 의 히어로 로고(80px)가
   아직 `logo.png` 다.** 미커밋 변경이 있는 금지 파일이라 손대지 않았다.
   이것 때문에 **114.7KB 짜리 `logo.png` 가 여전히 번들에 들어간다** (`dist/assets/logo-*.png`).
   그 파일 작업이 정리되면 `assets/brand/logo-mark-gradient.svg` 로 바꾸고
   `src/logo.png` 를 지우면 된다.
3. `logo-lockup.svg` — 폰트 확정 후.
4. `assets/icons/brand/` 빈 디렉터리 — 로더 사양(24 그리드)과 맞지 않아 쓰지 않았다.
   지우거나, 로더가 SVG 의 `viewBox` 를 그대로 읽도록 고치면 쓸 수 있다.
5. 빈 상태 일러스트 3종 (§4-3) · 인트로 히어로 (§4-4) — 별개 배치.

---
---

# 기존 로고로 되돌림 (2026-08-27)

## 사용자 결정

**위에서 선정한 새 로고(C1 W+A 모노그램)는 채택되지 않았다.**
사용자 사유: **"기본 로고가 이미 홍보용 자료에 적용돼서 바꾸기 어렵다."**

즉 위 §"로고 마크 — 후보 3개 비교와 선정" 은 **기각된 제안**이다.
브랜드 마크는 기존 `frontend/src/logo.png` (568×336 RGBA, 흰색 둥근 획 "WA" 워드마크) 로 유지한다.
이 결정에 따라 **새 로고 기준으로 만들어져 있던 파비콘·OG 를 WA 기준으로 전부 재생성**했다.

> 위 후보 비교 기록과 `frontend/src/assets/brand/` 의 SVG 자산은 **지우지 않았다.**
> 홍보물이 갱신되는 시점에 다시 검토할 수 있는 유효한 자산이다.

## 재생성한 자산 — `frontend/public/`

| 파일 | 크기 | 투명도 | 구성 |
|---|---|---|---|
| `favicon-32.png` | 2.1KB | 라운드 밖 투명 | `#0f172a` rx6 플레이트 + 흰 WA 전체, 여백 2px |
| `favicon-16.png` **(신규)** | 789B | 라운드 밖 투명 | 동일, rx3 · 여백 1.5px · 획 보존 0.5px |
| `apple-touch-icon-180.png` | 14.3KB | **불투명 RGB** | 라운드 없음(iOS 자체 스퀴클 마스킹) · 여백 18px |
| `og-image-1200x630.png` | 136KB | 불투명 RGB | 다크 슬레이트 + dot grid 6% + 노드 그래프 + 우 1/3 WA |

`favicon.svg` 는 **삭제했다** (아래 이유 참조). PNG 만 제공한다.

**모든 자산은 `logo.png` 를 그대로 스케일 합성한 것이다** — 재드로잉·벡터화·트레이스 없음.
리샘플링은 전부 `Image.LANCZOS`, 플레이트는 16배 슈퍼샘플로 그린 뒤 한 번만 축소한다.

### `favicon.svg` 를 삭제한 이유

기존 로고는 **PNG 래스터**다. SVG 파비콘을 유지하려면 WA 를 벡터로 트레이스해야 하는데,
트레이스는 곡률·획 끝단·광학 보정이 원본과 미묘하게 달라진다. 그건 **"로고를 바꾸지 말라"는
사용자 결정에 정면으로 위배**된다 — 홍보물의 WA 와 탭의 WA 가 다른 그림이 된다.

SVG 파비콘의 이점(무한 확대·다크모드 미디어쿼리)은 **32px 이하에서만 쓰이는 파비콘에서는
실익이 없다.** 그래서 SVG 를 버리고 PNG 2종(16·32)으로 갔다.
`index.html` 의 `favicon.svg` link 는 제거해야 한다 (아래 참조).

## 16px 가독성 판단 — **불가. 다만 전용 파일은 만들었다**

**결론: WA 워드마크는 16×16 에서 글자로 읽히지 않는다. 렌더로 확정했다.**

기하학적 이유가 명확하다. `logo.png` 의 유효 영역은 565×307 (**가로세로비 1.84:1**) 이고
획 굵기는 높이의 약 9% 다. 정사각형에 폭 기준으로 맞추면:

| | 로고 실크기 | 획 굵기 |
|---|---|---|
| 32px 아이콘 (여백 2) | 28 × 15.2 | **≈1.04px** |
| 16px 아이콘 (여백 1.5) | 13 × 7.1 | **≈0.48px** |

16px 에서 획이 0.5px 다. 게다가 WA 는 가로로 **획 경계가 8회 이상 교차**하는데
16px 안에 그걸 넣으면 교차당 2px 뿐이다. 카운터(W 획 사이 빈 공간, A 삼각형)가 먼저 무너진다.

실제로 **여백 4종 × 획보존 4종 = 16조합을 렌더**했고 (`04-16px-thick.png`, `11-16px-faithful.png`)
전부 회색 얼룩이었다. 여백을 줄이면 오히려 획이 겹쳐 더 지저분해진다 —
지시받은 예시("여백 축소")는 이 로고에서는 **역효과**다.

### 그래도 `favicon-16.png` 를 만든 이유

전용 16px 파일이 **없을 때보다 있을 때가 측정 가능하게 낫다.**
파일이 없으면 브라우저가 `favicon-32.png` 를 16px 로 재축소하는데,
그건 **이미 축소된 이미지를 또 축소**하는 것이라 더 흐리다.
전용 파일은 565px 원본에서 LANCZOS 로 **한 번만** 내려오고 획 보존까지 적용된다.
`13-shipped-tabs.png` 4번째 칸(브라우저 재축소)과 1번째 칸(전용 파일)을 비교하면 차이가 보인다.

즉 `favicon-16.png` 는 "글자가 읽히는 파비콘"이 아니라
**"다크 플레이트 위 밝은 워드마크 덩어리"로서 최선인 파비콘**이다. 브랜드 색 플레이트로 식별된다.

### 대안: 16px 만 W 로 크롭 — 렌더까지 해뒀으나 **채택하지 않았다**

로고 왼쪽 57% 만 크롭하면 가로세로비가 **1.05:1(거의 정사각)** 이 되어 글리프가
16px 안에서 2배 가까이 커지고, **16px 에서도 "W" 가 선명하게 읽힌다** (`10-16px-final.png` C칸).
가독성만 보면 압도적으로 낫다.

**그런데 채택하지 않았다.** 이유:

- 탭에 "W" 가 보이면 브랜드 마크가 "WA" 가 아니라 "W" 로 읽힌다. 크롭은 재드로잉이 아니지만
  **결과적으로 다른 마크**다. 사용자 결정("로고를 바꾸지 말라")의 취지에 어긋난다.
- 오케스트레이터가 든 단순화 예시가 "여백 축소" 였다 — **프레이밍 조정 범위**이고
  글자 구성을 바꾸는 건 그 범위를 넘는다.
- W 와 A 는 **획을 공유한다** (W 의 마지막 상승획 = A 의 왼쪽 다리, 컬럼 잉크 프로파일로 확인).
  그래서 어디를 잘라도 **평평한 절단면**이 남는다. 최소 잉크 지점(x=304~314)조차
  높이의 23% 가 잘린다.

대안 파일은 `favicon-wa/alt-favicon-16-wcrop.png` 에 남겼다. 사용자가 가독성을 택한다면:

```bash
cp <scratchpad>/favicon-wa/alt-favicon-16-wcrop.png frontend/public/favicon-16.png
```

## 렌더해보고 고친 것 (3건)

정적으로 잡힌 것은 이번에도 0건이다.

1. **OG 로고 글로가 배경보다 어두운 헤일로를 만들고 있었다 (실측 5,155픽셀).**
   `RGBA` 이미지를 그대로 `GaussianBlur` 하면 **알파=0 영역의 검정 RGB 가 같이 번진다**
   (비프리멀티플라이드 블러). 글로가 흰색이 아니라 탁한 회색이 되고, W 획 사이·A 카운터
   안쪽에 **회색 얼룩**이 끼어 획이 흐려 보였다 (`14-og-logo-zoom.png`).
   → **알파를 `L` 마스크로 뽑아 블러한 뒤 단색 레이어를 그 마스크로 합성.**
   노드/커넥터 글로도 같은 버그였어서 색상별 마스크 패스로 분리했다.
   수정 후 배경보다 어두운 픽셀 **0개** (`15-og-logo-zoom-fixed.png`).

2. **단순 LANCZOS 축소만 하면 32px 에서 흰 획이 회색으로 흐려졌다.**
   1px 획을 축소하면 부분 커버리지 때문에 픽셀이 50% 회색이 된다.
   → 슈퍼샘플 해상도에서 **알파를 `MaxFilter` 로 0.35px 만큼 팽창**시킨 뒤 축소하는
   **획 보존(스템 다크닝)** 단계를 넣었다. 폰트 래스터라이저가 하는 것과 같은 처리로,
   **형태·좌표는 그대로**다. 결과: 32px 획 최명 픽셀이 `#ffffff` (내부 대비 17.85:1).
   RGB 감마로 밝히는 방법도 시도했는데 **플레이트 색까지 밝아져서** 버렸다 (`03-enhance.png` 3행).

3. **OG 로고가 §4-2 의 80px safe margin 을 위반했다.**
   폭 300 을 x=1000 중심에 두니 우측 여백이 **50px** 이었다.
   → 폭 320, 중심 **x=960** (우 1/3 경계 800 에 좌변을 맞춤) → 여백 정확히 80px.
   실측 콘텐츠 bbox `(80, 115, 1120, 511)` — 좌 80 / 상 115 / 우 80 / 하 119. 전부 통과.

## 발견했지만 고치지 않은 것 — **`logo.png` 자체가 우측에서 잘려 있다**

`logo.png` 의 알파 bbox 가 `(3, 5, 568, 313)` 이다. **우변이 이미지 폭(568)에 닿아 있다** —
마지막 컬럼(x=567)에 알파>32 픽셀이 45개 있다. 즉 **A 의 오른쪽 획이 캔버스에서 잘렸다.**
`logo.png.orig` 백업에서도 동일하므로 **이번 얼룩 제거와 무관한 원본 결함**이다.

32px 파비콘에서는 안 보이지만 **OG 처럼 320px 로 키우면 평평한 절단면이 보인다**
(`15-og-logo-zoom-fixed.png` 우하단). 앱의 사이드바·히어로·로그인 화면도 같은 상태다.

**지시 범위 밖이라 손대지 않았다.** 마스터 로고 파일에서 우측 여백을 복원해 다시 내보내면
이 문서의 재생성 스니펫만 다시 돌려서 전 자산이 고쳐진다.

## 재생성 방법 — **이 스크립트가 유일한 소스다**

새 로고와 달리 **WA 자산에는 벡터 소스가 없다** (`logo.png` 가 래스터이고 트레이스를 금지했으므로).
따라서 아래 스크립트가 곧 소스다. `./backend/venv/bin/python` 으로 실행한다 (PIL 필요).

```python
# 사용법: cd /home/ubuntu/app && ./backend/venv/bin/python this.py
import os
from PIL import Image, ImageDraw, ImageFilter

APP, PUB = '/home/ubuntu/app', '/home/ubuntu/app/frontend/public'
PLATE, SS = (15, 23, 42, 255), 16          # #0f172a, 슈퍼샘플 배율
_R = {}

def logo():
    if 'r' not in _R:
        im = Image.open(os.path.join(APP, 'frontend/src/logo.png')).convert('RGBA')
        _R['r'] = im.crop(im.split()[-1].point(lambda v: 255 if v >= 8 else 0).getbbox())
    return _R['r']                          # 565x307

def icon(size, pad, radius, thick=0.35, opaque=False, ss=SS):
    """thick = 축소 시 획 보존량(대상 px). 형태는 안 바뀐다."""
    big = size * ss
    plate = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(plate)
    box = [0, 0, big - 1, big - 1]
    d.rectangle(box, fill=PLATE) if radius <= 0 else \
        d.rounded_rectangle(box, radius=radius * ss, fill=PLATE)
    lg = logo()
    avail = (size - 2 * pad) * ss
    s = min(avail / lg.width, avail / lg.height)
    tw, th = round(lg.width * s), round(lg.height * s)
    lg = lg.resize((tw, th), Image.LANCZOS)
    if thick > 0:                            # 획 보존(스템 다크닝)
        k = 2 * int(round(thick * ss / 2)) + 1
        lg = Image.merge('RGBA', lg.split()[:3] + (lg.split()[-1].filter(ImageFilter.MaxFilter(k)),))
    plate.alpha_composite(lg, (round((big - tw) / 2), round((big - th) / 2)))
    out = plate.resize((size, size), Image.LANCZOS)
    if opaque:                               # iOS 는 알파를 검게 합성한다
        bg = Image.new('RGBA', (size, size), PLATE); bg.alpha_composite(out); out = bg.convert('RGB')
    return out

def og():
    W, H, ss = 1200, 630, 2
    im = Image.new('RGB', (W * ss, H * ss), PLATE[:3])
    d = ImageDraw.Draw(im, 'RGBA')
    for y in range(0, H, 24):                # dot grid 6%
        for x in range(0, W, 24):
            cx, cy, r = (x + 2) * ss, (y + 2) * ss, 1.5 * ss
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 15))
    BLUE, VIOLET, EMERALD = (59, 130, 246), (139, 92, 246), (16, 185, 129)
    def bez(p0, p1, p2, p3, n=64):
        o = []
        for i in range(n + 1):
            t = i / n; u = 1 - t
            o.append((sum(c * k for c, k in zip((p0[0], p1[0], p2[0], p3[0]),
                      (u**3, 3*u*u*t, 3*u*t*t, t**3))) * ss,
                      sum(c * k for c, k in zip((p0[1], p1[1], p2[1], p3[1]),
                      (u**3, 3*u*u*t, 3*u*t*t, t**3))) * ss))
        return o
    CONN = [((230,315),(250,315),(250,155),(270,155),BLUE),
            ((230,315),(250,315),(250,470),(270,470),VIOLET),
            ((420,155),(440,155),(440,315),(460,315),BLUE),
            ((420,470),(440,470),(440,315),(460,315),BLUE),
            ((610,315),(630,315),(630,185),(650,185),EMERALD)]
    NODES = [((80,275),EMERALD),((270,115),BLUE),((270,430),VIOLET),
             ((460,275),BLUE),((650,145),EMERALD)]

    # soft glow — RGBA 를 직접 블러하면 알파=0 의 검정 RGB 가 섞여 어두운 헤일로가 생긴다.
    # 반드시 L 마스크를 블러하고 단색 레이어를 그 마스크로 합성할 것.
    for color in (BLUE, VIOLET, EMERALD):
        m = Image.new('L', im.size, 0); md = ImageDraw.Draw(m)
        for a, b, c, e, col in CONN:
            if col == color: md.line(bez(a, b, c, e), fill=255, width=5 * ss, joint='curve')
        for (nx, ny), col in NODES:
            if col == color:
                md.rounded_rectangle([nx*ss, ny*ss, (nx+150)*ss, (ny+80)*ss],
                                     radius=18*ss, outline=255, width=5*ss)
        if m.getbbox():
            m = m.filter(ImageFilter.GaussianBlur(7 * ss)).point(lambda v: int(v * 0.58))
            im = Image.composite(Image.new('RGB', im.size, color), im, m)
    d = ImageDraw.Draw(im, 'RGBA')
    for a, b, c, e, col in CONN:
        d.line(bez(a, b, c, e), fill=col + (217,), width=2 * ss, joint='curve')
    for (nx, ny), col in NODES:
        box = [nx*ss, ny*ss, (nx+150)*ss, (ny+80)*ss]
        d.rounded_rectangle(box, radius=18*ss, fill=col + (36,))
        d.rounded_rectangle(box, radius=18*ss, outline=col + (255,), width=2*ss)
        r, ccx, ccy = 7*ss, (nx+28)*ss, (ny+40)*ss
        d.ellipse([ccx-r, ccy-r, ccx+r, ccy+r], fill=col + (255,))
        d.rounded_rectangle([(nx+48)*ss,(ny+28)*ss,(nx+120)*ss,(ny+35)*ss], radius=3.5*ss,
                            fill=(226, 232, 240, 140))
        d.rounded_rectangle([(nx+48)*ss,(ny+45)*ss,(nx+94)*ss,(ny+52)*ss], radius=3.5*ss,
                            fill=(226, 232, 240, 71))
    # 우 1/3: WA 폭 320, 중심 (960, 308) → 좌 800 / 우 1120 = 80px safe margin
    lg = logo(); tw = 320 * ss; th = round(lg.height * tw / lg.width)
    lg = lg.resize((tw, th), Image.LANCZOS)
    lx, ly = round(960*ss - tw/2), round(308*ss - th/2)
    m = Image.new('L', im.size, 0); m.paste(lg.split()[-1], (lx, ly))
    m = m.filter(ImageFilter.GaussianBlur(18 * ss)).point(lambda v: int(v * 0.34))
    im = Image.composite(Image.new('RGB', im.size, (255, 255, 255)), im, m).convert('RGBA')
    im.alpha_composite(lg, (lx, ly))
    return im.convert('RGB').resize((W, H), Image.LANCZOS)

for name, im in [('favicon-32.png',           icon(32,  2,   6, 0.35)),
                 ('favicon-16.png',           icon(16,  1.5, 3, 0.5)),
                 ('apple-touch-icon-180.png', icon(180, 18,  0, 0.0, opaque=True)),
                 ('og-image-1200x630.png',    og())]:
    im.save(os.path.join(PUB, name), optimize=True); print(name)
```

## `index.html` 에 필요한 link 변경 (오케스트레이터 담당)

`favicon.svg` 가 없어졌고 `favicon-16.png` 가 생겼다. 11~13행을 아래로 교체할 것.

```html
<!-- 삭제 -->
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="alternate icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon-180.png" />

<!-- 교체 후 -->
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png" />
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon-180.png" />
```

`rel="alternate icon"` 은 `favicon.svg` 라는 **주(主) 아이콘이 있을 때만 의미가 있다.**
SVG 를 지웠으므로 둘 다 `rel="icon"` 으로 올리고 `sizes` 로 구분해야 한다.
그대로 두면 32px 이 "대체" 취급이라 브라우저가 무시할 수 있다.

OG/Twitter 메타는 파일명이 그대로이므로 **변경 없다.**

## 대비 실측 (WA 자산)

| | 값 |
|---|---|
| `favicon-32` 흰 획 최명 픽셀 `#ffffff` vs 플레이트 | **17.85:1** |
| `favicon-16` 획 최명 픽셀 `#e6e5e3` vs 플레이트 | **14.18:1** |
| 플레이트 `#0f172a` vs 라이트 탭바 `#ffffff` | **17.85:1** ✅ |
| 플레이트 `#0f172a` vs 다크 탭바 `#35363a` | 1.48 (플레이트는 녹지만 흰 획이 남는다) |

## 검증

| 항목 | 결과 |
|---|---|
| 여백 4종 × 32/16px 탐색 | `02-pad-explore.png` — 32px 통과, 16px 전멸 |
| 획 보존 방식 4종 비교 | `03-enhance.png` — MaxFilter 팽창 채택, RGB 감마 기각 |
| 16px 획보존 4종 × 여백 4종 | `04-16px-thick.png`, `11-16px-faithful.png` — 16조합 전부 불가 |
| W 크롭 비율 4종 | `05-wcrop.png`, `09-crop-frac.png` — 대안 확인용 |
| **실제 탭 맥락** (라이트/다크 탭바 × 16/32px 1:1) | `06-tabstrip.png`, `13-shipped-tabs.png` |
| 16px 최종 후보 4종 1:1 대조 | `10-16px-final.png` |
| apple-touch 여백 3종 + **iOS 스퀴클 마스크 시뮬레이션** | `12-apple-touch.png` — 여백 18 채택, 잘리는 요소 없음 |
| OG 로고 확대 (버그 전/후) | `14-og-logo-zoom.png` / `15-og-logo-zoom-fixed.png` |
| OG 소셜 카드 썸네일 크기 | `16-og-thumb.png` |
| 최종 컨택트 시트 | `17-contact-sheet.png` |
| `npx vite build` | ✅ 통과 (20.9s) |
| `dist/` 복사 | ✅ `favicon-16.png` `favicon-32.png` `apple-touch-icon-180.png` `og-image-1200x630.png` (`favicon.svg` 없음 확인) |

스크린샷: `/tmp/claude-1000/-home-ubuntu/1bfeb871-95b6-4056-84c0-723093f0178d/scratchpad/favicon-wa/`
