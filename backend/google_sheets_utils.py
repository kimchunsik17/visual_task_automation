"""
google_sheets_utils.py — googleSheetsNode가 쓰는 구글 시트 읽기/쓰기 헬퍼.

카카오/디스코드/텔레그램처럼 "사용자 한 명당 OAuth 로그인"을 시키는 대신, 서비스 계정
(Service Account) 하나로 통일했다 — 이유:
  1. 구글 시트 OAuth는 앱을 만들고, 동의 화면을 구성하고, 액세스 토큰이 만료될 때마다
     refresh_token으로 갱신하는 절차가 필요하다(이번 세션에서 카카오 access_token 자동 갱신을
     붙이다가 겪은 것과 같은 종류의 복잡도 — client_secret 필요 여부, 만료 시각 추적 등).
  2. 서비스 계정은 한 번 만들어서 backend/.env에 키를 등록해두면 끝이고, 이후 사용자는
     그냥 자기 시트를 그 서비스 계정 이메일과 "공유"만 하면 된다(구글 문서를 다른 사람과
     공유하는 것과 완전히 같은 방식이라 이해하기 쉽다) — 만료도, 재인증도 없다.
  트레이드오프: 모든 워크플로우가 "같은" 서비스 계정 신원으로 시트에 접근한다(사용자별로
  다른 구글 계정 권한을 쓸 수는 없다). MVP 단계에서는 이 쪽이 훨씬 낫다고 판단.

설정 방법(사용자가 해야 할 일 — README나 API 센터 안내에 반영):
  1. https://console.cloud.google.com/ 에서 프로젝트를 만들고 "Google Sheets API"를 사용 설정한다.
  2. IAM & 관리자 > 서비스 계정에서 새 서비스 계정을 만들고, 키(JSON)를 새로 만들어 다운로드한다.
  3. 그 JSON 파일 내용 전체를 backend/.env의 GOOGLE_SERVICE_ACCOUNT_JSON에 한 줄 문자열로 넣는다
     (또는 GOOGLE_SERVICE_ACCOUNT_FILE에 JSON 파일 경로를 넣어도 된다).
  4. 워크플로우에서 다룰 구글 시트를 열어 "공유" → 그 서비스 계정 이메일(JSON의 client_email
     필드, ...@...iam.gserviceaccount.com 형식)을 편집자로 추가한다.
"""
import json
import os

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

_client = None
_client_error = None


def _load_client():
    """gspread 클라이언트를 지연 생성한다(모듈 import 시점이 아니라 처음 실제로 쓸 때) —
    서비스 계정이 아직 설정 안 된 서버에서도 이 모듈을 import하는 것 자체는 실패하지 않게
    하기 위함. 실패하면 이유를 _client_error에 남겨서, 이후 호출들이 똑같은 친절한 에러를
    반복해서 만들어내지 않고 캐시된 이유를 그대로 재사용한다."""
    global _client, _client_error
    if _client is not None or _client_error is not None:
        return _client

    import gspread
    from google.oauth2.service_account import Credentials

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    try:
        if raw_json:
            info = json.loads(raw_json)
            creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
        elif key_file and os.path.exists(key_file):
            creds = Credentials.from_service_account_file(key_file, scopes=_SCOPES)
        else:
            _client_error = (
                "Google 서비스 계정이 설정되지 않았습니다 — backend/.env에 "
                "GOOGLE_SERVICE_ACCOUNT_JSON(서비스 계정 키 JSON 전체) 또는 "
                "GOOGLE_SERVICE_ACCOUNT_FILE(키 파일 경로)을 등록해주세요."
            )
            return None
        _client = gspread.authorize(creds)
    except Exception as e:
        _client_error = f"Google 서비스 계정 인증 실패: {e}"
        return None
    return _client


def is_configured() -> bool:
    return _load_client() is not None


def _open(spreadsheet_id: str):
    client = _load_client()
    if client is None:
        raise RuntimeError(_client_error)
    try:
        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        raise RuntimeError(
            f"스프레드시트를 열 수 없습니다({spreadsheet_id}): {e}. 시트를 서비스 계정 이메일과 "
            "공유(편집자 권한)했는지 확인해주세요."
        )


def read_range(spreadsheet_id: str, range_str: str) -> list:
    """range_str이 "시트이름"만 있으면 그 시트 전체를, "시트이름!A1:D10" 형식이면 그 범위만 읽는다."""
    sh = _open(spreadsheet_id)
    if "!" in range_str:
        sheet_name, cell_range = range_str.split("!", 1)
        ws = sh.worksheet(sheet_name) if sheet_name else sh.sheet1
        return ws.get(cell_range) if cell_range else ws.get_all_values()
    ws = sh.worksheet(range_str) if range_str else sh.sheet1
    return ws.get_all_values()


def append_row(spreadsheet_id: str, sheet_name: str, values: list) -> None:
    sh = _open(spreadsheet_id)
    ws = sh.worksheet(sheet_name) if sheet_name else sh.sheet1
    ws.append_row(values, value_input_option="USER_ENTERED")


def write_range(spreadsheet_id: str, range_str: str, values: list) -> None:
    """range_str은 "시트이름!A1"처럼 시작 셀만 줘도 되고(gspread의 update가 값 크기에 맞춰
    자동으로 범위를 채운다), 시트이름만 주면 A1부터 쓴다."""
    sh = _open(spreadsheet_id)
    if "!" in range_str:
        sheet_name, cell_range = range_str.split("!", 1)
        ws = sh.worksheet(sheet_name) if sheet_name else sh.sheet1
        ws.update(cell_range or "A1", values)
    else:
        ws = sh.worksheet(range_str) if range_str else sh.sheet1
        ws.update("A1", values)
