"""가상 포트폴리오 관리 및 메인 매매 사이클"""

import logging
from datetime import datetime

from app.config import (
    BUY_FEE_RATE,
    COOLDOWN_MINUTES,
    INITIAL_CAPITAL,
    MAX_DAILY_BUY_PER_STOCK,
    MAX_POSITIONS,
    MIN_CASH_RATIO,
    POSITION_SIZE,
    SELL_FEE_RATE,
    SELL_TAX_RATE,
)
from app.api.rest import get_naver_price
from app.screener.filters import screen_stocks
from app.storage.db import (
    close_position,
    get_open_positions,
    save_daily_portfolio,
    save_position,
    save_trade,
    update_position,
)
from app.strategy.pullback import check_hold_or_sell, evaluate_pullback

logger = logging.getLogger(__name__)


class Portfolio:
    """가상 매매 포트폴리오 (초기 자본 500만원)."""

    _instance: "Portfolio | None" = None

    def __init__(self) -> None:
        self._positions: list[dict] = []
        self._buy_total: int = 0   # 누적 매수 금액
        self._sell_total: int = 0  # 누적 매도 금액
        self._fees_total: int = 0  # 누적 수수료+세금
        self._reload()

    # ── 싱글턴 ──────────────────────────────────────────

    @classmethod
    def instance(cls) -> "Portfolio":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 상태 로드 ───────────────────────────────────────

    def _reload(self) -> None:
        """DB에서 현재 OPEN 포지션과 거래 내역을 로드해 상태를 재구성한다."""
        self._positions = get_open_positions()
        self._buy_total = sum(p["amount"] for p in self._positions)
        from app.storage.db import _conn  # noqa: WPS433

        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS s FROM trades WHERE side = 'SELL'"
                ).fetchone()
                self._sell_total = row["s"] if row else 0
                row = c.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS s FROM trades WHERE side = 'BUY'"
                ).fetchone()
                total_bought = row["s"] if row else 0
        except Exception:
            logger.exception("포트폴리오 DB 로드 실패")
            total_bought = self._buy_total
            self._sell_total = 0

        self._total_bought = total_bought
        # 누적 수수료 계산: 매수분 + 매도분
        self._fees_total = (
            int(total_bought * BUY_FEE_RATE)
            + int(self._sell_total * (SELL_FEE_RATE + SELL_TAX_RATE))
        )
        logger.info(
            "포트폴리오 로드: 포지션 %d개, 현금 %s원 (누적수수료 %s원)",
            len(self._positions), f"{self.cash:,}", f"{self._fees_total:,}",
        )

    # ── 프로퍼티 ────────────────────────────────────────

    @property
    def cash(self) -> int:
        """현재 현금 잔고 = 초기자본 - 누적매수 + 누적매도 - 누적수수료."""
        return INITIAL_CAPITAL - self._total_bought + self._sell_total - self._fees_total

    @property
    def total_fees(self) -> int:
        """누적 수수료+세금."""
        return self._fees_total

    @property
    def total_positions(self) -> int:
        """보유 종목 수."""
        return len(self._positions)

    @property
    def positions(self) -> list[dict]:
        return list(self._positions)

    # ── 매수 가능 여부 ──────────────────────────────────

    def can_buy(self) -> bool:
        """매수 가능 여부: 포지션 수 < MAX 이고 현금 비율 > MIN_CASH_RATIO."""
        if self.total_positions >= MAX_POSITIONS:
            return False
        # 현금 비율 체크: 매수 후에도 MIN_CASH_RATIO 이상 유지해야 함
        total_asset = self._estimate_total_asset()
        if total_asset <= 0:
            return False
        min_cash = int(total_asset * MIN_CASH_RATIO)
        return self.cash > min_cash

    def calculate_quantity(self, price: int) -> int:
        """매수 수량 계산.

        POSITION_SIZE(100만원) 범위 내에서, 현재 현금과 최소현금비율을
        고려한 최대 수량을 반환한다.
        """
        if price <= 0:
            return 0
        # 사용 가능 금액 = min(POSITION_SIZE, 현금 - 최소현금)
        total_asset = self._estimate_total_asset()
        min_cash = int(total_asset * MIN_CASH_RATIO)
        available = min(POSITION_SIZE, max(0, self.cash - min_cash))
        return available // price

    # ── 매수 ────────────────────────────────────────────

    def buy(self, code: str, name: str, price: int, strategy: str) -> dict | None:
        """가상 매수를 실행한다.

        Returns
        -------
        dict | None
            매수 성공 시 trade dict, 실패 시 None.
        """
        if not self.can_buy():
            logger.warning("매수 불가: 포지션 %d/%d, 현금 %s원",
                           self.total_positions, MAX_POSITIONS, f"{self.cash:,}")
            return None

        # 중복 종목 체크
        if any(p["code"] == code for p in self._positions):
            logger.warning("이미 보유 중: %s %s", code, name)
            return None

        # 쿨다운 체크: 최근 N분 이내 매도한 종목 재매수 방지
        if self._is_in_cooldown(code):
            logger.info("쿨다운 중: %s %s (%d분 이내 매도)", code, name, COOLDOWN_MINUTES)
            return None

        # 당일 동일 종목 매수 횟수 제한
        if self._daily_buy_count(code) >= MAX_DAILY_BUY_PER_STOCK:
            logger.info("당일 매수 제한: %s %s (최대 %d회)", code, name, MAX_DAILY_BUY_PER_STOCK)
            return None

        qty = self.calculate_quantity(price)
        if qty <= 0:
            logger.warning("매수 수량 0: %s %s (가격 %s원)", code, name, f"{price:,}")
            return None

        amount = price * qty
        # 최소 매수 금액 체크 (10만원 미만 소액 매수 방지)
        if amount < 100_000:
            logger.info("소액 매수 방지: %s %s (%s원 < 10만원)", code, name, f"{amount:,}")
            return None
        buy_fee = int(amount * BUY_FEE_RATE)

        # DB 저장
        try:
            pos_id = save_position(code, name, price, qty, amount, strategy)
            trade_id = save_trade(code, name, "BUY", price, qty, amount, strategy=strategy)
        except Exception:
            logger.exception("매수 DB 저장 실패: %s %s", code, name)
            return None

        # 내부 상태 갱신 (수수료 포함)
        self._total_bought += amount
        self._fees_total += buy_fee
        self._positions.append({
            "id": pos_id,
            "code": code,
            "name": name,
            "buy_price": price,
            "quantity": qty,
            "amount": amount,
            "highest_price": price,
            "strategy": strategy,
            "status": "OPEN",
        })

        trade = {
            "id": trade_id,
            "code": code,
            "name": name,
            "side": "BUY",
            "price": price,
            "quantity": qty,
            "amount": amount,
            "strategy": strategy,
        }

        logger.info(
            "[BUY] %s %s | %s원 x %d주 = %s원 (수수료 %s원) | 잔여현금 %s원",
            code, name, f"{price:,}", qty, f"{amount:,}", f"{buy_fee:,}", f"{self.cash:,}",
        )

        try:
            from app.notifier import notify_buy
            notify_buy(code, name, price, qty, amount)
        except Exception:
            logger.debug("매수 알림 전송 실패")

        return trade

    # ── 매도 ────────────────────────────────────────────

    def sell(self, code: str, price: int, ratio: float = 1.0) -> dict | None:
        """가상 매도를 실행한다.

        Parameters
        ----------
        code : str
            종목코드.
        price : int
            매도 단가.
        ratio : float
            매도 비율 (1.0=전량, 0.5=반매도).

        Returns
        -------
        dict | None
            매도 성공 시 trade dict, 실패 시 None.
        """
        pos = self._find_position(code)
        if pos is None:
            logger.warning("보유하지 않은 종목: %s", code)
            return None

        sell_qty = max(1, int(pos["quantity"] * ratio))
        # 반매도 시 남은 수량이 0이 되면 전량 매도로
        if sell_qty >= pos["quantity"]:
            sell_qty = pos["quantity"]
            ratio = 1.0

        sell_amount = price * sell_qty
        sell_fee = int(sell_amount * (SELL_FEE_RATE + SELL_TAX_RATE))
        buy_price = pos["buy_price"]
        # 수익 계산: 매수 수수료 + 매도 수수료/세금 반영
        buy_fee_per_share = int(buy_price * BUY_FEE_RATE)
        net_profit_per_share = price - buy_price - buy_fee_per_share - int(price * (SELL_FEE_RATE + SELL_TAX_RATE))
        profit_amount = net_profit_per_share * sell_qty
        profit_pct = (net_profit_per_share / (buy_price + buy_fee_per_share)) * 100 if buy_price else 0

        # DB 저장
        try:
            trade_id = save_trade(
                code, pos["name"], "SELL", price, sell_qty, sell_amount,
                profit_pct=round(profit_pct, 2),
                profit_amount=profit_amount,
                strategy=pos.get("strategy", ""),
            )
        except Exception:
            logger.exception("매도 trade 저장 실패: %s", code)
            return None

        try:
            if ratio >= 1.0:
                close_position(pos["id"])
                self._positions = [p for p in self._positions if p["code"] != code]
            else:
                remaining_qty = pos["quantity"] - sell_qty
                remaining_amount = buy_price * remaining_qty
                update_position(pos["id"], quantity=remaining_qty, amount=remaining_amount)
                # 내부 상태 갱신
                for p in self._positions:
                    if p["code"] == code:
                        p["quantity"] = remaining_qty
                        p["amount"] = remaining_amount
                        break
        except Exception:
            logger.exception("포지션 업데이트 실패: %s", code)

        self._sell_total += sell_amount
        self._fees_total += sell_fee

        side_label = "SELL" if ratio >= 1.0 else "PARTIAL_SELL"
        logger.info(
            "[%s] %s %s | %s원 x %d주 = %s원 (수수료+세금 %s원) | 순수익 %+.2f%% (%s원)",
            side_label, code, pos["name"],
            f"{price:,}", sell_qty, f"{sell_amount:,}", f"{sell_fee:,}",
            profit_pct, f"{profit_amount:+,}",
        )

        result = {
            "id": trade_id,
            "code": code,
            "name": pos["name"],
            "side": "SELL",
            "price": price,
            "quantity": sell_qty,
            "amount": sell_amount,
            "profit_pct": round(profit_pct, 2),
            "profit_amount": profit_amount,
        }

        try:
            from app.notifier import notify_sell
            notify_sell(code, pos["name"], price, sell_qty,
                        round(profit_pct, 2), profit_amount)
        except Exception:
            logger.debug("매도 알림 전송 실패")

        return result

    # ── 최고가 갱신 ─────────────────────────────────────

    def update_highest_prices(self) -> None:
        """보유 종목의 현재가를 조회해 highest_price를 갱신한다."""
        for pos in self._positions:
            try:
                data = get_naver_price(pos["code"])
                cur = data.get("price", 0) if isinstance(data, dict) else 0
                if cur > pos.get("highest_price", 0):
                    update_position(pos["id"], highest_price=cur)
                    pos["highest_price"] = cur
                    logger.debug(
                        "최고가 갱신: %s %s → %s원",
                        pos["code"], pos["name"], f"{cur:,}",
                    )
            except Exception:
                logger.debug("최고가 갱신 실패: %s", pos["code"])

    # ── 요약 ────────────────────────────────────────────

    def get_summary(self) -> dict:
        """포트폴리오 요약 정보를 반환한다."""
        stock_value = self._estimate_stock_value()
        total_asset = self.cash + stock_value
        profit_pct = (total_asset - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

        return {
            "total_asset": total_asset,
            "cash": self.cash,
            "stock_value": stock_value,
            "positions": self.total_positions,
            "profit_pct": round(profit_pct, 2),
            "initial_capital": INITIAL_CAPITAL,
        }

    # ── 내부 헬퍼 ───────────────────────────────────────

    def _is_in_cooldown(self, code: str) -> bool:
        """최근 COOLDOWN_MINUTES 이내에 매도한 종목인지 확인."""
        from app.storage.db import _conn
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT COUNT(*) FROM trades WHERE code = ? AND side = 'SELL' "
                    "AND created_at >= datetime('now', 'localtime', ?)",
                    (code, f"-{COOLDOWN_MINUTES} minutes"),
                ).fetchone()
                return row[0] > 0
        except Exception:
            return False

    def _daily_buy_count(self, code: str) -> int:
        """당일 동일 종목 매수 횟수."""
        from app.storage.db import _conn
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT COUNT(*) FROM trades WHERE code = ? AND side = 'BUY' "
                    "AND DATE(created_at) = DATE('now', 'localtime')",
                    (code,),
                ).fetchone()
                return row[0]
        except Exception:
            return 0

    def _find_position(self, code: str) -> dict | None:
        for p in self._positions:
            if p["code"] == code:
                return p
        return None

    def _estimate_stock_value(self) -> int:
        """보유 종목 평가액 (현재가 조회 시도, 실패 시 매입가 사용)."""
        total = 0
        for pos in self._positions:
            try:
                data = get_naver_price(pos["code"])
                cur = data.get("price", 0) if isinstance(data, dict) else 0
                total += (cur if cur > 0 else pos["buy_price"]) * pos["quantity"]
            except Exception:
                total += pos["buy_price"] * pos["quantity"]
        return total

    def _estimate_total_asset(self) -> int:
        """총 자산 추정 (빠른 계산용, 매입가 기준)."""
        stock = sum(p["buy_price"] * p["quantity"] for p in self._positions)
        return self.cash + stock


