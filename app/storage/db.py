"""SQLite 데이터 접근 계층"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from app.models import TABLES_DDL

DB_PATH = "/data/stock_screener.db"


@contextmanager
def _conn():
    """WAL 모드 SQLite 커넥션 컨텍스트."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


# ── 초기화 ──────────────────────────────────────────────

def init_db():
    """모든 테이블 생성 + 마이그레이션."""
    with _conn() as c:
        for ddl in TABLES_DDL:
            c.execute(ddl)
        # 마이그레이션: original_quantity 컬럼 추가
        try:
            c.execute("ALTER TABLE positions ADD COLUMN original_quantity INTEGER DEFAULT 0")
        except Exception:
            pass  # 이미 존재하면 무시


# ── signals ─────────────────────────────────────────────

def save_signal(code: str, name: str, signal_type: str, strategy: str,
                score: float = 0, reason: str = "", price: int = 0) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO signals (code, name, signal_type, strategy, score, reason, price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, signal_type, strategy, score, reason, price),
        )
        return cur.lastrowid


def get_signals(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── trades ──────────────────────────────────────────────

def save_trade(code: str, name: str, side: str, price: int, quantity: int,
               amount: int, profit_pct: float = 0, profit_amount: int = 0,
               strategy: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO trades (code, name, side, price, quantity, amount, "
            "profit_pct, profit_amount, strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, name, side, price, quantity, amount, profit_pct, profit_amount, strategy),
        )
        return cur.lastrowid


def get_trades(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── positions ───────────────────────────────────────────

def save_position(code: str, name: str, buy_price: int, quantity: int,
                  amount: int, strategy: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO positions (code, name, buy_price, quantity, amount, "
            "highest_price, strategy, status, original_quantity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)",
            (code, name, buy_price, quantity, amount, buy_price, strategy, quantity),
        )
        return cur.lastrowid


def update_position(position_id: int, **kwargs) -> None:
    """가변 컬럼 업데이트. ex) update_position(1, highest_price=52000)"""
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [position_id]
    with _conn() as c:
        c.execute(f"UPDATE positions SET {cols} WHERE id = ?", vals)


def get_open_positions() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY opened_at"
        ).fetchall()
        return [dict(r) for r in rows]


def close_position(position_id: int, closed_at: str | None = None) -> None:
    ts = closed_at or datetime.now().isoformat()
    with _conn() as c:
        c.execute(
            "UPDATE positions SET status = 'CLOSED', closed_at = ? WHERE id = ?",
            (ts, position_id),
        )


# ── screening_log ──────────────────────────────────────

def save_screening_log(total_scanned: int, passed: int,
                       details: Any = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO screening_log (total_scanned, passed, details_json) "
            "VALUES (?, ?, ?)",
            (total_scanned, passed, json.dumps(details, ensure_ascii=False) if details else None),
        )
        return cur.lastrowid


# ── daily_portfolio ────────────────────────────────────

def save_daily_portfolio(date: str, total_asset: int, cash: int,
                         stock_value: int, profit_pct: float) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO daily_portfolio (date, total_asset, cash, stock_value, profit_pct) "
            "VALUES (?, ?, ?, ?, ?)",
            (date, total_asset, cash, stock_value, profit_pct),
        )
        return cur.lastrowid


def get_daily_portfolios(limit: int = 30) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM daily_portfolio ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_cash_from_trades(initial_capital: int) -> int:
    """trades 기반 현금 계산: 초기자본 - 매수총액 + 매도총액 - 수수료/세금."""
    from app.config import BUY_FEE_RATE, SELL_FEE_RATE, SELL_TAX_RATE
    with _conn() as c:
        buy = c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM trades WHERE side = 'BUY'"
        ).fetchone()[0]
        sell = c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM trades WHERE side = 'SELL'"
        ).fetchone()[0]
        buy_fees = int(buy * BUY_FEE_RATE)
        sell_fees = int(sell * (SELL_FEE_RATE + SELL_TAX_RATE))
        return initial_capital - buy + sell - buy_fees - sell_fees


def get_total_fees() -> int:
    """누적 수수료+세금 총액."""
    from app.config import BUY_FEE_RATE, SELL_FEE_RATE, SELL_TAX_RATE
    with _conn() as c:
        buy = c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM trades WHERE side = 'BUY'"
        ).fetchone()[0]
        sell = c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM trades WHERE side = 'SELL'"
        ).fetchone()[0]
        return int(buy * BUY_FEE_RATE) + int(sell * (SELL_FEE_RATE + SELL_TAX_RATE))
