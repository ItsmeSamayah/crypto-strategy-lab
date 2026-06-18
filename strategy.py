"""
Consensus Engine Strategy Module.
Includes: Market Regime Filter (ADX), ATR Volatility Filter, Cooldown Logic,
           Multi-Timeframe Confirmation.
"""
from config import ADX_TREND_THRESHOLD, MIN_ATR_RATIO, COOLDOWN_CANDLES
from indicators import calculate_indicators


def get_market_regime(df, adx_threshold=20):
    """
    Returns (regime, adx_val, atr_val, volatility_state).
    regime:           TRENDING | SIDEWAYS
    volatility_state: HIGH VOLATILITY | NORMAL | LOW VOLATILITY
    """
    if 'ADX_14' not in df.columns or 'ATR_14' not in df.columns:
        return "UNKNOWN", 0.0, 0.0, "UNKNOWN"

    adx_val = float(df.iloc[-1].get('ADX_14', 0.0))
    atr_val = float(df.iloc[-1].get('ATR_14', 0.0))
    price   = float(df.iloc[-1]['close'])
    ratio   = atr_val / price if price > 0 else 0.0

    regime = "TRENDING" if adx_val >= adx_threshold else "SIDEWAYS"

    if ratio < MIN_ATR_RATIO:
        vol_state = "LOW VOLATILITY"
    elif ratio > 0.02:  # ATR > 2% of price
        vol_state = "HIGH VOLATILITY"
    else:
        vol_state = "NORMAL"

    return regime, round(adx_val, 2), round(atr_val, 2), vol_state



def is_volatility_ok(df):
    """Returns True when ATR/Price ratio is above the minimum threshold."""
    if 'ATR_14' not in df.columns:
        return True, 0.0
    current = df.iloc[-1]
    atr   = float(current.get('ATR_14', 0.0))
    price = float(current['close'])
    ratio = atr / price if price > 0 else 0.0
    return ratio >= MIN_ATR_RATIO, round(atr, 2)


