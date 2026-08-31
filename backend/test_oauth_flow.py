"""인가 코드 흐름 계약 테스트 (한국형 노드 계획 Phase 0).

이 파일이 지키는 문장들:

  1. **state 는 서버가 만들고 한 번만 쓴다.** 재사용·만료·provider 불일치는 전부 거부한다.
  2. **redirect_uri 는 요청이 정하지 않는다.** allowlist 밖 주소로는 절대 나가지 않는다.
  3. **동의 후 돌아갈 주소는 우리 사이트 안이어야 한다.** 열린 리다이렉터가 되지 않는다.
  4. **PKCE 는 선언대로 동작한다.** 켜면 challenge 가 나가고 verifier 로 교환한다.
  5. **토큰은 암호화되어 저장되고 평문이 새지 않는다.**
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors import oauth, oauth_flow, providers
from credential_crypto import decrypt_secret, encrypt_secret
from database import Base

PROVIDER = "naver_user_oauth"
CLIENT_PROVIDER = "naver_oauth_client"


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(models.User(id=1, name="u1", email="u1@t.com", role="user"))
    session.add(models.User(id=2, name="u2", email="u2@t.com", role="user"))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def app_credential(db):
    """네이버 로그인 앱 자격증명이 등록된 상태."""
    db.add(models.UserApiKey(user_id=1, provider=CLIENT_PROVIDER,
                             api_key=encrypt_secret("naver-client-id:naver-client-secret")))
    db.commit()


@pytest.fixture(autouse=True)
def fixed_redirect_base(monkeypatch):
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "https://wa-pnu.duckdns.org,http://localhost:5173")


def _fake_token_endpoint(captured):
    def post_form(token_url, data, timeout):
        captured.append({"url": token_url, "data": dict(data)})
        return {"access_token": "AT-new", "refresh_token": "RT-new", "expires_in": 3600}
    return post_form


# ── 선언 자체 ───────────────────────────────────────────────────────────

def test_authorize_선언이_있는_provider만_흐름을_시작한다(db, app_credential):
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.build_authorization_url("openai", 1, db)
    assert exc.value.reason == "NOT_AN_OAUTH_PROVIDER"


def test_앱_자격증명이_없으면_시작하지_않고_무엇을_등록할지_알려준다(db):
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.build_authorization_url(PROVIDER, 1, db)
    assert exc.value.reason == "CLIENT_CREDENTIAL_MISSING"
    assert "네이버 로그인 앱" in str(exc.value)


# ── redirect_uri: 요청이 정하지 않는다 ──────────────────────────────────

def test_콜백_주소는_설정된_base에서만_만들어진다():
    assert oauth_flow.callback_url(PROVIDER) == \
        f"https://wa-pnu.duckdns.org/api/oauth/{PROVIDER}/callback"
    assert oauth_flow.callback_url(PROVIDER, base="http://localhost:5173") == \
        f"http://localhost:5173/api/oauth/{PROVIDER}/callback"


def test_allowlist_밖의_콜백_주소는_거부한다():
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.callback_url(PROVIDER, base="https://evil.example.com")
    assert exc.value.reason == "REDIRECT_NOT_ALLOWED"


# ── return_to: 열린 리다이렉터가 되지 않는다 ────────────────────────────

@pytest.mark.parametrize("value", [
    "https://evil.example.com/steal",
    "//evil.example.com",            # 스킴 상대 URL — '/' 로 시작한다고 통과시키면 놓친다
    "http://localhost:5173/x",
    "javascript:alert(1)",
    "api-center",                    # 상대 경로지만 '/' 로 시작하지 않는다
])
def test_사이트_밖으로_돌려보내지_않는다(value):
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.safe_return_to(value)
    assert exc.value.reason == "BAD_RETURN_TO"


def test_사이트_안_경로는_허용한다():
    assert oauth_flow.safe_return_to("/api-center?connected=1") == "/api-center?connected=1"
    assert oauth_flow.safe_return_to(None) is None


# ── 1단계: 동의 URL ─────────────────────────────────────────────────────

def test_동의_URL과_저장된_state가_짝을_이룬다(db, app_credential):
    from urllib.parse import parse_qs, urlparse

    result = oauth_flow.build_authorization_url(PROVIDER, 1, db, return_to="/api-center")
    query = parse_qs(urlparse(result["url"]).query)

    assert urlparse(result["url"]).netloc == "nid.naver.com"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["naver-client-id"]
    assert query["redirect_uri"] == [f"https://wa-pnu.duckdns.org/api/oauth/{PROVIDER}/callback"]
    assert query["state"] == [result["state"]]
    # client_secret 은 동의 URL(브라우저에 노출된다)에 절대 실리지 않는다
    assert "naver-client-secret" not in result["url"]

    row = db.query(models.OAuthState).filter_by(state=result["state"]).one()
    assert row.user_id == 1 and row.provider == PROVIDER
    assert row.return_to == "/api-center" and row.consumed_at is None


def test_네이버는_scope_파라미터를_싣지_않는다(db, app_credential):
    """요청 때가 아니라 개발자센터 설정에서 권한이 정해지는 provider다."""
    result = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    assert "scope=" not in result["url"]


def test_PKCE를_켠_provider는_challenge를_싣고_verifier를_저장한다(db):
    db.add(models.UserApiKey(user_id=1, provider="google_oauth_client",
                             api_key=encrypt_secret("g-id:g-secret")))
    db.commit()
    from urllib.parse import parse_qs, urlparse

    result = oauth_flow.build_authorization_url("google_oauth", 1, db)
    query = parse_qs(urlparse(result["url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]

    row = db.query(models.OAuthState).filter_by(state=result["state"]).one()
    verifier = decrypt_secret(row.code_verifier)
    assert verifier and verifier not in result["url"], "verifier 는 절대 URL 에 실리지 않는다"

    # challenge 가 실제로 verifier 의 S256 이다
    import base64, hashlib
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert query["code_challenge"] == [expected]


def test_구글은_refresh_token을_받기_위한_파라미터를_함께_보낸다(db):
    db.add(models.UserApiKey(user_id=1, provider="google_oauth_client",
                             api_key=encrypt_secret("g-id:g-secret")))
    db.commit()
    url = oauth_flow.build_authorization_url("google_oauth", 1, db)["url"]
    assert "access_type=offline" in url and "prompt=consent" in url


# ── 2단계: 토큰 교환 ────────────────────────────────────────────────────

def test_교환하면_토큰이_암호화되어_저장된다(db, app_credential):
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db, return_to="/api-center")
    captured = []
    result = oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                                      post_form=_fake_token_endpoint(captured))

    assert result["user_id"] == 1 and result["return_to"] == "/api-center"
    row = db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).one()
    assert decrypt_secret(row.api_key) == "AT-new"
    assert decrypt_secret(row.refresh_token) == "RT-new"
    assert row.api_key != "AT-new", "평문으로 저장되면 안 된다"
    assert row.token_expires_at is not None


def test_교환_요청이_인가_때와_같은_redirect_uri를_쓴다(db, app_credential):
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    captured = []
    oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                             post_form=_fake_token_endpoint(captured))
    sent = captured[0]["data"]
    assert sent["redirect_uri"] == f"https://wa-pnu.duckdns.org/api/oauth/{PROVIDER}/callback"
    assert sent["grant_type"] == "authorization_code"
    assert sent["client_secret"] == "naver-client-secret"
    # 네이버는 토큰 교환에도 state 를 요구한다
    assert sent["state"] == started["state"]


def test_PKCE_provider는_verifier로_교환한다(db):
    db.add(models.UserApiKey(user_id=1, provider="google_oauth_client",
                             api_key=encrypt_secret("g-id:g-secret")))
    db.commit()
    started = oauth_flow.build_authorization_url("google_oauth", 1, db)
    row = db.query(models.OAuthState).filter_by(state=started["state"]).one()
    verifier = decrypt_secret(row.code_verifier)

    captured = []
    oauth_flow.exchange_code("google_oauth", db, code="CODE", state=started["state"],
                             post_form=_fake_token_endpoint(captured))
    assert captured[0]["data"]["code_verifier"] == verifier


def test_refresh_token이_안_오면_기존_값을_지우지_않는다(db, app_credential):
    """구글은 첫 동의에만 refresh_token 을 준다 — 지우면 자동 갱신이 영영 끊긴다."""
    db.add(models.UserApiKey(user_id=1, provider=PROVIDER,
                             api_key=encrypt_secret("AT-old"), refresh_token=encrypt_secret("RT-keep")))
    db.commit()
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                             post_form=lambda u, d, t: {"access_token": "AT-2", "expires_in": 3600})

    row = db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).one()
    assert decrypt_secret(row.api_key) == "AT-2"
    assert decrypt_secret(row.refresh_token) == "RT-keep"


# ── state: 위조·재사용·만료 ─────────────────────────────────────────────

def test_모르는_state는_거부한다(db, app_credential):
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.exchange_code(PROVIDER, db, code="CODE", state="공격자가-지어낸-값",
                                 post_form=_fake_token_endpoint([]))
    assert exc.value.reason == "STATE_UNKNOWN"


def test_같은_state를_두_번_쓰지_못한다(db, app_credential):
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    captured = []
    oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                             post_form=_fake_token_endpoint(captured))
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                                 post_form=_fake_token_endpoint(captured))
    assert exc.value.reason == "STATE_ALREADY_USED"
    assert len(captured) == 1, "거부된 두 번째 시도는 토큰 endpoint 를 부르지 않는다"


def test_만료된_state는_거부한다(db, app_credential):
    past = datetime.datetime.utcnow() - datetime.timedelta(minutes=oauth_flow.STATE_TTL_MINUTES + 1)
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db, now=past)
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                                 post_form=_fake_token_endpoint([]))
    assert exc.value.reason == "STATE_EXPIRED"


def test_다른_provider의_state로는_교환하지_못한다(db, app_credential):
    db.add(models.UserApiKey(user_id=1, provider="google_oauth_client",
                             api_key=encrypt_secret("g-id:g-secret")))
    db.commit()
    started = oauth_flow.build_authorization_url("google_oauth", 1, db)
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                                 post_form=_fake_token_endpoint([]))
    assert exc.value.reason == "STATE_PROVIDER_MISMATCH"


def test_토큰은_state의_주인에게_저장된다(db, app_credential):
    """콜백에는 로그인 세션이 없을 수도 있다 — 소유자는 state 가 정한다."""
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                             post_form=_fake_token_endpoint([]))
    assert db.query(models.UserApiKey).filter_by(user_id=2, provider=PROVIDER).first() is None
    assert db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).first() is not None


def test_access_token이_없는_응답은_저장하지_않는다(db, app_credential):
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    with pytest.raises(oauth_flow.OAuthFlowError) as exc:
        oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                                 post_form=lambda u, d, t: {"error": "invalid_grant"})
    assert exc.value.reason == "NO_ACCESS_TOKEN"
    assert db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).first() is None


# ── 기존 자동 갱신과 이어진다 ───────────────────────────────────────────

def test_동의로_받은_토큰을_기존_갱신_경로가_그대로_쓴다(db, app_credential):
    """저장 위치가 수동 붙여넣기와 같아서 oauth.ensure_fresh_token 은 손댈 필요가 없다."""
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    oauth_flow.exchange_code(PROVIDER, db, code="CODE", state=started["state"],
                             post_form=_fake_token_endpoint([]))

    # 만료를 앞당겨 갱신이 실제로 일어나게 한다
    row = db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).one()
    row.token_expires_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
    db.commit()

    token = oauth.ensure_fresh_token(PROVIDER, 1, db,
                                     post_form=lambda u, d, t: {"access_token": "AT-refreshed", "expires_in": 3600})
    assert token == "AT-refreshed"


# ── 정리와 해제 ─────────────────────────────────────────────────────────

def test_쓰거나_만료된_state는_치운다(db, app_credential):
    used = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    oauth_flow.exchange_code(PROVIDER, db, code="C", state=used["state"],
                             post_form=_fake_token_endpoint([]))
    past = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    oauth_flow.build_authorization_url(PROVIDER, 1, db, now=past)
    alive = oauth_flow.build_authorization_url(PROVIDER, 1, db)

    assert oauth_flow.purge_expired(db) == 2
    remaining = db.query(models.OAuthState).all()
    assert [r.state for r in remaining] == [alive["state"]]


def test_해제하면_토큰과_남은_state가_사라진다(db, app_credential):
    started = oauth_flow.build_authorization_url(PROVIDER, 1, db)
    oauth_flow.exchange_code(PROVIDER, db, code="C", state=started["state"],
                             post_form=_fake_token_endpoint([]))
    oauth_flow.build_authorization_url(PROVIDER, 1, db)  # 진행 중이던 왕복

    oauth_flow.revoke(PROVIDER, 1, db, post_form=lambda u, d, t: {})
    assert db.query(models.UserApiKey).filter_by(user_id=1, provider=PROVIDER).first() is None
    assert db.query(models.OAuthState).filter_by(user_id=1, provider=PROVIDER).count() == 0


def test_상대_해제_통보가_실패해도_우리_토큰은_지운다(db):
    """'끊었다'고 했는데 우리 DB 에 토큰이 남아 있는 편이 훨씬 나쁘다."""
    db.add(models.UserApiKey(user_id=1, provider="google_oauth_client",
                             api_key=encrypt_secret("g-id:g-secret")))
    db.add(models.UserApiKey(user_id=1, provider="google_oauth", api_key=encrypt_secret("AT")))
    db.commit()

    def failing(url, data, timeout):
        raise RuntimeError("provider down")

    oauth_flow.revoke("google_oauth", 1, db, post_form=failing)
    assert db.query(models.UserApiKey).filter_by(user_id=1, provider="google_oauth").first() is None


# ── 레지스트리 정합 ─────────────────────────────────────────────────────

def test_authorize를_선언한_provider는_앱_자격증명이_실재한다():
    for provider_id in providers.provider_ids():
        spec = providers.authorize_spec(provider_id)
        if spec is None:
            continue
        assert providers.get_provider(spec.clientCredential.provider) is not None, \
            f"{provider_id}: clientCredential 이 가리키는 {spec.clientCredential.provider} 가 레지스트리에 없다"
