"""도로명주소 connector 계약 테스트 (한국형 노드 계획 §6.8, Phase 3).

이 파일이 지키는 문장:

  1. **실패를 성공처럼 돌려주지 않는다.** juso 는 승인키가 틀려도 HTTP 200 을 준다 —
     본문 `errorCode` 를 안 보면 "결과 0건" 으로 조용히 넘어간다. 이게 이 API 의 핵심 함정이다.
  2. **모르는 필드를 버리지 않는다.** 규격을 2차 출처에서 모았으므로 우리가 틀렸을 수 있다.
  3. **출처 표시를 잃지 않는다.** 공공데이터는 이용허락범위와 출처 표시가 따라붙는다.
  4. **승인키를 도메인 문제와 구분해서 알린다.** E0002 는 키가 아니라 등록 주소가 틀린 것이다.
"""

from __future__ import annotations

import pytest

import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import juso
from connectors.session import ConnectorSession, Response

DEFINITION = node_definition.get_definition("jusoNode")
KEY = "U01TX-test-key"


class _Recorder:
    def __init__(self, body=None, status=200):
        self.calls = []
        self.status = status
        self.body = body if body is not None else _ok()

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body)


def _common(**kw):
    base = {"totalCount": "1", "currentPage": "1", "countPerPage": "10",
            "errorCode": "0", "errorMessage": "정상"}
    base.update(kw)
    return base


def _ok(items=None, **kw):
    row = {"roadAddr": "부산광역시 금정구 부산대학로63번길 2 (장전동)",
           "jibunAddr": "부산광역시 금정구 장전동 30",
           "engAddr": "2, Busandaehak-ro 63beon-gil, Geumjeong-gu, Busan",
           "zipNo": "46241", "bdNm": "부산대학교", "siNm": "부산광역시",
           "sggNm": "금정구", "emdNm": "장전동", "rn": "부산대학로63번길"}
    return {"results": {"common": _common(**kw), "juso": [row] if items is None else items}}


def _session(transport):
    return ConnectorSession("도로명주소", transport=transport, sleep=lambda _s: None)


def _search(transport, **kwargs):
    kwargs.setdefault("keyword", "부산대학로63번길 2")
    return juso.search(DEFINITION, KEY, session=_session(transport), **kwargs)


# ── 1. 200 인데 실패인 경우 ─────────────────────────────────────────────

@pytest.mark.parametrize("code", ["E0001", "E0002", "E0005", "E0006",
                                  "E0008", "E0009", "E0014"])
def test_상태는_200이어도_본문_오류면_실패로_올린다(code):
    """이걸 안 하면 승인키가 틀려도 '결과 0건' 으로 조용히 지나간다."""
    rec = _Recorder(body={"results": {"common": _common(errorCode=code, errorMessage="원문"),
                                      "juso": []}})
    with pytest.raises(ConnectorError):
        _search(rec)


def test_승인키_오류와_도메인_오류를_구분해_알린다():
    """E0002 는 키가 아니라 **신청할 때 적은 서비스 URL** 이 다른 것이다."""
    rec = _Recorder(body={"results": {"common": _common(errorCode="E0002"), "juso": []}})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    detail = exc.value.detail or ""
    assert "URL" in detail or "주소" in detail
    assert "E0002" in detail


def test_모르는_오류코드는_원문을_그대로_보여준다():
    """지어내는 것보다 낫다."""
    rec = _Recorder(body={"results": {"common": _common(
        errorCode="E9999", errorMessage="알 수 없는 서버 오류"), "juso": []}})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    assert "알 수 없는 서버 오류" in (exc.value.detail or "")


@pytest.mark.parametrize("code", ["0", "00", ""])
def test_정상_코드는_통과한다(code):
    assert _search(_Recorder(body=_ok(errorCode=code)))["total"] == 1


