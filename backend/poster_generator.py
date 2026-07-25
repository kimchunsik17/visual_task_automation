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
import os
import re

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


def render_html_to_file(html: str, save_path: str, width: int = 900, height: int = 1200, fmt: str = "png") -> None:
    from playwright.sync_api import sync_playwright

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

    if "<head>" in html:
        html = html.replace("<head>", "<head>" + _BASE_STYLE, 1)
    else:
        html = _BASE_STYLE + html

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html)
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
