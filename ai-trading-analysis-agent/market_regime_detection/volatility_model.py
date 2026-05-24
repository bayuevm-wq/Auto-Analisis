from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class VolatilityState:
    level: str
    atr_value: float


def detect_volatility(df: pd.DataFrame) -> VolatilityState:
    atr_series = df["atr"].dropna()
    if atr_series.empty:
        return VolatilityState(level="unknown", atr_value=0.0)

    last_atr = float(atr_series.iloc[-1])
    median_atr = float(atr_series.median())
    level = "low" if last_atr < median_atr else "high"
    return VolatilityState(level=level, atr_value=last_atr)
