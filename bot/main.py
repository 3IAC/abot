import os
import sys
import time
import signal
import threading
from datetime import datetime, timezone

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

import bot.database as db
import bot.alpaca_client as alpaca
from bot.trader import run_scan, run_learn, check_open_trades
from bot.config import SCAN_INTERVAL_MINUTES, LEARN_INTERVAL_HOURS, DASHBOARD_PORT, MAX_TRADE_DURATION_MINUTES

_shutdown = threading.Event()
_market_was_open = False  # tracks last known market state for open-watcher

def start_dashboard():
    try:
        from dashboard.app import app
        port = int(os.environ.get("PORT", DASHBOARD_PORT))
        print(f"[ABOT] Dashboard on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        db.log_error("main.dashboard", str(e))

def _market_open_watcher():
    """Fire an immediate scan the moment market transitions from closed to open."""
    global _market_was_open
    try:
        clock = alpaca.get_clock()
        if not clock:
            return
        is_open = clock.get("is_open", False)
        if is_open and not _market_was_open:
            print("[ABOT] Market just opened — firing immediate scan")
            run_scan()
        _market_was_open = is_open
    except Exception:
        pass


def _close_stale_positions():
    """
    On startup: close ALL open Alpaca positions immediately.
    BTC/ETH may be orphans (opened before DB tracking) — close them regardless.
    Also close any DB-tracked open trades that are too old.
    """
    from datetime import datetime, timezone, timedelta
    from bot.trader import _log_learning

    # ── Close all live Alpaca positions (orphans + tracked) ──────────
    live_positions = alpaca.get_positions()
    if live_positions:
        print(f"[ABOT] STARTUP: found {len(live_positions)} open Alpaca position(s) — closing all")
        for pos in live_positions:
            sym = pos.get("symbol", "")
            # Convert BTCUSD → BTC/USD for our close helper
            canonical = sym
            if sym == "BTCUSD":
                canonical = "BTC/USD"
            elif sym == "ETHUSD":
                canonical = "ETH/USD"
            try:
                ok = alpaca.close_position(canonical)
                price = float(pos.get("current_price") or pos.get("avg_entry_price") or 0)
                entry = float(pos.get("avg_entry_price") or 0)
                pnl_pct = (price - entry) / entry * 100 if entry else 0
                outcome = "WIN" if pnl_pct > 0 else "LOSS"
                print(f"[ABOT] STARTUP CLOSE {sym} ok={ok} | entry={entry:.2f} current={price:.2f} | {pnl_pct:+.2f}% {outcome}")
            except Exception as e:
                db.log_error("startup.close_live", str(e))

    # ── Also mark any lingering DB open trades as closed ─────────────
    open_db = db.get_open_trades()
    for trade in open_db:
        try:
            sym = trade["symbol"]
            price = alpaca.get_latest_price(sym)
            if price:
                db.close_trade(trade["id"], price)
                entry = trade["entry_price"]
                pnl_pct = (price - entry) / entry * 100
                outcome = "WIN" if pnl_pct > 0 else "LOSS"
                print(f"[ABOT] STARTUP DB-CLOSE {sym} {outcome} | {pnl_pct:+.2f}%")
                _log_learning(sym, trade, price, pnl_pct)
        except Exception as e:
            db.log_error("startup.close_db", str(e))


def main():
    print("""
╬══════════════════════════════════════════════════════════╬
║           ABOT — Adaptive Trading Intelligence           ║
║         Learns. Adapts. Trades Gold, Silver, S&P.       ║
╙══════════════════════════════════════════════════════════╜
""")
    db.init_db()
    _close_stale_positions()
    print(f"[ABOT] Scan interval: every {SCAN_INTERVAL_MINUTES} minutes")
    print(f"[ABOT] Learning cycle: every {LEARN_INTERVAL_HOURS} hours")

    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(4)},
        timezone="UTC"
    )
    scheduler.add_job(run_scan, "interval", minutes=SCAN_INTERVAL_MINUTES,
                      id="scanner", next_run_time=datetime.now(timezone.utc))
    scheduler.add_job(run_learn, "interval", hours=LEARN_INTERVAL_HOURS, id="learner")
    scheduler.add_job(check_open_trades, "interval", minutes=2, id="exit_monitor")
    scheduler.add_job(_market_open_watcher, "interval", seconds=30, id="open_watcher")
    scheduler.start()

    dash_thread = threading.Thread(target=start_dashboard, daemon=True)
    dash_thread.start()

    def _shutdown_handler(sig, frame):
        print("\n[ABOT] Shutting down...")
        _shutdown.set()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    while not _shutdown.is_set():
        time.sleep(5)

if __name__ == "__main__":
    main()
