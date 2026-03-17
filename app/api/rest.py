"""KIS Open API REST 호출 모듈.

Rate limit: 초당 20건 (0.05s sleep).
모든 함수는 에러 시 빈 dict/list를 반환하여 서비스 중단을 방지한다.
"""

import logging
import time
from datetime import datetime

import requests

from app.auth import get_access_token, get_market_token
from app.config import APP_KEY, APP_SECRET, BASE_URL_MARKET, BASE_URL_TRADE, IS_REAL

logger = logging.getLogger(__name__)

_session = requests.Session()
_last_request_time: float = 0.0
_RATE_LIMIT_INTERVAL = 0.05  # 초당 20건


# ──────────────────────────────────────────────
# 공통 요청
# ──────────────────────────────────────────────

def _request(
    method: str,
    path: str,
    headers_extra: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    use_trade_domain: bool = False,
) -> dict:
    """공통 API 호출. Rate limit 준수, 에러 핸들링.

    Args:
        use_trade_domain: True면 주문/잔고용 도메인(모의투자), False면 시세 도메인(실전).
    """
    global _last_request_time

    # rate limit
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_INTERVAL:
        time.sleep(_RATE_LIMIT_INTERVAL - elapsed)

    base_url = BASE_URL_TRADE if use_trade_domain else BASE_URL_MARKET
    url = f"{base_url}{path}"
    token = get_access_token() if use_trade_domain else get_market_token()

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "custtype": "P",
    }
    if headers_extra:
        headers.update(headers_extra)

    try:
        _last_request_time = time.time()
        resp = _session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # KIS API 에러 코드 체크
        rt_cd = data.get("rt_cd")
        if rt_cd and rt_cd != "0":
            msg = data.get("msg1", "unknown error")
            logger.error("KIS API error [%s] %s: %s", path, rt_cd, msg)
            return {}

        return data
    except requests.RequestException as exc:
        logger.error("HTTP error [%s]: %s", path, exc)
        return {}
    except Exception as exc:
        logger.error("Unexpected error [%s]: %s", path, exc)
        return {}


# ──────────────────────────────────────────────
# 현재가 조회
# ──────────────────────────────────────────────

def get_current_price(stock_code: str) -> dict:
    """현재가 시세 조회.

    Returns:
        {price, change_rate, volume, trade_amount, market_cap,
         high, low, open, prev_close, volume_ratio, listing_date, ...}
        에러 시 빈 dict.
    """
    data = _request(
        "GET",
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        headers_extra={"tr_id": "FHKST01010100"},
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        },
    )
    if not data:
        return {}

    out = data.get("output", {})
    if not out:
        return {}

    try:
        return {
            "code": stock_code,
            "name": out.get("hts_kor_isnm", ""),
            "price": int(out.get("stck_prpr", 0)),
            "change_rate": float(out.get("prdy_ctrt", 0)),
            "volume": int(out.get("acml_vol", 0)),
            "trade_amount": int(out.get("acml_tr_pbmn", 0)),
            "market_cap": int(out.get("hts_avls", 0)) * 100_000_000,  # 억 → 원
            "high": int(out.get("stck_hgpr", 0)),
            "low": int(out.get("stck_lwpr", 0)),
            "open": int(out.get("stck_oprc", 0)),
            "prev_close": int(out.get("stck_sdpr", 0)),
            "volume_ratio": float(out.get("vol_tnrt", 0)),  # 거래량 회전율
            "listing_date": out.get("stck_lstn_date", ""),  # YYYYMMDD
            "chegyol_strength": float(out.get("seln_cntg_smtn", 0)),
        }
    except (ValueError, TypeError) as exc:
        logger.warning("현재가 파싱 실패 [%s]: %s", stock_code, exc)
        return {}


# ──────────────────────────────────────────────
# 분봉 데이터
# ──────────────────────────────────────────────

