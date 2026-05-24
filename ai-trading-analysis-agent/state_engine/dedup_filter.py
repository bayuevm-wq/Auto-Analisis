import time
from typing import Dict, Any

from state_engine.signal_cache import get_last_signal_timestamp, update_signal_timestamp

def is_duplicate_signal(pair: str, timeframe: str, action: str, cooldown_minutes: int = 120) -> bool:
    """
    Check if we already pushed this exact LONG/SHORT to the user recently.
    Default cooldown is 2 hours (120 minutes) for identical actions on identical timeframes.
    If action is "ENTER", we use that.
    """
    # Skip tracking for neutral/risk off outputs
    if action in ["NO TRADE", "RISK OFF", "RECALIBRATING"]:
        return True # Always filter out junk from notifications
        
    last_pushed = get_last_signal_timestamp(pair, timeframe, action)
    now = time.time()
    minutes_elapsed = (now - last_pushed) / 60.0
    
    if minutes_elapsed < cooldown_minutes:
        return True # Is duplicate (recently pushed)
        
    return False

def register_signal_sent(pair: str, timeframe: str, action: str):
    """
    Called only AFTER successfully sending a notification to prevent loops.
    """
    update_signal_timestamp(pair, timeframe, action)
