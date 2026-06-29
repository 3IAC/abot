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
from bot.trader import run_scan, run_learn
from bot.config import SCAN_INTERVAL_MINUTES, LEARN_INTERVAL_HOURS, DASHBOARD_PORT

_shutdown = threading.Event()

def start_dashboard():
    try:
        from dashboard.app import app
        port = int(os.environ.get("PORT", DASHBOARD_PORT))
        print(f"[ABOT] Dashboard on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        db.log_error("main.dashboard", str(e))

def main():
    print("""
╬══════════════════════════════════════════════════════════╬
║           ABOT — Adaptive Trading Intelligence           ║
║         Learns. Adapts. Trades Gold, Silver, S&P.       ║
╙══════════════════════════════════════════════════════════╜
""")
    db.init_db()
    print(f"[ABOT] Scan interval: every {SCAN_INTERVAL_MINUTES} minutes")
    print(f"[ABOT] Learning cycle: every {LEARN_INTERVAL_HOURS} hours")

    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(4)},
        timezone="UTC"
    )
    scheduler.add_job(run_scan, "interval", minutes=SCAN_INTERVAL_MINUTES,
                      id="scanner", next_run_time=datetime.now(timezone.utc))
    scheduler.add_job(run_learn, "interval", hours=LEARN_INTERVAL_HOURS, id="learner")
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