def get_minute_chart(stock_code: str, time_unit: str = "1") -> list[dict]:
    """분봉 차트 데이터 조회.

    Args:
        stock_code: 종목코드 (6자리)
        time_unit: 분봉 단위 ("1", "3", "5", "10", "15", "30", "60")

    Returns:
        [{time, open, high, low, close, volume, trade_amount}, ...]
        최신 데이터가 리스트 앞. 에러 시 빈 list.
    """
    now = datetime.now().strftime("%H%M%S")

    data = _request(
        "GET",
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        headers_extra={"tr_id": "FHKST03010200"},
        params={
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": now,
            "FID_PW_DATA_INCU_YN": "Y",
        },
    )
    if not data:
        return []

    output2 = data.get("output2", [])
    if not output2:
        return []

    result = []
    for item in output2:
        try:
            result.append({
                "time": item.get("stck_cntg_hour", ""),
                "open": int(item.get("stck_oprc", 0)),
                "high": int(item.get("stck_hgpr", 0)),
                "low": int(item.get("stck_lwpr", 0)),
                "close": int(item.get("stck_prpr", 0)),
                "volume": int(item.get("cntg_vol", 0)),
                "trade_amount": int(item.get("acml_tr_pbmn", 0)),
            })
        except (ValueError, TypeError):
            continue

    return result


# ──────────────────────────────────────────────
# 거래량 순위
# ──────────────────────────────────────────────

