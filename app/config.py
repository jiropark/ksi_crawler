import os

# KIS API (모의투자)
APP_KEY = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
ACCOUNT_SUFFIX = "01"  # 모의투자 계좌 suffix
IS_REAL = os.getenv("KIS_IS_REAL", "false").lower() == "true"

# API 도메인 (모의투자 시 모든 API를 VTS 도메인으로 호출)
BASE_URL_REAL = "https://openapi.koreainvestment.com:9443"
BASE_URL_VTS = "https://openapivts.koreainvestment.com:29443"
BASE_URL_TRADE = BASE_URL_REAL if IS_REAL else BASE_URL_VTS
BASE_URL_MARKET = BASE_URL_REAL if IS_REAL else BASE_URL_VTS

# 스크리닝 기준
MIN_TRADE_AMOUNT = 100_000_000_000   # 거래대금 1000억
MIN_CHANGE_RATE = 5.0                # 등락률 +5% (이전: 10%)
MAX_CHANGE_RATE = 20.0               # 등락률 상한 20% (이전: 27%)
MIN_MARKET_CAP = 100_000_000_000     # 시총 1000억
MIN_VOLUME_RATIO = 3.0               # 평균 거래량 3배
MAX_DROP_RATE = -5.0                 # 고점대비 -5% 이내
MIN_LISTING_DAYS = 10                # 신규상장 제외

# 손익
PULLBACK_TARGET_1 = 5.0    # 1차 익절 +5% (이전: +3%)
PULLBACK_STOP_LOSS = -5.0  # 손절 -5% (이전: -3%)
TRAILING_STOP = 3.0        # 트레일링 스탑 -3% (이전: -1%)
TRAILING_ACTIVATE = 2.0    # 트레일링 활성화 최소 수익률 +2%

# 재매수 제한
COOLDOWN_MINUTES = 30      # 매도 후 재매수 쿨다운 30분
MAX_DAILY_BUY_PER_STOCK = 2  # 당일 동일 종목 최대 매수 횟수

# 매매 제한
MAX_POSITIONS = 5
POSITION_SIZE = 1_000_000  # 종목당 최대 100만원
INITIAL_CAPITAL = 5_000_000
MIN_CASH_RATIO = 0.3       # 현금 30% 유지

# 수수료/세금 (2025년 기준)
BUY_FEE_RATE = 0.00015     # 매수 수수료 0.015% (온라인 증권사)
SELL_FEE_RATE = 0.00015    # 매도 수수료 0.015%
SELL_TAX_RATE = 0.0018     # 거래세+농특세 0.18% (코스피/코스닥 동일)

# 스케줄
MARKET_OPEN = "09:00"
MARKET_CLOSE = "15:30"
SCAN_INTERVAL_SEC = 60

# 프로그램매매
PROGRAM_SELL_WARNING = 10_000_000_000
PROGRAM_SELL_CONSEC = 2

# Web
WEB_PORT = int(os.getenv("WEB_PORT", "8089"))
