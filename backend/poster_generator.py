"""
poster_generator.py — posterGeneratorNode가 쓰는, LLM이 만든 HTML+CSS를 실제
포스터 이미지(PNG)나 PDF로 렌더링하는 모듈.

배경: 포스터/전단지처럼 자유로운 디자인(그라데이션, 둥근 배지, 커스텀 레이아웃)은 PyMuPDF의
fitz.Story 같은 경량 HTML 렌더러로는 대부분 무시되거나 깨진다(배경/크기/스타일이 거의 안 먹힘,
실제로 테스트해서 확인함). 반면 Playwright로 실제 Chromium을 띄워 렌더링하면 일반 브라우저와
동일한 품질로 나온다 — 이 서버에는 이미 프론트엔드 테스트용으로 Playwright의 Chromium 바이너리가
설치돼 있어(~/.cache/ms-playwright) 추가 다운로드 없이 재사용한다.

생성형 이미지 API(DALL-E 등)로 직접 포스터를 그리는 대안도 있지만, 그런 모델은 텍스트(특히
한글)를 정확히 그리지 못하는 경우가 잦고 건당 비용도 든다. 반면 이 방식은 이미 쓰고 있는 텍스트
LLM 호출 하나로 HTML을 만들게 하는 것뿐이라 텍스트가 항상 정확하고 추가 비용이 없다.
"""
import base64
import os
import re
from functools import lru_cache
from pathlib import Path

# LLM이 <style>에 폰트나 box-sizing을 깜빡 빠뜨려도 최소한의 품질(가독성 좋은 한/영 폰트,
# padding이 크기에 더해져 레이아웃이 깨지는 일 방지)은 보장하기 위한 기본값. <head> 맨 앞에
# 넣어서 LLM이 만든 <style>이 항상 이걸 덮어쓸 수 있게 한다(우선순위상 나중에 나온 규칙이 이김).
_BASE_STYLE = """<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif;
  -webkit-font-smoothing: antialiased;
}
</style>"""


_POSTER_BACKGROUND_DIR = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "assets"
    / "editorial"
    / "poster-backgrounds"
)

_POSTER_BACKGROUND_FILES = {
    "poster-01-midnight-grid": "poster-01-midnight-grid.png",
    "poster-02-cobalt-orbits": "poster-02-cobalt-orbits.png",
    "poster-03-violet-arches": "poster-03-violet-arches.png",
    "poster-04-emerald-flow": "poster-04-emerald-flow.png",
    "poster-05-layered-paper": "poster-05-layered-paper.png",
    "poster-06-dot-matrix": "poster-06-dot-matrix.png",
    "poster-07-blueprint-lines": "poster-07-blueprint-lines.png",
    "poster-08-diagonal-blocks": "poster-08-diagonal-blocks.png",
    "poster-09-emerald-wave": "poster-09-emerald-wave.png",
    "poster-10-neutral-editorial": "poster-10-neutral-editorial.png",
    "poster-11-concentric-frames": "poster-11-concentric-frames.png",
    "poster-12-sparse-geometry": "poster-12-sparse-geometry.png",
}


@lru_cache(maxsize=len(_POSTER_BACKGROUND_FILES))
def _poster_background_style(preset: str) -> str:
    """선택된 내장 배경을 data URI로 만들어 Chromium 렌더링에 주입한다.

    사용자 입력을 파일 경로로 직접 쓰지 않고 고정 매핑만 허용해 상위 경로 접근을 막는다.
    data URI를 쓰므로 page.set_content()의 about:blank 문서에서도 로컬 파일 권한 문제 없이
    동일하게 렌더링된다.
    """
    filename = _POSTER_BACKGROUND_FILES.get(preset)
    if not filename:
        return ""

    asset_path = _POSTER_BACKGROUND_DIR / filename
    if not asset_path.is_file():
        raise FileNotFoundError(f"포스터 배경 자산을 찾을 수 없습니다: {filename}")

    encoded = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    return f"""<style id="nodi-poster-background">
html, body {{ min-height: 100%; background-color: transparent !important; }}
body {{
  background-image: url("data:image/png;base64,{encoded}") !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-size: cover !important;
}}
</style>"""


# ── P0 렌더링 격리 (INCOMPLETE_NODE_STRUCTURE_REVIEW §4.5) ──────────────
# 이 HTML은 LLM이 만든 문자열이고, 서버 안의 실제 Chromium에서 열린다. 격리 없이 열면
# LLM 출력(또는 프롬프트 주입으로 유도된 출력)에 섞인 script/iframe/외부 요청이 서버측
# 브라우저에서 실행된다. 세 겹으로 막는다: ① 위험 태그 제거(아래), ② JavaScript 비활성화,
# ③ 모든 네트워크 요청 차단(내장 배경은 data URI라 영향 없음 — 외부 폰트/이미지는 어차피
# 렌더 결과의 재현성을 해치므로 기본 폰트 스택으로 대체된다).
# 짝이 맞는 컨테이너(내용 포함) → 남은 여는/자기닫는 태그 → 고아 닫는 태그 순서로 지운다.
# 한 패턴으로 합치면 lazy 매칭이 여는 태그의 '>'에서 멈춰 내용이 남는다.
_DANGEROUS_PAIRED_RE = re.compile(
    r"<\s*(script|iframe|object|embed|form)\b[^>]*>[\s\S]*?<\s*/\s*\1\s*>", re.IGNORECASE,
)
_DANGEROUS_OPEN_RE = re.compile(r"<\s*(script|iframe|object|embed|base|form)\b[^>]*/?>", re.IGNORECASE)
_DANGEROUS_CLOSE_RE = re.compile(r"<\s*/\s*(script|iframe|object|embed|base|form)\s*>", re.IGNORECASE)
_EVENT_HANDLER_ATTR_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)

