import os
import json
import requests
from datetime import datetime, timezone
import bot.database as db
from bot.config import ANTHROPIC_API_KEY

def analyze_signal(symbol, indicators, recent_trades):
    if not ANTHROPIC_API_KEY:
        return _rule_based_signal(symbol, indicators)

    trade_summary = ""
    if recent_trades:
        wins = [t for t in recent_trades if t.get("pnl", 0) and t["pnl"] > 0]
        losses = [t for t in recent_trades if t.get("pnl", 0) and t["pnl"] <= 0]
        trade_summary = f"Recent performance: {len(wins)} wins, {len(losses)} losses on {symbol}."

    prompt = f"""You are an expert quantitative trader analyzing {symbol}.

Market data right now:
- Price: ${indicators.get('price', 'N/A')}
- RSI (14): {indicators.get('rsi', 'N/A')} (>70 overbought, <30 oversold)
- MA9: {indicators.get('ma9', 'N/A')}
- MA20: {indicators.get('ma20', 'N/A')}
- MA50: {indicators.get('ma50', 'N/A')}
- MACD: {indicators.get('macd', 'N/A')}
- Bollinger Upper: {indicators.get('bb_upper', 'N/A')}
- Bollinger Lower: {indicators.get('bb_lower', 'N/A')}
- Price above MA20: {indicators.get('above_ma20', 'N/A')}
- Price above MA50: {indicators.get('above_ma50', 'N/A')}
- 1-day change: {indicators.get('price_change_1d', 'N/A')}%
- 5-day change: {indicators.get('price_change_5d', 'N/A')}%
- Volume surge: {indicators.get('volume_surge', False)}
{trade_summary}

Respond ONLY with valid JSON, no markdown:
{{
  "action": "buy" | "sell" | "hold",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentence explanation",
  "key_signal": "the single most important indicator driving this decision"
}}"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            db.log_signal(symbol, result["action"], result["confidence"],
                         result["reasoning"], indicators)
            return result
    except Exception as e:
        db.log_error("brain.analyze_signal", str(e))

    return _rule_based_signal(symbol, indicators)

def _rule_based_signal(symbol, indicators):
    rsi = indicators.get("rsi")
    above_ma20 = indicators.get("above_ma20")
    if rsi and rsi < 35 and above_ma20:
        return {"action": "buy", "confidence": 0.65, "reasoning": "RSI oversold with price above MA20.", "key_signal": "RSI"}
    elif rsi and rsi > 70:
        return {"action": "sell", "confidence": 0.60, "reasoning": "RSI overbought.", "key_signal": "RSI"}
    else:
        return {"action": "hold", "confidence": 0.50, "reasoning": "No clear signal.", "key_signal": "none"}

def learn_from_trades(all_trades):
    if not all_trades or len(all_trades) < 5:
        return None
    if not ANTHROPIC_API_KEY:
        return None

    closed = [t for t in all_trades if t["status"] == "closed" and t.get("pnl") is not None]
    if len(closed) < 3:
        return None

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    win_rate = len(wins) / len(closed) * 100

    trade_data = json.dumps([{
        "symbol": t["symbol"],
        "side": t["side"],
        "pnl": t["pnl"],
        "pnl_pct": t["pnl_pct"],
        "strategy": t["strategy"],
        "conditions": t.get("market_conditions", "{}")
    } for t in closed[-20:]], indent=2)

    prompt = f"""You are analyzing trading bot performance to improve its strategy.

Win rate: {win_rate:.1f}% ({len(wins)} wins, {len(losses)} losses)

Recent closed trades:
{trade_data}

Respond ONLY with valid JSON:
{{
  "summary": "2-3 sentence overall assessment",
  "winning_patterns": "what conditions led to winning trades",
  "losing_patterns": "what conditions led to losing trades",
  "adjustments": "specific strategy adjustments to improve performance"
}}"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            db.log_brain(result["summary"], result["winning_patterns"],
                        result["adjustments"], win_rate)
            return result
    except Exception as e:
        db.log_error("brain.learn", str(e))
    return None
