"""connectors/services/juso.py — 행정안전부 도로명주소 검색 (한국형 노드 계획 §6.8, Phase 3).

■ 이 노드가 하는 일은 "주소 문자열을 정본 주소로 바꾸는 것" 이다

사람이 쓴 주소는 제각각이다 — "부산대 앞", "부산광역시 금정구 부산대학로63번길 2",
"금정구 장전동 30". 이걸 그대로 배송·청구·통계에 쓰면 같은 곳이 여러 값으로 흩어진다.
이 노드는 그 문자열을 **도로명·지번·우편번호·영문주소가 모두 채워진 한 건**으로 바꾼다.

■ 규격 출처와 한계 (중요)

2026-08-30 기준 `juso.go.kr` 이 자동 요청을 막아 **공식 규격 문서를 직접 열지 못했다.**
아래 필드명과 errorCode 는 2차 출처(개발자 블로그·연계 가이드)에서 모은 것이다.

    승인키를 발급받으면 가장 먼저 `verify_against_official_docs()` 의 주석대로
    실제 응답 한 건을 받아 이 파일의 FIELD_MAP·ERROR_MESSAGES 와 대조해야 한다.

그래서 **모르는 필드는 버리지 않고 `raw` 에 담아 둔다.** 우리가 안다고 생각한 이름이 틀렸을 때
사용자가 원본에서 찾을 수 있어야 한다.

■ 승인키는 도메인에 묶인다

juso 승인키는 신청할 때 등록한 서비스 URL 에서만 동작한다(E0002). 그래서 키가 맞는데도
실패할 수 있고, 그 경우 사용자가 봐야 할 것은 "키가 틀렸다" 가 아니라 "등록한 주소와 다르다" 다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "도로명주소"
BASE_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"

MODES = ("search",)

MAX_COUNT_PER_PAGE = 100
DEFAULT_COUNT_PER_PAGE = 10

# 공식 문서를 직접 못 읽었으므로 **아는 것만** 적는다. 나머지는 raw 로 넘어간다.
FIELD_MAP = {
    "roadAddr": "roadAddress",           # 전체 도로명주소
    "roadAddrPart1": "roadAddressPart1",  # 도로명주소(참고항목 제외)
    "roadAddrPart2": "roadAddressPart2",  # 도로명주소 참고항목
    "jibunAddr": "jibunAddress",         # 지번주소
    "engAddr": "englishAddress",         # 도로명주소(영문)
    "zipNo": "zipCode",                  # 우편번호
    "admCd": "adminCode",                # 행정구역코드
    "rnMgtSn": "roadNameCode",           # 도로명코드
    "bdMgtSn": "buildingCode",           # 건물관리번호
    "bdNm": "buildingName",              # 건물명
    "detBdNmList": "detailBuildingNames",  # 상세건물명
    "siNm": "sido",                      # 시도명
    "sggNm": "sigungu",                  # 시군구명
    "emdNm": "eupmyeondong",             # 읍면동명
    "liNm": "ri",                        # 법정리명
    "rn": "roadName",                    # 도로명
    "buldMnnm": "buildingMainNo",        # 건물본번
    "buldSlno": "buildingSubNo",         # 건물부번
    "udrtYn": "underground",             # 지하여부(0/1)
}

# errorCode "0" 이 정상이다. 나머지는 사용자가 고칠 수 있는 것과 아닌 것이 섞여 있다.
ERROR_MESSAGES = {
    "E0001": "도로명주소 승인키가 승인되지 않았습니다. 발급 상태를 확인해주세요",
    "E0002": "승인키에 등록한 서비스 주소와 다릅니다. 신청할 때 적은 URL 을 확인해주세요",
    "E0005": "검색어가 비어 있습니다",
    "E0006": "주소를 조금 더 자세히 입력해주세요",
    "E0008": "검색어는 한 글자 이상이어야 합니다",
    "E0009": "검색어에 문자와 숫자를 함께 넣어주세요",
    "E0010": "검색어가 너무 깁니다",
    "E0011": "검색어에 쓸 수 없는 특수문자가 있습니다",
    "E0012": "검색어에 시도명만으로는 검색할 수 없습니다",
    "E0014": "개발승인키 사용 기간이 끝났습니다. 운영키로 다시 신청해주세요",
}
# 사용자가 입력을 고쳐서 해결되는 것들. 나머지는 키·계약 문제라 다시 시도해도 같다.
USER_FIXABLE = {"E0005", "E0006", "E0008", "E0009", "E0010", "E0011", "E0012"}


def _keyword(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail="검색할 주소가 비어 있습니다")
    if len(text) > 80:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                             detail=f"검색어가 너무 깁니다({len(text)}자). 80자 이내로 줄여주세요")
    return text


def _count(value: Any) -> int:
    """개수는 1~100. **0 을 '안 정함' 으로 읽지 않는다** — 네이버 검색에서 그 실수를 했다."""
    if value is None or value == "":
        return DEFAULT_COUNT_PER_PAGE
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_COUNT_PER_PAGE
    return max(1, min(number, MAX_COUNT_PER_PAGE))


def _page(value: Any) -> int:
    if value is None or value == "":
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """아는 필드는 이름을 붙이고, **모르는 것은 raw 에 남긴다.**

    필드명을 2차 출처에서 가져왔으므로 우리가 틀렸을 수 있다. 버려 두면 사용자가 확인할
    방법이 없어진다.
    """
    out: Dict[str, Any] = {}
    for source, target in FIELD_MAP.items():
        if source in item:
            out[target] = item.get(source)
    out["raw"] = dict(item)
    return out


def _check_error(common: Dict[str, Any]) -> None:
    code = str(common.get("errorCode") or "0").strip()
    if code in ("0", "00", ""):
        return
    message = ERROR_MESSAGES.get(code)
    if not message:
        # 모르는 코드다. 원문을 그대로 보여주는 편이 지어내는 것보다 낫다.
        message = str(common.get("errorMessage") or "").strip() or f"도로명주소 API 오류({code})"
    raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                         detail=f"{message} [{code}]")


def search(definition, confirm_key: str, *, keyword: Any, count: Any = None,
           page: Any = None, include_history: bool = False,
           session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """주소를 검색해 정본 주소 목록을 돌려준다. 읽기 전용이라 재시도해도 안전하다."""
    key = str(confirm_key or "").strip()
    if not key:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="도로명주소 승인키가 없습니다 — API 센터에서 juso 승인키를 등록해주세요",
        )
    text = _keyword(keyword)
    per_page, current = _count(count), _page(page)

    session = session or definition.new_session()
    response = session.request(
        "GET", BASE_URL,
        params={
            "confmKey": key,
            "keyword": text,
            "currentPage": current,
            "countPerPage": per_page,
            # XML 이 기본값이라 **매번 명시한다.** 빼먹으면 파서가 조용히 빈 결과를 낸다.
            "resultType": "json",
            "hstryYn": "Y" if include_history else "N",
        },
        idempotent=True,
    )

    body = response.body if isinstance(response.body, dict) else {}
    results = body.get("results") if isinstance(body.get("results"), dict) else {}
    common = results.get("common") if isinstance(results.get("common"), dict) else {}
    _check_error(common)

    rows = results.get("juso")
    items = [normalize_item(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    try:
        total = int(common.get("totalCount") or 0)
    except (TypeError, ValueError):
        total = len(items)

    return {
        "mode": "search",
        "keyword": text,
        "total": total,
        "page": current,
        "countPerPage": per_page,
        "items": items,
        # 공공데이터는 출처 표시 요구가 따라붙는다(§6.8). 결과에 함께 남긴다.
        "attribution": "행정안전부 도로명주소 (juso.go.kr)",
    }
