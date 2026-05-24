from __future__ import annotations

import argparse
import logging
from typing import Dict, List, Any, Tuple

import numpy as np
import pandas as pd
import yaml

from data_engine.market_data import fetch_ohlcv
from feature_engine.feature_extractor import generate_features
from feature_engine.structure_features import detect_swings
from analysis_engine.market_structure import analyze_market_structure
from analysis_engine.liquidity_analysis import analyze_liquidity
from analysis_engine.supply_demand import detect_supply_demand_zones
from analysis_engine.wyckoff_phase import detect_wyckoff_phase
from analysis_engine.smc_analysis import analyze_smc
from market_regime_detection.regime_classifier import classify_regime
from probability_engine.probability_model import score_direction
from probability_engine.scoring_engine import score_to_probabilities
from backtesting_engine.backtest_runner import run_backtest
from report_engine.analysis_report import AnalysisReport
from report_engine.report_formatter import format_report
from execution_engine.okx_integration import submit_okx_signal
from news_engine.sentiment_score import get_asset_sentiment
from news_engine.high_impact_filter import check_high_impact_window

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("ai-trading-analysis-agent")

STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "scalping": {
        "lookback": 25,
        "rr_min": 1.1,
        "buffer_atr": 0.2,
        "min_dist_pct": 0.0025,
        "range_buffer_pct": 0.008,
        "zone_pos_bull": 0.8,
        "zone_pos_bear": 0.2,
        "pullbacks": [0.382, 0.5],
        "tp_mults": [0.8, 1.2, 1.6],
    },
    "intraday": {
        "lookback": 80,
        "rr_min": 1.8,
        "buffer_atr": 0.55,
        "min_dist_pct": 0.007,
        "range_buffer_pct": 0.02,
        "zone_pos_bull": 0.5,
        "zone_pos_bear": 0.5,
        "pullbacks": [0.5, 0.618],
        "tp_mults": [1.0, 2.0, 3.0],
    },
    "swing": {
        "lookback": 150,
        "rr_min": 2.5,
        "buffer_atr": 0.6,
        "min_dist_pct": 0.01,
        "range_buffer_pct": 0.025,
        "zone_pos_bull": 0.2,
        "zone_pos_bear": 0.8,
        "pullbacks": [0.618, 0.705],
        "tp_mults": [1.5, 3.0, 4.5],
    },
}


def get_style_params(style: str | None) -> Dict[str, Any]:
    key = (style or "swing").strip().lower()
    return STYLE_PRESETS.get(key, STYLE_PRESETS["swing"])


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def premium_discount(df: pd.DataFrame) -> Dict[str, float]:
    last_swing_high = df["high"].rolling(window=20).max().iloc[-1]
    last_swing_low = df["low"].rolling(window=20).min().iloc[-1]
    premium = last_swing_low + 0.75 * (last_swing_high - last_swing_low)
    discount = last_swing_low + 0.25 * (last_swing_high - last_swing_low)
    return {"premium": float(premium), "discount": float(discount)}


def key_levels(df: pd.DataFrame, structure: Dict[str, object], liquidity: Dict[str, object], zones: List[Dict[str, object]], poc: float) -> List[Dict[str, object]]:
    # numpy imported at top-level
    
    raw_levels = []
    if structure.get("last_swing_high"):
        raw_levels.append(float(structure["last_swing_high"]))
    if structure.get("last_swing_low"):
        raw_levels.append(float(structure["last_swing_low"]))
    for pool in liquidity.get("buy_side_pools", []):
        raw_levels.append(float(pool.level))
    for pool in liquidity.get("sell_side_pools", []):
        raw_levels.append(float(pool.level))

    if not raw_levels:
        return []

    sorted_raw = sorted(set(raw_levels))
    clustered = []
    current_cluster = [sorted_raw[0]]
    for i in range(1, len(sorted_raw)):
        if (sorted_raw[i] - current_cluster[-1]) / current_cluster[-1] < 0.002: # 0.2%
            current_cluster.append(sorted_raw[i])
        else:
            clustered.append(float(np.mean(current_cluster)))
            current_cluster = [sorted_raw[i]]
    clustered.append(float(np.mean(current_cluster)))
    
    scored_levels = []
    pullbacks = pullback_zones(df)["zones"]
    last_price = float(df["close"].iloc[-1])
    
    for lvl in clustered:
        score = 0
        reasons = []
        
        for z in zones:
            if float(z["low"]) <= lvl <= float(z["high"]):
                score += 3
                z_type_raw = str(z.get("type", "Demand/Supply")).capitalize()
                
                if abs(lvl - last_price) / last_price < 0.005:  # 0.5% threshold
                    if z_type_raw == "Demand":
                        z_type = "Immediate Support / Minor Demand"
                    elif z_type_raw == "Supply":
                        z_type = "Immediate Resistance / Minor Supply"
                    else:
                        z_type = f"{z_type_raw} zone"
                else:
                    z_type = f"{z_type_raw} zone"
                    
                reasons.append(z_type)
                break
                
        for pb in pullbacks:
            if abs(lvl - pb) / pb < 0.005:
                score += 2
                reasons.append("Pullback zone")
                break
                
        if poc > 0 and abs(lvl - poc) / poc < 0.005:
            score += 2
            reasons.append("Volume POC proximity")
            
        if lvl % 1000 == 0 or lvl % 500 == 0:
            score += 1
            reasons.append("Round number")
            
        if structure.get("last_swing_low") and abs(lvl - float(structure["last_swing_low"])) < (last_price * 0.001):
            score += 2
            reasons.append("Structural invalidation")

        if score > 0:
            scored_levels.append({
                "price": lvl,
                "score": score,
                "reasons": " + ".join(reasons),
                "distance": abs(lvl - last_price)
            })
            
    scored_levels.sort(key=lambda x: (-x["score"], x["distance"]))
    return scored_levels[:3]


def pullback_zones(df: pd.DataFrame, fib_levels: List[float] | None = None) -> Dict[str, List[float]]:
    """Compute pullback zones using configurable Fibonacci levels."""
    if fib_levels is None:
        fib_levels = [0.5, 0.618]
    high = df["high"].rolling(window=20).max().iloc[-1]
    low = df["low"].rolling(window=20).min().iloc[-1]
    zones = [low + (high - low) * fib for fib in fib_levels]
    return {"zones": zones}


def momentum_snapshot(features: Dict[str, float]) -> Dict[str, float]:
    """Snapshot all momentum-related features for the report."""
    return {
        "rsi": features.get("rsi", 50.0),
        "macd_hist": features.get("macd_hist", 0.0),
        "momentum": features.get("momentum", 0.0),
        "roc_price": features.get("roc_price", 0.0),
        "roc_momentum": features.get("roc_momentum", 0.0),
        "bullish_divergence": features.get("bullish_divergence", 0.0),
        "bearish_divergence": features.get("bearish_divergence", 0.0),
        "rsi_bullish_hidden": features.get("rsi_bullish_hidden", 0.0),
        "rsi_bearish_hidden": features.get("rsi_bearish_hidden", 0.0),
        "macd_bullish_div": features.get("macd_bullish_div", 0.0),
        "macd_bearish_div": features.get("macd_bearish_div", 0.0),
    }


def market_bias(probabilities: Dict[str, float]) -> Dict[str, str]:
    if probabilities["bullish"] > probabilities["bearish"]:
        bias = "bullish"
    elif probabilities["bearish"] > probabilities["bullish"]:
        bias = "bearish"
    else:
        bias = "neutral"
    return {"bias": bias}


