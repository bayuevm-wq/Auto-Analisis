import logging
import os
from typing import List

from main import fetch_ohlcv, generate_features, build_report
from scheduler_engine.alert_trigger import process_and_alert

try:
    import yaml
    with open(os.path.join("config", "settings.yaml"), "r") as f:
        config = yaml.safe_load(f)
        ENABLE_DISCORD = config.get("notifications", {}).get("enable_discord", False)
except:
    ENABLE_DISCORD = False

logger = logging.getLogger("scheduler_engine.monitor")

def monitor_pairs(pairs: List[str], timeframe: str, style: str):
    """
    The routine that scans memory pairs and triggers alerts.
    Includes auto-rescan: if structure age is stale (>80% validity),
    automatically re-fetches with extended data and rebuilds report.
    """
    logger.info(f"Starting scheduled run for {len(pairs)} pairs on {timeframe}")
    
    for pair in pairs:
        try:
            df = fetch_ohlcv(pair, timeframe, limit=300)
            if df.empty:
                continue
                
            df, features = generate_features(df)
            report = build_report(pair, timeframe, df, features, style)
            
            # ── Auto-Rescan: archive stale setup and re-scan fresh ──
            needs_rescan = report.trade_setup.get("needs_rescan", False)
            if needs_rescan:
                logger.info(f"⏳ {pair}: Setup stale (>80% validity). Auto-rescanning with fresh data...")
                # Re-fetch with larger limit to capture newer structure
                df = fetch_ohlcv(pair, timeframe, limit=500)
                if df.empty:
                    continue
                df, features = generate_features(df)
                report = build_report(pair, timeframe, df, features, style)
                logger.info(f"✅ {pair}: Fresh report rebuilt after auto-rescan")
            
            # Reconstruct the dict that message_formatter expects
            es = report.executive_summary
            action = es.get("action", "WAIT")
            
            bull_prob = report.probability_model.get("bullish", 0)
            bear_prob = report.probability_model.get("bearish", 0)
            final_prob = max(bull_prob, bear_prob)
            
            conf = report.confidence_metrics
            decay_str = conf.get("decay_adj", "x1.0")
            try:
                decay_multi = float(decay_str.replace("×", "").replace("x", ""))
            except:
                decay_multi = 1.0
                
            final_score = final_prob * decay_multi
            
            data = {
                "pair": pair,
                "score": final_score,
                "action": action,
                "setup": report.trade_setup
            }
            
            # Send to analysis trigger
            process_and_alert(data, timeframe, disable_discord=not ENABLE_DISCORD)
            
        except Exception as e:
            logger.error(f"Failed to monitor {pair}: {e}")
            
    logger.info(f"Finished scheduled run on {timeframe}")
