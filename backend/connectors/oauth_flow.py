"""connectors/oauth_flow.py — 인가 코드(authorization code) 흐름 (한국형 노드 계획 Phase 0).

`oauth.py` 가 "만료된 토큰을 어떻게 새로 고치나"라면 여기는 **"애초에 어떻게 받나"**다.

지금까지 이 단계가 없었다. `google_oauth`·`kakao_token` 의 guide 를 보면 사용자가 provider
콘솔의 "토큰 받기" 도구로 직접 발급받아 붙여넣는 절차가 적혀 있다. 서비스가 하나둘일 때는
버틸 만했지만 네이버·X·Instagram 을 붙이려면 셋 다 그 안내를 새로 쓰게 되고, 무엇보다 그
방식은 **사용자가 refresh_token 원문을 손으로 옮기게 한다.**

서비스마다 다른 부분(동의 URL, 토큰 URL, scope 를 어떻게 싣는지, PKCE 를 쓰는지, refresh_token
을 받으려면 무엇을 더 보내야 하는지)은 전부 `credential_providers.json` 의 `authorize` 선언으로
옮기고, 절차 자체는 여기 한 곳에만 둔다.

■ 이 모듈이 지키는 것

  1. **state 는 서버가 들고 있는다.** 클라이언트가 만들어 보내고 돌아온 값을 그대로 믿으면
     CSRF 로 남의 계정에 공격자의 토큰을 붙일 수 있다. 한 번 쓰면 소비 표시가 찍혀 재사용이
     안 되고(코드 재생 방지), 10분이 지나면 만료된다.
  2. **redirect_uri 는 설정된 allowlist 안에서만 만든다.** 요청 파라미터로 받지 않는다 —
     받는 순간 공격자가 자기 서버로 인가 코드를 보낼 수 있다.
  3. **동의 후 돌아갈 우리 화면(`return_to`)도 서버가 검증한다.** 상대 경로만 받는다.
     그러지 않으면 이 엔드포인트 자체가 열린 리다이렉터가 된다.
  4. **PKCE 는 선언으로 켠다.** 지원하지 않는 provider 에 보내면 오류를 내는 곳이 있다.
  5. **토큰 원문은 로그에 남기지 않는다.** 저장은 다른 자격증명과 같은 암호화 계층을 쓴다.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import os
import secrets
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode, urlparse

from . import providers

STATE_TTL_MINUTES = 10
CALLBACK_PATH = "/api/oauth/{provider}/callback"
DEFAULT_REDIRECT_BASE = "https://wa-pnu.duckdns.org"


class OAuthFlowError(RuntimeError):
    """흐름을 더 진행할 수 없다. 메시지는 사용자에게 그대로 보여도 되는 수준으로 쓴다."""

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


# ── 설정: 어디로 돌아올 것인가 ──────────────────────────────────────────

def allowed_redirect_bases() -> List[str]:
    """콜백을 받을 수 있는 origin 목록.

    `OAUTH_REDIRECT_BASE_URL` 에 쉼표로 여러 개를 둘 수 있다(운영 + 로컬 개발). 첫 번째가
    기본값이고, provider 콘솔에는 여기 있는 주소를 그대로 등록해야 한다.
    """
    raw = os.getenv("OAUTH_REDIRECT_BASE_URL", "").strip()
    bases = [b.strip().rstrip("/") for b in raw.split(",") if b.strip()] if raw else []
    return bases or [DEFAULT_REDIRECT_BASE]


def callback_url(provider_id: str, *, base: Optional[str] = None) -> str:
    """provider 콘솔에 등록할 콜백 주소. 인가 요청과 토큰 교환에 **같은 값**을 써야 한다."""
    bases = allowed_redirect_bases()
    if base is None:
        chosen = bases[0]
    else:
        chosen = base.rstrip("/")
        if chosen not in bases:
            raise OAuthFlowError(
                "허용되지 않은 콜백 주소입니다. 서버의 OAUTH_REDIRECT_BASE_URL 설정을 확인해주세요.",
                reason="REDIRECT_NOT_ALLOWED",
            )
    return chosen + CALLBACK_PATH.format(provider=provider_id)


def safe_return_to(value: Optional[str]) -> Optional[str]:
    """동의 후 돌려보낼 우리 화면. **상대 경로만** 허용한다.

    `//evil.com` 은 스킴 상대 URL 이라 브라우저가 외부로 간다 — `/` 로 시작하는지만 보면
    놓치므로 파싱해서 netloc/scheme 이 비어 있는지까지 확인한다.
    """
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        raise OAuthFlowError("돌아갈 주소는 이 사이트 안의 경로여야 합니다.", reason="BAD_RETURN_TO")
    return value


# ── 앱 자격증명 읽기 ────────────────────────────────────────────────────

def _client_credential(spec_ref, user_id: int, db) -> tuple[str, Optional[str]]:
    import models

    from credential_crypto import decrypt_secret

    row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == spec_ref.provider)
        .first()
    )
    if not row or not row.api_key:
        provider = providers.get_provider(spec_ref.provider)
        name = provider.name if provider else spec_ref.provider
        raise OAuthFlowError(
            f"먼저 API 센터에 '{name}' 을(를) 등록해주세요. 앱 자격증명이 있어야 동의 절차를 시작할 수 있습니다.",
            reason="CLIENT_CREDENTIAL_MISSING",
        )
    raw = decrypt_secret(row.api_key) or ""
    if spec_ref.format == "client_id:client_secret":
        client_id, _, client_secret = raw.partition(":")
        return client_id.strip(), (client_secret.strip() or None)
    return raw.strip(), None


# ── 1단계: 동의 화면으로 보낸다 ─────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def build_authorization_url(
    provider_id: str,
    user_id: int,
    db,
    *,
    return_to: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """동의 화면 URL 을 만들고 왕복 상태를 저장한다. `{"url": ..., "state": ...}` 를 돌려준다."""
    import models

    from credential_crypto import encrypt_secret

    spec = providers.authorize_spec(provider_id)
    if spec is None:
        raise OAuthFlowError(
            f"'{provider_id}' 는 동의 절차로 연결하는 provider 가 아닙니다.",
            reason="NOT_AN_OAUTH_PROVIDER",
        )

    now = now or datetime.datetime.utcnow()
    client_id, _secret = _client_credential(spec.clientCredential, user_id, db)
    redirect_uri = callback_url(provider_id)
    checked_return_to = safe_return_to(return_to)

    state = secrets.token_urlsafe(32)
    verifier = challenge = None
    if spec.usesPkce:
        verifier, challenge = _pkce_pair()

    db.add(models.OAuthState(
        user_id=user_id,
        provider=provider_id,
        state=state,
        code_verifier=encrypt_secret(verifier) if verifier else None,
        redirect_uri=redirect_uri,
        return_to=checked_return_to,
        created_at=now,
        expires_at=now + datetime.timedelta(minutes=STATE_TTL_MINUTES),
    ))
    db.commit()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    scopes = providers.requested_scopes(provider_id)
    if scopes:
        params["scope"] = spec.scopeSeparator.join(scopes)
    if challenge:
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    params.update(spec.extraParams)

    return {"url": f"{spec.authorizeUrl}?{urlencode(params)}", "state": state}


# ── 2단계: 돌아온 code 를 토큰으로 바꾼다 ───────────────────────────────

def _post_form(token_url: str, data: Dict[str, str], timeout: float) -> Dict[str, Any]:
    import requests

    response = requests.post(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        # 상대 서비스 원문은 진단 로그에만 두고 사용자에게는 조치를 보여준다(ADR-0016).
        print(f"[oauth_flow] 토큰 교환 실패 {response.status_code}: {response.text[:300]}")
        raise OAuthFlowError(
            "토큰 발급을 거절당했습니다. 앱 자격증명과 콜백 주소 등록 상태를 확인해주세요.",
            reason="TOKEN_EXCHANGE_REJECTED",
        )
    return response.json()


def consume_state(provider_id: str, state: str, db, *, now: Optional[datetime.datetime] = None):
    """state 를 검증하고 **소비 표시를 찍은 뒤** 돌려준다. 같은 state 는 두 번 못 쓴다."""
    import models

    now = now or datetime.datetime.utcnow()
    row = db.query(models.OAuthState).filter(models.OAuthState.state == state).first()
    if not row:
        raise OAuthFlowError("만료됐거나 알 수 없는 요청입니다. 연결을 다시 시작해주세요.", reason="STATE_UNKNOWN")
    if row.provider != provider_id:
        raise OAuthFlowError("요청과 응답의 서비스가 다릅니다.", reason="STATE_PROVIDER_MISMATCH")
    if row.consumed_at is not None:
        raise OAuthFlowError("이미 사용된 요청입니다. 연결을 다시 시작해주세요.", reason="STATE_ALREADY_USED")
    if row.expires_at <= now:
        raise OAuthFlowError("요청이 만료됐습니다. 연결을 다시 시작해주세요.", reason="STATE_EXPIRED")

    row.consumed_at = now
    db.commit()
    return row


def exchange_code(
    provider_id: str,
    db,
    *,
    code: str,
    state: str,
    now: Optional[datetime.datetime] = None,
    post_form: Callable[..., Dict[str, Any]] = _post_form,
) -> Dict[str, Any]:
    """콜백에서 받은 code 를 토큰으로 바꿔 `user_api_keys` 에 저장한다.

    저장 위치가 수동 붙여넣기와 같아서 `ensure_fresh_token` 은 손대지 않아도 그대로 동작한다.
    """
    import models

    from credential_crypto import decrypt_secret, encrypt_secret

    spec = providers.authorize_spec(provider_id)
    if spec is None:
        raise OAuthFlowError(
            f"'{provider_id}' 는 동의 절차로 연결하는 provider 가 아닙니다.",
            reason="NOT_AN_OAUTH_PROVIDER",
        )
    if not code:
        raise OAuthFlowError("인가 코드가 없습니다.", reason="NO_CODE")

    now = now or datetime.datetime.utcnow()
    state_row = consume_state(provider_id, state, db, now=now)
    user_id = state_row.user_id

    client_id, client_secret = _client_credential(spec.clientCredential, user_id, db)
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        # 인가 요청 때와 **같은 값**이어야 한다. 그래서 지금 다시 만들지 않고 저장된 것을 쓴다.
        "redirect_uri": state_row.redirect_uri,
    }
    if client_secret and spec.secretInBody:
        form["client_secret"] = client_secret
    if spec.sendStateOnTokenExchange:
        form["state"] = state
    if state_row.code_verifier:
        # PKCE 를 켜고 시작한 왕복이면 저장해둔 verifier 를 그대로 보낸다. 선언을 끄더라도
        # 진행 중이던 왕복은 시작할 때의 규칙으로 끝나야 provider 가 받아준다.
        form["code_verifier"] = decrypt_secret(state_row.code_verifier)

    payload = post_form(spec.tokenUrl, form, 10)
    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthFlowError(
            "토큰 응답에 access_token 이 없습니다. 앱 설정의 권한을 확인해주세요.",
            reason="NO_ACCESS_TOKEN",
        )

    row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == provider_id)
        .first()
    )
    if row is None:
        row = models.UserApiKey(user_id=user_id, provider=provider_id)
        db.add(row)

    row.api_key = encrypt_secret(access_token)
    if payload.get("refresh_token"):
        # 안 왔을 때 기존 값을 지우면 자동 갱신이 영영 끊긴다(구글은 첫 동의에만 준다).
        row.refresh_token = encrypt_secret(payload["refresh_token"])
    expires_in = payload.get("expires_in")
    if expires_in:
        try:
            row.token_expires_at = now + datetime.timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            row.token_expires_at = None
    db.commit()

    print(f"[oauth_flow] user {user_id} 의 {provider_id} 를 동의 절차로 연결했다")
    return {
        "provider": provider_id,
        "user_id": user_id,
        "return_to": state_row.return_to,
        "has_refresh_token": bool(row.refresh_token),
        "expires_at": row.token_expires_at.isoformat() if row.token_expires_at else None,
    }


# ── 정리와 해제 ─────────────────────────────────────────────────────────

def purge_expired(db, *, now: Optional[datetime.datetime] = None) -> int:
    """만료됐거나 이미 쓴 왕복 상태를 치운다. 표가 무한히 자라지 않게 한다."""
    import models

    now = now or datetime.datetime.utcnow()
    deleted = (
        db.query(models.OAuthState)
        .filter((models.OAuthState.expires_at <= now) | (models.OAuthState.consumed_at.isnot(None)))
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)


def revoke(provider_id: str, user_id: int, db, *, post_form: Callable[..., Dict[str, Any]] = _post_form) -> None:
    """연결을 끊는다. provider 가 해제 endpoint 를 주면 알려주고, 우리 쪽 값은 무조건 지운다.

    상대 호출이 실패해도 로컬 삭제는 진행한다 — 사용자가 "끊었다"고 했는데 우리 DB 에 토큰이
    남아 있는 편이 훨씬 나쁘다.
    """
    import models

    from credential_crypto import decrypt_secret

    spec = providers.authorize_spec(provider_id)
    row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == provider_id)
        .first()
    )
    if row and spec and spec.revokeUrl:
        try:
            client_id, client_secret = _client_credential(spec.clientCredential, user_id, db)
            form = {"client_id": client_id, "token": decrypt_secret(row.api_key) or ""}
            if client_secret:
                form["client_secret"] = client_secret
            post_form(spec.revokeUrl, form, 10)
        except Exception as exc:
            print(f"[oauth_flow] {provider_id} 해제 통보 실패(로컬 삭제는 진행): {type(exc).__name__}")

    db.query(models.UserApiKey).filter(
        models.UserApiKey.user_id == user_id, models.UserApiKey.provider == provider_id
    ).delete(synchronize_session=False)
    db.query(models.OAuthState).filter(
        models.OAuthState.user_id == user_id, models.OAuthState.provider == provider_id
    ).delete(synchronize_session=False)
    db.commit()
