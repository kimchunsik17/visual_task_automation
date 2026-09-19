"""국내 협업 메신저 발송 3종(백로그 34 DEV-3 1차, ADR-0035) — Dooray · 잔디 · 카카오워크 계약 테스트.

  1. **Slack 발송과 같은 메시지 규약.** 비우면 직전 출력, 채우면 덧붙임, {{last_result}} 자리.
  2. **웹훅 URL 은 허용 호스트만.** 사용자가 저장한 URL 로 서버가 POST 하므로 내부 주소·다른 호스트는 요청 전에 막는다.
  3. **서비스별 payload 모양.** Dooray attachments / 잔디 connectInfo+Accept 헤더 / 카카오워크 Bearer + messages.send(_by_email).
  4. **발송 결과는 보낸 텍스트.** 그래프 안에서 결과가 텍스트로 남고, 실패해도 본문은 남는다(delivery 도메인 오류).
"""

from __future__ import annotations

import pytest

import mock_service
import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import team_chat
from connectors.session import ConnectorSession, Response

DOORAY = node_definition.get_definition("doorayNode")
JANDI = node_definition.get_definition("jandiNode")
KAKAO = node_definition.get_definition("kakaoWorkNode")
DOORAY_URL = "https://hook.dooray.com/services/111/222/abc"
JANDI_URL = "https://wh.jandi.com/connect-api/webhook/111/abc"


class _Recorder:
    def __init__(self, status=200, body=None):
        self.calls = []
        self.status, self.body = status, body

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body if self.body is not None else {})


def _session(rec):
    return ConnectorSession("test", transport=rec, sleep=lambda _s: None)


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    import url_guard

    monkeypatch.setattr(url_guard, "check_url", lambda url: (url, "x"))


# ── 1. 메시지 규약 ────────────────────────────────────────────────────────

def test_메시지_규약은_Slack_발송과_같다():
    assert team_chat.compose_message("", "직전 출력") == "직전 출력"
    assert team_chat.compose_message("요약:", "직전 출력") == "요약:\n\n직전 출력"
    assert team_chat.compose_message("결과 → {{last_result}} 끝", "X") == "결과 → X 끝"
    assert team_chat.compose_message("고정 문구", "") == "고정 문구"
    assert team_chat.compose_message(None, None) == ""


def test_상한을_넘는_본문은_잘라_표시한다():
    text = team_chat.truncate("x" * 5000)
    assert len(text) == team_chat.MAX_TEXT_CHARS and text.endswith("…(잘림)")
    assert team_chat.truncate("짧다") == "짧다"


def test_빈_본문은_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_dooray(DOORAY, DOORAY_URL, text="   ", session=_session(rec))
    assert exc.value.code == "invalid_request" and rec.calls == []


# ── 2. 웹훅 URL 검사 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "http://hook.dooray.com/services/x", "https://evil.example.com/hook", "https://hook.dooray.com.evil.com/x",
                                 "https://wh.jandi.com/connect-api/webhook/x", "https://10.0.0.1/x"])
