"""네이버 카페 connector 계약 테스트 (한국형 노드 계획 Phase 2, §4.2).

이 파일이 지키는 문장:

  1. **실수로 게시되지 않는다.** 글쓰기는 되돌릴 수 없다. `confirm` 을 켜지 않으면 요청이
     한 건도 나가지 않아야 한다.
  2. **한글이 깨지지 않는다.** 공식 예제가 URL 인코딩을 **두 번** 한다. 한 번만 하거나,
     이미 인코딩된 값을 라이브러리에 다시 맡기면(세 번째) 제목이 깨진 채 올라간다.
  3. **재시도하지 않는다.** timeout 뒤 재시도는 같은 글을 두 번 올린다 — 한 번 실패하는 것보다 나쁘다.
  4. **검색과 다른 곳으로 간다.** 카페는 HUB 이관 대상이 아니라 개발자센터에 남았다(§4.0).
"""

from __future__ import annotations

from urllib.parse import quote_plus

import pytest

import node_definition
from connectors import mock as mock_fixtures
from connectors.errors import ConnectorError
from connectors.services import naver_cafe
from connectors.session import ConnectorSession, Response

DEFINITION = node_definition.get_definition("naverCafeNode")
TOKEN = "test-access-token"


class _Recorder:
    def __init__(self, status=200, body=None):
        self.calls = []
        self.status = status
        self.body = body if body is not None else {"message": {"status": "200"}}

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return Response(status=self.status, headers={}, body=self.body)


def _session(transport):
    return ConnectorSession("네이버 카페", transport=transport, sleep=lambda _s: None)


def _write(transport, **kwargs):
    kwargs.setdefault("club_id", "12345678")
    kwargs.setdefault("menu_id", "1")
    kwargs.setdefault("subject", "제목")
    kwargs.setdefault("content", "본문")
    return naver_cafe.write_article(DEFINITION, TOKEN, session=_session(transport), **kwargs)


# ── 1. 한글 인코딩 — 두 번이다 ──────────────────────────────────────────

def test_공식_예제와_같이_두_번_인코딩한다():
    """`URLEncoder.encode(URLEncoder.encode(s, "UTF-8"), "MS949")` 와 같은 결과여야 한다."""
    once = quote_plus("카페 가입 인사", encoding="utf-8")
    assert naver_cafe.encode_field("카페 가입 인사") == quote_plus(once)


def test_한_번만_인코딩하면_다른_값이다():
    """한 번만 하면 한글이 깨진다 — 두 결과가 같으면 이 테스트가 의미를 잃는다."""
    once = quote_plus("제목", encoding="utf-8")
    assert naver_cafe.encode_field("제목") != once
    assert naver_cafe.encode_field("제목").startswith("%25")


def test_인코딩된_값을_그대로_body로_보낸다():
    """dict 로 넘기면 HTTP 라이브러리가 **세 번째** 인코딩을 한다."""
    rec = _Recorder()
    _write(rec, subject="한글 제목", content="한글 본문")
    sent = rec.calls[0]["data"]
    assert isinstance(sent, str), "dict 로 넘기면 라이브러리가 다시 인코딩한다"
    assert f"subject={naver_cafe.encode_field('한글 제목')}" in sent
    assert f"content={naver_cafe.encode_field('한글 본문')}" in sent


def test_공백과_특수문자도_함께_인코딩된다():
    body = naver_cafe.form_body({"subject": "A & B 테스트"})
    assert " " not in body and "&" not in body.split("=", 1)[1]


def test_빈_값도_깨지지_않는다():
    assert naver_cafe.encode_field(None) == ""
    assert naver_cafe.encode_field("") == ""


# ── 2. 어디로 보내는가 ──────────────────────────────────────────────────

def test_HUB_가_아니라_개발자센터로_보낸다():
    """검색만 HUB 로 이관됐다 — 카페는 openapi.naver.com 그대로다(§4.0)."""
    rec = _Recorder()
    _write(rec)
    url = rec.calls[0]["url"]
    assert url.startswith("https://openapi.naver.com/v1/cafe/")
    assert "ntruss.com" not in url


def test_글쓰기_경로에_카페와_게시판_id가_들어간다():
    rec = _Recorder()
    _write(rec, club_id="12345678", menu_id="7")
    assert rec.calls[0]["url"].endswith("/v1/cafe/12345678/menu/7/articles")
    assert rec.calls[0]["method"] == "POST"


def test_가입_경로는_members_다():
    rec = _Recorder()
    naver_cafe.join(DEFINITION, TOKEN, club_id="12345678", nickname="개발자",
                    session=_session(rec))
    assert rec.calls[0]["url"].endswith("/v1/cafe/12345678/members")


def test_사용자_토큰으로_인증한다():
    """검색의 NCP 키가 아니라 네이버 로그인 사용자 토큰이다."""
    rec = _Recorder()
    _write(rec)
    headers = rec.calls[0]["headers"]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert "X-NCP-APIGW-API-KEY" not in headers


def test_토큰이_없으면_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        naver_cafe.write_article(DEFINITION, "", club_id="1", menu_id="1",
                                 subject="a", content="b", session=_session(rec))
    assert rec.calls == []


# ── 3. 보내기 전에 거른다 ───────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"club_id": ""}, {"club_id": "카페주소"}, {"club_id": "abc"},
    {"menu_id": ""}, {"menu_id": "자유게시판"},
    {"subject": ""}, {"subject": "   "},
])
def test_잘못된_입력은_보내지_않는다(bad):
    rec = _Recorder()
    with pytest.raises(ConnectorError):
        _write(rec, **bad)
    assert rec.calls == [], "잘못된 값으로 외부에 요청을 보내지 않는다"


