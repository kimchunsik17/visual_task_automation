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

from connectors import oauth
from connectors import providers as connector_providers

# 갱신 설정(토큰 URL, 앱 자격증명 위치, 여유 시간)은 credential_providers.json 의
# kakao_token 항목에 선언돼 있고, 갱신 절차 자체는 connectors/oauth.py 한 곳에 있다
# (ADR-0007, ADR-0008). 이 모듈은 호환을 위해 남은 얇은 이름이다.
_REFRESH_SPEC = connector_providers.refresh_spec("kakao_token")
KAKAO_TOKEN_URL = _REFRESH_SPEC.tokenUrl
CLIENT_ID_PROVIDER = _REFRESH_SPEC.clientCredential.provider
REFRESH_MARGIN = datetime.timedelta(minutes=_REFRESH_SPEC.marginMinutes)


def ensure_kakao_token_fresh(user_id: int, db) -> str:
    """provider='kakao_token' 의 access_token 을 반환한다(필요하면 갱신 후).

    호출부(graph.run_workflow)를 바꾸지 않기 위해 이름만 남기고, 실제 절차는 공통
    OAuth 경로에 위임한다.
    """
    return oauth.ensure_fresh_token("kakao_token", user_id, db)
