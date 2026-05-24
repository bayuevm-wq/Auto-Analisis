import argparse
import logging
import concurrent.futures
from collections import defaultdict
import time
import sys

# Suppress logging spam from tvDatafeed and werkzeug
logging.getLogger("tvDatafeed").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("ai-trading-analysis-agent").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("data_engine.tradingview_connector").setLevel(logging.ERROR)
logging.getLogger("data_engine.market_data").setLevel(logging.ERROR)

from main import fetch_ohlcv, generate_features, build_report

def fetch_pairs_from_ctval(file_path="ctval.txt"):
    pairs = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                pair_name = line.split(":")[0].strip()
                if pair_name.endswith("-USDT-SWAP"):
                    base = pair_name.replace("-USDT-SWAP", "")
                    pairs.append(f"{base}/USDT")
        return pairs
    except FileNotFoundError:
        print(f"Error: Could not find {file_path}")
        sys.exit(1)

def scan_pair(pair, timeframe, style, fast=True, retry_count=2):
    """Scan a single pair with retry logic and graceful degradation."""
    last_error = None
    
    for attempt in range(retry_count):
        try:
            # Fast mode: 200 candles is enough; full mode: 300
            limit = 200 if fast else 300
            df = fetch_ohlcv(pair, timeframe, limit=limit)
            if df is None or df.empty:
                return pair, None, "Failed to fetch data (empty DataFrame)"
                
            df, features = generate_features(df)
            report = build_report(pair, timeframe, df, features, style, fast=fast)
            
            # Extract conviction
            es = report.executive_summary
            action = es.get("action", "WAIT")
            conviction_str = es.get("conviction", "")
            
            # Get probabilities from report
            bull_prob = report.probability_model.get("bullish", 0)
            bear_prob = report.probability_model.get("bearish", 0)
            final_prob = max(bull_prob, bear_prob)
            
            # Decay multi logic
            conf = report.confidence_metrics
            decay_str = conf.get("decay_adj", "x1.0")
            try:
                decay_multi = float(decay_str.replace("×", "").replace("x", ""))
            except:
                decay_multi = 1.0
                
            final_score = final_prob * decay_multi
            
            return pair, {
                "pair": pair,
                "score": final_score,
                "action": action,
                "conviction": conviction_str,
                "bias": "LONG" if bull_prob > bear_prob else "SHORT",
                "price": float(df["close"].iloc[-1]),
                "setup": report.trade_setup
            }, None
            
        except ValueError as e:
            # Data not available — no point retrying
            return pair, None, str(e)
        except Exception as e:
            last_error = str(e)
            if attempt < retry_count - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
    
    return pair, None, f"Failed after {retry_count} attempts: {last_error}"

def format_price(p):
    if p is None: return "N/A"
    try:
        p = float(p)
    except:
        return str(p)
    if abs(p) >= 1000:
        return f"{p:.2f}"
    elif abs(p) >= 1.0:
        return f"{p:.4f}"
    elif abs(p) >= 0.01:
        return f"{p:.5f}"
    elif abs(p) >= 0.0001:
        return f"{p:.6f}"
    elif abs(p) >= 0.000001:
        return f"{p:.8f}"
    else:
        return f"{p:.10f}"

