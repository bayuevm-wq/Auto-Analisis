from typing import Dict, Any

def format_signal_message(data: Dict[str, Any]) -> str:
    """
    Takes the structured dict dictionary passed from the scanner and formats it.
    """
    pair = data.get("pair", "UNKNOWN")
    action = data.get("action", "")
    score = data.get("score", 0.0)
    setup = data.get("setup", {})
    
    preferred = setup.get("preferred", "neutral").upper()
    
    if action == "ENTER":
        icon = "🟢"
    elif action == "REDUCE SIZE":
        icon = "🟠"
    else:
        icon = "⚪"
        
    p = setup.get("long", {}) if preferred == "LONG" else setup.get("short", {})
    entry = p.get("entry", 0)
    sl = p.get("stop_loss", 0)
    tp1 = p.get("tp1", 0)
    tp2 = p.get("take_profit", 0)
    
    msg = f"{icon} **AI Trading Alert: {pair}**\n"
    msg += f"**Direction:** {preferred}\n"
    msg += f"**Conviction Score:** {score:.1f}%\n"
    msg += f"**Action Level:** {action}\n\n"
    
    msg += f"🎯 **Trade Setup**\n"
    msg += f"• **Entry:** ${entry:.6f}\n"
    msg += f"• **Stop Loss:** ${sl:.6f}\n"
    msg += f"• **Take Profit 1:** ${tp1:.6f}\n"
    msg += f"• **Take Profit 2:** ${tp2:.6f}\n\n"
    
    msg += f"_{setup.get('conviction', '')}_\n"
    
    return msg
