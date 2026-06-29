import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flask import Flask, jsonify, render_template
import bot.database as db
import bot.alpaca_client as alpaca

app = Flask(__name__)

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
        "pnl_today": float(acc.get("equity", 0)) - float(acc.get("last_equity", 0))
    })

@app.route("/api/positions")
def api_positions():
    positions = alpaca.get_positions()
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