def test_너무_긴_제목은_보내지_않는다():
    rec = _Recorder()
    with pytest.raises(ConnectorError) as exc:
        _write(rec, subject="가" * (naver_cafe.MAX_SUBJECT + 1))
    assert rec.calls == []
    # 사유는 detail 에 남는다. `user_message` 는 code 에서 템플릿으로 만들어지므로 우리가
    # 쓴 문구가 그대로 사용자에게 가지는 않는다 — connector 전반의 구조다(ADR-0016).
    assert "제목" in (exc.value.detail or "")


def test_카페_id_안내가_사용자에게_쓸모있다():
    with pytest.raises(ConnectorError) as exc:
        _write(_Recorder(), club_id="abc")
    assert "숫자" in (exc.value.detail or "")


# ── 4. 재시도하지 않는다 ────────────────────────────────────────────────

def test_글쓰기는_멱등하지_않다고_표시한다():
    rec = _Recorder()
    _write(rec)
    # ConnectorSession.request 에 idempotent=False 로 넘어가야 재시도 정책이 막는다.
    assert DEFINITION.connector.retryPolicy.retryNonIdempotent is False


def test_정의가_재시도를_열어두지_않는다():
    """timeout 뒤 재시도는 같은 글을 두 번 올린다."""
    assert DEFINITION.connector.retryPolicy.maxAttempts == 1


def test_timeout_은_한_번만_시도하고_끝난다():
    class _Timeout:
        def __init__(self):
            self.calls = 0

        def __call__(self, method, url, **kwargs):
            self.calls += 1
            raise TimeoutError("timed out")

    transport = _Timeout()
    with pytest.raises(ConnectorError):
        _write(transport)
    assert transport.calls == 1, "쓰기를 재시도하면 중복 게시가 난다"


# ── 5. 미리보기는 아무것도 보내지 않는다 ────────────────────────────────

def test_미리보기는_무엇이_어디에_올라가는지_보여준다():
    result = naver_cafe.preview("write_article", club_id="12345678", menu_id="7",
                                subject="주간 보고", content="본문" * 200)
    assert result["willSend"] is False
    assert result["clubId"] == "12345678" and result["menuId"] == "7"
    assert result["subject"] == "주간 보고"
    assert result["contentLength"] == 400
    assert len(result["contentPreview"]) <= 201


def test_미리보기_요약에_카페와_게시판이_보인다():
    """실행 전에 사용자가 '어디에 올라가는지' 를 볼 수 있어야 한다."""
    summary = naver_cafe.preview("write_article", club_id="123", menu_id="7",
                                 subject="제목")["summary"]
    assert "123" in summary and "7" in summary and "제목" in summary


def test_가입_미리보기도_보낸다고_하지_않는다():
    result = naver_cafe.preview("join", club_id="123", nickname="개발자")
    assert result["willSend"] is False and "개발자" in result["summary"]


def test_confirm_을_켜지_않으면_생성_코드가_요청을_만들지_않는다():
    """노드 기본값이 미리보기다 — 생성된 코드에 호출 자체가 없어야 한다."""
    from graph import compile_workflow

    nodes = [{"id": "c1", "type": "naverCafeNode",
              "data": {"mode": "write_article", "clubId": "1", "menuId": "1",
                       "subject": "제목", "content": "본문"},
              "position": {"x": 0, "y": 0}}]
    source = compile_workflow(nodes, [])
    assert "_naver_cafe.write_article(" not in source, "확인 없이 게시 호출이 생성됐다"
    assert "_naver_cafe.preview(" in source


def test_confirm_을_켜야_실제_호출이_생성된다():
    from graph import compile_workflow

    nodes = [{"id": "c1", "type": "naverCafeNode",
              "data": {"mode": "write_article", "clubId": "1", "menuId": "1",
                       "subject": "제목", "content": "본문", "confirm": True},
              "position": {"x": 0, "y": 0}}]
    source = compile_workflow(nodes, [])
    assert "_naver_cafe.write_article(" in source


def test_노드_기본값이_미리보기다():
    assert DEFINITION.field("confirm").default is False


# ── 6. 정의 정합과 mock ─────────────────────────────────────────────────

def test_외부_쓰기로_분류돼_있다():
    """dry-run 이 막아야 하는 노드다."""
    assert DEFINITION.sideEffect == "external-write"
    for mode in DEFINITION.connector.modes:
        assert DEFINITION.connector.writes_externally(mode) is True


def test_사용자_토큰_자격증명을_요구한다():
    assert DEFINITION.connector.required_providers() == ["naver_user_oauth"]


def test_mock_이_Phase0_계약을_지킨다():
    assert mock_fixtures.validate_mock(DEFINITION.mock, DEFINITION.connector,
                                       label="naverCafeNode") == []


def test_mock_성공이_글_번호를_돌려준다():
    transport = mock_fixtures.transport_for(DEFINITION.mock, "success")
    result = naver_cafe.write_article(DEFINITION, TOKEN, club_id="1", menu_id="1",
                                      subject="제목", content="본문",
                                      session=_session(transport))
    assert result["sent"] is True
    assert result["articleId"] == 12345, "중복 게시를 확인할 근거가 남아야 한다"


def test_정의가_선언한_mode와_구현이_아는_mode가_같다():
    declared = {o.value for o in DEFINITION.field("mode").options}
    assert declared == set(naver_cafe.MODES)