def test_결과가_0건인_것은_오류가_아니다():
    """찾는 주소가 없는 것과 API 가 실패한 것은 다르다."""
    result = _search(_Recorder(body=_ok(items=[], totalCount="0")))
    assert result["items"] == [] and result["total"] == 0


# ── 2. 요청을 어떻게 보내는가 ───────────────────────────────────────────

def test_resultType_json을_매번_명시한다():
    """기본값이 XML 이다 — 빼먹으면 파서가 조용히 빈 결과를 낸다."""
    rec = _Recorder()
    _search(rec)
    assert rec.calls[0]["params"]["resultType"] == "json"


def test_승인키를_confmKey로_보낸다():
    rec = _Recorder()
    _search(rec)
    assert rec.calls[0]["params"]["confmKey"] == KEY


def test_승인키가_없으면_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        juso.search(DEFINITION, "", keyword="주소", session=_session(rec))
    assert rec.calls == []


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_검색어가_비면_보내지_않는다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _search(rec, keyword=bad)
    assert rec.calls == []


def test_너무_긴_검색어는_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _search(rec, keyword="가" * 81)
    assert rec.calls == []


@pytest.mark.parametrize("given,expected", [
    (None, 10), ("", 10), (0, 1), (-5, 1), (5, 5), (100, 100), (500, 100), ("abc", 10),
])
def test_개수가_범위_안으로_정리된다(given, expected):
    """0 을 '안 정함' 으로 읽지 않는다 — 네이버 검색에서 했던 실수다."""
    rec = _Recorder()
    _search(rec, count=given)
    assert rec.calls[0]["params"]["countPerPage"] == expected


@pytest.mark.parametrize("given,expected", [(None, 1), (0, 1), (-3, 1), (2, 2), ("x", 1)])
def test_페이지가_1_아래로_안_내려간다(given, expected):
    rec = _Recorder()
    _search(rec, page=given)
    assert rec.calls[0]["params"]["currentPage"] == expected


@pytest.mark.parametrize("flag,expected", [(True, "Y"), (False, "N")])
def test_옛_주소_포함_여부가_전달된다(flag, expected):
    rec = _Recorder()
    _search(rec, include_history=flag)
    assert rec.calls[0]["params"]["hstryYn"] == expected