# ── 메인 사이클 함수들 ──────────────────────────────────


def run_screening_cycle() -> None:
    """1분마다 실행되는 메인 스크리닝-매수 사이클.

    1. screen_stocks()로 스크리닝
    2. evaluate_pullback()로 시그널 생성
    3. BUY 시그널 → portfolio.buy() 실행
    """
    portfolio = Portfolio.instance()

    if not portfolio.can_buy():
        logger.debug("매수 불가 상태, 스크리닝 스킵")
        return

    # 1. 스크리닝
    try:
        screened = screen_stocks()
    except Exception:
        logger.exception("screen_stocks() 실패")
        return

    if not screened:
        logger.debug("스크리닝 통과 종목 없음")
        return

    logger.info("스크리닝 통과: %d종목", len(screened))

    # 2. 눌림목 시그널 평가
    signals = evaluate_pullback(screened)
    if not signals:
        logger.debug("눌림목 시그널 없음")
        return

    # 3. 매수 실행 (score 높은 순서대로)
    for sig in signals:
        if not portfolio.can_buy():
            logger.info("매수 한도 도달, 매수 중단")
            break

        result = portfolio.buy(
            code=sig["code"],
            name=sig["name"],
            price=sig["price"],
            strategy=sig["strategy"],
        )
        if result:
            logger.info(
                "매수 체결: %s %s (score %.1f, %s)",
                sig["code"], sig["name"], sig["score"], sig["reason"],
            )