def swing_range(df: pd.DataFrame, lookback: int = 120) -> Tuple[float, float]:
    window = df.tail(min(lookback, len(df)))
    high = float(window["high"].max())
    low = float(window["low"].min())
    return high, low


def _zone_entry(zone: Dict[str, object], pos: float) -> float:
    low = float(zone["low"])
    high = float(zone["high"])
    return low + pos * (high - low)


def trade_setup(
    df: pd.DataFrame,
    structure: Dict[str, object],
    zones: List[Dict[str, object]],
    probabilities: Dict[str, float],
    style: str,
    timeframe: str,
    macro_context: Dict[str, Any],
    regime: str = "unknown",
) -> Dict[str, object]:
    params = get_style_params(style)

    swing_high, swing_low = swing_range(df, lookback=int(params["lookback"]))
    range_size = max(1e-9, swing_high - swing_low)
    last_price = float(df["close"].iloc[-1])

    atr_series = df.get("atr")
    atr = float(atr_series.dropna().iloc[-1]) if atr_series is not None and not atr_series.dropna().empty else 0.0
    buffer = atr * float(params["buffer_atr"]) if atr > 0 else range_size * float(params["range_buffer_pct"])
    min_dist = max(
        atr * float(params["buffer_atr"]),
        last_price * float(params["min_dist_pct"]),
        range_size * float(params["range_buffer_pct"]),
    )
    
    if style == "swing":
        min_dist = min(min_dist, last_price * 0.01)

    pullbacks = params.get("pullbacks", [0.5, 0.618])
    pb_levels = [swing_low + float(p) * range_size for p in pullbacks]

    demand = [z for z in zones if z["type"] == "demand"]
    supply = [z for z in zones if z["type"] == "supply"]

    def pick_long_entry() -> Tuple[float, Dict[str, object] | None]:
        candidates = [z for z in demand if float(z["high"]) <= last_price]
        if candidates:
            zone = max(candidates, key=lambda z: float(z["high"]))
            return _zone_entry(zone, float(params["zone_pos_bull"])), zone
        below = [c for c in pb_levels if c <= last_price]
        if below:
            return max(below), None
        return last_price - min_dist, None

    def pick_short_entry() -> Tuple[float, Dict[str, object] | None]:
        candidates = [z for z in supply if float(z["low"]) >= last_price]
        if candidates:
            zone = min(candidates, key=lambda z: float(z["low"]))
            return _zone_entry(zone, float(params["zone_pos_bear"])), zone
        above = [c for c in pb_levels if c >= last_price]
        if above:
            return min(above), None
        return last_price + min_dist, None

    rr_min = float(params["rr_min"])
    tp_mults = params.get("tp_mults", [1.0, rr_min, rr_min + 1.0])

    def build_side(direction: str, entry: float, zone: Dict[str, object] | None) -> Dict[str, float]:
        if direction == "long":
            if entry >= last_price:
                entry = max(swing_low, last_price - min_dist)
            entry = min(max(entry, swing_low), swing_high)
            
            if atr > 0:
                # Use structural SL when zone available, ATR as fallback/buffer
                if zone:
                    structural_sl = float(zone["low"]) - (0.3 * atr)
                    atr_sl = entry - (1.5 * atr)
                    stop = min(structural_sl, atr_sl)  # More conservative of the two
                else:
                    stop = entry - (1.5 * atr)
                tp1 = entry + (1.5 * atr)
                tp2 = entry + (3.0 * atr)
                tp3 = entry + (4.5 * atr)
            else:
                stop_base = float(zone["low"]) if zone else swing_low
                stop = stop_base - buffer
                risk = max(abs(entry - stop), min_dist)
                tp1 = entry + risk * float(tp_mults[0])
                tp2 = entry + risk * float(tp_mults[1])
                tp3 = entry + risk * float(tp_mults[2])

            if stop >= entry:
                stop = entry - min_dist
            
            # SL validation for LONG: Push stop loss below demand zone
            if zone:
                zone_low = float(zone["low"])
                if stop > zone_low:
                    stop = zone_low - (0.3 * atr if atr > 0 else zone_low * 0.003)
            
            risk = max(abs(entry - stop), min_dist)
            
            if atr == 0:
                if tp1 <= entry:
                    tp1 = entry + risk * float(tp_mults[0])
                if tp2 <= tp1:
                    tp2 = entry + risk * max(float(tp_mults[1]), float(tp_mults[0]) + 0.2)
                if tp3 <= tp2:
                    tp3 = entry + risk * max(float(tp_mults[2]), float(tp_mults[1]) + 0.4)
        else:
            if entry <= last_price:
                entry = min(swing_high, last_price + min_dist)
            entry = min(max(entry, swing_low), swing_high)
            
            if atr > 0:
                # Use structural SL when zone available, ATR as fallback/buffer
                if zone:
                    structural_sl = float(zone["high"]) + (0.3 * atr)
                    atr_sl = entry + (1.5 * atr)
                    stop = max(structural_sl, atr_sl)  # More conservative of the two
                else:
                    stop = entry + (1.5 * atr)
                tp1 = entry - (1.5 * atr)
                tp2 = entry - (3.0 * atr)
                tp3 = entry - (4.5 * atr)
            else:
                stop_base = float(zone["high"]) if zone else swing_high
                stop = stop_base + buffer
                risk = max(abs(entry - stop), min_dist)
                tp1 = entry - risk * float(tp_mults[0])
                tp2 = entry - risk * float(tp_mults[1])
                tp3 = entry - risk * float(tp_mults[2])

            if stop <= entry:
                stop = entry + min_dist
                
            # SL validation for SHORT: Push stop loss above supply zone
            if zone:
                zone_high = float(zone["high"])
                if stop < zone_high:
                    stop = zone_high + (0.3 * atr if atr > 0 else zone_high * 0.003)
                
            risk = max(abs(entry - stop), min_dist)
            
            if atr == 0:
                if tp1 >= entry:
                    tp1 = entry - risk * float(tp_mults[0])
                if tp2 >= tp1:
                    tp2 = entry - risk * max(float(tp_mults[1]), float(tp_mults[0]) + 0.2)
                if tp3 >= tp2:
                    tp3 = entry - risk * max(float(tp_mults[2]), float(tp_mults[1]) + 0.4)

        rr = abs((tp2 - entry) / (entry - stop)) if entry != stop else 0.0
        if rr < rr_min:
            if direction == "long":
                tp2 = entry + risk * rr_min
                tp3 = entry + risk * max(rr_min * 1.5, float(tp_mults[2]))
            else:
                tp2 = entry - risk * rr_min
                tp3 = entry - risk * max(rr_min * 1.5, float(tp_mults[2]))
            rr = abs((tp2 - entry) / (entry - stop)) if entry != stop else 0.0

        return {
            "entry": entry,
            "stop_loss": stop,
            "take_profit": tp2,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": round(rr, 2),
        }

    long_entry, long_zone = pick_long_entry()
    short_entry, short_zone = pick_short_entry()

    long_setup = build_side("long", long_entry, long_zone)
    short_setup = build_side("short", short_entry, short_zone)
    
    if atr > 0:
        req_dist = 1.5 * atr
        if long_entry > 0 and (long_setup["tp1"] - long_entry) < req_dist:
            long_setup["tp1"] = long_entry + req_dist
            long_setup["tp2"] = max(long_setup["tp2"], long_setup["tp1"] + atr)
            long_setup["tp3"] = max(long_setup["tp3"], long_setup["tp2"] + atr)
            long_setup["rr"] = abs(long_setup["tp2"] - long_entry) / abs(long_entry - long_setup["stop_loss"]) if long_entry != long_setup["stop_loss"] else 0
            
        if short_entry > 0 and (short_entry - short_setup["tp1"]) < req_dist:
            short_setup["tp1"] = short_entry - req_dist
            short_setup["tp2"] = min(short_setup["tp2"], short_setup["tp1"] - atr)
            short_setup["tp3"] = min(short_setup["tp3"], short_setup["tp2"] - atr)
            short_setup["rr"] = abs(short_entry - short_setup["tp2"]) / abs(short_entry - short_setup["stop_loss"]) if short_entry != short_setup["stop_loss"] else 0

    long_setup["probability"] = probabilities["bullish"]
    short_setup["probability"] = probabilities["bearish"]

    long_prob = probabilities["bullish"]
    short_prob = probabilities["bearish"]

    if probabilities["bullish"] > probabilities["bearish"]:
        preferred = "long"
        prob, opp_prob = long_prob, short_prob
    elif probabilities["bearish"] > probabilities["bullish"]:
        preferred = "short"
        prob, opp_prob = short_prob, long_prob
    else:
        preferred = "neutral"
        prob, opp_prob = 0.0, 0.0
        
    num = int(''.join(c for c in timeframe if c.isdigit()) or 1)
    unit = ''.join(c for c in timeframe if not c.isdigit()).lower()
    
    if unit == 'm': tf_hours = num / 60.0
    elif unit == 'd': tf_hours = num * 24.0
    elif unit == 'w': tf_hours = num * 24.0 * 7
    else: tf_hours = num
    
    # Scale validity proportionately to the lookback period of the active trading style
    validity_candles = max(10, int(params["lookback"]) * 0.6)
    validity_hours = tf_hours * validity_candles

    # Find the index of the actual swing points used for the trade setup
    # Use proper swing detection (detect_swings) to find the MOST RECENT
    # structural pivot, not absolute idxmax/idxmin which can pick very old extremes.
    lookback_window = df.tail(min(int(params["lookback"]), len(df)))
    swings_df = detect_swings(lookback_window, lookback=5)
    
    # Get indices of detected swing highs and swing lows
    sh_indices = swings_df[swings_df["swing_high"]].index
    sl_indices = swings_df[swings_df["swing_low"]].index
    
    # Most recent swing high / swing low index
    recent_sh_idx = sh_indices[-1] if len(sh_indices) > 0 else None
    recent_sl_idx = sl_indices[-1] if len(sl_indices) > 0 else None
    
    # Fallback to absolute max/min only if no swing points detected
    if recent_sh_idx is None:
        recent_sh_idx = lookback_window["high"].idxmax()
    if recent_sl_idx is None:
        recent_sl_idx = lookback_window["low"].idxmin()
    
    if preferred == "long":
        pivot_idx = recent_sl_idx
    elif preferred == "short":
        pivot_idx = recent_sh_idx
    else:
        # Neutral: use whichever swing point is more recent
        if recent_sh_idx is not None and recent_sl_idx is not None:
            pivot_idx = max(recent_sh_idx, recent_sl_idx)
        elif recent_sh_idx is not None:
            pivot_idx = recent_sh_idx
        elif recent_sl_idx is not None:
            pivot_idx = recent_sl_idx
        else:
            pivot_idx = df.index[-1]
        
    if pd.notna(pivot_idx):    
        candles_since_setup = len(df) - df.index.get_loc(pivot_idx) - 1
    else:
        candles_since_setup = 0
        
    hours_elapsed = candles_since_setup * tf_hours
    
    MATURE_HOURS_INTRADAY = 20
    # 1H and above uses swing (non-intraday) parameters
    is_intraday = tf_hours < 1.0
    
    if is_intraday:
        if hours_elapsed <= MATURE_HOURS_INTRADAY * 0.5:
            decay_multi = 1.0
            decay_status = "✅ FRESH"
        elif hours_elapsed <= MATURE_HOURS_INTRADAY:
            decay_multi = 0.9
            decay_status = "🟡 MATURE"
        elif hours_elapsed <= validity_hours * 0.90:
            decay_multi = max(0.0, 1.0 - ((hours_elapsed - MATURE_HOURS_INTRADAY) / max(1e-5, validity_hours - MATURE_HOURS_INTRADAY)))
            decay_status = "⚠️ DECAYING"
        elif hours_elapsed <= validity_hours:
            decay_multi = 0.01
            decay_status = "⏳ AUTO_RESCAN (Stale setup >=90% — forced rescan)"
        else:
            decay_multi = 0.0
            decay_status = "❌ EXPIRED"
    else:
        if hours_elapsed <= validity_hours * 0.40:
            decay_multi = 1.0
            decay_status = "✅ FRESH"
        elif hours_elapsed <= validity_hours * 0.65:
            # Gradual decay: 1.0 → 0.5 across MATURING window
            decay_multi = 1.0 - ((hours_elapsed - validity_hours * 0.40) / (validity_hours * 0.25)) * 0.5
            decay_status = "🟡 MATURING (Consider re-scanning for fresher setup)"
        elif hours_elapsed <= validity_hours * 0.90:
            decay_multi = 0.25
            decay_status = "⏳ AUTO_RESCAN (Stale setup — archiving & re-scanning)"
        elif hours_elapsed <= validity_hours:
            decay_multi = 0.01
            decay_status = "⏳ AUTO_RESCAN (Stale setup >=90% — forced rescan)"
        else:
            decay_multi = 0.0
            decay_status = "❌ EXPIRED"
        
    vix = macro_context.get("vix", 0.0)
    
    # Session / Volume Volatility Check
    import datetime
    is_weekend = datetime.datetime.now(datetime.timezone.utc).weekday() >= 5
    
    vol_state = "Normal"
    vol_moving_avg = float(df["volume"].rolling(20).mean().iloc[-1]) if "volume" in df.columns else 1.0
    current_vol = float(df["volume"].iloc[-1]) if "volume" in df.columns else 1.0
    
    is_low_vol = False
    if is_weekend:
        is_low_vol = True
        vol_state = "Low Volatility (Weekend)"
    elif current_vol < (vol_moving_avg * 0.75):
        is_low_vol = True
        vol_state = "Low Volatility (Resting/Asia)"
    elif current_vol > (vol_moving_avg * 1.2):
        vol_state = "High Volatility (London/NY Breakout)"
        
    # Regime-aware threshold: ranging markets produce more false signals
    if "ranging" in regime:
        base_threshold = 60.0
    else:
        base_threshold = 55.0
    no_trade_threshold = base_threshold + (10.0 if is_low_vol else 0.0)
    
    final_prob = prob * decay_multi
    decayed_opp = opp_prob * decay_multi  # Decay both sides for consistent spread
    spread = abs(final_prob - decayed_opp)

    if decay_multi == 0.0:
        action = "RECALIBRATING"
        conviction_str = f"⚪ NO TRADE (Data Outdated)"
        account_risk = 0.0
        risk_alloc_str = "CASH ONLY"
        final_prob = 0.0
    elif vix > 30.0:
        action = "RISK OFF"
        conviction_str = f"⚪ NO TRADE (Macro Extreme)"
        account_risk = 0.0
        risk_alloc_str = "CASH ONLY (SQUARE POSITIONS)"
        final_prob = 0.0
    elif spread < 5.0 and prob != 0:
        action = "NO TRADE"
        conviction_str = f"⚪ NEUTRAL (Spread < 5%)"
        account_risk = 0.0
        risk_alloc_str = "0% risk"
    elif final_prob > 65.0:
        action = "ENTER"
        conviction_str = f"🟢 HIGH ({final_prob:.1f}% vs {decayed_opp:.1f}%)"
        account_risk = 0.02
        risk_alloc_str = "Full size (2% risk)"
    elif final_prob >= no_trade_threshold:
        action = "REDUCE SIZE"
        conviction_str = f"🟠 MEDIUM ({final_prob:.1f}% vs {decayed_opp:.1f}%)"
        account_risk = 0.01
        risk_alloc_str = "50% size (1.0% risk)"
    else:
        action = "NO TRADE"
        conviction_str = f"🔴 NO TRADE ({final_prob:.1f}% — Below {no_trade_threshold}% Threshold)"
        account_risk = 0.0
        risk_alloc_str = "0% risk (NO ENTRY)"

    long_risk_pct = abs(long_entry - long_setup["stop_loss"]) / long_entry if long_entry > 0 else 0
    short_risk_pct = abs(short_entry - short_setup["stop_loss"]) / short_entry if short_entry > 0 else 0
    
    MAX_POSITION_PCT = 100.0  # Hard cap: never exceed 1x account equity
    long_setup["position_size_pct"] = min(
        round((account_risk / long_risk_pct) * 100, 2), MAX_POSITION_PCT
    ) if long_risk_pct > 0 and account_risk > 0 else 0.0
    short_setup["position_size_pct"] = min(
        round((account_risk / short_risk_pct) * 100, 2), MAX_POSITION_PCT
    ) if short_risk_pct > 0 and account_risk > 0 else 0.0

    return {
        "last_price": last_price,
        "preferred": preferred,
        "action": action,
        "conviction": conviction_str,
        "risk_alloc_str": risk_alloc_str,
        "long": long_setup,
        "short": short_setup,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "needs_rescan": decay_status.startswith("⏳"),
        "confidence_metrics": {
            "base_conviction": f"{prob:.1f}%",
            "decay_adj": f"×{decay_multi:.2f}",
            "final_conviction": f"{final_prob:.1f}% → Status: {action}",
            "structure_age": f"{hours_elapsed:.1f} jam ({(hours_elapsed/validity_hours)*100:.0f}% of validity) → {decay_status}"
        }
    }

