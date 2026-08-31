"""connectors/services/data_go_kr.py — 공공데이터포털 오픈 API (한국형 노드 계획 §6.8, Phase 3).

■ 임의 URL 프록시가 아니다

이 노드는 사용자가 준 주소를 그대로 열지 않는다. **미리 등록한 데이터셋만** 호출한다.
이유는 둘이다.

  1. `httpRequestNode` 가 이미 임의 요청을 담당한다. 같은 것을 하나 더 만들 이유가 없다.
  2. 공공 데이터는 데이터셋마다 **이용허락범위와 출처 표시 요구가 다르다.** 임의 URL 을
     허용하면 그 조건을 결과에 붙일 방법이 없다.

새 데이터셋을 넣으려면 `DATASETS` 에 항목을 더한다. 각 항목은 공식 문서 주소와 **대조한 날**을
갖는다 — 규격을 추측해서 넣으면 실행 시점에야 틀린 것을 안다.

■ 데이터셋마다 다른 것들 (이게 registry 가 필요한 진짜 이유)

같은 포털인데 API 마다 다르다.

    과기정통부 보도자료   returnType=json
    기상청 단기예보       dataType=JSON

`_type` 을 쓰는 API 도 있다. 이름 하나만 틀려도 **오류가 아니라 XML 이 돌아와서**, 파서가
조용히 빈 결과를 낸다. 그래서 형식 파라미터 이름을 데이터셋별로 적어 둔다.

■ serviceKey 를 두 번 인코딩하지 않는다

포털이 "일반 인증키(Encoding)" 와 "(Decoding)" 두 가지를 준다. Encoding 키를 그대로
HTTP 라이브러리에 넘기면 라이브러리가 한 번 더 인코딩해서 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`
가 난다 — 네이버 카페의 이중 인코딩과 같은 계열의 함정이고, 방향만 반대다.
여기서는 **넘어온 키가 이미 인코딩된 것이면 먼저 되돌린 뒤** 넘긴다.

■ 실패가 200 으로 온다

인증 실패·한도 초과도 HTTP 200 이고 본문 `resultCode` 로만 알 수 있다(도로명주소와 같다).
그래서 정의의 `errorStyle` 이 `body` 다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "공공데이터포털"
BASE_HOST = "https://apis.data.go.kr"

MODES = ("query",)

MAX_ROWS = 100
DEFAULT_ROWS = 10


class Dataset:
    """등록된 데이터셋 하나. **공식 문서와 대조한 날이 없으면 등록하지 않는다.**"""

    def __init__(self, *, dataset_id: str, label: str, agency: str, path: str,
                 operations: Dict[str, str], format_param: str, format_value: str,
                 required: Dict[str, List[str]], docs_url: str, verified_at: str,
                 attribution: str, license_note: str):
        self.dataset_id = dataset_id
        self.label = label
        self.agency = agency
        self.path = path                     # /{기관코드}/{서비스명}
        self.operations = operations         # 표시 이름 → 실제 오퍼레이션 경로
        self.format_param = format_param     # returnType | dataType | _type …
        self.format_value = format_value     # json | JSON
        self.required = required             # 오퍼레이션별 필수 파라미터
        self.docs_url = docs_url
        self.verified_at = verified_at
        self.attribution = attribution       # 출처 표시 문구
        self.license_note = license_note     # 이용허락범위

    def url(self, operation: str) -> str:
        return f"{BASE_HOST}{self.path}/{self.operations[operation]}"


#: 승인된 데이터셋. 2026-08-30 에 각 공식 페이지를 열어 경로·파라미터·응답 필드를 대조했다.
DATASETS: Dict[str, Dataset] = {
    "msit_press_release": Dataset(
        dataset_id="msit_press_release",
        label="과학기술정보통신부 보도자료",
        agency="과학기술정보통신부",
        path="/1721000/msitpressreleaseinfo",
        operations={"list": "pressReleaseList"},
        format_param="returnType", format_value="json",
        required={"list": []},
        docs_url="https://www.data.go.kr/data/15074632/openapi.do",
        verified_at="2026-08-30",
        attribution="과학기술정보통신부 보도자료 (공공데이터포털)",
        license_note="이용허락범위 제한 없음 — 출처 표시 권장",
    ),
    "kma_village_forecast": Dataset(
        dataset_id="kma_village_forecast",
        label="기상청 단기예보",
        agency="기상청",
        path="/1360000/VilageFcstInfoService_2.0",
        operations={
            "now": "getUltraSrtNcst",        # 초단기실황
            "short_forecast": "getUltraSrtFcst",  # 초단기예보(6시간)
            "forecast": "getVilageFcst",     # 단기예보
        },
        # ⚠️ 보도자료는 returnType, 여기는 dataType 이다. 이름 하나 틀리면 XML 이 온다.
        format_param="dataType", format_value="JSON",
        required={
            "now": ["base_date", "base_time", "nx", "ny"],
            "short_forecast": ["base_date", "base_time", "nx", "ny"],
            "forecast": ["base_date", "base_time", "nx", "ny"],
        },
        docs_url="https://www.data.go.kr/data/15084084/openapi.do",
        verified_at="2026-08-30",
        attribution="기상청 단기예보 (공공데이터포털)",
        license_note="이용허락범위 제한 없음 — 출처 표시 필요",
    ),
}


def dataset_ids() -> List[str]:
    return sorted(DATASETS)


def get_dataset(dataset_id: Any) -> Dataset:
    key = str(dataset_id or "").strip()
    if key not in DATASETS:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=(f"등록되지 않은 데이터셋입니다: {key or '(비어 있음)'} — "
                    f"쓸 수 있는 것: {', '.join(dataset_ids())}"),
        )
    return DATASETS[key]


def service_key(raw: Any) -> str:
    """이미 인코딩된 키면 되돌린다.

    포털이 Encoding/Decoding 두 가지를 주는데, Encoding 쪽을 그대로 넘기면 HTTP 라이브러리가
    한 번 더 인코딩해서 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 가 난다. 사용자가 어느 쪽을
    붙여넣었는지 알 수 없으므로 **여기서 한 번 정규화**한다.
    """
    key = str(raw or "").strip()
    if not key:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="공공데이터포털 인증키가 없습니다 — API 센터에 등록해주세요",
        )
    # `%2B`·`%3D` 처럼 인코딩 흔적이 있으면 되돌린다. 원래 키에 % 가 들어갈 일은 없다.
    return unquote_plus(key) if "%" in key else key


# ── 응답을 공통 모양으로 ────────────────────────────────────────────────

def _xml_to_dict(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    out: Dict[str, Any] = {}
    for child in children:
        tag = child.tag.rsplit("}", 1)[-1]
        value = _xml_to_dict(child)
        if tag in out:
            if not isinstance(out[tag], list):
                out[tag] = [out[tag]]
            out[tag].append(value)
        else:
            out[tag] = value
    return out


def parse_body(body: Any) -> Dict[str, Any]:
    """JSON dict 든 XML 문자열이든 같은 모양으로 만든다.

    형식 파라미터 이름을 틀리면 **JSON 을 요청해도 XML 이 온다.** 그때 조용히 빈 결과를
    내지 않으려면 둘 다 읽을 수 있어야 한다.
    """
    if isinstance(body, dict):
        return body
    text = body if isinstance(body, str) else ""
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("<"):
        try:
            root = ET.fromstring(stripped)
        except ET.ParseError as exc:
            raise ConnectorError(
                code=INVALID_REQUEST, service=SERVICE,
                detail=f"응답을 XML 로도 JSON 으로도 읽지 못했습니다: {exc}",
            ) from None
        tag = root.tag.rsplit("}", 1)[-1]
        parsed = _xml_to_dict(root)
        return parsed if tag == "response" else {tag: parsed}
    import json as _json

    try:
        return _json.loads(stripped)
    except ValueError:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail="응답을 JSON 으로 읽지 못했습니다",
        ) from None


def _items_of(body_block: Any) -> List[Any]:
    """`body.items.item` 은 1건이면 dict, 여러 건이면 list 로 온다. XML 이면 더 흔들린다."""
    if not isinstance(body_block, dict):
        return []
    items = body_block.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    if items is None or items == "":
        return []
    return items if isinstance(items, list) else [items]


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


SUCCESS_CODES = {"00", "0"}
#: 사용자가 고칠 수 있는 것과 아닌 것이 섞여 있다. 문구는 그대로 보여도 되는 수준으로 쓴다.
ERROR_MESSAGES = {
    "01": "제공 기관 시스템에 오류가 있습니다",
    "02": "데이터베이스 오류입니다",
    "03": "데이터가 없습니다",
    "04": "HTTP 오류입니다",
    "05": "서비스 연결에 실패했습니다",
    "10": "잘못된 요청 파라미터가 있습니다",
    "11": "필수 요청 파라미터가 빠졌습니다",
    "12": "폐기되었거나 없는 서비스입니다",
    "20": "서비스 접근이 거부되었습니다",
    "21": "일시적으로 사용할 수 없는 키입니다",
    "22": "일일 요청 한도를 초과했습니다",
    "30": "등록되지 않은 인증키입니다 — 포털에서 발급 상태를 확인해주세요",
    "31": "활용 기간이 만료된 인증키입니다",
    "32": "등록되지 않은 도메인/IP 입니다",
    "99": "제공 기관에서 알 수 없는 오류가 발생했습니다",
}


def _check_result(header: Dict[str, Any]) -> None:
    code = str(header.get("resultCode") or "").strip()
    if not code or code in SUCCESS_CODES:
        return
    message = ERROR_MESSAGES.get(code.zfill(2)) or ERROR_MESSAGES.get(code)
    if not message:
        message = str(header.get("resultMsg") or "").strip() or "알 수 없는 오류"
    raise ConnectorError(code=INVALID_REQUEST, service=SERVICE,
                         detail=f"{message} [{code}]")


def query(definition, api_key: str, *, dataset_id: Any, operation: Any = None,
          params: Optional[Dict[str, Any]] = None, rows: Any = None, page: Any = None,
          session: Optional[ConnectorSession] = None) -> Dict[str, Any]:
    """등록된 데이터셋 하나를 조회한다. 읽기 전용이라 재시도해도 안전하다."""
    dataset = get_dataset(dataset_id)
    op = str(operation or "").strip() or sorted(dataset.operations)[0]
    if op not in dataset.operations:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=(f"'{dataset.label}' 에 없는 동작입니다: {op} — "
                    f"쓸 수 있는 것: {', '.join(sorted(dataset.operations))}"),
        )

    extra = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    missing = [p for p in dataset.required.get(op, []) if p not in extra]
    if missing:
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"'{dataset.label}' 조회에 필요한 값이 빠졌습니다: {', '.join(missing)}",
        )

    per_page = max(1, min(_number(rows, DEFAULT_ROWS) or DEFAULT_ROWS, MAX_ROWS))
    current = max(1, _number(page, 1) or 1)

    session = session or definition.new_session()
    response = session.request(
        "GET", dataset.url(op),
        params={
            "serviceKey": service_key(api_key),
            "pageNo": current,
            "numOfRows": per_page,
            # 이름이 데이터셋마다 다르다 — 틀리면 오류가 아니라 XML 이 온다.
            dataset.format_param: dataset.format_value,
            **extra,
        },
        idempotent=True,
    )

    parsed = parse_body(response.body)
    envelope = parsed.get("response") if isinstance(parsed.get("response"), dict) else parsed
    header = envelope.get("header") if isinstance(envelope.get("header"), dict) else {}
    _check_result(header)
    body_block = envelope.get("body") if isinstance(envelope.get("body"), dict) else {}
    items = _items_of(body_block)

    return {
        "mode": "query",
        "dataset": dataset.dataset_id,
        "datasetLabel": dataset.label,
        "operation": op,
        "page": _number(body_block.get("pageNo"), current),
        "rows": _number(body_block.get("numOfRows"), per_page),
        "total": _number(body_block.get("totalCount"), len(items)),
        "items": items,
        # 공공 데이터는 출처 표시와 이용허락범위가 따라붙는다(§6.8). 결과에 함께 남긴다.
        "attribution": dataset.attribution,
        "license": dataset.license_note,
        "docsUrl": dataset.docs_url,
    }
