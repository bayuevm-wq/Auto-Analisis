from __future__ import annotations

import logging
import random
import time
import threading
from typing import Optional

try:
    from tvDatafeed import TvDatafeed
except Exception as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "tvDatafeed is required. Install with: pip install tvdatafeed"
    ) from exc

logger = logging.getLogger(__name__)

# ── Singleton instance ──────────────────────────────────────────────
_tv_instance: Optional[TvDatafeed] = None
_tv_credentials: tuple = (None, None)
_tv_lock = threading.Lock()

# ── Simple TTL cache for OHLCV data ────────────────────────────────
_data_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 300  # 5 minutes

# ── Rate limiter: thread-safe request throttle ─────────────────────
_request_lock = threading.Lock()
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # 1s between TradingView API calls (safe for bulk)
_consecutive_429_count = 0
_429_cooldown_until = 0.0


def _throttle():
    """Enforce minimum interval between TradingView requests to avoid rate-limits."""
    global _last_request_time, _429_cooldown_until
    with _request_lock:
        now = time.time()
        # If we're in a 429 cooldown period, wait it out
        if now < _429_cooldown_until:
            sleep_time = _429_cooldown_until - now
            logger.debug(f"429 cooldown active, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        elapsed = time.time() - _last_request_time
        # Add jitter to avoid thundering herd when multiple threads resume
        jitter = random.uniform(0, 0.3)
        interval = _MIN_REQUEST_INTERVAL + jitter
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_request_time = time.time()


def get_tradingview(username: Optional[str] = None, password: Optional[str] = None) -> TvDatafeed:
    """
    Get or create a singleton TradingView client.
    Re-creates the instance only if credentials change.
    Thread-safe.
    """
    global _tv_instance, _tv_credentials
    new_creds = (username, password)

    with _tv_lock:
        if _tv_instance is not None and _tv_credentials == new_creds:
            return _tv_instance

        if username and password:
            _tv_instance = TvDatafeed(username=username, password=password)
            logger.info("Initialized TradingView client with credentials")
        else:
            _tv_instance = TvDatafeed()
            logger.info("Initialized TradingView client (anonymous)")

        _tv_credentials = new_creds
        return _tv_instance


def throttled_get_hist(tv: TvDatafeed, symbol: str, exchange: str, interval, n_bars: int):
    """Throttled wrapper around tv.get_hist to prevent rate-limit bans.
    Includes 429-specific exponential backoff with progressive cooldown."""
    global _consecutive_429_count, _429_cooldown_until
    _throttle()
    try:
        result = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars)
        # Successful request — reset 429 counter
        with _request_lock:
            _consecutive_429_count = 0
        return result
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str:
            with _request_lock:
                _consecutive_429_count += 1
                # Exponential backoff: 5s, 10s, 20s, 40s, capped at 60s
                backoff = min(60, 5 * (2 ** (_consecutive_429_count - 1)))
                _429_cooldown_until = time.time() + backoff
            logger.warning(f"429 rate-limited on {exchange}:{symbol}, backing off {backoff}s (count={_consecutive_429_count})")
            time.sleep(backoff)
            # Retry once after backoff
            _throttle()
            return tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars)
        raise


def get_cached_data(cache_key: str):
    """Return cached data if still valid (within TTL), else None."""
    with _cache_lock:
        entry = _data_cache.get(cache_key)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > _CACHE_TTL_SECONDS:
            del _data_cache[cache_key]
            return None
        return data


def set_cached_data(cache_key: str, data) -> None:
    """Store data in cache with current timestamp."""
    with _cache_lock:
        _data_cache[cache_key] = (time.time(), data)
        # Evict oldest entries if cache grows too large
        if len(_data_cache) > 500:
            oldest_key = min(_data_cache, key=lambda k: _data_cache[k][0])
            del _data_cache[oldest_key]