def get_time_estimate(timeframe: str, multiplier_low: int = 3, multiplier_high: int = 5) -> str:
    from data_engine.market_data import normalize_timeframe
    tf = normalize_timeframe(timeframe)
    num_str = ""
    unit_str = ""
    for char in tf:
        if char.isdigit():
            num_str += char
        else:
            unit_str += char
    num = int(num_str) if num_str else 1
    unit = unit_str.lower()
    low_val = num * multiplier_low
    high_val = num * multiplier_high
    if unit == 'm':
        if high_val >= 60:
            if low_val >= 60:
                low_val, high_val = round(low_val / 60, 1), round(high_val / 60, 1)
                return f"±{low_val}-{high_val} jam"
        return f"±{low_val}-{high_val} menit"
    elif unit == 'h':
        if high_val >= 24:
            if low_val >= 24:
                low_val, high_val = round(low_val / 24, 1), round(high_val / 24, 1)
                return f"±{low_val}-{high_val} hari"
        return f"±{low_val}-{high_val} jam"
    elif unit == 'd':
        return f"±{low_val}-{high_val} hari"
    elif unit == 'w':
        return f"±{low_val}-{high_val} minggu"
    elif unit == 'mo':
        return f"±{low_val}-{high_val} bulan"
    return f"±{low_val}-{high_val} {unit}"

