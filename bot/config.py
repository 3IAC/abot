import os
from dotenv import load_dotenv
load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYMBOLS = ["GLD", "SLV", "SPY", "QQQ"]          # stocks — market hours only
CRYPTO_SYMBOLS = ["BTC/USD", "ETH/USD"]          # crypto — 24/7

MAX_POSITION_PCT = 0.10
MAX_OPEN_POSITIONS = 10
STOP_LOSS_PCT = 0.005    # 0.5% — fast scalp stop
TAKE_PROFIT_PCT = 0.015  # 1.5% — fast scalp target

SCAN_INTERVAL_MINUTES = 2
LEARN_INTERVAL_HOURS = 6
DEFAULT_CONFIDENCE_THRESHOLD = 0.25
MAX_TRADE_DURATION_MINUTES = 15

DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5000")))
