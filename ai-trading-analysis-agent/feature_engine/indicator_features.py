from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's smoothing (EMA with alpha=1/period) to match TradingView."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": histogram})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def price_momentum(series: pd.Series, period: int = 10) -> pd.Series:
    return series.pct_change(periods=period)


def trend_strength(series: pd.Series, period: int = 20) -> pd.Series:
    """
    Trend strength approximation using EMA slope normalized by price.
    """
    ema_series = ema(series, period)
    slope = ema_series.diff()
    return slope / series.replace(0, np.nan)


def volume_spike(volume: pd.Series, period: int = 20, threshold: float = 1.5) -> pd.Series:
    avg = volume.rolling(window=period).mean()
    return (volume / avg) >= threshold


def volume_imbalance(volume: pd.Series, period: int = 20) -> pd.Series:
    avg = volume.rolling(window=period).mean()
    return (volume - avg) / avg.replace(0, np.nan)


def detect_rsi_divergence(df: pd.DataFrame, rsi_series: pd.Series, lookback: int = 14) -> Dict[str, bool]:
    """
    Basic detection of RSI divergence by comparing recent vs previous windows.
    Returns boolean dictionary indicating presence.
    """
    if len(df) < lookback * 2:
        return {"bullish": False, "bearish": False, "bullish_hidden": False, "bearish_hidden": False}

    recent_idx = df.index[-lookback:]
    prev_idx = df.index[-lookback * 2 : -lookback]

    # Bullish divergence: Lower low in price, higher low in RSI
    price_recent_low_idx = df.loc[recent_idx, "low"].idxmin()
    price_prev_low_idx = df.loc[prev_idx, "low"].idxmin()

    price_recent_low = df.loc[price_recent_low_idx, "low"]
    price_prev_low = df.loc[price_prev_low_idx, "low"]
    
    rsi_recent_low = rsi_series.loc[price_recent_low_idx]
    rsi_prev_low = rsi_series.loc[price_prev_low_idx]

    bullish_div = bool(price_recent_low < price_prev_low and rsi_recent_low > rsi_prev_low)

    # Bullish Hidden: Higher low in price, lower low in RSI
    bullish_hidden = bool(price_recent_low > price_prev_low and rsi_recent_low < rsi_prev_low)

    # Bearish divergence: Higher high in price, lower high in RSI
    price_recent_high_idx = df.loc[recent_idx, "high"].idxmax()
    price_prev_high_idx = df.loc[prev_idx, "high"].idxmax()

    price_recent_high = df.loc[price_recent_high_idx, "high"]
    price_prev_high = df.loc[price_prev_high_idx, "high"]

    rsi_recent_high = rsi_series.loc[price_recent_high_idx]
    rsi_prev_high = rsi_series.loc[price_prev_high_idx]

    bearish_div = bool(price_recent_high > price_prev_high and rsi_recent_high < rsi_prev_high)

    # Bearish Hidden: Lower high in price, higher high in RSI
    bearish_hidden = bool(price_recent_high < price_prev_high and rsi_recent_high > rsi_prev_high)

    return {
        "bullish": bullish_div, 
        "bearish": bearish_div,
        "bullish_hidden": bullish_hidden,
        "bearish_hidden": bearish_hidden
    }

def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP with daily session reset so it stays relevant on multi-day data."""
    tmp = df.copy()
    typical_price = (tmp['high'] + tmp['low'] + tmp['close']) / 3
    pv = typical_price * tmp['volume']
    if 'timestamp' in tmp.columns:
        session = tmp['timestamp'].dt.date
        cum_pv = pv.groupby(session).cumsum()
        cum_volume = tmp['volume'].groupby(session).cumsum()
    else:
        cum_pv = pv.cumsum()
        cum_volume = tmp['volume'].cumsum()
    return cum_pv / cum_volume.replace(0, np.nan)

def obv(df: pd.DataFrame) -> pd.DataFrame:
    direction = np.sign(df['close'].diff())
    direction = direction.fillna(0)
    obv_line = (df['volume'] * direction).cumsum()
    obv_ema = obv_line.ewm(span=20, adjust=False).mean()
    return pd.DataFrame({'obv': obv_line, 'obv_ema': obv_ema})

def volume_profile_poc(df: pd.DataFrame, bins: int = 50) -> float:
    """Volume-weighted POC using vectorized np.histogram (O(n) vs old O(n²))."""
    if df.empty or df['volume'].sum() == 0:
        return 0.0
    typical_prices = ((df['high'] + df['low'] + df['close']) / 3).values
    volumes = df['volume'].values
    hist, edges = np.histogram(typical_prices, bins=bins, weights=volumes)
    max_idx = np.argmax(hist)
    return float((edges[max_idx] + edges[max_idx + 1]) / 2)

def bb_width(series: pd.Series, period: int = 20) -> pd.DataFrame:
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (2 * std)
    lower = sma - (2 * std)
    width = (upper - lower) / sma
    
    # User's Z-Score implementation for Squeeze detection
    width_ma = width.rolling(period).mean()
    width_std = width.rolling(period).std()
    zscore = (width - width_ma) / width_std
    
    return pd.DataFrame({'width': width, 'zscore': zscore})

def detect_macd_divergence(df: pd.DataFrame, macd_hist: pd.Series, lookback: int = 14) -> Dict[str, bool]:
    if len(df) < lookback * 2:
        return {"bullish": False, "bearish": False}

    recent_idx = df.index[-lookback:]
    prev_idx = df.index[-lookback * 2 : -lookback]

    # Bullish divergence: Lower low in price, higher low in MACD Hist
    price_recent_low_idx = df.loc[recent_idx, "low"].idxmin()
    price_prev_low_idx = df.loc[prev_idx, "low"].idxmin()

    price_recent_low = df.loc[price_recent_low_idx, "low"]
    price_prev_low = df.loc[price_prev_low_idx, "low"]
    
    macd_recent_low = macd_hist.loc[price_recent_low_idx]
    macd_prev_low = macd_hist.loc[price_prev_low_idx]

    bullish_div = bool(price_recent_low < price_prev_low and macd_recent_low > macd_prev_low)

    # Bearish divergence: Higher high in price, lower high in MACD Hist
    price_recent_high_idx = df.loc[recent_idx, "high"].idxmax()
    price_prev_high_idx = df.loc[prev_idx, "high"].idxmax()

    price_recent_high = df.loc[price_recent_high_idx, "high"]
    price_prev_high = df.loc[price_prev_high_idx, "high"]

    macd_recent_high = macd_hist.loc[price_recent_high_idx]
    macd_prev_high = macd_hist.loc[price_prev_high_idx]

    bearish_div = bool(price_recent_high > price_prev_high and macd_recent_high < macd_prev_high)

    return {"bullish": bullish_div, "bearish": bearish_div}

def roc(series: pd.Series, period: int = 10) -> pd.Series:
    return series.pct_change(periods=period) * 100

