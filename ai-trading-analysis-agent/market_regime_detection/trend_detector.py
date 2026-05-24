from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TrendState:
    direction: str
    strength: float


def detect_trend(df: pd.DataFrame, threshold: float = 0.0005) -> TrendState:
    last = df.iloc[-1]
    strength = float(last.get("trend_strength", 0.0))
    direction = "ranging"

    if strength > threshold and last["close"] > last["ema_slow"]:
        direction = "bullish"
    elif strength < -threshold and last["close"] < last["ema_slow"]:
        direction = "bearish"

    return TrendState(direction=direction, strength=abs(strength))
