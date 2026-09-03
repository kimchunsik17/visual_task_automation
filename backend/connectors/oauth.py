"""connectors/oauth.py — refresh_token 기반 access_token 자동 갱신 (ADR-0008).

카카오만 있었을 때는 갱신 로직이 `kakao_utils.py` 안에 서비스 전용으로 박혀 있었다. 구글을
추가하면서 그 코드를 복사하면 두 번째, 세 번째 서비스마다 같은 일이 반복된다 — 그래서
서비스별로 다른 부분(토큰 URL, 앱 자격증명이 어디 저장돼 있는지, client_secret 이 필요한지,
갱신 여유)을 전부 credential_providers.json 의 `refresh` 선언으로 옮기고, 갱신 절차 자체는
여기 한 곳에만 둔다.

■ 자격증명이 새지 않게 하는 규칙
  - 토큰 원문은 반환값으로만 흐르고 로그에 남기지 않는다.
  - 갱신 실패는 정규화된 ConnectorError 로 올리지 않고 기존 토큰을 그대로 돌려준다 —
    실제로 만료됐다면 상대 API 가 401 을 주고, 그때 auth_invalid 로 정확히 분류된다.
    (여기서 실패를 던지면 '아직 유효한 토큰인데 갱신 서버가 잠깐 죽어서' 워크플로우가 멈춘다.)
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from . import providers
from .errors import AUTH_MISSING, ConnectorError


def _split_client_credential(raw: str, fmt: str) -> Tuple[str, Optional[str]]:
    if fmt == "client_id:client_secret":
        client_id, _, client_secret = raw.partition(":")
        return client_id.strip(), (client_secret.strip() or None)
    return raw.strip(), None


def _post_form(token_url: str, data: Dict[str, str], timeout: float) -> Dict[str, Any]:
    import requests

    response = requests.post(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def ensure_fresh_token(
    provider_id: str,
    user_id: int,
    db,
    *,
    now: Optional[datetime.datetime] = None,
    post_form: Callable[..., Dict[str, Any]] = _post_form,
) -> str:
    """provider 의 access_token 을 돌려준다. 만료가 임박했고 갱신에 필요한 값이 모두
    갖춰져 있으면 실제로 갱신해서 DB 에 반영한 뒤 새 값을 돌려준다.

    레코드가 없으면 빈 문자열을 돌려준다 — 하류가 '값이 없다'를 정상적으로 감지하게 하려는
    기존 규약을 유지한다.
    """
    import models

    from credential_crypto import decrypt_secret, encrypt_secret

    spec = providers.refresh_spec(provider_id)
    now = now or datetime.datetime.utcnow()

    token_row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == provider_id)
        .first()
    )
    if not token_row or not token_row.api_key:
        return ""

    access_token = decrypt_secret(token_row.api_key)
    if spec is None:
        return access_token  # 자동 갱신이 없는 provider

    refresh_token = decrypt_secret(token_row.refresh_token)
    margin = datetime.timedelta(minutes=spec.marginMinutes)
    needs_refresh = token_row.token_expires_at is None or token_row.token_expires_at <= now + margin
    if not needs_refresh or not refresh_token:
        return access_token

    client_row = (
        db.query(models.UserApiKey)
        .filter(
            models.UserApiKey.user_id == user_id,
            models.UserApiKey.provider == spec.clientCredential.provider,
        )
        .first()
    )
    if not client_row or not client_row.api_key:
        # 앱 자격증명이 없으면 갱신할 방법이 없다. 기존 값을 그대로 쓰고, 정말 만료됐다면
        # 상대 API 의 401 로 드러난다(연결 상태 API 가 이 상태를 미리 알려준다).
        print(f"[oauth] {provider_id}: 갱신에 필요한 {spec.clientCredential.provider} 가 없어 기존 토큰을 사용한다")
        return access_token

    client_id, client_secret = _split_client_credential(
        decrypt_secret(client_row.api_key), spec.clientCredential.format
    )
    form = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token}
    if client_secret:
        form["client_secret"] = client_secret

    try:
        payload = post_form(spec.tokenUrl, form, 10)
    except Exception as exc:  # 갱신 실패로 워크플로우를 멈추지 않는다
        print(f"[oauth] {provider_id} 토큰 갱신 실패, 기존 값 사용: {type(exc).__name__}")
        return access_token

    new_access_token = payload.get("access_token")
    if not new_access_token:
        return access_token

    token_row.api_key = encrypt_secret(new_access_token)
    expires_in = payload.get("expires_in")
    if expires_in:
        token_row.token_expires_at = now + datetime.timedelta(seconds=int(expires_in))
    # 카카오는 refresh_token 만료가 가까울 때만, 구글은 대개 아예 새 refresh_token 을 주지
    # 않는다 — 왔을 때만 갱신한다(없다고 기존 값을 지우면 자동 갱신이 영영 끊긴다).
    if payload.get("refresh_token"):
        token_row.refresh_token = encrypt_secret(payload["refresh_token"])

    db.commit()
    print(f"[oauth] user {user_id} 의 {provider_id} access_token 을 자동 갱신했다")
    return new_access_token


def require_token(provider_id: str, user_id: int, db, *, service: str) -> str:
    """토큰이 반드시 있어야 하는 경로용. 없으면 '연결 안내'로 이어지는 오류를 올린다.

    mock 실행 모드(ADR-0009)에서는 실제 자격증명을 읽지 않는다 — 아직 아무것도 등록하지 않은
    사용자도 워크플로우를 끝까지 돌려볼 수 있어야 하기 때문이다. 인증 실패 경로는 자격증명을
    비우는 방식이 아니라 `auth_failed` 시나리오로 재현한다.
    """
    from . import mock_runtime

    mock_token = mock_runtime.token_for(provider_id)
    if mock_token is not None:
        return mock_token

    token = ensure_fresh_token(provider_id, user_id, db)
    if not token:
        # 시연 공유 자격증명(opt-in, demo_credentials.py) — 사용자에게 키가 없을 때만
        # 부스 계정 키로 폴백하고, 사용을 서버 로그 + flow_execution_logs 에 남긴다.
        import demo_credentials

        shared_uid = demo_credentials.fallback_user_id(provider_id)
        if shared_uid is not None and shared_uid != user_id:
            token = ensure_fresh_token(provider_id, shared_uid, db)
            if token:
                demo_credentials.record_use(
                    db, providers=[provider_id], actor_user_id=user_id,
                    shared_user_id=shared_uid, source="connector")
                return token
    if not token:
        provider = providers.get_provider(provider_id)
        raise ConnectorError(
            code=AUTH_MISSING,
            service=service,
            context={"provider": provider_id, "provider_name": provider.name if provider else provider_id},
        )
    return token