def check_positions_cycle() -> None:
    """5분마다 실행되는 보유 종목 체크-매도 사이클.

    1. 보유 종목 순회
    2. check_hold_or_sell() 판단
    3. SELL/PARTIAL_SELL → portfolio.sell() 실행
    4. highest_price 갱신
    """
    portfolio = Portfolio.instance()

    if portfolio.total_positions == 0:
        logger.debug("보유 종목 없음, 체크 스킵")
        return

    # 최고가 먼저 갱신
    portfolio.update_highest_prices()

    # DB에서 최신 포지션 다시 로드 (highest_price 반영)
    positions = get_open_positions()

    for pos in positions:
        decision = check_hold_or_sell(pos)

        if decision["signal"] == "SELL":
            portfolio.sell(
                code=decision["code"],
                price=decision["current_price"],
                ratio=1.0,
            )
        elif decision["signal"] == "PARTIAL_SELL":
            portfolio.sell(
                code=decision["code"],
                price=decision["current_price"],
                ratio=0.5,
            )
        # HOLD는 로깅만 (WARNING 포함 시 이미 pullback.py에서 로그)

    summary = portfolio.get_summary()
    logger.info(
        "포트폴리오: 총자산 %s원 (수익 %+.2f%%), 현금 %s원, 포지션 %d개",
        f"{summary['total_asset']:,}",
        summary["profit_pct"],
        f"{summary['cash']:,}",
        summary["positions"],
    )


def save_daily_snapshot() -> None:
    """매일 15:35 실행. 일일 포트폴리오 스냅샷을 DB에 저장한다."""
    portfolio = Portfolio.instance()
    summary = portfolio.get_summary()
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        save_daily_portfolio(
            date=today,
            total_asset=summary["total_asset"],
            cash=summary["cash"],
            stock_value=summary["stock_value"],
            profit_pct=summary["profit_pct"],
        )
        logger.info(
            "[일일 스냅샷] %s | 총자산 %s원 | 수익 %+.2f%%",
            today, f"{summary['total_asset']:,}", summary["profit_pct"],
        )

        # 텔레그램 일일 리포트
        try:
            from app.notifier import notify_daily_report
            notify_daily_report(summary, portfolio.positions)
        except Exception:
            logger.debug("일일 리포트 전송 실패")

    except Exception:
        logger.exception("일일 스냅샷 저장 실패")
