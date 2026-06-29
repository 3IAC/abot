import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "abot.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            status TEXT DEFAULT 'open',
            strategy TEXT,
            market_conditions TEXT,
            ai_reasoning TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            stop_loss REAL,
            take_profit REAL
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence REAL,
            reasoning TEXT,
            indicators TEXT,
            created_at TEXT NOT NULL,
            acted_on INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS brain_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary TEXT,
            patterns TEXT,
            adjustments TEXT,
            win_rate REAL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            price REAL,
            rsi REAL,
            ma20 REAL,
            ma50 REAL,
            volume REAL,
            snapshot_at TEXT NOT NULL
        );
        """)

def log_trade(symbol, side, qty, entry_price, strategy, market_conditions, ai_reasoning, stop_loss, take_profit):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades (symbol, side, qty, entry_price, strategy, market_conditions, ai_reasoning, opened_at, stop_loss, take_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, side, qty, entry_price, strategy, json.dumps(market_conditions), ai_reasoning,
              datetime.now(timezone.utc).isoformat(), stop_loss, take_profit))
        return cur.lastrowid

def close_trade(trade_id, exit_price):
    with get_conn() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not trade:
            return
        pnl = (exit_price - trade["entry_price"]) * trade["qty"]
        if trade["side"] == "sell":
            pnl = -pnl
        pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
        conn.execute("""
            UPDATE trades SET exit_price=?, pnl=?, pnl_pct=?, status='closed', closed_at=?
            WHERE id=?
        """, (exit_price, pnl, pnl_pct, datetime.now(timezone.utc).isoformat(), trade_id))

def get_open_trades():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM trades WHERE status='open' ORDER BY opened_at DESC").fetchall()]

def get_all_trades(limit=100):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()]

def log_signal(symbol, action, confidence, reasoning, indicators):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO signals (symbol, action, confidence, reasoning, indicators, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, action, confidence, reasoning, json.dumps(indicators), datetime.now(timezone.utc).isoformat()))

def log_brain(summary, patterns, adjustments, win_rate):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO brain_log (summary, patterns, adjustments, win_rate, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (summary, patterns, adjustments, win_rate, datetime.now(timezone.utc).isoformat()))

def log_error(source, message):
    with get_conn() as conn:
        conn.execute("INSERT INTO errors (source, message, created_at) VALUES (?, ?, ?)",
                     (source, message, datetime.now(timezone.utc).isoformat()))
    print(f"[ERROR] {source}: {message}")

def get_stats():
    with get_conn() as conn:
        trades = conn.execute("SELECT * FROM trades WHERE status='closed'").fetchall()
        if not trades:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0, "avg_pnl": 0}
        wins = [t for t in trades if t["pnl"] and t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] and t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in trades if t["pnl"])
        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(trades), 2) if trades else 0
        }

def save_snapshot(symbol, price, rsi, ma20, ma50, volume):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO market_snapshots (symbol, price, rsi, ma20, ma50, volume, snapshot_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, price, rsi, ma20, ma50, volume, datetime.now(timezone.utc).isoformat()))

def get_latest_brain():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM brain_log ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

def get_recent_signals(limit=20):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
