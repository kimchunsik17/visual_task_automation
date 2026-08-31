"""네이버 검색 connector 계약 테스트 (한국형 노드 계획 Phase 2, §4.2).

이 파일이 지키는 문장:

  1. **HUB 계약대로 부른다.** 호스트·헤더·경로가 옛 개발자센터와 다르다(§4.0). 하나라도 옛것으로
     돌아가면 401 이나 404 를 받는데, 그건 사용자 입장에서 "왜 안 되는지 모르는" 실패다.
  2. **호출 전에 거른다.** 범위 밖 값은 HUB 가 400 으로 돌려주지만, 그건 일 25,000건 한도를
     축내며 배우는 것이다. 고칠 수 있는 입력은 나가기 전에 잡는다.
  3. **원문을 그대로 흘리지 않는다.** 네이버는 검색어에 `<b>` 를 씌워 준다. 그대로 두면 LLM
     프롬프트와 문서에 태그가 섞인다.
  4. **오류 두 형태를 모두 다룬다.** 게이트웨이(401)와 검색(400)의 응답 모양이 다르다.
"""

from __future__ import annotations

import pytest

import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import naver_search
from connectors.session import ConnectorSession, Response

DEFINITION = node_definition.get_definition("naverSearchNode")
KEY = "test-key-id:test-key-secret"


class _Recorder:
    """호출 내용을 잡아 두는 transport. 무엇을 어디로 보냈는지 검사한다."""

    def __init__(self, status=200, body=None):
        self.calls = []
        self.status = status
        self.body = body if body is not None else {"total": 0, "start": 1, "display": 0, "items": []}

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body)


def _session(transport):
    return ConnectorSession("네이버 검색", transport=transport, sleep=lambda _s: None)


def _search(transport, **kwargs):
    kwargs.setdefault("query", "부산 맛집")
    return naver_search.search(DEFINITION, KEY, session=_session(transport), **kwargs)


# ── 1. HUB 계약대로 부른다 ──────────────────────────────────────────────

def test_옛_개발자센터가_아니라_HUB_호스트로_부른다():
    """2026-06-25 이관. openapi.naver.com 으로 가면 안 된다(§4.0)."""
    rec = _Recorder()
    _search(rec)
    url = rec.calls[0]["url"]
    assert url.startswith("https://naverapihub.apigw.ntruss.com/search/v1/")
    assert "openapi.naver.com" not in url


@pytest.mark.parametrize("mode, path", [("blog", "/search/v1/blog"),
                                        ("cafe_article", "/search/v1/cafearticle")])
def test_모드마다_정해진_경로로_간다(mode, path):
    """2026-08-30 실제 키로 호출해 200 을 확인한 경로다."""
    rec = _Recorder()
    _search(rec, mode=mode)
    assert rec.calls[0]["url"].endswith(path)


def test_NCP_게이트웨이_헤더로_인증한다():
    """옛 X-Naver-Client-Id/Secret 이 아니다."""
    rec = _Recorder()
    _search(rec)
    headers = rec.calls[0]["headers"]
    assert headers["X-NCP-APIGW-API-KEY-ID"] == "test-key-id"
    assert headers["X-NCP-APIGW-API-KEY"] == "test-key-secret"
    assert "X-Naver-Client-Id" not in headers


def test_검색어와_옵션을_그대로_싣는다():
    rec = _Recorder()
    _search(rec, query="부산 맛집", display=5, sort="date")
    params = rec.calls[0]["params"]
    assert params["query"] == "부산 맛집"
    assert params["display"] == 5
    assert params["sort"] == "date"


# ── 2. 호출 전에 거른다 ─────────────────────────────────────────────────

def test_키_형식이_어긋나면_호출하지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        naver_search.search(DEFINITION, "콜론없는키", session=_session(rec), query="x")
    assert exc.value.code == "auth_invalid"
    assert rec.calls == [], "형식이 틀린 키로 한도를 축내지 않는다"


@pytest.mark.parametrize("bad", [{"query": ""}, {"query": "   "}])
def test_검색어가_비면_호출하지_않는다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        naver_search.search(DEFINITION, KEY, session=_session(rec), **bad)
    assert rec.calls == []


def test_모르는_검색_대상은_호출하지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _search(rec, mode="쇼핑")
    assert "쇼핑" in (exc.value.detail or "")
    assert rec.calls == []


def test_잘못된_정렬값은_호출하지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _search(rec, sort="아무거나")
    assert rec.calls == []