def main():
    parser = argparse.ArgumentParser(description="Bulk Market Scanner for AI Trading Agent")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g. 15m, 1h, 4h, 1d)")
    parser.add_argument("--style", type=str, default="swing", choices=["scalping", "intraday", "swing"], help="Trading style")
    parser.add_argument("--threads", type=int, default=4, help="Number of concurrent scanner threads (default: 4)")
    parser.add_argument("--market", type=str, default="crypto", choices=["crypto", "forex", "stocks", "indexes", "all"], help="Market to scan")
    parser.add_argument("--fast", action="store_true", default=True, help="Fast scan mode: skip HTF, news, per-pair correlation (default: on)")
    parser.add_argument("--full", action="store_true", help="Full analysis mode: include HTF trend, news, and correlations (slower)")
    args = parser.parse_args()

    # --full overrides --fast
    fast_mode = not args.full

    # Clamp threads to a safe range
    args.threads = max(1, min(args.threads, 8))

    print(f"Loading pairs for market: {args.market.upper()}")
    pairs = []
    if args.market in ["crypto", "all"]:
        pairs.extend(fetch_pairs_from_ctval())
    if args.market in ["forex", "all"]:
        pairs.extend(["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "NZD/USD", "USD/CAD", "EUR/GBP", "EUR/JPY", "GBP/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY", "EUR/AUD", "EUR/CAD", "EUR/CHF", "GBP/AUD", "GBP/CAD", "GBP/CHF"])
    if args.market in ["stocks", "all"]:
        pairs.extend(["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "LLY", "V", "JPM", "WMT", "MA", "UNH", "JNJ", "PG", "HD", "ORCL", "COST", "CRM"])
    if args.market in ["indexes", "all"]:
        pairs.extend(["SPX500", "NAS100", "DJI30", "DAX40", "FTSE100", "JP225", "EU50", "FR40", "AU200", "US2000", "HK33", "IN50", "SG30", "TWIX", "CN50", "CH20", "NL25", "ES35", "VIX", "DXY"])

    mode_str = "⚡ FAST" if fast_mode else "🔍 FULL"
    print(f"Found {len(pairs)} pairs to scan.")
    print(f"Mode: {mode_str} | Timeframe: {args.timeframe} | Style: {args.style} | Threads: {args.threads}")
    print("-" * 60)
    
    # ── Pre-warm global macro cache (DXY/VIX/SPX) ──
    print("Pre-loading macro context (DXY, VIX, SPX)...")
    try:
        from main import _fetch_global_macro
        _fetch_global_macro()
        print("✅ Macro context loaded.")
    except Exception as e:
        print(f"⚠️ Macro context pre-load failed (will use defaults): {e}")
    
    results = {
        "HIGH (>70%)": [],
        "MEDIUM (60-70%)": [],
        "LOW (50-60%)": [],
        "RISK OFF / HALTED": [],
        "ERROR": []
    }
    
    start_time = time.time()
    total = len(pairs)
    completed = 0
    success = 0
    
    # Run thread pool with controlled concurrency
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(scan_pair, pair, args.timeframe, args.style, fast_mode): pair for pair in pairs}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                pair, data, err = future.result(timeout=90)
            except concurrent.futures.TimeoutError:
                pair = futures[future]
                data, err = None, "Scan timed out after 90s"
            except Exception as e:
                pair = futures[future]
                data, err = None, f"Unexpected error: {str(e)}"
            
            completed += 1
            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (total - completed) / rate if rate > 0 else 0
            
            status_icon = "✓" if data else "✗"
            if data: success += 1
            sys.stdout.write(f"\r⏳ [{completed}/{total}] {status_icon} {pair:<12} | {success}✓ {completed-success}✗ | {rate:.1f}/s | ETA {eta:.0f}s      ")
            sys.stdout.flush()
            
            if err or not data:
                results["ERROR"].append((pair, err))
                continue
                
            action = data["action"]
            score = data["score"]
            
            if "RISK" in action or "HALT" in action or "RECALIBRATING" in action or score < 50.0:
                results["RISK OFF / HALTED"].append(data)
            elif score > 70.0:
                results["HIGH (>70%)"].append(data)
            elif score >= 60.0:
                results["MEDIUM (60-70%)"].append(data)
            else:
                results["LOW (50-60%)"].append(data)
                
    total_time = time.time() - start_time
    sys.stdout.write("\n")
    print("-" * 60)
    print(f"✅ SCAN COMPLETE in {total_time:.1f}s ({total_time/60:.1f} min) | {completed/total_time:.1f} pairs/sec")
    print("=" * 60)
    print(" 🎯 H I G H   C O N V I C T I O N  (> 70%) ")
    print("=" * 60)
    
    results["HIGH (>70%)"].sort(key=lambda x: x["score"], reverse=True)
    if not results["HIGH (>70%)"]:
        print("   No pairs found in this category.")
    else:
        for d in results["HIGH (>70%)"]:
            p = d["setup"]["long"] if d["bias"] == "LONG" else d["setup"]["short"]
            lp = format_price(d['setup']['last_price'])
            ent = format_price(p['entry'])
            sl = format_price(p['stop_loss'])
            tp = format_price(p['take_profit'])
            print(f" 🟢 {d['pair']:<12} | {d['setup']['preferred'].upper():5} | {d['score']:>4.1f}% | {lp:<10} -> Entry: {ent:<8} | SL: {sl:<8} | TP: {tp:<8}")

    print("\n" + "=" * 60)
    print(" 🟠 M E D I U M   C O N V I C T I O N  (60 - 70%) ")
    print("=" * 60)
    results["MEDIUM (60-70%)"].sort(key=lambda x: x["score"], reverse=True)
    if not results["MEDIUM (60-70%)"]:
        print("   No pairs found in this category.")
    else:
        for d in results["MEDIUM (60-70%)"]:
            p = d["setup"]["long"] if d["bias"] == "LONG" else d["setup"]["short"]
            lp = format_price(d['setup']['last_price'])
            ent = format_price(p['entry'])
            sl = format_price(p['stop_loss'])
            tp = format_price(p['take_profit'])
            print(f" 🟠 {d['pair']:<12} | {d['setup']['preferred'].upper():5} | {d['score']:>4.1f}% | {lp:<10} -> Entry: {ent:<8} | SL: {sl:<8} | TP: {tp:<8}")

    print("\n" + "=" * 60)
    print(" 🟡 L O W   C O N V I C T I O N  (50 - 60%) ")
    print("=" * 60)
    results["LOW (50-60%)"].sort(key=lambda x: x["score"], reverse=True)
    if not results["LOW (50-60%)"]:
        print("   No pairs found in this category.")
    else:
        for d in results["LOW (50-60%)"]:
            p = d["setup"]["long"] if d["bias"] == "LONG" else d["setup"]["short"]
            lp = format_price(d['setup']['last_price'])
            ent = format_price(p['entry'])
            sl = format_price(p['stop_loss'])
            tp = format_price(p['take_profit'])
            print(f" 🟡 {d['pair']:<12} | {d['setup']['preferred'].upper():5} | {d['score']:>4.1f}% | {lp:<10} -> Entry: {ent:<8} | SL: {sl:<8} | TP: {tp:<8}")

    print("\n" + "-" * 60)
    print(f" SUMMARY STATS")
    print("-" * 60)
    print(f" High Conviction   : {len(results['HIGH (>70%)'])} pairs")
    print(f" Medium Conviction : {len(results['MEDIUM (60-70%)'])} pairs")
    print(f" Low Conviction    : {len(results['LOW (50-60%)'])} pairs")
    print(f" Risk Off / Halted : {len(results['RISK OFF / HALTED'])} pairs")
    if results["ERROR"]:
        print(f" Failed/Errors     : {len(results['ERROR'])} pairs")
        print("-" * 60)
        print(" ERROR LOG (first 20):")
        for err_pair, err_msg in results["ERROR"][:20]:
            print(f" ❌ {err_pair:<12} | {err_msg}")
        if len(results["ERROR"]) > 20:
            print(f" ... and {len(results['ERROR']) - 20} more errors")
    else:
        print(f" Failed/Errors     : 0 pairs ✅")
    print("-" * 60)
    print(f" Total time: {total_time:.1f}s | Speed: {completed/total_time:.1f} pairs/sec")
    print(f" Mode: {mode_str} | Threads: {args.threads}")
    print("-" * 60)
    
if __name__ == "__main__":
    main()
