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
MIN_TRADE_AMOUNT = 30_000_000_000    # 거래대금 300억 (v2: 기존 100억)
MIN_CHANGE_RATE = 7.0                # 등락률 +7% (v2: 기존 5%)
MAX_CHANGE_RATE = 15.0               # 등락률 상한 15% (v2: 기존 20%)
MIN_MARKET_CAP = 100_000_000_000     # 시총 1000억
MIN_VOLUME_RATIO = 3.0               # 평균 거래량 3배
MAX_DROP_RATE = -5.0                 # 고점대비 -5% 이내
MIN_LISTING_DAYS = 10                # 신규상장 제외

# 손익
PULLBACK_TARGET_1 = 7.0    # 1차 익절 +7% 전량 매도 (v2: 기존 +5%)
PULLBACK_STOP_LOSS = -4.0  # 손절 -4% (v2: 기존 -5%)
TRAILING_STOP = 2.5        # 트레일링 스탑 -2.5% (v2: 기존 -3%, 초기엔 미사용)
TRAILING_ACTIVATE = 4.0    # 트레일링 활성화 +4% (v2: 기존 +2%, 초기엔 미사용)

# 재매수 제한
COOLDOWN_MINUTES = 9999    # 사실상 당일 재매수 금지 (v2: 기존 30분)
MAX_DAILY_BUY_PER_STOCK = 1  # 당일 동일 종목 1회 (v2: 기존 2회)

# 매매 제한
MAX_POSITIONS = 3           # 최대 3종목 (v2: 기존 5)
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
SCAN_INTERVAL_SEC = 300     # 5분 (v2: 기존 60초)

# 2단계 진입 필터
WATCHLIST_MIN_WAIT_SEC = 300       # 최소 대기 시간 5분
WATCHLIST_PULLBACK_MIN = -1.0      # 눌림 허용 최소 (%)
WATCHLIST_PULLBACK_MAX = 2.0       # 추가 상승 허용 최대 (%)

# 포지션 체크 주기
POSITION_CHECK_SEC = 180    # 3분

# 일일 최대 매수 건수
MAX_DAILY_BUYS = 5

# 당일 강제 청산 시간
FORCED_CLOSE_TIME = "15:20"

# 프로그램매매
PROGRAM_SELL_WARNING = 10_000_000_000
PROGRAM_SELL_CONSEC = 2

# Web
WEB_PORT = int(os.getenv("WEB_PORT", "8089"))
