"""
kakao_utils.py — 카카오톡 개인 메시지 API(나에게 보내기/친구에게 보내기)용 OAuth access_token
자동 갱신.

배경: 카카오 REST API의 access_token은 발급 후 6시간이면 만료된다. 그동안은 사용자가 수동으로
재로그인해서 kakaoNode의 accessToken 값을 다시 붙여넣어야 했다(project 26에서 실제로 이 문제를
겪음). 하지만 로그인 시 access_token과 함께 발급되는 refresh_token은 약 2개월간 유효하고, 만료
1개월 이내에 갱신하면 새 refresh_token까지 같이 발급되어 사실상 계속 연장된다. 이 refresh_token
기반 자동 갱신은 사업자 등록과 무관하게 개인 개발자 앱에서도 그대로 쓸 수 있다(카카오 "알림톡"
비즈메시지와는 완전히 별개 — 그건 사업자 등록이 실제로 필요하다).

API Center에 저장되는 카카오 관련 값 2가지(서로 다른 provider):
  - "kakao"       : REST API 키(=client_id, 카카오 디벨로퍼스 앱의 요약 정보에서 확인) — 앱 단위 값.
  - "kakao_token" : access_token(api_key 컬럼) + refresh_token + token_expires_at — 유저가 카카오
                    로그인 OAuth 동의를 한 번 완료해서 얻은 개인 토큰 쌍.
"""
import datetime
import requests

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
# access_token 만료 시각까지 이 여유(margin) 안으로 들어오면 미리 갱신한다 — 워크플로우 실행
# 도중에 애매하게 만료되어 실패하는 것을 막기 위한 안전 버퍼.
REFRESH_MARGIN = datetime.timedelta(minutes=30)


def ensure_kakao_token_fresh(user_id: int, db) -> str:
    """provider='kakao_token' 레코드의 access_token을 반환한다. 만료가 임박했고 refresh_token과
    client_id(provider='kakao')가 모두 있으면, 반환 전에 실제로 갱신 API를 호출해서 DB에 반영한다.

    레코드가 없으면 빈 문자열을 반환한다(그래야 하류에서 '값이 없다'는 걸 정상적으로 감지한다 —
    NODE_CATALOG의 다른 credential 필드들과 동일한 규약).
    """
    import models

    token_row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == "kakao_token")
        .first()
    )
    if not token_row or not token_row.api_key:
        return ""

    needs_refresh = (
        token_row.token_expires_at is None
        or token_row.token_expires_at <= datetime.datetime.utcnow() + REFRESH_MARGIN
    )
    if not needs_refresh or not token_row.refresh_token:
        return token_row.api_key

    client_row = (
        db.query(models.UserApiKey)
        .filter(models.UserApiKey.user_id == user_id, models.UserApiKey.provider == "kakao")
        .first()
    )
    if not client_row or not client_row.api_key:
        # REST API 키(client_id)가 없으면 갱신을 시도할 방법이 없다 — 기존 값을 그대로 반환하고
        # (곧 만료되어 카카오 API가 401을 주면 그때 사용자가 알게 됨) 조용히 넘어간다.
        return token_row.api_key

    try:
        resp = requests.post(
            KAKAO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_row.api_key,
                "refresh_token": token_row.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        print(f"[kakao_utils] 토큰 갱신 실패, 기존 값 사용: {e}")
        return token_row.api_key

    new_access_token = payload.get("access_token")
    if not new_access_token:
        return token_row.api_key

    token_row.api_key = new_access_token
    expires_in = payload.get("expires_in")
    if expires_in:
        token_row.token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))
    # 카카오는 refresh_token 만료가 가까울 때만 새 refresh_token을 같이 내려준다 — 왔을 때만 갱신.
    new_refresh_token = payload.get("refresh_token")
    if new_refresh_token:
        token_row.refresh_token = new_refresh_token
        refresh_expires_in = payload.get("refresh_token_expires_in")
        # (refresh_token 자체의 만료 시각은 별도 컬럼이 없어 저장하지 않는다 — access_token
        # 갱신 실패 시 사용자가 API 센터에서 재인증하면 되므로 MVP 범위에서는 충분하다.)

    db.commit()
    print(f"[kakao_utils] user {user_id}의 카카오 access_token을 자동 갱신했습니다.")
    return new_access_token
