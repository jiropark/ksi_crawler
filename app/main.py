"""KIS 스크리너 — 메인 엔트리포인트 (눌림목 v2)

APScheduler 기반 스케줄링 + Flask 웹서버.
- 5분마다 스크리닝 (2단계 확인 진입)
- 3분마다 포지션 체크 (손절/익절)
- 15:20 당일 강제 청산
- 15:35 일일 스냅샷
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()  # .env 로드 (Docker env_file보다 먼저)

from app.config import MARKET_OPEN, MARKET_CLOSE, SCAN_INTERVAL_SEC, WEB_PORT

_pos_check_sec = 180  # 3분 주기 (기본값)
try:
    from app.config import POSITION_CHECK_SEC
    _pos_check_sec = POSITION_CHECK_SEC
except ImportError:
    pass
from app.storage.db import init_db
from app.strategy.portfolio import (
    run_screening_cycle,
    check_positions_cycle,
    save_daily_snapshot as _save_snapshot,
    force_close_all as _force_close,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def is_market_open() -> bool:
    """평일 장 시간(09:00~15:30)인지 확인."""
    now = datetime.now()
    # 월~금 (0=월 … 4=금)
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return MARKET_OPEN <= t <= MARKET_CLOSE


def run_screening():
    """매 5분 스크리닝 (장 시간만)."""
    if not is_market_open():
        return
    try:
        run_screening_cycle()
    except Exception:
        logger.exception("스크리닝 사이클 실패")


def check_positions():
    """매 3분 보유종목 점검 (장 시간만)."""
    if not is_market_open():
        return
    try:
        check_positions_cycle()
    except Exception:
        logger.exception("포지션 체크 실패")


def force_close():
    """15:20 당일 강제 청산."""
    try:
        _force_close()
    except Exception:
        logger.exception("강제 청산 실패")


def save_daily_snapshot():
    """매일 15:35 일일 포트폴리오 스냅샷 저장."""
    try:
        _save_snapshot()
    except Exception:
        logger.exception("일일 스냅샷 저장 실패")


def main():
    init_db()
    logger.info("DB 초기화 완료")

    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    # 매 SCAN_INTERVAL_SEC초마다 스크리닝
    scheduler.add_job(run_screening, "interval", seconds=SCAN_INTERVAL_SEC,
                      id="screening", replace_existing=True)

    # 매 3분마다 보유종목 점검
    scheduler.add_job(check_positions, "interval", seconds=_pos_check_sec,
                      id="check_positions", replace_existing=True)

    # 매일 15:20 강제 청산
    scheduler.add_job(force_close, "cron", hour=15, minute=20,
                      id="force_close", replace_existing=True)

    # 매일 15:35 일일 스냅샷
    scheduler.add_job(save_daily_snapshot, "cron", hour=15, minute=35,
                      id="daily_snapshot", replace_existing=True)

    scheduler.start()
    logger.info("스케줄러 시작")

    # Flask 웹서버
    from app.web.app import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False)


if __name__ == "__main__":
    main()
