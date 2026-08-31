"""connectors/contract.py — 노드 정의의 `connector` 블록 (ADR-0007).

공식 연동 노드는 ADR-0005 의 NodeDefinition 을 그대로 쓰되, 연동에만 필요한 사실
(서비스, 동작 모드, 필요한 scope, 페이지네이션 방식, 재시도 정책, 모드별 부수효과)을
`connector` 블록에 덧붙인다. 노드당 정의 파일을 하나로 유지하기 위해 별도 레지스트리를
만들지 않았다.

이 블록이 있으면 실행 계층은 노드별 코드를 읽지 않고도 다음을 안다.

    - 어떤 자격증명이 어떤 scope 로 필요한지 (연결 안내와 dry-run 판정)
    - 이 모드가 외부에 쓰기를 하는지 (dry-run 에서 막아야 하는지)
    - 실패했을 때 다시 시도해도 되는지 (재시도 정책)
    - 목록을 어떻게 넘겨 받아야 하는지 (페이지네이션)
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import providers
from .errors import TERMS_BLOCKED, ConnectorError
from .pagination import PaginationConfig
from .retry import RetryPolicy
from .session import ConnectorSession, RateLimit

SideEffect = Literal["none", "external-read", "external-write"]


_DATE_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    """`YYYY-MM-DD` **만** 받는다. 다른 형식은 None — 호출부가 '형식 오류'로 다룬다.

    `date.fromisoformat` 는 3.11 부터 `20260830` 같은 기본 형식도 받는데, 설정 파일에 두 형식이
    섞이면 사람이 읽다 틀린다. 한 가지로 고정한다."""
    if not value or not _DATE_SHAPE.match(str(value)):
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorCredential(_Strict):
    # credential_providers.json 의 id. 로딩 시점에 존재를 확인한다.
    provider: str
    scopes: List[str] = Field(default_factory=list)
    optional: bool = False


class RetryPolicySpec(_Strict):
    maxAttempts: int = 3
    baseDelaySeconds: float = 0.5
    maxDelaySeconds: float = 20.0
    # 멱등 키를 갖춘 쓰기 요청만 열어준다. 기본은 닫혀 있다 — 중복 발송이 한 번 실패보다 나쁘다.
    retryNonIdempotent: bool = False

    def to_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.maxAttempts,
            base_delay=self.baseDelaySeconds,
            max_delay=self.maxDelaySeconds,
        )


class RateLimitSpec(_Strict):
    requestsPerMinute: Optional[int] = None

    def to_rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=self.requestsPerMinute)


class PaginationSpec(_Strict):
    style: Literal["cursor", "page", "offset"] = "cursor"
    cursorParam: str = "pageToken"
    cursorPath: str = "nextPageToken"
    itemsPath: str = "items"
    pageParam: str = "page"
    offsetParam: str = "offset"
    limitParam: str = "limit"
    pageSize: int = 50
    maxPages: int = 20
    maxItems: Optional[int] = None

    def to_config(self) -> PaginationConfig:
        return PaginationConfig.from_dict(self.model_dump(by_alias=True))


class TermsGate(_Strict):
    """이 서비스를 자동 처리해도 된다는 **근거**와 그 근거의 유효기간.

    커뮤니티 연동에서 나온 요구다(한국형 노드 계획 §6.5). "robots.txt 가 허용한다"는 약관상
    동의를 대체하지 못하고, 제휴는 갱신되거나 끊긴다. 그래서 근거를 코드 주석이나 회의록이
    아니라 **정의 파일에 적고 만료되면 호출을 막는다.**

    `basis` 세 가지 말고는 받지 않는다 — "공개돼 있으니 괜찮다"는 근거가 아니다.
    """

    basis: Literal["official_feed", "official_api", "written_partnership"]
    # 그 근거를 확인할 수 있는 곳(공식 RSS 안내 페이지, API 문서, 계약 문서 관리번호 등).
    evidenceUrl: Optional[str] = None
    # 마지막으로 사람이 직접 확인한 날. YYYY-MM-DD.
    verifiedAt: str
    # 이 날짜가 지나면 재확인 전까지 호출하지 않는다. 없으면 만료가 없다는 뜻이다.
    expiresAt: Optional[str] = None
    note: Optional[str] = None


class ConnectorSpec(_Strict):
    service: str
    role: Literal["trigger", "action"]
    # 이 노드가 할 수 있는 동작들. 모드마다 부수효과와 출력 스키마가 다르다.
    modes: List[str] = Field(default_factory=list)
    credentials: List[ConnectorCredential] = Field(default_factory=list)
    baseUrl: Optional[str] = None
    timeoutSeconds: float = 15.0
    pagination: Optional[PaginationSpec] = None
    rateLimit: Optional[RateLimitSpec] = None
    retryPolicy: RetryPolicySpec = Field(default_factory=RetryPolicySpec)
    # 모드별 부수효과 등급. dry-run 이 무엇을 막을지 판단하는 근거다.
    sideEffectByMode: Dict[str, SideEffect] = Field(default_factory=dict)
    inputSchema: Dict[str, Any] = Field(default_factory=dict)
    outputSchemaByMode: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # 이 연동을 만들 때 근거로 삼은 공식 문서와, 그 문서를 마지막으로 확인한 날(YYYY-MM-DD).
    # 외부 API 는 조용히 바뀐다 — "언제 기준의 사실인가"가 없으면 낡은 구현을 알아채지 못한다.
    docsUrl: Optional[str] = None
    verifiedAt: Optional[str] = None
    # 자동 처리 허용 근거. 선언하면 만료 시 호출 자체를 막는다(아래 terms_blocked_reason).
    termsGate: Optional[TermsGate] = None
    # 실패를 **어디로** 알리는 API 인가.
    #
    #   "http" (기본)  인증 실패는 401/403, 한도 초과는 429 처럼 HTTP 상태로 온다
    #   "body"         항상 200 을 주고 본문 안의 코드로 실패를 알린다
    #
    # 국내 공공 API 에 후자가 흔하다(도로명주소는 승인키가 틀려도 200 + errorCode E0001).
    # 이걸 구분하지 않으면 mock 계약이 "auth_failed 는 401 이어야 한다"고 요구하는 바람에
    # **실제로 일어나지 않는 상황을 재현한 fixture** 를 만들게 된다 — 없느니만 못하다.
    errorStyle: Literal["http", "body"] = "http"

    def validate_against_registry(self) -> List[str]:
        """정의 파일이 실제로 존재하는 provider 를 가리키는지, 모드 선언이 서로 맞는지.
        어긋나면 실행 시점에 '자격증명 없음'으로만 드러나서 원인을 찾기 어렵다."""
        problems: List[str] = []
        for credential in self.credentials:
            if providers.get_provider(credential.provider) is None:
                problems.append(
                    f"{self.service}: credential provider '{credential.provider}' 가 "
                    "credential_providers.json 에 없다"
                )
        for mode in self.sideEffectByMode:
            if self.modes and mode not in self.modes:
                problems.append(f"{self.service}: sideEffectByMode 의 '{mode}' 가 modes 에 없다")
        for mode in self.outputSchemaByMode:
            if self.modes and mode not in self.modes:
                problems.append(f"{self.service}: outputSchemaByMode 의 '{mode}' 가 modes 에 없다")
        missing = [m for m in self.modes if m not in self.sideEffectByMode]
        if missing:
            # 등급이 없으면 dry-run 이 안전한 쪽으로 가정할 수밖에 없어, 실제로는 읽기만 하는
            # 모드까지 막히거나 반대로 쓰기 모드가 새어 나간다.
            problems.append(f"{self.service}: sideEffectByMode 에 등급이 없는 모드 — {', '.join(missing)}")

        # 날짜는 형식이 어긋나면 비교가 조용히 실패한다 — 만료된 근거를 유효하다고 읽는 쪽으로
        # 틀리므로 로딩 시점에 막는다.
        for label, value in (("verifiedAt", self.verifiedAt),):
            if value is not None and _parse_date(value) is None:
                problems.append(f"{self.service}: {label} 는 YYYY-MM-DD 여야 한다 — {value!r}")
        if self.verifiedAt and not self.docsUrl:
            problems.append(f"{self.service}: verifiedAt 이 있으면 무엇을 확인했는지(docsUrl)도 있어야 한다")
        gate = self.termsGate
        if gate is not None:
            for label, value in (("termsGate.verifiedAt", gate.verifiedAt),
                                 ("termsGate.expiresAt", gate.expiresAt)):
                if value is not None and _parse_date(value) is None:
                    problems.append(f"{self.service}: {label} 는 YYYY-MM-DD 여야 한다 — {value!r}")
            if gate.basis == "written_partnership" and not gate.evidenceUrl:
                problems.append(
                    f"{self.service}: written_partnership 은 근거(evidenceUrl)를 남겨야 한다"
                )

        # 범용 크롤러에서 막는 곳을 전용 connector 로는 그냥 나가게 두면 정책이 반쪽이 된다.
        # 어느 호스트가 제휴 대상인지는 url_guard 한 곳에서만 정하고 여기서 그대로 쓴다.
        gated_host = self._partnership_host()
        if gated_host and gate is None:
            problems.append(
                f"{self.service}: '{gated_host}' 는 자동 처리 근거(termsGate)를 선언해야 한다 — "
                "official_feed / official_api / written_partnership 중 하나"
            )
        return problems

    def _partnership_host(self) -> Optional[str]:
        """baseUrl 이 제휴 확인 대상 호스트를 가리키면 그 호스트를 돌려준다."""
        if not self.baseUrl:
            return None
        try:
            import url_guard
        except ImportError:      # connectors 를 단독으로 쓰는 경우
            return None
        from urllib.parse import urlparse

        host = urlparse(self.baseUrl).hostname
        return host if host and url_guard.requires_partnership(host) else None

    def terms_blocked_reason(self, *, today: Optional[datetime.date] = None) -> Optional[str]:
        """자동 처리를 막아야 하는 이유. 막을 이유가 없으면 None.

        `termsGate` 를 **선언한 연동에만** 적용된다. 선언하지 않은 기존 연동의 동작은 그대로다.
        """
        gate = self.termsGate
        if gate is None:
            return None
        today = today or datetime.date.today()
        expires = _parse_date(gate.expiresAt) if gate.expiresAt else None
        if expires is not None and expires < today:
            return (
                f"{self.service} 의 자동 처리 근거가 {gate.expiresAt} 에 만료됐습니다. "
                "공식 API·RSS 또는 서면 제휴를 다시 확인한 뒤 사용할 수 있습니다."
            )
        return None

    def writes_externally(self, mode: Optional[str]) -> bool:
        """dry-run 에서 막아야 하는 모드인지. 모르는 모드는 쓰기로 간주한다(안전한 쪽)."""
        if mode is None:
            return any(effect == "external-write" for effect in self.sideEffectByMode.values())
        return self.sideEffectByMode.get(mode, "external-write") == "external-write"

    def required_providers(self) -> List[str]:
        return [c.provider for c in self.credentials if not c.optional]

    def new_session(self, **kwargs: Any) -> ConnectorSession:
        """이 노드의 정책이 그대로 반영된 호출 창구를 만든다.

        근거가 만료된 연동은 **여기서** 막는다 — HTTP client 를 만들기 전에 끊어야 "실수로 한 번
        나갔다"가 없다.
        """
        if self.terms_blocked_reason() is not None:
            raise ConnectorError(
                code=TERMS_BLOCKED, service=self.service,
                context={"termsGate": "expired",
                         "expiresAt": self.termsGate.expiresAt if self.termsGate else None},
            )
        return ConnectorSession(
            self.service,
            timeout=self.timeoutSeconds,
            retry_policy=self.retryPolicy.to_policy(),
            rate_limit=self.rateLimit.to_rate_limit() if self.rateLimit else None,
            **kwargs,
        )

    def pagination_config(self) -> PaginationConfig:
        return self.pagination.to_config() if self.pagination else PaginationConfig()
