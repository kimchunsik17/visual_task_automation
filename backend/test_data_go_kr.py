"""공공데이터포털 connector 계약 테스트 (한국형 노드 계획 §6.8, Phase 3).

이 파일이 지키는 문장:

  1. **임의 주소를 열지 않는다.** 등록된 데이터셋만 호출한다 — 그러지 않으면
     `httpRequestNode` 와 같아지고, 이용허락범위를 결과에 붙일 방법이 없어진다.
  2. **형식 파라미터 이름이 데이터셋마다 다르다.** 틀리면 오류가 아니라 XML 이 와서
     파서가 조용히 빈 결과를 낸다 — 그래서 둘 다 읽을 수 있어야 한다.
  3. **인증키를 두 번 인코딩하지 않는다.** 포털이 주는 Encoding 키를 그대로 넘기면
     `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 가 난다.
  4. **실패가 200 으로 온다.** 본문 `resultCode` 를 안 보면 '결과 0건' 으로 넘어간다.
  5. **출처 표시를 잃지 않는다.**
"""

from __future__ import annotations

import pytest

import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import data_go_kr as dgk
from connectors.session import ConnectorSession, Response

DEFINITION = node_definition.get_definition("dataGoKrNode")
KEY = "test-service-key"
WEATHER_PARAMS = {"base_date": "20260830", "base_time": "0500", "nx": 98, "ny": 76}


class _Recorder:
    def __init__(self, body=None, status=200):
        self.calls = []
        self.status = status
        self.body = body if body is not None else _ok()

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body)


def _ok(items=None, code="00", total=None):
    rows = items if items is not None else [{"category": "TMP", "fcstValue": "24"}]
    return {"response": {
        "header": {"resultCode": code, "resultMsg": "NORMAL_SERVICE"},
        "body": {"pageNo": 1, "numOfRows": 10,
                 "totalCount": len(rows) if total is None else total,
                 "items": {"item": rows}}}}


def _session(transport):
    return ConnectorSession("공공데이터포털", transport=transport, sleep=lambda _s: None)


def _query(transport, **kwargs):
    kwargs.setdefault("dataset_id", "kma_village_forecast")
    kwargs.setdefault("operation", "forecast")
    kwargs.setdefault("params", dict(WEATHER_PARAMS))
    return dgk.query(DEFINITION, KEY, session=_session(transport), **kwargs)


# ── 1. 임의 주소를 열지 않는다 ──────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "  ", "없는데이터셋", "https://evil.example/api", None])
def test_등록되지_않은_데이터셋은_거부한다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _query(rec, dataset_id=bad)
    assert rec.calls == [], "등록되지 않았는데 요청이 나갔다"
    assert "데이터셋" in (exc.value.detail or "")


def test_거부할_때_쓸_수_있는_것을_알려준다():
    with pytest.raises(ConnectorError) as exc:
        _query(_Recorder(), dataset_id="없음")
    detail = exc.value.detail or ""
    assert all(d in detail for d in dgk.dataset_ids())


def test_없는_동작은_거부한다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _query(rec, operation="아무거나")
    assert rec.calls == []


def test_주소는_registry가_정한다():
    rec = _Recorder()
    _query(rec)
    url = rec.calls[0]["url"]
    assert url == "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"


def test_모든_등록_데이터셋이_공식문서와_대조일을_갖는다():
    """규격을 추측해 넣으면 실행 시점에야 틀린 것을 안다."""
    import datetime

    for key, ds in dgk.DATASETS.items():
        assert ds.docs_url.startswith("https://"), f"{key}: 공식 문서 주소가 없다"
        datetime.date.fromisoformat(ds.verified_at)     # 형식이 틀리면 여기서 터진다
        assert ds.attribution and ds.license_note, f"{key}: 출처·이용허락 정보가 없다"


# ── 2. 형식 파라미터 이름이 데이터셋마다 다르다 ─────────────────────────

def test_데이터셋마다_형식_파라미터_이름이_다르다():
    """이걸 하나로 고정하면 한쪽은 XML 이 와서 조용히 빈 결과가 된다."""
    rec = _Recorder()
    _query(rec)
    assert rec.calls[0]["params"]["dataType"] == "JSON"

    rec2 = _Recorder(body={"response": {"header": {"resultCode": "00"}, "body": {"items": ""}}})
    dgk.query(DEFINITION, KEY, dataset_id="msit_press_release", operation="list",
              session=_session(rec2))
    assert rec2.calls[0]["params"]["returnType"] == "json"
    assert "dataType" not in rec2.calls[0]["params"]


