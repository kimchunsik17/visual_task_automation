"""공통 Connector/OAuth/Error 계약 (ADR-0007) 테스트."""

from __future__ import annotations

import json
import pathlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
import datetime

from connectors import errors, providers
from connectors.contract import ConnectorSpec
from connectors.errors import ConnectorError
from connectors.pagination import PaginationConfig, collect_pages, value_at
from connectors.retry import RetryPolicy, run_with_retry, should_retry
from connectors.session import ConnectorSession, RateLimit, Response
from database import Base

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def make_session_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ── 오류 정규화 ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "status, expected",
    [
        (400, errors.INVALID_REQUEST),
        (401, errors.AUTH_INVALID),
        (403, errors.AUTH_FORBIDDEN),
        (404, errors.NOT_FOUND),
        (422, errors.INVALID_REQUEST),
        (429, errors.RATE_LIMITED),
        (500, errors.SERVER_ERROR),
        (503, errors.SERVER_ERROR),
    ],
)
def test_http_status_maps_to_a_stable_code(status, expected):
    assert errors.code_for_status(status) == expected


def test_error_says_whether_the_user_must_fix_a_credential():
    unauthorized = errors.from_response(401, service="Notion")
    assert unauthorized.needs_credential and not unauthorized.retryable

    throttled = errors.from_response(429, service="Notion")
    assert throttled.retryable and not throttled.needs_credential


def test_retry_after_header_is_honoured_and_bad_values_fall_back():
    assert errors.from_response(429, service="X", headers={"Retry-After": "12"}).retry_after == 12.0
    # HTTP-date 형식은 해석하지 않고 기본 backoff 로 넘긴다 — 파싱 실패로 재시도가 깨지는 것보다 낫다.
    assert errors.from_response(429, service="X", headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}).retry_after is None


def test_user_message_never_leaks_the_raw_upstream_text():
    error = errors.from_response(500, service="YouTube", body="Traceback: internal-host-3 exploded")
    assert "Traceback" not in error.user_message
    assert "YouTube" in error.user_message
    assert error.detail and "Traceback" in error.detail  # 로그에는 남는다


def test_exception_is_classified_without_importing_the_http_library():
    class ConnectTimeout(Exception):
        pass

    class ConnectionError_(Exception):
        __name__ = "ConnectionError"

    assert errors.from_exception(ConnectTimeout("t"), service="X").code == errors.TIMEOUT
    assert errors.from_exception(type("ConnectionError", (Exception,), {})(), service="X").code == errors.NETWORK


# ── 재시도 정책 ────────────────────────────────────────────────────────
def test_read_requests_retry_on_transient_failures():
    policy = RetryPolicy(max_attempts=3)
    for code in (errors.RATE_LIMITED, errors.TIMEOUT, errors.SERVER_ERROR, errors.NETWORK):
        error = ConnectorError(code=code, service="X")
        assert should_retry(error, attempt=1, policy=policy, method="GET"), code


def test_write_requests_do_not_retry_on_timeout():
    """카카오 발송이 timeout 났을 때 다시 보내면 메시지가 두 번 갈 수 있다 — 요청이 서버에
    닿았는지 알 방법이 없기 때문이다. 자동화에서 중복 발송은 한 번 실패보다 나쁘다."""
    policy = RetryPolicy(max_attempts=3)
    assert not should_retry(ConnectorError(code=errors.TIMEOUT, service="X"), attempt=1, policy=policy, method="POST")
    assert not should_retry(ConnectorError(code=errors.SERVER_ERROR, service="X"), attempt=1, policy=policy, method="POST")
    # 429 는 상대가 '처리하지 않고' 거절한 것이라 다시 보내도 안전하다.
    assert should_retry(ConnectorError(code=errors.RATE_LIMITED, service="X"), attempt=1, policy=policy, method="POST")


def test_write_requests_can_opt_in_when_they_are_idempotent():
    policy = RetryPolicy(max_attempts=3)
    error = ConnectorError(code=errors.TIMEOUT, service="X")
    assert should_retry(error, attempt=1, policy=policy, method="POST", idempotent=True)


def test_auth_failures_are_never_retried():
    policy = RetryPolicy(max_attempts=5)
    for code in (errors.AUTH_INVALID, errors.AUTH_FORBIDDEN, errors.AUTH_MISSING, errors.NOT_FOUND):
        assert not should_retry(ConnectorError(code=code, service="X"), attempt=1, policy=policy, method="GET"), code


