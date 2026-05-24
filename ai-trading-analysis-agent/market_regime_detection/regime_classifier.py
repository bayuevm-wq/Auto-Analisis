from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .trend_detector import detect_trend
from .volatility_model import detect_volatility


@dataclass
class RegimeState:
    regime: str
    confidence: float


def classify_regime(df: pd.DataFrame) -> RegimeState:
    trend = detect_trend(df)
    volatility = detect_volatility(df)

    if trend.direction in {"bullish", "bearish"}:
        regime = f"trending-{trend.direction}"
        base_conf = 0.6
    else:
        regime = "ranging"
        base_conf = 0.5

    if volatility.level == "high":
        regime = f"{regime}-high-vol"
        base_conf += 0.1
    elif volatility.level == "low":
        regime = f"{regime}-low-vol"

    confidence = min(0.95, base_conf + trend.strength * 10)
    return RegimeState(regime=regime, confidence=confidence)
