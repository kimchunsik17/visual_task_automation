"""webhook_verify.py — 인바운드 웹훅 하드닝 (백로그 34 DEV-0, ADR-0031).

무엇을 막나
  `/webhook/{endpoint_id}` 는 공개 URL 이다. 지금까지는 누구나 POST 하면 워크플로우가 돌았고, 노드 문서가 "요청 검증을 흐름 안에서 하라" 고
  사용자에게 떠넘겼다. 여기서 세 겹을 건다 — 서명 검증(발신자가 누구인지), 본문 크기 상한, 엔드포인트별 분당 상한. 중복 제거(재전송)는
  idempotency.webhook_key 가 이미 한다.

검증 모드 (webhookNode.data)
  verifyMode    none | hmac_sha256 | static_token
  verifyHeader  서명/토큰이 든 헤더 — 기본 X-Hub-Signature-256(GitHub·Bitbucket·Sentry 계열) / X-Gitlab-Token(GitLab)
  verifySecret  **API 센터 참조만** — `{{API_CENTER:webhook_secret}}` 또는 `{{API_CENTER:webhook_secret#<id>}}`. 원문 비밀은 graph 에 저장하지
                않는다(graph_data·revision·공유 템플릿에 그대로 남는 값이다). 참조가 아니면 검증 실패로 본다.
  dedupeHeader  재전송 판별 헤더(선택) — idempotency.webhook_key 가 먼저 본다.

규칙
  - HMAC 은 **파싱 전 원문 바이트**로 계산하고 `hmac.compare_digest` 로 비교한다(GitHub 문서 그대로). 헤더 값은 `sha256=<hex>` 또는 `<hex>`.
  - 실패는 401 이고 실행하지 않는다. 사유는 로그에만 남긴다 — 응답 본문으로 어느 겹이 틀렸는지 알려 주면 공격자에게 힌트다.
  - 즉시 202 응답은 EXECUTION_QUEUE=1(ENGINE-2)이 담당한다 — GitHub 는 10초 안 2xx 를 기대하므로 웹훅을 많이 쓰면 큐를 켠다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

logger = logging.getLogger("webhook_verify")

MODE_NONE = "none"
MODE_HMAC = "hmac_sha256"
MODE_TOKEN = "static_token"
MODES = (MODE_NONE, MODE_HMAC, MODE_TOKEN)
DEFAULT_HEADERS = {MODE_HMAC: "X-Hub-Signature-256", MODE_TOKEN: "X-Gitlab-Token"}
#: `/webhook/{endpoint_id}` 가 엔드포인트로 인정하는 노드 타입. githubTriggerNode(DEV-1)는 webhookNode 와 같은 수신 경로를 쓰고
#: 그 위에 이벤트 필터·평탄화가 얹힌다(connectors/services/github.py).
INBOUND_NODE_TYPES = ("webhookNode", "githubTriggerNode", "gitlabTriggerNode")
#: 노드가 verifyMode 를 비웠을 때의 기본 모드. GitHub 트리거는 기본이 HMAC 이다 — 공개 URL 에 서명 없이 열어 두는 것이 예외여야 한다.
DEFAULT_MODE_BY_TYPE = {"githubTriggerNode": MODE_HMAC, "gitlabTriggerNode": MODE_TOKEN}
#: 개발 도구 트리거 — 핸들러가 서명 뒤·실행 전에 서비스 모듈의 trigger_matches 로 거르고 envelope 으로 싼다(DEV-1 GitHub, DEV-3 GitLab).
#: 모듈은 connectors/services/<module> 이고 trigger_matches(data, event, payload)·envelope(event, delivery, payload) 를 갖는다.
INBOUND_SERVICES = {
    "githubTriggerNode": {"module": "github", "event_header": "X-GitHub-Event", "delivery_header": "X-GitHub-Delivery"},
    "gitlabTriggerNode": {"module": "gitlab", "event_header": "X-Gitlab-Event", "delivery_header": "X-Gitlab-Event-UUID"},
}
DEFAULT_SECRET_REF = "{{API_CENTER:webhook_secret}}"
SECRET_PROVIDER = "webhook_secret"

CREDENTIAL_REF_RE = re.compile(r"^\{\{API_CENTER:([\w-]+)(?:#(\d+))?\}\}$")

MAX_BODY_ENV = "WEBHOOK_MAX_BODY_BYTES"
MAX_BODY_BYTES_DEFAULT = 1_048_576          # 1 MiB — GitHub 이벤트는 보통 수십 KB, 상한은 25 MB 지만 워크플로우 입력으로는 과하다
RATE_ACTION = "webhook.receive"             # rate_limit.DEFAULT_RULES: 엔드포인트별 분당 상한(RATE_LIMIT_WEBHOOK_RECEIVE 로 조정)


@dataclass(frozen=True)
class VerifySettings:
    mode: str
    header: str
    secret_ref: Optional[str]
    dedupe_header: Optional[str]


@dataclass(frozen=True)
class VerifyOutcome:
    ok: bool
    reason: str = ""            # 로그 전용 — 응답에 싣지 않는다


def settings_from_node(node: Optional[dict]) -> VerifySettings:
    """webhookNode/githubTriggerNode.data → 설정. 모르는 모드는 타입 기본값으로, 헤더가 비면 모드별 기본값."""
    data = (node or {}).get("data") or {}
    default_mode = DEFAULT_MODE_BY_TYPE.get(str((node or {}).get("type") or ""), MODE_NONE)
    mode = str(data.get("verifyMode") or default_mode).strip().lower()
    if mode not in MODES:
        mode = default_mode
    header = str(data.get("verifyHeader") or "").strip() or DEFAULT_HEADERS.get(mode, "")
    secret_ref = str(data.get("verifySecret") or "").strip() or (DEFAULT_SECRET_REF if mode != MODE_NONE else None)
    dedupe = str(data.get("dedupeHeader") or "").strip() or None
    return VerifySettings(mode=mode, header=header, secret_ref=secret_ref, dedupe_header=dedupe)


def parse_secret_ref(ref: Optional[str]):
    """`{{API_CENTER:provider}}` / `{{API_CENTER:provider#id}}` → (provider, id|None). 참조가 아니면 None."""
    if not ref:
        return None
    m = CREDENTIAL_REF_RE.match(str(ref).strip())
    if not m:
        return None
    provider, key_id = m.group(1), m.group(2)
    return provider, (int(key_id) if key_id else None)


def resolve_secret(db, user_id, ref: Optional[str]) -> Optional[str]:
    """API 센터 참조를 비밀 원문으로. 참조가 아니거나(원문을 graph 에 넣은 경우) 저장된 키가 없으면 None."""
    parsed = parse_secret_ref(ref)
    if parsed is None or db is None or user_id is None:
        return None
    provider, key_id = parsed
    import models
    from credential_crypto import decrypt_secret

    query = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == int(user_id), models.UserApiKey.provider == provider)
    if key_id is not None:
        query = query.filter(models.UserApiKey.id == key_id)
    row = query.order_by(models.UserApiKey.id.desc()).first()
    if row is None or not row.api_key:
        return None
    return decrypt_secret(row.api_key)


def _header(headers: Optional[Mapping[str, str]], name: str) -> Optional[str]:
    if not headers or not name:
        return None
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    if value is None:
        lowered = {str(k).lower(): v for k, v in headers.items()}
        value = lowered.get(name.lower())
    return str(value).strip() if value is not None else None


def compute_hmac_sha256(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body or b"", hashlib.sha256).hexdigest()


def verify(settings: VerifySettings, headers: Optional[Mapping[str, str]], body: bytes, secret: Optional[str]) -> VerifyOutcome:
    """설정·헤더·원문·(해석된) 비밀로 판정한다. DB 를 보지 않는다 — 호출자가 resolve_secret 로 비밀을 넘긴다."""
    if settings.mode == MODE_NONE:
        return VerifyOutcome(True)
    if not secret:
        return VerifyOutcome(False, "secret 을 해석할 수 없다 — verifySecret 이 API 센터 참조가 아니거나 저장된 키가 없다")
    given = _header(headers, settings.header)
    if not given:
        return VerifyOutcome(False, f"헤더 {settings.header} 가 없다")
    if settings.mode == MODE_HMAC:
        expected = compute_hmac_sha256(secret, body)
        provided = given.split("=", 1)[1] if given.lower().startswith("sha256=") else given
        if hmac.compare_digest(expected.lower(), provided.strip().lower()):
            return VerifyOutcome(True)
        return VerifyOutcome(False, "HMAC SHA-256 서명 불일치")
    if settings.mode == MODE_TOKEN:
        if hmac.compare_digest(secret.encode("utf-8"), given.encode("utf-8")):
            return VerifyOutcome(True)
        return VerifyOutcome(False, "고정 토큰 불일치")
    return VerifyOutcome(False, f"모르는 모드 {settings.mode}")  # pragma: no cover — settings_from_node 가 걸러낸다


def max_body_bytes() -> int:
    try:
        return max(1024, int(os.getenv(MAX_BODY_ENV) or MAX_BODY_BYTES_DEFAULT))
    except ValueError:
        return MAX_BODY_BYTES_DEFAULT


def body_too_large(body: Optional[bytes]) -> bool:
    return len(body or b"") > max_body_bytes()


def log_rejection(project_id, outcome: VerifyOutcome, *, remote: Optional[str] = None) -> None:
    logger.warning("[webhook] project %s 요청 거부(401): %s%s", project_id, outcome.reason, f" (from {remote})" if remote else "")
