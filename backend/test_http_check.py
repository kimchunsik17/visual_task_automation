"""httpCheckNode (백로그 34 DEV-2 2차, ADR-0034) — 웹사이트 점검 계약 테스트.

  1. **점검 결과는 실패가 아니다.** 503·키워드 없음·타임아웃은 ok=false 와 problems 로 나온다. 노드가 예외를 내는 것은 URL 이 막혔거나 입력이 틀린 때만.
  2. **변경 감지는 cursor 로.** 지난 해시가 있으면 changed 를 판정하고, 연결 실패 한 번으로 기준 해시를 잃지 않는다.
  3. **인증서·DNS 는 소켓 없이도 판정 로직을 검사한다.** tls_summary 는 getpeercert() dict 를 받고, check() 는 checker 를 주입받는다.
  4. **목업은 끝까지 돈다.** HTTP 는 시나리오, TLS·DNS 는 mock:true 고정값.
"""

from __future__ import annotations

import datetime
import json

import pytest

import mock_service
import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import http_check
from connectors.session import ConnectorSession, Response

DEFINITION = node_definition.get_definition("httpCheckNode")
NOW = datetime.datetime(2026, 9, 19, 0, 0, tzinfo=datetime.timezone.utc)


class _Transport:
    def __init__(self, status=200, body=None, headers=None, raise_timeout=False):
        self.calls = []
        self.status, self.body, self.headers, self.raise_timeout = status, body, headers or {}, raise_timeout

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.raise_timeout:
            raise _Timeout("mock timeout")
        return Response(status=self.status, headers=self.headers, body=self.body)


class _Timeout(Exception):
    pass


_Timeout.__name__ = "ConnectTimeout"


def _session(transport):
    return ConnectorSession("HTTP 점검", transport=transport, sleep=lambda _s: None)


def _tls_ok(host, **kwargs):
    return {"ok": True, "daysLeft": 200, "expiresAt": "2027-04-01T00:00:00+00:00", "issuer": "Test CA", "subject": host}


def _dns_ok(host, **kwargs):
    return {"ok": True, "record": "ANY", "records": ["93.184.216.34"]}


def _check(transport, **kwargs):
    kwargs.setdefault("url", "https://example.com/health")
    kwargs.setdefault("tls_checker", _tls_ok)
    kwargs.setdefault("dns_checker", _dns_ok)
    kwargs.setdefault("now", NOW)
    return http_check.check(DEFINITION, session=_session(transport), **kwargs)


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """SSRF 검사는 DNS 를 해석한다 — 테스트는 네트워크 없이 통과시킨다(정책 자체는 test_url_guard 가 본다)."""
    import url_guard

    monkeypatch.setattr(url_guard, "check_url", lambda url: (url, "example.com"))


# ── 1. 결과는 실패가 아니다 ──────────────────────────────────────────────────

def test_정상_응답은_ok_이고_상태_시간_해시_키워드를_준다():
    t = _Transport(body={"status": "ok", "v": 1}, headers={"Content-Type": "application/json"})
    result = _check(t, keyword='"status": "ok"')
    assert result["ok"] is True and result["problems"] == []
    http = result["http"]
    assert http["status"] == 200 and http["statusOk"] is True and http["keywordFound"] is True
    assert len(http["contentHash"]) == 16 and http["responseMs"] >= 0 and http["contentType"] == "application/json"
    assert result["tls"]["ok"] is True and result["dns"]["records"] == ["93.184.216.34"]
    assert t.calls[0]["headers"]["User-Agent"].startswith("Mozilla/5.0") and t.calls[0]["method"] == "GET"


def test_503_과_키워드_없음은_problems_로_나오고_예외가_아니다():
    result = _check(_Transport(status=503, body="down"), keyword="ok")
    assert result["ok"] is False and result["problems"] == ["http_status", "http_keyword"]
    assert result["http"]["status"] == 503 and result["http"]["keywordFound"] is False
    only_keyword = _check(_Transport(body="hello"), keyword="bye")
    assert only_keyword["problems"] == ["http_keyword"]


