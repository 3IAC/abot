import requests
from bot.config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, ALPACA_DATA_URL
import bot.database as db

def _headers():
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json"
    }

def get_account():
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/account", headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
        db.log_error("alpaca", f"account {r.status_code}: {r.text[:200]}")
    except Exception as e:
        db.log_error("alpaca", f"account exception: {e}")
    return None

def get_positions():
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/positions", headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        db.log_error("alpaca", f"positions exception: {e}")
    return []

def get_position(symbol):
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/positions/{symbol}", headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        db.log_error("alpaca", f"position {symbol} exception: {e}")
    return None

def place_order(symbol, qty, side, order_type="market", stop_loss=None, take_profit=None):
    body = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": "day"
    }
    if stop_loss or take_profit:
        body["order_class"] = "bracket"
        if stop_loss:
            body["stop_loss"] = {"stop_price": str(round(stop_loss, 2))}
        if take_profit:
            body["take_profit"] = {"limit_price": str(round(take_profit, 2))}
    try:
        r = requests.post(f"{ALPACA_BASE_URL}/v2/orders", headers=_headers(), json=body, timeout=10)
        if r.status_code in (200, 201):
            return r.json()
        db.log_error("alpaca", f"order {r.status_code}: {r.text[:300]}")
    except Exception as e:
        db.log_error("alpaca", f"order exception: {e}")
    return None

def close_position(symbol):
    try:
        r = requests.delete(f"{ALPACA_BASE_URL}/v2/positions/{symbol}", headers=_headers(), timeout=10)
        if r.status_code in (200, 204):
            return True
    except Exception as e:
        db.log_error("alpaca", f"close {symbol} exception: {e}")
    return False

def get_bars(symbol, timeframe="1Day", limit=60):
    try:
        params = {"symbols": symbol, "timeframe": timeframe, "limit": limit, "feed": "iex"}
        r = requests.get(f"{ALPACA_DATA_URL}/v2/stocks/bars", headers=_headers(), params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("bars", {}).get(symbol, [])
        db.log_error("alpaca", f"bars {symbol} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        db.log_error("alpaca", f"bars {symbol} exception: {e}")
    return []

def get_latest_price(symbol):
    try:
        r = requests.get(f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/trades/latest",
                         headers=_headers(), params={"feed": "iex"}, timeout=10)
        if r.status_code == 200:
            return float(r.json()["trade"]["p"])
    except Exception as e:
        db.log_error("alpaca", f"price {symbol} exception: {e}")
    return None

def get_clock():
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/clock", headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        db.log_error("alpaca", f"clock exception: {e}")
    return None