@pytest.mark.parametrize("given, sent", [(0, 1), (999, 100), (-5, 1), (100, 100), (10, 10)])
def test_개수를_허용_범위로_맞춰_보낸다(given, sent):
    """HUB 는 범위 밖이면 SE02 로 거절한다 — 한도를 축내며 배울 이유가 없다."""
    rec = _Recorder()
    _search(rec, display=given)
    assert rec.calls[0]["params"]["display"] == sent


def test_시작_위치도_범위로_맞춘다():
    rec = _Recorder()
    _search(rec, start=99999)
    assert rec.calls[0]["params"]["start"] == naver_search.MAX_START


# ── 3. 원문을 그대로 흘리지 않는다 ──────────────────────────────────────

BLOG_BODY = {
    "total": 20829413, "start": 1, "display": 1,
    "items": [{
        "title": "[코딩<b>테스트</b>] 구현 &amp; 알고리즘",
        "link": "https://blog.example.com/1",
        "description": "<b>테스트</b> 준비 &lt;글&gt;입니다.",
        "bloggername": "예시 블로그",
        "bloggerlink": "https://blog.example.com",
        "postdate": "20260829",
    }],
}


def test_강조_태그와_entity_를_걷어낸다():
    result = _search(_Recorder(body=BLOG_BODY))
    item = result["items"][0]
    assert item["title"] == "[코딩테스트] 구현 & 알고리즘"
    assert item["description"] == "테스트 준비 <글>입니다."
    assert "<b>" not in item["title"]


def test_원문도_함께_남긴다():
    """걷어낸 것이 원본을 지우는 것은 아니다 — 필요하면 볼 수 있어야 한다."""
    item = _search(_Recorder(body=BLOG_BODY))["items"][0]
    assert item["titleRaw"] == "[코딩<b>테스트</b>] 구현 &amp; 알고리즘"
    assert item["raw"]["bloggername"] == "예시 블로그"


def test_블로그_결과를_공통_모양으로_준다():
    item = _search(_Recorder(body=BLOG_BODY))["items"][0]
    assert item["link"] == "https://blog.example.com/1"
    assert item["author"] == "예시 블로그"
    assert item["publishedAt"] == "20260829"
    assert item["source"] == "blog"


CAFE_BODY = {
    "total": 10162808, "start": 1, "display": 1,
    "items": [{
        "title": "카페 <b>테스트</b> 글",
        "link": "https://cafe.naver.com/example/1",
        "description": "카페 본문 요약",
        "cafename": "예시 카페",
        "cafeurl": "https://cafe.naver.com/example",
    }],
}


def test_카페글도_같은_모양으로_준다():
    """블로그와 필드 이름이 다르다(cafename/cafeurl). 하류가 그 차이를 몰라도 되게 한다."""
    item = _search(_Recorder(body=CAFE_BODY), mode="cafe_article")["items"][0]
    assert item["title"] == "카페 테스트 글"
    assert item["author"] == "예시 카페"
    assert item["authorLink"] == "https://cafe.naver.com/example"
    assert item["source"] == "cafe_article"


def test_카페글에_없는_작성일을_지어내지_않는다():
    item = _search(_Recorder(body=CAFE_BODY), mode="cafe_article")["items"][0]
    assert item["publishedAt"] == ""


def test_전체_결과_수와_검색어를_함께_돌려준다():
    result = _search(_Recorder(body=BLOG_BODY), query="부산 맛집")
    assert result["total"] == 20829413
    assert result["query"] == "부산 맛집"
    assert result["mode"] == "blog"
    assert result["display"] == 1


def test_결과가_없어도_깨지지_않는다():
    result = _search(_Recorder(body={"total": 0, "items": []}))
    assert result["items"] == [] and result["total"] == 0


def test_응답이_JSON이_아니어도_깨지지_않는다():
    result = _search(_Recorder(body="이건 JSON이 아니다"))
    assert result["items"] == []


# ── 4. 오류 두 형태 ─────────────────────────────────────────────────────

def test_게이트웨이_인증실패를_자격증명_오류로_분류한다():
    """401 은 `{"error": {...}}` 형태로 온다(2026-08-30 실제 응답)."""
    rec = _Recorder(status=401, body={"error": {"errorCode": "200",
                                                "message": "Authentication Failed",
                                                "details": "Invalid authentication information."}})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    assert exc.value.code == "auth_invalid"
    assert exc.value.needs_credential is True


def test_검색쪽_거절은_입력_오류로_분류한다():
    """400 은 `{"errorMessage": ..., "errorCode": "SE01"}` — 위와 모양이 다르다."""
    rec = _Recorder(status=400, body={"errorMessage": "Incorrect query request", "errorCode": "SE01"})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    assert exc.value.code == "invalid_request"
    assert exc.value.retryable is False