def test_retry_gives_up_when_the_wait_would_be_absurd():
    """상대가 '10분 뒤에 오라'고 하면 워크플로우를 그만큼 붙잡아 두지 않고 실패로 끝낸다."""
    policy = RetryPolicy(max_attempts=3, max_delay=20)
    error = ConnectorError(code=errors.RATE_LIMITED, service="X", retry_after=600)
    assert not should_retry(error, attempt=1, policy=policy, method="GET")


def test_run_with_retry_stops_after_max_attempts():
    calls = []
    slept = []

    def failing():
        calls.append(1)
        raise ConnectorError(code=errors.SERVER_ERROR, service="X")

    with pytest.raises(ConnectorError):
        run_with_retry(failing, policy=RetryPolicy(max_attempts=3, jitter=0), sleep=slept.append)

    assert len(calls) == 3
    assert slept == [0.5, 1.0]  # 지수 백오프


def test_run_with_retry_does_not_swallow_unnormalized_errors():
    """정규화되지 않은 예외를 재시도하면 원인 모를 실패를 조용히 세 번 반복하게 된다."""
    def boom():
        raise ValueError("정규화 안 된 오류")

    with pytest.raises(ValueError):
        run_with_retry(boom, policy=RetryPolicy(max_attempts=3), sleep=lambda _: None)


# ── 세션 ───────────────────────────────────────────────────────────────
def test_session_accepts_the_whole_2xx_range():
    """노드마다 `== 200` 으로 좁게 비교하다 201/204 를 실패로 오해하는 일이 있었다."""
    session = ConnectorSession("X", transport=lambda *a, **k: Response(204, {}, None), sleep=lambda _: None)
    assert session.request("DELETE", "https://x.dev").status == 204


def test_session_normalizes_failures_and_retries_reads():
    responses = [Response(503, {}, "unavailable"), Response(200, {}, {"ok": True})]
    session = ConnectorSession(
        "YouTube",
        transport=lambda *a, **k: responses.pop(0),
        retry_policy=RetryPolicy(max_attempts=3, jitter=0),
        sleep=lambda _: None,
    )

    assert session.get("https://x.dev").json() == {"ok": True}
    assert session.attempts == 2
    assert session.retries == [{"attempt": 1, "delay": 0.5, "code": errors.SERVER_ERROR}]


def test_session_reports_telemetry_for_node_level_metrics():
    session = ConnectorSession("X", transport=lambda *a, **k: Response(200, {}, {}), sleep=lambda _: None)
    session.get("https://x.dev")
    assert session.telemetry() == {"service": "X", "attempts": 1, "retries": []}


def test_rate_limit_spaces_calls_out():
    slept = []
    clock = iter([0.0, 0.1])
    limiter = RateLimit(requests_per_minute=60)  # 1초 간격
    limiter.wait(now=lambda: next(clock), sleep=slept.append)   # 첫 호출은 기다리지 않는다
    limiter.wait(now=lambda: next(clock), sleep=slept.append)
    assert slept and abs(slept[0] - 0.9) < 0.001


def test_rate_limit_is_off_when_unconfigured():
    slept = []
    RateLimit().wait(now=lambda: 0.0, sleep=slept.append)
    assert slept == []


# ── 페이지네이션 ───────────────────────────────────────────────────────
def test_cursor_pagination_follows_the_next_token():
    pages = [
        {"items": [1, 2], "nextPageToken": "a"},
        {"items": [3, 4], "nextPageToken": "b"},
        {"items": [5], "nextPageToken": None},
    ]
    seen = []

    def fetch(params):
        seen.append(params.get("pageToken"))
        return pages[len(seen) - 1]

    result = collect_pages(fetch, PaginationConfig(style="cursor"))
    assert result.items == [1, 2, 3, 4, 5]
    assert seen == [None, "a", "b"]
    assert not result.truncated


def test_pagination_stops_at_max_pages_and_says_it_was_truncated():
    """상대가 커서를 잘못 돌려주면 무한 루프가 되고, 그건 워크플로우 하나가 실행 워커를
    영구히 점유하는 형태로 나타난다. 잘랐다는 사실은 반드시 알려야 한다."""
    def fetch(params):
        return {"items": [1], "nextPageToken": "언제나-다음이-있다"}

    result = collect_pages(fetch, PaginationConfig(style="cursor", max_pages=3))
    assert result.pages_fetched == 3 and result.truncated


