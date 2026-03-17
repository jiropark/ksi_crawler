"""SQLite DDL — 테이블 정의"""

TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        signal_type TEXT NOT NULL CHECK(signal_type IN ('BUY','HOLD','SELL')),
        strategy TEXT NOT NULL,
        score REAL DEFAULT 0,
        reason TEXT,
        price INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
        price INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        profit_pct REAL DEFAULT 0,
        profit_amount INTEGER DEFAULT 0,
        strategy TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        buy_price INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        highest_price INTEGER DEFAULT 0,
        strategy TEXT,
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CLOSED')),
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS screening_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_scanned INTEGER DEFAULT 0,
        passed INTEGER DEFAULT 0,
        details_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        total_asset INTEGER DEFAULT 0,
        cash INTEGER DEFAULT 0,
        stock_value INTEGER DEFAULT 0,
        profit_pct REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]
