"""모멘텀 스코어링 모듈.

KIS 모의투자에서 분봉 API가 제한되므로,
네이버 스크리닝 데이터 기반으로 모멘텀 점수를 산출한다.
"""

import logging

from app.config import MIN_CHANGE_RATE, MAX_CHANGE_RATE

logger = logging.getLogger(__name__)


def detect_pullback(stock: dict) -> dict | None:
    """스크리닝 데이터 기반 모멘텀 점수 산출.

    Args:
        stock: screen_stocks() 결과 항목.
            {code, name, price, change_rate, volume, trade_amount, market_cap}

    Returns:
        패턴 감지 시: {detected, score, price, change_rate, ...}
        미감지 시: None
    """
    code = stock.get("code", "")
    price = stock.get("price", 0)
    change_rate = stock.get("change_rate", 0)
    trade_amount = stock.get("trade_amount", 0)
    market_cap = stock.get("market_cap", 0)

    if price <= 0:
        return None

    # 등락률 범위 체크 (10~27%)
    if change_rate < MIN_CHANGE_RATE or change_rate >= MAX_CHANGE_RATE:
        return None

    score = _calculate_score(
        change_rate=change_rate,
        trade_amount=trade_amount,
        market_cap=market_cap,
    )

    result = {
        "detected": True,
        "code": code,
        "price": price,
        "change_rate": change_rate,
        "trade_amount": trade_amount,
        "market_cap": market_cap,
        "score": round(score, 3),
    }

    logger.info("[모멘텀 감지] %s | 등락률=%.2f%% 거래대금=%s 점수=%.3f",
                code, change_rate, f"{trade_amount:,}", score)

    return result


def _calculate_score(
    change_rate: float,
    trade_amount: int,
    market_cap: int,
) -> float:
    """모멘텀 점수 산출 (0~1).

    지표:
    - 등락률: 5%=0, 15%=1 (적당한 모멘텀)
    - 거래대금: 1000억=0, 5000억+=1 (거래 활발)
    - 시총: 1000억=0.3, 1조=0.7, 5조+=1.0 (적당한 사이즈)
    """
    # 등락률 점수: 7~15% 구간 정규화 (v2)
    rate_score = min(max((change_rate - 7) / 8, 0), 1.0)

    # 거래대금 점수: 3000억~1조 구간 정규화 (v2)
    amount_billion = trade_amount / 100_000_000_000  # 억원 → 1000억 단위
    amount_score = min(max((amount_billion - 3) / 7, 0), 1.0)

    # 시총 점수
    cap_trillion = market_cap / 1_000_000_000_000  # 조원 단위
    if cap_trillion >= 5:
        cap_score = 1.0
    elif cap_trillion >= 1:
        cap_score = 0.5 + (cap_trillion - 1) / 8
    else:
        cap_score = max(cap_trillion * 0.5, 0.1)

    # 가중합
    score = (
        rate_score * 0.30
        + amount_score * 0.45
        + cap_score * 0.25
    )

    return min(max(score, 0), 1.0)
