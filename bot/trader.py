import bot.database as db
import bot.alpaca_client as alpaca
from bot.brain import analyze_signal, learn_from_trades
from bot.indicators import get_all_indicators
from bot.config import SYMBOLS, MAX_POSITION_PCT, MAX_OPEN_POSITIONS, STOP_LOSS_PCT, TAKE_PROFIT_PCT

def run_scan():
    print("[ABOT] Starting market scan...")
    clock = alpaca.get_clock()
    if clock and not clock.get("is_open"):
        print("[ABOT] Market closed — skipping scan")
        return

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

    recent_trades = db.get_all_trades(limit=50)

    for symbol in SYMBOLS:
        try:
            bars = alpaca.get_bars(symbol, timeframe="1Day", limit=60)
            if not bars or len(bars) < 20:
                print(f"[ABOT] {symbol}: insufficient data")
                continue

            indicators = get_all_indicators(bars)
            db.save_snapshot(symbol, indicators.get("price"), indicators.get("rsi"),
                           indicators.get("ma20"), indicators.get("ma50"), indicators.get("volume"))

            symbol_trades = [t for t in recent_trades if t["symbol"] == symbol]
            signal = analyze_signal(symbol, indicators, symbol_trades)

            print(f"[ABOT] {symbol}: {signal['action'].upper()} ({signal['confidence']:.0%}) — {signal['key_signal']}")

            if signal["action"] == "buy" and symbol not in open_symbols and signal["confidence"] >= 0.35:
                price = indicators["price"]
                max_dollars = portfolio_value * MAX_POSITION_PCT
                qty = max(1, int(max_dollars / price))
                stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
                take_profit = round(price * (1 + TAKE_PROFIT_PCT), 2)

                order = alpaca.place_order(symbol, qty, "buy", stop_loss=stop_loss, take_profit=take_profit)
                if order:
                    db.log_trade(symbol, "buy", qty, price, "ai_signal",
                                indicators, signal["reasoning"], stop_loss, take_profit)
                    print(f"[ABOT] BOUGHT {qty} {symbol} @ ${price} | SL: ${stop_loss} | TP: ${take_profit}")

        except Exception as e:
            db.log_error(f"trader.{symbol}", str(e))

def run_learn():
    print("[ABOT] Running learning cycle...")
    all_trades = db.get_all_trades(limit=100)
    result = learn_from_trades(all_trades)
    if result:
        print(f"[ABOT] Brain updated: {result['summary'][:80]}...")
    else:
        print("[ABOT] Not enough trade data to learn yet")
