"""connectors/providers.py — 자격증명 provider 정본 레지스트리 (ADR-0007).

provider 목록(이름, 안내, 값의 성격, scope, 자동 갱신 방식)은 저장소 루트
`credential_providers.json` 한 곳에서 관리한다. 예전에는 이 목록이 프론트엔드
`ApiCenterPage.jsx` 안에만 있어서, 서버는 어떤 provider 가 유효한지도 몰랐고
"이 사용자가 무엇을 연결해뒀는지" 를 판단할 근거도 없었다.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

REGISTRY_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "credential_providers.json"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCredentialRef(_Strict):
    """토큰 갱신에 필요한 '앱 자격증명'이 어느 provider 에 저장돼 있는지.

    카카오는 client_id 하나면 되지만 구글은 client_secret 까지 요구한다. 서비스마다 갱신
    코드를 새로 쓰지 않으려면 이 차이를 코드가 아니라 선언으로 다뤄야 한다.
    """

    provider: str
    format: Literal["client_id", "client_id:client_secret"] = "client_id"


class RefreshSpec(_Strict):
    """만료되는 토큰을 자동 갱신하는 방법."""

    tokenUrl: str
    clientCredential: ClientCredentialRef
    # 만료가 이 여유 안으로 들어오면 미리 갱신한다.
    marginMinutes: int = 30


class ScopeSpec(_Strict):
    """사용자에게 '이 권한이 무엇을 허용하는지' 를 그대로 보여주기 위한 짝."""

    scope: str
    allows: str


class AuthorizeSpec(_Strict):
    """인가 코드(authorization code) 흐름으로 토큰을 처음 발급받는 방법.

    `refresh` 가 "만료된 토큰을 어떻게 새로 고치나"라면 이건 "애초에 어떻게 받나"다. 예전에는
    이 단계가 아예 없어서 사용자가 provider 콘솔에서 토큰을 직접 받아 붙여넣어야 했다
    (`google_oauth`·`kakao_token` 의 guide 가 그 절차를 설명하고 있다). 서비스가 늘수록 그
    안내를 서비스마다 새로 쓰게 되므로, 서비스별로 다른 부분만 여기 선언으로 남긴다.
    """

    authorizeUrl: str
    tokenUrl: str
    clientCredential: ClientCredentialRef
    # None 이면 provider.scopes 의 scope 값을 그대로 요청한다. [] 면 scope 파라미터를 보내지
    # 않는다 — 네이버처럼 요청 때가 아니라 개발자센터 설정에서 권한을 정하는 곳이 있다.
    scopes: Optional[List[str]] = None
    scopeSeparator: str = " "
    # PKCE(S256). 지원하지 않는 provider 에 보내면 오류를 내는 곳이 있어 선언으로 켠다.
    usesPkce: bool = False
    # refresh_token 을 받으려면 provider 마다 다른 값이 필요하다(구글은 access_type=offline).
    extraParams: Dict[str, str] = Field(default_factory=dict)
    # 토큰 교환 때 client_secret 을 body 로 보낼지. 일부 provider 는 Basic 인증만 받는다.
    secretInBody: bool = True
    # 네이버는 토큰 교환 요청에도 state 를 요구한다. 대부분은 필요 없고, 안 받는 곳에 보내면
    # 무시되기는 하지만 규격 밖 파라미터라 선언으로 켠다.
    sendStateOnTokenExchange: bool = False
    revokeUrl: Optional[str] = None


class CredentialProvider(_Strict):
    id: str
    name: str
    icon: str
    # api_key      : 값 하나를 붙여넣는다
    # token_pair   : access_token + refresh_token 쌍이며 자동 갱신된다
    # compound     : 한 칸에 두 값을 합쳐 넣는다(예: 이메일:앱비밀번호)
    # oauth2       : 동의 절차를 거쳐 발급받는다(scopes 를 쓴다)
    # service_account : 서버가 하나의 신원으로 접근한다(사용자별 값이 없다)
    kind: Literal["api_key", "token_pair", "compound", "oauth2", "service_account"]
    scopes: List[ScopeSpec] = Field(default_factory=list)
    guide: List[str] = Field(default_factory=list)
    placeholder: str
    role: Optional[str] = None
    note: Optional[str] = None
    secretFormat: Optional[str] = None
    refresh: Optional[RefreshSpec] = None
    authorize: Optional[AuthorizeSpec] = None


class ProviderRegistry(_Strict):
    version: int
    providers: List[CredentialProvider]


def _load() -> Dict[str, CredentialProvider]:
    if not REGISTRY_PATH.exists():
        return {}
    registry = ProviderRegistry.model_validate(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    by_id: Dict[str, CredentialProvider] = {}
    for provider in registry.providers:
        expected = "{{API_CENTER:%s}}" % provider.id
        if provider.placeholder != expected:
            # 이 값이 어긋나면 노드에 적은 자리표시자가 실행 시 치환되지 않는다 —
            # 조용히 빈 문자열이 들어가서 "인증 실패"로만 드러난다.
            raise ValueError(f"{provider.id}: placeholder 는 '{expected}' 여야 한다")
        by_id[provider.id] = provider
    return by_id


PROVIDERS: Dict[str, CredentialProvider] = _load()


def get_provider(provider_id: str) -> Optional[CredentialProvider]:
    return PROVIDERS.get(provider_id)


def provider_ids() -> List[str]:
    return list(PROVIDERS)


def refresh_spec(provider_id: str) -> Optional[RefreshSpec]:
    provider = PROVIDERS.get(provider_id)
    return provider.refresh if provider else None


def authorize_spec(provider_id: str) -> Optional[AuthorizeSpec]:
    provider = PROVIDERS.get(provider_id)
    return provider.authorize if provider else None


def requested_scopes(provider_id: str) -> List[str]:
    """인가 요청에 실을 scope 목록. 선언이 없으면 표시용 scopes 를 그대로 쓴다."""
    provider = PROVIDERS.get(provider_id)
    if not provider or not provider.authorize:
        return []
    if provider.authorize.scopes is not None:
        return list(provider.authorize.scopes)
    return [scope.scope for scope in provider.scopes]


def registry_payload() -> List[Dict[str, Any]]:
    return [
        provider.model_dump(mode="json", exclude_none=True)
        for provider in PROVIDERS.values()
    ]


def connection_status(db, user_id: int) -> List[Dict[str, Any]]:
    """사용자가 각 provider 를 연결해뒀는지, 자동 갱신 토큰이 아직 쓸 수 있는지.

    비밀값 자체는 절대 담지 않는다 — 연결 여부와 만료 상태만 알려준다.
    """
    import datetime

    import models

    rows = {
        row.provider: row
        for row in db.query(models.UserApiKey).filter(models.UserApiKey.user_id == user_id).all()
    }
    now = datetime.datetime.utcnow()

    statuses: List[Dict[str, Any]] = []
    for provider in PROVIDERS.values():
        row = rows.get(provider.id)
        status: Dict[str, Any] = {
            "provider": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "connected": bool(row and row.api_key),
            "scopes": [scope.model_dump() for scope in provider.scopes],
        }
        if provider.refresh:
            # 자동 갱신 provider 는 "연결됨" 만으로 부족하다 — 갱신에 필요한 짝
            # (refresh_token, client_id 역할 provider)이 갖춰져 있어야 실제로 동작한다.
            partner = rows.get(provider.refresh.clientCredential.provider)
            status["auto_refresh"] = {
                "has_refresh_token": bool(row and row.refresh_token),
                "client_id_provider": provider.refresh.clientCredential.provider,
                "client_id_connected": bool(partner and partner.api_key),
                "expires_at": row.token_expires_at.isoformat() if row and row.token_expires_at else None,
                "expired": bool(row and row.token_expires_at and row.token_expires_at <= now),
            }
            status["ready"] = bool(
                status["connected"]
                and status["auto_refresh"]["has_refresh_token"]
                and status["auto_refresh"]["client_id_connected"]
            )
        else:
            status["ready"] = status["connected"]
        statuses.append(status)
    return statuses
