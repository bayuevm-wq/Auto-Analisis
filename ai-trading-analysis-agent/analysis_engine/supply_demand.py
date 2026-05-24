from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _scan_zones(df: pd.DataFrame, body_threshold: float = 0.8) -> List[Dict[str, object]]:
    """Internal zone scanner with configurable body/ATR threshold.

    Detection criteria:
      - Primary: body > body_threshold * ATR (impulse candle)
      - Secondary: body > 0.5 * ATR + volume_spike (moderate + volume)
      - Fallback: engulfing pattern with body > 0.5 * ATR (structure-based)
    """
    zones: List[Dict[str, object]] = []

    if "atr" not in df.columns:
        return zones

    for i in range(1, len(df) - 1):
        candle = df.iloc[i]
        body = abs(candle["close"] - candle["open"])
        atr_val = candle["atr"] if pd.notna(candle["atr"]) else 0.0
        vol_spike = bool(candle.get("volume_spike", False))

        if atr_val == 0:
            continue

        # Relaxed detection: strong body alone OR moderate body + volume
        is_impulse = body > body_threshold * atr_val
        # Secondary threshold is always min(0.5, body_threshold) to stay proportional
        secondary_thresh = min(0.5, body_threshold)
        is_moderate_with_vol = body > secondary_thresh * atr_val and vol_spike

        # Engulfing fallback: current candle engulfs previous candle body
        prev_candle = df.iloc[i - 1]
        prev_body_high = max(prev_candle["open"], prev_candle["close"])
        prev_body_low = min(prev_candle["open"], prev_candle["close"])
        curr_body_high = max(candle["open"], candle["close"])
        curr_body_low = min(candle["open"], candle["close"])
        is_engulfing = (curr_body_high > prev_body_high and
                       curr_body_low < prev_body_low and
                       body > secondary_thresh * atr_val)

        if not (is_impulse or is_moderate_with_vol or is_engulfing):
            continue

        last_price = float(df.iloc[-1]["close"])
        zone_high = float(max(candle["open"], candle["close"]))
        zone_low = float(min(candle["open"], candle["close"]))

        if zone_high < last_price:
            zone_type = "demand"
        elif zone_low > last_price:
            zone_type = "supply"
        else:
            continue  # Price is inside, treat as neutral/spent

        # ── Mitigated zone check ──────────────────────────────────
        # A zone is mitigated only when a candle CLOSES through it,
        # not just a wick touch.  This prevents ranging-market zones
        # from being immediately invalidated by intra-bar noise.
        #   Demand: mitigated when a subsequent candle closes <= zone_low
        #   Supply: mitigated when a subsequent candle closes >= zone_high
        mitigated = False
        tested = False
        future_candles = df.iloc[i + 1:]
        if zone_type == "demand":
            # Full mitigation: close penetrates through zone
            if (future_candles["close"] <= zone_low).any():
                mitigated = True
            # Partial test: wick touched but didn't close through
            elif (future_candles["low"] <= zone_high).any():
                tested = True
        else:  # supply
            # Full mitigation: close penetrates through zone
            if (future_candles["close"] >= zone_high).any():
                mitigated = True
            # Partial test: wick touched but didn't close through
            elif (future_candles["high"] >= zone_low).any():
                tested = True

        if mitigated:
            continue  # Skip fully spent zones

        zones.append(
            {
                "type": zone_type,
                "high": zone_high,
                "low": zone_low,
                "timestamp": candle["timestamp"],
                "tested": tested,
            }
        )

    return zones


def detect_supply_demand_zones(df: pd.DataFrame) -> List[Dict[str, object]]:
    """Detect supply/demand zones with adaptive sensitivity.

    Uses a two-pass approach:
      1. Primary pass with 0.8 ATR threshold (strong impulse)
      2. If no supply OR no demand zones found, fallback pass with 0.4 ATR
         threshold to capture weaker but valid zones in ranging markets.
    """
    zones = _scan_zones(df, body_threshold=0.8)

    has_supply = any(z["type"] == "supply" for z in zones)
    has_demand = any(z["type"] == "demand" for z in zones)

    # Fallback: relax threshold if one side is completely empty
    if not has_supply or not has_demand:
        fallback_zones = _scan_zones(df, body_threshold=0.4)
        # Merge missing side(s) only
        existing_types = {z["type"] for z in zones}
        for fz in fallback_zones:
            if fz["type"] not in existing_types:
                zones.append(fz)

    return zones