def test_page_style_stops_on_a_short_page():
    pages = [{"items": [1, 2]}, {"items": [3]}]
    result = collect_pages(lambda p: pages[p["page"] - 1], PaginationConfig(style="page", page_size=2))
    assert result.items == [1, 2, 3] and not result.truncated


def test_nested_paths_are_supported():
    assert value_at({"data": {"list": [1]}}, "data.list") == [1]
    assert value_at({"data": {}}, "data.missing.deep") is None


def test_session_collect_merges_base_params():
    seen = []

    def transport(method, url, **kwargs):
        seen.append(kwargs.get("params"))
        return Response(200, {}, {"items": [1], "nextPageToken": None})

    session = ConnectorSession("X", transport=transport, sleep=lambda _: None)
    session.collect("https://x.dev", params={"channelId": "c1"}, config=PaginationConfig(page_size=10))
    assert seen == [{"channelId": "c1", "limit": 10}]


# ── provider 레지스트리 ────────────────────────────────────────────────
def test_registry_loads_every_provider_the_api_center_offers():
    assert set(providers.provider_ids()) == {
        "openai", "gemini", "kakao", "kakao_token", "google_oauth_client", "google_oauth",
        "discord", "telegram", "notion", "google_smtp", "toss", "database",
        # 한국형 노드 계획 Phase 0 — 검색 API 는 비로그인, 나머지 둘은 동의 절차 한 쌍이다
        "naver_api_hub", "naver_oauth_client", "naver_user_oauth",
        # Phase 3 — 도로명주소 승인키. 신청할 때 적은 서비스 URL 에서만 동작한다
        "juso",
        # Phase 3 — 공공데이터포털. 키는 하나지만 데이터셋마다 활용신청이 따로다
        "data_go_kr",
    }


def test_oauth_providers_explain_what_each_scope_allows():
    """사용자가 동의하기 전에 '이 권한이 무엇을 허용하는지' 를 볼 수 있어야 한다."""
    google = providers.get_provider("google_oauth")
    assert google.scopes
    for scope in google.scopes:
        assert scope.scope.startswith("https://www.googleapis.com/auth/")
        assert scope.allows.strip()


def test_placeholders_match_the_substitution_key():
    """이 값이 어긋나면 노드에 적은 자리표시자가 치환되지 않고 빈 문자열이 들어가서,
    원인이 '인증 실패'로만 드러난다."""
    for provider_id in providers.provider_ids():
        assert providers.get_provider(provider_id).placeholder == "{{API_CENTER:%s}}" % provider_id


def test_kakao_refresh_settings_come_from_the_registry():
    import kakao_utils

    spec = providers.refresh_spec("kakao_token")
    assert kakao_utils.KAKAO_TOKEN_URL == spec.tokenUrl
    assert kakao_utils.CLIENT_ID_PROVIDER == spec.clientCredential.provider
    assert kakao_utils.REFRESH_MARGIN.total_seconds() == spec.marginMinutes * 60


def test_two_oauth_services_declare_their_differences_instead_of_forking_code():
    """카카오는 client_id 만, 구글은 client_secret 까지 필요하다. 그 차이가 코드가 아니라
    선언으로만 나타나야 세 번째 서비스가 코드를 복사하지 않고 추가된다."""
    kakao = providers.refresh_spec("kakao_token")
    google = providers.refresh_spec("google_oauth")
    assert kakao.clientCredential.format == "client_id"
    assert google.clientCredential.format == "client_id:client_secret"
    assert kakao.tokenUrl != google.tokenUrl


def test_connection_status_reports_readiness_not_secrets():
    from credential_crypto import encrypt_secret

    db = make_session_db()
    db.add(models.User(id=1, name="u"))
    db.add(models.UserApiKey(user_id=1, provider="notion", api_key=encrypt_secret("secret_abc")))
    db.commit()

    statuses = {s["provider"]: s for s in providers.connection_status(db, 1)}

    assert statuses["notion"]["connected"] and statuses["notion"]["ready"]
    assert statuses["openai"]["connected"] is False
    # 비밀값이 새어 나가지 않는지.
    assert "secret_abc" not in json.dumps(statuses, ensure_ascii=False)


