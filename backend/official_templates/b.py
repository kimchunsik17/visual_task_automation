# -*- coding: utf-8 -*-
"""B묶음 — 구글 업무 자동화(Gmail·Drive·Sheets·Calendar). 142개가 한 번도 안 쓴 노드들이다."""
from ._lib import N, G, chain, link, llm, out, start, ask, sched

TEMPLATES = []


def add(title, desc, category, tags, nodes, edges, source=""):
    TEMPLATES.append({"title": title, "description": desc, "category": category,
                      "tags": tags, "graph": G(title, desc, nodes, edges), "source": source})


def t_gmail_triage():
    tr = N("gmailTriggerNode", query="is:unread", maxResults=20)
    a = llm("입력은 새로 온 메일이다. 각각을 '즉시 답장 / 오늘 안에 / 참고만 / 무시' 넷 중 하나로 "
            "분류하고 이유를 한 줄로 적는다. 확실하지 않으면 '오늘 안에'로 둔다.")
    n, e = chain(tr, a, out())
    add("받은 메일 자동 분류", "새 메일을 급한 것과 아닌 것으로 나눠 정리해 줍니다.",
        "automation", ["gmail", "분류", "메일"], n, e)


def t_gmail_draft_reply():
    tr = N("gmailTriggerNode", query="is:unread category:primary", maxResults=10)
    a = llm("입력은 받은 메일이다. 정중한 한국어 답장 초안을 쓴다. 확답이 필요한 부분은 "
            "'[확인 필요]' 로 표시하고 지어내지 않는다.")
    h = N("humanApprovalNode")
    g = N("gmailNode", mode="send_email", to="", subject="회신", body="")
    n, e = chain(tr, a, h, g, out())
    add("메일 답장 초안 → 사람 승인 후 발송", "답장 초안을 만들고 사람이 확인한 뒤에만 보냅니다.",
        "automation", ["gmail", "승인", "메일"], n, e)


def t_gmail_to_sheet():
    tr = N("gmailTriggerNode", query="subject:주문", maxResults=30)
    a = llm("입력은 주문 메일이다. 주문번호·품목·수량·연락처를 쉼표로 구분한 한 줄로만 출력한다. "
            "찾지 못한 항목은 빈칸으로 둔다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="주문!A:D")
    n, e = chain(tr, a, sh, out())
    add("주문 메일 → 구글 시트 적재", "주문 메일에서 항목을 뽑아 시트에 한 줄씩 쌓습니다.",
        "data", ["gmail", "시트", "주문"], n, e)


def t_drive_file_summary():
    s = sched("0 18 * * 5")
    d = N("googleDriveNode", mode="search_files", query="", folderId="")
    a = llm("입력은 드라이브 파일 목록이다. 이번 주에 새로 생기거나 바뀐 파일만 골라 "
            "이름과 용도 추정을 표로 정리한다.")
    n, e = chain(s, d, a, out())
    add("주간 드라이브 변경 요약", "금요일 저녁에 이번 주 드라이브 변화를 정리해 줍니다.",
        "document", ["드라이브", "주간", "요약"], n, e)


def t_sheet_to_report():
    s = sched("0 9 1 * *")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="매출!A:F")
    a = llm("입력은 매출 시트다. 전월 대비 늘고 준 항목을 각각 3개씩 뽑고 "
            "숫자와 함께 한 문단으로 정리한다. 시트에 없는 수치는 만들지 않는다.")
    n, e = chain(s, sh, a, out())
    add("월간 매출 시트 요약", "매달 1일에 매출 시트를 읽어 변화를 정리해 줍니다.",
        "data", ["시트", "매출", "월간"], n, e)


def t_calendar_briefing():
    s = sched("30 8 * * 1-5")
    c = N("googleCalendarNode", mode="list", calendarId="")
    a = llm("입력은 오늘 일정이다. 시간순으로 정리하고 준비물이 필요해 보이는 일정에는 "
            "'준비:' 를 붙인다. 일정이 없으면 '오늘 일정 없음'만 출력한다.")
    k = N("kakaoNode", template="text")
    n, e = chain(s, c, a, k, out())
    add("아침 일정 브리핑 (카카오)", "평일 아침에 오늘 일정을 정리해 카카오톡으로 보냅니다.",
        "notification", ["캘린더", "카카오", "브리핑"], n, e)