def test_호출_한도는_잠시_뒤_다시_시도한다():
    rec = _Recorder(status=429, body={"error": {"message": "Too Many Requests"}})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    assert exc.value.code == "rate_limited"
    assert exc.value.retryable is True


def test_상대_서비스_원문이_사용자_문구에_새지_않는다():
    """ADR-0016 — 영어 원문 대신 고칠 수 있는 안내를 준다."""
    rec = _Recorder(status=401, body={"error": {"details": "Invalid authentication information."}})
    with pytest.raises(ConnectorError) as exc:
        _search(rec)
    assert "Invalid authentication" not in exc.value.user_message
    assert "네이버 검색" in exc.value.user_message


# ── 5. mock 시나리오가 실제 응답과 같은 모양인가 ────────────────────────

def test_mock_이_Phase0_계약을_지킨다():
    problems = mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector,
                                           label="naverSearchNode")
    assert problems == []


@pytest.mark.parametrize("mode", ["blog", "cafe_article"])
def test_mock_성공_시나리오가_실제와_같은_경로로_동작한다(mode):
    """mock 과 실제의 계약이 갈라지면 '목업에선 됐는데' 가 생긴다(ADR-0009)."""
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    result = naver_search.search(DEFINITION, KEY, mode=mode, query="테스트",
                                 session=_session(transport))
    assert result["items"], "mock 성공 시나리오가 결과를 주지 않는다"
    assert result["items"][0]["source"] == mode
    assert "<b>" not in result["items"][0]["title"]


def test_mock_인증실패가_실제와_같은_코드로_분류된다():
    transport = mock_fixtures.transport_for(DEFINITION.mock, "auth_failed")
    with pytest.raises(ConnectorError) as exc:
        naver_search.search(DEFINITION, KEY, query="테스트", session=_session(transport))
    assert exc.value.code == "auth_invalid"


# ── 6. 정의와 구현이 어긋나지 않는다 ────────────────────────────────────

def test_정의가_선언한_mode와_구현이_아는_mode가_같다():
    declared = {o.value for o in DEFINITION.field("mode").options}
    assert declared == set(naver_search.MODE_PATHS)


def test_읽기_전용으로_선언돼_있다():
    """검색은 외부 상태를 바꾸지 않는다 — dry-run 이 막으면 안 된다."""
    assert DEFINITION.sideEffect == "external-read"
    for mode in DEFINITION.connector.modes:
        assert DEFINITION.connector.writes_externally(mode) is False


def test_HUB_자격증명을_요구한다():
    assert DEFINITION.connector.required_providers() == ["naver_api_hub"]


def test_값이_없을_때만_기본값을_쓴다():
    """`or` 로 기본값을 주면 0 이 '미지정' 으로 오인된다 — 위 케이스가 그걸 잡았다."""
    rec = _Recorder()
    _search(rec, display=None, start=None)
    assert rec.calls[0]["params"]["display"] == 10
    assert rec.calls[0]["params"]["start"] == 1


def test_숫자가_아닌_개수는_호출하지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _search(rec, display="열개")
    assert rec.calls == []


# ── 7. Trigger: 새 결과만 알린다 ────────────────────────────────────────
# 첫 실행에 과거를 쏟아내거나, 밀려났다 돌아온 항목을 다시 알리는 것이 트리거의 두 가지
# 흔한 실패다. rssTriggerNode 가 후자를 겪었다(계획 §2 불일치 12).

TRIGGER_DEF = node_definition.get_definition("naverSearchTriggerNode")


def _body(*links):
    return {"total": 100, "start": 1, "display": len(links),
            "items": [{"title": f"글 {i}", "link": link, "description": "",
                       "bloggername": "b", "bloggerlink": "", "postdate": "20260830"}
                      for i, link in enumerate(links)]}


def _poll(transport, cursor=None, **kwargs):
    return naver_search.poll_new_results(TRIGGER_DEF, KEY, query="테스트",
                                         cursor=cursor, session=_session(transport), **kwargs)


def test_첫_실행은_기준점만_잡는다():
    """켠 순간 과거 결과가 쏟아지면 안 된다."""
    result = _poll(_Recorder(body=_body("a", "b", "c")))
    assert result["first_run"] is True
    assert result["items"] == []
    assert set(result["cursor"]["seen_links"]) == {"a", "b", "c"}


def test_두_번째부터_새_글만_알린다():
    first = _poll(_Recorder(body=_body("a", "b")))
    second = _poll(_Recorder(body=_body("c", "a", "b")), cursor=first["cursor"])
    assert [i["link"] for i in second["items"]] == ["c"]
    assert second["first_run"] is False