def entry_trigger(structure: Dict[str, object], setup: Dict[str, Any], fvg_ce: List[Dict[str, object]] = None) -> Dict[str, str]:
    if fvg_ce and len(fvg_ce) > 0 and not structure.get("bos") and not structure.get("choch"):
        ce = fvg_ce[0]
        trigger = f"Wait for LTF CHOCH (M5/M15) reaction at FVG CE level ${ce['ce_level']:.2f} before entry."
    elif structure.get("bos"):
        trigger = "Wait for pullback to the BOS level and bullish confirmation candle."
    elif structure.get("choch"):
        trigger = "Wait for CHOCH retest and rejection before entry."
    else:
        trigger = "Wait for liquidity sweep or strong momentum confirmation."
    return {"trigger": trigger}

def fetch_htf_trend(pair: str, timeframe: str) -> str:
    from data_engine.market_data import normalize_timeframe
    try:
        norm = normalize_timeframe(timeframe)
        mapping = {"1m": "5m", "3m": "15m", "5m": "15m", "15m": "1h", "30m": "2h", "1h": "4h", "2h": "1d", "3h": "1d", "4h": "1d", "1d": "1w", "1w": "1mo"}
        htf = mapping.get(norm, "1d")
        # Optimization: limit=100 to quickly fetch HTF structure
        df = fetch_ohlcv(pair, htf, limit=100)
        struct = analyze_market_structure(df)
        return struct.get("trend", "unknown")
    except Exception as e:
        logger.warning(f"Failed to fetch HTF data: {e}")
    return "unknown"

# ── Global Macro Context Cache ──────────────────────────────────────
# DXY/VIX/SPX data is the same for all pairs. Cache globally to avoid
# redundant API calls during bulk scanning (saves ~300 requests per scan).
import threading as _threading
_macro_cache: Dict[str, Any] = {}
_macro_cache_lock = _threading.Lock()
_macro_cache_timestamp: float = 0.0
_MACRO_CACHE_TTL = 300  # 5 minutes

def _fetch_global_macro() -> Dict[str, Any]:
    """Fetch DXY/VIX/SPX once and cache globally for all pairs."""
    global _macro_cache, _macro_cache_timestamp
    import time as _time
    
    with _macro_cache_lock:
        now = _time.time()
        if _macro_cache and (now - _macro_cache_timestamp) < _MACRO_CACHE_TTL:
            return dict(_macro_cache)
    
    macro: Dict[str, Any] = {}
    _dxy_df = None
    
    try:
        _dxy_df = fetch_ohlcv("INDEX:DXY", "1d", limit=30)
        macro["dxy"] = float(_dxy_df["close"].iloc[-1])
        macro["dxy_trend"] = "up" if _dxy_df["close"].iloc[-1] > _dxy_df["close"].iloc[-2] else "down"
        macro["_dxy_df"] = _dxy_df
    except Exception as e:
        logger.debug(f"Failed to fetch DXY: {e}")

    try:
        vix_df = fetch_ohlcv("CBOE:VIX", "1d", limit=30)
        macro["vix"] = float(vix_df["close"].iloc[-1])
        macro["vix_trend"] = "up" if vix_df["close"].iloc[-1] > vix_df["close"].iloc[-2] else "down"
    except Exception as e:
        logger.debug(f"Failed to fetch VIX: {e}")
    
    try:
        macro["_spx_df"] = fetch_ohlcv("OANDA:SPX500USD", "1d", limit=30)
    except Exception as e:
        logger.debug(f"Failed to fetch SPX: {e}")
    
    with _macro_cache_lock:
        _macro_cache = dict(macro)
        _macro_cache_timestamp = _time.time()
    
    return macro

