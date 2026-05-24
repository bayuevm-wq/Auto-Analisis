import logging
import uuid
from flask import Flask, request, jsonify, render_template
import traceback

from main import fetch_ohlcv, generate_features, build_report, load_config
from report_engine.report_formatter import format_report
from execution_engine.okx_integration import submit_okx_signal

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-trading-web")

# UUID-keyed cache to prevent race conditions between concurrent users
report_cache = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        data = request.json
        pair = data.get("pair", "DOGE/USDT")
        timeframe = data.get("timeframe", "15m")
        limit = int(data.get("limit", 500))
        style = data.get("style", "swing")

        # Config fallback
        cfg = load_config("config/settings.yaml")
        
        df = fetch_ohlcv(pair, timeframe, limit=limit)
        df, features = generate_features(df)
        
        report = build_report(pair, timeframe, df, features, style)
        formatted_report = format_report(report)
        
        # Save to cache with unique ID
        cache_id = str(uuid.uuid4())
        report_cache[cache_id] = {
            "report": report,
            "pair": pair,
            "cfg": cfg
        }

        # Cleanup old cache entries (keep max 50)
        if len(report_cache) > 50:
            oldest_keys = list(report_cache.keys())[:-50]
            for k in oldest_keys:
                report_cache.pop(k, None)

        # Extract minimal fields for UI
        setup = report.trade_setup
        struct = report.market_structure
        regime = report.multi_timeframe_context["summary"]
        es = getattr(report, "executive_summary", {})
        conf = getattr(report, "confidence_metrics", {})
        
        return jsonify({
            "success": True,
            "cache_id": cache_id,
            "formatted_report": formatted_report,
            "summary": {
                "pair": pair,
                "timeframe": timeframe,
                "price": setup["last_price"],
                "trend": struct.get("trend", "unknown"),
                "regime": regime,
                "preferred": setup["preferred"],
                "probability_bull": setup.get("long", {}).get("probability", 0),
                "probability_bear": setup.get("short", {}).get("probability", 0),
                "long_setup": setup.get("long"),
                "short_setup": setup.get("short")
            },
            "executive_summary": es,
            "confidence_metrics": conf
        })
    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/execute", methods=["POST"])
def execute():
    try:
        data = request.json
        side = data.get("side") # 'long' or 'short'
        leverage = data.get("leverage")
        order_size = data.get("order_size")
        cache_id = data.get("cache_id")
        
        if not cache_id or cache_id not in report_cache:
            return jsonify({"success": False, "error": "No recent analysis to execute. Run analyze first."})
            
        cache = report_cache[cache_id]
        report = cache["report"]
        pair = cache["pair"]
        cfg = cache["cfg"]

        # Override OKX config with user inputs for this specific execution
        if "okx" not in cfg:
            cfg["okx"] = {}
        
        cfg["okx"]["submit"] = side.lower()
        
        # Override inst_id dynamically to match the active chart pair
        # Handle formats: "BTC/USDT", "BTCUSDT", "BINANCE:BTCUSDT"
        raw_pair = pair.strip().upper()
        if ":" in raw_pair:
            raw_pair = raw_pair.split(":", 1)[1]
        raw_pair = raw_pair.replace("/", "")
        # Extract base asset by removing known quote suffixes
        base_asset = raw_pair
        for suffix in ("USDT", "USDC", "USD", "BUSD"):
            if raw_pair.endswith(suffix) and len(raw_pair) > len(suffix):
                base_asset = raw_pair[:-len(suffix)]
                break
        cfg["okx"]["inst_id"] = f"{base_asset}-USDT-SWAP"
        
        # Disable auto-leverage so the user's manual input from web is respected
        cfg["okx"]["auto_leverage"] = False 
        
        if leverage:
            cfg["okx"]["leverage"] = float(leverage)
        if order_size:
            cfg["okx"]["order_size"] = float(order_size)
            cfg["okx"]["order_notional"] = 0 # Force size mode
        
        submit_okx_signal(report, pair, cfg)
        return jsonify({"success": True, "message": f"Execution signal sent for {side.upper()} order!"})
    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    app.run(debug=True, port=5000)

