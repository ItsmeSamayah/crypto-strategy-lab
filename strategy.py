"""
Consensus Engine Strategy Module with Advanced Strategy Upgrade Pack.
Includes: Smart Market Regime Engine, AI Confidence Score Engine, and BTC Correlation Filter.
"""
import importlib.util
from pathlib import Path

# Force load local config.py
config_path = Path(__file__).parent / "config.py"
spec = importlib.util.spec_from_file_location("local_config", config_path)
bot_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_config)

MIN_ATR_RATIO = bot_config.MIN_ATR_RATIO
COOLDOWN_CANDLES = bot_config.COOLDOWN_CANDLES
REGIME_ADX_TRENDING = bot_config.REGIME_ADX_TRENDING
REGIME_ATR_VOLATILITY = bot_config.REGIME_ATR_VOLATILITY
CONFIDENCE_THRESHOLD = bot_config.CONFIDENCE_THRESHOLD
WEIGHTS = bot_config.WEIGHTS

from indicators import calculate_indicators


def get_market_regime(df, adx_threshold=25, volatility_threshold=0.02):
    """
    Returns (regime, adx_val, atr_val, volatility_state).
    regime:           TRENDING | RANGING | HIGH_VOLATILITY
    volatility_state: HIGH VOLATILITY | NORMAL | LOW VOLATILITY
    """
    if 'ADX_14' not in df.columns or 'ATR_14' not in df.columns:
        return "RANGING", 0.0, 0.0, "UNKNOWN"

    current = df.iloc[-1]
    adx_val = float(current.get('ADX_14', 0.0))
    atr_val = float(current.get('ATR_14', 0.0))
    price   = float(current['close'])
    ratio   = atr_val / price if price > 0 else 0.0

    if ratio >= volatility_threshold:
        vol_state = "HIGH VOLATILITY"
        regime = "HIGH_VOLATILITY"
    elif adx_val >= adx_threshold:
        vol_state = "NORMAL"
        regime = "TRENDING"
    else:
        vol_state = "NORMAL"
        regime = "RANGING"

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
    Multi-Timeframe Confirmation check.
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