def get_volume_rank() -> list[dict]:
    """상승률 상위 종목 조회 (네이버 금융 API 기반).

    모의투자 앱키로는 KIS 거래량 순위 API가 빈 결과를 반환하므로
    네이버 금융 모바일 API에서 KOSPI+KOSDAQ 상승률 상위 종목을 가져온다.

    Returns:
        [{code, name, price, change_rate, volume, trade_amount, market_cap}, ...]
        에러 시 빈 list.
    """
    result = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for market in ("KOSPI", "KOSDAQ"):
        try:
            resp = requests.get(
                f"https://m.stock.naver.com/api/stocks/up/{market}",
                params={"page": "1", "pageSize": "50"},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("네이버 %s 상승률 순위 조회 실패: %s", market, exc)
            continue

        for item in data.get("stocks", []):
            try:
                code = item.get("itemCode", "")
                if not code or len(code) != 6:
                    continue

                # 쉼표 제거 후 숫자 변환
                price_str = item.get("closePrice", "0").replace(",", "")
                vol_str = item.get("accumulatedTradingVolume", "0").replace(",", "")
                val_str = item.get("accumulatedTradingValue", "0").replace(",", "")
                mcap_str = item.get("marketValue", "0").replace(",", "")

                result.append({
                    "code": code,
                    "name": item.get("stockName", ""),
                    "price": int(price_str),
                    "change_rate": float(item.get("fluctuationsRatio", 0)),
                    "volume": int(vol_str),
                    "trade_amount": int(val_str) * 1_000_000,  # 백만원 → 원
                    "market_cap": int(mcap_str) * 100_000_000,  # 억원 → 원
                })
            except (ValueError, TypeError):
                continue

    logger.info("네이버 상승률 순위: KOSPI+KOSDAQ %d종목 조회", len(result))
    return result


# ──────────────────────────────────────────────
# 네이버 개별 종목 현재가
# ──────────────────────────────────────────────

def get_naver_price(stock_code: str) -> dict:
    """네이버 금융에서 개별 종목 현재가를 조회한다.

    Returns:
        {price, change_rate, volume, trade_amount, market_cap, high, low, name}
        에러 시 빈 dict.
    """
    try:
        resp = requests.get(
            f"https://m.stock.naver.com/api/stock/{stock_code}/basic",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
    except Exception as exc:
        logger.debug("네이버 현재가 조회 실패 [%s]: %s", stock_code, exc)
        return {}

    try:
        stock_info = data
        price_str = str(stock_info.get("closePrice", "0")).replace(",", "")
        high_str = str(stock_info.get("highPrice", "0")).replace(",", "")
        low_str = str(stock_info.get("lowPrice", "0")).replace(",", "")
        vol_str = str(stock_info.get("accumulatedTradingVolume", "0")).replace(",", "")
        val_str = str(stock_info.get("accumulatedTradingValue", "0")).replace(",", "")
        mcap_str = str(stock_info.get("marketValue", "0")).replace(",", "")

        return {
            "code": stock_code,
            "name": stock_info.get("stockName", ""),
            "price": int(price_str),
            "change_rate": float(stock_info.get("fluctuationsRatio", 0)),
            "volume": int(vol_str),
            "trade_amount": int(val_str) * 1_000_000,  # 백만원 → 원
            "market_cap": int(mcap_str) * 100_000_000,  # 억원 → 원
            "high": int(high_str),
            "low": int(low_str),
        }
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("네이버 가격 파싱 실패 [%s]: %s", stock_code, exc)
        return {}


# ──────────────────────────────────────────────
# 투자자별 매매동향
# ──────────────────────────────────────────────

def get_investor_data(stock_code: str) -> dict:
    """투자자별 매매동향 (당일).

    Returns:
        {foreign_buy, foreign_sell, foreign_net,
         inst_buy, inst_sell, inst_net,
         individual_buy, individual_sell, individual_net}
        에러 시 빈 dict.
    """
    today = datetime.now().strftime("%Y%m%d")

    data = _request(
        "GET",
        "/uapi/domestic-stock/v1/quotations/inquire-investor",
        headers_extra={"tr_id": "FHKST01010900"},
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": today,
            "FID_INPUT_DATE_2": today,
        },
    )
    if not data:
        return {}

    # output1: 투자자별 매매 데이터 (리스트)
    output = data.get("output", [])
    if not output:
        return {}

    # 첫 번째 행이 당일 데이터
    row = output[0] if isinstance(output, list) else output

    try:
        foreign_buy = int(row.get("frgn_ntby_qty", 0) or 0)   # 외국인 순매수 수량
        inst_buy = int(row.get("orgn_ntby_qty", 0) or 0)       # 기관 순매수 수량

        return {
            "foreign_buy": max(foreign_buy, 0),
            "foreign_sell": abs(min(foreign_buy, 0)),
            "foreign_net": foreign_buy,
            "inst_buy": max(inst_buy, 0),
            "inst_sell": abs(min(inst_buy, 0)),
            "inst_net": inst_buy,
            "individual_net": int(row.get("prsn_ntby_qty", 0) or 0),
        }
    except (ValueError, TypeError) as exc:
        logger.warning("투자자 데이터 파싱 실패 [%s]: %s", stock_code, exc)
        return {}


# ──────────────────────────────────────────────
# 프로그램 매매 현황
# ──────────────────────────────────────────────

def get_program_trade(stock_code: str) -> dict:
    """프로그램 매매 현황 조회.

    Returns:
        {program_buy, program_sell, program_net}
        에러 시 빈 dict.
    """
    data = _request(
        "GET",
        "/uapi/domestic-stock/v1/quotations/program-trade-by-stock",
        headers_extra={"tr_id": "FHPPG04650100"},
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        },
    )
    if not data:
        return {}

    output = data.get("output", [])
    if not output:
        return {}

    # 첫 번째 행 = 최신 데이터
    row = output[0] if isinstance(output, list) else output

    try:
        buy = int(row.get("prgm_seln_amt", 0))   # 프로그램 매수 금액
        sell = int(row.get("prgm_shnu_amt", 0))   # 프로그램 매도 금액

        return {
            "program_buy": buy,
            "program_sell": sell,
            "program_net": buy - sell,
        }
    except (ValueError, TypeError) as exc:
        logger.warning("프로그램매매 파싱 실패 [%s]: %s", stock_code, exc)
        return {}
