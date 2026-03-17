"""KIS API 토큰 관리 (모의투자: VTS, 실전: REAL)

모의투자 시 모든 API(시세+주문)를 VTS 도메인으로 호출.
거래량 순위만 네이버 API 사용 (KIS 모의투자 미지원).
"""

import logging
import time
import requests
from app.config import APP_KEY, APP_SECRET, BASE_URL_TRADE

logger = logging.getLogger(__name__)

# 글로벌 토큰 캐시
_access_token: str = ""
_token_expires_at: float = 0.0


def get_access_token() -> str:
    """토큰 발급/캐시/자동갱신."""
    global _access_token, _token_expires_at

    if _access_token and time.time() < _token_expires_at - 60:
        return _access_token

    url = f"{BASE_URL_TRADE}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
    }

    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    _access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))
    _token_expires_at = time.time() + expires_in

    logger.info("토큰 발급 완료 (만료: %ds)", expires_in)
    return _access_token


def get_market_token() -> str:
    """시세 조회용 토큰. 모의투자에서는 거래 토큰과 동일."""
    return get_access_token()


def get_auth_headers() -> dict:
    """KIS API 공통 인증 헤더를 반환한다."""
    token = get_access_token()
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
    }