def t_meeting_to_calendar():
    s, i = start(), ask("회의 내용", "다음 주 화요일 오후 3시 기획 회의")
    a = llm("입력에서 일정 제목·날짜·시작 시각을 뽑아 'title|YYYY-MM-DD|HH:MM' 형식 한 줄로만 출력한다. "
            "정보가 부족하면 '정보 부족'만 출력한다.")
    c = N("googleCalendarNode", mode="create", calendarId="", summary="", startTime="")
    n, e = chain(s, i, a, c, out())
    add("말로 적은 약속 → 캘린더 등록", "문장으로 적은 약속을 캘린더 일정으로 만들어 줍니다.",
        "automation", ["캘린더", "일정"], n, e)


def t_sheet_dedupe():
    s = start()
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="명단!A:C")
    a = llm("입력은 명단이다. 이름과 연락처가 같은 중복 행을 찾아 목록으로 출력한다. "
            "중복이 없으면 '중복 없음'만 출력한다.")
    n, e = chain(s, sh, a, out())
    add("시트 중복 명단 찾기", "명단 시트에서 같은 사람이 두 번 들어간 행을 찾아 줍니다.",
        "data", ["시트", "정리", "중복"], n, e)


def t_drive_to_hwpx():
    s = start()
    d = N("googleDriveNode", mode="download_file", query="", fileName="")
    a = llm("입력은 문서 내용이다. 아래 JSON 하나만 출력한다 — 설명을 붙이지 않는다.\n"
            '{"title":"제목","blocks":[{"type":"heading","text":"소제목"},{"type":"paragraph","text":"내용"}]}')
    h = N("hwpxDocumentNode", mode="create", output_path="정리본.hwpx")
    n, e = chain(s, d, a, h, out())
    add("드라이브 문서 → 한글 정리본", "드라이브 파일을 읽어 한글 문서로 정리합니다.",
        "document", ["드라이브", "한글", "hwpx"], n, e)


def t_gmail_attachment_log():
    tr = N("gmailTriggerNode", query="has:attachment", maxResults=20)
    a = llm("입력은 첨부가 있는 메일이다. 보낸사람·제목·첨부 이름을 표로 정리한다.")
    sh = N("googleSheetsNode", mode="append", spreadsheetId="", range="첨부!A:C")
    n, e = chain(tr, a, sh, out())
    add("첨부 메일 대장 만들기", "첨부가 붙은 메일을 시트에 대장으로 기록합니다.",
        "data", ["gmail", "시트", "기록"], n, e)


def t_weekly_report_mail():
    s = sched("0 17 * * 5")
    sh = N("googleSheetsNode", mode="read", spreadsheetId="", range="업무!A:E")
    a = llm("입력은 이번 주 업무 시트다. 완료·진행·지연으로 나눠 정리하고, "
            "지연 항목에는 사유 칸의 내용을 함께 적는다. 비어 있으면 '사유 미기재'로 적는다.")
    g = N("gmailNode", mode="send_email", to="", subject="주간 업무 보고", body="")
    n, e = chain(s, sh, a, g, out())
    add("주간 업무 보고 메일 자동 발송", "금요일에 업무 시트를 정리해 보고 메일로 보냅니다.",
        "notification", ["시트", "gmail", "주간"], n, e)


def t_calendar_conflict():
    s = sched("0 20 * * 0")
    c = N("googleCalendarNode", mode="list", calendarId="")
    a = llm("입력은 다음 주 일정이다. 시간이 겹치는 일정 쌍을 찾아 알려 준다. "
            "겹치는 것이 없으면 '겹침 없음'만 출력한다.")
    n, e = chain(s, c, a, out())
    add("다음 주 일정 겹침 점검", "일요일 밤에 다음 주 일정 중 겹치는 것을 찾아 줍니다.",
        "notification", ["캘린더", "점검", "주간"], n, e)


for fn in list(globals().values()):
    if callable(fn) and getattr(fn, "__name__", "").startswith("t_"):
        fn()