def test_읽기_전용이라_일시적_실패는_재시도한다():
    """`idempotent=True` 는 세션이 소비하므로 transport 에는 안 보인다 — **동작**으로 확인한다."""
    class _FlakyThenOk:
        def __init__(self):
            self.calls = 0

        def __call__(self, method, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return Response(status=503, headers={}, body={})
            return Response(status=200, headers={}, body=_ok())

    transport = _FlakyThenOk()
    result = juso.search(DEFINITION, KEY, keyword="부산대", session=_session(transport))
    assert transport.calls == 2, "읽기인데 재시도하지 않았다"
    assert result["total"] == 1


def test_외부_읽기로_분류돼_있다():
    """dry-run 이 막지 않아야 하는 노드다."""
    assert DEFINITION.sideEffect == "external-read"
    for mode in DEFINITION.connector.modes:
        assert DEFINITION.connector.writes_externally(mode) is False


# ── 3. 결과를 어떻게 넘기는가 ───────────────────────────────────────────

def test_아는_필드에_이름을_붙인다():
    item = _search(_Recorder())["items"][0]
    assert item["roadAddress"].startswith("부산광역시")
    assert item["jibunAddress"] == "부산광역시 금정구 장전동 30"
    assert item["zipCode"] == "46241"
    assert item["englishAddress"].startswith("2, Busandaehak-ro")
    assert item["buildingName"] == "부산대학교"


def test_모르는_필드를_버리지_않는다():
    """규격을 2차 출처에서 모았다 — 우리가 틀렸을 때 사용자가 원본에서 찾을 수 있어야 한다."""
    rec = _Recorder(body=_ok(items=[{"roadAddr": "어떤 주소", "새로운필드": "값"}]))
    item = _search(rec)["items"][0]
    assert item["raw"]["새로운필드"] == "값"
    assert item["roadAddress"] == "어떤 주소"


def test_없는_필드는_지어내지_않는다():
    rec = _Recorder(body=_ok(items=[{"roadAddr": "어떤 주소"}]))
    item = _search(rec)["items"][0]
    assert "zipCode" not in item and "englishAddress" not in item


def test_출처_표시를_결과에_남긴다():
    """공공데이터는 이용허락범위와 출처 표시 요구가 따라붙는다(§6.8)."""
    assert "행정안전부" in _search(_Recorder())["attribution"]


def test_totalCount가_문자열이어도_숫자로_넘긴다():
    assert _search(_Recorder(body=_ok(totalCount="1234")))["total"] == 1234


def test_totalCount가_이상해도_터지지_않는다():
    result = _search(_Recorder(body=_ok(totalCount="많음")))
    assert result["total"] == len(result["items"])


@pytest.mark.parametrize("body", [{}, {"results": None}, {"results": {}},
                                  {"results": {"juso": None}}, "문자열"])
def test_응답_모양이_달라도_터지지_않는다(body):
    """공공 API 는 예고 없이 모양이 바뀐다. 우리가 500 을 내면 안 된다."""
    result = _search(_Recorder(body=body))
    assert result["items"] == [] and result["mode"] == "search"


# ── 4. 정의와 mock ──────────────────────────────────────────────────────

def test_본문으로_오류를_알리는_API라고_선언돼_있다():
    """이 선언이 없으면 mock 계약이 401 을 요구해서, 실제로 없는 상황을 재현한 fixture 가 된다."""
    assert DEFINITION.connector.errorStyle == "body"


def test_mock_이_계약을_지킨다():
    assert mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector,
                                       label="jusoNode") == []


def test_mock_성공이_두_건을_돌려준다():
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    result = juso.search(DEFINITION, KEY, keyword="부산대", session=_session(transport))
    assert len(result["items"]) == 2
    assert all(i.get("roadAddress") for i in result["items"])


def test_mock_인증실패가_실제로_실패한다():
    """mock 이 성공처럼 통과하면 fixture 로서 값이 없다."""
    transport = mock_fixtures.transport_for(DEFINITION.mock, "auth_failed")
    with pytest.raises(ConnectorError):
        juso.search(DEFINITION, KEY, keyword="부산대", session=_session(transport))


def test_정의가_선언한_mode와_구현이_아는_mode가_같다():
    assert set(DEFINITION.connector.modes) == set(juso.MODES)


def test_승인키_provider를_요구한다():
    assert DEFINITION.connector.required_providers() == ["juso"]


def test_공식문서를_아직_대조하지_못했음이_기록돼_있다():
    """`verifiedAt` 이 채워져 있으면 '확인했다' 는 뜻이다. 아직 아니다 — 거짓을 남기지 않는다."""
    assert DEFINITION.connector.verifiedAt is None
    assert DEFINITION.connector.docsUrl


# ── 5. 노드 실행 경로 ───────────────────────────────────────────────────

def _source(data):
    from graph import compile_workflow

    return compile_workflow(
        [{"id": "j1", "type": "jusoNode", "data": data, "position": {"x": 0, "y": 0}}], [])


def test_검색어가_비면_직전_노드_출력을_쓴다():
    source = _source({})
    assert "or str(last_result or '').strip()" in source


def test_생성_코드가_승인키를_API센터에서_가져온다():
    assert "_oauth.require_token('juso'" in _source({"keyword": "부산대"})


@pytest.mark.parametrize("given,expected", [(5, 5), (0, 10), (999, 100), ("abc", 10)])
def test_생성_코드의_개수도_범위_안이다(given, expected):
    assert f"count={expected}," in _source({"keyword": "부산대", "count": given})
