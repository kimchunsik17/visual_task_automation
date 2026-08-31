"""connectors/mock.py — 실제 API 없이 연동 노드를 실행하는 transport (ADR-0008).

노드 정의의 `mock` 블록(ADR-0005에서 슬롯만 잡아뒀던 자리)에 선언한 시나리오를 재생한다.
"성공"만 흉내 내면 쓸모가 적다 — 실제로 사용자를 막는 것은 인증 실패, 호출 한도, 잘못된 ID
같은 실패 경로이고, 그건 진짜 계정으로는 재현하기 어렵다. 그래서 시나리오를 여러 개 둔다.

같은 transport 를 테스트와 튜토리얼과 목업 서버 탭(백로그 7)이 함께 쓴다 — 세 곳이 서로
다른 가짜를 쓰면 "mock 에선 됐는데 실제로는 안 되는" 차이를 검증할 수 없다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .session import Response


class MockScenarioError(LookupError):
    """시나리오에 없는 요청이 나갔다. 조용히 200 을 돌려주면 mock 이 실제 계약과 어긋나도
    테스트가 통과해버리므로, 반드시 실패로 드러낸다."""


def _matches(rule: Dict[str, Any], method: str, url: str) -> bool:
    if not rule:
        return True
    if "method" in rule and rule["method"].upper() != method.upper():
        return False
    if "urlContains" in rule and rule["urlContains"] not in url:
        return False
    return True


class MockTransport:
    """`ConnectorSession(transport=...)` 에 그대로 끼울 수 있는 호출 대역.

    시나리오의 `responses` 를 위에서부터 훑어 첫 번째로 맞는 규칙을 쓴다. `once: true` 인
    규칙은 한 번 쓰이면 소진되므로, 같은 요청이 처음엔 429 였다가 다음엔 성공하는 재시도
    시나리오도 표현할 수 있다.
    """

    def __init__(self, scenario: Dict[str, Any]):
        self.rules: List[Dict[str, Any]] = list(scenario.get("responses") or [])
        self.calls: List[Dict[str, Any]] = []
        self._used: set = set()

    def __call__(self, method: str, url: str, **kwargs: Any) -> Response:
        self.calls.append({"method": method.upper(), "url": url, "params": kwargs.get("params")})
        stream_to = kwargs.get("stream_to")
        for index, rule in enumerate(self.rules):
            if index in self._used:
                continue
            if not _matches(rule.get("match") or {}, method, url):
                continue
            if rule.get("once"):
                self._used.add(index)
            if rule.get("raise") == "timeout":
                raise _MockTimeout(f"mock timeout: {method} {url}")
            status = rule.get("status", 200)
            # 바이너리 다운로드(session.download)는 본문을 파일로 흘려 넣는다. 시나리오는
            # `bodyBase64`(정확한 바이트) 또는 `bodyText`(간편)로 내용을 적는다 — 목업 탭에서도
            # 실제와 같은 경로로 파일이 만들어져야 다운로드 흐름을 확인할 수 있다.
            if stream_to is not None and 200 <= status < 300:
                payload = _mock_binary_body(rule)
                stream_to.write(payload)
                return Response(status=status, headers=rule.get("headers") or {},
                                body={"bytes": len(payload)})
            return Response(
                status=status,
                headers=rule.get("headers") or {},
                body=rule.get("body"),
            )
        raise MockScenarioError(f"mock 시나리오에 없는 요청이다: {method} {url}")


def _mock_binary_body(rule: Dict[str, Any]) -> bytes:
    if rule.get("bodyBase64"):
        import base64

        return base64.b64decode(rule["bodyBase64"])
    text = rule.get("bodyText")
    if text is None:
        text = rule.get("body") if isinstance(rule.get("body"), str) else ""
    return str(text or "").encode("utf-8")


class _MockTimeout(Exception):
    """이름으로 분류되므로(connectors.errors.from_exception) 실제 타임아웃과 같은 코드가 된다."""

    __name__ = "ConnectTimeout"


_MockTimeout.__name__ = "ConnectTimeout"


def scenario_names(definition_mock: Optional[Dict[str, Any]]) -> List[str]:
    return sorted((definition_mock or {}).get("scenarios", {}))


# ── 시나리오 계약 ───────────────────────────────────────────────────────
# "mock 이 있다"와 "mock 이 쓸모 있다"는 다르다. 성공만 흉내 내는 mock 은 실제로 사용자를 막는
# 경로(인증 실패·호출 한도·응답 지연)를 하나도 알려주지 않으면서 목업 탭에서는 초록불이 켜진다.
# 그래서 어떤 시나리오가 반드시 있어야 하는지를 여기서 정하고, 정의를 로드할 때 검사한다.
#
# 규칙은 만들어 낸 게 아니라 이미 있는 7개 연동 정의에서 뽑았다.
#   - success·timeout : 모든 연동. 네트워크를 타는 한 지연은 항상 가능하다.
#   - auth_failed·rate_limited : **자격증명이 필요한** 연동만. RSS 처럼 비로그인으로 읽는
#     연동에 "인증 실패" 시나리오를 요구하면 재현할 수 없는 상황을 지어내게 된다.
ALWAYS_REQUIRED = ("success", "timeout")
CREDENTIALED_REQUIRED = ("auth_failed", "rate_limited")

# 각 시나리오가 실제로 그 상황을 재현하는지 — 이름만 맞고 200 을 돌려주면 없느니만 못하다.
_EXPECTED_STATUS = {
    "auth_failed": (401, 403),
    "rate_limited": (429,),
    "not_found": (404,),
    "server_error": (500, 502, 503, 504),
}


def required_scenarios(connector) -> List[str]:
    """이 연동이 반드시 선언해야 하는 시나리오 이름들."""
    names = list(ALWAYS_REQUIRED)
    if connector is not None and connector.required_providers():
        names += list(CREDENTIALED_REQUIRED)
    return names


def validate_mock(definition_mock: Optional[Dict[str, Any]], connector, *, label: str) -> List[str]:
    """정의의 mock 블록이 계약을 지키는지. 문제 목록을 돌려준다(비어 있으면 통과)."""
    problems: List[str] = []
    scenarios = (definition_mock or {}).get("scenarios") or {}

    for name in required_scenarios(connector):
        if name not in scenarios:
            problems.append(f"{label}: mock 시나리오 '{name}' 가 없다")

    for name, scenario in scenarios.items():
        responses = (scenario or {}).get("responses")
        if not responses:
            problems.append(f"{label}: mock 시나리오 '{name}' 에 responses 가 없다")
            continue
        if name == "timeout":
            if not any(r.get("raise") == "timeout" for r in responses):
                problems.append(f"{label}: 'timeout' 시나리오는 raise: timeout 을 하나 이상 가져야 한다")
            continue
        expected = _EXPECTED_STATUS.get(name)
        if not expected:
            continue
        if getattr(connector, "errorStyle", "http") == "body":
            # 본문으로 실패를 알리는 API 다. 상태 코드를 요구하면 실제로 일어나지 않는
            # 상황을 재현하게 되므로, 대신 **성공과 다른 본문** 인지를 본다.
            if not any(_has_error_body(r) for r in responses):
                problems.append(
                    f"{label}: '{name}' 시나리오의 본문에 오류 표시가 없다 — "
                    "errorStyle 이 body 인데 성공 응답과 구분되지 않는다"
                )
            continue
        if not any(r.get("status") in expected for r in responses):
            problems.append(
                f"{label}: '{name}' 시나리오가 {expected} 중 어느 상태도 돌려주지 않는다 — "
                "이름만 맞고 실제로는 그 상황을 재현하지 않는다"
            )
    return problems


# 본문 어딘가에 비어 있지 않은 오류 코드/메시지가 있는가. 키 이름은 API 마다 달라서
# 값으로 판단하지 않고 **이름이 오류를 뜻하는 키가 채워져 있는가**만 본다.
_ERROR_KEYS = ("errorcode", "errormessage", "errmsg", "resultcode", "resultmsg", "error")


def _has_error_body(response: Dict[str, Any]) -> bool:
    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                name = str(key).lower()
                if name in _ERROR_KEYS:
                    text = str(item).strip()
                    # "0"·"00" 은 정상을 뜻하는 관례라 오류로 치지 않는다.
                    if text and text not in ("0", "00", "None"):
                        return True
                if walk(item):
                    return True
        elif isinstance(value, list):
            return any(walk(v) for v in value)
        return False

    return walk(response.get("body"))


def transport_for(definition_mock: Optional[Dict[str, Any]], scenario: str) -> MockTransport:
    scenarios = (definition_mock or {}).get("scenarios") or {}
    if scenario not in scenarios:
        raise MockScenarioError(
            f"'{scenario}' 시나리오가 정의의 mock 블록에 없다. 있는 것: {', '.join(sorted(scenarios)) or '없음'}"
        )
    return MockTransport(scenarios[scenario])
