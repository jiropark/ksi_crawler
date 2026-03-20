"""모멘텀 전략 — 시그널 평가 및 보유 종목 홀딩/매도 판단"""

import logging
from datetime import datetime

from app.config import (
    PULLBACK_STOP_LOSS,
    PULLBACK_TARGET_1,
    TRAILING_ACTIVATE,
    TRAILING_STOP,
)
from app.api.rest import get_naver_price
from app.screener.patterns import detect_pullback
from app.storage.db import save_signal, update_position

logger = logging.getLogger(__name__)


# ── 시그널 평가 ─────────────────────────────────────────

def evaluate_pullback(screened_stocks: list[dict]) -> list[dict]:
    """스크리닝 통과 종목에 대해 모멘텀 점수를 평가하고 BUY 시그널을 반환한다."""
    signals: list[dict] = []

    for stock in screened_stocks:
        code = stock["code"]
        name = stock["name"]

        try:
            pattern = detect_pullback(stock)
        except Exception:
            logger.exception("detect_pullback 실패: %s %s", code, name)
            continue

        if pattern is None:
            continue

        score = pattern.get("score", 0)
        price = pattern.get("price", stock.get("price", 0))

        reason = f"등락률 {pattern.get('change_rate', 0):.1f}% | 거래대금 {pattern.get('trade_amount', 0)/1e8:.0f}억"

        try:
            save_signal(
                code=code,
                name=name,
                signal_type="BUY",
                strategy="momentum",
                score=score,
                reason=reason,
                price=price,
            )
        except Exception:
            logger.exception("save_signal 실패: %s", code)

        signals.append({
            "code": code,
            "name": name,
            "signal": "BUY",
            "strategy": "momentum",
            "score": score,
            "price": price,
            "reason": reason,
            "pattern_data": pattern,
        })

    signals.sort(key=lambda s: s["score"], reverse=True)

    if signals:
        logger.info(
            "모멘텀 시그널 %d건 생성 (top: %s %.3f점)",
            len(signals), signals[0]["name"], signals[0]["score"],
        )

    return signals


# ── 보유 종목 판단 ──────────────────────────────────────

def check_hold_or_sell(position: dict) -> dict:
    """보유 종목의 홀딩/매도 여부를 판단한다 (네이버 현재가 사용)."""
    code = position["code"]
    name = position["name"]
    buy_price = position["buy_price"]
    prev_highest = position.get("highest_price") or buy_price
    # 네이버에서 현재가 조회
    try:
        price_data = get_naver_price(code)
        current_price = price_data.get("price", 0) if price_data else 0
    except Exception:
        logger.exception("현재가 조회 실패: %s", code)
        return _hold_result(position, buy_price, prev_highest, "현재가 조회 실패")

    if current_price <= 0:
        return _hold_result(position, buy_price, prev_highest, "현재가 0 이하")

    # 최고가 갱신
    highest = max(prev_highest, current_price)
    if highest > prev_highest:
        try:
            update_position(position["id"], highest_price=highest)
        except Exception:
            logger.exception("highest_price 갱신 실패: %s", code)

    profit_pct = (current_price - buy_price) / buy_price * 100
    drop_from_high = (current_price - highest) / highest * 100 if highest > 0 else 0
    gain_from_buy = (highest - buy_price) / buy_price * 100 if buy_price > 0 else 0

    # 1) 손절
    if profit_pct <= PULLBACK_STOP_LOSS:
        reason = f"손절 ({profit_pct:+.2f}% ≤ {PULLBACK_STOP_LOSS}%)"
        logger.warning("[SELL] %s %s — %s", code, name, reason)
        return _result(position, "SELL", reason, current_price, profit_pct, highest)

    # 2) 익절 → 전량 매도
    if profit_pct >= PULLBACK_TARGET_1:
        reason = f"익절 ({profit_pct:+.2f}% ≥ +{PULLBACK_TARGET_1}%)"
        logger.info("[SELL] %s %s — %s", code, name, reason)
        return _result(position, "SELL", reason, current_price, profit_pct, highest)

    # 3) 트레일링 스탑 (v2: 초기 비활성화, 데이터 축적 후 재검토)
    # if gain_from_buy >= TRAILING_ACTIVATE and drop_from_high <= -TRAILING_STOP:
    #     reason = (
    #         f"트레일링 스탑 (고점 {highest:,}원 대비 {drop_from_high:+.2f}% "
    #         f"≤ -{TRAILING_STOP}%, 활성화 조건: 고점 수익률 +{gain_from_buy:.1f}%)"
    #     )
    #     logger.warning("[SELL] %s %s — %s", code, name, reason)
    #     return _result(position, "SELL", reason, current_price, profit_pct, highest)

    return _result(position, "HOLD", "HOLD", current_price, profit_pct, highest)


# ── 내부 헬퍼 ───────────────────────────────────────────

def _result(position: dict, signal: str, reason: str,
            current_price: int, profit_pct: float, highest: int) -> dict:
    return {
        "code": position["code"],
        "name": position["name"],
        "position_id": position["id"],
        "signal": signal,
        "reason": reason,
        "current_price": current_price,
        "profit_pct": round(profit_pct, 2),
        "highest_price": highest,
    }


def _hold_result(position: dict, current_price: int,
                 highest: int, reason: str) -> dict:
    buy_price = position["buy_price"]
    pct = (current_price - buy_price) / buy_price * 100 if buy_price else 0
    return _result(position, "HOLD", reason, current_price, pct, highest)