def test_타임아웃은_http_unreachable_로_나온다():
    result = _check(_Transport(raise_timeout=True))
    assert result["ok"] is False and "http_unreachable" in result["problems"]
    assert result["http"]["error"] == "timeout" and result["http"]["contentHash"] == ""


@pytest.mark.parametrize("spec, status, ok", [("200-399", 301, True), ("200", 204, False), ("200,204", 204, True), ("2xx", 299, True), ("2xx", 301, False)])
def test_기대_상태_코드_표기(spec, status, ok):
    result = _check(_Transport(status=status, body="x"), expect_status=spec, mode="http")
    assert result["http"]["statusOk"] is ok


@pytest.mark.parametrize("bad", ["abc", "200-", "1-2-3"])
def test_잘못된_기대_상태_표기는_입력_오류(bad):
    with pytest.raises(ConnectorError) as exc:
        _check(_Transport(body="x"), expect_status=bad)
    assert exc.value.code == "invalid_request"


def test_URL_이_비거나_모드가_틀리면_입력_오류_이고_스킴이_없으면_https_로_본다():
    with pytest.raises(ConnectorError):
        _check(_Transport(body="x"), url="")
    with pytest.raises(ConnectorError):
        _check(_Transport(body="x"), mode="ping")
    t = _Transport(body="x")
    result = _check(t, url="example.com/health", mode="http")
    assert t.calls[0]["url"] == "https://example.com/health" and result["url"] == "https://example.com/health"


def test_막힌_주소는_요청_전에_커넥터_오류로_선다(monkeypatch):
    import url_guard

    def block(url):
        raise url_guard.UrlBlocked("사설 주소", reason="PRIVATE")

    monkeypatch.setattr(url_guard, "check_url", block)
    t = _Transport(body="x")
    with pytest.raises(ConnectorError) as exc:
        _check(t, url="http://10.0.0.1/")
    assert exc.value.code == "invalid_request" and t.calls == []


# ── 2. 변경 감지 ──────────────────────────────────────────────────────────────

def test_첫_점검은_firstRun_이고_해시가_바뀌면_changed():
    first = _check(_Transport(body="v1"), mode="http")
    assert first["firstRun"] is True and first["changed"] is False
    cursor = first["cursor"]
    assert cursor["contentHash"] == first["http"]["contentHash"] and cursor["status"] == 200 and cursor["version"] == 1
    same = _check(_Transport(body="v1"), mode="http", previous=cursor)
    assert same["changed"] is False and same["firstRun"] is False and same["previous"]["contentHash"] == cursor["contentHash"]
    changed = _check(_Transport(status=500, body="v2"), mode="http", previous=cursor)
    assert changed["changed"] is True and changed["statusChanged"] is True
    off = _check(_Transport(body="v2"), mode="http", previous=cursor, track_changes=False)
    assert off["changed"] is False and "firstRun" not in off


def test_연결_실패_한_번으로_기준_해시를_잃지_않는다():
    cursor = {"version": 1, "contentHash": "abc", "status": 200, "checkedAt": "x"}
    result = _check(_Transport(raise_timeout=True), mode="http", previous=cursor)
    assert result["cursor"]["contentHash"] == "abc" and result["changed"] is False


def test_JSON_본문은_키_순서가_달라도_같은_해시():
    a = _check(_Transport(body={"a": 1, "b": 2}), mode="http")["http"]["contentHash"]
    b = _check(_Transport(body={"b": 2, "a": 1}), mode="http")["http"]["contentHash"]
    assert a == b and a != http_check.content_hash("other")


# ── 3. 인증서·DNS ───────────────────────────────────────────────────────────

def _cert(days, issuer="Let's Encrypt", cn="example.com"):
    not_after = (NOW + datetime.timedelta(days=days)).strftime("%b %d %H:%M:%S %Y GMT")
    return {"notAfter": not_after, "issuer": ((("organizationName", issuer),),), "subject": ((("commonName", cn),),),
            "subjectAltName": (("DNS", cn), ("DNS", "www." + cn))}


