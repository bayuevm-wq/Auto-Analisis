from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import pandas as pd

from .tradingview_connector import get_tradingview, get_cached_data, set_cached_data, throttled_get_hist

try:
    from tvDatafeed import Interval
except Exception as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "tvDatafeed is required. Install with: pip install tvdatafeed"
    ) from exc

logger = logging.getLogger(__name__)

TIMEFRAME_MAP: Dict[str, str] = {
    "m1": "1m",
    "m3": "3m",
    "m5": "5m",
    "m15": "15m",
    "m30": "30m",
    "h1": "1h",
    "h2": "2h",
    "h3": "3h",
    "h4": "4h",
    "d1": "1d",
    "w1": "1w",
    "mo1": "1mo",
}

INTERVAL_MAP: Dict[str, Interval] = {
    "1m": Interval.in_1_minute,
    "3m": Interval.in_3_minute,
    "5m": Interval.in_5_minute,
    "15m": Interval.in_15_minute,
    "30m": Interval.in_30_minute,
    "1h": Interval.in_1_hour,
    "2h": Interval.in_2_hour,
    "3h": Interval.in_3_hour,
    "4h": Interval.in_4_hour,
    "1d": Interval.in_daily,
    "1w": Interval.in_weekly,
    "1mo": Interval.in_monthly,
}

CRYPTO_QUOTES = ("USDT", "USD", "USDC", "BUSD", "DAI", "BTC", "ETH")

# ── Exchange routing tables ─────────────────────────────────────────
# Coins that are best fetched from BYBIT (Solana memecoins, newer listings)
_BYBIT_COINS = {
    "KAS", "TAO", "ONDO", "HYPE", "AI16Z", "VIRTUAL", "FARTCOIN",
    "POPCAT", "WIF", "BONK", "MEW", "PENGU", "GRASS", "TURBO",
    "NEIRO", "JUP", "RAY", "TNSR", "HNT", "RENDER", "PYTH",
    "W", "IO", "WAL",
}

# Coins that are best fetched from OKX
_OKX_COINS = {"LRC", "LINK", "OKB", "ETHFI", "ZK"}


def normalize_timeframe(timeframe: str) -> str:
    tf = timeframe.strip().lower()
    if tf in TIMEFRAME_MAP:
        return TIMEFRAME_MAP[tf]

    # Accept inputs like H4, D1
    if len(tf) == 2 and tf[0] in {"h", "d", "w", "m"}:
        return TIMEFRAME_MAP.get(tf, tf)

    # Accept inputs like 4H, 1D, 15M
    if tf[0].isdigit() and tf[-1] in {"h", "d", "w", "m"}:
        return tf

    raise ValueError(f"Unsupported timeframe: {timeframe}")


def timeframe_to_interval(timeframe: str) -> Interval:
    tf = normalize_timeframe(timeframe)
    if tf not in INTERVAL_MAP:
        raise ValueError(f"Timeframe not supported by TradingView: {timeframe}")
    return INTERVAL_MAP[tf]


