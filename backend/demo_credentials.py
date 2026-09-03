"""demo_credentials.py — 시연 공유 자격증명 폴백 (opt-in, 시연 종합보고서 §4 · 체크리스트 7).

부스 시연에서는 방문자가 그 자리에서 승인키(도로명주소·공공데이터포털 등)를 발급받을 수
없다. 두 환경변수가 **모두** 설정된 동안, 자격증명이 없는 사용자의 실행에 한해 지정
계정(부스 계정)의 API 센터 키를 대신 쓴다.

    DEMO_SHARED_CREDENTIALS_USER_ID     키 주인(부스 계정)의 user id
    DEMO_SHARED_CREDENTIALS_PROVIDERS   허용 provider 쉼표 목록 (예: "juso,data_go_kr")

원칙:
- **기본 꺼짐.** 둘 중 하나라도 없으면 아무 동작도 하지 않는다 — 시연이 끝나면
  환경변수만 지우면 원상 복구된다.
- **사용자 키가 우선.** 직접 등록한 키가 있으면 절대 대체하지 않는다(없을 때의 폴백).
- **공개 데이터 API 만 공유할 것.** kakao_token·gmail 처럼 자동 갱신·개인 데이터가
  계정에 묶인 provider 를 목록에 넣으면 부스 계정의 개인 자원이 방문자 실행에 쓰인다.
- **사용은 전부 기록한다.** 서버 로그 한 줄(즉시) + flow_execution_logs 에
  event_type="demo_credential_use" 한 행(실행 로그와 같은 트랜잭션으로 커밋).
  비밀 값은 어디에도 남기지 않는다.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, Optional

EVENT_TYPE = "demo_credential_use"


def enabled_providers() -> set:
    return {p.strip() for p in os.getenv("DEMO_SHARED_CREDENTIALS_PROVIDERS", "").split(",") if p.strip()}


def demo_user_id() -> Optional[int]:
    raw = os.getenv("DEMO_SHARED_CREDENTIALS_USER_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def fallback_user_id(provider_id: str) -> Optional[int]:
    """이 provider 에 폴백이 켜져 있으면 부스 계정 id, 아니면 None."""
    if provider_id not in enabled_providers():
        return None
    return demo_user_id()


def record_use(db, *, providers: Iterable[str], actor_user_id: Optional[int],
               shared_user_id: int, project_id: Optional[int] = None,
               source: str = "connector") -> None:
    """공유 키가 실제로 쓰였음을 기록한다. 기록 실패가 실행을 멈추면 안 된다."""
    used = sorted(set(providers))
    print(f"[demo-credentials] {source}: providers={used} 실행자 user={actor_user_id} "
          f"project={project_id} (키 주인 user={shared_user_id})")
    try:
        import usage_tracking
        usage_tracking.record_usage(
            db,
            billable_user_id=shared_user_id,   # 부스 계정 기준으로 모아 본다 (차감 없음)
            actor_user_id=actor_user_id,
            project_id=project_id,
            total_tokens=0,
            deduct_balance=False,
            event_type=EVENT_TYPE,
            outcome="success",
            trigger_type=source,
            result=json.dumps({"providers": used}, ensure_ascii=False),
        )
    except Exception as exc:
        print(f"[demo-credentials] 사용 기록 실패(서버 로그로 대신한다): {exc}")


def augment_api_key_map(db, api_key_map: Dict[str, str], *, owner_user_id: Optional[int]) -> Dict[str, str]:
    """`{{API_CENTER:<provider>}}` 치환 맵에 폴백 키를 채운다.

    소유자가 이미 가진 placeholder 는 건드리지 않는다. 추가된 {placeholder: provider} 를
    돌려준다 — 호출자(graph.run_workflow)가 실제로 치환에 쓰인 것만 골라 기록한다.
    """
    added: Dict[str, str] = {}
    providers = enabled_providers()
    shared_uid = demo_user_id()
    if not providers or shared_uid is None or shared_uid == owner_user_id:
        return added

    import models
    from credential_crypto import decrypt_secret

    rows = (db.query(models.UserApiKey)
            .filter(models.UserApiKey.user_id == shared_uid,
                    models.UserApiKey.provider.in_(sorted(providers))).all())
    for row in rows:
        placeholder = f"{{{{API_CENTER:{row.provider}}}}}"
        if placeholder in api_key_map or not row.api_key:
            continue
        secret = decrypt_secret(row.api_key)
        if secret:
            api_key_map[placeholder] = secret
            added[placeholder] = row.provider
    return added