def test_auto_refresh_provider_is_not_ready_without_its_client_id():
    """카카오 토큰만 등록하고 REST API 키를 빼먹으면 자동 갱신이 조용히 실패한다 —
    연결 상태에서 미리 드러나야 한다."""
    from credential_crypto import encrypt_secret

    db = make_session_db()
    db.add(models.User(id=1, name="u"))
    db.add(models.UserApiKey(
        user_id=1, provider="kakao_token",
        api_key=encrypt_secret("access"), refresh_token=encrypt_secret("refresh"),
    ))
    db.commit()

    status = {s["provider"]: s for s in providers.connection_status(db, 1)}["kakao_token"]
    assert status["connected"] is True
    assert status["ready"] is False
    assert status["auto_refresh"]["client_id_connected"] is False


def test_frontend_provider_bundle_is_up_to_date():
    from export_node_definitions import PROVIDERS_BUNDLE_PATH, render_providers_bundle

    assert PROVIDERS_BUNDLE_PATH.read_text(encoding="utf-8") == render_providers_bundle(), (
        "provider 번들이 정본과 다르다 — python backend/export_node_definitions.py 를 실행하라"
    )


# ── 노드 정의의 connector 블록 ─────────────────────────────────────────
def _spec(**overrides):
    base = {
        "service": "youtube",
        "role": "action",
        "modes": ["upload_video", "list_videos"],
        "credentials": [{"provider": "openai", "scopes": ["a.b"]}],
        "sideEffectByMode": {"upload_video": "external-write", "list_videos": "external-read"},
    }
    base.update(overrides)
    return ConnectorSpec.model_validate(base)


def test_connector_spec_rejects_an_unknown_credential_provider():
    spec = _spec(credentials=[{"provider": "존재하지-않는-provider"}])
    problems = spec.validate_against_registry()
    assert any("credential_providers.json 에 없다" in p for p in problems)


def test_connector_spec_requires_a_side_effect_grade_for_every_mode():
    """등급이 없으면 dry-run 이 안전한 쪽으로 가정할 수밖에 없어, 읽기 전용 모드까지 막히거나
    반대로 쓰기 모드가 새어 나간다."""
    spec = _spec(sideEffectByMode={"upload_video": "external-write"})
    assert any("등급이 없는 모드" in p for p in spec.validate_against_registry())


def test_connector_spec_catches_a_mode_typo_in_side_effects():
    spec = _spec(sideEffectByMode={"upload_video": "external-write", "list_video": "external-read"})
    assert any("modes 에 없다" in p for p in spec.validate_against_registry())


def test_valid_spec_has_no_problems():
    assert _spec().validate_against_registry() == []


def test_dry_run_treats_an_unknown_mode_as_a_write():
    spec = _spec()
    assert spec.writes_externally("upload_video") is True
    assert spec.writes_externally("list_videos") is False
    assert spec.writes_externally("나중에-추가된-모드") is True


def test_spec_builds_a_session_carrying_its_own_policy():
    spec = _spec(timeoutSeconds=30.0, retryPolicy={"maxAttempts": 5}, rateLimit={"requestsPerMinute": 30})
    session = spec.new_session(transport=lambda *a, **k: Response(200, {}, {}))
    assert session.timeout == 30.0
    assert session.retry_policy.max_attempts == 5
    assert session.rate_limit.requests_per_minute == 30


def test_node_definitions_without_a_connector_block_still_load():
    import node_definition

    assert node_definition.get_definition("llmNode").connector is None


# ── 공통 OAuth 토큰 갱신 ───────────────────────────────────────────────
def _seed_token(db, provider, access, refresh=None, expires_at=None):
    from credential_crypto import encrypt_secret

    db.add(models.UserApiKey(
        user_id=1, provider=provider, api_key=encrypt_secret(access),
        refresh_token=encrypt_secret(refresh) if refresh else None,
        token_expires_at=expires_at,
    ))
    db.commit()


def _db_with_user():
    db = make_session_db()
    db.add(models.User(id=1, name="u"))
    db.commit()
    return db


