from __future__ import annotations

from typing import Dict

import pandas as pd


def detect_wyckoff_phase(df: pd.DataFrame, regime: str) -> Dict[str, object]:
    last = df.iloc[-1]
    phase = "neutral"
    signals = []

    if "trending-bullish" in regime:
        phase = "markup"
    elif "trending-bearish" in regime:
        phase = "markdown"
    elif "ranging" in regime:
        # Simple accumulation/distribution heuristic
        price_pos = (last["close"] - df["low"].min()) / (df["high"].max() - df["low"].min())
        if price_pos < 0.35 and last.get("rsi", 50) < 50:
            phase = "accumulation"
        else:
            phase = "distribution"

    # Optional signals
    if last["low"] < df["low"].rolling(window=20).min().iloc[-1] and last["close"] > last["open"]:
        signals.append("spring")
    if last["high"] > df["high"].rolling(window=20).max().iloc[-1] and last["close"] < last["open"]:
        signals.append("upthrust")

    return {"phase": phase, "signals": signals}