def evaluate_consensus(df, threshold=3, adx_threshold=25, cooldown_candles_left=0, mtf_trends=None, btc_df=None, asset_name="BTC"):
    """
    Evaluates indicators dynamically based on the current market regime.
    Returns:
      votes, consensus, regime, adx_val, atr_val, vol_state, block_msg, confidence_score, trade_quality
    """
    hold_result = (
        {"RSI": "HOLD", "MACD": "HOLD", "EMA": "HOLD", "Momentum": "HOLD", "Volume": "HOLD"},
        "HOLD", "UNKNOWN", 0.0, 0.0, "UNKNOWN", "", 0, "C Poor (No Trade)"
    )

    if len(df) < 50:
        return hold_result

    # 1. Detect regime
    regime, adx_val, atr_val, vol_state = get_market_regime(df, adx_threshold=adx_threshold)
    vol_ok, _ = is_volatility_ok(df)

    current  = df.iloc[-1]
    previous = df.iloc[-2]

    # Calculate standard votes for Conflict Radar
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

    # 2. Dynamic Regime Core Strategy Selection
    raw_consensus = "HOLD"

    if regime == "TRENDING":
        # Trend Following: EMA & MACD must agree
        if votes["EMA"] == votes["MACD"] and votes["EMA"] != "HOLD":
            raw_consensus = votes["EMA"]
    elif regime == "RANGING":
        # Mean Reversion: RSI or Bollinger Band touch
        upper_bb = current.get('BB_upper', 999999)
        lower_bb = current.get('BB_lower', 0)
        close_price = current['close']
        
        if rsi_val < 35 or close_price <= lower_bb:
            raw_consensus = "BUY"
        elif rsi_val > 65 or close_price >= upper_bb:
            raw_consensus = "SELL"
    elif regime == "HIGH_VOLATILITY":
        # Volatility Breakout: Price breaks Bollinger Bands Upper/Lower
        upper_bb = current.get('BB_upper', 999999)
        lower_bb = current.get('BB_lower', 0)
        close_price = current['close']
        
        if close_price > upper_bb and current['close'] > previous['close']:
            raw_consensus = "BUY"
        elif close_price < lower_bb and current['close'] < previous['close']:
            raw_consensus = "SELL"

    # 3. AI Confidence Score Engine
    confidence_score = 0
    trade_quality = "C Poor (No Trade)"

    if raw_consensus != "HOLD":
        score = 0
        # Check alignment of each indicator with direction
        if votes["RSI"] == raw_consensus: score += WEIGHTS.get("RSI", 15)
        if votes["MACD"] == raw_consensus: score += WEIGHTS.get("MACD", 15)
        if votes["EMA"] == raw_consensus: score += WEIGHTS.get("EMA", 15)
        if votes["Momentum"] == raw_consensus: score += WEIGHTS.get("Momentum", 10)
        if votes["Volume"] == raw_consensus: score += WEIGHTS.get("Volume", 10)

        # ADX alignment based on regime
        if regime == "TRENDING" and adx_val >= 25:
            score += WEIGHTS.get("ADX", 15)
        elif regime == "RANGING" and adx_val < 25:
            score += WEIGHTS.get("ADX", 15)
        else:
            score += WEIGHTS.get("ADX", 15) * 0.5

        # ATR validation
        if vol_ok:
            score += WEIGHTS.get("ATR", 10)

        # MTF trend confirmation
        if mtf_trends:
            aligned_tfs = 0
            expected_trend = "BULLISH" if raw_consensus == "BUY" else "BEARISH"
            if mtf_trends.get('15m') == expected_trend: aligned_tfs += 1
            if mtf_trends.get('1h') == expected_trend: aligned_tfs += 1
            score += WEIGHTS.get("MTF", 10) * (aligned_tfs / 2)

        confidence_score = int(score)

        if confidence_score >= 80:
            trade_quality = "A+ Excellent"
        elif confidence_score >= 70:
            trade_quality = "A Good"
        elif confidence_score >= 60:
            trade_quality = "B Moderate"
        else:
            trade_quality = "C Poor"

    # Apply filters
    block_msg = ""

    # Confidence Threshold Check
    if raw_consensus != "HOLD" and confidence_score < CONFIDENCE_THRESHOLD:
        block_msg = f"Blocked – Low confidence ({confidence_score} < {CONFIDENCE_THRESHOLD})"
        raw_consensus = "HOLD"

    # 4. BTC Correlation Filter (ETH & SOL only)
    if asset_name != "BTC" and btc_df is not None and not btc_df.empty:
        btc_current = btc_df.iloc[-1]
        btc_ema20 = btc_current.get('EMA_20', 0)
        btc_ema50 = btc_current.get('EMA_50', 0)
        btc_adx = btc_current.get('ADX_14', 0)
        
        strong_downtrend = (btc_ema20 < btc_ema50) and (btc_adx > 20)
        strong_uptrend = (btc_ema20 > btc_ema50) and (btc_adx > 20)
        
        if raw_consensus == "BUY" and strong_downtrend:
            block_msg = "Blocked – Strong BTC Downtrend correlation filter"
            raw_consensus = "HOLD"
        elif raw_consensus == "SELL" and strong_uptrend:
            block_msg = "Blocked – Strong BTC Uptrend correlation filter"
            raw_consensus = "HOLD"

    # Volatility Filter (minimum threshold)
    if not vol_ok and raw_consensus != "HOLD":
        block_msg = f"Blocked – Volatility too low (ATR {atr_val:.2f})"
        raw_consensus = "HOLD"

    # Cooldown Check
    if cooldown_candles_left > 0 and raw_consensus != "HOLD":
        block_msg = f"Blocked – Cooldown ({cooldown_candles_left} candle(s) remaining)"
        raw_consensus = "HOLD"

    return votes, raw_consensus, regime, adx_val, atr_val, vol_state, block_msg, confidence_score, trade_quality
