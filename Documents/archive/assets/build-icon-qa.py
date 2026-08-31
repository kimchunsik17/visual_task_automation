#!/usr/bin/env python3
"""
아이콘 QA 페이지 생성기.

  python3 Documents/build-icon-qa.py

frontend/src/assets/icons/**/*.svg 를 스캔해서 Documents/icon-qa.html 을 만든다.
SVG 소스를 HTML에 인라인하므로 file:// 로 그냥 열어도 동작한다 (CORS 없음).

검사 항목
  1) 광학 크기   — 기하 bbox 가 lucide 규약(2~22)에 맞는지, 브라우저 getBBox() 로 실측
  2) 가독성      — 16 / 18 / 24px 렌더를 다크·라이트 양쪽에서
  3) 색맹 대응    — 그레이스케일 렌더
  4) 형태 충돌    — 같은 배치 안에서 실루엣이 구분되는지 육안 비교
  5) 교체 전후    — 기존 lucide 아이콘과 나란히 (BEFORE 맵에 정의된 것만)

이 페이지는 눈으로 봐야 의미가 있다. B1~B6 에서 고친 문제 9건 중 정적 검사로 잡힌 것은
0건이고 전부 렌더해보고 발견했다(기어가 조타륜으로 읽힘, 반짝임이 + 로 읽힘, 책 3권이
막대그래프로 읽힘, 분배기가 웹훅의 거울상, …).

터미널에서 스크린샷을 뜨려면 백엔드 venv 의 playwright 를 쓴다 (이미 설치돼 있음):

    python3 Documents/build-icon-qa.py
    ./backend/venv/bin/python - <<'EOF'
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1480, 'height': 2400}, device_scale_factor=2)
        pg.goto('file:///home/ubuntu/app/Documents/icon-qa.html')
        pg.wait_for_timeout(1500)
        pg.locator('table').screenshot(path='/tmp/icon-qa.png')
        b.close()
    EOF

크롬이 없다고 하면 한 번만: ./backend/venv/bin/python -m playwright install chromium

실제 컴포넌트(Sidebar / MainSidebar / 캔버스 노드)를 띄워 확인하는 임시 하니스 예시는
Documents/icon-prompt-B6.md 의 "검증 결과" 항목에 적어뒀다. 프로바이더 스택이 필요하다.
"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "frontend" / "src" / "assets" / "icons"
OUT = Path(__file__).resolve().parent / "icon-qa.html"

# 노드별 색상 — frontend/src/Sidebar.jsx, nodeRegistry.js 와 동일하게 유지
COLORS = {
    "node-file-modifier": "#f43f5e",
    "node-template-analyzer": "#8b5cf6",
    "node-human-approval": "#f43f5e",
    "node-slack": "#0ea5e9",
    "node-payment-link": "#03c75a",
    "node-google-sheets": "#0f9d58",
    "node-google-calendar": "#4285f4",
    "node-poster-generator": "#f59e0b",
    "node-web-crawler": "#0ea5e9",
    "node-email": "#f43f5e",
    "node-kakao-alimtalk": "#facc15",
    "node-discord-send": "#5865F2",
    "node-telegram-send": "#26A5E4",
    "node-notion": "#9B9B9B",
    "node-toss-payments": "#3b82f6",
    "node-http-request": "#0ea5e9",
    "node-start": "#10b981",
    "node-schedule": "#8b5cf6",
    "node-output": "#f97316",
    "node-dynamic-input": "#d946ef",
    "node-webhook": "#0ea5e9",
    "node-discord-trigger": "#5865F2",
    "node-telegram-trigger": "#26A5E4",
    "node-value": "#ec4899",
    "node-prompt": "#3b82f6",
    "node-llm": "#8b5cf6",
    "node-multi-agent": "#6366f1",
    "node-condition": "#0ea5e9",
    "node-loop": "#ca8a04",
    "node-break": "#dc2626",
    "node-delay": "#3b82f6",
    "node-merge": "#ec4899",
    "node-python": "#eab308",
    "node-json-parser": "#eab308",
    "node-tokenizer": "#14b8a6",
    "node-distributor": "#6366f1",
    "node-database": "#059669",
    "nav-home": "#cbd5e1",
    "nav-workflows": "#cbd5e1",
    "nav-app-builder": "#cbd5e1",
    "nav-tutorial": "#cbd5e1",
    "nav-templates": "#cbd5e1",
    "nav-webhooks": "#cbd5e1",
    "nav-bots": "#cbd5e1",
    "nav-scheduler": "#cbd5e1",
    "nav-api-center": "#cbd5e1",
    "nav-statistics": "#cbd5e1",
    "nav-settings": "#cbd5e1",
    "nav-patch-notes": "#cbd5e1",
    "nav-intro": "#cbd5e1",
    "nav-admin": "#2ecc71",
    # B8 — 앱 빌더 팔레트 (AppBuilderPage.jsx). bp-* 만 팔레트에서 색 지정
    "ui-container": "#cbd5e1",
    "ui-text": "#cbd5e1",
    "ui-input": "#cbd5e1",
    "ui-textarea": "#cbd5e1",
    "ui-button": "#cbd5e1",
    "ui-image": "#cbd5e1",
    "ui-dropdown": "#cbd5e1",
    "ui-checkbox": "#cbd5e1",
    "ui-divider": "#cbd5e1",
    "ui-hierarchy": "#cbd5e1",
    "bp-event-trigger": "#ef4444",
    "bp-get-value": "#10b981",
    "bp-ui-action": "#3b82f6",
    "bp-workflow-execute": "#cbd5e1",
    # B9 — 실행 상태 (semantic color)
    "status-success": "#10b981",
    "status-failed": "#ef4444",
    "status-running": "#3b82f6",
    "status-pending": "#94a3b8",
    "status-warning": "#f59e0b",
    # B7 — 프로바이더 (컬러 SVG 자체 색 보유 → currentColor 영향 없음, 스와치 표기용)
    "provider-openai": "#10a37f",
    "provider-gemini": "#8b5cf6",
    "provider-kakao-rest": "#facc15",
    "provider-kakao-token": "#facc15",
    "provider-discord": "#5865F2",
    "provider-telegram": "#26A5E4",
    "provider-notion": "#191919",
    "provider-gmail-smtp": "#ea4335",
    "provider-toss": "#0064FF",
}

LABELS = {
    "node-file-modifier": "자동 완성",
    "node-template-analyzer": "템플릿 분석",
    "node-human-approval": "사용자 승인 (대기)",
    "node-slack": "Slack 메세지",
    "node-payment-link": "결제 링크 생성",
    "node-google-sheets": "구글 시트",
    "node-google-calendar": "구글 캘린더",
    "node-poster-generator": "포스터/이미지 생성",
    "node-web-crawler": "웹 크롤러",
    "node-email": "이메일 전송",
    "node-kakao-alimtalk": "카카오 알림톡",
    "node-discord-send": "디스코드 발송",
    "node-telegram-send": "텔레그램 발송",
    "node-notion": "Notion",
    "node-toss-payments": "토스페이먼츠",
    "node-http-request": "HTTP Request",
    "node-start": "시작",
    "node-schedule": "스케줄 (시작)",
    "node-output": "결과 출력",
    "node-dynamic-input": "동적 입력",
    "node-webhook": "웹훅 수신",
    "node-discord-trigger": "디스코드 봇 (시작)",
    "node-telegram-trigger": "텔레그램 봇 (시작)",
    "node-value": "변수 (값)",
    "node-prompt": "프롬프트",
    "node-llm": "LLM",
    "node-multi-agent": "Multi-Agent",
    "node-condition": "조건 분기",
    "node-loop": "반복 (Loop)",
    "node-break": "반복 종료",
    "node-delay": "Delay (대기)",
    "node-merge": "Merge (병합)",
    "node-python": "파이썬",
    "node-json-parser": "JSON 파서",
    "node-tokenizer": "토크나이저",
    "node-distributor": "분배기",
    "node-database": "데이터베이스",
    "nav-home": "홈",
    "nav-workflows": "내 워크플로우",
    "nav-app-builder": "앱 빌더 (AI)",
    "nav-tutorial": "튜토리얼",
    "nav-templates": "커뮤니티 템플릿",
    "nav-webhooks": "웹훅 관리",
    "nav-bots": "봇 관리",
    "nav-scheduler": "스케줄 관리",
    "nav-api-center": "API 센터",
    "nav-statistics": "통계",
    "nav-settings": "설정",
    "nav-patch-notes": "패치 노트",
    "nav-intro": "서비스 소개",
    "nav-admin": "어드민 패널",
    "ui-container": "Container (Div)",
    "ui-text": "Text",
    "ui-input": "Input Field",
    "ui-textarea": "Text Area",
    "ui-button": "Button",
    "ui-image": "Image",
    "ui-dropdown": "Dropdown",
    "ui-checkbox": "Checkbox",
    "ui-divider": "Divider",
    "ui-hierarchy": "Hierarchy",
    "bp-event-trigger": "Event Trigger",
    "bp-get-value": "Get Value",
    "bp-ui-action": "UI Action",
    "bp-workflow-execute": "Workflow Execute",
    "status-success": "성공",
    "status-failed": "실패",
    "status-running": "실행 중",
    "status-pending": "대기",
    "status-warning": "경고",
    "provider-openai": "OpenAI (ChatGPT)",
    "provider-gemini": "Google Gemini",
    "provider-kakao-rest": "Kakao REST API 키",
    "provider-kakao-token": "Kakao 메시지 토큰",
    "provider-discord": "Discord Bot Token",
    "provider-telegram": "Telegram Bot Token",
    "provider-notion": "Notion Token",
    "provider-gmail-smtp": "Gmail SMTP",
    "provider-toss": "토스페이먼츠 (신규)",
}

# 교체 대상 기존 lucide 아이콘 (lucide-react v0.300.0 원본 path)
LUCIDE_ATTRS = (
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"'
)
BEFORE = {
    "node-file-modifier": (
        "FileCode",
        '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>'
        '<polyline points="14 2 14 8 20 8"/><path d="m10 13-2 2 2 2"/><path d="m14 17 2-2-2-2"/>',
    ),
    "node-template-analyzer": (
        "FileCode (중복)",
        '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>'
        '<polyline points="14 2 14 8 20 8"/><path d="m10 13-2 2 2 2"/><path d="m14 17 2-2-2-2"/>',
    ),
    "node-human-approval": (
        "UserCheck",
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/>',
    ),
}
# B4 교체 대상 (lucide v0.300.0 원본)
BEFORE_B4 = {
    "node-web-crawler": ("Globe (3중 중복)",
        '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>'),
    "node-email": ("Mail",
        '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'),
    "node-kakao-alimtalk": ("MessageCircle (3중)",
        '<path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/>'),
    "node-discord-send": ("MessageCircle (3중)",
        '<path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/>'),
    "node-telegram-send": ("Send (2중)",
        '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>'),
    "node-notion": ("StickyNote",
        '<path d="M15.5 3H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h14a2 2 0 0 0 2-2V8.5L15.5 3Z"/>'
        '<path d="M15 3v6h6"/>'),
    "node-toss-payments": ("CreditCard",
        '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>'),
    "node-http-request": ("ArrowRightLeft (중복 없음)",
        '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>'),
}

PUZZLE = (
    "Puzzle (5종 공용)",
    '<path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 '
    "1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 "
    "0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705"
    ".707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02."
    "968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568"
    "A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.23 8.77c.24-.24.581-.353.917-.303.515.07"
    "7.877.528 1.073 1.01a2.5 2.5 0 1 0 3.259-3.259c-.482-.196-.933-.558-1.01-1.073-.05-.336.062-.676."
    "303-.917l1.525-1.525A2.402 2.402 0 0 1 12 1.998c.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556"
    '.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z"/>',
)
BEFORE.update(BEFORE_B4)
# B1/B2 교체 대상 (lucide v0.300.0 원본)
BEFORE_B12 = {
    "node-start": ("Play (실행버튼과 공용)", '<polygon points="5 3 19 12 5 21 5 3"/>'),
    "node-schedule": ("Clock (3중 중복)",
        '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "node-output": ("LogOut (2중)",
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>'),
    "node-dynamic-input": ("Keyboard",
        '<rect width="20" height="16" x="2" y="4" rx="2" ry="2"/><path d="M6 8h.001"/>'
        '<path d="M10 8h.001"/><path d="M14 8h.001"/><path d="M18 8h.001"/><path d="M8 12h.001"/>'
        '<path d="M12 12h.001"/><path d="M16 12h.001"/><path d="M7 16h10"/>'),
    "node-webhook": ("Globe (3중 중복)",
        '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>'),
    "node-discord-trigger": ("MessageCircle (3중)", '<path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/>'),
    "node-telegram-trigger": ("Send (2중)", '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>'),
    "node-value": ("Variable (중복 없음)",
        '<path d="M8 21s-4-3-4-9 4-9 4-9"/><path d="M16 3s4 3 4 9-4 9-4 9"/>'
        '<line x1="15" x2="9" y1="9" y2="9"/><line x1="15" x2="9" y1="15" y2="15"/>'),
    "node-prompt": ("MessageSquare",
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    "node-llm": ("BrainCircuit",
        '<path d="M12 4.5a2.5 2.5 0 0 0-4.96-.46 2.5 2.5 0 0 0-1.98 3 2.5 2.5 0 0 0-1.32 4.24 3 3 0 0 0 .34 5.58 2.5 2.5 0 0 0 2.96 3.08 2.5 2.5 0 0 0 4.91.05L12 20V4.5Z"/>'
        '<path d="M16 8V5c0-1.1.9-2 2-2"/><path d="M12 13h4"/><path d="M12 18h6a2 2 0 0 1 2 2v1"/>'
        '<path d="M12 8h8"/><path d="M20.5 8a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0Z"/>'
        '<path d="M16.5 13a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0Z"/><path d="M20.5 21a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0Z"/>'
        '<path d="M18.5 3a.5.5 0 1 1-1 0 .5.5 0 1 1 1 0Z"/>'),
    "node-multi-agent": ("Users",
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
    "node-condition": ("SplitSquareHorizontal",
        '<path d="M8 19H5c-1 0-2-1-2-2V7c0-1 1-2 2-2h3"/><path d="M16 5h3c1 0 2 1 2 2v10c0 1-1 2-2 2h-3"/>'
        '<line x1="12" x2="12" y1="4" y2="20"/>'),
    "node-loop": ("Repeat (중복 없음)",
        '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/>'
        '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>'),
    "node-break": ("LogOut 180도 회전 (2중)",
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>'),
    "node-delay": ("Clock (3중 중복)",
        '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "node-merge": ("Merge (중복 없음)",
        '<path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22"/><path d="m20 22-5-5"/>'),
}
BEFORE.update(BEFORE_B12)
# B3 교체 대상 (lucide v0.300.0 원본)

# B6 교체 대상 (lucide v0.300.0 원본)
BEFORE.update({
    "nav-home": ("Home", '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'),
    "nav-workflows": ("LayoutGrid",
        '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>'),
    "nav-app-builder": ("Wand2",
        '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72Z"/>'
        '<path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>'),
    "nav-tutorial": ("GraduationCap",
        '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>'),
    "nav-templates": ("LibraryBig",
        '<rect width="8" height="18" x="3" y="3" rx="1"/><path d="M7 3v18"/>'
        '<path d="M20.4 18.9c.2.5-.1 1.1-.6 1.3l-1.9.7c-.5.2-1.1-.1-1.3-.6L11.1 5.1c-.2-.5.1-1.1.6-1.3l1.9-.7c.5-.2 1.1.1 1.3.6Z"/>'),
    "nav-webhooks": ("Globe (3중 중복)",
        '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
    "nav-bots": ("Bot",
        '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/>'
        '<path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>'),
    "nav-scheduler": ("Clock (3중 중복)", '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "nav-api-center": ("Key",
        '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>'),
    "nav-statistics": ("BarChart",
        '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/>'),
    "nav-settings": ("Settings", '<circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/>'),
    "nav-patch-notes": ("ScrollText",
        '<path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v3h4"/>'
        '<path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M15 8h-5"/><path d="M15 12h-5"/>'),
    "nav-intro": ("Info", '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'),
    "nav-admin": ("Shield", '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'),
})
BEFORE.update({
    "node-python": ("Terminal", '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>'),
    "node-json-parser": ("Braces",
        '<path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1"/>'
        '<path d="M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"/>'),
    "node-tokenizer": ("Box (3중 중복)",
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
    "node-distributor": ("Network",
        '<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/>'
        '<rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>'
        '<path d="M12 12V8"/>'),
    "node-database": ("Database (2중 중복)",
        '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/>'
        '<path d="M3 12A9 3 0 0 0 21 12"/>'),
})
# B8 교체 대상 — AppBuilderPage.jsx 팔레트 (lucide v0.300.0 원본)
BEFORE.update({
    "ui-container": ("Box (3중 중복)",
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
    "ui-text": ("Type",
        '<polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/>'
        '<line x1="12" x2="12" y1="4" y2="20"/>'),
    "ui-input": ("TextCursorInput (2중)",
        '<path d="M5 4h1a3 3 0 0 1 3 3 3 3 0 0 1 3-3h1"/><path d="M13 20h-1a3 3 0 0 1-3-3 3 3 0 0 1-3 3H5"/>'
        '<path d="M5 16H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h1"/><path d="M13 8h7a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-7"/>'
        '<path d="M9 7v10"/>'),
    "ui-textarea": ("TextCursorInput (2중)",
        '<path d="M5 4h1a3 3 0 0 1 3 3 3 3 0 0 1 3-3h1"/><path d="M13 20h-1a3 3 0 0 1-3-3 3 3 0 0 1-3 3H5"/>'
        '<path d="M5 16H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h1"/><path d="M13 8h7a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-7"/>'
        '<path d="M9 7v10"/>'),
    "ui-button": ("MousePointerClick",
        '<path d="m9 9 5 12 1.8-5.2L21 14Z"/><path d="M7.2 2.2 8 5.1"/><path d="m5.1 8-2.9-.8"/>'
        '<path d="M14 4.1 12 6"/><path d="m6 12-1.9 2"/>'),
    "ui-image": ("Image",
        '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/>'
        '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'),
    "ui-dropdown": ("List",
        '<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/>'
        '<line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/>'
        '<line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>'),
    "ui-checkbox": ("CheckSquare",
        '<path d="m9 11 3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'),
    "ui-divider": ("Minus", '<path d="M5 12h14"/>'),
    "ui-hierarchy": ("Layers",
        '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>'
        '<path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>'),
    "bp-event-trigger": ("Play (실행버튼과 공용)", '<polygon points="5 3 19 12 5 21 5 3"/>'),
    "bp-get-value": ("Database (2중 중복)",
        '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/>'
        '<path d="M3 12A9 3 0 0 0 21 12"/>'),
    "bp-ui-action": ("ArrowRight", '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>'),
    "bp-workflow-execute": ("Sparkles (AI 버튼과 공용)",
        '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>'
        '<path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>'),
})
# B9 교체 대상 — 실행 상태 (lucide v0.300.0 원본)
BEFORE.update({
    "status-success": ("CheckCircle2", '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
    "status-failed": ("XCircle", '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>'),
    "status-running": ("Activity", '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>'),
    "status-pending": ("Clock (다중)",
        '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    "status-warning": ("AlertTriangle",
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'),
})
# B7 교체 대상 — ApiCenterPage.jsx 이모지 (SVG text 로 근사 렌더)
_EMOJI = lambda ch: (f"이모지 {ch}",
    f'<text x="12" y="17.5" font-size="14" text-anchor="middle" stroke="none" fill="currentColor">{ch}</text>')
BEFORE.update({
    "provider-openai": _EMOJI("🤖"),
    "provider-gemini": _EMOJI("✨"),
    "provider-kakao-rest": _EMOJI("💬"),
    "provider-kakao-token": _EMOJI("🔑"),
    "provider-discord": _EMOJI("🎮"),
    "provider-telegram": _EMOJI("✈️"),
    "provider-notion": _EMOJI("📝"),
    "provider-gmail-smtp": _EMOJI("📧"),
})


for _k in ("node-slack", "node-payment-link", "node-google-sheets",
           "node-google-calendar", "node-poster-generator"):
    BEFORE[_k] = PUZZLE


def inner(svg_text: str) -> str:
    """<svg> 래퍼를 벗기고 내부 도형만 반환."""
    body = re.sub(r"^.*?<svg[^>]*>", "", svg_text, flags=re.S)
    return re.sub(r"</svg>\s*$", "", body).strip()


def shape_count(body: str) -> int:
    return len(re.findall(r"<(path|circle|rect|line|polyline|polygon|ellipse)\b", body))


def main() -> int:
    icons = sorted(ICON_DIR.rglob("*.svg"), key=lambda p: (p.parent.name, p.name))
    if not icons:
        print(f"아이콘이 없습니다: {ICON_DIR}")
        return 1

    rows, cards = [], []
    for p in icons:
        stem = p.stem
        body = inner(p.read_text(encoding="utf-8"))
        color = COLORS.get(stem, "#3b82f6")
        label = LABELS.get(stem, stem)
        size_kb = p.stat().st_size / 1024
        n = shape_count(body)
        before = BEFORE.get(stem)

        before_cell = (
            f'<div class="cmp"><svg {LUCIDE_ATTRS} width="24" height="24">{before[1]}</svg>'
            f'<em>{html.escape(before[0])}</em></div>'
            if before else '<div class="cmp"><em>—</em></div>'
        )

        rows.append(f"""
    <tr data-name="{stem}">
      <td class="meta">
        <b>{html.escape(label)}</b>
        <code>{stem}.svg</code>
        <span class="tags">
          <i class="sw" style="background:{color}"></i>{color}
          · 도형 {n}개
          · {size_kb:.2f}KB
        </span>
      </td>
      <td>{before_cell}</td>
      <td class="on-dark">
        <span style="color:{color}"><svg class="probe" {LUCIDE_ATTRS} width="16" height="16">{body}</svg></span>
        <span style="color:{color}"><svg {LUCIDE_ATTRS} width="18" height="18">{body}</svg></span>
        <span style="color:{color}"><svg {LUCIDE_ATTRS} width="24" height="24">{body}</svg></span>
      </td>
      <td class="on-light">
        <span style="color:{color}"><svg {LUCIDE_ATTRS} width="16" height="16">{body}</svg></span>
        <span style="color:{color}"><svg {LUCIDE_ATTRS} width="18" height="18">{body}</svg></span>
        <span style="color:{color}"><svg {LUCIDE_ATTRS} width="24" height="24">{body}</svg></span>
      </td>
      <td class="on-dark gray">
        <span><svg {LUCIDE_ATTRS} width="16" height="16">{body}</svg></span>
        <span><svg {LUCIDE_ATTRS} width="24" height="24">{body}</svg></span>
      </td>
      <td class="bbox">측정 중…</td>
    </tr>""")

        cards.append(f"""
    <figure>
      <div class="grid-wrap">
        <svg viewBox="0 0 24 24" width="168" height="168" class="guides">
          <rect x="0" y="0" width="24" height="24" fill="none" stroke="#ef4444" stroke-width=".15"/>
          <rect x="2" y="2" width="20" height="20" fill="none" stroke="#22c55e"
                stroke-width=".15" stroke-dasharray=".6 .6"/>
          <g stroke="#64748b" stroke-width=".05" opacity=".55">
            {''.join(f'<path d="M{i} 0v24"/><path d="M0 {i}h24"/>' for i in range(2, 23, 2))}
          </g>
        </svg>
        <svg {LUCIDE_ATTRS} width="168" height="168" style="color:{color}">{body}</svg>
      </div>
      <figcaption>{html.escape(label)}<br><code>{stem}</code></figcaption>
    </figure>""")

    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>아이콘 QA — {len(icons)}개</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; padding:32px; background:#0f172a; color:#f8fafc;
         font:14px/1.6 Inter,-apple-system,'Noto Sans KR',sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:15px; margin:40px 0 12px; color:#94a3b8;
        border-top:1px solid #334155; padding-top:20px; }}
  .lede {{ color:#94a3b8; margin:0 0 24px; }}
  table {{ border-collapse:collapse; width:100%; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.08em;
        color:#64748b; padding:8px 12px; border-bottom:1px solid #334155; font-weight:600; }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b; vertical-align:middle; }}
  .meta b {{ display:block; }}
  .meta code {{ font-size:11px; color:#64748b; }}
  .tags {{ display:block; font-size:11px; color:#64748b; margin-top:2px; }}
  .sw {{ display:inline-block; width:9px; height:9px; border-radius:2px;
         margin-right:5px; vertical-align:-1px; }}
  td.on-dark, td.on-light {{ white-space:nowrap; }}
  td.on-dark span, td.on-light span, .cmp {{
      display:inline-flex; align-items:center; justify-content:center;
      width:40px; height:40px; border-radius:8px; }}
  td.on-dark span {{ background:#1e293b; }}
  td.on-light span {{ background:#f1f5f9; }}
  td.gray span {{ filter:grayscale(1); color:#94a3b8; }}
  .cmp {{ flex-direction:column; gap:2px; width:auto; min-width:56px;
          height:auto; padding:6px; background:#1e293b; color:#64748b; }}
  .cmp em {{ font-size:9px; font-style:normal; }}
  td.bbox {{ font-size:11px; font-family:ui-monospace,monospace; white-space:pre-line; }}
  .ok {{ color:#22c55e; }} .warn {{ color:#f59e0b; }} .bad {{ color:#ef4444; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:20px; }}
  figure {{ margin:0; }}
  .grid-wrap {{ position:relative; width:168px; height:168px;
                background:#111c33; border-radius:10px; }}
  .grid-wrap svg {{ position:absolute; inset:0; }}
  figcaption {{ font-size:11px; color:#94a3b8; margin-top:8px; text-align:center; }}
  figcaption code {{ color:#64748b; font-size:10px; }}
  .legend {{ font-size:11px; color:#64748b; margin:8px 0 16px; }}
  .legend i {{ display:inline-block; width:18px; height:0; border-top:2px solid;
               margin:0 4px 0 12px; vertical-align:3px; }}
</style>

<h1>아이콘 QA — {len(icons)}개</h1>
<p class="lede">
  <code>Documents/build-icon-qa.py</code> 로 생성. 새 SVG를 추가하면 다시 실행하세요.
  광학 크기는 브라우저 <code>getBBox()</code> 실측값입니다.
</p>

<h2>1. 크기별 · 테마별 · 그레이스케일 렌더</h2>
<table>
  <thead><tr>
    <th style="width:230px">아이콘</th><th style="width:70px">BEFORE</th>
    <th>다크 16·18·24</th><th>라이트 16·18·24</th>
    <th>그레이스케일</th><th style="width:190px">기하 bbox</th>
  </tr></thead>
  <tbody>{''.join(rows)}
  </tbody>
</table>

<h2>2. 기하 검사 — 24×24 그리드 위 168px 확대</h2>
<p class="legend">
  <i style="color:#ef4444"></i>viewBox 경계 (0~24)
  <i style="color:#22c55e"></i>lucide 규약 영역 (2~22)
  <i style="color:#64748b"></i>2px 그리드
</p>
<div class="cards">{''.join(cards)}</div>

<script>
// 기하 bbox 실측 — lucide 규약은 2~22. 획 외곽(±1)은 1~23 까지 허용.
for (const tr of document.querySelectorAll('tr[data-name]')) {{
  const svg = tr.querySelector('svg.probe');
  const cell = tr.querySelector('td.bbox');
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const el of svg.children) {{
    let b; try {{ b = el.getBBox(); }} catch (e) {{ continue; }}
    if (!b || (b.width === 0 && b.height === 0 && !el.getAttribute('d'))) continue;
    x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
  }}
  if (!isFinite(x0)) {{ cell.textContent = '측정 실패'; continue; }}
  const w = x1 - x0, h = y1 - y0, span = Math.max(w, h);
  const r = n => Math.round(n * 10) / 10;
  // 판정: 최대 변이 18 미만이면 주변 lucide 아이콘보다 작아 보인다
  let cls = 'ok', note = '광학 크기 일치';
  if (x0 < 1 || y0 < 1 || x1 > 23 || y1 > 23) {{ cls = 'bad'; note = '획이 캔버스를 넘음'; }}
  else if (span < 18) {{ cls = 'warn'; note = `최대 변 ${{r(span)}} < 18 — lucide보다 작음`; }}
  cell.innerHTML = `x ${{r(x0)}}–${{r(x1)}}  (${{r(w)}})\\n`
                 + `y ${{r(y0)}}–${{r(y1)}}  (${{r(h)}})\\n`
                 + `<span class="${{cls}}">${{note}}</span>`;
}}
</script>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"생성: {OUT}  (아이콘 {len(icons)}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
