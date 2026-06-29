def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ma(prices, period):
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 4)

def calculate_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return None, None, None
    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for p in data[1:]:
            ema_val = p * k + ema_val * (1 - k)
        return ema_val
    fast_ema = ema(prices[-fast:], fast)
    slow_ema = ema(prices[-slow:], slow)
    macd_line = fast_ema - slow_ema
    return round(macd_line, 4), None, None

def calculate_bollinger(prices, period=20, std_dev=2):
    if len(prices) < period:
        return None, None, None
    recent = prices[-period:]
    ma = sum(recent) / period
    variance = sum((p - ma) ** 2 for p in recent) / period
    std = variance ** 0.5
    upper = round(ma + std_dev * std, 4)
    lower = round(ma - std_dev * std, 4)
    return round(ma, 4), upper, lower

def get_all_indicators(bars):
    if not bars or len(bars) < 20:
        return {}
    closes = [float(b["c"]) for b in bars]
    volumes = [float(b["v"]) for b in bars]
    rsi = calculate_rsi(closes)
    ma20 = calculate_ma(closes, 20)
    ma50 = calculate_ma(closes, 50) if len(closes) >= 50 else None
    ma9 = calculate_ma(closes, 9)
    macd, _, _ = calculate_macd(closes)
    bb_mid, bb_upper, bb_lower = calculate_bollinger(closes)
    avg_volume = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else None
    current_volume = volumes[-1] if volumes else None
    price = closes[-1]
    price_change_1d = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else None
    price_change_5d = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else None
    return {
        "price": price,
        "rsi": rsi,
        "ma9": ma9,
        "ma20": ma20,
        "ma50": ma50,
        "macd": macd,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "volume": current_volume,
        "avg_volume": avg_volume,
        "price_change_1d": price_change_1d,
        "price_change_5d": price_change_5d,
        "above_ma20": price > ma20 if ma20 else None,
        "above_ma50": price > ma50 if ma50 else None,
        "volume_surge": (current_volume / avg_volume > 1.5) if (current_volume and avg_volume) else False
    }