def test_인증서_요약은_남은_일수와_발급자를_주고_경고_일수로_ok_를_판정한다():
    fine = http_check.tls_summary(_cert(60), now=NOW, warn_days=14)
    assert fine["ok"] is True and fine["daysLeft"] == 60 and fine["issuer"] == "Let's Encrypt" and fine["altNames"] == ["example.com", "www.example.com"]
    soon = http_check.tls_summary(_cert(10), now=NOW, warn_days=14)
    assert soon["ok"] is False and soon["daysLeft"] == 10
    broken = http_check.tls_summary({"notAfter": "garbage"}, now=NOW)
    assert broken["ok"] is False and broken["daysLeft"] is None


def test_점검은_인증서와_DNS_문제를_problems_에_싣는다():
    def expiring(host, **kwargs):
        return {"ok": False, "error": "tls_expiring", "daysLeft": 3}

    def unresolved(host, **kwargs):
        return {"ok": False, "error": "dns_unresolved", "records": []}

    result = _check(_Transport(body="x"), tls_checker=expiring, dns_checker=unresolved)
    assert result["problems"] == ["tls_expiring", "dns_unresolved"] and result["cursor"]["tlsDaysLeft"] == 3
    http_only = _check(_Transport(body="x"), url="http://example.com/", tls_checker=expiring)
    assert http_only["tls"]["skipped"] is True and "tls_expiring" not in http_only["problems"], "http 주소는 인증서 점검을 건너뛴다"
    tls_only = _check(_Transport(body="x"), mode="tls", tls_checker=expiring)
    assert "http" not in tls_only and tls_only["problems"] == ["tls_expiring"]


def test_DNS_레코드_종류가_틀리면_입력_오류():
    with pytest.raises(ConnectorError):
        http_check.check_dns("example.com", record="MX")


# ── 4. 정의·mock·그래프 ─────────────────────────────────────────────────────

def test_정의는_자격증명_없는_읽기_전용_커넥터다():
    assert DEFINITION.connector.required_providers() == [] and DEFINITION.connector.writes_externally(None) is False
    assert not mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector, label="httpCheckNode")
    assert set(DEFINITION.connector.modes) == set(http_check.MODES)


def _graph(data, scenario="success"):
    graph = {"nodes": [{"id": "w1", "type": "webhookNode", "data": {}}, {"id": "h1", "type": "httpCheckNode", "data": data},
                       {"id": "o1", "type": "outputNode", "data": {}}],
             "edges": [{"id": "e1", "source": "w1", "target": "h1"}, {"id": "e2", "source": "h1", "target": "o1"}]}
    result = mock_service.run(graph, db=None, project_id=1, entry_node_id="w1", payload={"x": 1}, scenario=scenario)
    return result, next(s for s in result["logs"] if s.get("node_id") == "h1")


def test_목업에서_끝까지_돌고_TLS_DNS_는_고정값이다():
    result, step = _graph({"url": "https://example.com/health", "keyword": '"status": "ok"'})
    assert result["success"] is True, result["result"]
    out = json.loads(step["result_data"])
    assert out["ok"] is True and out["tls"]["mock"] is True and out["dns"]["mock"] is True and out["http"]["status"] == 200
    assert [q["url"] for q in result["requests"]] == ["https://example.com/health"]


def test_목업_503_은_결과이고_failOnProblem_이면_HTTPCHECK_PROBLEM():
    result, step = _graph({"url": "https://example.com/health"}, scenario="server_error")
    out = json.loads(step["result_data"])
    assert out["ok"] is False and "http_status" in out["problems"] and step.get("error") is None
    _, failing = _graph({"url": "https://example.com/health", "failOnProblem": True}, scenario="server_error")
    assert (failing.get("error") or {}).get("code") == "HTTPCHECK_PROBLEM"
    assert "http_status" in (failing["error"].get("safeDetails") or failing["error"].get("safe_details") or {}).get("problems", ["http_status"])