def fetch_macro_context(pair: str) -> Dict[str, Any]:
    """Fetch macro context for a pair, using global cache for DXY/VIX/SPX."""
    global_macro = _fetch_global_macro()
    macro = {k: v for k, v in global_macro.items() if not k.startswith("_")}
    
    _dxy_df = global_macro.get("_dxy_df")
    spx_df = global_macro.get("_spx_df")
    
    # Per-pair correlation (BTC-DXY, BTC-SPX)
    try:
        target_pair = pair.replace("/", "") if "BINANCE:" not in pair else pair
        btc_df = fetch_ohlcv(f"BINANCE:{target_pair}", "1d", limit=30)
        
        if "close" in btc_df and "dxy" in macro and _dxy_df is not None:
            min_len = min(len(btc_df), len(_dxy_df))
            btc_slice = btc_df["close"].iloc[-min_len:].reset_index(drop=True)
            dxy_slice = _dxy_df["close"].iloc[-min_len:].reset_index(drop=True)
            corr = float(btc_slice.corr(dxy_slice))
            macro["btc_dxy_corr"] = corr if not pd.isna(corr) else 0.0
            
        if "close" in btc_df and spx_df is not None and "close" in spx_df:
            min_len = min(len(btc_df), len(spx_df))
            btc_slice = btc_df["close"].iloc[-min_len:].reset_index(drop=True)
            spx_slice = spx_df["close"].iloc[-min_len:].reset_index(drop=True)
            spx_corr = float(btc_slice.corr(spx_slice))
            macro["btc_spx_corr"] = spx_corr if not pd.isna(spx_corr) else 0.0
            
    except Exception as e:
        logger.debug(f"Failed to fetch BTC logic vectors: {e}")
        
    return macro

def generate_management_rules(timeframe: str, long_invalid: float, short_invalid: float) -> tuple[Dict[str, str], Dict[str, str]]:
    time_est = get_time_estimate(timeframe)
    mgmt = {
        "validity": f"3-5 candle ({time_est} pada {timeframe})",
        "long_invalidation": f"Close below ${long_invalid:.2f} (structural break)",
        "short_invalidation": f"Close above ${short_invalid:.2f} (supply break)",
        "timeout_rule": f"Jika tidak terjemput dalam {time_est.split(' ')[0]} → re-evaluate"
    }
    
    triggers = {
        "long": f"Liquidity sweep: Wick below ${long_invalid * 1.005:.2f} + close above ${(long_invalid * 1.01):.2f}\\nMomentum confirmation: MACD histogram expansion + volume >1.5x 20-period avg",
        "short": f"Rejection at supply: Close below ${(short_invalid * 0.99):.2f} after testing ${short_invalid * 0.995:.2f}+\\nBearish divergence: RSI lower high + price higher high"
    }
    return mgmt, triggers