def test_XML로_와도_읽는다():
    """형식 파라미터가 무시되면 XML 이 온다 — 조용히 빈 결과를 내면 안 된다."""
    xml = ("<response><header><resultCode>00</resultCode></header>"
           "<body><totalCount>1</totalCount><items>"
           "<item><category>TMP</category><fcstValue>24</fcstValue></item>"
           "</items></body></response>")
    result = _query(_Recorder(body=xml))
    assert result["items"] == [{"category": "TMP", "fcstValue": "24"}]
    assert result["total"] == 1


def test_XML_항목이_여러_건이면_목록이_된다():
    xml = ("<response><header><resultCode>00</resultCode></header><body><items>"
           "<item><a>1</a></item><item><a>2</a></item></items></body></response>")
    assert _query(_Recorder(body=xml))["items"] == [{"a": "1"}, {"a": "2"}]


def test_한_건이면_dict로_와도_목록으로_만든다():
    """`items.item` 은 1건일 때 dict, 여러 건일 때 list 다."""
    body = {"response": {"header": {"resultCode": "00"},
                         "body": {"items": {"item": {"a": "1"}}}}}
    assert _query(_Recorder(body=body))["items"] == [{"a": "1"}]


@pytest.mark.parametrize("empty", [{}, {"items": ""}, {"items": {}}, {"items": {"item": ""}}])
def test_비어_있는_응답이_터지지_않는다(empty):
    body = {"response": {"header": {"resultCode": "00"}, "body": empty}}
    assert _query(_Recorder(body=body))["items"] == []


# ── 3. 인증키를 두 번 인코딩하지 않는다 ─────────────────────────────────

def test_인코딩된_키를_되돌린다():
    """포털의 Encoding 키를 그대로 넘기면 라이브러리가 한 번 더 인코딩한다."""
    assert dgk.service_key("abc%2Bdef%3D") == "abc+def="


def test_평범한_키는_건드리지_않는다():
    assert dgk.service_key("plain-key-123") == "plain-key-123"


def test_키가_없으면_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        dgk.query(DEFINITION, "", dataset_id="kma_village_forecast",
                  operation="forecast", params=WEATHER_PARAMS, session=_session(rec))
    assert rec.calls == []


# ── 4. 200 인데 실패인 경우 ─────────────────────────────────────────────

@pytest.mark.parametrize("code", ["30", "31", "22", "11", "20", "99"])
def test_상태는_200이어도_본문_오류면_실패로_올린다(code):
    with pytest.raises(ConnectorError) as exc:
        _query(_Recorder(body=_ok(code=code)))
    assert code in (exc.value.detail or "")


def test_인증키_오류를_사람이_알아볼_수_있게_말한다():
    with pytest.raises(ConnectorError) as exc:
        _query(_Recorder(body=_ok(code="30")))
    assert "인증키" in (exc.value.detail or "")


def test_한도_초과를_구분해서_말한다():
    with pytest.raises(ConnectorError) as exc:
        _query(_Recorder(body=_ok(code="22")))
    assert "한도" in (exc.value.detail or "")


def test_모르는_코드는_원문_메시지를_보여준다():
    body = {"response": {"header": {"resultCode": "77", "resultMsg": "UNKNOWN_THING"}, "body": {}}}
    with pytest.raises(ConnectorError) as exc:
        _query(_Recorder(body=body))
    assert "UNKNOWN_THING" in (exc.value.detail or "")


@pytest.mark.parametrize("code", ["00", "0", ""])
def test_정상_코드는_통과한다(code):
    assert _query(_Recorder(body=_ok(code=code)))["items"]


# ── 5. 필수 파라미터와 범위 ─────────────────────────────────────────────

@pytest.mark.parametrize("missing", ["base_date", "base_time", "nx", "ny"])
def test_필수값이_빠지면_보내지_않는다(missing):
    params = {k: v for k, v in WEATHER_PARAMS.items() if k != missing}
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _query(rec, params=params)
    assert rec.calls == [], "필수값이 없는데 요청이 나갔다"
    assert missing in (exc.value.detail or "")