def test_token_that_is_still_valid_is_not_refreshed():
    """멀쩡한 토큰을 매 실행마다 갱신하면 호출 한도만 축낸다."""
    from connectors import oauth

    db = _db_with_user()
    later = datetime.datetime.utcnow() + datetime.timedelta(hours=5)
    _seed_token(db, "kakao_token", "still-good", "refresh", later)

    calls = []
    token = oauth.ensure_fresh_token("kakao_token", 1, db, post_form=lambda *a, **k: calls.append(a) or {})
    assert token == "still-good" and calls == []


def test_expiring_token_is_refreshed_and_persisted():
    from connectors import oauth
    from credential_crypto import decrypt_secret

    db = _db_with_user()
    _seed_token(db, "kakao", "rest-api-key")
    soon = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    _seed_token(db, "kakao_token", "old-token", "refresh-1", soon)

    sent = {}

    def fake_post(url, data, timeout):
        sent.update({"url": url, "data": data})
        return {"access_token": "new-token", "expires_in": 21600}

    assert oauth.ensure_fresh_token("kakao_token", 1, db, post_form=fake_post) == "new-token"
    assert sent["url"] == providers.refresh_spec("kakao_token").tokenUrl
    assert sent["data"]["client_id"] == "rest-api-key"
    assert "client_secret" not in sent["data"]  # 카카오는 secret 을 쓰지 않는다

    row = db.query(models.UserApiKey).filter_by(provider="kakao_token").first()
    assert decrypt_secret(row.api_key) == "new-token"
    assert row.token_expires_at > datetime.datetime.utcnow() + datetime.timedelta(hours=5)


def test_google_refresh_sends_the_client_secret_from_the_same_field():
    """같은 갱신 코드가 두 서비스를 처리한다 — 차이는 정의 파일에만 있다."""
    from connectors import oauth

    db = _db_with_user()
    _seed_token(db, "google_oauth_client", "client-abc:secret-xyz")
    soon = datetime.datetime.utcnow() + datetime.timedelta(minutes=2)
    _seed_token(db, "google_oauth", "old", "refresh-g", soon)

    sent = {}
    oauth.ensure_fresh_token("google_oauth", 1, db,
                             post_form=lambda url, data, timeout: sent.update(data) or {"access_token": "fresh-g"})

    assert sent["client_id"] == "client-abc"
    assert sent["client_secret"] == "secret-xyz"


def test_refresh_failure_falls_back_to_the_existing_token():
    """갱신 서버가 잠깐 죽었다고 아직 유효한 토큰까지 버리고 워크플로우를 멈추면 안 된다.
    정말 만료됐다면 상대 API 의 401 이 auth_invalid 로 정확히 알려준다."""
    from connectors import oauth

    db = _db_with_user()
    _seed_token(db, "kakao", "client")
    _seed_token(db, "kakao_token", "old-token", "refresh", datetime.datetime.utcnow())

    def boom(*args, **kwargs):
        raise RuntimeError("갱신 서버 오류")

    assert oauth.ensure_fresh_token("kakao_token", 1, db, post_form=boom) == "old-token"


def test_missing_app_credential_does_not_crash_the_run():
    from connectors import oauth

    db = _db_with_user()
    _seed_token(db, "google_oauth", "old", "refresh-g", datetime.datetime.utcnow())
    assert oauth.ensure_fresh_token("google_oauth", 1, db, post_form=lambda *a, **k: {}) == "old"


def test_refresh_token_is_kept_when_the_provider_does_not_return_a_new_one():
    """구글은 대개 새 refresh_token 을 주지 않는다 — 없다고 기존 값을 지우면 자동 갱신이 영영 끊긴다."""
    from connectors import oauth
    from credential_crypto import decrypt_secret

    db = _db_with_user()
    _seed_token(db, "google_oauth_client", "id:secret")
    _seed_token(db, "google_oauth", "old", "keep-me", datetime.datetime.utcnow())

    oauth.ensure_fresh_token("google_oauth", 1, db, post_form=lambda *a, **k: {"access_token": "new", "expires_in": 3600})

    row = db.query(models.UserApiKey).filter_by(provider="google_oauth").first()
    assert decrypt_secret(row.refresh_token) == "keep-me"


def test_missing_credential_raises_an_actionable_error_where_required():
    from connectors import oauth

    db = _db_with_user()
    with pytest.raises(ConnectorError) as caught:
        oauth.require_token("google_oauth", 1, db, service="YouTube")

    assert caught.value.code == errors.AUTH_MISSING
    assert "API 센터" in caught.value.user_message
