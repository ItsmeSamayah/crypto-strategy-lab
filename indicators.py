"""
Technical Indicators Module using pure pandas (no pandas_ta required).
Includes: RSI, MACD, EMA, Volume, ADX, ATR
"""
import pandas as pd
import numpy as np


def calculate_indicators(df):
    """
    Calculates all required indicators using pure pandas and adds them to the dataframe.
    """
    if len(df) < 50:
        return df

    # ── A. RSI (14) ── Wilder's Smoothing
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # ── B. MACD (12, 26, 9) ──
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema_12 - ema_26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()

    # ── C. EMA Trend ──
    df['EMA_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()

    # ── D. Volume Trend (20-period average volume) ──
    df['SMA_Volume_20'] = df['volume'].rolling(window=20).mean()

    # ── E. ATR (14) ── Average True Range for volatility measurement
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift(1)).abs()
    low_cp  = (df['low']  - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    df['ATR_14'] = tr.ewm(alpha=1/14, adjust=False).mean()

    # ── F. ADX (14) ── Average Directional Index for trend strength
    plus_dm  = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm  = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr14   = df['ATR_14']
    plus_di  = 100 * (plus_dm.ewm(alpha=1/14, adjust=False).mean()  / atr14)
    minus_di = 100 * (minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14)
    dx = (((plus_di - minus_di).abs()) / ((plus_di + minus_di).abs())) * 100
    df['ADX_14']      = dx.ewm(alpha=1/14, adjust=False).mean()
    df['DI_plus_14']  = plus_di
    df['DI_minus_14'] = minus_di

    # ── G. Bollinger Bands (20, 2.0) ──
    df['BB_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['BB_upper'] = df['BB_middle'] + 2.0 * bb_std
    df['BB_lower'] = df['BB_middle'] - 2.0 * bb_std

    return df