def test_같은_결과를_다시_보면_알리지_않는다():
    first = _poll(_Recorder(body=_body("a", "b")))
    second = _poll(_Recorder(body=_body("a", "b")), cursor=first["cursor"])
    assert second["items"] == []


def test_밀려났다_돌아온_항목을_다시_알리지_않는다():
    """겹침 창이 없으면 여기서 재통지가 난다 — rssTriggerNode 가 겪은 문제다."""
    first = _poll(_Recorder(body=_body("a", "b")))
    # a 가 피드에서 밀려났다가
    second = _poll(_Recorder(body=_body("c", "b")), cursor=first["cursor"])
    assert [i["link"] for i in second["items"]] == ["c"]
    # 다시 돌아온다
    third = _poll(_Recorder(body=_body("a", "c", "b")), cursor=second["cursor"])
    assert third["items"] == [], "밀려났다 돌아온 항목을 새 글로 알렸다"


def test_겹침_창에_상한이_있다():
    """무한히 쌓이면 cursor 가 커지고 저장이 느려진다."""
    cursor = None
    for batch in range(6):
        links = [f"b{batch}-{i}" for i in range(100)]
        cursor = _poll(_Recorder(body=_body(*links)), cursor=cursor)["cursor"]
    assert len(cursor["seen_links"]) <= naver_search.SEEN_WINDOW


def test_트리거는_항상_최신순으로_본다():
    """정확도순으로 폴링하면 새 글이 상위에 못 올라와 영영 놓친다."""
    rec = _Recorder(body=_body("a"))
    _poll(rec)
    assert rec.calls[0]["params"]["sort"] == "date"


def test_모르는_cursor_형식은_첫_실행으로_강등하지_않는다():
    """강등하면 조용히 과거를 다시 알린다 — 시끄럽게 실패하는 편이 낫다."""
    with pytest.raises(ConnectorError):
        _poll(_Recorder(body=_body("a")), cursor={"version": 99, "seen_links": ["a"]})


def test_트리거는_시작점이라_입력_포트가_없다():
    assert TRIGGER_DEF.inputs == []
    assert TRIGGER_DEF.category == "trigger"


def test_확인_주기에_1분은_없다():
    """1분이면 워크플로 17개에서 하루 한도가 찬다(계획 §4.0)."""
    values = {o.value for o in TRIGGER_DEF.field("pollInterval").options}
    assert "1m" not in values
    assert TRIGGER_DEF.field("pollInterval").default == "10m"


# ── 8. 하루 한도를 우리가 먼저 센다 ─────────────────────────────────────

class _FakeDb:
    """rate_limit.hit 이 쓰는 최소 인터페이스."""

    def __init__(self):
        self.counts = {}

    def execute(self, statement, params):
        key = params["key"]
        self.counts[key] = self.counts.get(key, 0) + 1
        value = self.counts[key]

        class _R:
            def scalar(self_inner):
                return value
        return _R()

    def commit(self):
        pass


def test_호출을_셀_때마다_남은_양을_알려준다():
    db = _FakeDb()
    first = naver_search.consume_quota(db, owner_user_id=1)
    assert first["used"] == 1 and first["limit"] == 25000
    assert first["remaining"] == 24999


def test_한도를_넘으면_호출하지_않고_멈춘다(monkeypatch):
    import rate_limit

    # 25,000번을 실제로 돌 이유가 없다 — 한도만 낮춰 경계 동작을 본다.
    monkeypatch.setattr(rate_limit, "rule_for",
                        lambda action, **kw: rate_limit.Rule(limit=2, window_seconds=86400))
    db = _FakeDb()
    naver_search.consume_quota(db, owner_user_id=1)
    naver_search.consume_quota(db, owner_user_id=1)
    with pytest.raises(ConnectorError) as exc:
        naver_search.consume_quota(db, owner_user_id=1)
    assert exc.value.code == "rate_limited"
    assert exc.value.retryable is True, "다음 날이면 풀린다 — 고쳐지는 실패다"


def test_한도는_사용자별로_따로_센다():
    db = _FakeDb()
    naver_search.consume_quota(db, owner_user_id=1)
    other = naver_search.consume_quota(db, owner_user_id=2)
    assert other["used"] == 1, "남의 사용량이 내 한도를 깎으면 안 된다"


def test_db가_없으면_세지_않고_넘어간다():
    """에디터 미리보기처럼 db 없이 도는 경로에서 죽지 않는다."""
    assert naver_search.consume_quota(None, owner_user_id=1)["limit"] == 0
