# -*- coding: utf-8 -*-
"""seed_demo_booth.py — 부스 시연 콘텐츠 시딩 (시연 종합보고서 §4).

시연 계정에 "생활 밀착 자동화"를 보여주는 워크플로우 5개 + 앱 빌더 앱 2개 +
전용 문서 포맷 2개를 심는다. 코드가 아니라 **데이터**라서 시연 브랜치를 따지 않는다 —
이 스크립트는 멱등(제목 기준 upsert)이라 몇 번을 돌려도 안전하고, 시연 후에도 무해하다.

사용:
    venv\\Scripts\\python seed_demo_booth.py --email booth@example.com
    venv\\Scripts\\python seed_demo_booth.py --user-id 3

시딩 전 모든 워크플로우를 dry_run 으로 검증한다 — 하나라도 실패하면 아무것도 쓰지 않는다.

콘텐츠 목록 (2026-09-04 교체 — 이전 세트는 "[시연-보관]" 으로 개명된다):
  포맷   demo-travel-itinerary     여행 일정표 (document)
  포맷   demo-notice-poster        안내 포스터 (design — 생성 배경 이미지 슬롯)
  WF1    핫딜 키워드 알림 → 이메일            httpRequestNode ×2 병렬(뽐뿌·어미새 RSS, UA 헤더) + llmNode + emailNode
  WF2    유튜브 채널 최신 영상 요약 → 이메일    httpRequestNode(Data API 키·공개 RSS) + emailNode
  WF3    회사 분석 → 입사지원서(Word)          httpRequestNode + formatNode(job-application, docx) + emailNode
  WF4    여행지 → 여행 일정표                  naverSearchNode ×2 병렬 + formatNode(docx) + emailNode
  WF5    공고문 → 안내 포스터                  llmNode + formatNode(디자인, PNG) + emailNode
  APP1   여행 플래너            (WF4 연결 — 층 1 QR 체험용)
  APP2   입사 지원서 도우미      (WF3 연결 — 층 1 QR 체험용)

주의(시연 계정 운영 준비):
  - WF1 은 트리거가 아니라 방문자가 적은 키워드로 *현재* 뽐뿌 핫딜 RSS 를 골라 보낸다(2026-09-06 재설계).
    rssTriggerNode 는 첫 실행에 기준점만 잡아 빈 결과를 내고(트리거의 올바른 동작), 루리웹은 이 서버에서
    응답이 없어 매번 타임아웃이 났다. 뽐뿌는 기본 UA 를 403 으로 막으므로 HTTP 노드에 브라우저형 UA 헤더를
    명시한다(rss.py 의 RSS_USER_AGENT 와 같은 값). 아카라이브는 Cloudflare 차단으로 여전히 제외.
  - WF2 는 API 센터의 YouTube Data API 키(youtube_data_api)를 쓴다 — 게스트에게 공유하려면 .env 의
    DEMO_SHARED_CREDENTIALS_PROVIDERS 에 youtube_data_api 를 넣는다(공개 데이터 키라 공유해도 된다).
    구글 OAuth 는 더 이상 필요 없다. 검색은 하루 할당량 10,000 단위 중 100 을 쓴다(핸들 입력은 1).
  - WF5 는 이미지 생성 단계를 뺐다(2026-09-08, 시연 기간 안에 이미지 API 를 쓸 수 없어서). 배경 없는 디자인 포맷
    (어두운 그라데이션 + 문안)으로 PNG 를 만든다. imageGenerationNode 는 HIDDEN_NODE_TYPES 로 팔레트에서도 숨긴다.
  - 이메일 발송은 서비스 SMTP 설정을 따른다. 수신자는 {{USER_EMAIL}} 자리표시자 — 발송 직전 실행
    계정(게스트가 입장 뒤 등록한 이메일)으로 풀린다. 결과 문서는 부스 노트북에 한/글이 없을 수
    있어 Word(DOCX) 로 만든다(2026-09-05 결정).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# 포맷 id 는 소유자별로 나눈다 — DocumentFormat.id 가 PK 이고 formatNode 는 소유자 검증을
# 하므로, 게스트 입장(DEMO_GUEST)처럼 여러 계정에 같은 콘텐츠를 심으면 계정마다 자기
# 포맷 행이 필요하다. 워크플로우의 formatId 도 같은 규칙으로 만들어 참조가 맞는다.
TRAVEL_FORMAT_BASE = "demo-travel-itinerary"
POSTER_FORMAT_BASE = "demo-notice-poster"
TITLE_PREFIX = "[시연] "
# 이메일 노드의 수신자. 게스트의 실제 이메일은 입장 뒤 최초 1회 등록되므로 시딩 때는 알 수 없다 —
# 발송 직전 delivery_runtime.resolve_recipient 가 프로젝트 소유자의 이메일로 푼다(관리자 계정도 같다).
USER_EMAIL_PLACEHOLDER = "{{USER_EMAIL}}"


def format_ids_for(user_id: int) -> dict:
    return {TRAVEL_FORMAT_BASE: f"{TRAVEL_FORMAT_BASE}-u{int(user_id)}",
            POSTER_FORMAT_BASE: f"{POSTER_FORMAT_BASE}-u{int(user_id)}"}

PPOMPPU_HOTDEAL_RSS = "https://www.ppomppu.co.kr/rss.php?id=ppomppu"
# 2026-09-06 서버 실측: 클리앙·에펨코리아 404, 퀘이사존 403, 쿨엔조이·루리웹 무응답, 딜바다 RSS 금지 — 받아지는 것은
# 뽐뿌와 어미새(인기정보) 둘이다.
EOMISAE_HOTDEAL_RSS = "https://eomisae.co.kr/rss?mid=fs"
# 뽐뿌는 python-requests 기본 UA 를 403 으로 막는다 — 트리거(rss.py)와 같은 브라우저형 UA 를 HTTP 노드 헤더에 명시
from connectors.services.rss import RSS_USER_AGENT  # noqa: E402
HOTDEAL_KEYWORD = "아이폰"


# ── 그래프 조립 헬퍼 (official_templates/_lib 과 같은 문법, id 는 안정적으로 지정) ──

def N(node_id: str, node_type: str, **data):
    return {"id": node_id, "type": node_type, "data": data, "position": None}


def link(a, b, source_handle=None):
    return {"id": f"e-{a['id']}-{b['id']}-{source_handle or ''}", "source": a["id"],
            "target": b["id"], "sourceHandle": source_handle, "targetHandle": None}


# ── 전용 문서 포맷 1: 여행 일정표 (document) ─────────────────────────────

TRAVEL_ITINERARY_SPEC = {
    "version": 1,
    "name": "여행 일정표",
    "description": "네이버 검색 결과를 바탕으로 관광·먹거리를 정리한 여행 일정 문서",
    "layout": "document",
    "output": {"default": "hwpx", "allowed": ["hwpx", "docx", "pdf"]},
    "fields": [
        {"name": "tripTitle", "label": "일정표 제목", "kind": "text", "required": True,
         "example": "전주 1박 2일 여행 일정"},
        {"name": "destination", "label": "여행지", "kind": "text", "required": True,
         "example": "전주"},
        {"name": "period", "label": "기간", "kind": "text", "required": True,
         "example": "1박 2일"},
        {"name": "planDate", "label": "작성일", "kind": "text", "required": True,
         "example": "2026년 9월 10일"},
        {"name": "days", "label": "일정표", "kind": "rows",
         "columns": ["일정", "오전", "오후", "저녁·먹거리"], "required": True},
        {"name": "foods", "label": "추천 먹거리", "kind": "rows",
         "columns": ["이름", "위치/특징", "추천 이유"], "required": True},
        {"name": "tips", "label": "여행 팁", "kind": "multiline", "required": False,
         "example": "주말에는 한옥마을 주차장이 일찍 찹니다."},
    ],
    "blocks": [
        {"type": "heading", "level": 1, "text": "{{tripTitle}}"},
        {"type": "table", "columns": ["항목", "내용"],
         "rows": [["여행지", "{{destination}}"], ["기간", "{{period}}"], ["작성일", "{{planDate}}"]]},
        {"type": "heading", "level": 2, "text": "1. 일정"},
        {"type": "table", "fromField": "days"},
        {"type": "heading", "level": 2, "text": "2. 추천 먹거리"},
        {"type": "table", "fromField": "foods"},
        {"type": "heading", "level": 2, "text": "3. 여행 팁"},
        {"type": "paragraph", "text": "{{tips}}"},
        {"type": "paragraph", "text": "본 일정은 네이버 검색 결과를 바탕으로 자동 생성되었습니다."},
    ],
}

# ── 전용 문서 포맷 2: 안내 포스터 (design — 풀블리드 배경 이미지 슬롯) ────
#
# backgroundImage 는 이미지 생성 노드가 만든 배경이 들어가는 슬롯이다. 값이 파일
# 경로(uploads/…)여도 formatNode 런타임이 같은 소유자의 등록된 artifact 로 역조회해
# 연결한다(documents/format_runtime._resolve_image_values). 이미지가 없으면(생성 실패
# 등) 테마 배경색 위에 텍스트만으로도 완성된 포스터가 나온다 — 슬롯은 필수가 아니다.

POSTER_CSS = (
    ".cv{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;"
    "background:var(--fs-backgroundColor);color:var(--fs-textColor);}\n"
    ".cv .e{position:absolute;box-sizing:border-box;margin:0;white-space:pre-wrap;word-break:keep-all;}\n"
    ".cv .e1{left:0;top:0;width:794px;height:1123px;object-fit:cover;}\n"
    ".cv .e2{left:0;top:0;width:794px;height:1123px;"
    "background:linear-gradient(180deg,rgba(10,14,26,.18) 0%,rgba(10,14,26,.52) 52%,rgba(10,14,26,.9) 100%);}\n"
    ".cv .e3{left:64px;top:552px;width:666px;height:176px;font-size:56px;font-weight:800;"
    "text-align:left;color:var(--fs-textColor);line-height:1.18;}\n"
    ".cv .e4{left:64px;top:738px;width:666px;height:42px;font-size:24px;font-weight:700;"
    "text-align:left;color:var(--fs-primaryColor);line-height:1.4;}\n"
    ".cv .e5{left:64px;top:796px;width:666px;height:150px;font-size:17px;font-weight:400;"
    "text-align:left;color:var(--fs-mutedColor);line-height:1.65;}\n"
    ".cv .e6{left:64px;top:962px;width:666px;height:34px;font-size:20px;font-weight:700;"
    "text-align:left;color:var(--fs-textColor);line-height:1.4;}\n"
    ".cv .e7{left:64px;top:1006px;width:666px;height:34px;font-size:20px;font-weight:700;"
    "text-align:left;color:var(--fs-textColor);line-height:1.4;}\n"
    ".cv .e8{left:64px;top:1062px;width:666px;height:32px;font-size:14px;font-weight:400;"
    "text-align:left;color:var(--fs-mutedColor);line-height:1.4;}"
)

NOTICE_POSTER_SPEC = {
    "version": 1,
    "name": "안내 포스터",
    "description": "공고문을 정리해 만드는 세로 안내 포스터 — 배경은 이미지 생성 노드가 채운다",
    "layout": "design",
    "output": {"default": "png", "allowed": ["png", "pdf"]},
    "fields": [
        {"name": "posterTitle", "label": "제목", "kind": "text", "required": True,
         "example": "제10회 부산 청년 창업 공모전"},
        {"name": "tagline", "label": "부제", "kind": "text", "required": False,
         "example": "당신의 아이디어가 부산을 바꿉니다"},
        {"name": "bodyText", "label": "본문(대상·혜택 등)", "kind": "multiline", "required": True},
        {"name": "dateLine", "label": "일시/기간", "kind": "text", "required": True,
         "example": "접수 9월 15일(화) ~ 10월 2일(금)"},
        {"name": "placeLine", "label": "장소/방법", "kind": "text", "required": True,
         "example": "부산창업카페 2호점(서면)"},
        {"name": "contactLine", "label": "문의", "kind": "text", "required": False,
         "example": "051-000-0000 · startup@busan.go.kr"},
        {"name": "backgroundImage", "label": "배경 이미지", "kind": "image", "required": False},
    ],
    "design": {
        "width": 794,
        "height": 1123,
        "theme": {"primaryColor": "#ffd166", "backgroundColor": "#101623",
                  "textColor": "#f8fafc", "mutedColor": "#cbd5e1", "fontFamily": "Pretendard"},
        "elements": [
            {"id": "bg", "kind": "image", "field": "backgroundImage", "x": 0, "y": 0, "w": 794, "h": 1123},
            {"id": "scrim", "kind": "text", "text": "", "x": 0, "y": 0, "w": 794, "h": 1123, "fontSize": 1},
            {"id": "title", "kind": "text", "bold": True, "align": "left", "color": "textColor",
             "lineHeight": 1.18, "text": "{{posterTitle}}", "x": 64, "y": 552, "w": 666, "h": 176, "fontSize": 56},
            {"id": "tagline", "kind": "text", "bold": True, "align": "left", "color": "primaryColor",
             "lineHeight": 1.4, "text": "{{tagline}}", "x": 64, "y": 738, "w": 666, "h": 42, "fontSize": 24},
            {"id": "body", "kind": "text", "align": "left", "color": "mutedColor",
             "lineHeight": 1.65, "text": "{{bodyText}}", "x": 64, "y": 796, "w": 666, "h": 150, "fontSize": 17},
            {"id": "meta1", "kind": "text", "bold": True, "align": "left", "color": "textColor",
             "lineHeight": 1.4, "text": "일시  {{dateLine}}", "x": 64, "y": 962, "w": 666, "h": 34, "fontSize": 20},
            {"id": "meta2", "kind": "text", "bold": True, "align": "left", "color": "textColor",
             "lineHeight": 1.4, "text": "장소  {{placeLine}}", "x": 64, "y": 1006, "w": 666, "h": 34, "fontSize": 20},
            {"id": "contact", "kind": "text", "align": "left", "color": "mutedColor",
             "lineHeight": 1.4, "text": "{{contactLine}}", "x": 64, "y": 1062, "w": 666, "h": 32, "fontSize": 14},
        ],
        "html": ("<div class=\"cv\"><img data-field=\"backgroundImage\" class=\"e e1\">"
                 "<div class=\"e e2\"></div>"
                 "<div class=\"e e3\">{{posterTitle}}</div>"
                 "<div class=\"e e4\">{{tagline}}</div>"
                 "<div class=\"e e5\">{{bodyText}}</div>"
                 "<div class=\"e e6\">일시  {{dateLine}}</div>"
                 "<div class=\"e e7\">장소  {{placeLine}}</div>"
                 "<div class=\"e e8\">{{contactLine}}</div></div>"),
        "css": POSTER_CSS,
    },
}

FORMAT_SPECS = {TRAVEL_FORMAT_BASE: TRAVEL_ITINERARY_SPEC, POSTER_FORMAT_BASE: NOTICE_POSTER_SPEC}


# ── LLM 구조화 출력 스키마 ───────────────────────────────────────────────

JOB_APPLICATION_SCHEMA = json.dumps({
    "title": "JobApplication",
    "type": "object",
    "properties": {
        "applicantName": {"type": "string", "description": "지원자 성명 (프로필의 이름)"},
        "position": {"type": "string", "description": "지원 직무 — 회사 사업에 맞는 직무명"},
        "contact": {"type": "string", "description": "연락처 (프로필의 전화번호)"},
        "email": {"type": "string", "description": "이메일 (프로필의 이메일)"},
        "education": {"type": "array", "description": "학력 사항, 각 행은 [기간, 학교/전공, 졸업 여부]",
                      "items": {"type": "array", "items": {"type": "string"}}},
        "career": {"type": "array", "description": "경력 사항, 각 행은 [기간, 회사/직무, 주요 성과]",
                   "items": {"type": "array", "items": {"type": "string"}}},
        "certificates": {"type": "array", "description": "자격·어학, 각 행은 [취득일, 자격/시험명, 발급 기관·점수]",
                         "items": {"type": "array", "items": {"type": "string"}}},
        "introduction": {"type": "string", "description": "자기소개 4~6문장 — 프로필 경험을 회사 인재상·문화와 연결"},
        "motivation": {"type": "string", "description": "지원 동기 4~6문장 — 회사 분석 내용(사업·가치)을 구체적으로 인용"},
        "appliedAt": {"type": "string", "description": "오늘 날짜를 한국어로 (예: 2026년 9월 10일)"},
    },
    "required": ["applicantName", "position", "contact", "email", "education",
                 "career", "certificates", "introduction", "motivation", "appliedAt"],
}, ensure_ascii=False)

TRAVEL_SCHEMA = json.dumps({
    "title": "TravelItinerary",
    "type": "object",
    "properties": {
        "tripTitle": {"type": "string", "description": "일정표 제목 (예: 전주 1박 2일 여행 일정)"},
        "destination": {"type": "string", "description": "여행지 이름"},
        "period": {"type": "string", "description": "기간 (예: 1박 2일)"},
        "planDate": {"type": "string", "description": "오늘 날짜를 한국어로"},
        "days": {"type": "array", "description": "일정, 각 행은 [일정(1일차 등), 오전, 오후, 저녁·먹거리] — 1박 2일 기준 2행",
                 "items": {"type": "array", "items": {"type": "string"}}},
        "foods": {"type": "array", "description": "추천 먹거리 3~5건, 각 행은 [이름, 위치/특징, 추천 이유]",
                  "items": {"type": "array", "items": {"type": "string"}}},
        "tips": {"type": "string", "description": "여행 팁 2~3문장"},
    },
    "required": ["tripTitle", "destination", "period", "planDate", "days", "foods", "tips"],
}, ensure_ascii=False)

POSTER_FIELDS = {
    "posterTitle": {"type": "string", "description": "포스터 제목 — 공고문의 행사/공고 이름"},
    "tagline": {"type": "string", "description": "부제 한 줄 — 공고 내용에서 뽑은 핵심 문구, 마땅치 않으면 빈 문자열"},
    "bodyText": {"type": "string", "description": "본문 3~4줄 — 대상·혜택·핵심 정보를 줄바꿈으로 구분해 빠짐없이"},
    "dateLine": {"type": "string", "description": "일시/기간 값만 한 줄, 30자 이내 — '접수 기간:' 같은 라벨은 넣지 않는다(포스터가 '일시' 라벨을 따로 찍는다). 기간과 발표일이 둘이면 접수 기간만"},
    "placeLine": {"type": "string", "description": "장소명만 한 줄, 25자 이내 — '장소:' 라벨은 넣지 않는다(포스터가 '장소' 라벨을 따로 찍는다)"},
    "contactLine": {"type": "string", "description": "문의처 한 줄, 없으면 빈 문자열"},
}

POSTER_SCHEMA = json.dumps({
    "title": "NoticePoster",
    "type": "object",
    "properties": POSTER_FIELDS,
    "required": ["posterTitle", "bodyText", "dateLine", "placeLine"],
}, ensure_ascii=False)

# ── 워크플로우 5종 ───────────────────────────────────────────────────────

def build_workflows(owner_email: str, travel_format_id: str = TRAVEL_FORMAT_BASE,
                    poster_format_id: str = POSTER_FORMAT_BASE):
    """제목 → (설명, nodes, edges). 노드 id 는 앱 payload 키로도 쓰이므로 바꾸지 말 것."""
    flows = {}

    # WF1 — 핫딜 키워드 알림 → 이메일 (키워드 입력 → 뽐뿌·어미새 RSS 병렬 수집 → 합치기 → 골라내기 → 분기 → 발송)
    # 2026-09-06 재설계: 예전 RSS 트리거 시작은 첫 실행에 기준점만 잡아 "[]" 를 냈고(트리거로서는 맞는 동작),
    # 루리웹 병렬 수집은 이 서버에서 응답이 없어 매번 15초×재시도 타임아웃이 났다(부스 점검 실측 50초).
    # 방문자가 관심 키워드를 적으면 지금 올라와 있는 핫딜에서 골라 바로 보낸다 — 키워드 글이 없으면 빈손 대신
    # 최신 5개를 보낸다(막다른 분기 없음). 뽐뿌는 기본 UA 를 403 으로 막아 브라우저형 UA 헤더를 명시한다.
    n_start = N("start1", "startNode")
    n_in = N("in_keyword", "dynamicInputNode", inputLabel="관심 키워드 (예: 아이폰, 에어팟, 라면)",
             testValue=HOTDEAL_KEYWORD)
    n_fetch = N("fetch_ppomppu", "httpRequestNode", method="GET", url=PPOMPPU_HOTDEAL_RSS,
                headers={"User-Agent": RSS_USER_AGENT})
    n_fetch2 = N("fetch_eomisae", "httpRequestNode", method="GET", url=EOMISAE_HOTDEAL_RSS,
                 headers={"User-Agent": RSS_USER_AGENT})
    n_join = N("merge_deal_input", "mergeNode")
    # 한쪽 커뮤니티만 실패해도 나머지로 정리하도록 실패 판정은 LLM 출력에서 한다 — 수집 결과에 조건을 걸면
    # 한 목록의 오류 문구 때문에 다른 목록까지 버려진다.
    n_pick = N("pick_llm", "llmNode", model="gpt-5.4-mini",
               systemPrompt=("입력에는 관심 키워드 한 줄과 두 커뮤니티의 핫딜 RSS(XML) — 뽐뿌, 어미새 — 가 함께 있다. "
                             "제목에 키워드(띄어쓰기·대소문자 무시, 흔한 표기 변형 포함)가 든 글을 골라 각 건을 '· [뽐뿌] 제목' "
                             "또는 '· [어미새] 제목' 한 줄과 '  링크' 한 줄로 정리한다. 첫 줄은 '🛒 <키워드> 핫딜 알림' 으로 "
                             "시작한다. 키워드 글이 하나도 없으면 첫 줄 다음에 '해당 키워드 글이 아직 없어 최신 핫딜을 대신 "
                             "보냅니다' 라고 쓰고 두 커뮤니티 *각각* 에서 최신 3개씩을 같은 형식으로 정리한다(한 커뮤니티만 "
                             "쓰지 않는다). 링크는 XML 엔티티를 풀어 쓴다 — &amp; 는 & 로(그대로 두면 잘못된 글로 연결된다). "
                             "어느 한 목록이 'HTTP Request "
                             "Error' 로 시작하는 오류 문구면 그 커뮤니티는 건너뛴다. 두 목록이 모두 오류면 다른 말 없이 정확히 "
                             "'핫딜 목록을 가져오지 못했습니다 — 잠시 후 다시 시도해 주세요.' 한 줄만 출력한다. 목록에 없는 글을 "
                             "지어내지 않고, 링크는 입력의 link 값을 그대로 쓴다."))
    n_cond = N("cond_result", "conditionNode",
               rules=[{"id": "failed", "operator": "Contains", "value": "가져오지 못했습니다"}])
    n_fail = N("fetch_fail_msg", "valueNode",
               value="핫딜 목록을 가져오지 못했습니다 — 잠시 후 다시 시도해 주세요.")
    n_mail = N("alert_mail", "emailNode", toEmail=owner_email, subject="[핫딜] 관심 키워드 알림")
    n_merge = N("merge1", "mergeNode")
    n_out = N("out1", "outputNode")
    nodes = [n_start, n_in, n_fetch, n_fetch2, n_join, n_pick, n_cond, n_fail, n_mail, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_join), link(n_in, n_fetch), link(n_in, n_fetch2),
             link(n_fetch, n_join), link(n_fetch2, n_join), link(n_join, n_pick), link(n_pick, n_cond),
             link(n_cond, n_fail, source_handle="failed"),
             link(n_cond, n_mail, source_handle="else"),
             link(n_mail, n_merge), link(n_fail, n_merge), link(n_merge, n_out)]
    flows["핫딜 키워드 알림 → 이메일"] = (
        "관심 키워드를 넣으면 뽐뿌·어미새 핫딜에 지금 올라온 글을 병렬로 모아 그 키워드가 든 글의 제목과 링크를 "
        "골라 이메일로 보냅니다. 해당 글이 없으면 최신 핫딜 5개를 대신 보내고, 목록을 못 가져오면 분기해 안내합니다 — "
        "입력 → 병렬 수집 → 병합 → 골라내기 → 분기 → 발송의 완결 흐름.", nodes, edges)

    # WF2 — 유튜브 채널 최신 영상 요약 → 이메일 (채널 입력 → 채널 ID 조회 → 분기 → 공개 RSS → 요약 → 발송)
    # 2026-09-05 재설계: 예전 EBS *트리거* 는 (1) 계정별 구글 OAuth 가 필요해 게스트가 쓸 수 없고,
    # (2) "마지막 실행 이후 새 영상" 만 알려 첫 실행이 늘 빈손이었다. 방문자가 채널을 적으면 그 채널의
    # 최신 영상을 바로 요약한다. 채널 ID 조회는 YouTube Data API **키**(공개 데이터, 공유 자격증명
    # youtube_data_api — 헤더 X-Goog-Api-Key 로 실림)로, 영상 목록은 인증이 필요 없는 공개 RSS 로 가져온다.
    n_start = N("start2", "startNode")
    n_in = N("in_channel", "dynamicInputNode", inputLabel="유튜브 채널 (이름, @핸들, 또는 채널 주소)",
             testValue="@EBSCulture")
    n_q = N("channel_query_llm", "llmNode", model="gpt-5.4-mini",
            systemPrompt=("입력은 유튜브 채널을 가리키는 글이다(채널 이름, @핸들, 또는 youtube.com 주소). "
                          "YouTube Data API v3 요청 URL 한 줄만 출력한다.\n"
                          "- 입력에 @핸들이 있거나 주소가 youtube.com/@… 형태면: "
                          "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&forHandle=<핸들(@ 제외)>\n"
                          "- 주소가 youtube.com/channel/UC… 형태면: "
                          "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&id=<UC로 시작하는 채널 ID>\n"
                          "- 그 외(채널 이름)는: "
                          "https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&maxResults=1&q=<이름을 URL 인코딩>\n"
                          "설명·따옴표·코드블록 없이 URL 만 출력한다."))
    n_lookup = N("lookup_channel", "httpRequestNode", method="GET", url="",
                 headers={"X-Goog-Api-Key": "{{API_CENTER:youtube_data_api}}"},
                 bindings={"url": {"source": "channel_query_llm"}})
    n_feed_url = N("feed_url_llm", "llmNode", model="gpt-5.4-mini",
                   systemPrompt=("입력은 YouTube Data API 의 channels 또는 search 응답(JSON)이다. 첫 항목의 채널 ID"
                                 "(channels 응답은 items[0].id, search 응답은 items[0].snippet.channelId 또는 "
                                 "items[0].id.channelId)를 찾아 "
                                 "https://www.youtube.com/feeds/videos.xml?channel_id=<채널 ID> 한 줄만 출력한다. "
                                 "items 가 비어 있거나 오류 응답이면 정확히 NOT_FOUND 만 출력한다."))
    n_cond = N("cond_channel", "conditionNode",
               rules=[{"id": "missing", "operator": "Contains", "value": "NOT_FOUND"}])
    n_fail = N("channel_fail_msg", "valueNode",
               value="채널을 찾지 못했습니다 — 채널 이름이나 @핸들, 채널 주소를 다시 확인해 주세요.")
    n_feed = N("fetch_feed", "httpRequestNode", method="GET", url="",
               bindings={"url": {"source": "feed_url_llm"}})
    n_sum = N("sum_llm", "llmNode", model="gpt-5.4-mini",
              systemPrompt=("입력은 유튜브 채널의 최신 영상 RSS(XML)다. 첫 줄은 '📺 <채널명> 최신 영상 브리핑' 으로 "
                            "시작한다. 게시일이 최신인 영상 5개까지, 영상마다 '🎬 제목', '  · 게시: YYYY-MM-DD', "
                            "'  · 내용: 제목과 설명(media:description)에 근거해 2~3문장', '  · 링크' 순으로 정리한다. "
                            "설명에 없는 내용을 추측하지 않는다."))
    n_mail = N("channel_mail", "emailNode", toEmail=owner_email, subject="[유튜브] 채널 최신 영상 브리핑")
    n_merge = N("merge2", "mergeNode")
    n_out = N("out2", "outputNode")
    nodes = [n_start, n_in, n_q, n_lookup, n_feed_url, n_cond, n_fail, n_feed, n_sum, n_mail, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_q), link(n_q, n_lookup), link(n_lookup, n_feed_url),
             link(n_feed_url, n_cond),
             link(n_cond, n_fail, source_handle="missing"),
             link(n_cond, n_feed, source_handle="else"),
             link(n_feed, n_sum), link(n_sum, n_mail), link(n_mail, n_merge), link(n_fail, n_merge),
             link(n_merge, n_out)]
    flows["유튜브 채널 최신 영상 요약 → 이메일"] = (
        "유튜브 채널 이름이나 @핸들, 주소를 넣으면 채널을 찾아 최신 영상 5개를 제목·설명에 근거해 요약하고 "
        "이메일로 보냅니다. 채널을 못 찾으면 분기해 안내합니다 — 입력 → 조회 → 분기 → 수집 → 요약 → 발송의 "
        "완결 흐름. (수신 주소는 입장 시 등록한 이메일)", nodes, edges)

    # WF3 — 회사 분석 → 입사지원서 (URL 입력 → 사이트 수집 → 분석 → 프로필 결합 → Word → 이메일)
    n_start = N("start3", "startNode")
    n_in = N("in_url", "dynamicInputNode", inputLabel="회사 홈페이지 주소", testValue="https://toss.im")
    n_url = N("url_llm", "llmNode", model="gpt-5.4-mini",
              systemPrompt="입력에서 회사 홈페이지 URL 을 찾아 URL 한 줄만 출력한다. 설명·따옴표 없이 URL 만.")
    n_fetch = N("fetch_site", "httpRequestNode", method="GET", url="",
                bindings={"url": {"source": "url_llm"}})
    n_cond = N("cond_site", "conditionNode",
               rules=[{"id": "ok", "operator": "Contains", "value": "<"}])
    n_fail = N("fail_msg", "valueNode",
               value="회사 사이트에 접속하지 못했습니다 — 주소를 확인하거나 잠시 후 다시 시도해 주세요.")
    n_analyze = N("analyze_llm", "llmNode", model="gpt-5.4-mini",
                  systemPrompt=("입력은 회사 웹사이트의 HTML 이다. 태그를 무시하고 (1) 회사명, (2) 주요 사업·제품, "
                                "(3) 고객/시장, (4) 회사가 강조하는 가치·문화(인재상)를 한국어로 정리한다. "
                                "페이지에 근거가 없는 항목은 일반적으로 알려진 정보로 보충하되 '(일반 정보)' 로 표시한다."))
    n_fill = N("fill_llm", "llmNode", model="gpt-5.4-mini",
               systemPrompt=("입력은 회사 분석이다. 아래 지원자 프로필과 회사 분석을 결합해 입사지원서 빈칸을 채운다. "
                             "introduction(자기소개)과 motivation(지원 동기)은 회사의 사업·가치를 구체적으로 "
                             "인용해 맞춤으로 쓴다. position 은 회사 사업과 프로필에 맞는 직무로 정한다. "
                             "appliedAt 은 오늘 날짜를 한국어로 쓴다.\n\n"
                             "[지원자 프로필 — 미리 입력된 정보]\n"
                             "이름: 김워크 / 연락처: 010-1234-5678 / 이메일: kim.work@example.com\n"
                             "학력: 2018.03~2024.02 부산대학교 정보컴퓨터공학부 졸업\n"
                             "경력: 2024.03~현재 스타트업 '플로우랩' 백엔드 개발자 — FastAPI 기반 자동화 "
                             "서비스 개발, 결제·알림 연동 3종 출시, 월간 실행 10만 건 처리\n"
                             "자격·어학: 2023.08 정보처리기사(한국산업인력공단) / 2023.11 TOEIC 905\n"
                             "강점: Python·FastAPI·PostgreSQL, 외부 API 연동 자동화 설계"),
               useStructuredOutput=True, jsonSchema=JOB_APPLICATION_SCHEMA)
    n_doc = N("app_doc", "formatNode", formatId="job-application", output="docx")
    n_mail = N("app_mail", "emailNode", toEmail=owner_email, subject="[입사지원서] 회사 맞춤 입사지원서(Word) 생성 완료")
    n_merge = N("merge3", "mergeNode")
    n_out = N("out3", "outputNode")
    nodes = [n_start, n_in, n_url, n_fetch, n_cond, n_fail, n_analyze, n_fill, n_doc, n_mail, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_url), link(n_url, n_fetch), link(n_fetch, n_cond),
             link(n_cond, n_analyze, source_handle="ok"),
             link(n_cond, n_fail, source_handle="else"),
             link(n_analyze, n_fill), link(n_fill, n_doc), link(n_doc, n_mail),
             link(n_mail, n_merge), link(n_fail, n_merge), link(n_merge, n_out)]
    flows["회사 분석 → 입사지원서(Word)"] = (
        "회사 홈페이지 주소를 넣으면 사이트를 수집·분석하고, 미리 입력해 둔 지원자 프로필과 결합해 "
        "회사 맞춤 입사지원서를 Word(DOCX) 문서로 만들어 이메일로 보냅니다. 접속 실패 시 분기해 안내합니다 — "
        "입력 → 수집 → 분기 → 분석 → 결합 → 문서화 → 발송의 완결 흐름.", nodes, edges)

    # WF4 — 여행지 → 여행 일정표 (관광지·맛집 병렬 검색 → 합치기 → 일정 작성 → Word → 이메일)
    n_start = N("start4", "startNode")
    n_in = N("in_place", "dynamicInputNode", inputLabel="여행지", testValue="전주")
    n_q1 = N("q_tour_llm", "llmNode", model="gpt-5.4-mini",
             systemPrompt="입력의 여행지로 '<여행지> 가볼만한 곳' 형태의 네이버 검색어를 만든다. 검색어 한 줄만 출력한다.")
    n_s1 = N("search_tour", "naverSearchNode", mode="blog", query="", display=8, sort="sim")
    n_q2 = N("q_food_llm", "llmNode", model="gpt-5.4-mini",
             systemPrompt="입력의 여행지로 '<여행지> 맛집' 형태의 네이버 검색어를 만든다. 검색어 한 줄만 출력한다.")
    n_s2 = N("search_food", "naverSearchNode", mode="blog", query="", display=8, sort="sim")
    n_info = N("merge_info", "mergeNode")
    # 검색 자격증명이 없거나 조회가 실패하면 커넥터가 '[⚠️ …]' 문구를 남긴다 — 그대로 LLM 에 넘기면
    # 검색 결과 없이 일정을 지어낸다(실측: 전주를 묻자 '서울' 일정을 만들었다). 분기해서 안내한다.
    n_cond = N("cond_info", "conditionNode",
               rules=[{"id": "failed", "operator": "Contains", "value": "⚠️"}])
    n_fail = N("search_fail_msg", "valueNode",
               value="여행지 검색에 실패해 일정을 만들지 못했습니다 — API 센터의 네이버 검색 연동을 확인해 주세요.")
    n_plan = N("plan_llm", "llmNode", model="gpt-5.4-mini",
               systemPrompt=("입력은 여행지의 관광지 검색 결과와 맛집 검색 결과다. 검색 결과에 실제로 언급된 "
                             "장소·가게만 사용해 1박 2일 일정을 만든다. days 는 [1일차, 오전, 오후, 저녁·먹거리] "
                             "와 [2일차, …] 2행으로, 동선이 자연스럽게 이어지게 짠다. foods 는 검색 결과에서 "
                             "3~5곳을 고른다. 검색 결과에 없는 곳을 지어내지 않는다. planDate 는 오늘 날짜를 "
                             "한국어로 쓴다."),
               useStructuredOutput=True, jsonSchema=TRAVEL_SCHEMA)
    n_doc = N("plan_doc", "formatNode", formatId=travel_format_id, output="docx")
    n_mail = N("plan_mail", "emailNode", toEmail=owner_email, subject="[여행 일정표] 1박 2일 일정표(Word) 생성 완료")
    n_merge = N("merge4", "mergeNode")
    n_out = N("out4", "outputNode")
    nodes = [n_start, n_in, n_q1, n_s1, n_q2, n_s2, n_info, n_cond, n_fail, n_plan, n_doc, n_mail, n_merge, n_out]
    edges = [link(n_start, n_in), link(n_in, n_q1), link(n_in, n_q2),
             link(n_q1, n_s1), link(n_q2, n_s2),
             link(n_s1, n_info), link(n_s2, n_info), link(n_info, n_cond),
             link(n_cond, n_fail, source_handle="failed"),
             link(n_cond, n_plan, source_handle="else"),
             link(n_plan, n_doc), link(n_doc, n_mail), link(n_mail, n_merge), link(n_fail, n_merge),
             link(n_merge, n_out)]
    flows["여행지 → 여행 일정표"] = (
        "여행지를 넣으면 관광지와 맛집을 네이버에서 병렬로 검색해 모으고, 실제 검색 결과만으로 1박 2일 "
        "일정과 먹거리 목록을 짜서 여행 일정표 Word(DOCX) 문서로 만들어 이메일로 보냅니다. 검색이 실패하면 "
        "분기해 안내합니다 — 입력 → 병렬 수집 → 병합 → 분기 → 일정 작성 → 문서화 → 발송. (층 1 QR 체험용)", nodes, edges)

    # WF5 — 공고문 → 안내 포스터 (문안 정리 → 디자인 포맷 PNG → 발송)
    # 2026-09-08: 배경 이미지 생성 단계(bg_prompt_llm ∥ imageGenerationNode → 병합 → 조립)를 뺐다 — 시연 기간 안에
    # 이미지 API 를 쓸 수 없다. 포스터 포맷의 backgroundImage 는 선택 필드라 문안 JSON 을 그대로 넣으면
    # 어두운 그라데이션 배경 위에 문안만 놓인 PNG 가 나온다(실측 확인). 이미지 API 가 열리면 예전 4노드를 되살린다.
    n_start = N("start5", "startNode")
    n_in = N("in_notice", "dynamicInputNode", inputLabel="공고문 내용",
             testValue=("제10회 부산 청년 창업 아이디어 공모전을 개최합니다. "
                        "접수 기간: 2026년 9월 15일(화)~10월 2일(금), 결과 발표: 10월 16일(금). "
                        "장소: 부산창업카페 2호점(서면), 접수는 이메일로도 가능합니다. "
                        "대상: 만 19~39세 부산 거주 청년 누구나. 총상금 1,000만 원(대상 1팀 500만 원). "
                        "문의: 051-000-0000, startup@busan.go.kr"))
    n_copy = N("copy_llm", "llmNode", model="gpt-5.4-mini",
               systemPrompt=("입력은 공고문이다. 포스터에 실을 문안을 만든다 — 공고문에 있는 내용만 쓰고, "
                             "날짜·장소·대상·혜택·문의처 같은 필수 정보를 빠뜨리지 않는다. bodyText 는 "
                             "대상·혜택·핵심 정보를 3~4줄로, 각 줄을 줄바꿈으로 구분한다. dateLine·placeLine 은 "
                             "값만 짧게 한 줄로 쓴다 — 포스터가 '일시'·'장소' 라벨을 따로 찍으므로 '접수 기간:', "
                             "'장소:' 같은 라벨을 값에 넣지 않고, 상자가 한 줄이라 dateLine 30자·placeLine 25자를 넘기지 않는다."),
               useStructuredOutput=True, jsonSchema=POSTER_SCHEMA)
    n_doc = N("poster_doc", "formatNode", formatId=poster_format_id, output="png")
    n_mail = N("issue_mail", "emailNode", toEmail=owner_email, subject="[포스터] 안내 포스터 생성 완료")
    n_out = N("out5", "outputNode")
    nodes = [n_start, n_in, n_copy, n_doc, n_mail, n_out]
    edges = [link(n_start, n_in), link(n_in, n_copy), link(n_copy, n_doc), link(n_doc, n_mail), link(n_mail, n_out)]
    flows["공고문 → 안내 포스터"] = (
        "공고문을 넣으면 필수 정보(일시·장소·대상·문의)를 빠짐없이 담은 포스터 문안을 정리하고, 디자인 포맷(고정 골격)에 "
        "채워 깨지지 않는 안내 포스터(PNG)를 만들어 이메일로 발송합니다 — 입력 → 문안 정리 → 조판 → 발송의 완결 흐름.",
        nodes, edges)

    return flows


# ── 앱 2종 (앱 빌더) ─────────────────────────────────────────────────────

def _text(cid, text, x, y, w, h=36, **style):
    return {"id": cid, "type": "text",
            "props": {"text": text, "position": {"x": x, "y": y},
                      "style": {"width": f"{w}px", "height": f"{h}px", **style}}}


def _input(cid, label, placeholder, input_key, x, y, w=420):
    return {"id": cid, "type": "input",
            "props": {"label": label, "placeholder": placeholder, "inputKey": input_key,
                      "position": {"x": x, "y": y}, "style": {"width": f"{w}px", "height": "68px"}}}


def _button(cid, text, x, y, w=180):
    return {"id": cid, "type": "button",
            "props": {"text": text, "position": {"x": x, "y": y},
                      "style": {"width": f"{w}px", "height": "48px"}}}


def _result(cid, kind, placeholder, x, y, w=560, h=200):
    return {"id": cid, "type": kind,
            "props": {"label": "결과", "placeholder": placeholder, "readOnly": True,
                      "position": {"x": x, "y": y}, "style": {"width": f"{w}px", "height": f"{h}px"}}}


def _blueprint(button_id, project_id, fields, result_id):
    """버튼 클릭 → 워크플로우 실행 → 결과 컴포넌트 표시 — UIEngine 의 표준 3노드 체인."""
    nodes = [
        {"id": "t1", "type": "triggerNode", "data": {"componentId": button_id, "eventType": "onClick"},
         "position": {"x": 40, "y": 80}},
        {"id": "s1", "type": "submitNode",
         "data": {"projectId": str(project_id),
                  "fields": [{"name": name, "componentId": cid} for name, cid in fields]},
         "position": {"x": 300, "y": 80}},
        {"id": "o1", "type": "outputNode", "data": {"componentId": result_id, "format": "text"},
         "position": {"x": 560, "y": 80}},
    ]
    edges = [
        {"id": "be1", "source": "t1", "target": "s1", "sourceHandle": "triggerOut", "targetHandle": "triggerIn"},
        {"id": "be2", "source": "s1", "target": "o1", "sourceHandle": "triggerOut", "targetHandle": "triggerIn"},
    ]
    return {"nodes": nodes, "edges": edges}


def build_apps(project_ids: dict):
    """제목 → (ui_graph_data, logic_graph, workflow_mappings)."""
    apps = {}

    # APP1 — 여행 플래너 (WF4)
    travel_pid = project_ids["여행지 → 여행 일정표"]
    components = [
        _text("title", "🧳 여행 플래너", 60, 44, 560, 44, fontSize="30px", fontWeight="700"),
        _text("desc", "여행지를 적으면 관광지·맛집을 모아 1박 2일 일정표(Word 문서)를 만들어 드려요.",
              60, 96, 740, 30, fontSize="15px", color="#64748b"),
        _input("place_input", "여행지", "예: 전주, 경주, 여수", "in_place", 60, 150),
        _button("plan_btn", "일정 만들기", 500, 172),
        _result("plan_box", "textarea", "생성된 일정표 파일 경로가 여기에 표시됩니다. (약 30~40초)", 60, 250),
        _text("hint", "생성이 끝나면 .docx 파일이 내 파일함에 저장되고, 입장 때 등록한 이메일로도 보내 드립니다.",
              60, 468, 640, 26, fontSize="13px", color="#94a3b8"),
    ]
    ui = {"components": components, "canvas": {"width": 800, "height": 540, "autoHeight": True},
          "rootStyle": {"backgroundColor": "#f8fafc"}, "globalCss": "", "globalJs": "",
          "description": "네이버 검색으로 관광지·맛집을 모아 여행 일정표를 만드는 앱"}
    logic = _blueprint("plan_btn", travel_pid, [("in_place", "place_input")], "plan_box")
    apps["여행 플래너"] = (ui, logic, {"plan_btn": {"projectId": str(travel_pid)}})

    # APP2 — 입사 지원서 도우미 (WF3)
    job_pid = project_ids["회사 분석 → 입사지원서(Word)"]
    components = [
        _text("title", "📄 입사 지원서 도우미", 60, 44, 560, 44, fontSize="30px", fontWeight="700"),
        _text("desc", "회사 홈페이지 주소를 넣으면 회사를 분석해 맞춤 입사지원서(Word 문서)를 작성해 드려요.",
              60, 96, 760, 30, fontSize="15px", color="#64748b"),
        _input("url_input", "회사 홈페이지 주소", "예: https://toss.im", "in_url", 60, 150),
        _button("write_btn", "지원서 작성", 500, 172),
        _result("app_box", "textarea", "생성된 지원서 파일 경로가 여기에 표시됩니다. (약 30~40초)", 60, 250),
        _text("hint", "생성이 끝나면 .docx 파일이 내 파일함에 저장되고, 입장 때 등록한 이메일로도 보내 드립니다.",
              60, 468, 640, 26, fontSize="13px", color="#94a3b8"),
    ]
    ui = {"components": components, "canvas": {"width": 800, "height": 540, "autoHeight": True},
          "rootStyle": {"backgroundColor": "#f8fafc"}, "globalCss": "", "globalJs": "",
          "description": "회사 사이트 분석 + 미리 입력한 프로필로 맞춤 입사지원서를 만드는 앱"}
    logic = _blueprint("write_btn", job_pid, [("in_url", "url_input")], "app_box")
    apps["입사 지원서 도우미"] = (ui, logic, {"write_btn": {"projectId": str(job_pid)}})

    return apps


# ── 시딩 본체 ────────────────────────────────────────────────────────────

def seed(db, user, validate: bool = True) -> dict:
    """검증 → upsert. 반환: {'formats': [...], 'projects': {제목: id}, 'apps': {제목: id}}.

    validate=False 는 게스트 입장(DEMO_GUEST)처럼 **이미 검증된 그래프를 복사만** 하는
    경로용이다 — 테스트(test_demo_booth_seed)가 같은 그래프의 dry_run 을 상시 검증한다.
    """
    import models
    from dry_run import dry_run_workflow

    fmt_ids = format_ids_for(user.id)
    flows = build_workflows(owner_email=USER_EMAIL_PLACEHOLDER,
                            travel_format_id=fmt_ids[TRAVEL_FORMAT_BASE],
                            poster_format_id=fmt_ids[POSTER_FORMAT_BASE])

    # 1) 전량 사전 검증 — 하나라도 실패하면 아무것도 쓰지 않는다.
    if validate:
        failures = []
        for title, (_desc, nodes, edges) in flows.items():
            result = dry_run_workflow({"nodes": nodes, "edges": edges})
            if not (result.success and result.compile_passed):
                failures.append((title, [str(i) for i in (result.issues or [])]))
        if failures:
            raise SystemExit(f"dry_run 검증 실패 — 시딩 중단: {failures}")

    # 2) 전용 포맷 (formatNode 가 참조하므로 워크플로우보다 먼저)
    from documents.format_spec import validate_format_spec
    for base_id, raw_spec in FORMAT_SPECS.items():
        format_id = fmt_ids[base_id]
        spec = validate_format_spec({**raw_spec, "id": format_id})
        fmt = db.query(models.DocumentFormat).filter(models.DocumentFormat.id == format_id).first()
        if fmt is None:
            fmt = models.DocumentFormat(id=format_id, owner_user_id=user.id,
                                        name=spec["name"], layout=spec["layout"], spec=spec)
            db.add(fmt)
        else:
            fmt.owner_user_id, fmt.name, fmt.layout, fmt.spec = user.id, spec["name"], spec["layout"], spec

    # 3) 워크플로우 upsert (소유자+제목 기준)
    project_ids = {}
    for title, (desc, nodes, edges) in flows.items():
        full_title = TITLE_PREFIX + title
        graph = {"nodes": nodes, "edges": edges}
        row = (db.query(models.Project)
               .filter(models.Project.user_id == user.id, models.Project.title == full_title).first())
        if row is None:
            row = models.Project(user_id=user.id, title=full_title, description=desc, graph_data=graph)
            db.add(row)
            db.flush()
        else:
            row.description, row.graph_data = desc, graph
        if not row.share_token:            # 층 1 QR 체험은 share 링크가 필요하다
            row.share_token = str(uuid.uuid4())
        project_ids[title] = row.id

    # 4) 앱 upsert (소유자+제목 기준)
    apps_map = build_apps(project_ids)
    app_ids = {}
    for title, (ui, logic, mappings) in apps_map.items():
        full_title = TITLE_PREFIX + title
        combined = {"ui": ui, "logic": logic}
        row = (db.query(models.CustomApp)
               .filter(models.CustomApp.owner_id == user.id, models.CustomApp.title == full_title).first())
        if row is None:
            row = models.CustomApp(id=str(uuid.uuid4()), title=full_title,
                                   ui_graph_data=combined, workflow_mappings=mappings, owner_id=user.id)
            db.add(row)
        else:
            row.ui_graph_data, row.workflow_mappings = combined, mappings
        app_ids[title] = row.id

    # 5) 목록에서 빠진 [시연] 항목 정리 — 콘텐츠를 교체해도 옛 항목이 계정 화면에 남지 않게
    #    "[시연-보관]" 으로 개명한다. 실행 로그·리비전이 걸려 있을 수 있어 삭제하지 않는다.
    #    (옛 전용 포맷 demo-news-briefing 은 보관된 워크플로우가 참조하므로 그대로 둔다.)
    archive_prefix = "[시연-보관] "
    expected = {TITLE_PREFIX + t for t in flows}
    for row in (db.query(models.Project)
                .filter(models.Project.user_id == user.id,
                        models.Project.title.like(f"{TITLE_PREFIX}%")).all()):
        if row.title not in expected:
            row.title = archive_prefix + row.title[len(TITLE_PREFIX):]
    expected_apps = {TITLE_PREFIX + t for t in apps_map}
    for row in (db.query(models.CustomApp)
                .filter(models.CustomApp.owner_id == user.id,
                        models.CustomApp.title.like(f"{TITLE_PREFIX}%")).all()):
        if row.title not in expected_apps:
            row.title = archive_prefix + row.title[len(TITLE_PREFIX):]

    db.commit()
    return {"formats": sorted(fmt_ids.values()), "projects": project_ids, "apps": app_ids}


def main():
    parser = argparse.ArgumentParser(description="부스 시연 콘텐츠 시딩")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="시연 계정 이메일")
    group.add_argument("--user-id", type=int, help="시연 계정 user id")
    args = parser.parse_args()

    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        query = db.query(models.User)
        user = (query.filter(models.User.email == args.email).first() if args.email
                else query.filter(models.User.id == args.user_id).first())
        if user is None:
            raise SystemExit("사용자를 찾을 수 없습니다 — 먼저 그 계정으로 한 번 로그인해 주세요.")
        result = seed(db, user)
        print(f"시딩 완료 (user={user.id} {user.email})")
        print(f"  포맷: {result['formats']}")
        for title, pid in result["projects"].items():
            print(f"  워크플로우 #{pid}: {TITLE_PREFIX}{title}")
        for title, aid in result["apps"].items():
            print(f"  앱 {aid}: {TITLE_PREFIX}{title}")
        print("남은 일(시연 계정 API 센터): OpenAI 키(WF5 이미지 생성), 네이버 검색 키(WF4),")
        print("        구글 OAuth youtube.readonly 연결(WF2), 디스코드 봇 토큰/웹훅(WF2 발송 노드),")
        print("        앱은 앱 빌더에서 '배포' 로 링크 발급. HIDDEN_NODE_TYPES=jusoNode 유지 권장.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