def get_trend_direction(df):
    """
    Quick trend check using EMA 20 vs EMA 50.
    Returns: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    if 'EMA_20' not in df.columns or 'EMA_50' not in df.columns:
        return "NEUTRAL"
    ema20 = float(df.iloc[-1].get('EMA_20', 0))
    ema50 = float(df.iloc[-1].get('EMA_50', 0))
    if ema20 > ema50:
        return "BULLISH"
    elif ema20 < ema50:
        return "BEARISH"
    return "NEUTRAL"


def evaluate_multi_timeframe(mtf_data: dict[str, 'pd.DataFrame']):
    """
    Evaluate trend direction across multiple timeframes.
    Returns: dict { '5m': 'BULLISH', '15m': 'BEARISH', '1h': 'BULLISH', ... }
    """
    trends = {}
    for tf, df in mtf_data.items():
        if df is not None and not df.empty and len(df) >= 50:
            df = calculate_indicators(df)
            trends[tf] = get_trend_direction(df)
        else:
            trends[tf] = "NEUTRAL"
    return trends


def check_mtf_confirmation(consensus: str, mtf_trends: dict) -> tuple[bool, str]:
    """
    Multi-Timeframe Confirmation:
      BUY  allowed only when 5m=BUY/BULLISH, 15m=BULLISH, 1h=BULLISH
      SELL allowed only when 5m=SELL/BEARISH, 15m=BEARISH, 1h=BEARISH
    Returns (confirmed: bool, reason: str)
    """
    if consensus == "HOLD":
        return True, ""

    trend_15m = mtf_trends.get('15m', 'NEUTRAL')
    trend_1h  = mtf_trends.get('1h', 'NEUTRAL')

    if consensus == "BUY":
        if trend_15m != "BULLISH":
            return False, f"MTF blocked — 15m trend is {trend_15m}, not BULLISH"
        if trend_1h != "BULLISH":
            return False, f"MTF blocked — 1h trend is {trend_1h}, not BULLISH"
        return True, ""

    if consensus == "SELL":
        if trend_15m != "BEARISH":
            return False, f"MTF blocked — 15m trend is {trend_15m}, not BEARISH"
        if trend_1h != "BEARISH":
            return False, f"MTF blocked — 1h trend is {trend_1h}, not BEARISH"
        return True, ""

    return True, ""


def evaluate_consensus(df, threshold=3, adx_threshold=20, cooldown_candles_left=0):
    """
    Evaluates the last candle and returns:
      votes, consensus, regime, adx_val, atr_val, vol_state, block_msg
    """
    hold_result = (
        {"RSI": "HOLD", "MACD": "HOLD", "EMA": "HOLD", "Momentum": "HOLD", "Volume": "HOLD"},
        "HOLD", "UNKNOWN", 0.0, 0.0, "UNKNOWN", ""
    )

    if len(df) < 50:
        return hold_result

    regime, adx_val, atr_val, vol_state = get_market_regime(df, adx_threshold=adx_threshold)
    vol_ok, _ = is_volatility_ok(df)

    current  = df.iloc[-1]
    previous = df.iloc[-2]

    votes = {
        "RSI":      "HOLD",
        "MACD":     "HOLD",
        "EMA":      "HOLD",
        "Momentum": "HOLD",
        "Volume":   "HOLD",
    }

    # A. RSI (14)
    rsi_val = current.get('RSI_14', 50)
    if rsi_val < 30:
        votes["RSI"] = "BUY"
    elif rsi_val > 70:
        votes["RSI"] = "SELL"

    # B. MACD
    macd_curr   = current.get('MACD_12_26_9', 0)
    signal_curr = current.get('MACDs_12_26_9', 0)
    macd_prev   = previous.get('MACD_12_26_9', 0)
    signal_prev = previous.get('MACDs_12_26_9', 0)
    if macd_curr > signal_curr and macd_prev <= signal_prev:
        votes["MACD"] = "BUY"
    elif macd_curr < signal_curr and macd_prev >= signal_prev:
        votes["MACD"] = "SELL"

    # C. EMA Trend
    ema20 = current.get('EMA_20', 0)
    ema50 = current.get('EMA_50', 0)
    if ema20 > ema50:
        votes["EMA"] = "BUY"
    elif ema20 < ema50:
        votes["EMA"] = "SELL"

    # D. Momentum
    if current['close'] > previous['close']:
        votes["Momentum"] = "BUY"
    elif current['close'] < previous['close']:
        votes["Momentum"] = "SELL"

    # E. Volume Trend
    vol_curr  = current['volume']
    vol_sma20 = current.get('SMA_Volume_20', vol_curr)
    if vol_curr > vol_sma20:
        votes["Volume"] = "BUY"
    elif vol_curr < vol_sma20:
        votes["Volume"] = "SELL"

    # Count raw votes
    buy_votes  = list(votes.values()).count("BUY")
    sell_votes = list(votes.values()).count("SELL")

    if buy_votes >= threshold:
        raw_consensus = "BUY"
    elif sell_votes >= threshold:
        raw_consensus = "SELL"
    else:
        raw_consensus = "HOLD"

    # Apply filters
    block_msg = ""

    if regime == "SIDEWAYS" and raw_consensus != "HOLD":
        block_msg = f"Blocked – Sideways market (ADX {adx_val:.1f} < {adx_threshold})"
        return votes, "HOLD", regime, adx_val, atr_val, vol_state, block_msg

    if not vol_ok and raw_consensus != "HOLD":
        block_msg = f"Blocked – Volatility too low (ATR {atr_val:.2f})"
        return votes, "HOLD", regime, adx_val, atr_val, vol_state, block_msg

    if cooldown_candles_left > 0 and raw_consensus != "HOLD":
        block_msg = f"Blocked – Cooldown ({cooldown_candles_left} candle(s) remaining)"
        return votes, "HOLD", regime, adx_val, atr_val, vol_state, block_msg

    return votes, raw_consensus, regime, adx_val, atr_val, vol_state, block_msg
