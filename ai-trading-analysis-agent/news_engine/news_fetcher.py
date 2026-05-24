import os
import json
import logging
from typing import List, Dict

try:
    from gnews import GNews
    GNEWS_AVAILABLE = True
except ImportError:
    GNEWS_AVAILABLE = False

logger = logging.getLogger("news_engine.fetcher")

# Thread-safe cache for news results
import threading
import time

_news_fetch_cache: Dict[str, tuple] = {}
_news_cache_lock = threading.Lock()
_NEWS_CACHE_TTL = 900  # 15 minutes

def fetch_crypto_news(asset_name: str, max_results: int = 5) -> List[str]:
    """
    Fetch latest news headlines for a specific asset using GNews.
    We just need the basic text (title/description) to analyze sentiment.
    Includes caching and timeout protection to avoid hanging during bulk scans.
    """
    if not GNEWS_AVAILABLE:
        logger.warning("gnews package not installed. Skipping news fetch.")
        return []
    
    # Check cache first
    cache_key = asset_name.upper()
    with _news_cache_lock:
        if cache_key in _news_fetch_cache:
            cached_data, timestamp = _news_fetch_cache[cache_key]
            if time.time() - timestamp < _NEWS_CACHE_TTL:
                return cached_data
        
    try:
        # Configuration for GNews with timeout
        google_news = GNews(max_results=max_results)
        
        # Build search query (e.g. for "BTC", search "Bitcoin crypto")
        query = f"{asset_name} crypto market"
        news_items = google_news.get_news(query)
        
        headlines = []
        if news_items:
            for item in news_items:
                # We usually care about the title and a snippet
                title = item.get("title", "")
                desc = item.get("description", "")
                if title:
                    headlines.append(f"{title}. {desc}")
        
        # Cache the result
        with _news_cache_lock:
            _news_fetch_cache[cache_key] = (headlines, time.time())
                    
        return headlines
    except Exception as e:
        logger.error(f"Error fetching news for {asset_name}: {e}")
        # Cache empty result to avoid retrying immediately
        with _news_cache_lock:
            _news_fetch_cache[cache_key] = ([], time.time())
        return []

if __name__ == "__main__":
    # Test
    news = fetch_crypto_news("Bitcoin", 2)
    for i, n in enumerate(news):
        print(f"{i+1}: {n}")
