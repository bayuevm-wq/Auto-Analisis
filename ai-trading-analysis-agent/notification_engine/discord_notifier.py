import os
import requests
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("notification_engine.discord")

def send_discord_message(message: str) -> bool:
    """
    Sends message to Discord Webhook.
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        logger.warning("Discord webhook URL is missing.")
        return False
        
    payload = {
        "content": message
    }
    
    try:
        req = requests.post(webhook_url, json=payload, timeout=10)
        req.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Discord message: {e}")
        return False
