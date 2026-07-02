from datetime import datetime, timezone, timedelta
import bot.database as db
import bot.alpaca_client as alpaca
from bot.brain import analyze_signal, learn_from_trades
from bot.indicators import get_all_indicators
from bot.config import (
    SYMBOLS, CRYPTO_SYMBOLS, MAX_POSITION_PCT, MAX_OPEN_POSITIONS,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, DEFAULT_CONFIDENCE_THRESHOLD,
    MAX_TRADE_DURATION_MINUTES
)

_MAX_AGE = timedelta(minutes=MAX_TRADE_DURATION_MINUTES)


def _scan_symbol(symbol, is_crypto_symbol, open_symbols, portfolio_value, recent_trades):
    """Scan one symbol on 1Min bars and place a trade if signal qualifies."""
    bars = alpaca.get_bars(symbol, timeframe="1Min", limit=100)
    if not bars or len(bars) < 20:
        print(f"[ABOT] {symbol}: insufficient bar data ({len(bars) if bars else 0} bars)")
        return False

    indicators = get_all_indicators(bars)
    db.save_snapshot(symbol, indicators.get("price"), indicators.get("rsi"),
                     indicators.get("ma20"), indicators.get("ma50"), indicators.get("volume"))

    symbol_trades = [t for t in recent_trades if t["symbol"] == symbol]
    signal = analyze_signal(symbol, indicators, symbol_trades)
    threshold = db.get_adaptive_threshold(symbol, default=DEFAULT_CONFIDENCE_THRESHOLD)

    # Always log signal so dashboard populates
    db.log_signal(symbol, signal["action"], signal["confidence"],
                  signal["reasoning"], indicators)

    print(f"[ABOT] {symbol}: {signal['action'].upper()} ({signal['confidence']:.0%}) "
          f"threshold={threshold:.0%} — {signal['key_signal']}")

    if signal["action"] == "buy" and symbol not in open_symbols and signal["confidence"] >= threshold:
        price = indicators["price"]
        max_dollars = portfolio_value * MAX_POSITION_PCT

        if is_crypto_symbol:
            qty = round(max_dollars / price, 6)
        else:
            qty = max(1, int(max_dollars / price))

        stop_loss = round(price * (1 - STOP_LOSS_PCT), 4)
        take_profit = round(price * (1 + TAKE_PROFIT_PCT), 4)

        order = alpaca.place_order(symbol, qty, "buy", stop_loss=stop_loss, take_profit=take_profit)
        if order:
            db.log_trade(symbol, "buy", qty, price, "ai_signal",
                         indicators, signal["reasoning"], stop_loss, take_profit)
            print(f"[ABOT] {'CRYPTO' if is_crypto_symbol else 'STOCK'} BUY "
                  f"{qty} {symbol} @ ${price} | SL: ${stop_loss} | TP: ${take_profit}")
            return True
    return False


def run_scan():
    """Main scan: stocks only if market open, crypto always."""
    print("[ABOT] Starting market scan...")

    clock = alpaca.get_clock()
    market_open = clock.get("is_open", False) if clock else False

    account = alpaca.get_account()
    if not account:
        print("[ABOT] Could not fetch account")
        return

    portfolio_value = float(account.get("portfolio_value", 100000))
    open_positions = alpaca.get_positions()
    open_symbols = [p["symbol"] for p in open_positions]

    if len(open_positions) >= MAX_OPEN_POSITIONS:
        print(f"[ABOT] Max positions ({MAX_OPEN_POSITIONS}) reached")
        return

    recent_trades = db.get_all_trades(limit=100)

    # ── Crypto: always scan 24/7 ──────────────────────────────────────
    for symbol in CRYPTO_SYMBOLS:
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            break
        try:
            _scan_symbol(symbol, True, open_symbols, portfolio_value, recent_trades)
        except Exception as e:
            db.log_error(f"trader.crypto.{symbol}", str(e))

    # ── Stocks: only when market open ────────────────────────────────
    if not market_open:
        print("[ABOT] Market closed — skipping stocks")
        return

    for symbol in SYMBOLS:
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            break
        try:
            _scan_symbol(symbol, False, open_symbols, portfolio_value, recent_trades)
        except Exception as e:
            db.log_error(f"trader.stock.{symbol}", str(e))


def check_open_trades():
    """
    Exit monitor: close trades that hit TP/SL or exceeded MAX_TRADE_DURATION_MINUTES.
    Also closes any positions that Alpaca closed via bracket orders.
    """
    open_db_trades = db.get_open_trades()
    if not open_db_trades:
        return

    alpaca_positions = {p["symbol"]: p for p in alpaca.get_positions()}
    now = datetime.now(timezone.utc)

    for trade in open_db_trades:
        symbol = trade["symbol"]
        alpaca_sym = symbol.replace("/", "")

        # Force-close if trade exceeded max duration
        opened_at = trade.get("opened_at")
        if opened_at:
            try:
                opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                age_min = int((now - opened_dt).total_seconds() // 60)
                if (now - opened_dt) > _MAX_AGE:
                    print(f"[ABOT] TIMEOUT {symbol} open {age_min}min — force closing")
                    alpaca.close_position(symbol)
                    price = alpaca.get_latest_price(symbol)
                    if price:
                        db.close_trade(trade["id"], price)
                        pnl_pct = (price - trade["entry_price"]) / trade["entry_price"] * 100
                        outcome = "WIN" if price > trade["entry_price"] else "LOSS"
                        print(f"[ABOT] TIMEOUT {outcome} {symbol} | {pnl_pct:+.2f}%")
                        _log_learning(symbol, trade, price, pnl_pct)
                    continue
            except Exception as e:
                db.log_error("check_open.timeout", str(e))

        # Check if Alpaca closed the position (TP/SL hit)
        if alpaca_sym not in alpaca_positions and symbol not in alpaca_positions:
            price = alpaca.get_latest_price(symbol)
            if price:
                db.close_trade(trade["id"], price)
                entry = trade["entry_price"]
                pnl_pct = (price - entry) / entry * 100
                outcome = "WIN" if price > entry else "LOSS"
                print(f"[ABOT] {outcome} {symbol} | entry=${entry:.4f} exit=${price:.4f} | {pnl_pct:+.2f}%")
                _log_learning(symbol, trade, price, pnl_pct)


def _log_learning(symbol, trade, exit_price, pnl_pct):
    """Log learning insight after a trade closes and adjust threshold in brain log."""
    closed_trades = db.get_closed_trades_for_symbol(symbol, limit=20)
    if not closed_trades:
        return

    wins = sum(1 for t in closed_trades if t.get("pnl", 0) and t["pnl"] > 0)
    total = len(closed_trades)
    win_rate = wins / total if total else 0
    new_threshold = db.get_adaptive_threshold(symbol, DEFAULT_CONFIDENCE_THRESHOLD)

    outcome = "WIN" if pnl_pct > 0 else "LOSS"
    detail = (f"win_rate={win_rate:.1%} over last {total} trades | "
              f"pnl={pnl_pct:+.2f}% | adaptive_threshold={new_threshold:.2f}")
    db.log_learning_event(symbol, outcome, detail)
    print(f"[LEARN] {symbol}: {detail}")


def run_learn():
    print("[ABOT] Running learning cycle...")
    all_trades = db.get_all_trades(limit=100)
    result = learn_from_trades(all_trades)
    if result:
        print(f"[ABOT] Brain updated: {result['summary'][:80]}...")
    else:
        print("[ABOT] Not enough trade data to learn yet")
