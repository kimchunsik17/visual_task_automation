"""connectors/services/http_request.py — httpRequestNode 의 실행부 (ADR-0009).

이 노드는 원래 codegen 이 `requests.get/post/...` 를 문자열로 조립하고 status_code 를 직접
비교했다. 그래서 (1) 재시도가 없었고 (2) 실패가 `HTTP Request Error: ...` 한 줄로 뭉개졌고
(3) mock 으로 갈아끼울 방법이 없어 Mock 탭에서 다룰 수가 없었다.

공통 계약(ADR-0007) 위로 옮기면서 셋 다 해결된다 — GET 은 일시적 오류에 재시도하고,
POST/PUT/DELETE 는 중복 실행을 막기 위해 429 에서만 재시도하며, mock 모드에서는 정의의
시나리오를 재생한다.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..errors import INVALID_REQUEST, ConnectorError
from ..session import ConnectorSession

SERVICE = "HTTP"
NODE_TYPE = "httpRequestNode"

# meta_agent 가 "URL 을 아직 모른다"는 뜻으로 넣는 값. 실제 요청을 시도하지 않는다.
PLACEHOLDER_URL = "REPLACE_WITH_ACTUAL_URL"


def _parse_json_field(raw: Any, label: str) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise ConnectorError(
            code=INVALID_REQUEST, service=SERVICE,
            detail=f"{label}이(가) 유효한 JSON 이 아니다: {text[:120]}",
        ) from None
    return parsed if isinstance(parsed, dict) else {}


def call(
    definition,
    *,
    method: str,
    url: str,
    headers: Any = None,
    body: Any = None,
    session: Optional[ConnectorSession] = None,
) -> str:
    """요청을 보내고 응답 본문을 문자열로 돌려준다(JSON 이면 보기 좋게 정렬해서).

    반환 형태를 예전 구현과 똑같이 유지한다 — 이 노드의 출력을 뒤 노드(jsonParserNode 등)가
    그대로 받아 쓰고 있어서, 형태가 바뀌면 기존 워크플로우가 조용히 깨진다.
    """
    method = (method or "GET").upper()
    if not url or not str(url).strip():
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail="URL 이 비어 있다")

    session = session or definition.new_session()
    parsed_headers = _parse_json_field(headers, "headers")
    parsed_body = _parse_json_field(body, "body")

    kwargs: Dict[str, Any] = {"headers": parsed_headers}
    if method == "GET":
        kwargs["params"] = parsed_body
    else:
        kwargs["json"] = parsed_body

    response = session.request(method, str(url).strip(), **kwargs)
    payload = response.json()
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return "" if payload is None else str(payload)
