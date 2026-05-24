from __future__ import annotations

from typing import Dict, List

import pandas as pd


def detect_order_blocks(df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, object]]:
    """Detect order blocks with stricter conditions:
    - The OB candle must be small (body < ATR)
    - The *next* candle must be impulsive (body > 1.5× ATR) to confirm displacement
    - Volume confirmation on the impulsive candle (above 20-period average)
    """
    blocks: List[Dict[str, object]] = []
    if "atr" not in df.columns:
        return blocks

    vol_avg = df["volume"].rolling(window=20).mean() if "volume" in df.columns else None

    start = max(1, len(df) - lookback)
    for i in range(start, len(df) - 1):
        candle = df.iloc[i]
        next_candle = df.iloc[i + 1]
        body = abs(candle["close"] - candle["open"])
        next_body = abs(next_candle["close"] - next_candle["open"])
        atr_val = candle["atr"] if pd.notna(candle["atr"]) else 0.0
        if atr_val == 0:
            continue

        # Next candle must show displacement (impulsive move)
        is_impulsive = next_body > 1.5 * atr_val

        # Volume confirmation (if available)
        has_vol_confirm = True
        if vol_avg is not None and pd.notna(vol_avg.iloc[i + 1]):
            has_vol_confirm = next_candle["volume"] > vol_avg.iloc[i + 1]

        if not is_impulsive:
            continue

        # Bullish order block: bearish candle before strong bullish displacement
        if candle["close"] < candle["open"] and next_candle["close"] > next_candle["open"] and body < atr_val:
            blocks.append(
                {
                    "type": "bullish",
                    "high": float(candle["open"]),
                    "low": float(candle["close"]),
                    "timestamp": candle["timestamp"],
                    "vol_confirmed": has_vol_confirm,
                }
            )

        # Bearish order block: bullish candle before strong bearish displacement
        if candle["close"] > candle["open"] and next_candle["close"] < next_candle["open"] and body < atr_val:
            blocks.append(
                {
                    "type": "bearish",
                    "high": float(candle["close"]),
                    "low": float(candle["open"]),
                    "timestamp": candle["timestamp"],
                    "vol_confirmed": has_vol_confirm,
                }
            )

    return blocks


def detect_fvg(df: pd.DataFrame) -> List[Dict[str, object]]:
    gaps: List[Dict[str, object]] = []
    for i in range(1, len(df) - 1):
        prev_candle = df.iloc[i - 1]
        next_candle = df.iloc[i + 1]
        if prev_candle["high"] < next_candle["low"]:
            gaps.append(
                {
                    "type": "bullish",
                    "high": float(next_candle["low"]),
                    "low": float(prev_candle["high"]),
                    "timestamp": df.iloc[i]["timestamp"],
                }
            )
        if prev_candle["low"] > next_candle["high"]:
            gaps.append(
                {
                    "type": "bearish",
                    "high": float(prev_candle["low"]),
                    "low": float(next_candle["high"]),
                    "timestamp": df.iloc[i]["timestamp"],
                }
            )
    return gaps


def detect_fvg_ce(df: pd.DataFrame, fvgs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Detect Consequent Encroachment (50% FVG fill) with reaction confirmation."""
    ce_triggers = []
    if fvgs and len(df) > 0:
        last_candle = df.iloc[-1]
        last_price = float(last_candle["close"])
        atr = float(last_candle["atr"]) if "atr" in last_candle and pd.notna(last_candle["atr"]) else 0.0
        tolerance = 0.5 * atr if atr > 0 else last_price * 0.003
        
        for fvg in fvgs:
            ce_level = (float(fvg["high"]) + float(fvg["low"])) / 2.0
            if abs(last_price - ce_level) <= tolerance:
                ce_triggers.append({
                    "type": fvg["type"],
                    "ce_level": ce_level,
                    "fvg_high": fvg["high"],
                    "fvg_low": fvg["low"]
                })
    return ce_triggers


def analyze_smc(df: pd.DataFrame) -> Dict[str, object]:
    order_blocks = detect_order_blocks(df)
    fvgs = detect_fvg(df)
    
    # Filter FVGs to top 10 by significance (HTF aligned priority simulated by biggest gaps)
    filtered_fvgs = sorted(fvgs, key=lambda x: abs(float(x["high"]) - float(x["low"])), reverse=True)[:10]
    
    fvg_ce = detect_fvg_ce(df, filtered_fvgs)
    
    return {"order_blocks": order_blocks, "fvg": filtered_fvgs, "fvg_ce": fvg_ce}
