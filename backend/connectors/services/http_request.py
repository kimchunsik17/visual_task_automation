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


def _guard_url(url: str) -> None:
    """SSRF 검사. 막을 이유가 있으면 요청을 보내기 전에 ConnectorError 로 세운다.

    이 노드의 URL 은 사용자·LLM 이 정한다 — 저장소에서 유일하게 목적지가 자유로운 노드다.
    정책 자체는 `url_guard` 에 이미 있고 webCrawlerNode 가 쓰고 있었는데, 이쪽만 배선이
    빠져 있었다(내부 주소·클라우드 메타데이터 엔드포인트로 그냥 나갈 수 있었다).

    INVALID_REQUEST 를 쓰는 이유: 재시도 대상이 아니다(`errors.RETRYABLE_CODES` 밖). 막힌
    주소로 다시 보내봐야 결과가 같다.
    """
    import url_guard

    try:
        url_guard.check_url(url)
    except url_guard.UrlBlocked as exc:
        raise ConnectorError(code=INVALID_REQUEST, service=SERVICE, detail=str(exc)) from exc


def _redirect_guard(response, *args: Any, **kwargs: Any):
    """리다이렉트를 따라가기 전에 다음 홉을 검사하는 requests response 훅.

    초기 URL 만 검사하면 공격자가 자기 서버에서 302 로 169.254.169.254 를 가리키는 것으로
    우회할 수 있다. requests 는 응답 훅을 **다음 요청을 보내기 전에** 부르므로, 여기서
    세우면 내부 주소로는 요청이 나가지 않는다.
    """
    if response.is_redirect or response.is_permanent_redirect:
        location = response.headers.get("Location")
        if location:
            from urllib.parse import urljoin

            _guard_url(urljoin(response.url, location))
    return response


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

    target = str(url).strip()

    # mock 재생은 네트워크를 타지 않는다(node_definition.new_session 이 재생 transport 를 끼운다).
    # 그런데 check_url 은 DNS 를 해석하므로, 목업 시나리오의 가짜 호스트를 막아버린다.
    # 나가지 않는 요청을 SSRF 로 막을 이유가 없으니 목업에서는 건너뛴다.
    from .. import mock_runtime

    if mock_runtime.current() is None:
        _guard_url(target)
        kwargs["hooks"] = {"response": _redirect_guard}

    response = session.request(method, target, **kwargs)
    payload = response.json()
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return "" if payload is None else str(payload)
