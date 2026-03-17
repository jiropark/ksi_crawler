"""텔레그램 봇 알림 모듈 (KIS 스크리너)"""

import logging
import requests
import os

logger = logging.getLogger(__name__)

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _send(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        resp = requests.post(
            API_URL.format(token=TG_BOT_TOKEN),
            json={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if not resp.json().get("ok"):
            logger.warning("텔레그램 전송 실패: %s", resp.text)
    except Exception:
        logger.exception("텔레그램 전송 에러")


def notify_buy(code: str, name: str, price: int, qty: int, amount: int, score: float = 0, reason: str = ""):
    """매수 알림"""
    text = (
        f"<b>📈 [KIS 스크리너] 매수</b>\n"
        f"종목: {name} ({code})\n"
        f"수량: {qty}주 @ {price:,}원\n"
        f"금액: {amount:,}원"
    )
    if score:
        text += f"\n스코어: {score:.1f}"
    if reason:
        text += f"\n사유: {reason}"
    _send(text)


def notify_sell(code: str, name: str, price: int, qty: int,
                profit_pct: float, profit_amount: int, reason: str = ""):
    """매도 알림"""
    emoji = "📉" if profit_amount < 0 else "📊"
    text = (
        f"<b>{emoji} [KIS 스크리너] 매도</b>\n"
        f"종목: {name} ({code})\n"
        f"수량: {qty}주 @ {price:,}원\n"
        f"손익: {profit_pct:+.2f}% ({profit_amount:+,}원)"
    )
    if reason:
        text += f"\n사유: {reason}"
    _send(text)


def notify_daily_report(summary: dict, positions: list):
    """일일 리포트"""
    total = summary["total_asset"]
    cash = summary["cash"]
    stock = summary["stock_value"]
    pct = summary["profit_pct"]
    sign = "+" if pct >= 0 else ""

    lines = [
        f"<b>📋 [KIS 스크리너] 일일 리포트</b>",
        f"",
        f"💰 총자산: {total:,}원 ({sign}{pct:.1f}%)",
        f"  현금: {cash:,}원 / 주식: {stock:,}원",
        f"",
    ]

    if positions:
        lines.append(f"<b>📌 보유종목 ({len(positions)})</b>")
        for p in positions:
            buy = p.get("buy_price", 0)
            highest = p.get("highest_price", buy)
            pnl = ((highest - buy) / buy * 100) if buy else 0
            lines.append(f"  {p['name']}: {pnl:+.1f}%")
        lines.append("")

    _send("\n".join(lines))
