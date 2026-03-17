"""기본 스크리닝 조건 필터.

네이버 금융 API에서 상승률 상위 종목을 가져온 뒤 필터링한다.
KIS 모의투자 앱키로는 거래량순위/현재가 등 시세 API가 제한되므로
네이버 데이터로 1차 스크리닝 후 KIS는 주문에만 사용한다.
"""

import json
import logging
from datetime import datetime, timedelta

from app.api.rest import get_volume_rank
from app.config import (
    MAX_CHANGE_RATE,
    MIN_CHANGE_RATE,
    MIN_MARKET_CAP,
    MIN_TRADE_AMOUNT,
)

logger = logging.getLogger(__name__)

_EXCLUDED_NAME_KEYWORDS = ("ETF", "ETN", "KODEX", "TIGER", "KBSTAR", "ARIRANG",
                           "SOL", "HANARO", "KOSEF", "KINDEX", "TIMEFOLIO",
                           "ACE", "BNK", "마이다스", "파워", "레버리지", "인버스")


def _is_etf_or_etn(code: str, name: str) -> bool:
    """ETF/ETN 여부 판정."""
    for kw in _EXCLUDED_NAME_KEYWORDS:
        if kw in name:
            return True
    return False


def _is_preferred_stock(code: str, name: str) -> bool:
    """우선주 여부 (코드 끝자리 5~9 + 이름에 '우' 포함)."""
    if name.endswith("우") or name.endswith("우B") or "우선" in name:
        return True
    if code and code[-1] in ("5", "7", "8", "9"):
        return True
    return False


def screen_stocks() -> list[dict]:
    """기본 스크리닝 조건 적용.

    네이버 상승률 순위 데이터를 기반으로 필터링한다.
    조건: 거래대금, 등락률 범위, 시가총액, ETF/우선주 제외.

    Returns:
        통과 종목 리스트: [{code, name, price, change_rate, volume,
                          trade_amount, market_cap}, ...]
    """
    logger.info("=== 스크리닝 시작 ===")

    # 1) 네이버 상승률 순위에서 후보 가져오기
    candidates = get_volume_rank()
    if not candidates:
        logger.warning("상승률 순위 조회 실패 또는 빈 결과")
        return []

    total_scanned = len(candidates)
    logger.info("상승률 순위 %d 종목 조회", total_scanned)

    # ETF/ETN, 우선주 사전 제외
    filtered = []
    for c in candidates:
        code = c["code"]
        name = c["name"]

        if _is_etf_or_etn(code, name):
            continue
        if _is_preferred_stock(code, name):
            continue
        filtered.append(c)

    logger.info("ETF/ETN/우선주 제외 후 %d 종목", len(filtered))

    passed = []
    filter_stats = {
        "trade_amount": 0,
        "change_rate_min": 0,
        "change_rate_max": 0,
        "market_cap": 0,
    }

    for c in filtered:
        code = c["code"]
        name = c["name"]
        price = c.get("price", 0)
        change_rate = c.get("change_rate", 0)
        trade_amount = c.get("trade_amount", 0)
        market_cap = c.get("market_cap", 0)
        volume = c.get("volume", 0)

        # ① 당일 누적 거래대금 >= MIN_TRADE_AMOUNT
        if trade_amount < MIN_TRADE_AMOUNT:
            filter_stats["trade_amount"] += 1
            continue

        # ② 등락률 >= MIN_CHANGE_RATE
        if change_rate < MIN_CHANGE_RATE:
            filter_stats["change_rate_min"] += 1
            continue

        # ③ 등락률 < MAX_CHANGE_RATE (상한가 근처 제외)
        if change_rate >= MAX_CHANGE_RATE:
            filter_stats["change_rate_max"] += 1
            continue

        # ④ 시가총액 >= MIN_MARKET_CAP
        if market_cap < MIN_MARKET_CAP:
            filter_stats["market_cap"] += 1
            continue

        # 모든 필터 통과
        logger.info("[통과] %s %s | 가격=%s 등락률=%.2f%% 거래대금=%s 시총=%s",
                    code, name,
                    f"{price:,}", change_rate,
                    f"{trade_amount:,}", f"{market_cap:,}")

        passed.append({
            "code": code,
            "name": name,
            "price": price,
            "change_rate": change_rate,
            "volume": volume,
            "trade_amount": trade_amount,
            "market_cap": market_cap,
            "high": price,  # 네이버 데이터에 고가 없으므로 현재가 사용
            "low": price,
            "investor_data": {},
        })

    logger.info("=== 스크리닝 완료: %d/%d 종목 통과 ===", len(passed), total_scanned)
    logger.info("탈락 사유: %s", filter_stats)

    _save_screening_log(total_scanned, len(passed), filter_stats, passed)

    return passed


def _save_screening_log(
    total: int,
    passed: int,
    filter_stats: dict,
    passed_stocks: list[dict],
) -> None:
    """screening_log 테이블에 결과 저장."""
    try:
        from app.storage.db import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        details = {
            "filter_stats": filter_stats,
            "passed_stocks": [
                {"code": s["code"], "name": s["name"], "change_rate": s["change_rate"]}
                for s in passed_stocks
            ],
        }
        cursor.execute(
            "INSERT INTO screening_log (total_scanned, passed, details_json) VALUES (?, ?, ?)",
            (total, passed, json.dumps(details, ensure_ascii=False)),
        )
        conn.commit()
    except Exception as exc:
        logger.debug("screening_log 저장 스킵: %s", exc)
