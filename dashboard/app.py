import os, sys, time as _time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flask import Flask, jsonify, render_template, request
import bot.database as db
import bot.alpaca_client as alpaca

app = Flask(__name__)

_cache: dict = {}
_CACHE_TTL = 30

def _cached(key, fn):
    now = _time.time()
    if key in _cache and now - _cache[key][1] < _CACHE_TTL:
        return _cache[key][0]
    data = fn()
    _cache[key] = (data, now)
    return data

_TF_MAP = {"M1":"1Min","M5":"5Min","M15":"15Min","H1":"1Hour","H4":"4Hour","D":"1Day"}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/account")
def api_account():
    acc = alpaca.get_account()
    if not acc:
        return jsonify({"error": "no account"})
    return jsonify({
        "portfolio_value": float(acc.get("portfolio_value", 0)),
        "cash": float(acc.get("cash", 0)),
        "buying_power": float(acc.get("buying_power", 0)),
        "pnl_today": float(acc.get("equity", 0)) - float(acc.get("last_equity", 0)),
    })

@app.route("/api/candles")
def api_candles():
    symbol = request.args.get("symbol", "BTC/USD")
    tf = _TF_MAP.get(request.args.get("tf", "M5"), "5Min")
    count = min(int(request.args.get("count", "200")), 500)
    key = f"candles_{symbol}_{tf}"
    bars = _cached(key, lambda: alpaca.get_bars(symbol, timeframe=tf, limit=count))
    return jsonify(bars)

@app.route("/api/positions")
def api_positions():
    positions = alpaca.get_positions()
    # Enrich with SL/TP + opened_at from our DB
    db_trades = {t["symbol"]: t for t in db.get_open_trades()}
    for p in positions:
        sym = p.get("symbol", "")
        # Try as-is, then with slash (BTCUSD -> BTC/USD)
        db_t = db_trades.get(sym)
        if not db_t and len(sym) > 4 and "/" not in sym:
            for k, v in db_trades.items():
                if k.replace("/", "") == sym:
                    db_t = v
                    break
        if db_t:
            p["stop_loss"] = db_t.get("stop_loss")
            p["take_profit"] = db_t.get("take_profit")
            p["opened_at"] = db_t.get("opened_at")
            p["ai_reasoning"] = db_t.get("ai_reasoning", "")
    return jsonify(positions)

@app.route("/api/trades")
def api_trades():
    return jsonify(db.get_all_trades(limit=50))

@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())

@app.route("/api/signals")
def api_signals():
    return jsonify(db.get_recent_signals(20))

@app.route("/api/brain")
def api_brain():
    return jsonify(db.get_latest_brain() or {})

@app.route("/api/clock")
def api_clock():
    clock = alpaca.get_clock()
    return jsonify(clock or {"is_open": False})

@app.route("/api/performance")
def api_performance():
    return jsonify(db.get_performance())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