def test_필수값이_없는_데이터셋은_그냥_통과한다():
    rec = _Recorder(body={"response": {"header": {"resultCode": "00"}, "body": {}}})
    dgk.query(DEFINITION, KEY, dataset_id="msit_press_release", operation="list",
              session=_session(rec))
    assert rec.calls, "필수값이 없는데 막혔다"


@pytest.mark.parametrize("given,expected", [
    (None, 10), ("", 10), (0, 10), (-5, 1), (20, 20), (100, 100), (5000, 100), ("abc", 10)])
def test_개수가_범위_안으로_정리된다(given, expected):
    rec = _Recorder()
    _query(rec, rows=given)
    assert rec.calls[0]["params"]["numOfRows"] == expected


def test_동작을_안_주면_첫_번째를_쓴다():
    rec = _Recorder()
    _query(rec, operation=None)
    assert rec.calls[0]["url"].endswith("/getVilageFcst")


# ── 6. 출처 표시 ────────────────────────────────────────────────────────

def test_출처와_이용허락을_결과에_남긴다():
    result = _query(_Recorder())
    assert "기상청" in result["attribution"]
    assert result["license"]
    assert result["docsUrl"].startswith("https://")


def test_어느_데이터셋인지_결과에_적는다():
    result = _query(_Recorder())
    assert result["dataset"] == "kma_village_forecast"
    assert result["datasetLabel"] == "기상청 단기예보"
    assert result["operation"] == "forecast"


# ── 7. 정의와 mock ──────────────────────────────────────────────────────

def test_본문으로_오류를_알리는_API라고_선언돼_있다():
    assert DEFINITION.connector.errorStyle == "body"


def test_mock_이_계약을_지킨다():
    assert mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector,
                                       label="dataGoKrNode") == []


def test_mock_인증실패가_실제로_실패한다():
    transport = mock_fixtures.transport_for(DEFINITION.mock, "auth_failed")
    with pytest.raises(ConnectorError):
        dgk.query(DEFINITION, KEY, dataset_id="kma_village_forecast", operation="forecast",
                  params=WEATHER_PARAMS, session=_session(transport))


def test_mock_성공이_두_건을_돌려준다():
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    result = dgk.query(DEFINITION, KEY, dataset_id="kma_village_forecast", operation="forecast",
                       params=WEATHER_PARAMS, session=_session(transport))
    assert len(result["items"]) == 2


def test_외부_읽기로_분류돼_있다():
    assert DEFINITION.sideEffect == "external-read"
    for mode in DEFINITION.connector.modes:
        assert DEFINITION.connector.writes_externally(mode) is False


def test_정의의_데이터셋_선택지가_registry와_같다():
    """화면에서 고를 수 있는데 실행하면 '등록되지 않았다' 가 나오면 안 된다."""
    options = {o.value for o in DEFINITION.field("dataset").options}
    assert options == set(dgk.dataset_ids())


def test_정의의_동작_선택지가_registry_안에_있다():
    declared = {o.value for o in DEFINITION.field("operation").options}
    known = {op for ds in dgk.DATASETS.values() for op in ds.operations}
    assert declared <= known, f"registry 에 없는 동작: {sorted(declared - known)}"


# ── 8. 생성 코드 ────────────────────────────────────────────────────────

def _source(data):
    from graph import compile_workflow

    return compile_workflow(
        [{"id": "d1", "type": "dataGoKrNode", "data": data, "position": {"x": 0, "y": 0}}], [])


def test_생성_코드에_주소가_박히지_않는다():
    """주소가 박히면 registry 가 무의미해진다."""
    source = _source({"dataset": "kma_village_forecast", "operation": "forecast"})
    assert "apis.data.go.kr" not in source
    assert 'dataset_id="kma_village_forecast"' in source


def test_생성_코드가_인증키를_API센터에서_가져온다():
    assert "_oauth.require_token('data_go_kr'" in _source({"dataset": "msit_press_release"})


def test_망가진_params_JSON이_생성을_깨지_않는다():
    source = _source({"dataset": "kma_village_forecast", "operation": "forecast",
                      "params": "{이건 JSON 이 아니다"})
    assert "params={}" in source
