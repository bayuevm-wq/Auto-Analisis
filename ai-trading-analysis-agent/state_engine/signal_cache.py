import json
import os
import time

CACHE_FILE = os.path.join(os.path.dirname(__file__), "signal_cache.json")

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def update_signal_timestamp(pair: str, timeframe: str, action: str):
    cache = load_cache()
    key = f"{pair}_{timeframe}_{action}"
    cache[key] = time.time()
    save_cache(cache)
    
def get_last_signal_timestamp(pair: str, timeframe: str, action: str) -> float:
    cache = load_cache()
    key = f"{pair}_{timeframe}_{action}"
    return cache.get(key, 0.0)
