import logging
from typing import Dict, Any

from state_engine.dedup_filter import is_duplicate_signal, register_signal_sent
from notification_engine.message_formatter import format_signal_message
from notification_engine.telegram_notifier import send_telegram_message
from notification_engine.discord_notifier import send_discord_message

logger = logging.getLogger("scheduler_engine.alert")

def process_and_alert(data: Dict[str, Any], timeframe: str, disable_discord: bool = True):
    """
    Evaluates a signal output object. Hand over to Dedup Filter.
    If valid and High Conviction, pushes to Notifier.
    """
    pair = data.get("pair")
    score = data.get("score", 0.0)
    action = data.get("action", "")
    
    # We only care about HIGH CONVICTION alerts when running auto loops
    if score < 70.0 or action not in ["ENTER"]:
        return
        
    # Check deduplication
    if is_duplicate_signal(pair, timeframe, action):
        logger.info(f"Filtered out duplicate signal for {pair} {timeframe}")
        return
        
    # We have a valid new high conviction signal!
    logger.info(f"🚨 TRIGGERING ALERT FOR {pair} - Score: {score}")
    
    msg = format_signal_message(data)
    
    # Send Telegram
    tg_success = send_telegram_message(msg)
    
    # Send Discord
    if not disable_discord:
        dc_success = send_discord_message(msg)
    else:
        dc_success = False
        
    # If any succeeded, register state as sent to prevent spam loops
    if tg_success or dc_success:
        register_signal_sent(pair, timeframe, action)
