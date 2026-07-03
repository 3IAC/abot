import json
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
    signal = analyze_signal(symbol, indicators, symbol_trades)  # brain already logs signal
    threshold = db.get_adaptive_threshold(symbol, default=DEFAULT_CONFIDENCE_THRESHOLD)

    action = signal["action"]
    conf = signal["confidence"]
    print(f"[ABOT] {symbol}: {action.upper()} ({conf:.0%}) "
          f"threshold={threshold:.0%} — {signal['key_signal']}")

    if action not in ("buy", "sell") or conf < threshold or symbol in open_symbols:
        return False

    price = indicators["price"]
    max_dollars = portfolio_value * MAX_POSITION_PCT
    qty = round(max_dollars / price, 6) if is_crypto_symbol else max(1, int(max_dollars / price))

    if action == "buy":
        stop_loss   = round(price * (1 - STOP_LOSS_PCT), 4)
        take_profit = round(price * (1 + TAKE_PROFIT_PCT), 4)
    else:  # sell / short
        stop_loss   = round(price * (1 + STOP_LOSS_PCT), 4)   # above entry for short
        take_profit = round(price * (1 - TAKE_PROFIT_PCT), 4) # below entry for short
        if is_crypto_symbol:
            # Alpaca paper does not support crypto short selling
            print(f"[ABOT] {symbol}: SELL signal {conf:.0%} — skipping (no crypto shorts on paper)")
            return False

    label = "BUY" if action == "buy" else "SHORT"
    print(f"[ABOT] Placing {label} {qty} {symbol} @ ${price} SL=${stop_loss} TP=${take_profit}")
    order = alpaca.place_order(symbol, qty, action, stop_loss=stop_loss, take_profit=take_profit)
    print(f"[ABOT] ORDER RESPONSE: {json.dumps(order)[:400] if order else 'None/Error'}")

    if order:
        db.log_trade(symbol, action, qty, price, "ai_signal",
                     indicators, signal["reasoning"], stop_loss, take_profit)
        print(f"[ABOT] {'CRYPTO' if is_crypto_symbol else 'STOCK'} {label} placed: {qty} {symbol} @ ${price}")
        return True
    else:
        print(f"[ABOT] {symbol}: {label} order FAILED — check errors table")
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

    for symbol in CRYPTO_SYMBOLS:
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            break
        try:
            _scan_symbol(symbol, True, open_symbols, portfolio_value, recent_trades)
        except Exception as e:
            db.log_error(f"trader.crypto.{symbol}", str(e))

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
                    ok = alpaca.close_position(symbol)
                    print(f"[ABOT] close_position({symbol}) = {ok}")
                    price = alpaca.get_latest_price(symbol)
                    if price:
                        db.close_trade(trade["id"], price)
                        entry = trade["entry_price"]
                        side = trade.get("side", "buy")
                        pnl_pct = (price - entry) / entry * 100 * (1 if side == "buy" else -1)
                        outcome = "WIN" if pnl_pct > 0 else "LOSS"
                        print(f"[ABOT] TIMEOUT {outcome} {symbol} | entry={entry:.4f} exit={price:.4f} | {pnl_pct:+.2f}%")
                        _log_learning(symbol, trade, price, pnl_pct)
                    continue
            except Exception as e:
                db.log_error("check_open.timeout", str(e))

        # Check if Alpaca closed the position (TP/SL hit by bracket order)
        if alpaca_sym not in alpaca_positions and symbol not in alpaca_positions:
            price = alpaca.get_latest_price(symbol)
            if price:
                db.close_trade(trade["id"], price)
                entry = trade["entry_price"]
                side = trade.get("side", "buy")
                pnl_pct = (price - entry) / entry * 100 * (1 if side == "buy" else -1)
                outcome = "WIN" if pnl_pct > 0 else "LOSS"
                print(f"[ABOT] {outcome} {symbol} closed by Alpaca | "
                      f"entry=${entry:.4f} exit=${price:.4f} | {pnl_pct:+.2f}%")
                _log_learning(symbol, trade, price, pnl_pct)


def _log_learning(symbol, trade, exit_price, pnl_pct):
    """Update per-symbol learning after a trade closes."""
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
