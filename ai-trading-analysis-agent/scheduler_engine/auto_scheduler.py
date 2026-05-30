import argparse
import logging
import os
import sys
import time
from typing import List

# Ensure project root is on sys.path so package imports work
# even when this script is invoked directly (e.g. py -3 scheduler_engine/auto_scheduler.py)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
except ImportError:
    print("Error: apscheduler is not installed. Please run: pip install apscheduler")
    exit(1)

from scheduler_engine.market_monitor import monitor_pairs
from scanner import fetch_pairs_from_ctval

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("AutoScheduler")

# ── Default pair lists per market ────────────────────────────────────────
FOREX_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "NZD/USD", "USD/CAD",
               "EUR/GBP", "EUR/JPY", "GBP/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY",
               "EUR/AUD", "EUR/CAD", "EUR/CHF", "GBP/AUD", "GBP/CAD", "GBP/CHF"]

STOCK_PAIRS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
               "LLY", "V", "JPM", "WMT", "MA", "UNH", "JNJ", "PG", "HD", "ORCL", "COST", "CRM"]

INDEX_PAIRS = ["SPX500", "NAS100", "DJI30", "DAX40", "FTSE100", "JP225", "EU50",
               "FR40", "AU200", "US2000", "HK33", "IN50", "VIX", "DXY"]


def resolve_pairs(market: str) -> List[str]:
    """Build pair list based on selected market."""
    pairs = []
    if market in ["crypto", "all"]:
        pairs.extend(fetch_pairs_from_ctval("ctval.txt"))
    if market in ["forex", "all"]:
        pairs.extend(FOREX_PAIRS)
    if market in ["stocks", "all"]:
        pairs.extend(STOCK_PAIRS)
    if market in ["indexes", "all"]:
        pairs.extend(INDEX_PAIRS)
    return pairs


def make_job(market: str, timeframe: str, style: str):
    """Create a closure so APScheduler can call it without arguments."""
    def job():
        pairs = resolve_pairs(market)
        logger.info(f"⏰ Scheduled run: {len(pairs)} pairs | {market.upper()} | {timeframe} | {style}")
        monitor_pairs(pairs, timeframe, style)
    return job


def start_scheduler(args):
    logger.info("=" * 60)
    logger.info("🤖 AI Trading Auto-Scheduler")
    logger.info(f"   Market    : {args.market.upper()}")
    logger.info(f"   Timeframe : {args.timeframe}")
    logger.info(f"   Style     : {args.style}")
    logger.info(f"   Interval  : every {args.interval} minutes")
    logger.info("=" * 60)

    scheduler = BlockingScheduler()

    job_fn = make_job(args.market, args.timeframe, args.style)

    # Register the repeating job
    scheduler.add_job(job_fn, 'interval', minutes=args.interval,
                      id="main_scan", replace_existing=True)

    # Run immediately once (bootstrap)
    logger.info("🚀 Running initial bootstrap scan...")
    job_fn()

    logger.info(f"✅ Scheduler active — next run in {args.interval} minutes. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")


def main():
    parser = argparse.ArgumentParser(
        description="AI Trading Auto-Scheduler — Automatic scanner loop + notifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  py -3 scheduler_engine/auto_scheduler.py --timeframe 1h --style swing --interval 60
  py -3 scheduler_engine/auto_scheduler.py --market forex --timeframe 4h --style swing --interval 240
  py -3 scheduler_engine/auto_scheduler.py --market all --timeframe 15m --style scalping --interval 15
        """)

    parser.add_argument("--market", type=str, default="crypto",
                        choices=["crypto", "forex", "stocks", "indexes", "all"],
                        help="Target market to scan (default: crypto)")
    parser.add_argument("--timeframe", type=str, default="1h",
                        help="Analysis timeframe, e.g.: 5m, 15m, 1h, 4h, 1d (default: 1h)")
    parser.add_argument("--style", type=str, default="swing",
                        choices=["scalping", "intraday", "swing"],
                        help="Trading style (default: swing)")
    parser.add_argument("--interval", type=int, default=60,
                        help="Loop interval in MINUTES (default: 60)")

    args = parser.parse_args()
    start_scheduler(args)


if __name__ == "__main__":
    main()
