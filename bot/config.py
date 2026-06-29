import os
from dotenv import load_dotenv
load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYMBOLS = ["GLD", "SLV", "SPY", "QQQ"]

MAX_POSITION_PCT = 0.10
MAX_OPEN_POSITIONS = 5
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06

SCAN_INTERVAL_MINUTES = 15
LEARN_INTERVAL_HOURS = 6

DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5000")))
