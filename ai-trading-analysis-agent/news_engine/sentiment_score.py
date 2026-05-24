import logging
from typing import Dict, Any

from news_engine.news_fetcher import fetch_crypto_news
from news_engine.sentiment_analyzer import analyze_sentiments

logger = logging.getLogger("news_engine.pipeline")

# A simple cache so we don't bombard the News API if we scan the same pair multiple times quickly
_news_sentiment_cache = {}
import time

def get_asset_sentiment(pair: str) -> Dict[str, Any]:
    """
    Provides sentiment context for a specific pair.
    Output: { 'score': float (-1.0 to 1.0), 'status': str (Bullish/Bearish/Neutral) }
    """
    # Clean pair name (e.g. "BINANCE:BTCUSDT" -> "BTC")
    base_asset = pair.split(":")[1] if ":" in pair else pair
    base_asset = base_asset.replace("USDT", "").replace("/", "").strip()
    
    # Check Cache (valid for 15 minutes)
    now = time.time()
    if base_asset in _news_sentiment_cache:
        cached_data, timestamp = _news_sentiment_cache[base_asset]
        if now - timestamp < (15 * 60):
            return cached_data
            
    # Fetch and Analyze
    headlines = fetch_crypto_news(base_asset, max_results=5)
    
    if not headlines:
        result = {"score": 0.0, "status": "Neutral (No News)"}
        _news_sentiment_cache[base_asset] = (result, now)
        return result
        
    avg_compound = analyze_sentiments(headlines)
    
    if avg_compound >= 0.15:
        status = "Bullish"
    elif avg_compound <= -0.15:
        status = "Bearish"
    else:
        status = "Neutral"
        
    result = {"score": avg_compound, "status": status}
    _news_sentiment_cache[base_asset] = (result, now)
    
    return result
