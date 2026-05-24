from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd


@dataclass
class StructureState:
    trend: str
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    prev_swing_high: Optional[float]
    prev_swing_low: Optional[float]
    bos: bool
    choch: bool


def detect_swings(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    window = lookback * 2 + 1
    swing_high = df["high"] == df["high"].rolling(window=window, center=True).max()
    swing_low = df["low"] == df["low"].rolling(window=window, center=True).min()

    df = df.copy()
    df["swing_high"] = swing_high.fillna(False)
    df["swing_low"] = swing_low.fillna(False)
    return df


def _last_two_swings(series: pd.Series, values: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    idxs = series[series].index
    if len(idxs) < 2:
        return None, None
    last = values.loc[idxs[-1]]
    prev = values.loc[idxs[-2]]
    return last, prev


def classify_structure(df: pd.DataFrame) -> StructureState:
    df = detect_swings(df)
    last_high, prev_high = _last_two_swings(df["swing_high"], df["high"])
    last_low, prev_low = _last_two_swings(df["swing_low"], df["low"])

    trend = "ranging"
    if last_high is not None and prev_high is not None and last_low is not None and prev_low is not None:
        if last_high > prev_high and last_low > prev_low:
            trend = "bullish"
        elif last_high < prev_high and last_low < prev_low:
            trend = "bearish"

    last_close = float(df["close"].iloc[-1])
    bos = False
    choch = False

    if trend == "bullish" and prev_high is not None:
        bos = last_close > prev_high
        if prev_low is not None:
            choch = last_close < prev_low
    elif trend == "bearish" and prev_low is not None:
        bos = last_close < prev_low
        if prev_high is not None:
            choch = last_close > prev_high

    return StructureState(
        trend=trend,
        last_swing_high=last_high,
        last_swing_low=last_low,
        prev_swing_high=prev_high,
        prev_swing_low=prev_low,
        bos=bos,
        choch=choch,
    )