def build_report(
    pair: str,
    timeframe: str,
    df: pd.DataFrame,
    features: Dict[str, float],
    style: str,
    fast: bool = False,
) -> AnalysisReport:
    regime = classify_regime(df)
    structure = analyze_market_structure(df)
    liquidity = analyze_liquidity(df)
    zones = detect_supply_demand_zones(df)
    wyckoff = detect_wyckoff_phase(df, regime.regime)
    smc = analyze_smc(df)

    # ── Resilient sub-calls: degrade gracefully instead of failing ──
    # Fast mode skips expensive API calls (HTF, news) for speed
    if fast:
        htf_trend = "unknown"
    else:
        try:
            htf_trend = fetch_htf_trend(pair, timeframe)
        except Exception as e:
            logger.warning(f"HTF trend fetch failed for {pair}: {e}")
            htf_trend = "unknown"
    
    try:
        if fast:
            # Fast mode: only use cached global macro (no per-pair correlation)
            global_macro = _fetch_global_macro()
            macro_context = {k: v for k, v in global_macro.items() if not k.startswith("_")}
        else:
            macro_context = fetch_macro_context(pair)
    except Exception as e:
        logger.warning(f"Macro context fetch failed for {pair}: {e}")
        macro_context = {}
    
    # News Sentiment (skipped in fast mode)
    if fast:
        news_data = {"score": 0.0, "status": "Skipped (fast mode)"}
        news_score = 0.0
    else:
        try:
            news_data = get_asset_sentiment(pair)
            news_score = news_data.get("score", 0.0)
        except Exception as e:
            logger.warning(f"News sentiment failed for {pair}: {e}")
            news_data = {"score": 0.0, "status": "Neutral (Error)"}
            news_score = 0.0

    score = score_direction(df, features, structure, liquidity, zones, regime.regime,
                            htf_trend=htf_trend, wyckoff=wyckoff, timeframe=timeframe, smc=smc,
                            news_sentiment=news_score)
    probabilities = score_to_probabilities(score)
    raw_probabilities = dict(probabilities)  # Snapshot BEFORE any penalties
    
    last_price = float(df["close"].iloc[-1])
    poc = features.get("poc", 0.0)
    vwap = features.get("vwap", 0.0)
    dxy_t = macro_context.get("dxy_trend", "n/a")
    vix = macro_context.get("vix", 0.0)
    
    # Weighting matrix: gradual adjustment based on POC distance (capped at 15%)
    bias_note = ""
    if probabilities["bullish"] > probabilities["bearish"]:
        if (poc > 0 and last_price < poc) and (vwap > 0 and last_price < vwap) and (dxy_t == 'up' or vix > 25):
            poc_dist = abs(last_price - poc) / last_price if last_price > 0 else 0
            adjustment = min(15.0, max(5.0, poc_dist * 500))  # 5-15% based on distance
            probabilities["bullish"] = max(0.0, probabilities["bullish"] - adjustment)
            probabilities["bearish"] = min(100.0, probabilities["bearish"] + adjustment)
            bias_note = f" (Downgraded -{adjustment:.0f}% due to Bearish Volume Flow)"
    elif probabilities["bearish"] > probabilities["bullish"]:
        if (poc > 0 and last_price > poc) and (vwap > 0 and last_price > vwap) and (dxy_t == 'down' or vix < 20):
            poc_dist = abs(last_price - poc) / last_price if last_price > 0 else 0
            adjustment = min(15.0, max(5.0, poc_dist * 500))  # 5-15% based on distance
            probabilities["bearish"] = max(0.0, probabilities["bearish"] - adjustment)
            probabilities["bullish"] = min(100.0, probabilities["bullish"] + adjustment)
            bias_note = f" (Downgraded -{adjustment:.0f}% due to Bullish Volume Flow)"
    
    # Initialize early so pre-computation logic can store warnings
    analysis_summary = {}
    _penalty_tracker = []  # Track ALL applied penalties: (name, side, amount)

    # ── Determine stable preferred direction ONCE from raw probabilities ──
    # This is the ANCHOR for all penalty applications.
    # Hysteresis buffer: require 3% spread to switch. Below that, use score direction.
    _raw_bull = probabilities["bullish"]
    _raw_bear = probabilities["bearish"]
    _raw_spread = _raw_bull - _raw_bear  # positive = bullish dominant
    
    if abs(_raw_spread) < 3.0:
        # Spread too narrow — use score direction (more stable, less noise)
        if score < -0.02:
            _initial_preferred_key = "bearish"
        elif score > 0.02:
            _initial_preferred_key = "bullish"
        else:
            _initial_preferred_key = "bearish" if _raw_bear >= _raw_bull else "bullish"
    else:
        _initial_preferred_key = "bullish" if _raw_spread > 0 else "bearish"

    # ── Data Source Fallback Penalty ──
    req_ex = df.attrs.get("exchange_requested", "UNKNOWN")
    use_ex = df.attrs.get("exchange_used", "UNKNOWN")
    has_fallback = (req_ex != use_ex) and (req_ex != "UNKNOWN") and (use_ex != "UNKNOWN")
    if has_fallback:
        fallback_warning = f"Requested {req_ex} but fell back to {use_ex}. Data anomalies possible."
        analysis_summary["fallback_warning"] = fallback_warning
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - 15.0)
        _penalty_tracker.append(("Data Fallback", _initial_preferred_key, 15.0))

    # ── VWAP/POC Divergence Penalty ──
    # Non-directional: reduces confidence in the preferred trade
    vwap_poc_penalty = 0.0
    vwap_val = features.get("vwap", 0.0)
    _has_vwap_poc_conflict = False
    if vwap_val > 0 and poc > 0:
        vwap_bias = "Bullish" if last_price > vwap_val else "Bearish"
        poc_bias = "Bullish" if last_price > poc else "Bearish"
        if vwap_bias != poc_bias:
            _has_vwap_poc_conflict = True
            divergence_pct = abs(vwap_val - poc) / max(vwap_val, poc)
            vwap_poc_penalty = min(10.0, max(5.0, divergence_pct * 200))
            probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - vwap_poc_penalty)
            _penalty_tracker.append(("VWAP/POC Divergence", _initial_preferred_key, vwap_poc_penalty))
                
    # ── OBV Hidden Divergence Penalty ──
    # Directional: specifically targets the conflicting side
    obv_val = features.get("obv", 0.0)
    obv_ema = features.get("obv_ema", 0.0)
    obv_trend = "Rising" if obv_val > obv_ema else "Falling"
    trend = structure.get("trend", "ranging")
    
    _has_obv_conflict = False
    obv_penalty_str = ""
    if trend == "bearish" and obv_trend == "Rising":
        _has_obv_conflict = True
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - 10.0)
        obv_penalty_str = " (Hidden Accumulation → Penalty: -10% conviction)"
        _penalty_tracker.append(("OBV Hidden Accumulation", _initial_preferred_key, 10.0))
    elif trend == "bullish" and obv_trend == "Falling":
        _has_obv_conflict = True
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - 10.0)
        obv_penalty_str = " (Hidden Distribution → Penalty: -10% conviction)"
        _penalty_tracker.append(("OBV Hidden Distribution", _initial_preferred_key, 10.0))

    # ── Counter-Trend Divergence Penalty ──
    # Directional: counter-trend divergence undermines the preferred direction
    _has_div_conflict = False
    div_penalty = 0.0
    _initial_pref_direction = "long" if _initial_preferred_key == "bullish" else "short"
    
    macd_bull_pre = features.get("macd_bullish_div")
    rsi_bull_pre = features.get("bullish_divergence")
    macd_bear_pre = features.get("macd_bearish_div")
    rsi_bear_pre = features.get("bearish_divergence")
    
    # Bullish div is counter-trend for short; Bearish div is counter-trend for long
    if _initial_pref_direction == "short" and (macd_bull_pre or rsi_bull_pre):
        _has_div_conflict = True
        div_penalty = 7.0
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - div_penalty)
        _penalty_tracker.append(("Counter-trend Divergence", _initial_preferred_key, div_penalty))
    elif _initial_pref_direction == "long" and (macd_bear_pre or rsi_bear_pre):
        _has_div_conflict = True
        div_penalty = 7.0
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - div_penalty)
        _penalty_tracker.append(("Counter-trend Divergence", _initial_preferred_key, div_penalty))

    # ── Momentum Exhaustion Penalty ──
    # Directional: exhaustion of momentum in the preferred direction
    _has_exhaustion = False
    exhaustion_penalty = 0.0
    roc_price = features.get("roc_price", 0.0)
    roc_momentum = features.get("roc_momentum", 0.0)
    # Bullish exhaustion: price up + momentum down → penalizes bullish preference
    # Bearish exhaustion: price down + momentum up → penalizes bearish preference
    if roc_price > 0 and roc_momentum < 0 and _initial_preferred_key == "bullish":
        _has_exhaustion = True
        exhaustion_penalty = 5.0
        probabilities["bullish"] = max(0.0, probabilities["bullish"] - exhaustion_penalty)
        _penalty_tracker.append(("Bullish Exhaustion", "bullish", exhaustion_penalty))
    elif roc_price < 0 and roc_momentum > 0 and _initial_preferred_key == "bearish":
        _has_exhaustion = True
        exhaustion_penalty = 5.0
        probabilities["bearish"] = max(0.0, probabilities["bearish"] - exhaustion_penalty)
        _penalty_tracker.append(("Bearish Exhaustion", "bearish", exhaustion_penalty))
    # Cross-direction exhaustion: exhaustion signal contrary to preferred → also penalize preferred
    elif roc_price > 0 and roc_momentum < 0 and _initial_preferred_key == "bearish":
        _has_exhaustion = True
        exhaustion_penalty = 5.0
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - exhaustion_penalty)
        _penalty_tracker.append(("Bullish Exhaustion (counter-preferred)", _initial_preferred_key, exhaustion_penalty))
    elif roc_price < 0 and roc_momentum > 0 and _initial_preferred_key == "bullish":
        _has_exhaustion = True
        exhaustion_penalty = 5.0
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - exhaustion_penalty)
        _penalty_tracker.append(("Bearish Exhaustion (counter-preferred)", _initial_preferred_key, exhaustion_penalty))

    # ── Wyckoff vs Ranging HTF: Explicit Penalty ──
    # Non-directional: unconfirmed Wyckoff → reduces preferred conviction
    _has_wyckoff_htf_conflict = False
    wyckoff_ranging_penalty = 0.0
    if wyckoff is not None and htf_trend in {"ranging", "unknown"}:
        _wk_phase = wyckoff.get("phase", "neutral")
        _wk_direction = {
            "accumulation": "bullish", "markup": "bullish",
            "distribution": "bearish", "markdown": "bearish",
        }.get(_wk_phase, "neutral")
        if _wk_direction != "neutral":
            _has_wyckoff_htf_conflict = True
            wyckoff_ranging_penalty = 5.0
            probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - wyckoff_ranging_penalty)
            _penalty_tracker.append((f"Wyckoff {_wk_phase} vs Ranging HTF", _initial_preferred_key, wyckoff_ranging_penalty))

    # ── Volatility Squeeze Conviction Penalty ──
    # Non-directional: squeeze = uncertain breakout direction → penalize preferred
    bb_w_pre = features.get("bb_width", 0.0)
    zscore_pre = features.get("bb_zscore", 0.0)
    _is_squeeze = zscore_pre < -1.0 or (bb_w_pre > 0 and bb_w_pre < 0.025)
    if _is_squeeze:
        squeeze_penalty = 5.0
        probabilities[_initial_preferred_key] = max(0.0, probabilities[_initial_preferred_key] - squeeze_penalty)
        _penalty_tracker.append(("Volatility Squeeze", _initial_preferred_key, squeeze_penalty))


    # ── High-Impact News Filter ──
    news_filter = check_high_impact_window()
    
    setup_data = trade_setup(df, structure, zones, probabilities, style, timeframe, macro_context,
                             regime=regime.regime)
    
    # Text Analysis Logic (reuse last_price/poc from above)
    if vwap_val > 0:
        analysis_summary["vwap"] = "Bullish (Price > VWAP)" if last_price > vwap_val else "Bearish (Price < VWAP)"
    else:
        analysis_summary["vwap"] = "N/A"

    if _has_obv_conflict:
        if obv_trend == "Rising":
            analysis_summary["obv"] = f"Hidden Accumulation detected{obv_penalty_str}"
        else:
            analysis_summary["obv"] = f"Hidden Distribution detected{obv_penalty_str}"
    else:
        analysis_summary["obv"] = f"Trend aligns with OBV ({obv_trend})"

    if poc > 0:
        dist_to_poc = abs(last_price - poc) / last_price
        if dist_to_poc < 0.005:
            analysis_summary["poc"] = "Trading near high-liquidity Value Area"
        else:
            analysis_summary["poc"] = "Price above POC (Bullish bias)" if last_price > poc else "Price below POC (Bearish bias)"
    else:
        analysis_summary["poc"] = "N/A"

    if _has_vwap_poc_conflict:
        if "Bearish" in analysis_summary.get("vwap", "") and "Bullish" in analysis_summary.get("poc", ""):
            analysis_summary["volume_conflict"] = f"⚠️ VWAP/POC Divergence: Price < VWAP but > POC — Penalty: -{vwap_poc_penalty:.0f}% conviction"
        elif "Bullish" in analysis_summary.get("vwap", "") and "Bearish" in analysis_summary.get("poc", ""):
            analysis_summary["volume_conflict"] = f"⚠️ VWAP/POC Divergence: Price > VWAP but < POC — Penalty: -{vwap_poc_penalty:.0f}% conviction"
        else:
            analysis_summary["volume_conflict"] = f"⚠️ VWAP/POC Divergence — Penalty: -{vwap_poc_penalty:.0f}% conviction"
    else:
        analysis_summary["volume_conflict"] = None

    zscore = features.get("bb_zscore", 0.0)
    bb_w = features.get("bb_width", 0.0)
    volatility_emoji = ""
    # Dual check: z-score AND raw BB Width for squeeze detection
    is_squeeze = zscore < -1.0 or (bb_w > 0 and bb_w < 0.025)
    if is_squeeze:
        analysis_summary["bb_width"] = f"🔶 Volatility Squeeze (BB Width: {bb_w:.4f}) — Tunggu arah breakout squeeze sebelum entry"
        analysis_summary["volatility_squeeze"] = True
        volatility_emoji = "🔶 Squeeze (pending breakout)"
    elif zscore > 1.0:
        analysis_summary["bb_width"] = "Volatility Expansion"
        analysis_summary["volatility_squeeze"] = False
        volatility_emoji = "📈 Expansion"
    else:
        analysis_summary["bb_width"] = "Normal Volatility"
        analysis_summary["volatility_squeeze"] = False
        volatility_emoji = "⚖️ Normal"
    
    # ── RSI Near-Oversold / Overbought Warning ──
    rsi_val = features.get("rsi", 50.0)
    if rsi_val < 40:
        analysis_summary["rsi_warning"] = f"⚠️ RSI {rsi_val:.2f} mendekati oversold — risiko bounce tiba-tiba untuk short setup"
    elif rsi_val > 60:
        analysis_summary["rsi_warning"] = f"⚠️ RSI {rsi_val:.2f} mendekati overbought — risiko rejection untuk long setup"
    else:
        analysis_summary["rsi_warning"] = None
    
    # ── Divergence Penalty Summary for Report ──
    if _has_div_conflict:
        analysis_summary["div_conflict"] = f"⚠️ Counter-trend divergence detected — Penalty: -{div_penalty:.0f}% conviction"
    
    # ── Exhaustion Summary for Report ──
    if _has_exhaustion:
        if roc_price > 0 and roc_momentum < 0:
            analysis_summary["exhaustion"] = f"⚠️ Bullish Exhaustion (Price ↑ Momentum ↓) — Penalty: -{exhaustion_penalty:.0f}% bullish conviction"
        else:
            analysis_summary["exhaustion"] = f"⚠️ Bearish Exhaustion (Price ↓ Momentum ↑) — Penalty: -{exhaustion_penalty:.0f}% bearish conviction"
    
    # ── Wyckoff vs Ranging HTF Summary for Report ──
    if _has_wyckoff_htf_conflict:
        _wk_phase_display = wyckoff.get("phase", "unknown") if wyckoff else "unknown"
        analysis_summary["wyckoff_htf_conflict"] = f"⚠️ Wyckoff {_wk_phase_display.title()} vs Ranging HTF — Penalty: -{wyckoff_ranging_penalty:.0f}% conviction (unconfirmed phase)"

    bias = market_bias(probabilities)["bias"] + bias_note
    trend_val = structure.get("trend", "ranging")
    if "bullish" in bias and (trend_val == "bearish" or htf_trend == "bearish"):
        conflict = "Bullish bias vs Bearish structure"
    elif "bearish" in bias and (trend_val == "bullish" or htf_trend == "bullish"):
        conflict = "Bearish bias vs Bullish structure"
    elif "neutral" in bias:
        conflict = "Neutral bias"
    else:
        conflict = "Aligned (No major conflict)"

    # Setup Trade Context Evaluator (Before Macro Output, so we can override size)
    
    dxy_t = macro_context.get("dxy_trend", "n/a")
    vix_val = macro_context.get("vix", 0.0)
    
    if vix_val > 30.0:
        vix_str = f"🔴 <b>CRITICAL:</b> {vix_val:.1f} (High Risk - Reduce Size/Square Positions)"
    elif vix_val < 20.0:
        vix_str = f"🟢 <b>Stable:</b> {vix_val:.1f} (Supportive baseline)"
    else:
        vix_str = f"⚪ <b>Neutral:</b> {vix_val:.1f}"
    asset_name = pair.split(":")[1] if ":" in pair else pair
    base_asset = asset_name.split("/")[0] if "/" in asset_name else asset_name

    corr = macro_context.get("btc_dxy_corr", 0.0)
    if corr < -0.5:
        corr_str = f"{base_asset}-DXY 30d corr: {corr:.2f} (Tailwind Valid)"
    else:
        corr_str = f"{base_asset}-DXY 30d corr: {corr:.2f} (Neutral/Weak)"
        
    spx_corr = macro_context.get("btc_spx_corr", 0.0)
    if spx_corr < 0.0:
        spx_str = f"Negative ({spx_corr:.2f}) - Potential Decoupling"
    else:
        spx_str = f"Positive ({spx_corr:.2f}) - {base_asset} tracking Equities"

    # Convert to the requested dashboard syntax
    if dxy_t == "down":
        dxy_str = f"🟢 <b>Bearish</b> (Tailwind for {base_asset})"
    elif dxy_t == "up":
        dxy_str = f"🔴 <b>Bullish</b> (Headwind for {base_asset})"
    else:
        dxy_str = f"⚪ <b>Neutral</b>"

    macro_tail = f"{dxy_str} | VIX: {vix_val:.1f}"
    
    # --- EXECUTION ADVICE LOGIC ---
    pd_zones = premium_discount(df)
    discount_lvl = pd_zones.get("discount", 0.0)
    premium_lvl = pd_zones.get("premium", 0.0)
    
    execution_advice = ""
    preferred_side = setup_data.get("preferred", "neutral")
    if preferred_side == "short" and last_price < discount_lvl and discount_lvl > 0:
        execution_advice += f"Jangan Market Sell sekarang! Harga sedang di area Discount (< ${discount_lvl:,.2f}). Tetap gunakan Short Limit di area Premium/Pullback. "
    elif preferred_side == "long" and last_price > premium_lvl and premium_lvl > 0:
        execution_advice += f"Jangan Market Buy sekarang! Harga sedang di area Premium (> ${premium_lvl:,.2f}). Tetap gunakan Long Limit di area Discount/Pullback. "
        
    macd_bull = features.get("macd_bullish_div")
    rsi_bull = features.get("bullish_divergence")
    macd_bear = features.get("macd_bearish_div")
    rsi_bear = features.get("bearish_divergence")
    
    if preferred_side == "short" and (macd_bull or rsi_bull):
        div_srcs = []
        if rsi_bull: div_srcs.append("RSI")
        if macd_bull: div_srcs.append("MACD")
        execution_advice += f"Risiko: Ada Bullish Divergence ({' & '.join(div_srcs)}). Ini peringatan bahwa harga kemungkinan besar akan memantul naik dulu sebelum lanjut turun."
    elif preferred_side == "long" and (macd_bear or rsi_bear):
        div_srcs = []
        if rsi_bear: div_srcs.append("RSI")
        if macd_bear: div_srcs.append("MACD")
        execution_advice += f"Risiko: Ada Bearish Divergence ({' & '.join(div_srcs)}). Ini peringatan bahwa harga kemungkinan besar akan koreksi turun dulu sebelum lanjut naik."
    
    # Override action if news filter blocks
    final_action = setup_data.get("action", "WAIT")
    if news_filter.get("blocked") and final_action == "ENTER":
        final_action = "NO TRADE"
        setup_data["action"] = final_action
        setup_data["conviction"] = f"🔴 NO TRADE (Blocked: {news_filter.get('event_name', 'Macro Event')} within 2h)"
        setup_data["risk_alloc_str"] = "0% risk (NEWS BLOCK)"
    
    # ── Volatility Squeeze: Suppress entry until breakout resolves ──
    if analysis_summary.get("volatility_squeeze") and final_action in ("ENTER", "REDUCE SIZE"):
        if final_action == "ENTER":
            final_action = "REDUCE SIZE"
            setup_data["action"] = final_action
            setup_data["conviction"] = setup_data.get("conviction", "").replace("🟢 HIGH", "🟠 MEDIUM (Squeeze Hold)")
            setup_data["risk_alloc_str"] = "25% size (0.5% risk) — Squeeze Active"
        else:  # REDUCE SIZE → NO TRADE
            final_action = "NO TRADE"
            setup_data["action"] = final_action
            setup_data["conviction"] = f"🔴 NO TRADE (Volatility Squeeze — Tunggu breakout)"
            setup_data["risk_alloc_str"] = "0% risk (SQUEEZE HOLD)"
        execution_advice += " 🔶 Volatility Squeeze aktif — entry ditunda sampai BB Width > 0.030 (breakout resolution)."
    
    executive_summary = {
        "action": final_action,
        "conviction": setup_data.get("conviction", "Unknown"),
        "conflict": conflict,
        "volatility": volatility_emoji,
        "macro": macro_tail,
        "dxy_str": dxy_str,
        "vix_str": vix_str,
        "corr_str": corr_str,
        "spx_str": spx_str,
        "bias": bias,
        "execution_advice": execution_advice.strip(),
        "news_filter": news_filter.get("status", "N/A"),
        "data_fallback_warning": analysis_summary.get("fallback_warning", None),
    }
    
    sl_long = setup_data.get("long", {}).get("stop_loss", 0.0) if setup_data.get("long") else 0.0
    sl_short = setup_data.get("short", {}).get("stop_loss", 0.0) if setup_data.get("short") else 0.0
    if not sl_long: sl_long = setup_data.get("swing_low", 0.0)
    if not sl_short: sl_short = setup_data.get("swing_high", 0.0)

    trade_mgmt, triggers = generate_management_rules(
        timeframe, 
        sl_long, 
        sl_short
    )
    
    trade_mgmt["structure_age"] = setup_data.get("confidence_metrics", {}).get("structure_age", "N/A")

    # Enrich confidence_metrics with penalty tracker totals
    _conf_metrics = setup_data.get("confidence_metrics", {})
    _preferred_side = setup_data.get("preferred", "neutral")
    
    # Compute penalties per side from tracker
    _bull_penalties = sum(p[2] for p in _penalty_tracker if p[1] == "bullish")
    _bear_penalties = sum(p[2] for p in _penalty_tracker if p[1] == "bearish")
    _total_all_penalties = _bull_penalties + _bear_penalties
    
    if _preferred_side == "long":
        _raw_conv = raw_probabilities.get("bullish", 0.0)
        _post_conv = probabilities.get("bullish", 0.0)
        _side_penalty = _bull_penalties
    elif _preferred_side == "short":
        _raw_conv = raw_probabilities.get("bearish", 0.0)
        _post_conv = probabilities.get("bearish", 0.0)
        _side_penalty = _bear_penalties
    else:
        _raw_conv = 0.0
        _post_conv = 0.0
        _side_penalty = 0.0
    
    # Build penalty breakdown string
    _penalty_details = []
    for pname, pside, pamt in _penalty_tracker:
        _penalty_details.append(f"{pname}: -{pamt:.0f}% ({pside})")
    _penalty_breakdown = " | ".join(_penalty_details) if _penalty_details else "None"
    
    _conf_metrics["pre_penalty_conviction"] = f"{_raw_conv:.1f}%"
    _conf_metrics["total_penalties"] = f"-{_total_all_penalties:.0f}% (Bull: -{_bull_penalties:.0f}%, Bear: -{_bear_penalties:.0f}%)"
    _conf_metrics["penalty_breakdown"] = _penalty_breakdown
    _conf_metrics["base_conviction"] = f"{_post_conv:.1f}% (raw: {_raw_conv:.1f}%, {_preferred_side} penalties: -{_side_penalty:.0f}%)"

    report = AnalysisReport(
        chart_context={"pair": pair, "timeframe": timeframe, "source": "TradingView", "style": style},
        macro_context=macro_context,
        multi_timeframe_context={
            "summary": f"Regime: {regime.regime} (confidence {regime.confidence:.2f})",
            "htf_trend": htf_trend,
        },
        market_structure=structure,
        wyckoff_phase=wyckoff,
        supply_demand=zones,
        volume_analysis={
            "vwap": features.get("vwap", 0.0),
            "obv": features.get("obv", 0.0),
            "poc": features.get("poc", 0.0),
        },
        volatility={
            "atr": features.get("atr", 0.0),
            "bb_width": features.get("bb_width", 0.0),
        },
        liquidity_analysis=liquidity,
        liquidity_map={},
        smc=smc,
        premium_discount=pd_zones,
        key_levels=key_levels(df, structure, liquidity, zones, features.get("poc", 0.0)),
        pullback_zones=pullback_zones(df, fib_levels=get_style_params(style).get("pullbacks")),
        momentum=momentum_snapshot(features),
        probability_model=probabilities,
        market_bias=market_bias(probabilities),
        trade_setup=setup_data,
        entry_trigger=entry_trigger(structure, setup_data, fvg_ce=smc.get("fvg_ce")),
        analysis_summary=analysis_summary,
        executive_summary=executive_summary,
        trade_management=trade_mgmt,
        confidence_metrics=_conf_metrics,
        specific_triggers=triggers,
    )

    report.backtest = run_backtest(df)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Trading Chart Analysis Agent")
    parser.add_argument("--pair", type=str, help="Trading pair or TV symbol, e.g., BTC/USDT or BINANCE:BTCUSDT")
    parser.add_argument("--timeframe", type=str, help="Timeframe, e.g., H4")
    parser.add_argument("--limit", type=int, help="Number of candles")
    parser.add_argument("--style", type=str, choices=["scalping", "intraday", "swing"], help="Trading style")
    parser.add_argument("--config", type=str, default="config/settings.yaml", help="Config file")
    parser.add_argument("--tv-user", type=str, help="TradingView username (optional)")
    parser.add_argument("--tv-pass", type=str, help="TradingView password (optional)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    pair = args.pair or cfg.get("pair")
    timeframe = args.timeframe or cfg.get("timeframe")
    limit = args.limit or cfg.get("limit", 500)
    style = args.style or cfg.get("trade_style", "swing")

    tv_user = args.tv_user or cfg.get("tv_username") or None
    tv_pass = args.tv_pass or cfg.get("tv_password") or None

    df = fetch_ohlcv(pair, timeframe, limit=limit, username=tv_user, password=tv_pass)
    df, features = generate_features(df)

    report = build_report(pair, timeframe, df, features, style)
    output = format_report(report)
    print(output)

    submit_okx_signal(report, pair, cfg)


if __name__ == "__main__":
    main()