def resolve_symbol(pair: str) -> Tuple[str, str]:
    """
    Resolve a TradingView symbol and exchange from a user pair string.

    Accepted:
    - Crypto: "BTC/USDT" -> ("BTCUSDT", "BINANCE")
    - Forex: "EUR/USD" -> ("EURUSD", "OANDA")
    - Stock: "AAPL" -> ("AAPL", "NASDAQ")
    - Index: "SPX500" -> ("SPX500USD", "OANDA")
    - Explicit: "BINANCE:BTCUSDT" -> ("BTCUSDT", "BINANCE")
    """
    raw = pair.strip().upper()
    if ":" in raw:
        exchange, symbol = raw.split(":", 1)
        return symbol, exchange

    index_map = {
        "SPX500": ("SPX500USD", "OANDA"),
        "NAS100": ("NAS100USD", "OANDA"),
        "DJI30": ("US30USD", "OANDA"),
        "DAX40": ("DE30EUR", "OANDA"),
        "FTSE100": ("UK100GBP", "OANDA"),
        "JP225": ("JP225USD", "OANDA"),
        "EU50": ("EU50EUR", "OANDA"),
        "FR40": ("FR40EUR", "OANDA"),
        "AU200": ("AU200AUD", "OANDA"),
        "US2000": ("US2000USD", "OANDA"),
        "HK33": ("HK33HKD", "OANDA"),
        "IN50": ("IN50USD", "OANDA"),
        "SG30": ("SG30SGD", "OANDA"),
        "TWIX": ("TWIXUSD", "OANDA"),
        "CN50": ("CN50USD", "OANDA"),
        "CH20": ("CH20CHF", "OANDA"),
        "NL25": ("NL25EUR", "OANDA"),
        "ES35": ("ES35EUR", "OANDA"),
        "VIX": ("VIX", "CBOE"),
        "DXY": ("DXY", "INDEX"),
    }
    
    if raw in index_map:
        return index_map[raw]

    if "/" in raw:
        base, quote = raw.split("/", 1)
        symbol = f"{base}{quote}"
        
        # Check standard Forex fiat quotes & bases
        fiat_quotes = {"USD", "JPY", "EUR", "GBP", "CHF", "AUD", "CAD", "NZD"}
        fiat_bases = {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY"}
        if quote in fiat_quotes and base in fiat_bases:
            return symbol, "FX_IDC"  # FX_IDC provides composite free forex feeds

        if base in _BYBIT_COINS:
            return symbol, "BYBIT"

        if base in _OKX_COINS:
            return symbol, "OKX"

        if base == "BGB":
            return symbol, "BITGET"

        # FTM migrated to Sonic (S) token on most exchanges
        if base == "FTM":
            return "SUSDT", "BINANCE"

        # Otherwise assume Crypto
        return symbol, "BINANCE"

    # No slash found
    for qc in CRYPTO_QUOTES:
        if raw.endswith(qc) and len(raw) > len(qc):
            base = raw[:-len(qc)]
            fiat_bases = {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY"}
            if base in fiat_bases and qc in {"USD", "EUR", "GBP", "JPY"}:
                return raw, "FX_IDC"
            if base in _BYBIT_COINS:
                return raw, "BYBIT"
            if base in _OKX_COINS:
                return raw, "OKX"
            if base == "BGB":
                return raw, "BITGET"
            if base == "FTM":
                return "SUSDT", "BINANCE"
            return raw, "BINANCE"

    # Default to NASDAQ for stocks (AAPL, MSFT, etc)
    return raw, "NASDAQ"


def fetch_ohlcv(
    pair: str,
    timeframe: str,
    limit: int = 500,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV data from TradingView via tvDatafeed.
    Uses a time-based TTL cache to prevent rate-limit bans on repeated calls.
    Includes retry logic with exponential backoff for resilience.
    """
    symbol, exchange = resolve_symbol(pair)
    interval = timeframe_to_interval(timeframe)
    cache_key = f"{exchange}:{symbol}:{timeframe}:{limit}"
    
    cached = get_cached_data(cache_key)
    if cached is not None:
        logger.debug("Using cached data for %s", cache_key)
        return cached

    tv = get_tradingview(username=username, password=password)

    requested_exchange = exchange
    exchanges_to_try = [exchange]
    if exchange == "BINANCE":
        exchanges_to_try.extend(["OKX", "BYBIT"])
    elif exchange == "BYBIT":
        exchanges_to_try.extend(["OKX", "BINANCE"])
    elif exchange == "OKX":
        exchanges_to_try.extend(["BINANCE", "BYBIT"])
    elif exchange == "BITGET":
        exchanges_to_try.extend(["BINANCE", "BYBIT"])
    elif exchange == "FX_IDC":
        exchanges_to_try.extend(["OANDA", "FOREXCOM"])

    MAX_RETRIES = 2
    df = None
    last_error = None
    
    for ex in exchanges_to_try:
        for attempt in range(MAX_RETRIES):
            try:
                df = throttled_get_hist(tv, symbol=symbol, exchange=ex, interval=interval, n_bars=limit)
                if df is not None and not df.empty:
                    exchange = ex  # Update successful exchange
                    break
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    backoff = 0.5 * (attempt + 1)
                    time.sleep(backoff)
                continue
        if df is not None and not df.empty:
            break

    if df is None or df.empty:
        error_detail = f" Last error: {last_error}" if last_error else ""
        raise ValueError(f"No OHLCV data returned from TradingView for {symbol}. Tried: {', '.join(exchanges_to_try)}.{error_detail}")

    df = df.reset_index()
    df.rename(columns={"datetime": "timestamp"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns from TradingView: {missing}")

    result = df[["timestamp", "open", "high", "low", "close", "volume"]]
    result.attrs["exchange_requested"] = requested_exchange  # The originally requested exchange
    result.attrs["exchange_used"] = exchange          # The exchange actually used (fallback)
    
    logger.info("Fetched %d candles for %s (%s) %s from TradingView", len(result), symbol, exchange, timeframe)
    
    set_cached_data(cache_key, result.copy())
    return result
