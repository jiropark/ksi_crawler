"""웹 라우트 정의"""

from datetime import datetime

from flask import Blueprint, jsonify, render_template

from app.config import INITIAL_CAPITAL, MAX_POSITIONS, POSITION_SIZE
from app.storage.db import (
    get_cash_from_trades,
    get_daily_portfolios,
    get_open_positions,
    get_signals,
    get_total_fees,
    get_trades,
)

bp = Blueprint("main", __name__)


def _market_status() -> str:
    """현재 장 상태를 반환한다."""
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return "장외 (주말)"
    t = now.time()
    from datetime import time as T
    if T(9, 0) <= t <= T(15, 30):
        return "장중"
    return "장외"


def _portfolio_summary() -> dict:
    """포트폴리오 요약 데이터를 실시간으로 구성한다."""
    positions = get_open_positions()

    # trades 기반으로 현금 실시간 계산 (수수료 포함)
    cash = get_cash_from_trades(INITIAL_CAPITAL)
    total_fees = get_total_fees()
    stock_value = sum(p.get("amount", 0) for p in positions)
    total_asset = cash + stock_value
    profit_pct = ((total_asset - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL else 0.0

    return {
        "total_asset": total_asset,
        "cash": cash,
        "stock_value": stock_value,
        "profit_pct": round(profit_pct, 2),
        "total_fees": total_fees,
        "position_count": len(positions),
        "max_positions": MAX_POSITIONS,
        "positions": positions,
        "initial_capital": INITIAL_CAPITAL,
    }


@bp.route("/")
def index():
    summary = _portfolio_summary()
    signals = get_signals(limit=5)
    daily = get_daily_portfolios(limit=30)
    return render_template(
        "index.html",
        summary=summary,
        signals=signals,
        daily=daily,
        market_status=_market_status(),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@bp.route("/signals")
def signals_page():
    signals = get_signals(limit=100)
    buy_count = sum(1 for s in signals if s.get("signal_type") == "BUY")
    sell_count = sum(1 for s in signals if s.get("signal_type") == "SELL")
    hold_count = sum(1 for s in signals if s.get("signal_type") == "HOLD")
    return render_template(
        "signals.html",
        signals=signals,
        buy_count=buy_count,
        sell_count=sell_count,
        hold_count=hold_count,
        market_status=_market_status(),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@bp.route("/trades")
def trades_page():
    trades = get_trades(limit=100)
    total_profit = sum(t.get("profit_amount", 0) or 0 for t in trades)
    win_count = sum(1 for t in trades if (t.get("profit_pct") or 0) > 0)
    loss_count = sum(1 for t in trades if (t.get("profit_pct") or 0) < 0)
    trade_count = len([t for t in trades if t.get("side") == "SELL"])
    win_rate = (win_count / trade_count * 100) if trade_count else 0.0
    return render_template(
        "trades.html",
        trades=trades,
        total_profit=total_profit,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
        market_status=_market_status(),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── JSON API ──

@bp.route("/api/portfolio")
def api_portfolio():
    return jsonify(_portfolio_summary())


@bp.route("/api/signals")
def api_signals():
    return jsonify(get_signals(limit=50))


@bp.route("/api/trades")
def api_trades():
    return jsonify(get_trades(limit=50))