# 렌더링 크기 상한: 상한 없이는 한 번의 실행이 Chromium에 수억 픽셀 렌더링을 요청할 수 있다.
MIN_DIMENSION = 100
MAX_DIMENSION = 4000
RENDER_TIMEOUT_MS = 15_000


def sanitize_poster_html(html: str) -> str:
    """script/iframe/object/embed/base/form 태그와 인라인 이벤트 핸들러를 제거한다.
    JS 비활성화·네트워크 차단이 있어도 벨트와 멜빵으로 원문에서 지운다."""
    cleaned = _DANGEROUS_PAIRED_RE.sub("", html or "")
    cleaned = _DANGEROUS_OPEN_RE.sub("", cleaned)
    cleaned = _DANGEROUS_CLOSE_RE.sub("", cleaned)
    return _EVENT_HANDLER_ATTR_RE.sub("", cleaned)


def clamp_poster_dimensions(width, height) -> tuple:
    """width/height를 안전 범위로 고정한다. 값이 없거나 숫자가 아니면 기본값을 쓴다."""
    def _clamp(value, default):
        try:
            return max(MIN_DIMENSION, min(int(value), MAX_DIMENSION))
        except (TypeError, ValueError):
            return default
    return _clamp(width, 900), _clamp(height, 1200)


def render_html_to_file(
    html: str,
    save_path: str,
    width: int = 900,
    height: int = 1200,
    fmt: str = "png",
    background_preset: str = "none",
) -> None:
    from playwright.sync_api import sync_playwright

    width, height = clamp_poster_dimensions(width, height)

    html = (html or "").strip()
    # LLM이 "출력은 HTML만 허용한다" 같은 지시를 받고도, 특히 "스스로 점검하고 수정해라" 식의
    # 자가검토 단계에서는 코드 앞뒤에 설명 문구("최종 HTML은 ... 조건을 모두 만족합니다" 등)를
    # 덧붙이는 경우가 실제로 있었다(그 설명 텍스트가 그대로 포스터 위에 렌더링되는 문제로 이어짐).
    # 코드펜스 하나로 깔끔하게 감싼 경우만 처리하는 정규식은 이런 경우를 못 잡으므로, 응답 어디에
    # 있든 <html>...</html> 블록 자체를 찾아 그것만 쓴다 — 앞뒤에 뭐가 더 있어도 무시된다.
    html_tag_match = re.search(r"<html[\s\S]*?</html>", html, re.IGNORECASE)
    if html_tag_match:
        html = html_tag_match.group(0)
    else:
        fence_match = re.match(r"^```(?:html)?\s*\n?(.*?)\n?```$", html, re.DOTALL)
        if fence_match:
            html = fence_match.group(1).strip()
    if not html:
        raise ValueError("렌더링할 HTML 내용이 비어 있습니다.")

    html = sanitize_poster_html(html)

    if "<head>" in html:
        html = html.replace("<head>", "<head>" + _BASE_STYLE, 1)
    else:
        html = _BASE_STYLE + html

    background_style = _poster_background_style(background_preset)
    if background_style:
        head_close = re.search(r"</head\s*>", html, re.IGNORECASE)
        if head_close:
            html = html[:head_close.start()] + background_style + html[head_close.start():]
        else:
            html = background_style + html

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # JS 비활성화 + 전 네트워크 차단: 포스터는 정적 HTML/CSS 렌더링이라 어느 쪽도
            # 필요 없고, LLM이 만든 HTML을 서버 브라우저에서 여는 경로의 P0 격리 조건이다.
            page = browser.new_page(
                viewport={"width": width, "height": height},
                java_script_enabled=False,
            )
            page.set_default_timeout(RENDER_TIMEOUT_MS)
            page.route("**/*", lambda route: route.abort())
            page.set_content(html, timeout=RENDER_TIMEOUT_MS)
            if fmt == "pdf":
                # 기본 여백(약 0.4in)이 있으면 콘텐츠 영역이 지정한 width/height보다 작아져서
                # 포스터 내용이 흘러넘쳐 불필요한 2페이지가 생긴다(실제로 겪음) — 여백을 0으로 없앤다.
                page.pdf(
                    path=save_path, width=f"{width}px", height=f"{height}px",
                    print_background=True,
                    margin={"top": "0px", "bottom": "0px", "left": "0px", "right": "0px"},
                )
            else:
                page.screenshot(path=save_path, full_page=False)
        finally:
            browser.close()