def test_Dooray_웹훅은_dooray_com_https_만(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_dooray(DOORAY, bad, text="hi", session=_session(rec))
    assert exc.value.code == "invalid_request" and rec.calls == []


def test_잔디_웹훅은_wh_jandi_com_만_그리고_url_guard_를_거친다(monkeypatch):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        team_chat.send_jandi(JANDI, DOORAY_URL, text="hi", session=_session(rec))
    import url_guard

    def block(url):
        raise url_guard.UrlBlocked("막힘", reason="PRIVATE")

    monkeypatch.setattr(url_guard, "check_url", block)
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_jandi(JANDI, JANDI_URL, text="hi", session=_session(rec))
    assert "막힘" in (exc.value.detail or "") and rec.calls == []


def test_테넌트_도메인_형태의_Dooray_주소도_받는다():
    rec = _Recorder(body={"header": {"isSuccessful": True}})
    team_chat.send_dooray(DOORAY, "https://acme.dooray.com/services/1/2/abc", text="hi", session=_session(rec))
    assert rec.calls[0]["url"].startswith("https://acme.dooray.com/")


# ── 3. payload 모양 ───────────────────────────────────────────────────────

def test_Dooray_payload_와_첨부_카드():
    rec = _Recorder(body={"header": {"isSuccessful": True, "resultCode": 0}})
    result = team_chat.send_dooray(DOORAY, DOORAY_URL, text="본문", title="배포 완료", link="https://x/y", color="green", bot_name="봇",
                                   session=_session(rec))
    call = rec.calls[0]
    assert call["method"] == "POST" and call["url"] == DOORAY_URL and call["headers"]["Content-Type"] == "application/json"
    assert call["json"] == {"text": "본문", "botName": "봇", "attachments": [{"title": "배포 완료", "titleLink": "https://x/y", "color": "#2ECC71"}]}
    assert result["sent"] is True and result["text"] == "본문" and result["title"] == "배포 완료" and result["chars"] == 2
    plain = _Recorder(body={"header": {"isSuccessful": True}})
    team_chat.send_dooray(DOORAY, DOORAY_URL, text="본문만", session=_session(plain))
    assert plain.calls[0]["json"] == {"text": "본문만"}


def test_Dooray_가_header_isSuccessful_false_로_거절하면_커넥터_오류():
    rec = _Recorder(body={"header": {"isSuccessful": False, "resultCode": -1, "resultMessage": "채널 없음"}})
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_dooray(DOORAY, DOORAY_URL, text="본문", session=_session(rec))
    assert exc.value.code == "invalid_request" and "채널 없음" in (exc.value.detail or "")


def test_잔디_payload_와_Accept_헤더():
    rec = _Recorder(body={})
    result = team_chat.send_jandi(JANDI, JANDI_URL, text="본문", title="CI 실패", link="https://ci/1", color="red", session=_session(rec))
    call = rec.calls[0]
    assert call["headers"]["Accept"] == "application/vnd.tosslab.jandi-v2+json"
    assert call["json"] == {"body": "본문", "connectColor": "#E74C3C", "connectInfo": [{"title": "CI 실패", "description": "https://ci/1"}]}
    assert result["title"] == "CI 실패"
    rec2 = _Recorder(body={})
    team_chat.send_jandi(JANDI, JANDI_URL, text="본문", description="설명", image_url="https://img/1.png", session=_session(rec2))
    assert rec2.calls[0]["json"]["connectInfo"] == [{"title": "알림", "description": "설명", "imageUrl": "https://img/1.png"}]


@pytest.mark.parametrize("bad", ["pink", "#12", "rgb(1,2,3)"])
def test_모르는_색은_요청_전에_거절(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        team_chat.send_jandi(JANDI, JANDI_URL, text="x", color=bad, session=_session(rec))
    assert rec.calls == []


def test_hex_색은_그대로_쓴다():
    rec = _Recorder(body={})
    team_chat.send_jandi(JANDI, JANDI_URL, text="x", color="#abcdef", session=_session(rec))
    assert rec.calls[0]["json"]["connectColor"] == "#ABCDEF"


def test_카카오워크는_Bearer_로_대화방_또는_이메일로():
    rec = _Recorder(body={"success": True, "message": {"id": "m1", "conversation_id": "42", "text": "본문"}})
    result = team_chat.send_kakaowork(KAKAO, "app-key", text="본문", conversation_id="42", session=_session(rec))
    call = rec.calls[0]
    assert call["url"] == "https://api.kakaowork.com/v1/messages.send" and call["headers"]["Authorization"] == "Bearer app-key"
    assert call["json"] == {"text": "본문", "conversation_id": "42"}
    assert result["messageId"] == "m1" and result["conversationId"] == "42" and result["mode"] == "send"
    rec2 = _Recorder(body={"success": True, "message": {"id": "m2"}})
    team_chat.send_kakaowork(KAKAO, "app-key", text="본문", mode="send_by_email", email="a@b.com", session=_session(rec2))
    assert rec2.calls[0]["url"].endswith("/v1/messages.send_by_email") and rec2.calls[0]["json"] == {"text": "본문", "email": "a@b.com"}


@pytest.mark.parametrize("kwargs", [{"conversation_id": ""}, {"mode": "send_by_email", "email": "not-an-email"}, {"mode": "broadcast", "conversation_id": "1"}])
def test_카카오워크_수신자_검증은_요청_전에(kwargs):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        team_chat.send_kakaowork(KAKAO, "app-key", text="x", session=_session(rec), **kwargs)
    assert rec.calls == []


def test_카카오워크_success_false_는_코드에_따라_인증_또는_요청_오류():
    rec = _Recorder(body={"success": False, "error": {"code": "unauthorized", "message": "bad key"}})
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_kakaowork(KAKAO, "k", text="x", conversation_id="1", session=_session(rec))
    assert exc.value.code == "auth_invalid"
    rec = _Recorder(body={"success": False, "error": {"code": "invalid_parameter", "message": "no such conversation"}})
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_kakaowork(KAKAO, "k", text="x", conversation_id="1", session=_session(rec))
    assert exc.value.code == "invalid_request" and "no such conversation" in (exc.value.detail or "")
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_kakaowork(KAKAO, "", text="x", conversation_id="1", session=_session(_Recorder()))
    assert exc.value.code == "auth_invalid"


# ── 4. 정의·mock·그래프 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("definition, provider", [(DOORAY, "dooray_webhook"), (JANDI, "jandi_webhook"), (KAKAO, "kakaowork")])
def test_정의는_자격증명이_필요한_쓰기_커넥터다(definition, provider):
    assert definition.connector.required_providers() == [provider] and definition.connector.writes_externally(None) is True
    assert not mock_fixtures.validate_mock(definition.mock, definition.connector, label=definition.type)
    assert definition.sideEffect == "external-write"


@pytest.mark.parametrize("scenario, code", [("auth_failed", "auth_invalid"), ("rate_limited", "rate_limited"), ("timeout", "timeout")])
def test_실패_시나리오는_정규화된_코드로(scenario, code):
    transport = mock_fixtures.transport_for(KAKAO.mock, scenario)
    session = KAKAO.new_session(transport=transport, sleep=lambda _s: None)
    with pytest.raises(ConnectorError) as exc:
        team_chat.send_kakaowork(KAKAO, "k", text="x", conversation_id="1", session=session)
    assert exc.value.code == code


def _graph(node_type, data, payload, scenario="success"):
    graph = {"nodes": [{"id": "w1", "type": "webhookNode", "data": {}}, {"id": "s1", "type": node_type, "data": data},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "w1", "target": "s1"}, {"id": "e2", "source": "s1", "target": "o1"}]}
    result = mock_service.run(graph, db=None, project_id=1, entry_node_id="w1", payload=payload, scenario=scenario)
    return result, next(s for s in result["logs"] if s.get("node_id") == "s1")


@pytest.mark.parametrize("node_type, data, url_part", [
    ("doorayNode", {"message": "요약:", "title": "제목"}, None),
    ("jandiNode", {"message": ""}, None),
    ("kakaoWorkNode", {"mode": "send", "conversationId": "42", "message": "결과: {{last_result}}"}, "/v1/messages.send"),
])
def test_목업_그래프에서_보낸_텍스트가_결과로_남는다(node_type, data, url_part):
    result, step = _graph(node_type, data, "직전 출력")
    assert result["success"] is True, result["result"]
    expected = team_chat.compose_message(data.get("message", ""), "직전 출력")
    assert step["result_data"] == expected and step.get("error") is None
    assert len(result["requests"]) == 1 and result["requests"][0]["method"] == "POST"
    if url_part:
        assert url_part in result["requests"][0]["url"]
    assert result["requests"][0]["request_headers"].get("Authorization", "[redacted]") == "[redacted]"


def test_목업_인증_실패는_본문을_남기고_delivery_오류로():
    _, step = _graph("doorayNode", {"message": "요약:"}, "직전 출력", scenario="auth_failed")
    assert step["result_data"].startswith("요약:\n\n직전 출력\n\n[⚠️")
    error = step.get("error") or {}
    # 인증 실패는 delivery 도메인에서도 자격증명 범주(CREDENTIAL_INVALID)로 승격된다 — 사용자가 API 센터로 가야 풀리는 문제라서.
    assert error.get("code") in ("CREDENTIAL_INVALID", "DELIVERY_AUTH_FAILED"), error
    assert error.get("category") in ("credential", "delivery")
